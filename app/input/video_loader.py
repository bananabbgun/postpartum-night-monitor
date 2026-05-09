from __future__ import annotations

from pathlib import Path
from typing import Iterator

import cv2

from app.types import FrameRecord


class VideoLoader:
    def __init__(self, video_path: Path) -> None:
        self.video_path = Path(video_path)

    def iter_frames(self, max_frames: int | None = None) -> Iterator[FrameRecord]:
        capture = cv2.VideoCapture(str(self.video_path))
        if not capture.isOpened():
            raise FileNotFoundError(f"Unable to open video: {self.video_path}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        frame_index = 0

        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if max_frames is not None and frame_index >= max_frames:
                    break
                yield FrameRecord(
                    index=frame_index,
                    timestamp_seconds=frame_index / fps,
                    frame=frame,
                    source_id=self.video_path.name,
                )
                frame_index += 1
        finally:
            capture.release()
