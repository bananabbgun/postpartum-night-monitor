from __future__ import annotations

from pathlib import Path
from typing import Iterator

import cv2

from app.types import FrameRecord


class ImageSequenceLoader:
    def __init__(self, image_dir: Path, fps: float = 5.0) -> None:
        self.image_dir = Path(image_dir)
        self.fps = fps

    def iter_frames(self, max_frames: int | None = None) -> Iterator[FrameRecord]:
        image_paths = sorted(self.image_dir.glob("*.png"))
        if not image_paths:
            raise FileNotFoundError(f"No PNG files found in {self.image_dir}")

        for index, image_path in enumerate(image_paths):
            if max_frames is not None and index >= max_frames:
                break
            frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            yield FrameRecord(
                index=index,
                timestamp_seconds=index / self.fps,
                frame=frame,
                source_id=image_path.name,
            )
