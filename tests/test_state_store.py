from __future__ import annotations

from pathlib import Path

from raspi_revive.models import ControllerState, ControllerRuntimeState
from raspi_revive.state_store import load_runtime_state, save_runtime_state


def test_load_runtime_state_returns_default_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    state = load_runtime_state(path)
    assert isinstance(state, ControllerRuntimeState)
    assert state.current_state == ControllerState.HEALTHY
    assert state.schema_version == 1
    assert state.last_state_write_ts is None


def test_save_and_load_runtime_state_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    state = ControllerRuntimeState(
        current_state=ControllerState.HEALTHY,
        schema_version=2,
        code_version="0.1.0-test",
        last_loop_ts=123.0,
        last_observation_ts=122.5,
        last_state_write_ts=123.0,
    )
    save_runtime_state(path, state)
    loaded = load_runtime_state(path)
    assert loaded.schema_version == 2
    assert loaded.code_version == "0.1.0-test"
    assert loaded.last_loop_ts == 123.0
    assert loaded.last_observation_ts == 122.5
    assert loaded.last_state_write_ts == 123.0
