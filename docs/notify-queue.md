# Notify Queue Design

This document summarizes the notification-only extension added to `raspi-revive` without enabling recovery actions.

## Goal

- Keep restart/reboot actions disabled.
- Detect sustained reboot-candidate states.
- Deliver operational alerts through resilient queue-based delivery.

## Trigger Condition

A notify event is enqueued when both conditions are true:

1. `classified_state` is one of:
   - `HOST_DEGRADED`
   - `FREEZE_SUSPECTED`
2. The same incident remains in candidate state for at least `candidate_hold_seconds` (default: 300 seconds).

## Delivery Targets

Each queued event attempts both targets:

1. Remote JSONL append on Pi 5 via SSH (`notify.remote_jsonl_path`)
2. Discord webhook POST

The event is removed from queue only after all enabled targets succeed.

## Retry Policy

- Base retry interval: `queue_retry_interval_seconds` (default: 60s)
- If continuous failure time reaches `backoff_after_seconds` (default: 300s),
  retry delay switches to exponential backoff:
  - `delay = base * backoff_multiplier^n`
  - capped by `backoff_max_seconds`

## Queue Bounds

- Queue has a maximum size (`max_queue_size`).
- Oldest events are dropped on overflow.
- Events older than `max_event_age_seconds` are dropped as expired.

## Runtime Files

- Queue: `notify-queue.json`
- Stats: `notify-stats.json`
- Events: `notify-events.jsonl`

`notify-stats.json` is memory-first. It is flushed periodically by
`stats_flush_interval_seconds` (default: 60s) to reduce write frequency.

These files are controller-side runtime artifacts and must not be committed.

## Security and Secret Handling

- Webhook URL is loaded from environment variable (`notify.discord_webhook_url_env`).
- Avoid hard-coding webhook values in repository files.
- Public layer keeps placeholders/sanitized paths only.

## Code Mapping

- Dispatcher: `src/raspi_revive/notifier.py`
- Config model/loading: `src/raspi_revive/config.py`
- Controller integration: `src/raspi_revive/controller.py`
- Unit tests: `tests/test_notifier.py`

## Validation

The implementation was verified with:

- `ruff check .`
- `pytest -q`
- `python3 -m py_compile ...`
- scenario replay CLI regression run
