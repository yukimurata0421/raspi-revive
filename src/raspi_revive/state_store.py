from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import read_json, write_json_atomic
from .models import ControllerRuntimeState


def load_runtime_state(path: Path) -> ControllerRuntimeState:
    payload = read_json(path)
    if payload is None:
        return ControllerRuntimeState()
    return ControllerRuntimeState.from_dict(payload)


def save_runtime_state(path: Path, state: ControllerRuntimeState) -> None:
    write_json_atomic(path, state.to_dict())


def save_runtime_state_if_changed(
    path: Path,
    last_saved_dict: dict[str, Any] | None,
    state: ControllerRuntimeState,
) -> bool:
    """Backwards-compatible conditional writer used by legacy tests/callers."""
    current = state.to_dict()
    if path.exists() and isinstance(last_saved_dict, dict) and last_saved_dict == current:
        return False
    write_json_atomic(path, current)
    return True
