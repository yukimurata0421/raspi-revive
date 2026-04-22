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
from raspi_revive.controller import ReviveController


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
            post_boot_reconciliation_wait_seconds=60.0,
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


def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_events_do_not_spam_steady_healthy_loop(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, phase_b=False)
    _write_fact_files(tmp_path)
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)

    controller = ReviveController(config)
    controller.run_cycle()
    controller.run_cycle()
    controller.run_cycle()

    events = _events(config.paths.events_log_path)
    names = [item["event"] for item in events]
    assert "controller_started" in names
    assert "phase_changed" in names
    transitions = [e for e in events if e["event"] == "controller_state_changed"]
    assert len(transitions) == 1
    assert transitions[0]["detail"]["to_state"] == "HEALTHY"


def test_events_emit_on_state_transition(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, phase_b=False)
    _write_fact_files(tmp_path)
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)

    controller = ReviveController(config)
    controller.run_cycle()

    stale_ts = datetime.now(timezone.utc).timestamp() - 120.0
    os.utime(config.paths.sentinel_stats_path, (stale_ts, stale_ts))
    os.utime(config.paths.sentinel_state_path, (stale_ts, stale_ts))
    controller.run_cycle()

    transitions = [
        item for item in _events(config.paths.events_log_path) if item["event"] == "controller_state_changed"
    ]
    assert any(t["detail"]["to_state"] == "SENTINEL_ONLY_FAILURE" for t in transitions)


def test_phase_change_and_gate_change_events(tmp_path: Path, monkeypatch) -> None:
    _write_fact_files(tmp_path)
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)

    phase_a = _build_config(tmp_path, phase_b=False)
    controller_a = ReviveController(phase_a)
    controller_a.run_cycle()

    phase_b = _build_config(tmp_path, phase_b=True)
    controller_b = ReviveController(phase_b)
    controller_b.run_cycle()

    events = _events(phase_b.paths.events_log_path)
    assert any(e["event"] == "phase_b_enabled" for e in events)
    assert any(
        e["event"] == "phase_changed" and e["detail"].get("to_phase") == "PHASE_B"
        for e in events
    )
    assert any(e["event"] == "action_gate_changed" for e in events)


def test_phase_b_restart_logs_verification_events(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, phase_b=True)
    _write_fact_files(tmp_path)
    stale_ts = datetime.now(timezone.utc).timestamp() - 120.0
    os.utime(config.paths.sentinel_stats_path, (stale_ts, stale_ts))
    os.utime(config.paths.sentinel_state_path, (stale_ts, stale_ts))
    monkeypatch.setattr("raspi_revive.collector.ping_probe", lambda **_: True)
    monkeypatch.setattr("raspi_revive.collector.ssh_probe", lambda **_: True)
    monkeypatch.setattr(
        ReviveController,
        "_verify_sentinel_restart_freshness",
        lambda self: {
            "verification_kind": "sentinel_freshness",
            "verified": True,
            "sentinel_stats_age_sec": 1.0,
            "sentinel_stats_fresh": True,
            "sentinel_state_age_sec": 1.0,
            "sentinel_state_fresh": True,
            "sentinel_stats_stale_sec": 30.0,
            "sentinel_state_stale_sec": 30.0,
        },
    )

    controller = ReviveController(config)
    controller.run_cycle()

    action = json.loads(config.paths.actions_log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert action["chosen_action"] == "RESTART_SENTINEL"
    assert action["execution"]["verification"]["verification_kind"] == "sentinel_freshness"

    names = [e["event"] for e in _events(config.paths.events_log_path)]
    assert "sentinel_restart_scheduled" in names
    assert "sentinel_restart_completed" in names
    assert "sentinel_restart_verified" in names
