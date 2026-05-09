from __future__ import annotations


def classify_primitive_state(
    local_motion_mean: float | None,
    centroid_displacement: float | None,
    person_presence_ratio: float | None,
    motion_low_threshold: float,
    still_centroid_threshold: float,
    centroid_low_threshold: float,
    centroid_high_threshold: float,
    person_presence_ratio_threshold: float,
) -> str | None:
    if local_motion_mean is None:
        return None

    if (
        person_presence_ratio is not None
        and person_presence_ratio < person_presence_ratio_threshold
    ):
        return "no_person"

    if local_motion_mean < motion_low_threshold and (
        centroid_displacement is None or centroid_displacement <= still_centroid_threshold
    ):
        return "still"

    if centroid_displacement is None:
        return "mixed_motion"

    if centroid_displacement <= centroid_low_threshold:
        return "in_place_active"

    if centroid_displacement >= centroid_high_threshold:
        return "relocating"

    return "mixed_motion"
