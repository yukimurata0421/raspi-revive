# Phase A 検証チェックリスト

このチェックリストは、介入 action を有効化する前の観測専用検証向けです。

## 事前条件

- 配線は観測専用:
  - Pi 5 physical pin 11（`BCM17`）-> Zero physical pin 11（`BCM17`）
  - GND 共通
  - ボード間で 5V を接続しない
  - ボード間で 3.3V を接続しない
  - 介入用 GPIO 線は未接続
- controller 設定は Phase A（`dry_run=true`、`enable_* = false`）
- 以下のサービスが稼働:
  - `raspi-revive-gpio-heartbeat.service`（Pi 5）
  - `raspi-revive-gpio-observer.service`（Zero）
  - `raspi-revive-controller.service`（Zero）

## Stage 1: 観測安定性（24時間）

目的: GPIO 証拠が安定し、偽 stale / 偽 action を起こさないことを確認する。

1. Phase A を開始し、最低 24 時間連続で運用する。
2. mirror の更新状況を定期確認:
```bash
watch -n 2 'cat /var/lib/raspi-revive-agent/gpio-heartbeat.json'
```
3. controller ログを確認:
```bash
tail -n 200 /var/log/raspi-revive/observations.jsonl
tail -n 200 /var/log/raspi-revive/actions.jsonl
```

合格条件:

- `last_edge_wall_time` が期待 cadence で継続更新される。
- `gpio_heartbeat_fresh` が健全時に概ね安定して `true` になる。
- `actions.jsonl` に想定外の hard action 実行がない。

## Stage 2: 障害注入

目的: 実機の汚い失敗を想定状態にマップし、誤介入しないことを確認する。

各ケースは個別に実施し、毎回ベースラインへ復帰してから次へ進む。

### Case A: Pi 5 emitter だけ停止

```bash
sudo systemctl stop raspi-revive-gpio-heartbeat.service
```

期待:

- Zero observer は実 edge を受け取れなくなる。
- controller は時間経過で GPIO stale 判定へ進む。
- Phase A なので hard action 実行は発生しない。

### Case B: Zero observer だけ停止

```bash
sudo systemctl stop raspi-revive-gpio-observer.service
```

期待:

- Pi 5 が emit 中でも mirror 更新が止まる。
- controller は mirror stale に従って判定する。
- Phase A なので hard action 実行は発生しない。

### Case C: controller だけ再起動

```bash
sudo systemctl restart raspi-revive-controller.service
```

期待:

- runtime state を使って再開し、不自然な振動がない。
- incident dedupe が継続して効く。
- 再起動直後の想定外介入がない。

### Case D: mirror path を一時的に破壊

安全な方法で一時退避し、復元する:

```bash
sudo mv /var/lib/raspi-revive-agent/gpio-heartbeat.json /var/lib/raspi-revive-agent/gpio-heartbeat.json.bak
# ... 挙動観測 ...
sudo mv /var/lib/raspi-revive-agent/gpio-heartbeat.json.bak /var/lib/raspi-revive-agent/gpio-heartbeat.json
```

期待:

- mirror missing/malformed は stale/unavailable evidence として扱われる。
- 分類結果がシナリオ期待から逸脱しない。
- Phase A なので hard action 実行は発生しない。

### Case E: GPIO 生存のまま network 側だけ失敗

期待:

- `gpio_heartbeat_fresh = true` を維持できる。
- network 依存証拠（`ping/ssh` など）のみ劣化する。
- Phase A なので hard action 実行は発生しない。

## Stage 3: 閾値の一回調整

目的: 実測 jitter / 欠落を見てから一度だけ調整する。

調整順:

1. `GPIO_PULSE_HOLD_MS`
2. `GPIO_OBSERVER_INTERVAL_SEC`
3. `gpio_heartbeat_stale_sec`（controller 側）

指針:

- 最初は保守的に設定:
  - pulse は短すぎない
  - observer interval はやや細かい
  - stale 閾値は余裕を持つ
- 一度に 1 項目だけ調整し、Stage 1/2 を再確認する。

## 昇格ゲート（Phase A -> B）

以下をすべて満たしたときのみ昇格:

- 24時間安定運用で説明不能な stale スパイクがない。
- 障害注入 Case A-E が期待どおり。
- `actions.jsonl` に意図しない hard action がない。
- すべての stale イベントをログとサービス状態で説明できる。
