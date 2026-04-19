# Runtime Layout

runtime ファイルはこのリポジトリにコミットしません。

controller 側の例:

- `/var/lib/raspi-revive/state/controller-state.json`
- `/var/log/raspi-revive/observations.jsonl`
- `/var/log/raspi-revive/decisions.jsonl`
- `/var/log/raspi-revive/actions.jsonl`

agent export 側の例:

- `/var/lib/raspi-revive-agent/host-heartbeat.json`
- `/var/lib/raspi-revive-agent/gpio-heartbeat.json`（Pi Zero 側 GPIO observer が物理 edge 観測から更新）
- `/var/lib/raspi-revive-agent/sentinel/stats.json`
- `/var/lib/raspi-revive-agent/sentinel/state.json`
- `/var/lib/raspi-revive-agent/sentinel/events.jsonl`

## Notes

- JSON producer は atomic write（tmp + rename）を使う
- JSONL ログは append-only
- repo には schema/example だけ置き、runtime data は置かない
