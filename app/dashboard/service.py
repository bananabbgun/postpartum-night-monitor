from __future__ import annotations

import csv
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import AppConfig
from app.main import run_pipeline
from app.types import EventRecord, VLMResult


@dataclass
class StateSegment:
    primitive_state: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    frame_count: int


@dataclass
class DashboardRunResult:
    risk_detected: bool
    processed_frames: int
    events: list[EventRecord]
    state_segments: list[StateSegment]
    frame_metrics_path: Path | None
    events_jsonl_path: Path | None
    vlm_result: VLMResult | None


def _write_constant_bed_label_csv(
    output_dir: Path,
    start_seconds: float,
    end_seconds: float | None,
    bed_occupied: bool,
) -> Path:
    csv_path = output_dir / "dashboard_bed_labels.csv"
    final_second = end_seconds if end_seconds is not None else start_seconds + 600.0
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_seconds", "bed_occupied"])
        writer.writerow([start_seconds, str(bed_occupied).lower()])
        writer.writerow([final_second, str(bed_occupied).lower()])
    return csv_path


def _read_frame_metrics(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _build_state_segments(rows: list[dict[str, str]]) -> list[StateSegment]:
    if not rows:
        return []

    segments: list[StateSegment] = []
    current_state = rows[0].get("primitive_state", "") or "unclassified"
    start_seconds = float(rows[0]["timestamp_seconds"])
    end_seconds = start_seconds
    frame_count = 1

    for row in rows[1:]:
        row_state = row.get("primitive_state", "") or "unclassified"
        row_time = float(row["timestamp_seconds"])
        if row_state == current_state:
            end_seconds = row_time
            frame_count += 1
            continue

        segments.append(
            StateSegment(
                primitive_state=current_state,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                duration_seconds=max(0.0, end_seconds - start_seconds),
                frame_count=frame_count,
            )
        )
        current_state = row_state
        start_seconds = row_time
        end_seconds = row_time
        frame_count = 1

    segments.append(
        StateSegment(
            primitive_state=current_state,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            duration_seconds=max(0.0, end_seconds - start_seconds),
            frame_count=frame_count,
        )
    )
    return segments


def analyze_uploaded_video(
    *,
    video_path: Path,
    room_id: str,
    bed_occupied: bool,
    start_seconds: float,
    end_seconds: float | None,
    smooth_window_seconds: float,
    motion_low_threshold: float,
    still_centroid_threshold: float,
    centroid_low_threshold: float,
    centroid_high_threshold: float,
    mixed_motion_tolerance_seconds: float,
    still_tolerance_seconds: float,
    in_bed_active_alert_seconds: float,
    out_of_bed_still_alert_seconds: float,
    out_of_bed_no_person_alert_seconds: float | None,
    grace_period_seconds: float,
    grayscale_threshold: int,
    area_threshold: int,
    openai_api_key: str | None,
    openai_model: str,
) -> DashboardRunResult:
    output_dir = Path(tempfile.mkdtemp(prefix="dashboard_run_"))
    bed_csv_path = _write_constant_bed_label_csv(output_dir, start_seconds, end_seconds, bed_occupied)

    config = AppConfig(
        input_mode="video",
        video_path=video_path,
        bed_label_path=bed_csv_path,
        output_dir=output_dir,
        room_id=room_id,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        smooth_window_seconds=smooth_window_seconds,
        motion_low_threshold=motion_low_threshold,
        still_centroid_threshold=still_centroid_threshold,
        centroid_low_threshold=centroid_low_threshold,
        centroid_high_threshold=centroid_high_threshold,
        mixed_motion_tolerance_seconds=mixed_motion_tolerance_seconds,
        still_tolerance_seconds=still_tolerance_seconds,
        in_bed_active_alert_seconds=in_bed_active_alert_seconds,
        out_of_bed_still_alert_seconds=out_of_bed_still_alert_seconds,
        out_of_bed_no_person_alert_seconds=out_of_bed_no_person_alert_seconds,
        grace_period_seconds=grace_period_seconds,
        grayscale_threshold=grayscale_threshold,
        area_threshold=area_threshold,
        max_frames=None,
        save_debug_csv=True,
        save_events_jsonl=True,
    )
    result = run_pipeline(config, vlm_api_key=openai_api_key, vlm_model=openai_model)
    risk_detected = len(result.events) > 0

    state_segments: list[StateSegment] = []
    if result.debug_csv_path is not None:
        rows = _read_frame_metrics(result.debug_csv_path)
        state_segments = _build_state_segments(rows)

    # VLM result is already attached to each event — surface the last triggered event's result
    vlm_result = result.events[-1].vlm_result if result.events else None

    return DashboardRunResult(
        risk_detected=risk_detected,
        processed_frames=result.processed_frames,
        events=result.events,
        state_segments=state_segments,
        frame_metrics_path=result.debug_csv_path,
        events_jsonl_path=result.events_jsonl_path,
        vlm_result=vlm_result,
    )
