# Runtime Layout

Runtime files must not be committed into this repository.

Example runtime layout on controller host:

- `/var/lib/raspi-revive/state/controller-state.json`
- `/var/log/raspi-revive/observations.jsonl`
- `/var/log/raspi-revive/decisions.jsonl`
- `/var/log/raspi-revive/actions.jsonl`

Example agent export area:

- `/var/lib/raspi-revive-agent/host-heartbeat.json`
- `/var/lib/raspi-revive-agent/gpio-heartbeat.json` (written by Pi Zero GPIO observer from physical edge observation)
- `/var/lib/raspi-revive-agent/sentinel/stats.json`
- `/var/lib/raspi-revive-agent/sentinel/state.json`
- `/var/lib/raspi-revive-agent/sentinel/events.jsonl`

## Notes

- Use atomic write (`tmp + rename`) for JSON producers.
- JSONL logs are append-only.
- Keep schema/examples in repo; keep runtime data out.
