# raspi-revive

`raspi-revive` is an out-of-band recovery layer for Raspberry Pi systems.

It exists to cover failure modes that in-band recovery cannot safely resolve:

- `raspi-sentinel` handles in-band recovery inside the managed host boundary.
- host freeze, management-plane loss, or sentinel self-failure can exceed that boundary.
- `raspi-revive` provides an outer control loop with evidence-gated and phased interventions.

Role split:

- `raspi-5-agent`: facts only (host heartbeat, GPIO heartbeat emission, sentinel facts export)
- `raspi-zero-controller`: judgment + intervention (state machine, staged actions, cooldown/lockout, audit logs)

## Current Scope and Gaps

- Current rollout position is `Phase A`.
- Operation is observation-first.
- Intervention lines are not enabled/connected in this phase.
- Stronger interventions are staged and must be enabled only after evidence from lower-risk phases.

## Design Quality Declaration

- Correctness of `Fact / Decision / Intervention` boundary is treated as a first-class quality target.
- No hard action is allowed without stronger evidence gates.
- Observation-first rollout is required before intervention enablement.

## Fact / Decision / Intervention Boundary

- Fact: produced by agent scripts and probes.
- Decision: performed only by controller evaluator + state machine.
- Intervention: executed only by controller action executor.

## Action Conditions (MVP)

| Classified state | Required evidence (summary) | Action |
| --- | --- | --- |
| `HEALTHY` | no stale/degraded/freeze gate triggered | `NO_ACTION` |
| `MANAGEMENT_PLANE_DEGRADED` | gpio fresh + host heartbeat fresh + ping ok + ssh fail | `NO_ACTION` |
| `NETWORK_ONLY_ISSUE` | ping/ssh issue + out-of-band gpio fresh | `NO_ACTION` |
| `SENTINEL_ONLY_FAILURE` | gpio fresh + host heartbeat fresh + ssh ok + sentinel stale | `RESTART_SENTINEL` |
| `HOST_DEGRADED` | (gpio stale + host stale + ssh ok) or (host stale + sentinel stale + ssh ok) | `REMOTE_REBOOT` |
| `FREEZE_SUSPECTED` | gpio stale + host stale + ssh fail + sustained cycles | `GPIO_REBOOT` |

## Safety Gates

- `cooldown_seconds` suppresses immediate repeated actions.
- `max_actions_per_window` within `lockout_window_seconds` enters `LOCKOUT`.
- Reboot actions require post-action verification by `boot_id` change.
- `maintenance_mode=true` disables interventions while audit keeps running.
- repeated intervention for the same incident key is suppressed.
- lockout lifecycle emits latch events (`entered/still_active/cleared`) into decision/action logs.

## GPIO Heartbeat Observation Policy (Phase A)

- Scope in this phase is observation only.
- Current wiring: Pi 5 physical pin 11 (`BCM17`) -> Pi Zero physical pin 11 (`BCM17`), plus shared GND.
- Do not connect 5V rails or 3.3V rails between boards.
- Keep controller action gates closed (`phase-a` config).
- Pi 5 emitter runs `targets/raspi-5-agent/scripts/emit_gpio_heartbeat.py`.
- Pi Zero observer runs `targets/raspi-zero-controller/scripts/observe_gpio_heartbeat.py` and writes the mirror JSON consumed by controller `FileHeartbeatInput`.

## Runtime Output (not committed)

- `observations.jsonl`
- `decisions.jsonl`
- `actions.jsonl`
- controller state JSON

## Scenario Replay Harness

- Harness module: `src/raspi_revive/scenario_harness.py`
- Fixture-driven scenario tests: `tests/scenario/test_fixture_replay.py`
- Scenario fixtures: `tests/scenario/fixtures/*.json`

The harness replays synthetic observations into evaluator/state machine and asserts expected state/action plus forbidden actions before running live failure injections.

### CLI

```bash
python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures
```

You can filter specific scenarios by repeating `--scenario-id`.

## Documentation

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- State machine: [`docs/state-machine.md`](docs/state-machine.md)
- Validation scenarios: [`docs/validation-scenarios.md`](docs/validation-scenarios.md)
- Replay guide: [`docs/scenario-replay.md`](docs/scenario-replay.md)
- Staged rollout: [`docs/rollout-phases.md`](docs/rollout-phases.md)
- Phase A field checklist: [`docs/phase-a-validation-checklist.md`](docs/phase-a-validation-checklist.md)
- Engineering rationale: [`docs/engineering-decisions.md`](docs/engineering-decisions.md)
- Public ops note template: [`docs/ops-notes.md`](docs/ops-notes.md)
- Private runbook template (fill outside public repo): [`docs/private-runbook.template.md`](docs/private-runbook.template.md)

Japanese docs are available as `*.ja.md` (for example: `README.ja.md`, `docs/architecture.ja.md`).

## Assumptions (MVP)

- Controller can read agent-exported fact files via configured paths.
- GPIO electrical safety layer is handled outside this repository.
- `pinctrl` (default GPIO backend) or libgpiod tools, plus `ping` and `ssh`, are available on deployment targets.

## TODO (Future)

- Add Level 4 strongest fallback action with stricter gates.
- Add dedicated notifier integration on `LOCKOUT`.
- Add hardware-specific GPIO driver backends beyond command execution.
