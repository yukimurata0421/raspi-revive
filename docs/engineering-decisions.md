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
