from __future__ import annotations

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
from raspi_revive.evaluator import classify
from raspi_revive.models import ControllerRuntimeState, Observation, RecoveryAction
from raspi_revive.state_machine import StateMachine


def build_config(tmp_path: Path) -> ControllerConfig:
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
            required_consecutive_freeze_suspected=3,
        ),
        guard=GuardConfig(
            cooldown_seconds=60.0,
            lockout_window_seconds=600.0,
            max_actions_per_window=2,
            post_action_verification_wait_seconds=120.0,
            post_boot_reconciliation_wait_seconds=120.0,
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
            enable_restart_sentinel=True,
            enable_remote_reboot=True,
            enable_gpio_reboot=True,
            enable_power_button_pulse=True,
            restart_sentinel_cmd=["true"],
            remote_reboot_cmd=["true"],
            gpio_reboot_cmd=["true"],
            power_button_pulse_cmd=["true"],
        ),
        loop=LoopConfig(cycle_seconds=1.0),
        mode=ControllerModeConfig(maintenance_mode=False),
        notify=NotifyConfig(
            enabled=False,
            candidate_states=("HOST_DEGRADED", "FREEZE_SUSPECTED"),
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


def make_observation(
    *,
    gpio_fresh: bool,
    host_fresh: bool,
    ping_ok: bool,
    ssh_ok: bool,
    sentinel_stats_fresh: bool,
    sentinel_state_fresh: bool,
    host_boot_id: str | None = "boot-a",
    host_seq: int | None = 1,
) -> Observation:
    return Observation(
        ts=1000.0,
        host_boot_id=host_boot_id,
        host_seq=host_seq,
        host_monotonic_sec=100.0,
        host_wall_time="2026-04-19T00:00:00+00:00",
        host_heartbeat_age_sec=1.0 if host_fresh else 100.0,
        host_heartbeat_fresh=host_fresh,
        host_heartbeat_progressing=True,
        gpio_heartbeat_age_sec=1.0 if gpio_fresh else 100.0,
        gpio_heartbeat_fresh=gpio_fresh,
        sentinel_stats_age_sec=1.0 if sentinel_stats_fresh else 100.0,
        sentinel_stats_fresh=sentinel_stats_fresh,
        sentinel_state_age_sec=1.0 if sentinel_state_fresh else 100.0,
        sentinel_state_fresh=sentinel_state_fresh,
        ping_ok=ping_ok,
        ssh_ok=ssh_ok,
    )


def test_network_outage_only_does_not_trigger_external_reboot(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    obs = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=False,
        ssh_ok=False,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.chosen_action == RecoveryAction.NO_ACTION


def test_sentinel_stale_only_stops_at_restart_sentinel(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    obs = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.chosen_action == RecoveryAction.RESTART_SENTINEL


def test_freeze_needs_consecutive_cycles_before_gpio_reboot(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    for _ in range(2):
        obs = make_observation(
            gpio_fresh=False,
            host_fresh=False,
            ping_ok=False,
            ssh_ok=False,
            sentinel_stats_fresh=False,
            sentinel_state_fresh=False,
        )
        decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
        assert decision.chosen_action == RecoveryAction.NO_ACTION

    obs = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=False,
        ssh_ok=False,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=False,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.chosen_action == RecoveryAction.GPIO_REBOOT


def test_action_enters_cooldown(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    times = iter([1000.0, 1000.0, 1001.0])
    monkeypatch.setattr("raspi_revive.state_machine.time.time", lambda: next(times))

    obs = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    machine.register_action(
        runtime,
        decision.chosen_action,
        decision.correlation_id,
        decision.incident_key,
        obs.host_boot_id,
    )

    next_decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert next_decision.chosen_action == RecoveryAction.NO_ACTION
    assert next_decision.cooldown_active is True


def test_exceed_action_budget_enters_lockout(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    timestamps = iter([1000.0, 1000.0, 1001.0, 1001.0, 1002.0])
    monkeypatch.setattr("raspi_revive.state_machine.time.time", lambda: next(timestamps))

    machine.register_action(runtime, RecoveryAction.RESTART_SENTINEL, "c1", "i1", "boot-a")
    machine.register_action(runtime, RecoveryAction.RESTART_SENTINEL, "c2", "i2", "boot-a")

    obs = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=False,
        ssh_ok=False,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=False,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.classified_state.value == "LOCKOUT"


def test_reboot_verification_uses_boot_id_change(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    times = iter([999.0, 1000.0, 1000.0, 1001.0, 1002.0])
    monkeypatch.setattr("raspi_revive.state_machine.time.time", lambda: next(times))

    baseline = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
        host_boot_id="boot-a",
    )
    baseline_decision = machine.decide(runtime, classify(baseline), current_boot_id=baseline.host_boot_id)
    assert baseline_decision.classified_state.value == "HEALTHY"

    obs = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
        host_boot_id="boot-a",
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.chosen_action == RecoveryAction.REMOTE_REBOOT
    machine.register_action(
        runtime,
        decision.chosen_action,
        decision.correlation_id,
        decision.incident_key,
        obs.host_boot_id,
    )

    same_boot = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
        host_boot_id="boot-a",
    )
    in_progress = machine.decide(runtime, classify(same_boot), current_boot_id=same_boot.host_boot_id)
    assert in_progress.classified_state.value == "RECOVERY_IN_PROGRESS"

    changed_boot = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
        host_boot_id="boot-b",
    )
    verified = machine.decide(runtime, classify(changed_boot), current_boot_id=changed_boot.host_boot_id)
    assert verified.classified_state.value != "RECOVERY_IN_PROGRESS"
    assert runtime.pending_verification is None


def test_false_positive_guard_freeze_does_not_trigger_on_single_cycle(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    freeze_once = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=False,
        ssh_ok=False,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=False,
    )
    d1 = machine.decide(runtime, classify(freeze_once), current_boot_id=freeze_once.host_boot_id)
    assert d1.chosen_action == RecoveryAction.NO_ACTION

    back_to_normal = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    d2 = machine.decide(runtime, classify(back_to_normal), current_boot_id=back_to_normal.host_boot_id)
    assert d2.chosen_action == RecoveryAction.NO_ACTION


def test_management_plane_degraded_classification(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    obs = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=False,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.classified_state.value == "MANAGEMENT_PLANE_DEGRADED"
    assert decision.chosen_action == RecoveryAction.NO_ACTION


def test_host_degraded_requires_multi_evidence(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    gpio_only_stale = make_observation(
        gpio_fresh=False,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(gpio_only_stale), current_boot_id=gpio_only_stale.host_boot_id)
    assert decision.chosen_action == RecoveryAction.NO_ACTION
    assert decision.classified_state.value == "HEALTHY"


def test_action_disabled_by_rollout_policy(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    config.actions.enable_remote_reboot = False
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()
    runtime.last_telemetry_healthy_boot_id = "boot-a"

    obs = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.classified_state.value == "HOST_DEGRADED"
    assert decision.chosen_action == RecoveryAction.NO_ACTION
    assert "rollout phase policy" in decision.reason


def test_telemetry_pipeline_failure_does_not_trigger_remote_reboot(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    obs = make_observation(
        gpio_fresh=True,
        host_fresh=False,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.classified_state.value == "TELEMETRY_PIPELINE_FAILURE"
    assert decision.chosen_action == RecoveryAction.NO_ACTION


def test_post_boot_reconciliation_holds_after_reboot_until_telemetry_recovers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = build_config(tmp_path)
    config.guard.cooldown_seconds = 0.0
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    times = iter([999.0, 1000.0, 1000.0, 1001.0, 1002.0, 1003.0])
    monkeypatch.setattr("raspi_revive.state_machine.time.time", lambda: next(times))

    baseline = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
        host_boot_id="boot-a",
    )
    machine.decide(runtime, classify(baseline), current_boot_id=baseline.host_boot_id)

    degraded = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
        host_boot_id="boot-a",
    )
    reboot = machine.decide(runtime, classify(degraded), current_boot_id=degraded.host_boot_id)
    assert reboot.chosen_action == RecoveryAction.REMOTE_REBOOT
    machine.register_action(
        runtime,
        reboot.chosen_action,
        reboot.correlation_id,
        reboot.incident_key,
        degraded.host_boot_id,
    )

    changed_boot_not_recovered = make_observation(
        gpio_fresh=True,
        host_fresh=False,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=True,
        host_boot_id="boot-b",
    )
    hold = machine.decide(
        runtime,
        classify(changed_boot_not_recovered),
        current_boot_id=changed_boot_not_recovered.host_boot_id,
    )
    assert hold.classified_state.value == "POST_BOOT_RECONCILIATION"
    assert hold.chosen_action == RecoveryAction.NO_ACTION

    recovered = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
        host_boot_id="boot-b",
    )
    done = machine.decide(runtime, classify(recovered), current_boot_id=recovered.host_boot_id)
    assert done.classified_state.value == "HEALTHY"
    assert runtime.post_boot_reconciliation is None


def test_maintenance_mode_blocks_intervention(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    config.mode.maintenance_mode = True
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    obs = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=True,
    )
    decision = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert decision.chosen_action == RecoveryAction.NO_ACTION
    assert decision.maintenance_mode_active is True


def test_incident_dedupe_prevents_repeated_same_intervention(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    config.guard.cooldown_seconds = 0.0
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    times = iter([1000.0, 1000.0, 1001.0, 1001.0])
    monkeypatch.setattr("raspi_revive.state_machine.time.time", lambda: next(times))

    obs = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=True,
    )
    d1 = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert d1.chosen_action == RecoveryAction.RESTART_SENTINEL
    machine.register_action(runtime, d1.chosen_action, d1.correlation_id, d1.incident_key, obs.host_boot_id)

    d2 = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert d2.chosen_action == RecoveryAction.NO_ACTION
    assert "already handled" in d2.reason


def test_lockout_latch_events_enter_and_clear(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()
    runtime.lockout_until_ts = 1010.0

    times = iter([1000.0, 1005.0, 1011.0])
    monkeypatch.setattr("raspi_revive.state_machine.time.time", lambda: next(times))

    obs = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=False,
        ssh_ok=False,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=False,
    )
    d1 = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert d1.classified_state.value == "LOCKOUT"
    assert d1.lockout_latch_event == "lockout_entered"

    d2 = machine.decide(runtime, classify(obs), current_boot_id=obs.host_boot_id)
    assert d2.classified_state.value == "LOCKOUT"
    assert d2.lockout_latch_event == "lockout_still_active"

    healthy = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    d3 = machine.decide(runtime, classify(healthy), current_boot_id=healthy.host_boot_id)
    assert d3.lockout_latch_event == "lockout_cleared"


def test_phase_b_allows_only_restart_sentinel(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    config.actions.dry_run = False
    config.actions.enable_restart_sentinel = True
    config.actions.enable_remote_reboot = False
    config.actions.enable_gpio_reboot = False
    config.actions.enable_power_button_pulse = False
    machine = StateMachine(config)
    runtime = ControllerRuntimeState()

    sentinel_only = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=False,
        sentinel_state_fresh=True,
    )
    d_sentinel = machine.decide(runtime, classify(sentinel_only), current_boot_id=sentinel_only.host_boot_id)
    assert d_sentinel.chosen_action == RecoveryAction.RESTART_SENTINEL

    host_degraded = make_observation(
        gpio_fresh=False,
        host_fresh=False,
        ping_ok=True,
        ssh_ok=True,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    d_host = machine.decide(runtime, classify(host_degraded), current_boot_id=host_degraded.host_boot_id)
    assert d_host.classified_state.value == "HOST_DEGRADED"
    assert d_host.chosen_action == RecoveryAction.NO_ACTION

    management_plane = make_observation(
        gpio_fresh=True,
        host_fresh=True,
        ping_ok=True,
        ssh_ok=False,
        sentinel_stats_fresh=True,
        sentinel_state_fresh=True,
    )
    d_mgmt = machine.decide(
        runtime,
        classify(management_plane),
        current_boot_id=management_plane.host_boot_id,
    )
    assert d_mgmt.classified_state.value == "MANAGEMENT_PLANE_DEGRADED"
    assert d_mgmt.chosen_action == RecoveryAction.NO_ACTION
