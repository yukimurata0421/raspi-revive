# raspi-revive

`raspi-revive` は Raspberry Pi 向けの out-of-band 復旧レイヤーです。

このリポジトリは、in-band 復旧だけでは安全に扱いにくい故障モードを外側から扱うためにあります。

- `raspi-sentinel` は管理対象ホスト内の in-band recovery を担います。
- ホストフリーズ、管理プレーン断、sentinel 自体の不全は in-band 境界を超える場合があります。
- `raspi-revive` は evidence gate と段階投入（phased rollout）で hard action を抑制しながら外側の制御ループを提供します。

役割分離:

- `raspi-5-agent`: 事実のみを出力（host heartbeat、GPIO heartbeat、sentinel facts export）
- `raspi-zero-controller`: 判定と介入を担当（state machine、段階的 action、cooldown/lockout、監査ログ）

## 現在のスコープと未完成事項

- 公開ベースラインの投入は `Phase A`（observation-first）からの段階適用を維持する。
- 実運用は Phase A/B の証拠を経て、実機で `Phase C` まで進行している。
- `Phase C` では `RESTART_SENTINEL` と `REMOTE_REBOOT` を有効化し、`GPIO_REBOOT` と `POWER_BUTTON_PULSE` は無効のまま。
- より強い介入は、低リスク phase の証拠が揃ってから段階的に有効化する。

運用記録:
- [`docs/phase-c-operations-log.ja.md`](docs/phase-c-operations-log.ja.md): 誤発火ハードニング（`2026-04-23`）と GPIO observer 互換性/配線切り分け（`2026-04-24`）を記録。
- [`docs/phase-b-operations-log.ja.md`](docs/phase-b-operations-log.ja.md): Phase C 昇格前の段階投入エビデンスを記録。

## 設計品質宣言

- `Fact / Decision / Intervention` 境界の正しさを第一級の品質目標として扱う。
- 強い証拠ゲートが揃わない限り hard action を実行しない。
- intervention 有効化より前に observation-first の段階投入を必須とする。

## Fact / Decision / Intervention の境界

- Fact: agent スクリプトと probe が生成。
- Decision: controller の evaluator + state machine のみで実施。
- Intervention: controller の action executor のみで実行。

## Action 条件（MVP）

| 判定状態 | 必要証拠（要約） | 候補 Action | Phase ゲート条件 |
| --- | --- | --- | --- |
| `HEALTHY` | stale/degraded/freeze のゲート未該当 | `NO_ACTION` | 常時許可 |
| `MANAGEMENT_PLANE_DEGRADED` | gpio fresh + host heartbeat fresh + ping ok + ssh fail | `NO_ACTION` | 常時許可 |
| `NETWORK_ONLY_ISSUE` | ping/ssh 問題 + out-of-band gpio fresh | `NO_ACTION` | 常時許可 |
| `SENTINEL_ONLY_FAILURE` | gpio fresh + host heartbeat fresh + ssh ok + sentinel stale | `RESTART_SENTINEL` | Phase B 以降で有効 |
| `HOST_DEGRADED` | (gpio stale + host stale + ssh ok) または (host stale + sentinel stale + ssh ok) | `REMOTE_REBOOT` | Phase B では無効（Phase C 以降） |
| `FREEZE_SUSPECTED` | gpio stale + host stale + ssh fail + 連続サイクル成立 | `GPIO_REBOOT` | Phase B では無効（Phase C 以降） |

## Safety Gate

- `cooldown_seconds` で連続介入を抑止。
- `max_actions_per_window` と `lockout_window_seconds` で `LOCKOUT` へ遷移。
- reboot 系 action は `boot_id` 変化で post-action verification。
- Phase B の sentinel restart verification は freshness（`sentinel stats/state`）で判定し、reboot verification と分離する。
- `maintenance_mode=true` で介入を停止（観測/判定/監査は継続）。
- 同一 incident key への再介入を抑止。
- lockout のラッチイベント（`entered/still_active/cleared`）を decision/action ログに記録。

## GPIO heartbeat 観測方針（Phase A）

- この phase のスコープは観測のみ。
- 現在の配線: Pi 5 physical pin 11（`BCM17`）-> Pi Zero physical pin 11（`BCM17`）+ GND 共通。
- 5V 同士、3.3V 同士はボード間で接続しない。
- controller は `phase-a` 設定で action gate を閉じたまま運用する。
- Pi 5 emitter は `targets/raspi-5-agent/scripts/emit_gpio_heartbeat.py`。
- Pi Zero observer は `targets/raspi-zero-controller/scripts/observe_gpio_heartbeat.py` で物理 edge を観測し、controller が読む mirror JSON を更新する。

## Runtime 出力（コミットしない）

- `observations.jsonl`
- `decisions.jsonl`
- `actions.jsonl`
- `events.jsonl`（lifecycle / transition 専用、意図的に疎）
- controller state JSON
- 任意通知ファイル: `notify-events.jsonl`、`notify-stats.json`、`notify-queue.json`

steady-state の連続根拠は `observations.jsonl` / `decisions.jsonl` / `actions.jsonl` を正本として確認します。
安定した Phase A soak 中に `events.jsonl` が長時間静かな状態（例: 18時間エントリなし）は正常になりえます。

## 任意通知キュー（復旧アクション無効のまま利用可能）

- restart/reboot を無効のまま、通知専用ポリシーを有効化できます。
- `HOST_DEGRADED` または `FREEZE_SUSPECTED` が 5 分以上連続した場合、通知イベントを enqueue します。
- queue イベントは次を試行します。
  - SSH 経由で Pi 5 側 JSONL へ append（`notify.remote_jsonl_path`）
  - Discord webhook 送信
- 送達リトライ方針:
  - 失敗継続 5 分未満は 60 秒間隔でリトライ
  - 5 分連続失敗後は指数バックオフ
- secret 直書きは避け、`notify.discord_webhook_url_env` で `RASPI_REVIVE_DISCORD_WEBHOOK_URL` を使います。

## Scenario Replay Harness

- Harness: `src/raspi_revive/scenario_harness.py`
- Fixture テスト: `tests/scenario/test_fixture_replay.py`
- Fixture: `tests/scenario/fixtures/*.json`

harness は合成観測を evaluator/state machine に再生し、実機故障注入の前に期待 state/action と禁止 action を検証します。

### CLI

```bash
python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures
```

`--scenario-id` を複数指定すると対象シナリオを絞れます。

## ドキュメント

- アーキテクチャ: [`docs/architecture.ja.md`](docs/architecture.ja.md)
- ステートマシン: [`docs/state-machine.ja.md`](docs/state-machine.ja.md)
- 検証シナリオ: [`docs/validation-scenarios.ja.md`](docs/validation-scenarios.ja.md)
- Event policy: [`docs/event-policy.ja.md`](docs/event-policy.ja.md)
- リプレイ手順: [`docs/scenario-replay.ja.md`](docs/scenario-replay.ja.md)
- 段階投入: [`docs/rollout-phases.ja.md`](docs/rollout-phases.ja.md)
- Phase A 実機チェック: [`docs/phase-a-validation-checklist.ja.md`](docs/phase-a-validation-checklist.ja.md)
- Phase B 実機チェック: [`docs/phase-b-validation-checklist.ja.md`](docs/phase-b-validation-checklist.ja.md)
- Phase B 運用ログ: [`docs/phase-b-operations-log.ja.md`](docs/phase-b-operations-log.ja.md)
- 設計判断: [`docs/engineering-decisions.ja.md`](docs/engineering-decisions.ja.md)
- Notify Queue 設計: [`docs/notify-queue.ja.md`](docs/notify-queue.ja.md)
- 公開向け運用ノート雛形: [`docs/ops-notes.ja.md`](docs/ops-notes.ja.md)
- private runbook 雛形（実値を入れた版は公開外で管理）: [`docs/private-runbook.template.ja.md`](docs/private-runbook.template.ja.md)

## Assumptions（MVP）

- Controller が agent export の fact ファイルを設定パスから読めること。
- GPIO の電気的安全層はこのリポジトリの外で担保すること。
- 配備先で `pinctrl`（既定 GPIO backend）または libgpiod tools、および `ping`, `ssh` が使えること。

## TODO（将来拡張）

- より強い Level 4 最終手段を追加。
- `LOCKOUT` 向け専用 notifier 連携を追加。
- コマンド実行以外の GPIO backend を追加。
