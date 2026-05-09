from __future__ import annotations

import csv
from bisect import bisect_right
from pathlib import Path

from app.types import BedStatusRecord


class BedLabelLoader:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = Path(csv_path)
        self._timestamps: list[float] = []
        self._records: list[BedStatusRecord] = []
        self._load()

    def _load(self) -> None:
        with self.csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                timestamp_seconds = float(row["timestamp_seconds"])
                bed_occupied = row["bed_occupied"].strip().lower() == "true"
                record = BedStatusRecord(
                    timestamp_seconds=timestamp_seconds,
                    bed_occupied=bed_occupied,
                    source=self.csv_path.name,
                )
                self._timestamps.append(timestamp_seconds)
                self._records.append(record)
        if not self._records:
            raise ValueError(f"No bed labels loaded from {self.csv_path}")

    def get_status(self, timestamp_seconds: float) -> BedStatusRecord:
        index = bisect_right(self._timestamps, timestamp_seconds) - 1
        if index < 0:
            return self._records[0]
        return self._records[index]
