# Engineering Decisions

## 2026-04-19: Phase A GPIO Observation Bring-up (Pi 5 -> Zero)

### Context

- Goal was to enable real GPIO heartbeat observation as out-of-band evidence.
- Scope was explicitly observation-only:
  - no GPIO reboot action enablement
  - no power-button pulse wiring/enablement
  - no state-machine hard-action expansion
- Physical wiring at this stage:
  - Pi 5 physical pin 11 (`BCM17`) -> Zero physical pin 11 (`BCM17`)
  - shared GND
  - no 5V rail connection
  - no 3.3V rail connection

### Decisions

1. Keep controller GPIO input file-based and decoupled from direct GPIO access.
   - Introduced Zero-side GPIO observer service that writes mirror JSON.
   - Controller continues reading `paths.gpio_heartbeat_path` via `FileHeartbeatInput`.
2. Use `pinctrl` as default GPIO backend.
   - Avoids hard-coding `gpiochip0`.
   - Keep `gpiod` fallback backend with dynamic line resolution (`gpiofind GPIO<BCM>`).
3. Prioritize observation reliability over aggressive stale thresholds.
   - Initial stale threshold was too tight for real jitter/dropouts.
   - Runtime tune performed to `gpio_heartbeat_stale_sec = 120.0` for Phase A.

### Implemented Changes

- Pi 5 emitter:
  - `targets/raspi-5-agent/scripts/emit_gpio_heartbeat.py`
  - Added backend selection, env defaults, pulse-hold control.
  - Added richer mirror fields (`source`, backend, emit status, error).
- Zero observer:
  - `targets/raspi-zero-controller/scripts/observe_gpio_heartbeat.py` (new)
  - Input pull configuration, periodic read, edge/freshness mirror JSON.
- Systemd/config:
  - Added `targets/raspi-zero-controller/systemd/raspi-revive-gpio-observer.service`.
  - Updated Pi 5 heartbeat service env usage and pulse settings.
  - Added observer env template.
  - Corrected controller service runtime assumptions for Zero deployment:
    - `User=root` (instead of a non-existing runtime user)
    - `/usr/bin/python3` (instead of environment-specific venv path)
- Tests/docs:
  - Added unit tests for mirror input handling and GPIO scripts dry-run behavior.
  - Updated README/wiring/runtime/rollout docs and added Phase A validation checklist.

### Deployment Notes (Sanitized)

- Controller probe target should use placeholders in public docs/config:
  - `ssh_target = "<agent-user>@<agent-host>"`
  - `ping_target = "<agent-host-or-ip>"`
- SSH options should stay abstract in public docs/config:
  - identity: `<controller-user-home>/.ssh/id_ed25519`
  - known_hosts: `<controller-user-home>/.ssh/known_hosts`
  - strict host key check enabled.
- Facts transport path should be represented as role-based placeholders:
  - agent export root: `<agent-export-root>`
  - controller local mirror root: `<local-facts-mirror-root>/remote/`
  - controller reads `host-heartbeat.json`, `sentinel/stats.json`, `sentinel/state.json` from that local mirror.
- Deployment root should be documented as placeholder:
  - `<deployment-root>`

### Post Bring-up Stabilization

- Service-user mismatch (`status=217/USER`) was resolved by aligning service units with actual runtime users.
- Controller reached stable observation loops and persisted logs/state outputs.
- Facts synchronization was moved to a continuous mirror model for deterministic controller reads.
- GPIO observation was tuned for Phase A reliability:
  - `gpio_heartbeat_stale_sec = 120.0`
  - `GPIO_PULSE_HOLD_MS = 1000`
- Result after stabilization:
  - controller observation converged to `HEALTHY` with
    `gpio/host/sentinel/ssh/ping = true` on healthy periods.
  - Phase A action policy still held: `NO_ACTION` only.

### Current Operational Posture

- Phase A is active for observation/stability learning.
- Keep intervention lines disconnected and action gates closed.
- Tighten stale thresholds gradually only after evidence.

## 2026-04-21: Phase A-C staged enablement and monitoring responsibility split

### Context

- After live operation in Phase A/B, Phase C was promoted only after confirming continuous controller runtime and safe gate behavior.
- In parallel, recurrence prevention was required for the previously observed `raspi-revive-controller.service: inactive (dead)` condition.

### Decisions

1. Keep strict staged enablement.
   - Phase A: observation only (no intervention)
   - Phase B: open only `enable_restart_sentinel=true`
   - Phase C: additionally open `enable_remote_reboot=true`
   - Keep `enable_gpio_reboot` and `enable_power_button_pulse` closed
2. Mitigate `inactive (dead)` by clarifying monitoring responsibility, not by adding controller-side complexity.
   - Shift supervision to the `raspi-sentinel` lite variant, favoring lightweight always-on monitoring and a simpler recovery path.
   - Keep the controller focused on evidence-based state judgment and staged action gates.

### Outcome

- In Phase B, sentinel-restart effectiveness was validated without opening unsafe actions.
- At Phase C promotion time, no immediate unsafe action firing was observed.
- For `inactive (dead)`, operational recurrence suppression is now established through the `raspi-sentinel` lite-side responsibility split.

## 2026-04-23: Phase C false-trigger incident response and reboot policy hardening

### Context

- During Phase C operation, a remote-reboot loop was observed at `06:55` and `06:58 JST` on `2026-04-23`.
- Incident evidence showed:
  - `REMOTE_REBOOT` executions were recorded in `actions.jsonl`.
  - SSH reachability was still present at incident time.
  - stale telemetry (`host heartbeat` + `sentinel`) could be classified as `HOST_DEGRADED` under the prior rule.
- This conflicted with the architecture intent: strong interventions must be tied to strong, causally relevant evidence.

### Decisions

1. Separate telemetry pipeline failure from host degradation.
   - Added `TELEMETRY_PIPELINE_FAILURE` and removed telemetry-only stale paths from `HOST_DEGRADED`.
   - Rationale: telemetry/exporter faults must not directly trigger host reboot.
2. Require reboot causality proof before `REMOTE_REBOOT`.
   - `HOST_DEGRADED` remote reboot now requires:
     - independent target-plane evidence (`gpio stale + host heartbeat stale + ssh ok`),
     - and same-boot telemetry baseline previously healthy.
   - Rationale: avoid acting on missing telemetry alone.
3. Extend post-reboot suppression into reconciliation.
   - Added `POST_BOOT_RECONCILIATION` and `RECOVERY_PARTIAL`.
   - Added `post_boot_reconciliation_wait_seconds`.
   - Rationale: avoid replaying strong action before telemetry convergence after boot change.
4. Keep enablement as an operator-controlled gate.
   - Immediate containment used `enable_remote_reboot=false`.
   - Re-enable was done only after hardening deployment and regression verification.

### Evidence and Verification

- RCA and runtime evidence are logged in:
  - `docs/phase-c-operations-log.md`
  - incident entries for `2026-04-23 06:55/06:58 JST`
- Regression checks after hardening:
  - `pytest -q` passed
  - `ruff check` passed
- Runtime re-enable evidence:
  - `phase_changed: PHASE_B -> PHASE_C`
  - `action_gate_changed` with `enable_remote_reboot=1`

## 2026-04-23: Promote negative validation as a first-class phase gate

### Context

- The incident was not caused by skipping Phase B work.
- The gap was that Phase B had a strong focus on "can intervention work when intended?" and no explicit, independent gate for "does intervention stay suppressed when it must not fire?"
- In practice, telemetry-only stale paths surfaced in Phase C as a previously unnamed failure mode.

### Decision

1. Treat strong-action validation as two-directional by design.
   - Positive validation:
     - if true `HOST_DEGRADED`, can `REMOTE_REBOOT` execute under control.
   - Negative validation:
     - for telemetry-only failure, post-boot transient, or freshness jitter, `REMOTE_REBOOT` must stay blocked.
2. Split future Phase B into two explicit subphases.
   - B1: soft-action and observation validation.
   - B2: hard-action exclusion validation (remote reboot still disabled).
3. Add fixed B2 counterexample scenarios before any hard-action enablement.
   - telemetry-only failure
   - post-boot reconciliation window
   - sentinel freshness jitter/flap

### Rationale

- This converts a vague "be more careful" lesson into a repeatable design contract.
- It prevents hard-action rollout from depending on "absence of incident by chance."
- It reduces the chance that unknown failure modes are discovered only after Phase C enablement.

## 2026-04-24: Locking GPIO observer compatibility and pin-mapping verification

### Context

- During rollback to `GPIO_OBSERVER_PIN=17`, `gpio_fresh` became unstable and required explicit separation of backend behavior vs signal-path mismatch.
- Investigation showed a combined issue:
  - `gpiod` compatibility gap in Zero runtime (`gpiofind` dependency and libgpiod v2 CLI mismatch),
  - temporary pin/config mismatch windows.

### Decisions

1. Treat `gpiod` backend as runtime-compatibility bound, not just code-path complete.
   - Support fallback resolution when `gpiofind` is missing.
   - Use libgpiod v2-safe `gpioget -c <chip> --numeric <offset>` invocation shape.
2. Make pin mapping verification an explicit pre-run operational check.
   - Force `HIGH/LOW` on Pi 5 `GPIO17` and verify which Zero pin follows.
3. Separate transition windows from steady-state windows in freshness evaluation.
   - Avoid using immediate post-change windows for stable-quality comparison.

### Evidence

- Detailed evidence is recorded in `docs/phase-c-operations-log.md` under the `2026-04-24` entry.
- Key outcomes:
  - Pi 5 output-hold failure hypothesis was rejected.
  - `gpiod` compatibility defects were reproducible and then removed by implementation change.
  - After wiring/config realignment, short-window `gpio_fresh` returned to `100%`.

## Phase A-C decision completeness

The engineering record now explicitly includes:

1. Phase A: GPIO observation-only bring-up, wiring constraints, runtime stabilization.
2. Phase B: sentinel-only intervention boundary and safe promotion evidence.
3. Phase C:
   - initial promotion and runtime verification,
   - remote reboot execution validation,
   - false-trigger incident response,
   - policy hardening and controlled re-enable criteria.
