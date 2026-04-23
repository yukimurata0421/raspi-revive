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

## 2026-04-21: Phase A-C 段階的有効化と監視責務の再整理

### 背景

- Phase A/B 実運用を経て、controller の連続稼働と action gate の安全性を確認したうえで Phase C へ移行した。
- 併行して、過去に観測された `raspi-revive-controller.service: inactive (dead)` 事象の再発抑制が必要だった。

### 意思決定

1. 段階的有効化を維持する。
   - Phase A: 観測専用（介入なし）
   - Phase B: `enable_restart_sentinel=true` のみ開放
   - Phase C: `enable_remote_reboot=true` を追加開放
   - `enable_gpio_reboot` / `enable_power_button_pulse` は引き続き閉じる
2. `inactive (dead)` 対策は controller 側の複雑化ではなく監視責務の整理で行う。
   - 監視系は `raspi-sentinel` lite 構成へ寄せ、軽量な常時監視と単純な復旧経路を優先する。
   - controller は証拠ベース判定と段階的 action gate の責務に集中させる。

### 結果

- フェーズBでは危険側アクションを開かずに sentinel restart 経路の有効性を確認できた。
- Phase C 移行時点でも unsafe action の即時発火は確認されていない。
- `inactive (dead)` 事象は、`raspi-sentinel` lite 側への責務寄せにより再発抑制の運用線を確立した。

## 2026-04-23: Phase C 誤発火事象への対応と reboot 方針のハードニング

### 背景

- Phase C 運用中の `2026-04-23 06:55` と `06:58 JST` に remote reboot ループ事象を確認した。
- 事象時点の証跡では:
  - `actions.jsonl` に `REMOTE_REBOOT` 実行記録が残っている。
  - SSH 到達性は維持されていた。
  - 旧判定式では telemetry stale（`host heartbeat` + `sentinel`）が `HOST_DEGRADED` に入り得た。
- これは「強い介入は強い因果証拠で行う」という設計意図と整合しなかった。

### 意思決定

1. telemetry 故障と host 劣化を分離する。
   - `TELEMETRY_PIPELINE_FAILURE` を追加し、telemetry stale 単独は `HOST_DEGRADED` から外す。
   - ねらい: exporter/facts 系故障で host reboot を引かない。
2. `REMOTE_REBOOT` に因果証明を要求する。
   - `HOST_DEGRADED` の remote reboot は次を必須化:
     - target-plane 独立証拠（`gpio stale + host heartbeat stale + ssh ok`）
     - 同一 boot 内で telemetry baseline 正常を一度確認済み
   - ねらい: 「観測欠落」をそのまま reboot 理由にしない。
3. reboot 後の再収束待ちを状態機械へ明示化する。
   - `POST_BOOT_RECONCILIATION` / `RECOVERY_PARTIAL` を追加。
   - `post_boot_reconciliation_wait_seconds` を追加。
   - ねらい: boot 変化直後に同種の強い介入を再発火させない。
4. 有効化は運用者判断の明示ゲートにする。
   - 初動封じ込めは `enable_remote_reboot=false`。
   - ハードニング配備と回帰確認後に、運用判断で再有効化した。

### 根拠と検証

- RCA と運用証跡は次に記録:
  - `docs/phase-c-operations-log.md`
  - `2026-04-23 06:55/06:58 JST` の incident 記録
- ハードニング後の回帰確認:
  - `pytest -q` 通過
  - `ruff check` 通過
- 再有効化時の運用証跡:
  - `phase_changed: PHASE_B -> PHASE_C`
  - `action_gate_changed` で `enable_remote_reboot=1`

## 2026-04-23: negative validation をフェーズ昇格条件として明示化

### 背景

- 今回の事象は「Phase Bで何もしていなかった」ことが原因ではない。
- 欠けていたのは、Phase Bの目的定義が「正しく動くか」に寄っていて、「誤って動かないか」を独立ゲートとして定義していなかった点だった。
- 実運用では、telemetry stale 由来の failure mode が Phase C で初めて表面化した。

### 意思決定

1. 強い action の検証を、常に双方向で設計する。
   - 正方向検証:
     - 真の `HOST_DEGRADED` で `REMOTE_REBOOT` が制御下で実行できること
   - 逆方向検証:
     - telemetry-only failure、post-boot 直後、freshness jitter で `REMOTE_REBOOT` が発火しないこと
2. 今後の Phase B を明示的に2分割する。
   - B1: soft-action / observation validation
   - B2: hard-action exclusion validation（`REMOTE_REBOOT` は未解禁のまま）
3. hard action 解禁前に、B2固定シナリオを必須化する。
   - telemetry-only failure
   - post-boot reconciliation window
   - sentinel freshness jitter/flap

### ねらい

- 「もっと慎重に」という感情的反省ではなく、再利用可能な設計契約へ落とし込む。
- 「たまたま事故が起きなかった」状態での昇格を防ぐ。
- 未知の failure mode が Phase C 解禁後に初めて露出する確率を下げる。

## 2026-04-24: GPIO observer backend互換性と pin mapping 検証手順の固定化

### 背景

- `GPIO_OBSERVER_PIN=17` 運用への復帰時に `gpio_fresh` が不安定化し、backend問題か配線問題かの切り分けが必要になった。
- 実調査で、`gpiod` 実装の環境互換ギャップ（`gpiofind` 依存 / libgpiod v2 CLI差異）と、pin設定不一致が混在していた。

### 意思決定

1. `gpiod` backend は「Zero実環境で成立する実装」を前提にする。
   - `gpiofind` 不在時の chip hint フォールバックを許容する。
   - `gpioget` は libgpiod v2 形式（`-c <chip> --numeric <offset>`）で統一する。
2. 配線確認は論理ではなく実測で固定化する。
   - Pi 5 `GPIO17` 強制 `HIGH/LOW` と Zero 側追従 pin を毎回確認する。
3. freshness評価は「遷移窓」と「安定窓」を分離する。
   - 設定変更直後の窓を定常比較に混ぜない。

### 根拠

- 詳細ログは `docs/phase-c-operations-log.ja.md` の `2026-04-24` 記録を参照。
- 主要結論:
  - Pi 5 側の `HIGH` 保持不能仮説は棄却。
  - `gpiod` 実装互換ギャップは成立し、修正後に再現しないことを確認。
  - pin mapping / 設定整合後、短窓で `gpio_fresh=100%` を確認。

## Phase A-C の記録充足性

設計判断の記録は、以下を明示的に含む状態に更新した。

1. Phase A: GPIO 観測専用立ち上げ、配線制約、観測安定化。
2. Phase B: sentinel-only 介入境界と安全な昇格根拠。
3. Phase C:
   - 初期昇格と実稼働確認、
   - remote reboot 実行検証、
   - 誤発火事象対応、
   - 判定/介入方針のハードニング、
   - 条件付きの再有効化判断。
