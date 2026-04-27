from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from raspi_revive.config import (
    ActionConfig,
    ControllerConfig,
    ControllerModeConfig,
    GuardConfig,
    LoopConfig,
    NotifyConfig,
    PathConfig,
    ProbeConfig,
    ThresholdConfig,
)
from raspi_revive.controller import (
    STATE_HEARTBEAT_WRITE_INTERVAL_SEC,
    ReviveController,
)
from raspi_revive.models import ControllerRuntimeState, HEARTBEAT_FIELDS


def _build_config(tmp_path: Path, *, phase_b: bool) -> ControllerConfig:
    return ControllerConfig(
        probe=ProbeConfig(
            ping_target="127.0.0.1",
            ping_timeout_sec=1.0,
            ping_retries=1,
            ssh_target="pi@127.0.0.1",
            ssh_timeout_sec=1.0,
            ssh_retries=1,
            ssh_options=[],
        ),
        threshold=ThresholdConfig(
            host_heartbeat_stale_sec=30.0,
            gpio_heartbeat_stale_sec=30.0,
            sentinel_stats_stale_sec=30.0,
            sentinel_state_stale_sec=30.0,
            required_consecutive_sentinel_failure=1,
            required_consecutive_host_degraded=1,
            required_consecutive_freeze_suspected=3,
        ),
        guard=GuardConfig(
            cooldown_seconds=0.0,
            lockout_window_seconds=600.0,
            max_actions_per_window=3,
            post_action_verification_wait_seconds=60.0,
        ),
        paths=PathConfig(
            host_heartbeat_path=tmp_path / "host-heartbeat.json",
            gpio_heartbeat_path=tmp_path / "gpio-heartbeat.json",
            sentinel_stats_path=tmp_path / "stats.json",
            sentinel_state_path=tmp_path / "state.json",
            observations_log_path=tmp_path / "observations.jsonl",
            decisions_log_path=tmp_path / "decisions.jsonl",
            actions_log_path=tmp_path / "actions.jsonl",
            events_log_path=tmp_path / "events.jsonl",
            controller_state_path=tmp_path / "controller-state.json",
        ),
        actions=ActionConfig(
            dry_run=not phase_b,
            enable_restart_sentinel=phase_b,
            enable_remote_reboot=False,
            enable_gpio_reboot=False,
            enable_power_button_pulse=False,
            restart_sentinel_cmd=["true"],
            remote_reboot_cmd=["true"],
            gpio_reboot_cmd=["true"],
            power_button_pulse_cmd=["true"],
        ),
        loop=LoopConfig(cycle_seconds=1.0),
        mode=ControllerModeConfig(maintenance_mode=False),
        notify=NotifyConfig(
            enabled=False,
            candidate_states=frozenset({"HOST_DEGRADED", "FREEZE_SUSPECTED"}),
            candidate_hold_seconds=300.0,
            queue_retry_interval_seconds=60.0,
            backoff_after_seconds=300.0,
            backoff_multiplier=2.0,
            backoff_max_seconds=3600.0,
            discord_webhook_url="",
            remote_append_enabled=False,
            remote_jsonl_path="/tmp/unused.jsonl",
            queue_path=tmp_path / "notify-queue.json",
            stats_path=tmp_path / "notify-stats.json",
            events_path=tmp_path / "notify-events.jsonl",
        ),
    )


def _write_fact_files(tmp_path: Path) -> None:
    now_wall = datetime.now(timezone.utc).isoformat()
    (tmp_path / "host-heartbeat.json").write_text(
        json.dumps(
            {
                "boot_id": "boot-a",
                "seq": 1,
                "monotonic_sec": 1.0,
                "wall_time": now_wall,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "gpio-heartbeat.json").write_text(
        json.dumps(
            {
                "observer_status": "ok",
                "last_edge_wall_time": now_wall,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "stats.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")


def _read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_structural_change_writes_immediately(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, phase_b=False)
    _write_fact_files(tmp_path)
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)

    controller = ReviveController(config)
    controller.run_cycle()
    first = _read_state(config.paths.controller_state_path)

    controller.run_cycle()
    second = _read_state(config.paths.controller_state_path)

    assert first["current_state"] == second["current_state"]
    assert first["last_state_write_ts"] == second["last_state_write_ts"]


def test_heartbeat_forces_write_after_interval(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, phase_b=False)
    _write_fact_files(tmp_path)
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)

    controller = ReviveController(config)
    controller.run_cycle()
    first_write = _read_state(config.paths.controller_state_path)["last_state_write_ts"]
    assert first_write is not None

    fake_now = first_write + STATE_HEARTBEAT_WRITE_INTERVAL_SEC + 1.0
    monkeypatch.setattr("raspi_revive.controller.time.time", lambda: fake_now)
    monkeypatch.setattr("raspi_revive.collector.time.time", lambda: fake_now)
    for name in ("host-heartbeat.json", "gpio-heartbeat.json", "stats.json", "state.json"):
        os.utime(tmp_path / name, (fake_now, fake_now))

    controller.run_cycle()
    second_write = _read_state(config.paths.controller_state_path)["last_state_write_ts"]

    assert second_write > first_write
    assert (second_write - first_write) >= STATE_HEARTBEAT_WRITE_INTERVAL_SEC


def test_structural_dict_excludes_heartbeat_fields() -> None:
    state = ControllerRuntimeState()
    state.last_loop_ts = 1000.0
    state.last_observation_ts = 1000.0
    state.last_state_write_ts = 1000.0

    structural = state.to_structural_dict()
    for field_name in HEARTBEAT_FIELDS:
        assert field_name not in structural
    assert "schema_version" in structural
    assert "code_version" in structural


def test_schema_version_change_is_structural(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, phase_b=False)
    _write_fact_files(tmp_path)
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)

    controller = ReviveController(config)
    controller.run_cycle()
    first_write = _read_state(config.paths.controller_state_path)["last_state_write_ts"]
    assert first_write is not None

    controller._runtime_state.schema_version = 2
    fake_now = first_write + 1.0
    monkeypatch.setattr("raspi_revive.controller.time.time", lambda: fake_now)
    monkeypatch.setattr("raspi_revive.collector.time.time", lambda: fake_now)
    for name in ("host-heartbeat.json", "gpio-heartbeat.json", "stats.json", "state.json"):
        os.utime(tmp_path / name, (fake_now, fake_now))

    controller.run_cycle()
    persisted = _read_state(config.paths.controller_state_path)
    assert persisted["schema_version"] == 2
    assert persisted["last_state_write_ts"] >= fake_now


def test_controller_state_write_stale_event_emitted(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, phase_b=False)
    _write_fact_files(tmp_path)
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)

    controller = ReviveController(config)
    controller.run_cycle()
    first_write = _read_state(config.paths.controller_state_path)["last_state_write_ts"]
    assert first_write is not None

    fake_now = first_write + 120.0
    monkeypatch.setattr("raspi_revive.controller.time.time", lambda: fake_now)
    monkeypatch.setattr("raspi_revive.collector.time.time", lambda: fake_now)
    for name in ("host-heartbeat.json", "gpio-heartbeat.json", "stats.json", "state.json"):
        os.utime(tmp_path / name, (fake_now, fake_now))

    controller.run_cycle()
    events = [
        json.loads(line)
        for line in config.paths.events_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stale = [item for item in events if item.get("event") == "controller_state_write_stale"]
    assert stale
    assert stale[-1]["detail"]["threshold_seconds"] == 90.0
