# Scenario Replay

`raspi-revive` には、実機 failure injection 前に fixture を検証する軽量 replay CLI があります。

## Fixture 配置

- `tests/scenario/fixtures/*.json`

各 fixture は次を含みます。

- `scenario_id`
- `injected_failure`
- `expected_evidence`
- `expected_state`
- `expected_action`
- `forbidden_action`
- `recovery_verification`
- `notes`
- 観測と期待結果を持つ `steps[]`

任意 override:

- `maintenance_mode`
- `threshold_overrides`
- `guard_overrides`

## 全シナリオ実行

```bash
python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures
```

## 特定シナリオのみ実行

```bash
python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures \
  --scenario-id SCN-006 \
  --scenario-id SCN-007
```

## 出力

- 期待 state/action と forbidden-action チェックが通ると `[PASS] <scenario_id>`
- どこかの step が不一致だと `[FAIL] <scenario_id>`
