from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

from app.types import EventRecord, VLMResult


GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _encode_frames(frames: list[np.ndarray]) -> list[str]:
    images: list[str] = []
    for frame in frames:
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        images.append(base64.b64encode(encoded.tobytes()).decode("ascii"))
    return images


def _evenly_spaced_times(start_seconds: float, end_seconds: float, max_frames: int, fps_hint: float) -> list[float]:
    if end_seconds <= start_seconds:
        return [start_seconds]
    duration = end_seconds - start_seconds
    desired = max(1, min(max_frames, int(math.ceil(duration * fps_hint))))
    if desired == 1:
        return [start_seconds]
    step = duration / (desired - 1)
    return [start_seconds + idx * step for idx in range(desired)]


def _build_event_frame_times(event: EventRecord, video_duration_seconds: float) -> list[float]:
    start_seconds = max(0.0, event.start_time_seconds)
    end_seconds = min(video_duration_seconds, event.start_time_seconds + max(event.duration_seconds, 0.0))

    if event.event_type == "bed_in_place_active":
        return _evenly_spaced_times(start_seconds, end_seconds, max_frames=10, fps_hint=2.0)

    if event.event_type == "out_of_bed_stillness":
        transition_start = max(0.0, start_seconds - 3.5)
        transition_end = min(video_duration_seconds, start_seconds + 0.5)
        return _evenly_spaced_times(transition_start, transition_end, max_frames=8, fps_hint=2.0)

    if event.event_type == "out_of_bed_no_person":
        transition_start = max(0.0, start_seconds - 2.0)
        transition_end = min(video_duration_seconds, start_seconds + 1.0)
        return _evenly_spaced_times(transition_start, transition_end, max_frames=6, fps_hint=1.5)

    return _evenly_spaced_times(start_seconds, end_seconds, max_frames=8, fps_hint=2.0)


def _extract_event_frames(video_path: Path | None, event: EventRecord) -> tuple[list[np.ndarray], list[float]]:
    if video_path is None:
        return [], []

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return [], []

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0 or total_frames <= 0:
        capture.release()
        return [], []

    duration_seconds = total_frames / fps
    target_times = _build_event_frame_times(event, duration_seconds)
    frames: list[np.ndarray] = []
    used_times: list[float] = []
    seen_indices: set[int] = set()
    try:
        for second in target_times:
            frame_index = min(max(int(round(second * fps)), 0), total_frames - 1)
            if frame_index in seen_indices:
                continue
            seen_indices.add(frame_index)
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if ok:
                frames.append(frame)
                used_times.append(frame_index / fps)
    finally:
        capture.release()
    return frames, used_times


def _build_prompt(event: EventRecord) -> str:
    base = (
        "你是產後夜間熱成像監測的臨床輔助摘要系統。"
        "你不是診斷工具，不要直接下疾病診斷。"
        "請根據提供的熱成像 frames 與結構化事件資訊，判斷這段影像比較像正常現象還是需要護理關注。"
        "只輸出 JSON，不要輸出任何額外說明。"
        "JSON 欄位必須包含："
        "patient_judgment, decision, decision_reason, summary, possible_situations, recommended_action, confidence。"
        "decision 只能是以下其中之一："
        "normal_observation, continue_monitoring, nurse_review, immediate_nurse_support。"
    )

    if event.event_type == "bed_in_place_active":
        return (
            base
            + "這次事件是在床上持續原地動作。"
            + "請重點判斷這比較像正常翻身、短暫調整姿勢，還是持續躁動、疼痛不適、掙扎或需要護理協助。"
            + "請特別留意動作是否持續、是否集中在原地、是否看起來不安穩。"
        )

    if event.event_type == "out_of_bed_stillness":
        return (
            base
            + "這次事件是離床後進入靜止。"
            + "提供的畫面重點是靜止前 3.5 秒到靜止開始後 0.5 秒。"
            + "請重點判斷病人是正常停下、主動坐下休息，還是像突然倒下、蹲下後無法起身、疼痛導致不動等需要立即關注的情況。"
            + "請特別描述靜止是如何發生的。"
        )

    if event.event_type == "out_of_bed_no_person":
        return (
            base
            + "這次事件是離床後畫面中看不到人。"
            + "請判斷比較像正常走出畫面、短暫遮擋，還是可能位置不明需要查看。"
        )

    return base


def _fallback_summary(event: EventRecord, reason: str | None = None) -> VLMResult:
    if event.event_type == "bed_in_place_active":
        patient_judgment = "病人在床上持續原地活動，可能是持續不適或躁動，也可能只是短時間的姿勢調整。"
        decision = "nurse_review"
        decision_reason = "系統偵測到在床上的原地活動 episode 已達警報門檻，需要護理人員再確認是否為異常不適。"
        situations = [
            "正常翻身或姿勢調整",
            "疼痛、不適或焦躁",
            "需要協助但無法自行處理",
        ]
        action = "請先查看病人目前狀態，確認是否只是正常翻身；若動作持續或看起來不安穩，建議護理師介入評估。"
    elif event.event_type == "out_of_bed_stillness":
        patient_judgment = "病人離床後進入靜止，需判斷這是主動停下還是因突發狀況導致不動。"
        decision = "immediate_nurse_support"
        decision_reason = "系統偵測到離床後靜止 episode 已達警報門檻，存在跌倒、疼痛或無法起身等風險。"
        situations = [
            "突然跌倒後不動",
            "蹲下或坐下後無法起身",
            "因疼痛或頭暈而停住",
        ]
        action = "請立即查看病人是否清醒、能否回應、是否需要攙扶或進一步醫療協助。"
    else:
        patient_judgment = "系統偵測到需要關注的事件，但目前缺少足夠影像資訊進一步判讀。"
        decision = "nurse_review"
        decision_reason = "事件已達警報條件，但 VLM 未取得可用影像結果，需人工確認。"
        situations = [
            "正常移動超出畫面",
            "短暫遮擋",
            "真實異常事件但影像不足",
        ]
        action = "請人工查看影像與病人現況，再決定是否需要進一步處置。"

    summary = (
        f"事件類型：{event.event_type}；"
        f"primitive 狀態：{event.primitive_state}；"
        f"風險等級：{event.risk_level}。"
    )
    raw_response = {"fallback_reason": reason} if reason else None
    return VLMResult(
        source="fallback",
        patient_judgment=patient_judgment,
        decision=decision,
        decision_reason=decision_reason,
        summary=summary,
        possible_situations=situations,
        recommended_action=action,
        confidence="medium",
        raw_response=raw_response,
    )


def summarize_risk_event(
    *,
    event: EventRecord,
    video_path: Path | None,
    api_key: str | None,
    model: str,
) -> VLMResult:
    if not api_key:
        return _fallback_summary(event, reason="No Gemini API key was provided.")

    frames, frame_times = _extract_event_frames(video_path, event)
    frame_b64 = _encode_frames(frames)
    if not frame_b64:
        return _fallback_summary(event, reason="No frames were available for VLM analysis.")

    try:
        sensor_text = json.dumps(
            {
                "event_type": event.event_type,
                "risk_level": event.risk_level,
                "bed_occupied": event.bed_occupied,
                "duration_seconds": event.duration_seconds,
                "primitive_state": event.primitive_state,
                "local_motion_mean": event.local_motion_mean,
                "frame_times_seconds": [round(t, 2) for t in frame_times],
            },
            ensure_ascii=False,
        )

        parts: list[dict[str, Any]] = [
            {"text": _build_prompt(event)},
            {"text": sensor_text},
        ]
        for image_b64 in frame_b64:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_b64,
                    }
                }
            )

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        response = requests.post(
            GEMINI_GENERATE_CONTENT_URL.format(model=model),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        raw = response.json()

        output_text = ""
        for candidate in raw.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if text:
                    output_text += text
        parsed = json.loads(output_text) if output_text else {}
        return VLMResult(
            source="gemini",
            patient_judgment=parsed.get("patient_judgment", ""),
            decision=parsed.get("decision", ""),
            decision_reason=parsed.get("decision_reason", ""),
            summary=parsed.get("summary", ""),
            possible_situations=parsed.get("possible_situations", []),
            recommended_action=parsed.get("recommended_action", ""),
            confidence=parsed.get("confidence", "unknown"),
            raw_response={
                "gemini_response": raw,
                "frame_times_seconds": [round(t, 2) for t in frame_times],
            },
        )
    except Exception as exc:
        return _fallback_summary(event, reason=f"Gemini request failed: {type(exc).__name__}: {exc}")
