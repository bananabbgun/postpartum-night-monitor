from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class FrameRecord:
    index: int
    timestamp_seconds: float
    frame: np.ndarray
    source_id: str


@dataclass
class BedStatusRecord:
    timestamp_seconds: float
    bed_occupied: bool
    source: str = "mock"


@dataclass
class DetectionResult:
    person_detected: bool
    human_mask: np.ndarray
    thermal_area: int
    centroid_x: float | None
    centroid_y: float | None


@dataclass
class FrameMetrics:
    local_motion_score: float | None
    centroid_step: float | None


@dataclass
class WindowMetrics:
    local_motion_mean: float | None
    centroid_displacement: float | None
    person_presence_ratio: float | None
    primitive_state: str | None


@dataclass
class FrameAnalysis:
    frame: FrameRecord
    bed_status: BedStatusRecord
    detection: DetectionResult
    frame_metrics: FrameMetrics
    window_metrics: WindowMetrics
    in_bed_active_episode_seconds: float = 0.0
    out_of_bed_still_episode_seconds: float = 0.0
    out_of_bed_no_person_episode_seconds: float = 0.0


@dataclass
class VLMResult:
    source: str
    patient_judgment: str
    decision: str
    decision_reason: str
    summary: str
    possible_situations: list[str]
    recommended_action: str
    confidence: str
    raw_response: dict[str, Any] | None = None


@dataclass
class EventRecord:
    event_type: str
    risk_level: str
    room_id: str
    start_time_seconds: float
    duration_seconds: float
    bed_occupied: bool
    person_detected: bool
    primitive_state: str | None
    local_motion_mean: float | None
    vlm_result: VLMResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class PipelineResult:
    processed_frames: int
    events: list[EventRecord]
    debug_csv_path: Path | None
    events_jsonl_path: Path | None
