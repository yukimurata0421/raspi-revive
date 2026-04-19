# Scenario Replay

`raspi-revive` provides a lightweight replay CLI to validate scenario fixtures before live failure injection.

## Fixture Location

- `tests/scenario/fixtures/*.json`

Each fixture includes:

- `scenario_id`
- `injected_failure`
- `expected_evidence`
- `expected_state`
- `expected_action`
- `forbidden_action`
- `recovery_verification`
- `notes`
- `steps[]` with observation + expected state/action

Optional fixture overrides:

- `maintenance_mode`
- `threshold_overrides`
- `guard_overrides`

## Run All Scenarios

```bash
python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures
```

## Run Specific Scenarios

```bash
python3 -m raspi_revive.scenario_replay_cli \
  --config targets/raspi-zero-controller/config/controller.example.toml \
  --scenario-dir tests/scenario/fixtures \
  --scenario-id SCN-006 \
  --scenario-id SCN-007
```

## Output

- `[PASS] <scenario_id>` when expected state/action and forbidden-action checks pass
- `[FAIL] <scenario_id>` when any step expectation mismatch occurs
