from __future__ import annotations

from pathlib import Path

from app.config import AppConfig, ensure_output_dirs
from app.detection.human_mask import detect_human_region, preprocess_frame
from app.detection.movement_score import compute_frame_metrics
from app.input.bed_label_loader import BedLabelLoader
from app.input.image_sequence_loader import ImageSequenceLoader
from app.input.video_loader import VideoLoader
from app.output.event_logger import DebugLogger
from app.rules.event_rules import EventDetector
from app.rules.motion_state import classify_primitive_state
from app.state.runtime_state import RuntimeContext
from app.types import FrameAnalysis, PipelineResult, WindowMetrics
from app.vlm.client import summarize_risk_event


def _build_frame_iterator(config: AppConfig):
    if config.input_mode == "video":
        return VideoLoader(config.video_path).iter_frames(config.max_frames)
    if config.input_mode == "image_sequence":
        return ImageSequenceLoader(config.image_dir).iter_frames(config.max_frames)
    raise ValueError(f"Unsupported input_mode: {config.input_mode}")


def run_pipeline(
    config: AppConfig,
    vlm_api_key: str | None = None,
    vlm_model: str = "gpt-4.1-mini",
) -> PipelineResult:
    ensure_output_dirs(config)
    bed_loader = BedLabelLoader(config.bed_label_path)
    context = RuntimeContext(config)
    event_detector = EventDetector(config)
    debug_logger = DebugLogger(config.output_dir)

    analyses: list[FrameAnalysis] = []
    events = []
    prev_timestamp = 0.0

    for frame in _build_frame_iterator(config):
        if frame.timestamp_seconds < config.start_seconds:
            continue
        if config.end_seconds is not None and frame.timestamp_seconds > config.end_seconds:
            break

        gray = preprocess_frame(frame.frame)
        bed_status = bed_loader.get_status(frame.timestamp_seconds)
        detection = detect_human_region(
            gray_frame=gray,
            threshold=config.grayscale_threshold,
            area_threshold=config.area_threshold,
        )

        frame_metrics = compute_frame_metrics(
            prev_gray=context.state.prev_gray,
            gray=gray,
            detection=detection,
            prev_centroid=context.state.prev_centroid,
        )

        local_motion_mean = context.local_motion_smoother.add(frame.timestamp_seconds, frame_metrics.local_motion_score)
        centroid_displacement, _ = context.centroid_tracker.add(frame.timestamp_seconds, detection.centroid_x, detection.centroid_y)
        person_presence_ratio = context.person_presence_smoother.add(
            frame.timestamp_seconds,
            1.0 if detection.person_detected else 0.0,
        )
        primitive_state = classify_primitive_state(
            local_motion_mean=local_motion_mean,
            centroid_displacement=centroid_displacement,
            person_presence_ratio=person_presence_ratio,
            motion_low_threshold=config.motion_low_threshold,
            still_centroid_threshold=config.still_centroid_threshold,
            centroid_low_threshold=config.centroid_low_threshold,
            centroid_high_threshold=config.centroid_high_threshold,
            person_presence_ratio_threshold=config.person_presence_ratio_threshold,
        )
        window_metrics = WindowMetrics(
            local_motion_mean=local_motion_mean,
            centroid_displacement=centroid_displacement,
            person_presence_ratio=person_presence_ratio,
            primitive_state=primitive_state,
        )

        context.frame_buffer.add(frame.timestamp_seconds, gray)

        dt = max(0.0, frame.timestamp_seconds - prev_timestamp)
        analysis = FrameAnalysis(
            frame=frame,
            bed_status=bed_status,
            detection=detection,
            frame_metrics=frame_metrics,
            window_metrics=window_metrics,
        )

        event = event_detector.check(analysis, dt=dt)
        (
            analysis.in_bed_active_episode_seconds,
            analysis.out_of_bed_still_episode_seconds,
            analysis.out_of_bed_no_person_episode_seconds,
        ) = event_detector.snapshot()
        analyses.append(analysis)

        if event is not None:
            window_frames = context.frame_buffer.sampled_frames(interval_seconds=1.0)
            vlm_result = summarize_risk_event(
                event=event,
                window_frames=window_frames,
                api_key=vlm_api_key,
                model=vlm_model,
            )
            event.vlm_result = vlm_result
            events.append(event)

        context.state.prev_gray = gray
        if detection.centroid_x is not None and detection.centroid_y is not None:
            context.state.prev_centroid = (detection.centroid_x, detection.centroid_y)
        prev_timestamp = frame.timestamp_seconds

    debug_csv_path = debug_logger.write_frame_metrics(analyses) if config.save_debug_csv else None
    events_jsonl_path = debug_logger.write_events(events) if config.save_events_jsonl else None

    return PipelineResult(
        processed_frames=len(analyses),
        events=events,
        debug_csv_path=debug_csv_path,
        events_jsonl_path=events_jsonl_path,
    )


def describe_result(result: PipelineResult) -> str:
    lines = [f"Processed frames: {result.processed_frames}", f"Events: {len(result.events)}"]
    if result.debug_csv_path is not None:
        lines.append(f"Frame metrics: {Path(result.debug_csv_path)}")
    if result.events_jsonl_path is not None:
        lines.append(f"Event log: {Path(result.events_jsonl_path)}")
    for event in result.events[:10]:
        lines.append(
            f"- {event.event_type} @ {event.start_time_seconds:.2f}s "
            f"for {event.duration_seconds:.2f}s ({event.risk_level})"
        )
    return "\n".join(lines)
