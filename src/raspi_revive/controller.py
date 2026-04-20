from __future__ import annotations

import time
from typing import Any

from .audit import AuditLogger
from .collector import ObservationCollector
from .config import ControllerConfig
from .evaluator import classify
from .executor import ActionExecutor
from .models import ControllerRuntimeState, Decision, RecoveryAction
from .notifier import NotifyDispatcher
from .probes import file_age_seconds
from .state_machine import StateMachine
from .state_store import load_runtime_state, save_runtime_state


class ReviveController:
    def __init__(self, config: ControllerConfig) -> None:
        self._config = config
        self._collector = ObservationCollector(config)
        self._state_machine = StateMachine(config)
        self._executor = ActionExecutor(config.actions)
        self._audit = AuditLogger(config.paths)
        self._notifier = NotifyDispatcher(config)
        self._runtime_state = load_runtime_state(config.paths.controller_state_path)
        # Force one baseline write after startup, then track actual persisted value.
        self._last_persisted_state: dict[str, Any] | None = None
        self._emit_startup_events(time.time())

    @property
    def runtime_state(self) -> ControllerRuntimeState:
        return self._runtime_state

    def run_cycle(self) -> None:
        obs = self._collector.collect(self._runtime_state.previous_host_seq)
        cycle_ts = obs.ts
        previous_state = self._runtime_state.current_state.value
        classification = classify(obs)
        decision = self._state_machine.decide(
            self._runtime_state,
            classification,
            current_boot_id=obs.host_boot_id,
        )

        self._runtime_state.current_state = decision.classified_state

        self._audit.log_observation(
            ts=cycle_ts,
            controller_state=self._runtime_state.current_state.value,
            correlation_id=decision.correlation_id,
            observation=obs,
        )
        self._audit.log_decision(cycle_ts, decision)

        execution_payload = {
            "executed": False,
            "success": True,
            "command": [],
            "detail": "no action",
        }
        if decision.chosen_action != RecoveryAction.NO_ACTION:
            if decision.chosen_action == RecoveryAction.RESTART_SENTINEL:
                self._audit.log_event(
                    ts=cycle_ts,
                    event="sentinel_restart_scheduled",
                    detail={
                        "incident_key": decision.incident_key,
                        "reason": decision.reason,
                    },
                    correlation_id=decision.correlation_id,
                )
            result = self._executor.run_action(decision.chosen_action)
            execution_payload = {
                "executed": result.executed,
                "success": result.success,
                "command": result.command,
                "detail": result.detail,
            }
            if decision.chosen_action == RecoveryAction.RESTART_SENTINEL:
                if result.success:
                    self._audit.log_event(
                        ts=cycle_ts,
                        event="sentinel_restart_completed",
                        detail={"command": result.command, "detail": result.detail},
                        correlation_id=decision.correlation_id,
                    )
                    verification = self._verify_sentinel_restart_freshness()
                    execution_payload["verification"] = verification
                    self._audit.log_event(
                        ts=cycle_ts,
                        event=(
                            "sentinel_restart_verified"
                            if verification["verified"]
                            else "sentinel_restart_failed"
                        ),
                        detail=verification,
                        correlation_id=decision.correlation_id,
                    )
                else:
                    self._audit.log_event(
                        ts=cycle_ts,
                        event="sentinel_restart_failed",
                        detail={
                            "command": result.command,
                            "detail": result.detail,
                            "stage": "command_execution",
                        },
                        correlation_id=decision.correlation_id,
                    )
            self._state_machine.register_action(
                runtime=self._runtime_state,
                action=decision.chosen_action,
                correlation_id=decision.correlation_id,
                incident_key=decision.incident_key,
                host_boot_id=obs.host_boot_id,
            )

        self._audit.log_action(
            ts=cycle_ts,
            controller_state=self._runtime_state.current_state.value,
            correlation_id=decision.correlation_id,
            chosen_action=decision.chosen_action.value,
            reason=decision.reason,
            cooldown_context={
                "cooldown_active": decision.cooldown_active,
                "cooldown_seconds": self._config.guard.cooldown_seconds,
                "last_action_ts": self._runtime_state.last_action_ts,
                "maintenance_mode_active": decision.maintenance_mode_active,
            },
            lockout_context={
                "lockout_active": decision.lockout_active,
                "lockout_until_ts": self._runtime_state.lockout_until_ts,
                "max_actions_per_window": self._config.guard.max_actions_per_window,
                "lockout_window_seconds": self._config.guard.lockout_window_seconds,
                "lockout_latch_event": decision.lockout_latch_event,
            },
            incident_key=decision.incident_key,
            execution=execution_payload,
        )
        self._log_lifecycle_events(cycle_ts, decision.correlation_id, previous_state, decision)

        self._runtime_state.previous_host_boot_id = obs.host_boot_id
        self._runtime_state.previous_host_seq = obs.host_seq
        self._notifier.handle_cycle(decision, obs)
        current_state = self._runtime_state.to_dict()
        if not self._config.paths.controller_state_path.exists() or self._last_persisted_state != current_state:
            save_runtime_state(self._config.paths.controller_state_path, self._runtime_state)
            self._last_persisted_state = current_state

    def _emit_startup_events(self, ts: float) -> None:
        phase = self._phase_label()
        self._audit.log_event(
            ts=ts,
            event="controller_started",
            detail={
                "phase": phase,
                "maintenance_mode": self._config.mode.maintenance_mode,
            },
        )

        self._emit_phase_and_gate_events(ts, correlation_id=None)
        self._emit_maintenance_mode_event(ts, correlation_id=None)

    def _log_lifecycle_events(
        self,
        ts: float,
        correlation_id: str,
        previous_state: str,
        decision: Decision,
    ) -> None:
        current_state = decision.classified_state.value
        emitted_state = self._runtime_state.last_emitted_controller_state
        if emitted_state is None or emitted_state != current_state:
            self._audit.log_event(
                ts=ts,
                event="controller_state_changed",
                detail={
                    "from_state": emitted_state if emitted_state is not None else previous_state,
                    "to_state": current_state,
                    "reason": decision.reason,
                    "incident_key": decision.incident_key,
                },
                correlation_id=correlation_id,
            )
            self._runtime_state.last_emitted_controller_state = current_state

        if decision.lockout_latch_event is not None:
            self._audit.log_event(
                ts=ts,
                event=decision.lockout_latch_event,
                detail={"incident_key": decision.incident_key},
                correlation_id=correlation_id,
            )

        self._emit_phase_and_gate_events(ts, correlation_id=correlation_id)
        self._emit_maintenance_mode_event(ts, correlation_id=correlation_id)

    def _emit_phase_and_gate_events(self, ts: float, correlation_id: str | None) -> None:
        current_phase = self._phase_label()
        if self._runtime_state.last_phase_label != current_phase:
            self._audit.log_event(
                ts=ts,
                event="phase_changed",
                detail={
                    "from_phase": self._runtime_state.last_phase_label,
                    "to_phase": current_phase,
                },
                correlation_id=correlation_id,
            )
            if current_phase == "PHASE_B":
                self._audit.log_event(
                    ts=ts,
                    event="phase_b_enabled",
                    detail={"phase": current_phase},
                    correlation_id=correlation_id,
                )
            self._runtime_state.last_phase_label = current_phase

        gates = self._action_gate_snapshot()
        signature = self._action_gate_signature(gates)
        if self._runtime_state.last_action_gate_signature != signature:
            self._audit.log_event(
                ts=ts,
                event="action_gate_changed",
                detail={
                    "from_signature": self._runtime_state.last_action_gate_signature,
                    "to_signature": signature,
                    "gates": gates,
                },
                correlation_id=correlation_id,
            )
            self._runtime_state.last_action_gate_signature = signature

    def _emit_maintenance_mode_event(self, ts: float, correlation_id: str | None) -> None:
        enabled = self._config.mode.maintenance_mode
        if self._runtime_state.last_maintenance_mode is None:
            event = "maintenance_mode_enabled" if enabled else "maintenance_mode_disabled"
            self._audit.log_event(
                ts=ts,
                event=event,
                detail={"maintenance_mode": enabled},
                correlation_id=correlation_id,
            )
            self._runtime_state.last_maintenance_mode = enabled
            return

        if self._runtime_state.last_maintenance_mode != enabled:
            event = "maintenance_mode_enabled" if enabled else "maintenance_mode_disabled"
            self._audit.log_event(
                ts=ts,
                event=event,
                detail={"maintenance_mode": enabled},
                correlation_id=correlation_id,
            )
            self._runtime_state.last_maintenance_mode = enabled

    def _action_gate_snapshot(self) -> dict[str, bool]:
        return {
            "dry_run": self._config.actions.dry_run,
            "enable_restart_sentinel": self._config.actions.enable_restart_sentinel,
            "enable_remote_reboot": self._config.actions.enable_remote_reboot,
            "enable_gpio_reboot": self._config.actions.enable_gpio_reboot,
            "enable_power_button_pulse": self._config.actions.enable_power_button_pulse,
        }

    def _action_gate_signature(self, gates: dict[str, bool]) -> str:
        return "|".join(f"{key}={int(value)}" for key, value in sorted(gates.items()))

    def _phase_label(self) -> str:
        actions = self._config.actions
        if (
            actions.dry_run
            and not actions.enable_restart_sentinel
            and not actions.enable_remote_reboot
            and not actions.enable_gpio_reboot
            and not actions.enable_power_button_pulse
        ):
            return "PHASE_A"
        if (
            (not actions.dry_run)
            and actions.enable_restart_sentinel
            and (not actions.enable_remote_reboot)
            and (not actions.enable_gpio_reboot)
            and (not actions.enable_power_button_pulse)
        ):
            return "PHASE_B"
        if (
            (not actions.dry_run)
            and actions.enable_restart_sentinel
            and actions.enable_remote_reboot
            and (not actions.enable_gpio_reboot)
            and (not actions.enable_power_button_pulse)
        ):
            return "PHASE_C"
        if (
            (not actions.dry_run)
            and actions.enable_restart_sentinel
            and actions.enable_remote_reboot
            and actions.enable_gpio_reboot
            and actions.enable_power_button_pulse
        ):
            return "PHASE_D"
        return "CUSTOM"

    def _verify_sentinel_restart_freshness(self) -> dict[str, Any]:
        # Sentinel facts are mirrored from the remote host and may lag by a few
        # seconds after a restart command succeeds, so poll briefly before final verdict.
        max_wait_sec = 8.0
        poll_interval_sec = 1.0
        deadline = time.time() + max_wait_sec
        attempts = 0
        stats_age = None
        state_age = None
        stats_fresh = False
        state_fresh = False

        while True:
            attempts += 1
            now_ts = time.time()
            stats_age = file_age_seconds(self._config.paths.sentinel_stats_path, now_ts)
            state_age = file_age_seconds(self._config.paths.sentinel_state_path, now_ts)
            stats_fresh = (
                stats_age is not None and stats_age <= self._config.threshold.sentinel_stats_stale_sec
            )
            state_fresh = (
                state_age is not None and state_age <= self._config.threshold.sentinel_state_stale_sec
            )
            if stats_fresh and state_fresh:
                break
            if now_ts >= deadline:
                break
            time.sleep(poll_interval_sec)

        return {
            "verification_kind": "sentinel_freshness",
            "verified": bool(stats_fresh and state_fresh),
            "sentinel_stats_age_sec": stats_age,
            "sentinel_stats_fresh": stats_fresh,
            "sentinel_state_age_sec": state_age,
            "sentinel_state_fresh": state_fresh,
            "sentinel_stats_stale_sec": self._config.threshold.sentinel_stats_stale_sec,
            "sentinel_state_stale_sec": self._config.threshold.sentinel_state_stale_sec,
            "verification_wait_max_sec": max_wait_sec,
            "verification_attempts": attempts,
        }
