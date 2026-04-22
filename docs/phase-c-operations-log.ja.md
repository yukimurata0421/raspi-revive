# Phase C Operations Log

この文書は、Phase C の移行可否確認と実地運用検証の記録を残すための運用ログです。

## 2026-04-22 (JST) フェーズC実稼働確認

### 対象

- Controller host: `pi5-guard`
- Deployment root: `/opt/raspi-revive`
- Service: `raspi-revive-controller.service`
- 確認時刻: `2026-04-22 19:05 JST`

### 実測エビデンス

- `systemctl status raspi-revive-controller.service`:
  - `2026-04-22 11:03:17 JST` から `active (running)`（確認時点で約8時間）。
- `/etc/raspi-revive/controller.toml` の action gate:
  - `dry_run=false`
  - `enable_restart_sentinel=true`
  - `enable_remote_reboot=true`
  - `enable_gpio_reboot=false`
  - `enable_power_button_pulse=false`
- 進行中の append-only ログは `/var/log/raspi-revive/` 側で確認:
  - `observations.jsonl`
  - `decisions.jsonl`
  - `actions.jsonl`
  - `events.jsonl`
- `actions.jsonl` の直近8時間集計:
  - `entries=2642`
  - `NO_ACTION=2642`
  - `RESTART_SENTINEL=0`
  - `REMOTE_REBOOT=0`

### 判断

- フェーズC設定は意図どおり適用済み。
- 観測した8時間窓では、危険側を含む予期しない介入は発生していない。
- `events.jsonl` では `SENTINEL_ONLY_FAILURE -> HEALTHY` の短周期遷移が継続しているが、action gate と閾値によりエスカレーションは抑制されている。
