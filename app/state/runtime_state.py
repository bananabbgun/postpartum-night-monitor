from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from app.config import AppConfig
from app.detection.smoothing import CentroidWindowTracker, ScoreSmoother


@dataclass
class RuntimeState:
    prev_gray: np.ndarray | None = None
    prev_centroid: tuple[float, float] | None = None


class FrameWindowBuffer:
    """Keeps a rolling buffer of raw gray frames matching the short-window duration."""

    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, np.ndarray]] = deque()

    def add(self, timestamp_seconds: float, gray: np.ndarray) -> None:
        self._samples.append((timestamp_seconds, gray))
        min_timestamp = timestamp_seconds - self.window_seconds
        while self._samples and self._samples[0][0] < min_timestamp:
            self._samples.popleft()

    def sampled_frames(self, interval_seconds: float = 1.0) -> list[np.ndarray]:
        if not self._samples:
            return []
        result: list[np.ndarray] = []
        next_threshold = self._samples[0][0]
        for ts, frame in self._samples:
            if ts >= next_threshold:
                result.append(frame)
                next_threshold = ts + interval_seconds
        return result

    def clear(self) -> None:
        self._samples.clear()


class RuntimeContext:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.state = RuntimeState()
        self.local_motion_smoother = ScoreSmoother(config.smooth_window_seconds)
        self.centroid_tracker = CentroidWindowTracker(config.smooth_window_seconds)
        self.person_presence_smoother = ScoreSmoother(config.smooth_window_seconds)
        self.frame_buffer = FrameWindowBuffer(config.smooth_window_seconds)
