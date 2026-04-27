from __future__ import annotations

import os
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
    assert phase_a.actions.enabled_phases == frozenset({"A"})

    assert phase_b.actions.dry_run is False
    assert phase_b.actions.enable_restart_sentinel is True
    assert phase_b.actions.enable_remote_reboot is False
    assert phase_b.actions.enable_gpio_reboot is False
    assert phase_b.actions.enable_power_button_pulse is False
    assert phase_b.actions.enabled_phases == frozenset({"A", "B"})



def test_phase_configs_include_events_log_path() -> None:
    phase_b = load_controller_config(PHASE_DIR / "controller.phase-b.toml")
    assert phase_b.paths.events_log_path.name == "events.jsonl"
    assert phase_b.logs.max_log_size_mb == 10.0


def test_phase_c_synthesizes_notify_providers_from_legacy_fields() -> None:
    phase_c = load_controller_config(PHASE_DIR / "controller.phase-c.toml")
    assert any(provider.kind == "ssh_append" for provider in phase_c.notify_providers)


def test_explicit_notify_providers_support_webhook_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RREVIVE_TEST_WEBHOOK", "https://example.test/from-env")
    base = (PHASE_DIR / "controller.phase-c.toml").read_text(encoding="utf-8")
    custom = (
        base
        + """

[[notify.providers]]
name = "discord-main"
kind = "discord_webhook"
enabled = true
webhook_url = ""
webhook_url_env = "RREVIVE_TEST_WEBHOOK"
"""
    )
    cfg_path = tmp_path / "controller.with-provider.toml"
    cfg_path.write_text(custom, encoding="utf-8")

    loaded = load_controller_config(cfg_path)
    found = [p for p in loaded.notify_providers if p.kind == "discord_webhook" and p.name == "discord-main"]
    assert found
    assert found[0].webhook_url == os.environ["RREVIVE_TEST_WEBHOOK"]


def test_remote_reboot_webhook_env_is_loaded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RREVIVE_REMOTE_REBOOT_WEBHOOK", "https://example.test/remote-reboot-from-env")
    base = (PHASE_DIR / "controller.phase-c.toml").read_text(encoding="utf-8")
    custom = base.replace(
        'remote_reboot_discord_webhook_url_env = "RASPI_REVIVE_REMOTE_REBOOT_WEBHOOK_URL"',
        (
            'remote_reboot_discord_webhook_url_env = "RREVIVE_REMOTE_REBOOT_WEBHOOK"'
        ),
    )
    cfg_path = tmp_path / "controller.remote-reboot-webhook.toml"
    cfg_path.write_text(custom, encoding="utf-8")

    loaded = load_controller_config(cfg_path)
    assert (
        loaded.notify.remote_reboot_discord_webhook_url
        == os.environ["RREVIVE_REMOTE_REBOOT_WEBHOOK"]
    )
