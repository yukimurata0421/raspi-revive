# State Machine

## 状態

- `HEALTHY`
- `MANAGEMENT_PLANE_DEGRADED`
- `SENTINEL_ONLY_FAILURE`
- `HOST_DEGRADED`
- `FREEZE_SUSPECTED`
- `NETWORK_ONLY_ISSUE`
- `RECOVERY_IN_PROGRESS`
- `COOLDOWN`
- `LOCKOUT`

## Evidence Gate（導出）

- Out-of-band:
  - `gpio_fresh`
- Network-dependent:
  - `host_heartbeat_fresh`
  - `host_heartbeat_progressing`
  - `sentinel_stats_fresh`
  - `sentinel_state_fresh`
  - `ping_ok`
  - `ssh_ok`

## 分類ルール（MVP）

1. `MANAGEMENT_PLANE_DEGRADED`
   - `gpio_fresh` and `host_heartbeat_fresh` and `ping_ok` and `not ssh_ok`
2. `NETWORK_ONLY_ISSUE`
   - `(not ping_ok or not ssh_ok)` and `gpio_fresh`
3. `SENTINEL_ONLY_FAILURE`
   - `gpio_fresh` and `host_heartbeat_fresh` and `ssh_ok`
   - かつ `sentinel_stats_fresh == false` または `sentinel_state_fresh == false`
4. `HOST_DEGRADED`
   - `ssh_ok`
   - かつ次のどちらか:
     - `not gpio_fresh` and `not host_heartbeat_fresh`
     - `not host_heartbeat_fresh` and sentinel stale
5. `FREEZE_SUSPECTED`
   - `not gpio_fresh` and `not host_heartbeat_fresh` and `not ssh_ok`
   - GPIO reboot 前に required consecutive cycles を満たす
6. それ以外は `HEALTHY`

## Action 対応

- `SENTINEL_ONLY_FAILURE` -> `RESTART_SENTINEL`（Level 1）
- `MANAGEMENT_PLANE_DEGRADED` -> `NO_ACTION`（観測/通知のみ）
- `HOST_DEGRADED` -> `REMOTE_REBOOT`（Level 2）
- `FREEZE_SUSPECTED` -> `GPIO_REBOOT`（Level 3, 連続条件成立時）
- `NETWORK_ONLY_ISSUE` -> `NO_ACTION`（観測/通知のみ）
- `HEALTHY` -> `NO_ACTION`

## Safety Gate

- `cooldown_seconds`: action 直後の再実行を抑止
- `max_actions_per_window` + `lockout_window_seconds`
- 予算超過で lockout
- lockout 中は自動介入を停止
- `maintenance_mode=true` で介入を全面停止（観測/判定ログは継続）
- incident dedupe で同一 incident key の再介入を抑止
- lockout latch イベント: `lockout_entered`, `lockout_still_active`, `lockout_cleared`

## Post-action Verification

reboot action（`REMOTE_REBOOT`, `GPIO_REBOOT`）では:

- action 前の `boot_id` を保持
- verification window 内に `boot_id` 変化を要求
- 完了まで状態は `RECOVERY_IN_PROGRESS`
