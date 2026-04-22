# raspi-revive

`raspi-revive` is an out-of-band recovery layer for Raspberry Pi systems.

It exists to cover failure modes that in-band recovery cannot safely resolve:

- `raspi-sentinel` handles in-band recovery inside the managed host boundary.
- host freeze, management-plane loss, or sentinel self-failure can exceed that boundary.
- `raspi-revive` provides an outer control loop with evidence-gated and phased interventions.

Role split:

- `raspi-5-agent`: facts only (host heartbeat, GPIO heartbeat emission, sentinel facts export)
- `raspi-zero-controller`: judgment + intervention (state machine, staged actions, cooldown/lockout, audit logs)

## What This Repository Demonstrates

- strict Fact/Decision/Intervention separation in a solo-built hardware-adjacent control loop
- evidence-gated staged rollout from observation-only to out-of-band recovery
- operational validation artifacts from Phase A through Phase C on real Raspberry Pi hardware

## Current Scope and Gaps

- Public baseline profile remains staged from `Phase A` (observation-first) upward.
- Field operation has progressed through `Phase C` on real hardware after Phase A/B evidence.
- After a `REMOTE_REBOOT` validation run on `2026-04-23`, a false-trigger reboot loop was observed at `06:55` and `06:58 JST`.
- Current field containment keeps `enable_remote_reboot=false`; `REMOTE_REBOOT` is re-enabled only when explicit safety criteria are met.
- The intended Phase C policy is: keep `RESTART_SENTINEL` as primary intervention and allow `REMOTE_REBOOT` only with independent host-degradation evidence.
- Stronger interventions remain staged and must be enabled only after evidence from lower-risk phases.

## Design Quality Declaration

- Correctness of `Fact / Decision / Intervention` boundary is treated as a first-class quality target.
- No hard action is allowed without stronger evidence gates.
- Observation-first rollout is required before intervention enablement.

## Fact / Decision / Intervention Boundary

- Fact: produced by agent scripts and probes.
- Decision: performed only by controller evaluator + state machine.
- Intervention: executed only by controller action executor.

## Action Conditions (MVP)

| Classified state | Required evidence (summary) | Candidate action | Phase gate requirement |
| --- | --- | --- | --- |
| `HEALTHY` | no stale/degraded/freeze gate triggered | `NO_ACTION` | always allowed |
| `MANAGEMENT_PLANE_DEGRADED` | gpio fresh + host heartbeat fresh + ping ok + ssh fail | `NO_ACTION` | always allowed |
| `NETWORK_ONLY_ISSUE` | ping/ssh issue + out-of-band gpio fresh | `NO_ACTION` | always allowed |
| `SENTINEL_ONLY_FAILURE` | gpio fresh + host heartbeat fresh + ssh ok + sentinel stale | `RESTART_SENTINEL` | enabled in Phase B+ |
| `TELEMETRY_PIPELINE_FAILURE` | (host heartbeat stale + sentinel stale + gpio fresh + ssh ok) OR (host heartbeat fresh-but-not-progressing + sentinel stale + gpio fresh + ssh ok) | `NO_ACTION` | always allowed |
| `HOST_DEGRADED` | gpio stale + host stale + ssh ok, and telemetry was previously healthy in same boot | `REMOTE_REBOOT` | disabled in Phase B (Phase C+) |
| `FREEZE_SUSPECTED` | gpio stale + host stale + ssh fail + sustained cycles | `GPIO_REBOOT` | disabled through Phase C (Phase D+) |

## Safety Gates

- `actions.enabled_phases = ["A","B","C", ...]` provides explicit phase gating in config.
- `cooldown_seconds` suppresses immediate repeated actions.
- `max_actions_per_window` within `lockout_window_seconds` enters `LOCKOUT`.
- Reboot actions require post-action verification by `boot_id` change.
- After reboot verification, the controller enters post-boot reconciliation and suppresses hard actions until telemetry recovers or the reconciliation window expires.
- Phase B sentinel restart verification is freshness-based (`sentinel stats/state`) and is logged separately from reboot verification.
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
- `events.jsonl` (lifecycle and transition events only; intentionally sparse)
- controller state JSON
- optional notify files: `notify-events.jsonl`, `notify-stats.json`, `notify-queue.json`

Steady-state evidence remains in `observations.jsonl` / `decisions.jsonl` / `actions.jsonl`.
A quiet `events.jsonl` during stable Phase A soak (for example, 18 hours without new entries) can be normal.

## Optional Notify Queue (No Recovery Action Required)

- You can enable a notification-only policy while keeping restart/reboot actions disabled.
- When `HOST_DEGRADED` or `FREEZE_SUSPECTED` stays continuous for 5+ minutes, controller enqueues a notify event.
- The queued event tries:
  - append JSONL to the Pi 5 over SSH (`notify.remote_jsonl_path`)
  - Discord webhook post
- You can define extensible providers with `[[notify.providers]]` (for example `ssh_append`, `discord_webhook`) while keeping backward-compatible legacy fields.
- Delivery retry policy:
  - every 60 seconds while failures are under 5 minutes
  - exponential backoff after 5 minutes of continuous failure
- Use `RASPI_REVIVE_DISCORD_WEBHOOK_URL` via `notify.discord_webhook_url_env` instead of hard-coding secrets.

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
- Event policy: [`docs/event-policy.md`](docs/event-policy.md)
- Replay guide: [`docs/scenario-replay.md`](docs/scenario-replay.md)
- Staged rollout: [`docs/rollout-phases.md`](docs/rollout-phases.md)
- Phase A field checklist: [`docs/phase-a-validation-checklist.md`](docs/phase-a-validation-checklist.md)
- Phase B field checklist: [`docs/phase-b-validation-checklist.md`](docs/phase-b-validation-checklist.md)
- Phase B operations log: [`docs/phase-b-operations-log.md`](docs/phase-b-operations-log.md)
- Phase C operations log: [`docs/phase-c-operations-log.md`](docs/phase-c-operations-log.md)
- Engineering rationale: [`docs/engineering-decisions.md`](docs/engineering-decisions.md)
- Notify queue design: [`docs/notify-queue.md`](docs/notify-queue.md)
- Public ops note template: [`docs/ops-notes.md`](docs/ops-notes.md)
- Private runbook template (fill outside public repo): [`docs/private-runbook.template.md`](docs/private-runbook.template.md)

Japanese docs are available as `*.ja.md` (for example: `README.ja.md`, `docs/architecture.ja.md`).

## Assumptions (MVP)

- Controller can read agent-exported fact files via configured paths.
- GPIO electrical safety layer is handled outside this repository.
- `pinctrl` (default GPIO backend) or libgpiod tools, plus `ping` and `ssh`, are available on deployment targets.
- Runtime JSONL logs are rotated by default using `[logs]` (`max_log_size_mb=10`, `rotation_count=3`).

## TODO (Future)

- Add Level 4 strongest fallback action with stricter gates.
- Add dedicated notifier integration on `LOCKOUT`.
- Add hardware-specific GPIO driver backends beyond command execution.
