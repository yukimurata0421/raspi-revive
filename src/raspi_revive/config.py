from __future__ import annotations

from dataclasses import dataclass, field
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
LOG_DEFAULT_MAX_LOG_SIZE_MB = 10.0
LOG_DEFAULT_ROTATION_COUNT = 3


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
    export_meta_path: Path | None = None
    intervention_evidence_dir: Path | None = None
    incident_summary_path: Path | None = None
    controller_stats_path: Path | None = None


@dataclass(slots=True)
class ActionConfig:
    dry_run: bool
    enable_restart_sentinel: bool
    enable_remote_reboot: bool
    enable_gpio_reboot: bool
    enable_power_button_pulse: bool
    enabled_phases: frozenset[str]
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
    remote_reboot_discord_webhook_url: str = ""


@dataclass(slots=True)
class NotifyProviderConfig:
    name: str
    kind: str
    enabled: bool
    webhook_url: str = ""
    remote_jsonl_path: str = ""


@dataclass(slots=True)
class LogConfig:
    max_log_size_mb: float = LOG_DEFAULT_MAX_LOG_SIZE_MB
    rotation_count: int = LOG_DEFAULT_ROTATION_COUNT

    @property
    def max_log_size_bytes(self) -> int:
        return int(max(0.0, self.max_log_size_mb) * 1024 * 1024)


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
    notify_providers: tuple[NotifyProviderConfig, ...] = ()
    logs: LogConfig = field(default_factory=LogConfig)


def _as_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def _normalize_phase_token(raw: str) -> str:
    normalized = str(raw).strip().upper()
    if normalized.startswith("PHASE_"):
        normalized = normalized.split("PHASE_", 1)[1]
    return normalized


def _validate_enabled_phases(raw_values: list[str]) -> frozenset[str]:
    allowed = {"A", "B", "C", "D"}
    phases = {_normalize_phase_token(x) for x in raw_values}
    invalid = sorted(x for x in phases if x not in allowed)
    if invalid:
        raise ValueError(f"invalid enabled_phases: {invalid}")
    if "A" not in phases:
        phases.add("A")
    return frozenset(phases)


def _derive_enabled_phases_from_legacy_flags(
    *,
    dry_run: bool,
    enable_restart_sentinel: bool,
    enable_remote_reboot: bool,
    enable_gpio_reboot: bool,
    enable_power_button_pulse: bool,
) -> frozenset[str]:
    phases = {"A"}
    if enable_restart_sentinel:
        phases.add("B")
    if enable_remote_reboot:
        phases.add("C")
    if enable_gpio_reboot or enable_power_button_pulse:
        phases.add("D")
    # Legacy phase-A profile keeps only A.
    if dry_run and not enable_restart_sentinel and not enable_remote_reboot and not enable_gpio_reboot and not enable_power_button_pulse:
        phases = {"A"}
    return frozenset(phases)


def _load_notify_providers(
    *,
    notify: dict,
    legacy_webhook_url: str,
    legacy_remote_append_enabled: bool,
    legacy_remote_jsonl_path: str,
) -> tuple[NotifyProviderConfig, ...]:
    providers_raw = notify.get("providers")
    providers: list[NotifyProviderConfig] = []
    if isinstance(providers_raw, list):
        for idx, raw_item in enumerate(providers_raw):
            if not isinstance(raw_item, dict):
                continue
            kind = str(raw_item.get("kind", raw_item.get("type", ""))).strip()
            if not kind:
                continue
            name = str(raw_item.get("name", f"{kind}-{idx+1}")).strip() or f"{kind}-{idx+1}"
            enabled = bool(raw_item.get("enabled", True))
            webhook_url = str(raw_item.get("webhook_url", "")).strip()
            webhook_env = str(raw_item.get("webhook_url_env", "")).strip()
            if webhook_env:
                webhook_url = os.getenv(webhook_env, webhook_url).strip()
            remote_jsonl_path = str(
                raw_item.get("remote_jsonl_path", legacy_remote_jsonl_path)
            ).strip()
            if kind not in {"discord_webhook", "ssh_append"}:
                raise ValueError(f"unsupported notify provider kind: {kind}")
            providers.append(
                NotifyProviderConfig(
                    name=name,
                    kind=kind,
                    enabled=enabled,
                    webhook_url=webhook_url,
                    remote_jsonl_path=remote_jsonl_path,
                )
            )
        return tuple(providers)

    # Backward-compatible synthesis from legacy fields.
    if legacy_remote_append_enabled:
        providers.append(
            NotifyProviderConfig(
                name="ssh_append_default",
                kind="ssh_append",
                enabled=True,
                remote_jsonl_path=legacy_remote_jsonl_path,
            )
        )
    if legacy_webhook_url:
        providers.append(
            NotifyProviderConfig(
                name="discord_webhook_default",
                kind="discord_webhook",
                enabled=True,
                webhook_url=legacy_webhook_url,
            )
        )
    return tuple(providers)


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
    logs = data.get("logs", {})

    webhook_url = str(notify.get("discord_webhook_url", "")).strip()
    webhook_env = str(notify.get("discord_webhook_url_env", "")).strip()
    if webhook_env:
        webhook_url = os.getenv(webhook_env, webhook_url).strip()
    remote_reboot_webhook_url = str(notify.get("remote_reboot_discord_webhook_url", "")).strip()
    remote_reboot_webhook_env = str(
        notify.get("remote_reboot_discord_webhook_url_env", "")
    ).strip()
    if remote_reboot_webhook_env:
        remote_reboot_webhook_url = os.getenv(
            remote_reboot_webhook_env, remote_reboot_webhook_url
        ).strip()
    legacy_remote_append_enabled = bool(notify.get("remote_append_enabled", True))
    legacy_remote_jsonl_path = str(
        notify.get("remote_jsonl_path", NOTIFY_DEFAULT_REMOTE_JSONL_PATH)
    )
    notify_providers = _load_notify_providers(
        notify=notify,
        legacy_webhook_url=webhook_url,
        legacy_remote_append_enabled=legacy_remote_append_enabled,
        legacy_remote_jsonl_path=legacy_remote_jsonl_path,
    )

    default_queue_path = _as_path(str(_as_path(paths["controller_state_path"]).with_name("notify-queue.json")))
    default_stats_path = _as_path(str(_as_path(paths["controller_state_path"]).with_name("notify-stats.json")))
    default_events_path = _as_path(str(_as_path(paths["actions_log_path"]).with_name("notify-events.jsonl")))
    default_controller_events_path = _as_path(
        str(_as_path(paths["actions_log_path"]).with_name("events.jsonl"))
    )

    dry_run = bool(actions.get("dry_run", True))
    enable_restart_sentinel = bool(actions.get("enable_restart_sentinel", True))
    enable_remote_reboot = bool(actions.get("enable_remote_reboot", True))
    enable_gpio_reboot = bool(actions.get("enable_gpio_reboot", True))
    enable_power_button_pulse = bool(actions.get("enable_power_button_pulse", True))
    enabled_phases_raw = actions.get("enabled_phases")
    if isinstance(enabled_phases_raw, list):
        enabled_phases = _validate_enabled_phases([str(x) for x in enabled_phases_raw])
    else:
        enabled_phases = _derive_enabled_phases_from_legacy_flags(
            dry_run=dry_run,
            enable_restart_sentinel=enable_restart_sentinel,
            enable_remote_reboot=enable_remote_reboot,
            enable_gpio_reboot=enable_gpio_reboot,
            enable_power_button_pulse=enable_power_button_pulse,
        )

    host_heartbeat_path = _as_path(paths["host_heartbeat_path"])
    controller_state_path = _as_path(paths["controller_state_path"])
    runtime_state_dir = controller_state_path.parent
    sentinel_stats_path = _as_path(paths["sentinel_stats_path"])
    sentinel_state_path = _as_path(paths["sentinel_state_path"])
    export_meta_raw = paths.get("export_meta_path")
    export_meta_path = (
        _as_path(str(export_meta_raw))
        if export_meta_raw is not None
        else host_heartbeat_path.parent / "meta.json"
    )
    intervention_evidence_raw = paths.get("intervention_evidence_dir")
    intervention_evidence_dir = (
        _as_path(str(intervention_evidence_raw))
        if intervention_evidence_raw is not None
        else runtime_state_dir / "intervention-evidence"
    )
    incident_summary_raw = paths.get("incident_summary_path")
    incident_summary_path = (
        _as_path(str(incident_summary_raw))
        if incident_summary_raw is not None
        else runtime_state_dir / "incident-summary.json"
    )
    controller_stats_raw = paths.get("controller_stats_path")
    controller_stats_path = (
        _as_path(str(controller_stats_raw))
        if controller_stats_raw is not None
        else runtime_state_dir / "controller-stats.json"
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
            host_heartbeat_path=host_heartbeat_path,
            gpio_heartbeat_path=_as_path(paths["gpio_heartbeat_path"]),
            sentinel_stats_path=sentinel_stats_path,
            sentinel_state_path=sentinel_state_path,
            observations_log_path=_as_path(paths["observations_log_path"]),
            decisions_log_path=_as_path(paths["decisions_log_path"]),
            actions_log_path=_as_path(paths["actions_log_path"]),
            events_log_path=_as_path(str(paths.get("events_log_path", default_controller_events_path))),
            controller_state_path=controller_state_path,
            export_meta_path=export_meta_path,
            intervention_evidence_dir=intervention_evidence_dir,
            incident_summary_path=incident_summary_path,
            controller_stats_path=controller_stats_path,
        ),
        actions=ActionConfig(
            dry_run=dry_run,
            enable_restart_sentinel=enable_restart_sentinel,
            enable_remote_reboot=enable_remote_reboot,
            enable_gpio_reboot=enable_gpio_reboot,
            enable_power_button_pulse=enable_power_button_pulse,
            enabled_phases=enabled_phases,
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
            remote_reboot_discord_webhook_url=remote_reboot_webhook_url,
            remote_append_enabled=legacy_remote_append_enabled,
            remote_jsonl_path=legacy_remote_jsonl_path,
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
        notify_providers=notify_providers,
        logs=LogConfig(
            max_log_size_mb=float(logs.get("max_log_size_mb", LOG_DEFAULT_MAX_LOG_SIZE_MB)),
            rotation_count=int(logs.get("rotation_count", LOG_DEFAULT_ROTATION_COUNT)),
        ),
    )
