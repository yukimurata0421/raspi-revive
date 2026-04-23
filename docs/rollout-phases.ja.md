# Rollout Phases

この runbook は `raspi-revive` の本番段階投入手順を定義します。

## Phase 設定ファイル

以下を用意済みです。

- `targets/raspi-zero-controller/config/phases/controller.phase-a.toml`
- `targets/raspi-zero-controller/config/phases/controller.phase-b.toml`
- `targets/raspi-zero-controller/config/phases/controller.phase-c.toml`
- `targets/raspi-zero-controller/config/phases/controller.phase-d.toml`

## 安全原則

低リスク段階のログ根拠が揃う前に、より強い介入を有効化しない。

## 共通コマンド

phase 設定を適用:

```bash
sudo install -m 0644 \
  <deployment-root>/targets/raspi-zero-controller/config/phases/controller.phase-a.toml \
  /etc/raspi-revive/controller.toml
sudo systemctl restart raspi-revive-controller.service
```

サービス確認:

```bash
systemctl status raspi-revive-controller.service --no-pager
journalctl -u raspi-revive-controller.service -n 200 --no-pager
```

ログ確認:

```bash
tail -n 200 /var/log/raspi-revive/observations.jsonl
tail -n 200 /var/log/raspi-revive/decisions.jsonl
tail -n 200 /var/log/raspi-revive/actions.jsonl
tail -n 200 /var/log/raspi-revive/events.jsonl
```

`events.jsonl` は transition/lifecycle 専用であり、毎 cycle heartbeat としては扱わない。

## Phase A（観測のみ）

設定意図:

- `dry_run=true`
- すべての action enable を `false`

目的:

- 判定品質と監査ログ品質の確認のみ
- 介入線を無効/未接続のまま、実GPIO heartbeat 観測（Pi 5 emitter -> Pi Zero observer mirror）を確認

昇格条件:

- forbidden action が 0
- incident key の束ね方が安定
- lockout latch イベントが整合
- 想定故障が想定 state に入る

ロールバック条件:

- 同一故障で分類が不安定

## Phase B（RESTART_SENTINEL のみ実行）

設定意図:

- `dry_run=false`
- `enable_restart_sentinel=true`
- remote/gpio/power は disabled

目的:

- Level 1 介入のみを安全に検証

昇格条件:

- sentinel-only 故障が restart で回復
- ログに remote/gpio action が出ない
- ログに `POWER_BUTTON_PULSE` action が出ない
- restart 後の cooldown/incident dedupe が効く
- restart verification が sentinel freshness として記録される（`sentinel_restart_verified` または `sentinel_restart_failed`）

ロールバック条件:

- sentinel 以外の事象で restart が走る

### 今後の B1 / B2 分割運用

hard action を解禁する前に、Phase B を2つのゲートとして明示的に運用する。

- B1: soft-action / observation validation
  - sentinel-only 介入挙動と観測品質を確認する
- B2: hard-action exclusion validation
  - `enable_remote_reboot=false` のまま、
  - 既知の false positive パターンが reboot へ昇格しないことを検証する

B2 の最小固定シナリオ:

- telemetry-only failure（`host heartbeat stale + sentinel stale` かつ `gpio fresh + ssh ok`）
- post-boot reconciliation window（起動直後の hard action 再発火を抑止）
- sentinel freshness jitter/flap（stale/fresh 揺れで reboot へ昇格しない）

## Phase C（REMOTE_REBOOT を監視時間帯で有効化）

設定意図:

- `dry_run=false`
- restart + remote reboot を有効化
- gpio/power は disabled

目的:

- Level 2 をオペレータ監視下で検証

運用ガード:

- 立ち会い可能な時間帯だけ実施

昇格条件:

- host-degraded の gate 成立時のみ remote reboot
- reboot 後 verification が `boot_id` 変化で完了
- cooldown/lockout で reboot loop を抑止
- `host_heartbeat_progressing` を注意書きから gate に昇格させるか判断する

ロールバック条件:

- false positive remote reboot
- verification 異常（`RECOVERY_IN_PROGRESS` が詰まる）

## Phase D（最後に GPIO_REBOOT）

設定意図:

- `dry_run=false`
- restart + remote reboot + gpio/power を有効化

目的:

- 先行 phase の安定後に最終 out-of-band 介入を有効化

昇格条件:

- freeze sustained 条件が揃った場合のみ gpio action
- network-only / management-plane degraded で gpio action が出ない
- 重故障反復でも lockout が健全に働く

ロールバック条件:

- 必要証拠なしで gpio action が発火

## 各 Phase 昇格前チェック

1. fixture replay:

```bash
PYTHONPATH=src python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures
```

2. `docs/validation-scenarios.md` の期待結果を再確認
3. maintenance mode の手順を事前確認し、テスト済みにする
