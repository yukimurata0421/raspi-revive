from __future__ import annotations

from dataclasses import dataclass
import time
import uuid

from .config import ControllerConfig
from .evaluator import Classification
from .models import (
    ControllerRuntimeState,
    ControllerState,
    Decision,
    PendingVerification,
    PostBootReconciliation,
    RecoveryAction,
)


@dataclass(slots=True)
class StateMachine:
    config: ControllerConfig

    def decide(
        self,
        runtime: ControllerRuntimeState,
        classification: Classification,
        current_boot_id: str | None,
    ) -> Decision:
        now_ts = time.time()
        correlation_id = str(uuid.uuid4())
        self._remember_boot_telemetry_health(runtime, classification, current_boot_id)
        incident_key = self._incident_key(runtime, classification, current_boot_id)
        lockout_latch_event = self._update_lockout_latch(runtime, now_ts)

        if self._lockout_active(runtime, now_ts):
            return Decision(
                classified_state=ControllerState.LOCKOUT,
                chosen_action=RecoveryAction.NO_ACTION,
                reason="lockout active",
                evidence=classification.evidence,
                cooldown_active=False,
                lockout_active=True,
                maintenance_mode_active=self.config.mode.maintenance_mode,
                incident_key=incident_key,
                lockout_latch_event=lockout_latch_event,
                correlation_id=correlation_id,
            )

        if runtime.pending_verification is not None:
            if self._verification_satisfied(runtime, current_boot_id):
                pending = runtime.pending_verification
                runtime.pending_verification = None
                runtime.post_boot_reconciliation = PostBootReconciliation(
                    action=pending.action,
                    boot_id=current_boot_id,
                    created_ts=now_ts,
                    deadline_ts=now_ts + self.config.guard.post_boot_reconciliation_wait_seconds,
                    attempt_id=pending.attempt_id,
                    correlation_id=pending.correlation_id,
                )
            elif now_ts < runtime.pending_verification.deadline_ts:
                return Decision(
                    classified_state=ControllerState.RECOVERY_IN_PROGRESS,
                    chosen_action=RecoveryAction.NO_ACTION,
                    reason="waiting for post-action verification",
                    evidence=classification.evidence,
                    cooldown_active=False,
                    lockout_active=False,
                    maintenance_mode_active=self.config.mode.maintenance_mode,
                    incident_key=incident_key,
                    lockout_latch_event=lockout_latch_event,
                    correlation_id=runtime.pending_verification.correlation_id,
                )
            else:
                runtime.pending_verification = None

        if runtime.post_boot_reconciliation is not None:
            if self._telemetry_reconciled(classification):
                runtime.post_boot_reconciliation = None
            elif now_ts < runtime.post_boot_reconciliation.deadline_ts:
                return Decision(
                    classified_state=ControllerState.POST_BOOT_RECONCILIATION,
                    chosen_action=RecoveryAction.NO_ACTION,
                    reason="post-boot telemetry reconciliation in progress",
                    evidence=classification.evidence,
                    cooldown_active=False,
                    lockout_active=False,
                    maintenance_mode_active=self.config.mode.maintenance_mode,
                    incident_key=incident_key,
                    lockout_latch_event=lockout_latch_event,
                    correlation_id=runtime.post_boot_reconciliation.correlation_id,
                )
            else:
                runtime.post_boot_reconciliation = None
                return Decision(
                    classified_state=ControllerState.RECOVERY_PARTIAL,
                    chosen_action=RecoveryAction.NO_ACTION,
                    reason="post-boot telemetry did not reconcile before deadline",
                    evidence=classification.evidence,
                    cooldown_active=False,
                    lockout_active=False,
                    maintenance_mode_active=self.config.mode.maintenance_mode,
                    incident_key=incident_key,
                    lockout_latch_event=lockout_latch_event,
                    correlation_id=correlation_id,
                )

        if self.config.mode.maintenance_mode:
            return Decision(
                classified_state=classification.state,
                chosen_action=RecoveryAction.NO_ACTION,
                reason="maintenance mode active; interventions disabled",
                evidence=classification.evidence,
                cooldown_active=False,
                lockout_active=False,
                maintenance_mode_active=True,
                incident_key=incident_key,
                lockout_latch_event=lockout_latch_event,
                correlation_id=correlation_id,
            )

        cooldown_active = self._cooldown_active(runtime, now_ts)
        if cooldown_active:
            return Decision(
                classified_state=ControllerState.COOLDOWN,
                chosen_action=RecoveryAction.NO_ACTION,
                reason="cooldown active",
                evidence=classification.evidence,
                cooldown_active=True,
                lockout_active=False,
                maintenance_mode_active=self.config.mode.maintenance_mode,
                incident_key=incident_key,
                lockout_latch_event=lockout_latch_event,
                correlation_id=correlation_id,
            )

        self._update_consecutive(runtime, classification.state)
        if classification.state == ControllerState.HEALTHY:
            runtime.last_action_incident_key = None

        action = RecoveryAction.NO_ACTION
        reason = classification.reason

        if classification.state == ControllerState.SENTINEL_ONLY_FAILURE:
            required = self.config.threshold.required_consecutive_sentinel_failure
            if self._count(runtime, classification.state) >= required:
                action = RecoveryAction.RESTART_SENTINEL
                reason = f"sentinel-only failure sustained for {required} cycles"
        elif classification.state == ControllerState.HOST_DEGRADED:
            required = self.config.threshold.required_consecutive_host_degraded
            if self._count(runtime, classification.state) >= required:
                if current_boot_id is not None and runtime.last_telemetry_healthy_boot_id == current_boot_id:
                    action = RecoveryAction.REMOTE_REBOOT
                    reason = f"host degraded sustained for {required} cycles with telemetry previously healthy in same boot"
                else:
                    reason = "host degraded observed but telemetry baseline not established in this boot; hold reboot"
        elif classification.state == ControllerState.FREEZE_SUSPECTED:
            required = self.config.threshold.required_consecutive_freeze_suspected
            if self._count(runtime, classification.state) >= required:
                action = RecoveryAction.GPIO_REBOOT
                reason = f"freeze suspected sustained for {required} cycles"

        if (
            action != RecoveryAction.NO_ACTION
            and runtime.last_action_incident_key is not None
            and runtime.last_action_incident_key == incident_key
        ):
            action = RecoveryAction.NO_ACTION
            reason = "incident already handled; waiting evidence transition"

        if action != RecoveryAction.NO_ACTION and not self._action_enabled(action):
            action = RecoveryAction.NO_ACTION
            reason = "action disabled by rollout phase policy"

        return Decision(
            classified_state=classification.state,
            chosen_action=action,
            reason=reason,
            evidence=classification.evidence,
            cooldown_active=False,
            lockout_active=False,
            maintenance_mode_active=self.config.mode.maintenance_mode,
            incident_key=incident_key,
            lockout_latch_event=lockout_latch_event,
            correlation_id=correlation_id,
        )

    def register_action(
        self,
        runtime: ControllerRuntimeState,
        action: RecoveryAction,
        correlation_id: str,
        incident_key: str,
        host_boot_id: str | None,
    ) -> None:
        if action == RecoveryAction.NO_ACTION:
            if runtime.current_state == ControllerState.HEALTHY:
                runtime.last_action_incident_key = None
            return

        now_ts = time.time()
        runtime.last_action_ts = now_ts
        runtime.action_timestamps.append(now_ts)
        runtime.action_timestamps = [
            x
            for x in runtime.action_timestamps
            if now_ts - x <= self.config.guard.lockout_window_seconds
        ]

        if len(runtime.action_timestamps) >= self.config.guard.max_actions_per_window:
            runtime.lockout_until_ts = now_ts + self.config.guard.lockout_window_seconds

        if action in (RecoveryAction.REMOTE_REBOOT, RecoveryAction.GPIO_REBOOT):
            attempt_id = str(uuid.uuid4())
            runtime.pending_verification = PendingVerification(
                action=action,
                previous_boot_id=host_boot_id,
                created_ts=now_ts,
                deadline_ts=now_ts + self.config.guard.post_action_verification_wait_seconds,
                attempt_id=attempt_id,
                correlation_id=correlation_id,
            )
            runtime.post_boot_reconciliation = None
        runtime.last_action_incident_key = incident_key

    def _cooldown_active(self, runtime: ControllerRuntimeState, now_ts: float) -> bool:
        if runtime.last_action_ts is None:
            return False
        return (now_ts - runtime.last_action_ts) < self.config.guard.cooldown_seconds

    def _lockout_active(self, runtime: ControllerRuntimeState, now_ts: float) -> bool:
        if runtime.lockout_until_ts is None:
            return False
        return now_ts < runtime.lockout_until_ts

    def _count(self, runtime: ControllerRuntimeState, state: ControllerState) -> int:
        return runtime.consecutive_counts.get(state.value, 0)

    def _update_consecutive(self, runtime: ControllerRuntimeState, current_state: ControllerState) -> None:
        if current_state == ControllerState.HEALTHY:
            runtime.consecutive_counts.clear()
            return

        keep = runtime.consecutive_counts.get(current_state.value, 0)
        runtime.consecutive_counts.clear()
        runtime.consecutive_counts[current_state.value] = keep + 1

    def _verification_satisfied(
        self,
        runtime: ControllerRuntimeState,
        current_boot_id: str | None,
    ) -> bool:
        pending = runtime.pending_verification
        if pending is None:
            return True
        if pending.previous_boot_id is None and current_boot_id is not None:
            return True
        if pending.previous_boot_id is None:
            return False
        if current_boot_id is None:
            return False
        return current_boot_id != pending.previous_boot_id

    def _incident_key(
        self,
        runtime: ControllerRuntimeState,
        classification: Classification,
        current_boot_id: str | None,
    ) -> str:
        ev = classification.evidence
        missing = [
            name
            for name, ok in (
                ("gpio", ev.gpio_fresh),
                ("host_hb", ev.host_heartbeat_fresh),
                ("sentinel", ev.sentinel_fresh),
                ("ping", ev.ping_ok),
                ("ssh", ev.ssh_ok),
            )
            if not ok
        ]
        parts = [
            classification.state.value,
            f"boot={current_boot_id or 'unknown'}",
            f"telemetry_boot={runtime.last_telemetry_healthy_boot_id or 'unknown'}",
            f"gpio={int(ev.gpio_fresh)}",
            f"host_hb={int(ev.host_heartbeat_fresh)}",
            f"sentinel={int(ev.sentinel_fresh)}",
            f"ping={int(ev.ping_ok)}",
            f"ssh={int(ev.ssh_ok)}",
            f"missing={','.join(missing) if missing else 'none'}",
        ]
        return "|".join(parts)

    def _remember_boot_telemetry_health(
        self,
        runtime: ControllerRuntimeState,
        classification: Classification,
        current_boot_id: str | None,
    ) -> None:
        if current_boot_id is None:
            return
        ev = classification.evidence
        if ev.host_heartbeat_fresh and ev.host_heartbeat_progressing and ev.sentinel_fresh and ev.ssh_ok:
            runtime.last_telemetry_healthy_boot_id = current_boot_id

    def _telemetry_reconciled(self, classification: Classification) -> bool:
        ev = classification.evidence
        return ev.host_heartbeat_fresh and ev.host_heartbeat_progressing and ev.sentinel_fresh

    def _update_lockout_latch(self, runtime: ControllerRuntimeState, now_ts: float) -> str | None:
        active = self._lockout_active(runtime, now_ts)
        if active and not runtime.lockout_latch_active:
            runtime.lockout_latch_active = True
            return "lockout_entered"
        if active and runtime.lockout_latch_active:
            return "lockout_still_active"
        if (not active) and runtime.lockout_latch_active:
            runtime.lockout_latch_active = False
            return "lockout_cleared"
        return None

    def _action_enabled(self, action: RecoveryAction) -> bool:
        if action == RecoveryAction.RESTART_SENTINEL:
            return self.config.actions.enable_restart_sentinel
        if action == RecoveryAction.REMOTE_REBOOT:
            return self.config.actions.enable_remote_reboot
        if action == RecoveryAction.GPIO_REBOOT:
            return self.config.actions.enable_gpio_reboot
        if action == RecoveryAction.POWER_BUTTON_PULSE:
            return self.config.actions.enable_power_button_pulse
        return True
