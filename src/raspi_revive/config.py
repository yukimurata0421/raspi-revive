from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib

NOTIFY_DEFAULT_CANDIDATE_STATES = frozenset({"HOST_DEGRADED", "FREEZE_SUSPECTED"})
NOTIFY_DEFAULT_CANDIDATE_HOLD_SECONDS = 300.0
NOTIFY_DEFAULT_QUEUE_RETRY_INTERVAL_SECONDS = 60.0
NOTIFY_DEFAULT_BACKOFF_AFTER_SECONDS = 300.0
NOTIFY_DEFAULT_BACKOFF_MULTIPLIER = 2.0
NOTIFY_DEFAULT_BACKOFF_MAX_SECONDS = 3600.0
NOTIFY_DEFAULT_REMOTE_JSONL_PATH = "/var/lib/raspi-revive-agent/revive-notify-events.jsonl"
NOTIFY_DEFAULT_STATS_FLUSH_INTERVAL_SECONDS = 60.0
NOTIFY_DEFAULT_MAX_QUEUE_SIZE = 256
NOTIFY_DEFAULT_MAX_EVENT_AGE_SECONDS = 86400.0


@dataclass(slots=True)
class ProbeConfig:
    ping_target: str
    ping_timeout_sec: float
    ping_retries: int
    ssh_target: str
    ssh_timeout_sec: float
    ssh_retries: int
    ssh_options: list[str]


@dataclass(slots=True)
class ThresholdConfig:
    host_heartbeat_stale_sec: float
    gpio_heartbeat_stale_sec: float
    sentinel_stats_stale_sec: float
    sentinel_state_stale_sec: float
    required_consecutive_sentinel_failure: int
    required_consecutive_host_degraded: int
    required_consecutive_freeze_suspected: int


@dataclass(slots=True)
class GuardConfig:
    cooldown_seconds: float
    lockout_window_seconds: float
    max_actions_per_window: int
    post_action_verification_wait_seconds: float
    post_boot_reconciliation_wait_seconds: float


@dataclass(slots=True)
class PathConfig:
    host_heartbeat_path: Path
    gpio_heartbeat_path: Path
    sentinel_stats_path: Path
    sentinel_state_path: Path
    observations_log_path: Path
    decisions_log_path: Path
    actions_log_path: Path
    events_log_path: Path
    controller_state_path: Path


@dataclass(slots=True)
class ActionConfig:
    dry_run: bool
    enable_restart_sentinel: bool
    enable_remote_reboot: bool
    enable_gpio_reboot: bool
    enable_power_button_pulse: bool
    restart_sentinel_cmd: list[str]
    remote_reboot_cmd: list[str]
    gpio_reboot_cmd: list[str]
    power_button_pulse_cmd: list[str]


@dataclass(slots=True)
class LoopConfig:
    cycle_seconds: float


@dataclass(slots=True)
class ControllerModeConfig:
    maintenance_mode: bool


@dataclass(slots=True)
class NotifyConfig:
    enabled: bool
    candidate_states: frozenset[str]
    candidate_hold_seconds: float
    queue_retry_interval_seconds: float
    backoff_after_seconds: float
    backoff_multiplier: float
    backoff_max_seconds: float
    discord_webhook_url: str
    remote_append_enabled: bool
    remote_jsonl_path: str
    queue_path: Path
    stats_path: Path
    events_path: Path
    stats_flush_interval_seconds: float = NOTIFY_DEFAULT_STATS_FLUSH_INTERVAL_SECONDS
    max_queue_size: int = NOTIFY_DEFAULT_MAX_QUEUE_SIZE
    max_event_age_seconds: float = NOTIFY_DEFAULT_MAX_EVENT_AGE_SECONDS


@dataclass(slots=True)
class ControllerConfig:
    probe: ProbeConfig
    threshold: ThresholdConfig
    guard: GuardConfig
    paths: PathConfig
    actions: ActionConfig
    loop: LoopConfig
    mode: ControllerModeConfig
    notify: NotifyConfig


def _as_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def load_controller_config(path: str | Path) -> ControllerConfig:
    with Path(path).open("rb") as f:
        data = tomllib.load(f)

    probe = data["probe"]
    threshold = data["threshold"]
    guard = data["guard"]
    paths = data["paths"]
    actions = data["actions"]
    loop = data.get("loop", {})
    mode = data.get("mode", {})
    notify = data.get("notify", {})

    webhook_url = str(notify.get("discord_webhook_url", "")).strip()
    webhook_env = str(notify.get("discord_webhook_url_env", "")).strip()
    if webhook_env:
        webhook_url = os.getenv(webhook_env, webhook_url).strip()

    default_queue_path = _as_path(str(_as_path(paths["controller_state_path"]).with_name("notify-queue.json")))
    default_stats_path = _as_path(str(_as_path(paths["controller_state_path"]).with_name("notify-stats.json")))
    default_events_path = _as_path(str(_as_path(paths["actions_log_path"]).with_name("notify-events.jsonl")))
    default_controller_events_path = _as_path(
        str(_as_path(paths["actions_log_path"]).with_name("events.jsonl"))
    )

    return ControllerConfig(
        probe=ProbeConfig(
            ping_target=str(probe["ping_target"]),
            ping_timeout_sec=float(probe.get("ping_timeout_sec", 1.0)),
            ping_retries=int(probe.get("ping_retries", 1)),
            ssh_target=str(probe["ssh_target"]),
            ssh_timeout_sec=float(probe.get("ssh_timeout_sec", 2.0)),
            ssh_retries=int(probe.get("ssh_retries", 1)),
            ssh_options=[str(x) for x in probe.get("ssh_options", [])],
        ),
        threshold=ThresholdConfig(
            host_heartbeat_stale_sec=float(threshold["host_heartbeat_stale_sec"]),
            gpio_heartbeat_stale_sec=float(threshold["gpio_heartbeat_stale_sec"]),
            sentinel_stats_stale_sec=float(threshold["sentinel_stats_stale_sec"]),
            sentinel_state_stale_sec=float(threshold["sentinel_state_stale_sec"]),
            required_consecutive_sentinel_failure=int(
                threshold.get("required_consecutive_sentinel_failure", 1)
            ),
            required_consecutive_host_degraded=int(
                threshold.get("required_consecutive_host_degraded", 1)
            ),
            required_consecutive_freeze_suspected=int(
                threshold.get("required_consecutive_freeze_suspected", 3)
            ),
        ),
        guard=GuardConfig(
            cooldown_seconds=float(guard["cooldown_seconds"]),
            lockout_window_seconds=float(guard["lockout_window_seconds"]),
            max_actions_per_window=int(guard["max_actions_per_window"]),
            post_action_verification_wait_seconds=float(
                guard["post_action_verification_wait_seconds"]
            ),
            post_boot_reconciliation_wait_seconds=float(
                guard.get(
                    "post_boot_reconciliation_wait_seconds",
                    guard["post_action_verification_wait_seconds"],
                )
            ),
        ),
        paths=PathConfig(
            host_heartbeat_path=_as_path(paths["host_heartbeat_path"]),
            gpio_heartbeat_path=_as_path(paths["gpio_heartbeat_path"]),
            sentinel_stats_path=_as_path(paths["sentinel_stats_path"]),
            sentinel_state_path=_as_path(paths["sentinel_state_path"]),
            observations_log_path=_as_path(paths["observations_log_path"]),
            decisions_log_path=_as_path(paths["decisions_log_path"]),
            actions_log_path=_as_path(paths["actions_log_path"]),
            events_log_path=_as_path(str(paths.get("events_log_path", default_controller_events_path))),
            controller_state_path=_as_path(paths["controller_state_path"]),
        ),
        actions=ActionConfig(
            dry_run=bool(actions.get("dry_run", True)),
            enable_restart_sentinel=bool(actions.get("enable_restart_sentinel", True)),
            enable_remote_reboot=bool(actions.get("enable_remote_reboot", True)),
            enable_gpio_reboot=bool(actions.get("enable_gpio_reboot", True)),
            enable_power_button_pulse=bool(actions.get("enable_power_button_pulse", True)),
            restart_sentinel_cmd=[str(x) for x in actions["restart_sentinel_cmd"]],
            remote_reboot_cmd=[str(x) for x in actions["remote_reboot_cmd"]],
            gpio_reboot_cmd=[str(x) for x in actions["gpio_reboot_cmd"]],
            power_button_pulse_cmd=[str(x) for x in actions.get("power_button_pulse_cmd", [])],
        ),
        loop=LoopConfig(cycle_seconds=float(loop.get("cycle_seconds", 10.0))),
        mode=ControllerModeConfig(maintenance_mode=bool(mode.get("maintenance_mode", False))),
        notify=NotifyConfig(
            enabled=bool(notify.get("enabled", False)),
            candidate_states=frozenset(
                str(x)
                for x in notify.get("candidate_states", sorted(NOTIFY_DEFAULT_CANDIDATE_STATES))
            ),
            candidate_hold_seconds=float(
                notify.get("candidate_hold_seconds", NOTIFY_DEFAULT_CANDIDATE_HOLD_SECONDS)
            ),
            queue_retry_interval_seconds=float(
                notify.get(
                    "queue_retry_interval_seconds",
                    NOTIFY_DEFAULT_QUEUE_RETRY_INTERVAL_SECONDS,
                )
            ),
            backoff_after_seconds=float(
                notify.get("backoff_after_seconds", NOTIFY_DEFAULT_BACKOFF_AFTER_SECONDS)
            ),
            backoff_multiplier=float(
                notify.get("backoff_multiplier", NOTIFY_DEFAULT_BACKOFF_MULTIPLIER)
            ),
            backoff_max_seconds=float(
                notify.get("backoff_max_seconds", NOTIFY_DEFAULT_BACKOFF_MAX_SECONDS)
            ),
            discord_webhook_url=webhook_url,
            remote_append_enabled=bool(notify.get("remote_append_enabled", True)),
            remote_jsonl_path=str(
                notify.get("remote_jsonl_path", NOTIFY_DEFAULT_REMOTE_JSONL_PATH)
            ),
            queue_path=_as_path(str(notify.get("queue_path", default_queue_path))),
            stats_path=_as_path(str(notify.get("stats_path", default_stats_path))),
            events_path=_as_path(str(notify.get("events_path", default_events_path))),
            stats_flush_interval_seconds=float(
                notify.get(
                    "stats_flush_interval_seconds",
                    NOTIFY_DEFAULT_STATS_FLUSH_INTERVAL_SECONDS,
                )
            ),
            max_queue_size=int(notify.get("max_queue_size", NOTIFY_DEFAULT_MAX_QUEUE_SIZE)),
            max_event_age_seconds=float(
                notify.get("max_event_age_seconds", NOTIFY_DEFAULT_MAX_EVENT_AGE_SECONDS)
            ),
        ),
    )
