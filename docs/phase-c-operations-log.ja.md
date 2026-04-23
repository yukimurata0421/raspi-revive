# Phase C Operations Log

この文書は、Phase C の実地運用確認と介入挙動の記録を残すための運用ログです。

## 背景とこの文書の意図

- 背景: `2026-04-23` の `REMOTE_REBOOT` 実行検証を起点に、短いポスト検証ウィンドウ（`T+0`, `T+約180s`）で再起動ループ（誤発火）を2回確認した。
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
- 事象時刻（公開表記）: 短いポスト検証ウィンドウを `T+0` と `T+約180s` で表現

### 観測事実

- `REMOTE_REBOOT` が同ウィンドウ内で2回実行された（`T+0`, `T+約180s`）。
- 事象中もホストへの SSH 到達性は維持されていた。
- 根因は `host heartbeat` と `sentinel` の stale が `HOST_DEGRADED` に吸い込まれていた判定式だった。
- 即時の封じ込めとして以下を実施:
  - `enable_remote_reboot=false`
  - `pi5-guard` 上で controller service を再起動
- 正確なローカル時刻は private runbook 側に保持し、公開文書は相対表現で記録する。

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
