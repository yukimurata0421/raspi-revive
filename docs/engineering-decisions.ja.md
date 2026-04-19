# Engineering Decisions

## 2026-04-19: Phase A GPIO 観測導入（Pi 5 -> Zero）

### 背景

- 目的は、out-of-band evidence として実 GPIO heartbeat 観測を有効化すること。
- 今回のスコープは観測専用:
  - GPIO reboot action は有効化しない
  - power-button pulse の配線/有効化はしない
  - state machine の hard action は増やさない
- 現在の物理配線:
  - Pi 5 physical pin 11（`BCM17`）-> Zero physical pin 11（`BCM17`）
  - GND 共通
  - 5V 同士は未接続
  - 3.3V 同士は未接続

### 意思決定

1. controller 直 GPIO アクセスは採用せず、疎結合を維持する。
   - Zero 側 observer service が実 GPIO を監視し mirror JSON を出力。
   - controller は既存どおり `FileHeartbeatInput` で `paths.gpio_heartbeat_path` を読む。
2. GPIO backend の既定は `pinctrl` にする。
   - `gpiochip0` 決め打ちを避ける。
   - `gpiod` fallback も維持し、`gpiofind GPIO<BCM>` で動的解決する。
3. stale 閾値は観測安定性優先で一時的に保守化する。
   - 実機 jitter/dropout に対して初期閾値は厳しすぎた。
   - Phase A 運用値として `gpio_heartbeat_stale_sec = 120.0` を適用。

### 実装内容

- Pi 5 emitter:
  - `targets/raspi-5-agent/scripts/emit_gpio_heartbeat.py`
  - backend 選択、env 既定値、pulse hold 調整を追加。
  - mirror に `source`、backend、emit status、error を追加。
- Zero observer:
  - `targets/raspi-zero-controller/scripts/observe_gpio_heartbeat.py`（新規）
  - pull 設定付き入力監視、edge/freshness mirror JSON 出力を追加。
- systemd/config:
  - `targets/raspi-zero-controller/systemd/raspi-revive-gpio-observer.service` を追加。
  - Pi 5 heartbeat service を env/pulse 設定対応に更新。
  - observer env テンプレートを追加。
  - Zero 実配備に合わせて controller service の前提を修正:
    - `User=root`（存在しない実行ユーザー前提を排除）
    - `/usr/bin/python3`（環境依存の venv path 前提を排除）
- tests/docs:
  - mirror 入力と GPIO scripts dry-run の unit test を追加。
  - README/wiring/runtime/rollout を更新し、Phase A checklist を追加。

### 配備ノート（公開向けサニタイズ）

- controller probe 先は公開文書/設定ではプレースホルダで表現する:
  - `ssh_target = "<agent-user>@<agent-host>"`
  - `ping_target = "<agent-host-or-ip>"`
- SSH options も公開文書/設定では抽象化する:
  - 鍵: `<controller-user-home>/.ssh/id_ed25519`
  - known_hosts: `<controller-user-home>/.ssh/known_hosts`
  - host key 厳格チェックは有効化する。
- facts 同期パスは役割ベースのプレースホルダで表現する:
  - agent export root: `<agent-export-root>`
  - controller local mirror root: `<local-facts-mirror-root>/remote/`
  - controller はこの mirror 配下の `host-heartbeat.json`、`sentinel/stats.json`、`sentinel/state.json` を読む。
- deployment root も公開文書ではプレースホルダにする:
  - `<deployment-root>`

### 立ち上げ後の安定化

- `status=217/USER` は service の実行ユーザー前提を実環境に合わせることで解消した。
- controller は観測ループと logs/state の永続化を安定して継続できる状態になった。
- facts 同期は controller 側の判定を安定化させるため、継続 mirror モデルへ変更した。
- GPIO 観測は Phase A の安定性優先で調整:
  - `gpio_heartbeat_stale_sec = 120.0`
  - `GPIO_PULSE_HOLD_MS = 1000`
- 安定化後の結果:
  - 健全時は `HEALTHY` かつ `gpio/host/sentinel/ssh/ping = true` に収束。
  - Phase A 方針どおり action は `NO_ACTION` のみ。

### 現在の運用姿勢

- Phase A で観測安定性を優先して継続運用。
- 介入線は未接続、action gate は閉じたまま維持。
- 閾値の引き締めは証拠ベースで段階的に行う。
