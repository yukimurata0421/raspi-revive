from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

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
from raspi_revive.scenario_harness import (
    assert_scenario_expectations,
    load_scenario_definitions_from_dir,
    replay_definition,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


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


def test_all_json_fixtures_replay(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    scenarios = load_scenario_definitions_from_dir(FIXTURE_DIR)
    assert len(scenarios) >= 10
    assert any(item.scenario_id == "SCN-010" for item in scenarios)

    for scenario in scenarios:
        results = replay_definition(config, scenario)
        assert_scenario_expectations(scenario.steps, results)


def test_cli_replays_fixture_dir(tmp_path: Path) -> None:
    config_path = tmp_path / "controller.toml"
    config_path.write_text(
        """
[probe]
ping_target = "127.0.0.1"
ping_timeout_sec = 1.0
ping_retries = 1
ssh_target = "pi@127.0.0.1"
ssh_timeout_sec = 1.0
ssh_retries = 1
ssh_options = []

[threshold]
host_heartbeat_stale_sec = 10.0
gpio_heartbeat_stale_sec = 10.0
sentinel_stats_stale_sec = 30.0
sentinel_state_stale_sec = 30.0
required_consecutive_sentinel_failure = 1
required_consecutive_host_degraded = 2
required_consecutive_freeze_suspected = 3

[guard]
cooldown_seconds = 0.0
lockout_window_seconds = 3600.0
max_actions_per_window = 10
post_action_verification_wait_seconds = 120.0

[paths]
host_heartbeat_path = "./runtime/host-heartbeat.json"
gpio_heartbeat_path = "./runtime/gpio-heartbeat.json"
sentinel_stats_path = "./runtime/stats.json"
sentinel_state_path = "./runtime/state.json"
observations_log_path = "./runtime/observations.jsonl"
decisions_log_path = "./runtime/decisions.jsonl"
actions_log_path = "./runtime/actions.jsonl"
controller_state_path = "./runtime/controller-state.json"

[actions]
dry_run = true
enable_restart_sentinel = true
enable_remote_reboot = true
enable_gpio_reboot = true
enable_power_button_pulse = true
restart_sentinel_cmd = ["true"]
remote_reboot_cmd = ["true"]
gpio_reboot_cmd = ["true"]
power_button_pulse_cmd = ["true"]

[loop]
cycle_seconds = 1.0

[mode]
maintenance_mode = false
""".strip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "raspi_revive.scenario_replay_cli",
            "--config",
            str(config_path),
            "--scenario-dir",
            str(FIXTURE_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "All" in proc.stdout
