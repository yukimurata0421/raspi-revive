from __future__ import annotations

import time

from .audit import AuditLogger
from .collector import ObservationCollector
from .config import ControllerConfig
from .evaluator import classify
from .executor import ActionExecutor
from .models import ControllerRuntimeState, RecoveryAction
from .state_machine import StateMachine
from .state_store import load_runtime_state, save_runtime_state


class ReviveController:
    def __init__(self, config: ControllerConfig) -> None:
        self._config = config
        self._collector = ObservationCollector(config)
        self._state_machine = StateMachine(config)
        self._executor = ActionExecutor(config.actions)
        self._audit = AuditLogger(config.paths)
        self._runtime_state = load_runtime_state(config.paths.controller_state_path)

    @property
    def runtime_state(self) -> ControllerRuntimeState:
        return self._runtime_state

    def run_cycle(self) -> None:
        obs = self._collector.collect(self._runtime_state.previous_host_seq)
        classification = classify(obs)
        decision = self._state_machine.decide(
            self._runtime_state,
            classification,
            current_boot_id=obs.host_boot_id,
        )

        self._runtime_state.current_state = decision.classified_state

        self._audit.log_observation(
            controller_state=self._runtime_state.current_state.value,
            correlation_id=decision.correlation_id,
            observation=obs,
        )
        self._audit.log_decision(decision)

        execution_payload = {
            "executed": False,
            "success": True,
            "command": [],
            "detail": "no action",
        }
        if decision.chosen_action != RecoveryAction.NO_ACTION:
            result = self._executor.run_action(decision.chosen_action)
            execution_payload = {
                "executed": result.executed,
                "success": result.success,
                "command": result.command,
                "detail": result.detail,
            }
            self._state_machine.register_action(
                runtime=self._runtime_state,
                action=decision.chosen_action,
                correlation_id=decision.correlation_id,
                incident_key=decision.incident_key,
                host_boot_id=obs.host_boot_id,
            )

        self._audit.log_action(
            ts=time.time(),
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

        self._runtime_state.previous_host_boot_id = obs.host_boot_id
        self._runtime_state.previous_host_seq = obs.host_seq
        save_runtime_state(self._config.paths.controller_state_path, self._runtime_state)
