# Phase C Operations Log

This document keeps an operational record for Phase C runtime verification and intervention behavior.

## Background and Intent

- Background: after the `REMOTE_REBOOT` validation on `2026-04-23`, a false-trigger reboot loop was observed at `06:55` and `06:58 JST`.
- Intent: this log is not only a success report; it is the single timeline for incident facts, root-cause evidence, containment, and hardening decisions.
- Operational stance: keep `REMOTE_REBOOT` under evidence-gated control, and change enablement only after explicit operator decision.

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

## Record: 2026-04-23 (JST) Phase C Remote Reboot Execution Test

### Scope

- Evidence files:
  - `<controller-home>/phase-c-remote-reboot-test-20260423T062804+0900.log`
  - `<controller-home>/phase-c-remote-reboot-test-20260423T062804+0900.summary`
  - `/var/log/raspi-revive/actions.jsonl`
  - `/var/log/raspi-revive/events.jsonl`
- Test runtime window: `2026-04-23 06:28:04` to `06:29:09 JST`

### Execution Evidence

- Baseline gate values at start:
  - `dry_run=false`
  - `enable_restart_sentinel=true`
  - `enable_remote_reboot=true`
  - `enable_gpio_reboot=false`
  - `enable_power_button_pulse=false`
- Test run injected a controlled `HOST_DEGRADED` condition.
- `actions.jsonl` recorded one intervention:
  - `chosen_action=REMOTE_REBOOT`
  - `execution.executed=true`
  - `execution.success=true`
  - `detail=exit=0`
- Poll log observed:
  - `remote_reboot_count=1` at `06:28:42 JST`
  - host `boot_id` changed from `5d86a957-291d-4f79-b7de-dc99648615ae` to `7618b75a-7ee4-4c56-9f0a-30a49e0f7323` at `06:29:08 JST`
- State transition sequence was logged as expected:
  - `HOST_DEGRADED -> RECOVERY_IN_PROGRESS -> COOLDOWN -> HEALTHY`

### Assessment

- The Phase C control loop was verified end-to-end for this test path:
  - evidence classification
  - gated intervention execution
  - post-action reboot verification by `boot_id` change
  - recovery back to steady state
- `summary` recorded `success=1` and `remote_reboot_count=1`.

## Record: 2026-04-23 (JST) False Trigger RCA and Logic Hardening

### Scope

- Evidence files:
  - `pi5:/var/log/raspi-revive/actions.jsonl`
  - `pi5:/var/log/raspi-revive/events.jsonl`
  - `pi5-guard:/etc/raspi-revive/controller.toml`
- Incident window: `2026-04-23 06:55` and `06:58 JST`

### Observed Facts

- `REMOTE_REBOOT` was executed at `06:55` and `06:58 JST`.
- Host was still reachable by SSH during the incident.
- Root condition was telemetry stale (`host heartbeat` and `sentinel`) being classified as `HOST_DEGRADED`.
- Temporary containment was applied immediately:
  - `enable_remote_reboot=false`
  - controller service restarted on `pi5-guard`

### Hardening Applied

- State split added:
  - `TELEMETRY_PIPELINE_FAILURE`
  - `POST_BOOT_RECONCILIATION`
  - `RECOVERY_PARTIAL`
- `HOST_DEGRADED` now requires target-plane independent evidence:
  - `gpio stale + host heartbeat stale + ssh ok`
- `REMOTE_REBOOT` now requires telemetry baseline in the same boot:
  - at least one prior cycle with `host heartbeat fresh + sentinel fresh + ssh ok`
- After reboot verification (`boot_id` change), hard actions are suppressed during `POST_BOOT_RECONCILIATION` until telemetry recovers or reconciliation times out.

### Validation

- Local regression run after hardening:
  - `pytest -q` -> `42 passed`
  - `python3 -m ruff check src tests` -> `All checks passed`

## Record: 2026-04-23 (JST) Phase C Re-enable Under Hardened Logic

### Scope

- Controller host: `pi5-guard`
- Config: `/etc/raspi-revive/controller.toml`
- Service: `raspi-revive-controller.service`

### Execution Evidence

- Operator approved re-enabling `REMOTE_REBOOT` after hardening was deployed.
- Config change applied:
  - `enable_remote_reboot = true`
  - `post_boot_reconciliation_wait_seconds = 180.0` remained configured
- Service was restarted and stayed `active`.
- `events.jsonl` recorded:
  - `phase_changed` from `PHASE_B` to `PHASE_C`
  - `action_gate_changed` with `enable_remote_reboot=1`

### Assessment

- The rollback containment (`REMOTE_REBOOT=0`) was lifted intentionally, not implicitly.
- Re-enable was performed only after:
  - false-trigger RCA was documented,
  - classification/action-gate hardening was applied,
  - local regression checks passed.

## Record: 2026-04-23 (JST) Sentinel Fact Freshness Flapping Analysis and Threshold Tuning

### Scope

- Controller host: `pi5-guard`
- Config: `/etc/raspi-revive/controller.toml`
- Runtime logs:
  - `/var/log/raspi-revive/observations.jsonl`
  - `/var/log/raspi-revive/decisions.jsonl`
  - `/var/log/raspi-revive/actions.jsonl`
  - `/var/log/raspi-revive/events.jsonl`
- Sentinel schedule inputs:
  - `/etc/systemd/system/raspi-sentinel.timer`
  - `/etc/raspi-sentinel/config.toml`

### Investigation Findings

- `raspi-revive` stale thresholds were:
  - `sentinel_stats_stale_sec = 30.0`
  - `sentinel_state_stale_sec = 30.0`
- `raspi-sentinel` run cadence was configured at `OnUnitActiveSec=30s` with jitter (`RandomizedDelaySec=5s`, `AccuracySec=15s`), and actual start intervals were mostly around `35-45s`.
- In the `2026-04-23 09:00+ JST` window before tuning:
  - `SENTINEL_ONLY_FAILURE` repeatedly appeared with reason `sentinel facts stale while host/gpio/ssh indicate OS alive`.
  - `REMOTE_REBOOT` / `RESTART_SENTINEL` were not fired (`NO_ACTION` only), so this was a data-freshness flapping issue, not an intervention storm.
- Cross-host mtime checks showed mirror lag was not the primary factor; the dominant cause was threshold-vs-cadence mismatch.

### Change Applied

- Updated `/etc/raspi-revive/controller.toml` on `pi5-guard`:
  - `sentinel_stats_stale_sec = 60.0`
  - `sentinel_state_stale_sec = 60.0`
- Restarted `raspi-revive-controller.service`.
- Post-change status at `2026-04-23 18:02 JST`:
  - service `active (running)`
  - immediate sample window remained `HEALTHY`.

### Short Verification After Change

- Observation watch window: `2026-04-23 18:02:35` to `18:04:25 JST` (about 110s)
- Results:
  - `observations=10`
  - `state=HEALTHY` for all entries
  - `sentinel_stats_fresh=false` / `sentinel_state_fresh=false`: `0`
- This does not replace longer soak validation, but confirms the immediate flapping trigger condition was removed in this window.

## Record: 2026-04-24 (JST) GPIO Freshness Instability Investigation (Backend A/B + Wiring Verification)

### Context

- After switching observer back to `GPIO_OBSERVER_PIN=17`, the short-window `gpio_fresh_ratio` looked unstable (around `~50%` in some windows).
- Goal was to determine whether this was primarily:
  - backend-level sampling behavior (`pinctrl` vs `gpiod`), or
  - lower-layer signal path mismatch.

### Investigation Approach

1. Excluded process conflicts in `projects` workspace (no non-`raspi-revive` GPIO17 actor).
2. Tried `pinctrl -> gpiod` observer switch under equivalent windows.
3. Found `gpiod` path startup failures and traced them to:
   - hard dependency on `gpiofind` (not installed on Zero),
   - non-v2 `gpioget` invocation shape.
4. Implemented compatibility fixes in `observe_gpio_heartbeat.py`:
   - fallback to `GPIO_OBSERVER_GPIOD_CHIP` when `gpiofind` is unavailable,
   - `gpioget -c <chip> --bias ... --numeric <offset>` for libgpiod v2.
5. Added regression tests in `tests/test_gpio_scripts.py` (`7 passed`).
6. Performed forced `HIGH/LOW` pin mapping checks:
   - at one point, Pi 5 `GPIO17` toggles were observed on Zero `GPIO27`, not `GPIO17`,
   - after rewiring and config alignment, Zero `GPIO17` correctly followed Pi 5 `GPIO17`.
7. Corrected residual config mismatch (`GPIO_OBSERVER_PIN` temporarily left as `27`) back to `17`.

### Findings

- Pi 5 output-hold hypothesis was rejected: forced `HIGH` hold on Pi 5 `GPIO17` remained stable in repeated reads.
- `gpiod` compatibility gap was real and reproducible; fixed in code.
- The observed freshness instability was mainly a combined issue:
  - temporary pin-mapping/config mismatch windows,
  - plus backend compatibility defects before the fix.

### Result After Alignment

- In latest short stable window:
  - `60s samples=5 true=5 false=0 ratio=100%`
  - `gpio_heartbeat_age_sec` around `~0.8s` (max `~1.7s`)

### Prevention Actions

1. Add pre-run pin mapping check (`force HIGH/LOW` on Pi 5 `GPIO17` and confirm Zero `GPIO17` follows).
2. Require backend switch health checks:
   - service active,
   - `--once` returns `observer_status=ok`,
   - edge timestamp progresses.
3. Treat post-change transition windows separately from stable-window metrics.

### Related Threshold Tightening

- With GPIO observation stabilized, `gpio_heartbeat_stale_sec` is operated under a tightened policy:
  - initial value: `120.0` (stability-first during early observation)
  - current value: `10.0` (still with margin vs measured `age ~0.8s`, `max ~1.7s`)
- Runtime backup checkpoints on the controller host show:
  - `120.0` at `2026-04-20 05:27 JST`
  - `10.0` at `2026-04-22 11:01 JST`
  - indicating the tightening was completed around `2026-04-22`.
- Repository phase configs already use `10.0` consistently across all phases.
- Rolling 24h soak snapshot (as of `2026-04-24 09:05 JST`):
  - window: `2026-04-23 09:05 JST` to `2026-04-24 09:05 JST`
  - `samples=7907`, `gpio_fresh=true=3709`, `false=4198`, `ratio=46.91%`
  - `age_mean=16.913s`, `p50=10.847s`, `p95=53.583s`, `max=238.386s`
  - note: this 24h window includes pre-fix and transition samples; completion judgment should be based on stable-window evidence in addition to rolling-window metrics.

## Phase A-C Coverage Check

This log plus linked docs now explicitly cover:

- Phase A: observation-only GPIO bring-up and stabilization.
- Phase B: sentinel-only intervention enablement and runtime validation.
- Phase C:
  - runtime verification,
  - controlled remote reboot execution test,
  - false-trigger incident and RCA,
  - logic hardening,
  - controlled re-enable decision and evidence.
