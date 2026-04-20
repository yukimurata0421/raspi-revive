from __future__ import annotations

from pathlib import Path

from raspi_revive.models import ControllerRuntimeState
from raspi_revive.state_store import save_runtime_state_if_changed


def test_save_runtime_state_if_changed_skips_unchanged_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    state = ControllerRuntimeState()
    path.write_text(
        '{"current_state":"HEALTHY","consecutive_counts":{},"last_action_ts":null,'
        '"action_timestamps":[],"lockout_until_ts":null,"pending_verification":null,'
        '"previous_host_boot_id":null,"previous_host_seq":null,"last_action_incident_key":null,'
        '"lockout_latch_active":false}',
        encoding="utf-8",
    )
    changed = save_runtime_state_if_changed(path, state.to_dict(), state)
    assert changed is False


def test_save_runtime_state_if_changed_writes_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "controller-state.json"
    state = ControllerRuntimeState()
    changed = save_runtime_state_if_changed(path, state.to_dict(), state)
    assert changed is True
    assert path.exists()
