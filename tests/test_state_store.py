from __future__ import annotations

import json
from pathlib import Path

from raspi_revive.models import ControllerRuntimeState
from raspi_revive.state_store import load_runtime_state, save_runtime_state


def test_save_runtime_state_writes_file(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    state = ControllerRuntimeState()
    save_runtime_state(path, state)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["current_state"] == "HEALTHY"
    assert payload["consecutive_counts"] == {}


def test_load_runtime_state_returns_default_on_broken_json(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    path.write_text("{broken", encoding="utf-8")
    loaded = load_runtime_state(path)
    assert loaded.current_state.value == "HEALTHY"
    assert loaded.consecutive_counts == {}
