# Validation Scenarios

このドキュメントは `raspi-revive` の本番前検証シナリオを定義します。

各シナリオは次の形に統一します。

- `scenario_id`
- `injected_failure`
- `expected_evidence`
- `expected_state`
- `expected_action`
- `forbidden_action`
- `recovery_verification`
- `notes`

## Scenario Matrix（MVP）

| scenario_id | injected_failure | expected_evidence | expected_state | expected_action | forbidden_action | recovery_verification | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SCN-001` | sentinel のみ停止 | out-of-band gpio fresh、network host hb fresh、sentinel stale、ssh ok | `SENTINEL_ONLY_FAILURE` | `RESTART_SENTINEL` | `REMOTE_REBOOT`, `GPIO_REBOOT` | 想定ウィンドウ内で sentinel freshness 回復 | in-band 優先確認 |
| `SCN-002` | host heartbeat writer のみ停止 | gpio fresh、host hb stale（network-dependent）、ssh ok | `HEALTHY` または observe-only | `NO_ACTION` | `REMOTE_REBOOT`, `GPIO_REBOOT` | 介入が記録されない | 単独信号故障で reboot しない |
| `SCN-003` | GPIO emitter のみ停止 | gpio stale、host hb fresh、ssh ok | `HEALTHY` または observe-only | `NO_ACTION` | `REMOTE_REBOOT`, `GPIO_REBOOT` | 介入が記録されない | 配線/サービス故障耐性 |
| `SCN-004` | Zero から SSH のみ遮断 | gpio fresh、ssh fail、ping は任意 | `NETWORK_ONLY_ISSUE` | `NO_ACTION` | `REMOTE_REBOOT`, `GPIO_REBOOT` | 介入が記録されない | network path 障害 |
| `SCN-005` | Zero から ping のみ遮断 | gpio fresh、ping fail、ssh は任意 | `NETWORK_ONLY_ISSUE` | `NO_ACTION` | `REMOTE_REBOOT`, `GPIO_REBOOT` | 介入が記録されない | 弱い network 証拠のみ |
| `SCN-006` | host degraded（host stale + sentinel stale + ssh ok）をN周期継続 | ssh alive の multi-evidence 劣化 | `HOST_DEGRADED` | `REMOTE_REBOOT` | `GPIO_REBOOT` | post-action verification 開始 | remote reboot gate 確認 |
| `SCN-007` | freeze（gpio stale + host stale + ssh fail）を継続 | out-of-band stale + network-path failure | `FREEZE_SUSPECTED` | `GPIO_REBOOT` | 設定より強い介入 | `boot_id` 変化で復帰確認 | 最強手段 gate 確認 |
| `SCN-008` | action 予算上限まで到達させる | lockout window 内の action 回数上限到達 | `LOCKOUT` | lockout 後は `NO_ACTION` | lockout 中のすべての介入 | `entered/still_active/cleared` を確認 | loop 停止性 |
| `SCN-009` | active failure 中に maintenance mode 有効化 | 分類は故障でも mode が action を遮断 | 分類状態は保持、action gate は抑止 | `NO_ACTION` | すべての介入 | 観測/判定/audit が継続 | メンテ安全性 |
| `SCN-010` | SSH 管理経路のみ劣化 | gpio fresh + host hb fresh + ping ok + ssh fail | `MANAGEMENT_PLANE_DEGRADED` | `NO_ACTION` | `REMOTE_REBOOT`, `GPIO_REBOOT` | SSH 経路復帰まで介入しない | 管理プレーン障害を別分類で保持 |

## 実行メモ

- failure injection 中は controller を dry-run のまま運用する
- append-only JSONL で結果を確認:
  - `observations.jsonl`
  - `decisions.jsonl`
  - `actions.jsonl`
- 各シナリオで `incident_key`、`correlation_id`、`lockout_latch_event` の連続性を確認する
