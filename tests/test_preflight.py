from __future__ import annotations

from pathlib import Path

from raspi_revive.preflight import run_runtime_preflight


def test_preflight_passes_for_repo_src() -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    errors = run_runtime_preflight(src_dir)
    assert errors == []


def test_preflight_fails_for_missing_src(tmp_path: Path) -> None:
    errors = run_runtime_preflight(tmp_path / "does-not-exist")
    assert errors
    assert "source directory not found" in errors[0]


def _write_minimal_config(path: Path) -> None:
    path.write_text(
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
host_heartbeat_stale_sec = 30.0
gpio_heartbeat_stale_sec = 30.0
sentinel_stats_stale_sec = 30.0
sentinel_state_stale_sec = 30.0
required_consecutive_sentinel_failure = 1
required_consecutive_host_degraded = 1
required_consecutive_freeze_suspected = 1

[guard]
cooldown_seconds = 120.0
lockout_window_seconds = 1800.0
max_actions_per_window = 3
post_action_verification_wait_seconds = 120.0
post_boot_reconciliation_wait_seconds = 120.0

[paths]
host_heartbeat_path = "__TMP__/facts/host-heartbeat.json"
gpio_heartbeat_path = "__TMP__/facts/gpio-heartbeat.json"
sentinel_stats_path = "__TMP__/facts/sentinel/stats.json"
sentinel_state_path = "__TMP__/facts/sentinel/state.json"
observations_log_path = "__TMP__/logs/observations.jsonl"
decisions_log_path = "__TMP__/logs/decisions.jsonl"
actions_log_path = "__TMP__/logs/actions.jsonl"
events_log_path = "__TMP__/logs/events.jsonl"
controller_state_path = "__TMP__/state/controller-state.json"
export_meta_path = "__TMP__/facts/meta.json"

[actions]
dry_run = true
enable_restart_sentinel = false
enable_remote_reboot = false
enable_gpio_reboot = false
enable_power_button_pulse = false
enabled_phases = ["A"]
restart_sentinel_cmd = ["true"]
remote_reboot_cmd = ["true"]
gpio_reboot_cmd = ["true"]
power_button_pulse_cmd = ["true"]

[loop]
cycle_seconds = 1.0

[mode]
maintenance_mode = false

[notify]
enabled = false
candidate_states = ["HOST_DEGRADED", "FREEZE_SUSPECTED"]
candidate_hold_seconds = 300.0
queue_retry_interval_seconds = 60.0
backoff_after_seconds = 300.0
backoff_multiplier = 2.0
backoff_max_seconds = 3600.0
discord_webhook_url = ""
remote_append_enabled = false
remote_jsonl_path = "__TMP__/notify/remote-events.jsonl"
queue_path = "__TMP__/notify/notify-queue.json"
stats_path = "__TMP__/notify/notify-stats.json"
events_path = "__TMP__/notify/notify-events.jsonl"
""".replace("__TMP__", str(path.parent)),
        encoding="utf-8",
    )


def test_preflight_passes_with_config_and_controller_init(tmp_path: Path) -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    config_path = tmp_path / "controller.toml"
    _write_minimal_config(config_path)
    errors = run_runtime_preflight(
        src_dir,
        config_path=config_path,
        check_runtime_writable=True,
        instantiate_controller=True,
    )
    assert errors == []


def test_preflight_fails_for_missing_config(tmp_path: Path) -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    errors = run_runtime_preflight(
        src_dir,
        config_path=tmp_path / "missing.toml",
        instantiate_controller=True,
    )
    assert errors
    assert "failed to load config" in errors[0]
