# Failure Model

## Evidence Groups

- Out-of-band evidence: GPIO heartbeat freshness.
- Network-dependent evidence: host heartbeat file, sentinel facts, ping, SSH.

## A. Sentinel-only issue

Signals:

- GPIO heartbeat fresh
- host heartbeat fresh
- SSH reachable
- sentinel stats/state stale

Interpretation:

- OS alive, sentinel path degraded.

Action:

- Restart `raspi-sentinel` only.
- External reboot prohibited.

## B. Host degraded

Signals:

- GPIO heartbeat stale or host heartbeat stale
- SSH reachable

Interpretation:

- Host responds but control/data plane progress is degraded.

Action:

- Remote OS reboot (`ssh sudo reboot`) first.

## C. Freeze suspected

Signals:

- GPIO heartbeat stale
- host heartbeat stale
- SSH fail
- sustained over configured consecutive cycles

Interpretation:

- Deep freeze or severe hang likely.

Action:

- Candidate for GPIO-based external reboot.

## D. Network-only issue

Signals:

- ping/SSH fail (or unstable)
- GPIO heartbeat fresh
- host heartbeat fresh

Interpretation:

- Host likely alive; network path problematic.

Action:

- No reboot; observe/notify only.

## E. Management-plane degraded

Signals:

- GPIO heartbeat fresh
- host heartbeat fresh
- ping ok
- SSH fail

Interpretation:

- Host is likely alive, but management plane access is degraded.

Action:

- No reboot; observe/notify only.

## F. Recovery guard states

- `RECOVERY_IN_PROGRESS`: action fired, waiting verification.
- `COOLDOWN`: no further action until cooldown expires.
- `LOCKOUT`: repeated actions exceeded budget, operator attention required.
