from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import json

from .config import ControllerConfig, ControllerModeConfig
from .evaluator import classify
from .models import ControllerRuntimeState, Observation, RecoveryAction
from .state_machine import StateMachine


@dataclass(slots=True)
class ScenarioStep:
    step_id: str
    observation: Observation
    expected_state: str
    expected_action: RecoveryAction
    forbidden_actions: tuple[RecoveryAction, ...] = ()


@dataclass(slots=True)
class ScenarioDefinition:
    scenario_id: str
    injected_failure: str
    expected_evidence: str
    recovery_verification: str
    notes: str
    steps: list[ScenarioStep]
    maintenance_mode: bool | None = None
    threshold_overrides: dict[str, int | float] | None = None
    guard_overrides: dict[str, int | float] | None = None


@dataclass(slots=True)
class ScenarioResult:
    step_id: str
    actual_state: str
    actual_action: RecoveryAction
    reason: str
    incident_key: str


def _parse_observation(data: dict) -> Observation:
    return Observation(
        ts=float(data["ts"]),
        host_boot_id=data.get("host_boot_id"),
        host_seq=(None if data.get("host_seq") is None else int(data["host_seq"])),
        host_monotonic_sec=(
            None if data.get("host_monotonic_sec") is None else float(data["host_monotonic_sec"])
        ),
        host_wall_time=data.get("host_wall_time"),
        host_heartbeat_age_sec=(
            None
            if data.get("host_heartbeat_age_sec") is None
            else float(data["host_heartbeat_age_sec"])
        ),
        host_heartbeat_fresh=bool(data["host_heartbeat_fresh"]),
        host_heartbeat_progressing=bool(data.get("host_heartbeat_progressing", True)),
        gpio_heartbeat_age_sec=(
            None
            if data.get("gpio_heartbeat_age_sec") is None
            else float(data["gpio_heartbeat_age_sec"])
        ),
        gpio_heartbeat_fresh=bool(data["gpio_heartbeat_fresh"]),
        sentinel_stats_age_sec=(
            None
            if data.get("sentinel_stats_age_sec") is None
            else float(data["sentinel_stats_age_sec"])
        ),
        sentinel_stats_fresh=bool(data["sentinel_stats_fresh"]),
        sentinel_state_age_sec=(
            None
            if data.get("sentinel_state_age_sec") is None
            else float(data["sentinel_state_age_sec"])
        ),
        sentinel_state_fresh=bool(data["sentinel_state_fresh"]),
        ping_ok=bool(data["ping_ok"]),
        ssh_ok=bool(data["ssh_ok"]),
    )


def load_scenario_definition(path: str | Path) -> ScenarioDefinition:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)

    steps: list[ScenarioStep] = []
    for raw in data["steps"]:
        forbidden_raw = raw.get("forbidden_actions", [])
        forbidden = tuple(RecoveryAction(x) for x in forbidden_raw)
        steps.append(
            ScenarioStep(
                step_id=str(raw["step_id"]),
                observation=_parse_observation(raw["observation"]),
                expected_state=str(raw["expected_state"]),
                expected_action=RecoveryAction(raw["expected_action"]),
                forbidden_actions=forbidden,
            )
        )

    return ScenarioDefinition(
        scenario_id=str(data["scenario_id"]),
        injected_failure=str(data["injected_failure"]),
        expected_evidence=str(data["expected_evidence"]),
        recovery_verification=str(data.get("recovery_verification", "")),
        notes=str(data.get("notes", "")),
        steps=steps,
        maintenance_mode=(None if data.get("maintenance_mode") is None else bool(data["maintenance_mode"])),
        threshold_overrides=(
            None if data.get("threshold_overrides") is None else dict(data["threshold_overrides"])
        ),
        guard_overrides=(None if data.get("guard_overrides") is None else dict(data["guard_overrides"])),
    )


def load_scenario_definitions_from_dir(path: str | Path) -> list[ScenarioDefinition]:
    files = sorted(Path(path).glob("*.json"))
    return [load_scenario_definition(f) for f in files]


def _apply_scenario_mode(config: ControllerConfig, scenario: ScenarioDefinition) -> ControllerConfig:
    updated = replace(
        config,
        threshold=replace(config.threshold),
        guard=replace(config.guard),
        mode=replace(config.mode),
    )
    if scenario.maintenance_mode is not None:
        updated = replace(updated, mode=ControllerModeConfig(maintenance_mode=scenario.maintenance_mode))
    if scenario.threshold_overrides:
        threshold = updated.threshold
        for key, value in scenario.threshold_overrides.items():
            setattr(threshold, key, value)
    if scenario.guard_overrides:
        guard = updated.guard
        for key, value in scenario.guard_overrides.items():
            setattr(guard, key, value)
    return updated


def replay_scenario(config: ControllerConfig, steps: list[ScenarioStep]) -> list[ScenarioResult]:
    runtime = ControllerRuntimeState()
    machine = StateMachine(config)
    results: list[ScenarioResult] = []

    for step in steps:
        classification = classify(step.observation)
        decision = machine.decide(runtime, classification, current_boot_id=step.observation.host_boot_id)
        runtime.current_state = decision.classified_state

        if decision.chosen_action != RecoveryAction.NO_ACTION:
            machine.register_action(
                runtime=runtime,
                action=decision.chosen_action,
                correlation_id=decision.correlation_id,
                incident_key=decision.incident_key,
                host_boot_id=step.observation.host_boot_id,
            )

        results.append(
            ScenarioResult(
                step_id=step.step_id,
                actual_state=decision.classified_state.value,
                actual_action=decision.chosen_action,
                reason=decision.reason,
                incident_key=decision.incident_key,
            )
        )

    return results


def replay_definition(config: ControllerConfig, scenario: ScenarioDefinition) -> list[ScenarioResult]:
    scenario_config = _apply_scenario_mode(config, scenario)
    return replay_scenario(scenario_config, scenario.steps)


def assert_scenario_expectations(steps: list[ScenarioStep], results: list[ScenarioResult]) -> None:
    if len(steps) != len(results):
        raise AssertionError(f"steps/results length mismatch: {len(steps)} vs {len(results)}")

    for step, result in zip(steps, results):
        if result.actual_state != step.expected_state:
            raise AssertionError(
                f"{step.step_id}: expected state {step.expected_state}, got {result.actual_state}"
            )
        if result.actual_action != step.expected_action:
            raise AssertionError(
                f"{step.step_id}: expected action {step.expected_action.value}, "
                f"got {result.actual_action.value}"
            )
        if result.actual_action in step.forbidden_actions:
            forbidden = ",".join(x.value for x in step.forbidden_actions)
            raise AssertionError(
                f"{step.step_id}: forbidden action triggered {result.actual_action.value}; "
                f"forbidden={forbidden}"
            )
