# Changelog

All notable changes to this project are documented in this file.

## 2026-04-23

### False-trigger hardening for Phase C remote reboot

- Reworked classifier and state machine to separate telemetry failure from host degradation:
  - Added `TELEMETRY_PIPELINE_FAILURE` state.
  - Restricted `HOST_DEGRADED` to target-plane evidence (`gpio stale + host heartbeat stale + ssh ok`).
- Added reboot lineage and reconciliation controls:
  - Added `POST_BOOT_RECONCILIATION` and `RECOVERY_PARTIAL` states.
  - Added `post_boot_reconciliation_wait_seconds` guard setting.
  - Suppressed hard actions after reboot until telemetry recovers or reconciliation timeout.
- Added stronger `REMOTE_REBOOT` gate:
  - Requires telemetry baseline in the same boot (`host heartbeat + sentinel + ssh` healthy at least once).
- Updated scenario fixtures and tests for new decision boundaries and reconciliation flow.
- Updated docs (`README`, state-machine docs, Phase C operations log, validation scenarios) to match the new behavior.

### Phase C remote reboot verification documentation update

- Updated `docs/phase-c-operations-log.md` / `docs/phase-c-operations-log.ja.md`:
  - Removed context wording tied to conversation transcripts.
  - Added a concrete execution record for the `2026-04-23` Phase C `REMOTE_REBOOT` test.
  - Recorded intervention evidence (`REMOTE_REBOOT`, `exit=0`) and post-action verification (`boot_id` change).
- Clarified Phase gating text in `README.md` / `README.ja.md`:
  - `GPIO_REBOOT` under `FREEZE_SUSPECTED` is documented as disabled through Phase C and enabled from Phase D.

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
