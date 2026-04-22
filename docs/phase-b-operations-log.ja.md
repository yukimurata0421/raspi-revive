# Phase B Operations Log

この文書は、Phase B 適用と実地検証の記録を残すための運用ログです。

## 2026-04-20 (JST) 適用記録

### 対象

- Controller host: `raspi-zero-controller`（運用ホスト）
- Deployment root: `/opt/raspi-revive`
- Service: `raspi-revive-controller.service`
- Active phase after apply: `Phase B`

### 実施内容

1. 最新コードを controller 側へ同期
2. `controller.toml` を Phase B 構成で適用
3. controller service を再起動
4. append-only ログを確認
5. heartbeat / network probe の実測
6. sentinel-only fault injection を実施
7. `RESTART_SENTINEL` 実行と verification 記録を確認

### 重要な修正

- `ssh_ok=0` の主因が host key verification 失敗であることを確認
- controller 側 `ssh_options` と action command に known_hosts を明示
- sentinel restart verification で mirror 遅延を吸収するため、短時間ポーリング（最大 8 秒）を追加

### 検証結果

- Phase B gate: 維持
  - `dry_run=false`
  - `enable_restart_sentinel=true`
  - `enable_remote_reboot=false`
  - `enable_gpio_reboot=false`
  - `enable_power_button_pulse=false`
- `events.jsonl` に lifecycle / transition 記録を確認
  - `controller_started`
  - `phase_b_enabled`
  - `action_gate_changed`
  - `sentinel_restart_scheduled`
  - `sentinel_restart_completed`
  - `sentinel_restart_verified`
- sentinel-only 条件で `RESTART_SENTINEL` が発火し、cooldown に遷移することを確認
- non-target action（remote/gpio/power）が発火していないことを確認

### 補足

- `events.jsonl` は heartbeat ストリームではないため、長時間エントリが少ない状態は正常になりうる
- steady-state の連続証跡は `observations.jsonl` / `decisions.jsonl` / `actions.jsonl` を正本として確認する

## 2026-04-21 (JST) フェーズB総括

### 稼働サマリ

- `raspi-revive-controller.service` は約 9 時間連続で `active (running)` を維持
- 直近 6 時間では `NO_ACTION` が大半で、危険側アクション（remote/gpio/power）は未実行
- `SENTINEL_ONLY_FAILURE` は断続的に観測されたが、短周期で `HEALTHY` に復帰

### `inactive (dead)` 事象への対策

- 過去に観測された `raspi-revive-controller.service: inactive (dead)` は、監視系を `raspi-sentinel` の lite バージョン構成へ寄せることで再発を抑制
- 具体的には、軽量監視の常時稼働と復旧経路の単純化により、controller 側の停止見逃しを減らす運用に整理

### 判断

- フェーズBとしての主要目的（sentinel restart 経路の安全な有効化と危険側アクション非発火）は達成
- 一方で sentinel freshness 揺れは継続するため、フェーズC移行後も `events.jsonl` と `actions.jsonl` の継続監視を前提とする

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
