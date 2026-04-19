# Phase A Validation Checklist

This checklist is for observation-only validation before enabling any intervention actions.

## Preconditions

- Wiring is observation-only:
  - Pi 5 physical pin 11 (`BCM17`) -> Zero physical pin 11 (`BCM17`)
  - GND shared
  - no 5V rail connection between boards
  - no 3.3V rail connection between boards
  - no intervention GPIO lines connected
- Controller config is Phase A (`dry_run=true`, all `enable_* = false`)
- Services running:
  - `raspi-revive-gpio-heartbeat.service` (Pi 5)
  - `raspi-revive-gpio-observer.service` (Zero)
  - `raspi-revive-controller.service` (Zero)

## Stage 1: Observation Stability (24h)

Goal: confirm GPIO evidence is stable and does not trigger false stale/action behavior.

1. Start Phase A and keep it running for at least 24 hours.
2. Sample mirror freshness repeatedly:
```bash
watch -n 2 'cat /var/lib/raspi-revive-agent/gpio-heartbeat.json'
```
3. Review controller logs:
```bash
tail -n 200 /var/log/raspi-revive/observations.jsonl
tail -n 200 /var/log/raspi-revive/actions.jsonl
```

Pass criteria:

- `last_edge_wall_time` keeps advancing at expected cadence.
- `gpio_heartbeat_fresh` is mostly stable (`true` during healthy run).
- `actions.jsonl` has no unexpected hard action execution.

## Stage 2: Failure Injection

Goal: verify dirty real-world failures map to expected states without accidental intervention.

Run each case independently and restore to baseline before the next case.

### Case A: Stop Pi 5 emitter only

```bash
sudo systemctl stop raspi-revive-gpio-heartbeat.service
```

Expected:

- Zero observer mirror stops receiving real edges.
- Controller eventually marks GPIO stale.
- No hard action execution in Phase A.

### Case B: Stop Zero observer only

```bash
sudo systemctl stop raspi-revive-gpio-observer.service
```

Expected:

- Mirror stops updating even if Pi 5 emits.
- Controller reacts to stale mirror evidence only.
- No hard action execution in Phase A.

### Case C: Restart controller only

```bash
sudo systemctl restart raspi-revive-controller.service
```

Expected:

- Controller resumes from runtime state file without unstable oscillation.
- Incident dedupe remains effective.
- No unexpected immediate intervention.

### Case D: Break mirror path temporarily

Use one safe method, then restore:

```bash
sudo mv /var/lib/raspi-revive-agent/gpio-heartbeat.json /var/lib/raspi-revive-agent/gpio-heartbeat.json.bak
# ... observe behavior ...
sudo mv /var/lib/raspi-revive-agent/gpio-heartbeat.json.bak /var/lib/raspi-revive-agent/gpio-heartbeat.json
```

Expected:

- Missing/malformed mirror is treated as stale/unavailable evidence.
- Classifier behavior stays consistent with scenario expectations.
- No hard action execution in Phase A.

### Case E: Network failure while GPIO stays alive

Expected:

- `gpio_heartbeat_fresh = true` remains valid.
- Network-dependent evidence degrades (`ping/ssh` etc.).
- Hard actions remain suppressed in Phase A.

## Stage 3: One-time Threshold Tuning

Goal: tune only after observing real jitter and dropout patterns.

Tune in this order:

1. `GPIO_PULSE_HOLD_MS`
2. `GPIO_OBSERVER_INTERVAL_SEC`
3. `gpio_heartbeat_stale_sec` (controller threshold)

Guideline:

- Prefer conservative settings first:
  - pulse not too short
  - observer interval relatively fine
  - stale threshold with margin
- Make one tuning change at a time, then re-run Stage 1/2 spot checks.

## Promotion Gate (Phase A -> B)

Promote only when all conditions hold:

- 24h stability passed with no unexplained stale spikes.
- Failure injection cases A-E behave as expected.
- `actions.jsonl` shows no unintended hard action behavior.
- Operator can explain every stale event using logs and service state.
