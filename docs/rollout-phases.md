# Rollout Phases

This runbook defines staged production enablement for `raspi-revive`.

## Phase Config Files

Prepared configs are provided under:

- `targets/raspi-zero-controller/config/phases/controller.phase-a.toml`
- `targets/raspi-zero-controller/config/phases/controller.phase-b.toml`
- `targets/raspi-zero-controller/config/phases/controller.phase-c.toml`
- `targets/raspi-zero-controller/config/phases/controller.phase-d.toml`

## Safety Principle

Do not enable stronger interventions until lower-risk phases are stable with evidence from append-only logs.

## Common Commands

Deploy phase config:

```bash
sudo install -m 0644 \
  <deployment-root>/targets/raspi-zero-controller/config/phases/controller.phase-a.toml \
  /etc/raspi-revive/controller.toml
sudo systemctl restart raspi-revive-controller.service
```

Check service:

```bash
systemctl status raspi-revive-controller.service --no-pager
journalctl -u raspi-revive-controller.service -n 200 --no-pager
```

Review logs:

```bash
tail -n 200 /var/log/raspi-revive/observations.jsonl
tail -n 200 /var/log/raspi-revive/decisions.jsonl
tail -n 200 /var/log/raspi-revive/actions.jsonl
tail -n 200 /var/log/raspi-revive/events.jsonl
```

`events.jsonl` is transition/lifecycle only and intentionally sparse. Do not treat it as per-cycle heartbeat.

## Phase A (Observe Only)

Config intent:

- `dry_run=true`
- all action enables `false`

Goal:

- validate classification and audit quality only.
- validate physical GPIO heartbeat observation (Pi 5 emitter -> Pi Zero observer mirror) while intervention lines remain disabled/unconnected.

Exit criteria:

- no forbidden actions
- incident key grouping is stable
- lockout latch events are coherent
- expected scenarios map to expected states

Rollback trigger:

- inconsistent classification across repeated identical failures

## Phase B (Enable Restart Sentinel Only)

Config intent:

- `dry_run=false`
- `enable_restart_sentinel=true`
- remote/gpio/power actions disabled

Goal:

- verify Level 1 intervention behavior safely.

Exit criteria:

- sentinel-only faults recover by restart
- no remote reboot or gpio action in logs
- no `POWER_BUTTON_PULSE` action in logs
- cooldown and incident dedupe work after restart actions
- restart verification is recorded using sentinel freshness checks (`sentinel_restart_verified` or `sentinel_restart_failed`)

Rollback trigger:

- restart actions fired during non-sentinel incidents

### B1 / B2 Structure for Future Rollouts

Use Phase B as two explicit gates before enabling any hard action:

- B1: soft-action / observation validation
  - focus on sentinel-only intervention behavior and telemetry quality.
- B2: hard-action exclusion validation
  - keep `enable_remote_reboot=false`,
  - and verify that known false-positive patterns do not escalate to reboot.

Minimum B2 counterexample set:

- telemetry-only failure (`host heartbeat stale + sentinel stale` while `gpio fresh + ssh ok`)
- post-boot reconciliation window (no immediate hard action replay)
- sentinel freshness jitter/flap (stale/fresh oscillation without reboot escalation)

## Phase C (Enable Remote Reboot in Controlled Window)

Config intent:

- `dry_run=false`
- restart + remote reboot enabled
- gpio/power actions disabled

Goal:

- verify Level 2 behavior with operator monitoring.

Operational guard:

- run in an attended time window.

Exit criteria:

- host-degraded incidents escalate to remote reboot only when gates match
- post-action verification tracks reboot via `boot_id` change
- lockout/cooldown stop repeated reboot loops
- decide whether to promote `host_heartbeat_progressing` from note to enforced gate

Rollback trigger:

- false-positive remote reboot
- verification anomalies (`RECOVERY_IN_PROGRESS` stuck)

## Phase D (Enable GPIO Reboot Last)

Config intent:

- `dry_run=false`
- restart + remote reboot + gpio/power actions enabled

Goal:

- enable final out-of-band intervention only after prior phases are stable.

Exit criteria:

- freeze-suspected sustained incidents are required before gpio action
- no gpio actions during network-only or management-plane degraded states
- lockout behavior remains correct under repeated severe faults

Rollback trigger:

- gpio action fired without required freeze evidence

## Pre-Phase Validation

Before each phase promotion:

1. replay fixtures:

```bash
PYTHONPATH=src python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures
```

2. verify target scenario outcomes in `docs/validation-scenarios.md`
3. confirm maintenance mode procedure is known and tested
