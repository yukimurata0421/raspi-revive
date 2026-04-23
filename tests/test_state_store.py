from __future__ import annotations

from pathlib import Path

from raspi_revive.models import ControllerRuntimeState
from raspi_revive.state_store import load_runtime_state, save_runtime_state


def test_load_runtime_state_returns_default_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    state = ControllerRuntimeState()
    loaded = load_runtime_state(path)
    assert loaded.to_dict() == state.to_dict()


def test_save_runtime_state_writes_state(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    state = ControllerRuntimeState()
    save_runtime_state(path, state)
    assert path.exists()
    loaded = load_runtime_state(path)
    assert loaded.to_dict() == state.to_dict()
