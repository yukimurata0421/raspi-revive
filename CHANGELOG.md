# Changelog

All notable changes to this project are documented in this file.

## 2026-04-21

### Phase C rollout documentation alignment

- Updated public `README.md` / `README.ja.md` top summary to match live phased rollout status through `Phase C`.
- Clarified that `Phase C` enables `RESTART_SENTINEL` and `REMOTE_REBOOT`, while `GPIO_REBOOT` and `POWER_BUTTON_PULSE` remain disabled.
- Added Phase A-C decision rationale to engineering decision docs:
  - `docs/engineering-decisions.md`
  - `docs/engineering-decisions.ja.md`

## 2026-04-20

### Phase A/B rollout and logging policy

- Added explicit event logging policy docs:
  - `docs/event-policy.md`
  - `docs/event-policy.ja.md`
- Clarified that steady healthy loops are recorded in:
  - `observations.jsonl`
  - `decisions.jsonl`
  - `actions.jsonl`
- Clarified that `events.jsonl` is reserved for transitions/lifecycle/notable events and should stay quiet during steady healthy operation.

### Phase B promotion safety boundary

- Promoted Phase B behavior to enable only `RESTART_SENTINEL` intervention.
- Kept `REMOTE_REBOOT`, `GPIO_REBOOT`, and `POWER_BUTTON_PULSE` disabled in Phase B.
- Updated rollout/config/docs to keep Phase A and Phase B boundaries explicit.

### Validation and verification updates

- Added/updated scenario coverage for sentinel-only failure handling.
- Added event logging tests to ensure no steady-state event spam.
- Added phase config tests to verify Phase B action gate settings.
- Added Phase B operation log/checklist docs:
  - `docs/phase-b-operations-log.md`
  - `docs/phase-b-operations-log.ja.md`
  - `docs/phase-b-validation-checklist.md`
  - `docs/phase-b-validation-checklist.ja.md`
