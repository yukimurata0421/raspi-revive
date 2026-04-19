from __future__ import annotations

from pathlib import Path

from raspi_revive.config import (
    ActionConfig,
    ControllerConfig,
    ControllerModeConfig,
    GuardConfig,
    LoopConfig,
    PathConfig,
    ProbeConfig,
    ThresholdConfig,
)
from raspi_revive.models import Observation, RecoveryAction
from raspi_revive.scenario_harness import (
    ScenarioStep,
    assert_scenario_expectations,
    replay_scenario,
)


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
            required_consecutive_host_degraded=2,
            required_consecutive_freeze_suspected=3,
        ),
        guard=GuardConfig(
            cooldown_seconds=0.0,
            lockout_window_seconds=3600.0,
            max_actions_per_window=10,
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
    )


def obs(
    *,
    gpio_fresh: bool,
    host_fresh: bool,
    ping_ok: bool,
    ssh_ok: bool,
    sentinel_stats_fresh: bool,
    sentinel_state_fresh: bool,
    boot_id: str = "boot-a",
) -> Observation:
    return Observation(
        ts=1000.0,
        host_boot_id=boot_id,
        host_seq=1,
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


def test_scenario_network_only_issue_forbids_reboot(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    steps = [
        ScenarioStep(
            step_id="SCN-004-STEP-1",
            observation=obs(
                gpio_fresh=True,
                host_fresh=False,
                ping_ok=False,
                ssh_ok=False,
                sentinel_stats_fresh=True,
                sentinel_state_fresh=True,
            ),
            expected_state="NETWORK_ONLY_ISSUE",
            expected_action=RecoveryAction.NO_ACTION,
            forbidden_actions=(RecoveryAction.REMOTE_REBOOT, RecoveryAction.GPIO_REBOOT),
        )
    ]

    results = replay_scenario(config, steps)
    assert_scenario_expectations(steps, results)


def test_scenario_sentinel_only_goes_to_restart_only(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    steps = [
        ScenarioStep(
            step_id="SCN-001-STEP-1",
            observation=obs(
                gpio_fresh=True,
                host_fresh=True,
                ping_ok=True,
                ssh_ok=True,
                sentinel_stats_fresh=False,
                sentinel_state_fresh=True,
            ),
            expected_state="SENTINEL_ONLY_FAILURE",
            expected_action=RecoveryAction.RESTART_SENTINEL,
            forbidden_actions=(RecoveryAction.REMOTE_REBOOT, RecoveryAction.GPIO_REBOOT),
        )
    ]

    results = replay_scenario(config, steps)
    assert_scenario_expectations(steps, results)


def test_scenario_freeze_requires_sustained_cycles_before_gpio_reboot(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    steps = [
        ScenarioStep(
            step_id="SCN-007-STEP-1",
            observation=obs(
                gpio_fresh=False,
                host_fresh=False,
                ping_ok=False,
                ssh_ok=False,
                sentinel_stats_fresh=False,
                sentinel_state_fresh=False,
            ),
            expected_state="FREEZE_SUSPECTED",
            expected_action=RecoveryAction.NO_ACTION,
            forbidden_actions=(RecoveryAction.REMOTE_REBOOT,),
        ),
        ScenarioStep(
            step_id="SCN-007-STEP-2",
            observation=obs(
                gpio_fresh=False,
                host_fresh=False,
                ping_ok=False,
                ssh_ok=False,
                sentinel_stats_fresh=False,
                sentinel_state_fresh=False,
            ),
            expected_state="FREEZE_SUSPECTED",
            expected_action=RecoveryAction.NO_ACTION,
            forbidden_actions=(RecoveryAction.REMOTE_REBOOT,),
        ),
        ScenarioStep(
            step_id="SCN-007-STEP-3",
            observation=obs(
                gpio_fresh=False,
                host_fresh=False,
                ping_ok=False,
                ssh_ok=False,
                sentinel_stats_fresh=False,
                sentinel_state_fresh=False,
            ),
            expected_state="FREEZE_SUSPECTED",
            expected_action=RecoveryAction.GPIO_REBOOT,
        ),
    ]

    results = replay_scenario(config, steps)
    assert_scenario_expectations(steps, results)
