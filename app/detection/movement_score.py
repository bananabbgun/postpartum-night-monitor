from __future__ import annotations

import numpy as np

from app.types import DetectionResult, FrameMetrics


def compute_frame_metrics(
    prev_gray: np.ndarray | None,
    gray: np.ndarray,
    detection: DetectionResult,
    prev_centroid: tuple[float, float] | None,
) -> FrameMetrics:
    if prev_gray is None:
        return FrameMetrics(local_motion_score=None, centroid_step=None)

    diff = np.abs(gray.astype(np.float32) - prev_gray.astype(np.float32))
    if detection.human_mask.any():
        local_motion_score = float(diff[detection.human_mask].mean())
    else:
        local_motion_score = float(diff.mean())

    centroid_step = None
    if prev_centroid is not None and detection.centroid_x is not None and detection.centroid_y is not None:
        dx = detection.centroid_x - prev_centroid[0]
        dy = detection.centroid_y - prev_centroid[1]
        centroid_step = float((dx * dx + dy * dy) ** 0.5)

    return FrameMetrics(
        local_motion_score=local_motion_score,
        centroid_step=centroid_step,
    )
