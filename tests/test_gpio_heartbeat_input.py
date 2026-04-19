from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from raspi_revive.gpio import FileHeartbeatInput
from raspi_revive.io import write_json_atomic


def test_file_heartbeat_input_missing_file_returns_none(tmp_path: Path) -> None:
    hb = FileHeartbeatInput(tmp_path / "missing.json")
    assert hb.edge_age_seconds(1000.0) is None


def test_file_heartbeat_input_malformed_json_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "gpio-heartbeat.json"
    path.write_text("{not-json", encoding="utf-8")
    hb = FileHeartbeatInput(path)
    assert hb.edge_age_seconds(1000.0) is None


def test_file_heartbeat_input_invalid_timestamp_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "gpio-heartbeat.json"
    write_json_atomic(path, {"last_edge_wall_time": "bad-ts"})
    hb = FileHeartbeatInput(path)
    assert hb.edge_age_seconds(1000.0) is None


def test_file_heartbeat_input_valid_timestamp_returns_age(tmp_path: Path) -> None:
    path = tmp_path / "gpio-heartbeat.json"
    edge = datetime.fromtimestamp(995.0, tz=timezone.utc).isoformat()
    write_json_atomic(path, {"last_edge_wall_time": edge})
    hb = FileHeartbeatInput(path)
    assert hb.edge_age_seconds(1000.0) == 5.0


def test_file_heartbeat_input_unhealthy_observer_status_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "gpio-heartbeat.json"
    edge = datetime.fromtimestamp(995.0, tz=timezone.utc).isoformat()
    write_json_atomic(
        path,
        {
            "last_edge_wall_time": edge,
            "observer_status": "read_error",
        },
    )
    hb = FileHeartbeatInput(path)
    assert hb.edge_age_seconds(1000.0) is None
