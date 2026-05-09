from __future__ import annotations

import cv2
import numpy as np

from app.types import DetectionResult


def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame.copy()


def detect_human_region(gray_frame: np.ndarray, threshold: int, area_threshold: int) -> DetectionResult:
    _, binary_mask = cv2.threshold(gray_frame, threshold, 255, cv2.THRESH_BINARY)
    human_mask = binary_mask > 0
    thermal_area = int(human_mask.sum())
    person_detected = thermal_area > area_threshold

    centroid_x = None
    centroid_y = None
    if person_detected:
        ys, xs = np.nonzero(human_mask)
        centroid_x = float(xs.mean())
        centroid_y = float(ys.mean())

    return DetectionResult(
        person_detected=person_detected,
        human_mask=human_mask,
        thermal_area=thermal_area,
        centroid_x=centroid_x,
        centroid_y=centroid_y,
    )
