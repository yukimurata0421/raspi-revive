# Validation Scenarios

This document defines pre-production validation scenarios for `raspi-revive`.

Each scenario must use the same record shape:

- `scenario_id`
- `injected_failure`
- `expected_evidence`
- `expected_state`
- `expected_action`
- `forbidden_action`
- `recovery_verification`
- `notes`

## Scenario Matrix (MVP)

| scenario_id | injected_failure | expected_evidence | expected_state | expected_action | forbidden_action | recovery_verification | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SCN-001` | Stop sentinel only | out-of-band gpio fresh, network host hb fresh, sentinel stale, ssh ok | `SENTINEL_ONLY_FAILURE` | `RESTART_SENTINEL` | `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE` | sentinel facts become fresh within expected window | validates in-band first |
| `SCN-002` | Stop host heartbeat writer only | gpio fresh, host hb stale (network-dependent), ssh ok | `HEALTHY` or observe-only state | `NO_ACTION` | `RESTART_SENTINEL`, `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE` | no intervention recorded | single-signal failure must not reboot |
| `SCN-003` | Stop GPIO emitter only | gpio stale, host hb fresh, ssh ok | `HEALTHY` or observe-only state | `NO_ACTION` | `RESTART_SENTINEL`, `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE` | no intervention recorded | wiring/service fault tolerance |
| `SCN-004` | Block SSH only from Zero | gpio fresh, ssh fail, ping maybe ok | `NETWORK_ONLY_ISSUE` | `NO_ACTION` | `RESTART_SENTINEL`, `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE` | no intervention recorded | network path issue only |
| `SCN-005` | Block ping only from Zero | gpio fresh, ping fail, ssh maybe ok | `NETWORK_ONLY_ISSUE` | `NO_ACTION` | `RESTART_SENTINEL`, `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE` | no intervention recorded | weak network evidence only |
| `SCN-006` | Simulate host degraded (gpio stale + host stale + ssh ok) for N cycles after baseline | target-plane degradation evidence with ssh alive | `HOST_DEGRADED` | `REMOTE_REBOOT` | `GPIO_REBOOT` | post-action verification starts | remote reboot gate check |
| `SCN-007` | Simulate freeze (gpio stale + host stale + ssh fail) sustained | out-of-band stale + network-path failures | `FREEZE_SUSPECTED` | `GPIO_REBOOT` | none stronger than configured level | reboot verified by `boot_id` change | strongest action gate |
| `SCN-008` | Trigger repeated actions to budget limit | action count reaches configured max in lockout window | `LOCKOUT` | `NO_ACTION` after lockout | any intervention during lockout | lockout latch `entered/still_active/cleared` appears | stop-loop safety |
| `SCN-009` | Enable maintenance mode during active failure | classification may indicate fault, mode blocks action | classified state unchanged, action gate suppressed | `NO_ACTION` | all interventions | audit still records observation/decision | maintenance safety |
| `SCN-010` | SSH management path degraded only | gpio fresh + host hb fresh + ping ok + ssh fail | `MANAGEMENT_PLANE_DEGRADED` | `NO_ACTION` | `RESTART_SENTINEL`, `REMOTE_REBOOT`, `GPIO_REBOOT`, `POWER_BUTTON_PULSE` | no intervention while SSH path recovers | keeps management-plane issues distinct |

## Execution Notes

- Keep controller in dry-run while running failure injections.
- Validate all outcomes via append-only JSONL:
  - `observations.jsonl`
  - `decisions.jsonl`
  - `actions.jsonl`
- Review `incident_key`, `correlation_id`, and `lockout_latch_event` continuity for each scenario.
