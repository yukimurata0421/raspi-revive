from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ControllerState(str, Enum):
    HEALTHY = "HEALTHY"
    MANAGEMENT_PLANE_DEGRADED = "MANAGEMENT_PLANE_DEGRADED"
    SENTINEL_ONLY_FAILURE = "SENTINEL_ONLY_FAILURE"
    TELEMETRY_PIPELINE_FAILURE = "TELEMETRY_PIPELINE_FAILURE"
    HOST_DEGRADED = "HOST_DEGRADED"
    FREEZE_SUSPECTED = "FREEZE_SUSPECTED"
    NETWORK_ONLY_ISSUE = "NETWORK_ONLY_ISSUE"
    RECOVERY_IN_PROGRESS = "RECOVERY_IN_PROGRESS"
    POST_BOOT_RECONCILIATION = "POST_BOOT_RECONCILIATION"
    RECOVERY_PARTIAL = "RECOVERY_PARTIAL"
    COOLDOWN = "COOLDOWN"
    LOCKOUT = "LOCKOUT"


class RecoveryAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    RESTART_SENTINEL = "RESTART_SENTINEL"
    REMOTE_REBOOT = "REMOTE_REBOOT"
    GPIO_REBOOT = "GPIO_REBOOT"
    POWER_BUTTON_PULSE = "POWER_BUTTON_PULSE"


@dataclass(slots=True)
class Observation:
    ts: float
    host_boot_id: str | None
    host_seq: int | None
    host_monotonic_sec: float | None
    host_wall_time: str | None
    host_heartbeat_age_sec: float | None
    host_heartbeat_fresh: bool
    host_heartbeat_progressing: bool
    gpio_heartbeat_age_sec: float | None
    gpio_heartbeat_fresh: bool
    sentinel_stats_age_sec: float | None
    sentinel_stats_fresh: bool
    sentinel_state_age_sec: float | None
    sentinel_state_fresh: bool
    ping_ok: bool
    ssh_ok: bool


@dataclass(slots=True)
class Evidence:
    out_of_band_gpio_fresh: bool
    network_dependent_host_heartbeat_fresh: bool
    network_dependent_host_heartbeat_progressing: bool
    network_dependent_sentinel_stats_fresh: bool
    network_dependent_sentinel_state_fresh: bool
    network_dependent_ping_ok: bool
    network_dependent_ssh_ok: bool

    @property
    def gpio_fresh(self) -> bool:
        return self.out_of_band_gpio_fresh

    @property
    def host_heartbeat_fresh(self) -> bool:
        return self.network_dependent_host_heartbeat_fresh

    @property
    def host_heartbeat_progressing(self) -> bool:
        return self.network_dependent_host_heartbeat_progressing

    @property
    def sentinel_stats_fresh(self) -> bool:
        return self.network_dependent_sentinel_stats_fresh

    @property
    def sentinel_state_fresh(self) -> bool:
        return self.network_dependent_sentinel_state_fresh

    @property
    def ping_ok(self) -> bool:
        return self.network_dependent_ping_ok

    @property
    def ssh_ok(self) -> bool:
        return self.network_dependent_ssh_ok

    @property
    def network_path_evidence_ok(self) -> bool:
        return self.ping_ok and self.ssh_ok and self.host_heartbeat_fresh

    @property
    def out_of_band_host_alive(self) -> bool:
        return self.gpio_fresh

    @property
    def network_dependent_any_failure(self) -> bool:
        return (not self.ping_ok) or (not self.ssh_ok) or (not self.host_heartbeat_fresh)

    @property
    def sentinel_fresh(self) -> bool:
        return self.sentinel_stats_fresh and self.sentinel_state_fresh


@dataclass(slots=True)
class Decision:
    classified_state: ControllerState
    chosen_action: RecoveryAction
    reason: str
    evidence: Evidence
    cooldown_active: bool
    lockout_active: bool
    maintenance_mode_active: bool
    incident_key: str
    lockout_latch_event: str | None
    correlation_id: str


@dataclass(slots=True)
class PendingVerification:
    action: RecoveryAction
    previous_boot_id: str | None
    created_ts: float
    deadline_ts: float
    attempt_id: str
    correlation_id: str


@dataclass(slots=True)
class PostBootReconciliation:
    action: RecoveryAction
    boot_id: str | None
    created_ts: float
    deadline_ts: float
    attempt_id: str
    correlation_id: str


@dataclass(slots=True)
class ControllerRuntimeState:
    current_state: ControllerState = ControllerState.HEALTHY
    consecutive_counts: dict[str, int] = field(default_factory=dict)
    last_action_ts: float | None = None
    action_timestamps: list[float] = field(default_factory=list)
    lockout_until_ts: float | None = None
    pending_verification: PendingVerification | None = None
    post_boot_reconciliation: PostBootReconciliation | None = None
    previous_host_boot_id: str | None = None
    previous_host_seq: int | None = None
    last_telemetry_healthy_boot_id: str | None = None
    last_action_incident_key: str | None = None
    lockout_latch_active: bool = False
    last_emitted_controller_state: str | None = None
    last_phase_label: str | None = None
    last_action_gate_signature: str | None = None
    last_maintenance_mode: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        pending = None
        if self.pending_verification is not None:
            pending = {
                "action": self.pending_verification.action.value,
                "previous_boot_id": self.pending_verification.previous_boot_id,
                "created_ts": self.pending_verification.created_ts,
                "deadline_ts": self.pending_verification.deadline_ts,
                "attempt_id": self.pending_verification.attempt_id,
                "correlation_id": self.pending_verification.correlation_id,
            }
        post_boot = None
        if self.post_boot_reconciliation is not None:
            post_boot = {
                "action": self.post_boot_reconciliation.action.value,
                "boot_id": self.post_boot_reconciliation.boot_id,
                "created_ts": self.post_boot_reconciliation.created_ts,
                "deadline_ts": self.post_boot_reconciliation.deadline_ts,
                "attempt_id": self.post_boot_reconciliation.attempt_id,
                "correlation_id": self.post_boot_reconciliation.correlation_id,
            }
        return {
            "current_state": self.current_state.value,
            "consecutive_counts": dict(self.consecutive_counts),
            "last_action_ts": self.last_action_ts,
            "action_timestamps": list(self.action_timestamps),
            "lockout_until_ts": self.lockout_until_ts,
            "pending_verification": pending,
            "post_boot_reconciliation": post_boot,
            "previous_host_boot_id": self.previous_host_boot_id,
            "previous_host_seq": self.previous_host_seq,
            "last_telemetry_healthy_boot_id": self.last_telemetry_healthy_boot_id,
            "last_action_incident_key": self.last_action_incident_key,
            "lockout_latch_active": self.lockout_latch_active,
            "last_emitted_controller_state": self.last_emitted_controller_state,
            "last_phase_label": self.last_phase_label,
            "last_action_gate_signature": self.last_action_gate_signature,
            "last_maintenance_mode": self.last_maintenance_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControllerRuntimeState":
        pending = data.get("pending_verification")
        pending_obj = None
        if pending is not None:
            pending_obj = PendingVerification(
                action=RecoveryAction(pending["action"]),
                previous_boot_id=pending.get("previous_boot_id"),
                created_ts=float(pending["created_ts"]),
                deadline_ts=float(pending["deadline_ts"]),
                attempt_id=str(pending.get("attempt_id", "")),
                correlation_id=str(pending["correlation_id"]),
            )
        post_boot = data.get("post_boot_reconciliation")
        post_boot_obj = None
        if post_boot is not None:
            post_boot_obj = PostBootReconciliation(
                action=RecoveryAction(post_boot["action"]),
                boot_id=post_boot.get("boot_id"),
                created_ts=float(post_boot["created_ts"]),
                deadline_ts=float(post_boot["deadline_ts"]),
                attempt_id=str(post_boot.get("attempt_id", "")),
                correlation_id=str(post_boot["correlation_id"]),
            )
        return cls(
            current_state=ControllerState(data.get("current_state", ControllerState.HEALTHY.value)),
            consecutive_counts={str(k): int(v) for k, v in data.get("consecutive_counts", {}).items()},
            last_action_ts=(None if data.get("last_action_ts") is None else float(data["last_action_ts"])),
            action_timestamps=[float(x) for x in data.get("action_timestamps", [])],
            lockout_until_ts=(
                None if data.get("lockout_until_ts") is None else float(data["lockout_until_ts"])
            ),
            pending_verification=pending_obj,
            post_boot_reconciliation=post_boot_obj,
            previous_host_boot_id=data.get("previous_host_boot_id"),
            previous_host_seq=(
                None if data.get("previous_host_seq") is None else int(data["previous_host_seq"])
            ),
            last_telemetry_healthy_boot_id=data.get("last_telemetry_healthy_boot_id"),
            last_action_incident_key=data.get("last_action_incident_key"),
            lockout_latch_active=bool(data.get("lockout_latch_active", False)),
            last_emitted_controller_state=data.get("last_emitted_controller_state"),
            last_phase_label=data.get("last_phase_label"),
            last_action_gate_signature=data.get("last_action_gate_signature"),
            last_maintenance_mode=(
                None
                if data.get("last_maintenance_mode") is None
                else bool(data.get("last_maintenance_mode"))
            ),
        )
