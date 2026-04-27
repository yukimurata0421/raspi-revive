# Changelog

All notable changes to this project are documented in this file.

## 2026-04-27

### Remote reboot notification routing

- Added dedicated notify config fields for remote reboot execution notifications:
  - `notify.remote_reboot_discord_webhook_url`
  - `notify.remote_reboot_discord_webhook_url_env`
- Added immediate Discord notification dispatch when `REMOTE_REBOOT` is actually executed.
- Switched `REMOTE_REBOOT` notification to queue-based delivery with the same retry policy as candidate alerts:
  - every minute up to 5 minutes
  - exponential backoff after 5 minutes
- Added notify event records for dedicated reboot notification delivery:
  - `remote_reboot_notify_sent`
  - `remote_reboot_notify_failed`
- Added explicit `User-Agent` header on Discord webhook POST to avoid `HTTP 403 (error code 1010)` rejections.
- Updated config templates and notify docs/README (JA/EN) to include the dedicated webhook setting.
- Added regression tests for dedicated remote reboot notify dispatch and env-driven config loading.
- Changed runtime cooldown from `120` to `300` seconds as an operational stability choice after reboot interventions.

## 2026-04-25

### Telemetry diagnostics hardening

- Added exporter self-health output: `export/meta.json` now records:
  - `last_export_attempt_ts`
  - `last_export_success_ts`
  - `last_error`
  - source file mtimes per input (`source_mtime.*`)
- Switched exporter behavior to partial export:
  - each source file is copied independently
  - missing/stale files no longer block exporting healthy inputs
  - per-input copy result is recorded in `meta.json`
- Added controller-side telemetry failure split for `TELEMETRY_PIPELINE_FAILURE`:
  - `TELEMETRY_SOURCE_FAILURE`
  - `TELEMETRY_EXPORT_FAILURE`
  - `TELEMETRY_PULL_FAILURE`
- Included failure reason code in incident key and decision logs to improve alert/action targeting.
- Added regression tests for exporter meta/partial export and telemetry failure reason splitting.

### Controller state persistence heartbeat and deployment recovery

- Added intervention evidence snapshots:
  - `intervention-evidence/intervention_evidence_*.json` (captured before action execution)
  - `incident-summary.json` (latest incident/decision read model)
  - `controller-stats.json` (runtime state/action counters)
- Added runtime-state persistence heartbeat fields:
  - `last_loop_ts`
  - `last_observation_ts`
  - `last_state_write_ts`
- Added structural metadata fields:
  - `schema_version`
  - `code_version`
- Added explicit structural-vs-heartbeat split using `HEARTBEAT_FIELDS` and `to_structural_dict()`.
- Updated persistence logic to write when any of the following is true:
  - structural state changed,
  - state file is missing,
  - heartbeat write interval elapsed (`30s`).
- Added lifecycle events for state persistence anomalies:
  - `controller_state_write_failed`
  - `controller_state_write_stale`
- Added `StartLimitIntervalSec=300` and `StartLimitBurst=5` to the controller unit (`[Unit]`) to bound rapid restart loops.
- Added a late-order unit drop-in override so the guard remains effective even when older drop-ins set `StartLimitIntervalSec=0`.
- Added repo-managed drop-in template:
  - `targets/raspi-zero-controller/systemd/raspi-revive-controller.service.d/40-start-limit.conf`
- Added regression tests for heartbeat write timing, structural-only diff behavior, and stale-write event emission.
- Applied the changes on the controller host and verified:
  - service recovery after a transient deploy mismatch,
  - active steady run,
  - state file freshness progression by heartbeat cadence.

## 2026-04-23

### Heartbeat progression gate hardening

- Promoted `host_heartbeat_progressing` from note-only evidence to an enforced decision gate.
- Added `fresh-but-not-progressing` + `sentinel stale` classification path to `TELEMETRY_PIPELINE_FAILURE` to prevent false `RESTART_SENTINEL` escalation.
- Tightened telemetry baseline and reconciliation checks so `REMOTE_REBOOT` requires progressing host heartbeat evidence.
- Replaced scenario override `setattr` mutation with typed `dataclasses.replace` updates and explicit unknown-key validation.
- Added regression tests for non-progressing heartbeat behavior and invalid scenario override keys.
- Updated README and state-machine/rollout docs (JA/EN) to align with the enforced gate.

### Config flexibility and runtime safety extensions

- Added config-driven phase gate:
  - `actions.enabled_phases` supports explicit phase allowlists (for example `["A","B","C"]`).
  - Legacy action booleans remain supported and are still enforced.
- Added extensible notify provider interface:
  - `[[notify.providers]]` with `kind` (`ssh_append`, `discord_webhook`) and per-provider settings.
  - Legacy notify fields remain backward-compatible.
- Added runtime JSONL rotation:
  - New `[logs]` section (`max_log_size_mb`, `rotation_count`), default `10MB` and `3` rotations.
  - Applied to controller audit logs and notify event logs.
- Added regression coverage for provider parsing and JSONL rotation behavior.

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
