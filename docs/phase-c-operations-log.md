# Phase C Operations Log

This document keeps an operational record for Phase C promotion readiness and runtime verification.

## Record: 2026-04-22 (JST) Phase C Runtime Check

### Scope

- Controller host: `pi5-guard`
- Deployment root: `/opt/raspi-revive`
- Service: `raspi-revive-controller.service`
- Check timestamp: `2026-04-22 19:05 JST`

### Runtime Evidence

- `systemctl status raspi-revive-controller.service` showed:
  - `active (running)` since `2026-04-22 11:03:17 JST` (about 8 hours at check time).
- `/etc/raspi-revive/controller.toml` action gates:
  - `dry_run=false`
  - `enable_restart_sentinel=true`
  - `enable_remote_reboot=true`
  - `enable_gpio_reboot=false`
  - `enable_power_button_pulse=false`
- Active append-only logs were under `/var/log/raspi-revive/`:
  - `observations.jsonl`
  - `decisions.jsonl`
  - `actions.jsonl`
  - `events.jsonl`
- `actions.jsonl` 8-hour window count:
  - `entries=2642`
  - `NO_ACTION=2642`
  - `RESTART_SENTINEL=0`
  - `REMOTE_REBOOT=0`

### Assessment

- Phase C configuration is applied as intended.
- No unsafe or unexpected intervention was fired in the observed 8-hour window.
- `SENTINEL_ONLY_FAILURE -> HEALTHY` short-cycle transitions remain visible in `events.jsonl`, but action gates and thresholds prevented escalation.
