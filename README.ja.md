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

- 現在の投入段階は `Phase A`。
- 運用方針は observation-first。
- この phase では intervention lines は有効化/接続しない。
- より強い介入は、低リスク phase の証拠が揃ってから段階的に有効化する。

## 設計品質宣言

- `Fact / Decision / Intervention` 境界の正しさを第一級の品質目標として扱う。
- 強い証拠ゲートが揃わない限り hard action を実行しない。
- intervention 有効化より前に observation-first の段階投入を必須とする。

## Fact / Decision / Intervention の境界

- Fact: agent スクリプトと probe が生成。
- Decision: controller の evaluator + state machine のみで実施。
- Intervention: controller の action executor のみで実行。

## Action 条件（MVP）

| 判定状態 | 必要証拠（要約） | Action |
| --- | --- | --- |
| `HEALTHY` | stale/degraded/freeze のゲート未該当 | `NO_ACTION` |
| `MANAGEMENT_PLANE_DEGRADED` | gpio fresh + host heartbeat fresh + ping ok + ssh fail | `NO_ACTION` |
| `NETWORK_ONLY_ISSUE` | ping/ssh 問題 + out-of-band gpio fresh | `NO_ACTION` |
| `SENTINEL_ONLY_FAILURE` | gpio fresh + host heartbeat fresh + ssh ok + sentinel stale | `RESTART_SENTINEL` |
| `HOST_DEGRADED` | (gpio stale + host stale + ssh ok) または (host stale + sentinel stale + ssh ok) | `REMOTE_REBOOT` |
| `FREEZE_SUSPECTED` | gpio stale + host stale + ssh fail + 連続サイクル成立 | `GPIO_REBOOT` |

## Safety Gate

- `cooldown_seconds` で連続介入を抑止。
- `max_actions_per_window` と `lockout_window_seconds` で `LOCKOUT` へ遷移。
- reboot 系 action は `boot_id` 変化で post-action verification。
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
- controller state JSON

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
- リプレイ手順: [`docs/scenario-replay.ja.md`](docs/scenario-replay.ja.md)
- 段階投入: [`docs/rollout-phases.ja.md`](docs/rollout-phases.ja.md)
- Phase A 実機チェック: [`docs/phase-a-validation-checklist.ja.md`](docs/phase-a-validation-checklist.ja.md)
- 設計判断: [`docs/engineering-decisions.ja.md`](docs/engineering-decisions.ja.md)
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
