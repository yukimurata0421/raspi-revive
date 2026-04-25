# Event Logging Policy

この文書は append-only 実行ログの役割分担を定義します。

## 各ログの役割

- `observations.jsonl`: 毎 cycle の事実 (`Fact` レイヤー)
- `decisions.jsonl`: 毎 cycle の判定と選択 action (`Decision` レイヤー)
- `actions.jsonl`: 毎 cycle の action 実行/抑止の詳細 (`Intervention` レイヤー)
- `events.jsonl`: noteworthy な lifecycle / transition のみ

`events.jsonl` は意図的に疎に保ち、heartbeat ストリームにはしません。

## `events.jsonl` に書くもの

明示的なマイルストーンと遷移イベントを記録します。

- `controller_started`
- `phase_changed`
- `phase_b_enabled`
- `action_gate_changed`
- `controller_state_changed`
- `maintenance_mode_enabled` / `maintenance_mode_disabled`
- `lockout_entered` / `lockout_still_active` / `lockout_cleared`
- `sentinel_restart_scheduled`
- `sentinel_restart_completed`
- `sentinel_restart_verified`
- `sentinel_restart_failed`
- `controller_state_write_failed`
- `controller_state_write_stale`

## `events.jsonl` に書かないもの

- HEALTHY 継続中の周期 heartbeat
- 既に `observations.jsonl` にある毎 cycle 観測
- 既に `actions.jsonl` にある毎 cycle 抑止詳細

`controller_state_write_stale` は判定入力ではなく lifecycle 異常イベントとして扱います。
過去に保存された state が古い場合、起動直後に記録されることがあります。

## Phase A で events が静かなときの解釈

Phase A soak 中に `events.jsonl` が長時間静かな状態（例: 18時間エントリなし）は正常になりえます。
連続稼働の根拠は `observations.jsonl` と `decisions.jsonl` を正本として確認します。

## Phase B の verification メモ

Phase B の sentinel restart verification は reboot verification と分離します。

- reboot 系 action: `boot_id` 変化で検証（`RECOVERY_IN_PROGRESS` フロー）
- sentinel restart: sentinel freshness（`stats/state` freshness）で検証し、`actions.jsonl` と `events.jsonl` に記録
