from __future__ import annotations

from dataclasses import asdict

from .config import LogConfig, PathConfig
from . import io
from .models import Decision, Observation


class AuditLogger:
    def __init__(self, paths: PathConfig, logs: LogConfig) -> None:
        self._paths = paths
        self._logs = logs

    def _append_jsonl(self, path, payload: dict) -> None:
        rotate_writer = getattr(io, "append_jsonl_with_rotation", None)
        if callable(rotate_writer):
            rotate_writer(
                path,
                payload,
                max_bytes=self._logs.max_log_size_bytes,
                rotation_count=self._logs.rotation_count,
            )
            return
        io.append_jsonl(path, payload)

    def log_observation(
        self,
        ts: float,
        controller_state: str,
        correlation_id: str,
        observation: Observation,
    ) -> None:
        payload = {
            "ts": ts,
            "controller_state": controller_state,
            "correlation_id": correlation_id,
            "observation": asdict(observation),
        }
        self._append_jsonl(self._paths.observations_log_path, payload)

    def log_decision(self, ts: float, decision: Decision) -> None:
        payload = {
            "ts": ts,
            "controller_state": decision.classified_state.value,
            "correlation_id": decision.correlation_id,
            "incident_key": decision.incident_key,
            "failure_reason_code": decision.failure_reason_code,
            "chosen_action": decision.chosen_action.value,
            "reason": decision.reason,
            "evidence_summary": asdict(decision.evidence),
            "cooldown_active": decision.cooldown_active,
            "lockout_active": decision.lockout_active,
            "maintenance_mode_active": decision.maintenance_mode_active,
            "lockout_latch_event": decision.lockout_latch_event,
        }
        self._append_jsonl(self._paths.decisions_log_path, payload)

    def log_action(
        self,
        ts: float,
        controller_state: str,
        correlation_id: str,
        chosen_action: str,
        reason: str,
        cooldown_context: dict,
        lockout_context: dict,
        incident_key: str,
        execution: dict,
    ) -> None:
        payload = {
            "ts": ts,
            "controller_state": controller_state,
            "correlation_id": correlation_id,
            "incident_key": incident_key,
            "chosen_action": chosen_action,
            "reason": reason,
            "cooldown_context": cooldown_context,
            "lockout_context": lockout_context,
            "execution": execution,
        }
        self._append_jsonl(self._paths.actions_log_path, payload)

    def log_event(
        self,
        ts: float,
        event: str,
        detail: dict,
        correlation_id: str | None = None,
    ) -> None:
        payload = {
            "ts": ts,
            "event": event,
            "detail": detail,
        }
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        self._append_jsonl(self._paths.events_log_path, payload)
