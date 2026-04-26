# Event Logging Policy

This policy defines roles for append-only runtime logs.

## Log Roles

- `observations.jsonl`: every control-loop cycle facts (`Fact` layer)
- `decisions.jsonl`: every control-loop cycle classification and selected action (`Decision` layer)
- `actions.jsonl`: every control-loop cycle action execution or suppression detail (`Intervention` layer)
- `events.jsonl`: notable lifecycle and transition events only
- `intervention-evidence/intervention_evidence_*.json`: evidence bundle captured immediately before intervention execution
- `incident-summary.json`: latest incident and decision read model for operators
- `controller-stats.json`: runtime counters and state/action aggregates for operators

`events.jsonl` is intentionally sparse and is not a heartbeat stream.

## Evidence Bundle Before Action

When `chosen_action != NO_ACTION`, the controller writes one evidence snapshot before command execution.
The bundle captures incident key, candidate action, phase gate, cooldown/lockout eligibility, suppressed actions, and the observation evidence set that justified the intervention.

## What Goes Into `events.jsonl`

`events.jsonl` is used for explicit milestones and lifecycle transitions:

- `controller_started`
- `phase_changed`
- `phase_b_enabled`
- `action_gate_changed`
- `controller_state_changed`
- `maintenance_mode_enabled` / `maintenance_mode_disabled`
- `lockout_entered` / `lockout_still_active` / `lockout_cleared`
- `sentinel_restart_scheduled`
- `sentinel_restart_completed`
- `sentinel_restart_verified`
- `sentinel_restart_failed`

## What Must Not Go Into `events.jsonl`

- periodic HEALTHY heartbeat events
- per-cycle observation snapshots already present in `observations.jsonl`
- per-cycle action suppression details already present in `actions.jsonl`

## How To Read A Quiet Phase A Window

A long quiet period in `events.jsonl` (for example, 18 hours without new entries) can be normal during stable Phase A soak.
Use `observations.jsonl` and `decisions.jsonl` as the source of truth for continuous loop evidence.

## Phase B Verification Note

Phase B sentinel restart verification is tracked separately from reboot verification:

- reboot actions verify via `boot_id` change (`RECOVERY_IN_PROGRESS` flow)
- sentinel restart verifies via sentinel freshness (`stats/state` freshness check) and is recorded in both `actions.jsonl` and `events.jsonl`
