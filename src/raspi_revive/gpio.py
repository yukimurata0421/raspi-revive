from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .io import read_json


class HeartbeatInput(Protocol):
    def edge_age_seconds(self, now_ts: float) -> float | None:
        ...


class ExternalResetOutput(Protocol):
    def pulse(self) -> None:
        ...


class PowerButtonPulseOutput(Protocol):
    def pulse(self) -> None:
        ...


@dataclass(slots=True)
class FileHeartbeatInput:
    path: Path

    def edge_age_seconds(self, now_ts: float) -> float | None:
        payload = read_json(self.path)
        if payload is None:
            return None
        wall = payload.get("last_edge_wall_time")
        if not isinstance(wall, str):
            return None
        try:
            dt = datetime.fromisoformat(wall.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, now_ts - dt.timestamp())
