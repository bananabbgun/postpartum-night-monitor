from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_VIDEO_PATH = ROOT_DIR / "Thermal camera video-20260502T062433Z-3-001" / "Thermal camera video" / "moving.mp4"
DEFAULT_IMAGE_DIR = ROOT_DIR / "archive" / "Thermal_Dataset_Fall_Non_Fall"
DEFAULT_BED_LABEL_PATH = ROOT_DIR / "app" / "mocks" / "sample_bed_labels.csv"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs"


@dataclass
class AppConfig:
    input_mode: str = "video"
    video_path: Path = DEFAULT_VIDEO_PATH
    image_dir: Path = DEFAULT_IMAGE_DIR
    bed_label_path: Path = DEFAULT_BED_LABEL_PATH
    output_dir: Path = DEFAULT_OUTPUT_DIR
    room_id: str = "demo-room"
    start_seconds: float = 0.0
    end_seconds: float | None = None
    smooth_window_seconds: float = 1.0
    grayscale_threshold: int = 90
    area_threshold: int = 5
    motion_low_threshold: float = 4.0
    centroid_low_threshold: float = 30.0
    centroid_high_threshold: float = 70.0
    person_presence_ratio_threshold: float = 0.4
    mixed_motion_tolerance_seconds: float = 0.5
    still_tolerance_seconds: float = 0.5
    in_bed_active_alert_seconds: float = 4.0
    out_of_bed_still_alert_seconds: float = 4.0
    out_of_bed_no_person_alert_seconds: float | None = None
    grace_period_seconds: float = 30.0
    max_frames: int | None = 300
    save_debug_csv: bool = True
    save_events_jsonl: bool = True


def ensure_output_dirs(config: AppConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
