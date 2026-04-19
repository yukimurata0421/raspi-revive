# State Machine

## States

- `HEALTHY`
- `MANAGEMENT_PLANE_DEGRADED`
- `SENTINEL_ONLY_FAILURE`
- `HOST_DEGRADED`
- `FREEZE_SUSPECTED`
- `NETWORK_ONLY_ISSUE`
- `RECOVERY_IN_PROGRESS`
- `COOLDOWN`
- `LOCKOUT`

## Evidence Gates (Derived)

- Out-of-band evidence:
  - `gpio_fresh`
- Network-dependent evidence:
  - `host_heartbeat_fresh`
  - `host_heartbeat_progressing`
  - `sentinel_stats_fresh`
  - `sentinel_state_fresh`
  - `ping_ok`
  - `ssh_ok`

## Classification Rules (MVP)

1. `MANAGEMENT_PLANE_DEGRADED`
   - `gpio_fresh` and `host_heartbeat_fresh` and `ping_ok` and `not ssh_ok`
2. `NETWORK_ONLY_ISSUE`
   - `(not ping_ok or not ssh_ok)` and `gpio_fresh`
3. `SENTINEL_ONLY_FAILURE`
   - `gpio_fresh` and `host_heartbeat_fresh` and `ssh_ok`
   - and (`sentinel_stats_fresh == false` or `sentinel_state_fresh == false`)
4. `HOST_DEGRADED`
   - formula:
     - `ssh_ok AND ( (not gpio_fresh AND not host_heartbeat_fresh) OR (not host_heartbeat_fresh AND sentinel stale) )`
5. `FREEZE_SUSPECTED`
   - `not gpio_fresh` and `not host_heartbeat_fresh` and `not ssh_ok`
   - required consecutive cycles must be satisfied before GPIO reboot
6. Otherwise `HEALTHY`

## Action Mapping

- `SENTINEL_ONLY_FAILURE` -> `RESTART_SENTINEL` (Level 1)
- `MANAGEMENT_PLANE_DEGRADED` -> `NO_ACTION` (observe/notify only)
- `HOST_DEGRADED` -> `REMOTE_REBOOT` (Level 2)
- `FREEZE_SUSPECTED` -> `GPIO_REBOOT` (Level 3, only after required consecutive cycles)
- `NETWORK_ONLY_ISSUE` -> `NO_ACTION` (observe/notify only)
- `HEALTHY` -> `NO_ACTION`

## Safety Gates

- `cooldown_seconds`: suppress new actions immediately after action.
- `max_actions_per_window` within `lockout_window_seconds`.
- lockout entered when action budget exceeded.
- lockout suppresses all automatic interventions.
- `maintenance_mode=true` suppresses all interventions without suppressing observation/decision logs.
- incident dedupe suppresses repeated actions for unchanged incident key.
- lockout latch emits `lockout_entered`, `lockout_still_active`, and `lockout_cleared`.

## Post-action Verification

For reboot actions (`REMOTE_REBOOT`, `GPIO_REBOOT`):

- Track pre-action `boot_id`.
- During verification window, require observed `boot_id` change.
- Until verification completes, controller state is `RECOVERY_IN_PROGRESS`.
