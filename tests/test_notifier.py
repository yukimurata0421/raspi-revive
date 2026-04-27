from __future__ import annotations

import json
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
from raspi_revive.models import ControllerState, Decision, Evidence, Observation, RecoveryAction
from raspi_revive.notifier import NotifyDispatcher


def _build_config(tmp_path: Path, *, webhook_url: str) -> ControllerConfig:
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
            host_heartbeat_stale_sec=10.0,
            gpio_heartbeat_stale_sec=10.0,
            sentinel_stats_stale_sec=30.0,
            sentinel_state_stale_sec=30.0,
            required_consecutive_sentinel_failure=1,
            required_consecutive_host_degraded=1,
            required_consecutive_freeze_suspected=1,
        ),
        guard=GuardConfig(
            cooldown_seconds=60.0,
            lockout_window_seconds=3600.0,
            max_actions_per_window=3,
            post_action_verification_wait_seconds=120.0,
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
            dry_run=True,
            enable_restart_sentinel=False,
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
            enabled=True,
            candidate_states=frozenset({"HOST_DEGRADED", "FREEZE_SUSPECTED"}),
            candidate_hold_seconds=300.0,
            queue_retry_interval_seconds=60.0,
            backoff_after_seconds=300.0,
            backoff_multiplier=2.0,
            backoff_max_seconds=3600.0,
            discord_webhook_url=webhook_url,
            remote_append_enabled=False,
            remote_jsonl_path="/tmp/unused.jsonl",
            queue_path=tmp_path / "notify-queue.json",
            stats_path=tmp_path / "notify-stats.json",
            events_path=tmp_path / "notify-events.jsonl",
        ),
    )


def _decision() -> Decision:
    evidence = Evidence(
        out_of_band_gpio_fresh=False,
        network_dependent_host_heartbeat_fresh=False,
        network_dependent_host_heartbeat_progressing=False,
        network_dependent_sentinel_stats_fresh=False,
        network_dependent_sentinel_state_fresh=False,
        network_dependent_ping_ok=False,
        network_dependent_ssh_ok=False,
    )
    return Decision(
        classified_state=ControllerState.HOST_DEGRADED,
        chosen_action=RecoveryAction.NO_ACTION,
        reason="host degraded sustained",
        evidence=evidence,
        cooldown_active=False,
        lockout_active=False,
        maintenance_mode_active=False,
        incident_key="incident-1",
        lockout_latch_event=None,
        correlation_id="corr-1",
    )


def _observation(ts: float) -> Observation:
    return Observation(
        ts=ts,
        host_boot_id="boot-a",
        host_seq=1,
        host_monotonic_sec=100.0,
        host_wall_time="2026-04-19T00:00:00+00:00",
        host_heartbeat_age_sec=100.0,
        host_heartbeat_fresh=False,
        host_heartbeat_progressing=False,
        gpio_heartbeat_age_sec=100.0,
        gpio_heartbeat_fresh=False,
        sentinel_stats_age_sec=100.0,
        sentinel_stats_fresh=False,
        sentinel_state_age_sec=100.0,
        sentinel_state_fresh=False,
        ping_ok=False,
        ssh_ok=False,
    )


def test_notifier_enqueues_after_5min_and_delivers(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, webhook_url="https://example.test/webhook")
    dispatcher = NotifyDispatcher(config)
    monkeypatch.setattr(NotifyDispatcher, "_send_discord", lambda self, payload: (True, None))

    decision = _decision()
    dispatcher.handle_cycle(decision, _observation(0.0))
    dispatcher.handle_cycle(decision, _observation(301.0))

    queue_payload = json.loads(config.notify.queue_path.read_text(encoding="utf-8"))
    assert queue_payload["items"] == []

    events = config.notify.events_path.read_text(encoding="utf-8")
    assert "enqueued" in events
    assert "delivery_complete" in events


def test_notifier_retries_and_switches_to_exponential_backoff(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, webhook_url="https://example.test/webhook")
    dispatcher = NotifyDispatcher(config)
    monkeypatch.setattr(
        NotifyDispatcher,
        "_send_discord",
        lambda self, payload: (False, "network down"),
    )

    decision = _decision()
    dispatcher.handle_cycle(decision, _observation(0.0))
    dispatcher.handle_cycle(decision, _observation(301.0))

    first = json.loads(config.notify.queue_path.read_text(encoding="utf-8"))["items"][0]
    assert first["attempt_count"] == 1
    assert first["next_retry_ts"] == 361.0

    dispatcher.handle_cycle(decision, _observation(362.0))
    second = json.loads(config.notify.queue_path.read_text(encoding="utf-8"))["items"][0]
    assert second["attempt_count"] == 2
    assert second["next_retry_ts"] == 422.0

    dispatcher.handle_cycle(decision, _observation(602.0))
    third = json.loads(config.notify.queue_path.read_text(encoding="utf-8"))["items"][0]
    assert third["attempt_count"] == 3
    assert third["next_retry_ts"] >= 722.0


def test_notifier_drops_expired_items(tmp_path: Path, monkeypatch) -> None:
    config = _build_config(tmp_path, webhook_url="https://example.test/webhook")
    config.notify.max_event_age_seconds = 10.0
    dispatcher = NotifyDispatcher(config)
    monkeypatch.setattr(
        NotifyDispatcher,
        "_send_discord",
        lambda self, payload: (False, "network down"),
    )

    decision = _decision()
    dispatcher.handle_cycle(decision, _observation(0.0))
    dispatcher.handle_cycle(decision, _observation(301.0))
    dispatcher.handle_cycle(decision, _observation(400.0))

    queue_payload = json.loads(config.notify.queue_path.read_text(encoding="utf-8"))
    assert queue_payload["items"] == []
    events = config.notify.events_path.read_text(encoding="utf-8")
    assert "dropped_expired" in events
