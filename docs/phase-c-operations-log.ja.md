# Phase C Operations Log

この文書は、Phase C の実地運用確認と介入挙動の記録を残すための運用ログです。

## 背景とこの文書の意図

- 背景: `2026-04-23` の `REMOTE_REBOOT` 実行検証を起点に、`06:55` と `06:58` JST に再起動ループ（誤発火）を確認した。
- 意図: この文書は「テスト成功記録」だけでなく、「誤発火の事実」「原因」「封じ込め」「再発防止ロジック」を同じ系列で追跡するための記録である。
- 運用方針: `REMOTE_REBOOT` は常時開放ではなく、証拠ゲートを満たす実装と明示的な運用判断の両方で制御する。

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

## 2026-04-23 (JST) フェーズC REMOTE_REBOOT 実行検証

### 対象

- 証跡ファイル:
  - `<controller-home>/phase-c-remote-reboot-test-20260423T062804+0900.log`
  - `<controller-home>/phase-c-remote-reboot-test-20260423T062804+0900.summary`
  - `/var/log/raspi-revive/actions.jsonl`
  - `/var/log/raspi-revive/events.jsonl`
- 実行ウィンドウ: `2026-04-23 06:28:04` から `06:29:09 JST`

### 実行エビデンス

- 開始時の gate 値:
  - `dry_run=false`
  - `enable_restart_sentinel=true`
  - `enable_remote_reboot=true`
  - `enable_gpio_reboot=false`
  - `enable_power_button_pulse=false`
- 検証では制御下で `HOST_DEGRADED` 条件を注入。
- `actions.jsonl` で介入を1回記録:
  - `chosen_action=REMOTE_REBOOT`
  - `execution.executed=true`
  - `execution.success=true`
  - `detail=exit=0`
- ポーリングログで以下を確認:
  - `06:28:42 JST` 時点で `remote_reboot_count=1`
  - `06:29:08 JST` 時点で host `boot_id` が `5d86a957-291d-4f79-b7de-dc99648615ae` から `7618b75a-7ee4-4c56-9f0a-30a49e0f7323` に変化
- 状態遷移も設計どおりに記録:
  - `HOST_DEGRADED -> RECOVERY_IN_PROGRESS -> COOLDOWN -> HEALTHY`

### 判断

- この検証経路では、Phase C の制御ループを end-to-end で確認できた:
  - 証拠にもとづく状態分類
  - gate 条件つき介入実行
  - `boot_id` 変化による post-action 検証
  - 定常状態への復帰
- `summary` には `success=1` と `remote_reboot_count=1` が記録されている。

## 2026-04-23 (JST) 誤発火RCAとロジック改修

### 対象

- 証跡ファイル:
  - `pi5:/var/log/raspi-revive/actions.jsonl`
  - `pi5:/var/log/raspi-revive/events.jsonl`
  - `pi5-guard:/etc/raspi-revive/controller.toml`
- 事象時刻: `2026-04-23 06:55` と `06:58 JST`

### 観測事実

- `REMOTE_REBOOT` が `06:55` と `06:58 JST` に実行された。
- 事象中もホストへの SSH 到達性は維持されていた。
- 根因は `host heartbeat` と `sentinel` の stale が `HOST_DEGRADED` に吸い込まれていた判定式だった。
- 即時の封じ込めとして以下を実施:
  - `enable_remote_reboot=false`
  - `pi5-guard` 上で controller service を再起動

### 実施したハードニング

- 状態分離を追加:
  - `TELEMETRY_PIPELINE_FAILURE`
  - `POST_BOOT_RECONCILIATION`
  - `RECOVERY_PARTIAL`
- `HOST_DEGRADED` は target-plane の独立証拠を必須化:
  - `gpio stale + host heartbeat stale + ssh ok`
- `REMOTE_REBOOT` は同一 boot 内の telemetry baseline を必須化:
  - `host heartbeat fresh + sentinel fresh + ssh ok` を少なくとも1回観測
- reboot 検証（`boot_id` 変化）後は `POST_BOOT_RECONCILIATION` 中に hard action を抑止し、telemetry 再収束または timeout まで待機する。

### 検証

- 改修後のローカル回帰:
  - `pytest -q` -> `42 passed`
  - `python3 -m ruff check src tests` -> `All checks passed`

## 2026-04-23 (JST) ハードニング後の Phase C 再有効化

### 対象

- Controller host: `pi5-guard`
- 設定ファイル: `/etc/raspi-revive/controller.toml`
- Service: `raspi-revive-controller.service`

### 実行エビデンス

- ハードニング適用後、運用判断により `REMOTE_REBOOT` を再有効化。
- 適用設定:
  - `enable_remote_reboot = true`
  - `post_boot_reconciliation_wait_seconds = 180.0` は維持
- service 再起動後も `active` を維持。
- `events.jsonl` で以下を確認:
  - `phase_changed` : `PHASE_B -> PHASE_C`
  - `action_gate_changed` : `enable_remote_reboot=1`

### 判断

- 封じ込め解除は自動ではなく、RCA と実装改修、回帰確認を満たした後の明示判断で実施した。

## 2026-04-23 (JST) sentinel facts 鮮度フラップ分析と閾値調整

### 対象

- Controller host: `pi5-guard`
- 設定ファイル: `/etc/raspi-revive/controller.toml`
- 実行ログ:
  - `/var/log/raspi-revive/observations.jsonl`
  - `/var/log/raspi-revive/decisions.jsonl`
  - `/var/log/raspi-revive/actions.jsonl`
  - `/var/log/raspi-revive/events.jsonl`
- sentinel 実行周期の根拠:
  - `/etc/systemd/system/raspi-sentinel.timer`
  - `/etc/raspi-sentinel/config.toml`

### 調査結果

- `raspi-revive` 側の stale 閾値は以下だった:
  - `sentinel_stats_stale_sec = 30.0`
  - `sentinel_state_stale_sec = 30.0`
- `raspi-sentinel` は `OnUnitActiveSec=30s` に jitter（`RandomizedDelaySec=5s`, `AccuracySec=15s`）が重なり、実測開始間隔は主に `35-45s` 帯だった。
- `2026-04-23 09:00 JST` 以降の調査窓では:
  - `SENTINEL_ONLY_FAILURE` が `sentinel facts stale while host/gpio/ssh indicate OS alive` 理由で繰り返し発生。
  - `REMOTE_REBOOT` / `RESTART_SENTINEL` は発火せず（`NO_ACTION`のみ）、介入暴走ではなく鮮度判定のフラップであることを確認。
- リモート側とミラー側の mtime を照合し、ミラー遅延が主因ではないことを確認。支配要因は「閾値と実周期のミスマッチ」。

### 適用変更

- `pi5-guard` 上の `/etc/raspi-revive/controller.toml` を更新:
  - `sentinel_stats_stale_sec = 60.0`
  - `sentinel_state_stale_sec = 60.0`
- `raspi-revive-controller.service` を再起動。
- `2026-04-23 18:02 JST` 時点で service は `active (running)` を確認。

### 変更直後の短期検証

- 観測窓: `2026-04-23 18:02:35` から `18:04:25 JST`（約110秒）
- 結果:
  - `observations=10`
  - 全件 `HEALTHY`
  - `sentinel_stats_fresh=false` / `sentinel_state_fresh=false`: `0`
- これは長時間ソークの代替ではないが、少なくとも直後窓では今回のフラップ起点が解消していることを示す。

## 2026-04-24 (JST) GPIO freshness 低下の切り分け（backend比較 + 配線実測）

### 背景

- 事象:
  - `GPIO_OBSERVER_PIN=17` へ戻した後に `gpio_fresh_ratio` が約 `50%` 前後で不安定に見えた。
- 目的:
  - 「pinctrl backend の取りこぼし」かどうかを、同条件で `gpiod` と比較し、ソフト層と物理層のどちらが支配要因かを確定する。

### 調査前に立てた仮説

1. ソフト層仮説:
   - `pinctrl` 読み取り取りこぼし。
   - `gpiod` 実装の互換不整合（`gpiofind` 依存、CLI差異）。
2. 物理層仮説:
   - observer が実際の受信線と異なる GPIO を監視している（pin mapping mismatch）。
   - Pi 5 側が `HIGH` を保持できず、Zero 側で `LOW` と見える。

### 切り分けアプローチ（実施順）

1. 競合プロセス除外:
   - `projects` 配下を走査し、GPIO17 を触る実装が `raspi-revive` 以外にないことを確認。
2. backend 切替A/B:
   - Zero observer を `pinctrl -> gpiod` に切替えて同窓比較を実施。
3. `gpiod` 起動失敗の原因特定:
   - `raspi-revive-gpio-observer.service` が restart loop。
   - 原因:
     - 実装が `gpiofind` 必須だが、Zero 環境に `gpiofind` が無い。
     - `gpioget` 呼び出しが libgpiod v2 CLI 仕様と不整合。
4. 実装修正 + テスト:
   - `observe_gpio_heartbeat.py` を修正:
     - `gpiofind` 不在時は `GPIO_OBSERVER_GPIOD_CHIP`（既定 `gpiochip0`）+ pin offset フォールバック。
     - `gpioget -c <chip> --bias ... --numeric <offset>` に統一。
   - `tests/test_gpio_scripts.py` に回帰テスト追加（`7 passed`）。
5. 物理対応確認（強制HIGH/LOW）:
   - Pi 5 側 `GPIO17` を強制 `HIGH/LOW` し、Zero 側の各 pin 反応を比較。
   - 実測:
     - 強制 `HIGH` で Zero `GPIO17=0`, `GPIO27=1`
     - 強制 `LOW` で Zero `GPIO17=0`, `GPIO27=0`
   - 一時的に「Pi 5の17信号はZeroの27で読める」状態を確認。
6. 配線・設定再調整:
   - 配線を見直し後、再測定で `Pi 5 GPIO17` の強制 `HIGH/LOW` に Zero `GPIO17` が追従することを確認。
   - あわせて observer 設定が誤って `PIN=27` に残っていた期間を補正し、`PIN=17` へ統一。

### 観測結果（要点）

- Pi 5 側の `HIGH` 保持不能仮説は棄却:
  - `pinctrl set 17 op dh` の連続読み取りで `hi` を安定確認。
- `gpiod` 経路の不整合は成立:
  - 修正前は起動失敗、修正後は `--once --backend gpiod` で `observer_status=ok`。
- freshness 低下の主因は「backend固有性能」単独ではなく、次の複合:
  1. `gpiod` 実装互換ギャップ（修正済み）
  2. 実配線/監視pinと設定pinの不一致が混在した時間窓
- 設定・配線の再整合後、直近短窓で以下を確認:
  - `60s samples=5 true=5 false=0 ratio=100%`
  - `gpio_heartbeat_age_sec` は概ね `~0.8s`（最大 `~1.7s`）

### 根因（RCA）

- 第一原因:
  - GPIO受信 pin と observer 設定 pin が一時的に不一致だったこと。
- 第二原因（増幅要因）:
  - `gpiod` backend 実装が Zero 実環境（libgpiod v2 + gpiofind未導入）に適合していなかったこと。

### 再発防止

1. 起動前 pin マッピング手順を固定化:
   - Pi 5 `GPIO17` 強制 `HIGH/LOW` と Zero 側 `gpioget -c gpiochip0 --numeric 17` の追従確認を実施。
2. observer の backend 切替時は次を必須チェック:
   - `systemctl is-active`
   - `--once` 実行で `observer_status=ok`
   - `last_edge_wall_time` が進むこと
3. 集計窓の運用ルール:
   - 設定変更直後の「遷移窓」を評価対象から分離し、比較は安定窓で行う。

### 関連する閾値の引き締め

- GPIO観測の安定化に合わせて、`gpio_heartbeat_stale_sec` は次の方針で運用している。
  - 初期運用値: `120.0`（観測安定性優先）
  - 現行運用値: `10.0`（実測 `age ~0.8s`, `max ~1.7s` に対して十分な余裕）
- 実機バックアップの確認:
  - `2026-04-20 05:27 JST` 時点: `120.0`
  - `2026-04-22 11:01 JST` 時点: `10.0`
  - 引き締め適用は `2026-04-22` 前後に完了したと判断できる。
- リポジトリ側の phase 設定は全phase共通で `10.0` を採用済み。
- rolling 24h 観測スナップショット（`2026-04-24 09:05 JST` 時点）:
  - 窓: `2026-04-23 09:05 JST` から `2026-04-24 09:05 JST`
  - `samples=7907`, `gpio_fresh=true=3709`, `false=4198`, `ratio=46.91%`
  - `age_mean=16.913s`, `p50=10.847s`, `p95=53.583s`, `max=238.386s`
  - 注記: この24h窓には修正前/切替中のサンプルが含まれるため、修正完了判定は「遷移窓を除いた安定窓」と併用して評価する。

### English Summary (short)

- Root cause was not a single `pinctrl` sampling issue.
- The dominant factors were:
  1. temporary pin mapping mismatch (observed signal path did not match configured observer pin),
  2. `gpiod` compatibility gap on Zero (`gpiofind` dependency + libgpiod v2 CLI mismatch), now fixed.
- After wiring/config realignment and `gpiod` compatibility fix, short-window `gpio_fresh` recovered to `100%`.

## Phase A-C 記録の充足確認

この運用ログと関連文書により、次を明示的に追跡できる状態になった。

- Phase A: GPIO 観測専用の立ち上げと安定化。
- Phase B: sentinel-only 介入境界での実運用検証。
- Phase C:
  - 実稼働確認、
  - controlled remote reboot 実行検証、
  - 誤発火事象とRCA、
  - ロジックハードニング、
  - 条件付き再有効化の実施証跡。

## 2026-04-25 (JST) controller-state 鮮度改善の概要

### 概要

- `HEALTHY` 連続時の state 停滞を避けるため、runtime state にハートビート保存を追加。
- 構造比較とハートビート比較を明示的に分離し、保存条件を明確化。
- state 永続化異常のイベントを追加:
  - `controller_state_write_failed`
  - `controller_state_write_stale`
- controller service に start-limit ガードを追加し、急速な restart loop を抑制。

### 検証

- persistence 専用の回帰テストを追加。
- 反映後に state の時刻進行が heartbeat 間隔で前進することを確認。
