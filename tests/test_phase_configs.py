from __future__ import annotations

from pathlib import Path

from raspi_revive.config import load_controller_config


PHASE_DIR = Path(__file__).resolve().parents[1] / "targets/raspi-zero-controller/config/phases"


def test_phase_a_and_b_action_gates() -> None:
    phase_a = load_controller_config(PHASE_DIR / "controller.phase-a.toml")
    phase_b = load_controller_config(PHASE_DIR / "controller.phase-b.toml")

    assert phase_a.actions.dry_run is True
    assert phase_a.actions.enable_restart_sentinel is False
    assert phase_a.actions.enable_remote_reboot is False
    assert phase_a.actions.enable_gpio_reboot is False
    assert phase_a.actions.enable_power_button_pulse is False

    assert phase_b.actions.dry_run is False
    assert phase_b.actions.enable_restart_sentinel is True
    assert phase_b.actions.enable_remote_reboot is False
    assert phase_b.actions.enable_gpio_reboot is False
    assert phase_b.actions.enable_power_button_pulse is False



def test_phase_configs_include_events_log_path() -> None:
    phase_b = load_controller_config(PHASE_DIR / "controller.phase-b.toml")
    assert phase_b.paths.events_log_path.name == "events.jsonl"
