from __future__ import annotations

from dataclasses import dataclass, field

from app.config import AppConfig
from app.types import EventRecord, FrameAnalysis


@dataclass
class EventDetector:
    config: AppConfig
    _in_bed_active_duration: float = field(default=0.0, init=False, repr=False)
    _in_bed_active_mixed_gap: float = field(default=0.0, init=False, repr=False)
    _in_bed_active_still_gap: float = field(default=0.0, init=False, repr=False)
    _in_bed_alerted: bool = field(default=False, init=False, repr=False)
    _out_of_bed_still_duration: float = field(default=0.0, init=False, repr=False)
    _out_of_bed_still_mixed_gap: float = field(default=0.0, init=False, repr=False)
    _out_of_bed_still_alerted: bool = field(default=False, init=False, repr=False)
    _out_of_bed_no_person_duration: float = field(default=0.0, init=False, repr=False)
    _out_of_bed_no_person_alerted: bool = field(default=False, init=False, repr=False)

    def snapshot(self) -> tuple[float, float, float]:
        return (
            self._in_bed_active_duration,
            self._out_of_bed_still_duration,
            self._out_of_bed_no_person_duration,
        )

    def _reset_in_bed_active(self) -> None:
        self._in_bed_active_duration = 0.0
        self._in_bed_active_mixed_gap = 0.0
        self._in_bed_active_still_gap = 0.0
        self._in_bed_alerted = False

    def _reset_out_of_bed_still(self) -> None:
        self._out_of_bed_still_duration = 0.0
        self._out_of_bed_still_mixed_gap = 0.0
        self._out_of_bed_still_alerted = False

    def _reset_out_of_bed_no_person(self) -> None:
        self._out_of_bed_no_person_duration = 0.0
        self._out_of_bed_no_person_alerted = False

    def check(self, analysis: FrameAnalysis, dt: float) -> EventRecord | None:
        ts = analysis.frame.timestamp_seconds
        bed_occupied = analysis.bed_status.bed_occupied
        person_detected = analysis.detection.person_detected
        primitive_state = analysis.window_metrics.primitive_state
        local_motion_mean = analysis.window_metrics.local_motion_mean

        if bed_occupied:
            self._reset_out_of_bed_still()
            self._reset_out_of_bed_no_person()

            if primitive_state == "in_place_active":
                self._in_bed_active_duration += dt
                self._in_bed_active_mixed_gap = 0.0
                self._in_bed_active_still_gap = 0.0
            elif self._in_bed_active_duration > 0.0 and primitive_state == "mixed_motion":
                self._in_bed_active_mixed_gap += dt
                self._in_bed_active_still_gap = 0.0
                if self._in_bed_active_mixed_gap <= self.config.mixed_motion_tolerance_seconds:
                    self._in_bed_active_duration += dt
                else:
                    self._reset_in_bed_active()
            elif self._in_bed_active_duration > 0.0 and primitive_state == "still":
                self._in_bed_active_still_gap += dt
                self._in_bed_active_mixed_gap = 0.0
                if self._in_bed_active_still_gap <= self.config.still_tolerance_seconds:
                    self._in_bed_active_duration += dt
                else:
                    self._reset_in_bed_active()
            else:
                self._reset_in_bed_active()

            if (
                self._in_bed_active_duration >= self.config.in_bed_active_alert_seconds
                and not self._in_bed_alerted
            ):
                self._in_bed_alerted = True
                return EventRecord(
                    event_type="bed_in_place_active",
                    risk_level="yellow",
                    room_id=self.config.room_id,
                    start_time_seconds=max(0.0, ts - self._in_bed_active_duration),
                    duration_seconds=self._in_bed_active_duration,
                    bed_occupied=True,
                    person_detected=person_detected,
                    primitive_state=primitive_state,
                    local_motion_mean=local_motion_mean,
                )
            return None

        self._reset_in_bed_active()

        if ts < self.config.grace_period_seconds:
            return None

        if primitive_state == "still":
            self._out_of_bed_still_duration += dt
            self._out_of_bed_still_mixed_gap = 0.0
        elif self._out_of_bed_still_duration > 0.0 and primitive_state == "mixed_motion":
            self._out_of_bed_still_mixed_gap += dt
            if self._out_of_bed_still_mixed_gap <= self.config.mixed_motion_tolerance_seconds:
                self._out_of_bed_still_duration += dt
            else:
                self._reset_out_of_bed_still()
        else:
            self._reset_out_of_bed_still()

        if primitive_state == "no_person":
            self._out_of_bed_no_person_duration += dt
        else:
            self._reset_out_of_bed_no_person()

        if (
            self._out_of_bed_still_duration >= self.config.out_of_bed_still_alert_seconds
            and not self._out_of_bed_still_alerted
        ):
            self._out_of_bed_still_alerted = True
            return EventRecord(
                event_type="out_of_bed_stillness",
                risk_level="red",
                room_id=self.config.room_id,
                start_time_seconds=max(0.0, ts - self._out_of_bed_still_duration),
                duration_seconds=self._out_of_bed_still_duration,
                bed_occupied=False,
                person_detected=True,
                primitive_state=primitive_state,
                local_motion_mean=local_motion_mean,
            )

        if (
            self.config.out_of_bed_no_person_alert_seconds is not None
            and self._out_of_bed_no_person_duration >= self.config.out_of_bed_no_person_alert_seconds
            and not self._out_of_bed_no_person_alerted
        ):
            self._out_of_bed_no_person_alerted = True
            return EventRecord(
                event_type="out_of_bed_no_person",
                risk_level="yellow",
                room_id=self.config.room_id,
                start_time_seconds=max(0.0, ts - self._out_of_bed_no_person_duration),
                duration_seconds=self._out_of_bed_no_person_duration,
                bed_occupied=False,
                person_detected=False,
                primitive_state=primitive_state,
                local_motion_mean=local_motion_mean,
            )

        return None
