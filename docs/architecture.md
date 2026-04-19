# raspi-revive Architecture

## Scope

`raspi-revive` is an out-of-band recovery system that complements in-band `raspi-sentinel`.

- `raspi-5-agent`: publishes facts only.
- `raspi-zero-controller`: owns judgment and intervention.

Runtime artifacts are intentionally outside the repository. This repository contains only source, schemas, examples, configs, and tests.

## Responsibility Split

### raspi-5-agent (facts producer)

- Writes host heartbeat JSON (`boot_id`, `seq`, `monotonic_sec`, `wall_time`, etc.).
- Emits GPIO heartbeat pulse/toggle.
- Exports runtime facts (`host-heartbeat`, `sentinel stats/state/events`) for collection.
- Does not include recovery decision logic.

### raspi-zero-controller (decision + action)

- Collects observations from multiple probes.
- Normalizes observations into explicit evidence gates.
- Runs explicit state machine.
- Selects staged recovery action.
- Executes actions via adapters (dry-run supported).
- Persists controller state (`cooldown`, `lockout`, counters, pending verification).
- Writes append-only audit JSONL.

## Pipeline Separation

1. Observation collection
2. Observation normalization
3. Evidence gate evaluation
4. State classification
5. Action selection (policy + safety gates)
6. Action execution
7. Post-action verification (for reboot, expect `boot_id` change)
8. Audit logging

These stages are implemented as separate modules to avoid hidden logic.

## Design Guarantees

- Evidence is explicitly split into two groups:
  - `out_of_band_evidence`: GPIO heartbeat freshness.
  - `network_path_evidence`: host heartbeat file, sentinel facts, ping, SSH.
- Network-only outage cannot trigger external reboot.
- Stronger actions require stronger evidence and continuity over multiple cycles.
- Repeated actions are bounded by cooldown and lockout.
- Every decision/action is traceable by `correlation_id` in JSONL logs.
- Maintenance mode can disable all interventions while observation/decision/audit continues.

## Assumptions (MVP)

- Zero can read agent-exported files from configured paths.
- GPIO pulse monitoring is represented by an adapter abstraction (`HeartbeatInput`) and default file-backed implementation.
- SSH/ping probe commands are available in the controller runtime.
