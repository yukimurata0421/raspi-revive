# Phase B Validation Checklist

## 1. Preconditions

- Confirm current policy is still observation-first at repository level.
- Ensure deployment uses `controller.phase-b.toml`.
- Ensure remote/gpio/power actions remain disabled.

## 2. Config Switch

```bash
sudo install -m 0644 \
  <deployment-root>/targets/raspi-zero-controller/config/phases/controller.phase-b.toml \
  /etc/raspi-revive/controller.toml
sudo systemctl restart raspi-revive-controller.service
```

## 3. Service Health

```bash
systemctl status raspi-revive-controller.service --no-pager
journalctl -u raspi-revive-controller.service -n 200 --no-pager
```

## 4. Log Confirmation

```bash
tail -n 200 /var/log/raspi-revive/observations.jsonl
tail -n 200 /var/log/raspi-revive/decisions.jsonl
tail -n 200 /var/log/raspi-revive/actions.jsonl
tail -n 200 /var/log/raspi-revive/events.jsonl
```

Expect `events.jsonl` to show lifecycle/transition milestones only.

## 5. Sentinel-Only Fault Injection

Inject sentinel-only failure while keeping gpio + host heartbeat + ping + ssh healthy.

Expected:

- state: `SENTINEL_ONLY_FAILURE`
- action: `RESTART_SENTINEL`
- forbidden: `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE`

## 6. Verification Expectation

Check:

- `actions.jsonl` includes restart command execution detail
- `actions.jsonl` includes sentinel freshness verification payload
- `events.jsonl` includes `sentinel_restart_scheduled/completed/verified` (or `failed`)

## 7. Rollback Triggers

Rollback to Phase A when:

- restart fires during non-sentinel incidents
- remote/gpio/power action appears in Phase B logs
- sentinel restart verification repeatedly fails

## 8. Rollback Procedure

```bash
sudo install -m 0644 \
  <deployment-root>/targets/raspi-zero-controller/config/phases/controller.phase-a.toml \
  /etc/raspi-revive/controller.toml
sudo systemctl restart raspi-revive-controller.service
```
