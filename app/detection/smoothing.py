from __future__ import annotations

from collections import deque
import math


class ScoreSmoother:
    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, float]] = deque()

    def add(self, timestamp_seconds: float, score: float | None) -> float | None:
        if score is None:
            return None
        self._samples.append((timestamp_seconds, score))
        min_timestamp = timestamp_seconds - self.window_seconds
        while self._samples and self._samples[0][0] < min_timestamp:
            self._samples.popleft()
        return sum(sample_score for _, sample_score in self._samples) / len(self._samples)

    def clear(self) -> None:
        self._samples.clear()


class CentroidWindowTracker:
    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, float, float]] = deque()

    def add(
        self,
        timestamp_seconds: float,
        centroid_x: float | None,
        centroid_y: float | None,
    ) -> tuple[float | None, float | None]:
        if centroid_x is None or centroid_y is None:
            return None, None
        self._samples.append((timestamp_seconds, centroid_x, centroid_y))
        min_timestamp = timestamp_seconds - self.window_seconds
        while self._samples and self._samples[0][0] < min_timestamp:
            self._samples.popleft()
        oldest = self._samples[0]
        dx = centroid_x - oldest[1]
        dy = centroid_y - oldest[2]
        displacement = math.sqrt(dx * dx + dy * dy)

        path_length = 0.0
        previous = None
        for _, sample_x, sample_y in self._samples:
            if previous is not None:
                step_dx = sample_x - previous[0]
                step_dy = sample_y - previous[1]
                path_length += math.sqrt(step_dx * step_dx + step_dy * step_dy)
            previous = (sample_x, sample_y)
        consistency = 0.0 if path_length == 0.0 else displacement / path_length
        return displacement, consistency

    def clear(self) -> None:
        self._samples.clear()
