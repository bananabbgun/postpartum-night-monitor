from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from app.types import EventRecord, FrameAnalysis


class DebugLogger:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.csv_path = output_dir / "frame_metrics.csv"
        self.jsonl_path = output_dir / "events.jsonl"

    def write_frame_metrics(self, analyses: list[FrameAnalysis]) -> Path:
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "frame_index",
                    "timestamp_seconds",
                    "bed_occupied",
                    "person_detected",
                    "thermal_area",
                    "local_motion_score",
                    "centroid_step",
                    "local_motion_mean",
                    "centroid_displacement",
                    "person_presence_ratio",
                    "primitive_state",
                    "in_bed_active_episode_seconds",
                    "out_of_bed_still_episode_seconds",
                    "out_of_bed_no_person_episode_seconds",
                ]
            )
            for analysis in analyses:
                writer.writerow(
                    [
                        analysis.frame.index,
                        analysis.frame.timestamp_seconds,
                        analysis.bed_status.bed_occupied,
                        analysis.detection.person_detected,
                        analysis.detection.thermal_area,
                        analysis.frame_metrics.local_motion_score,
                        analysis.frame_metrics.centroid_step,
                        analysis.window_metrics.local_motion_mean,
                        analysis.window_metrics.centroid_displacement,
                        analysis.window_metrics.person_presence_ratio,
                        analysis.window_metrics.primitive_state,
                        analysis.in_bed_active_episode_seconds,
                        analysis.out_of_bed_still_episode_seconds,
                        analysis.out_of_bed_no_person_episode_seconds,
                    ]
                )
        return self.csv_path

    def write_events(self, events: list[EventRecord]) -> Path:
        with self.jsonl_path.open("w", encoding="utf-8") as handle:
            for event in events:
                record = asdict(event)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.jsonl_path
