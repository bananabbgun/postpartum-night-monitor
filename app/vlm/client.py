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


def _build_event_frame_times(
    event: EventRecord,
    video_duration_seconds: float,
) -> list[float]:
    start_seconds = max(0.0, event.start_time_seconds)
    end_seconds = min(video_duration_seconds, event.start_time_seconds + max(event.duration_seconds, 0.0))

    if event.event_type == "bed_in_place_active":
        return _evenly_spaced_times(start_seconds, end_seconds, max_frames=10, fps_hint=2.0)

    if event.event_type == "out_of_bed_stillness":
        transition_start = max(0.0, start_seconds - 2.0)
        transition_end = min(video_duration_seconds, start_seconds + 2.0)
        return _evenly_spaced_times(transition_start, transition_end, max_frames=8, fps_hint=2.0)

    if event.event_type == "out_of_bed_no_person":
        transition_start = max(0.0, start_seconds - 2.0)
        transition_end = min(video_duration_seconds, start_seconds + 2.0)
        return _evenly_spaced_times(transition_start, transition_end, max_frames=6, fps_hint=1.5)

    return _evenly_spaced_times(start_seconds, end_seconds, max_frames=8, fps_hint=2.0)


def _extract_event_frames(
    video_path: Path | None,
    event: EventRecord,
) -> list[np.ndarray]:
    if video_path is None:
        return []

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0 or total_frames <= 0:
        capture.release()
        return []

    duration_seconds = total_frames / fps
    target_times = _build_event_frame_times(event, duration_seconds)
    frames: list[np.ndarray] = []
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
    finally:
        capture.release()
    return frames


def _fallback_summary(event: EventRecord, reason: str | None = None) -> VLMResult:
    if event.event_type == "bed_in_place_active":
        patient_judgment = "病人在床上持續活動，可能有躁動、不適或需要協助。"
        decision = "nurse_review"
        decision_reason = "在床活動 episode 已持續超過設定門檻，代表這不是短暫小動作。"
        situations = [
            "持續性躁動",
            "疼痛或不適",
            "需要協助但無法明確表達",
        ]
        action = "請護理師查看病人目前狀況，確認是否有疼痛、不適、情緒不安或立即照護需求。"
    elif event.event_type == "out_of_bed_stillness":
        patient_judgment = "病人離床後持續靜止，可能無法自行起身或有跌倒風險。"
        decision = "immediate_nurse_support"
        decision_reason = "離床後靜止 episode 已持續超過安全門檻，需要立即確認病人狀態。"
        situations = [
            "可能跌倒",
            "可能暈厥",
            "離床後無法自行起身",
        ]
        action = "請立即查看病人，確認是否跌倒、意識是否清楚，以及是否需要立即協助。"
    else:
        patient_judgment = "病人的位置或活動狀態不夠明確，需要人工確認。"
        decision = "nurse_review"
        decision_reason = "系統無法從目前 episode 確認穩定且安全的活動模式。"
        situations = [
            "病人位置不明",
            "偵測暫時不穩定",
            "活動模式超出預期",
        ]
        action = "請人工檢視最近影像內容，確認病人目前位置與狀態。"

    summary = (
        f"系統觸發事件：{event.event_type}。"
        f"觸發當下的 primitive 狀態為：{event.primitive_state}。"
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

    frame_b64 = _encode_frames(_extract_event_frames(video_path, event))
    if not frame_b64:
        return _fallback_summary(event, reason="No frames were available for VLM analysis.")

    try:
        prompt = (
            "你是一個產後夜間監測輔助系統。"
            "不要做疾病診斷，也不要下醫療定論。"
            "你會看到事件發生附近的影像幀，以及結構化感測資訊。"
            "請判斷病人目前最可能的狀態，並給出適合護理人員的處置建議。"
            "請用繁體中文回答，並只輸出 JSON。"
            "JSON 必須包含以下欄位："
            "patient_judgment, decision, decision_reason, summary, possible_situations, recommended_action, confidence。"
            "decision 請只使用以下其中一個值："
            "normal_observation, continue_monitoring, nurse_review, immediate_nurse_support。"
        )

        sensor_text = json.dumps(
            {
                "event_type": event.event_type,
                "risk_level": event.risk_level,
                "bed_occupied": event.bed_occupied,
                "duration_seconds": event.duration_seconds,
                "primitive_state": event.primitive_state,
                "local_motion_mean": event.local_motion_mean,
            },
            ensure_ascii=False,
        )

        parts: list[dict[str, Any]] = [
            {"text": prompt},
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
            "generationConfig": {
                "responseMimeType": "application/json",
            },
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
            raw_response=raw,
        )
    except Exception as exc:
        return _fallback_summary(event, reason=f"Gemini request failed: {type(exc).__name__}: {exc}")
