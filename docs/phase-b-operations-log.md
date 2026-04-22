# Phase B Operations Log

This document keeps an operational record for Phase B promotion and live validation.

## Record: 2026-04-20 (JST)

### Scope

- Controller host: `raspi-zero-controller` (operational host)
- Deployment root: `/opt/raspi-revive`
- Service: `raspi-revive-controller.service`
- Active phase after apply: `Phase B`

### Actions Performed

1. Synced the latest code to the controller host.
2. Applied Phase B controller configuration.
3. Restarted the controller service.
4. Checked append-only logs.
5. Measured heartbeat and network probes.
6. Executed sentinel-only fault injection.
7. Verified `RESTART_SENTINEL` execution and verification records.

### Important Fixes

- Confirmed root cause of `ssh_ok=0` was host key verification failure.
- Added explicit known_hosts options for probe SSH and action SSH commands.
- Added short polling (up to 8 seconds) for sentinel restart verification to absorb mirror lag.

### Validation Outcome

- Phase B gate preserved:
  - `dry_run=false`
  - `enable_restart_sentinel=true`
  - `enable_remote_reboot=false`
  - `enable_gpio_reboot=false`
  - `enable_power_button_pulse=false`
- Confirmed lifecycle/transition events in `events.jsonl`:
  - `controller_started`
  - `phase_b_enabled`
  - `action_gate_changed`
  - `sentinel_restart_scheduled`
  - `sentinel_restart_completed`
  - `sentinel_restart_verified`
- Confirmed `RESTART_SENTINEL` fires for sentinel-only evidence and transitions into cooldown.
- Confirmed no non-target actions (remote/gpio/power) were fired.

### Note

- `events.jsonl` is not a heartbeat stream, so long quiet periods can be normal.
- Use `observations.jsonl` / `decisions.jsonl` / `actions.jsonl` as the source of truth for steady-state continuity.

## Summary: 2026-04-21 (JST)

### Runtime Summary

- `raspi-revive-controller.service` stayed `active (running)` for about 9 continuous hours.
- Over the last 6 hours, `NO_ACTION` dominated and no high-impact actions (remote/gpio/power) were executed.
- `SENTINEL_ONLY_FAILURE` still appeared intermittently, but it returned to `HEALTHY` in short cycles.

### Mitigation for `inactive (dead)`

- The previously observed `raspi-revive-controller.service: inactive (dead)` condition was mitigated by shifting the monitoring side to the `raspi-sentinel` lite variant.
- In operational terms, this aligned the system to a lighter always-on supervision path and a simpler recovery flow, reducing missed controller-stop situations.

### Assessment

- Phase B objectives were met: safe sentinel-restart enablement and no unsafe action firing.
- Sentinel freshness jitter remains, so continued monitoring of `events.jsonl` and `actions.jsonl` is still required after Phase C promotion.

## Note

- Phase C records were moved to [`docs/phase-c-operations-log.md`](phase-c-operations-log.md) to keep this document focused on Phase B evidence only.
