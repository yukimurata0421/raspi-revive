# Private Runbook Template (Non-Public)

Use this file as a private operational runbook template.
Do not commit filled values to public repositories.

## 1. Environment Baseline

- Date:
- Operator:
- Controller host:
- Agent host:
- Deployment root:
- Runtime user:

## 2. Network and Identity (Real Values)

- `ping_target =`
- `ssh_target =`
- Controller SSH identity path:
- Controller known_hosts path:

## 3. Runtime Paths (Real Values)

- Agent export root:
- Controller local facts mirror root:
- Controller config path:
- Controller logs:
- Controller state file:

## 4. Services and Ownership

- Agent host services:
- Controller host services:
- systemd unit override notes:

## 5. Phase Rollout Record

- Current phase:
- `dry_run`:
- Enabled actions:
- Promotion criteria checked:
- Rollback criteria checked:

## 6. Safety Gates (Applied Values)

- `cooldown_seconds =`
- `lockout_window_seconds =`
- `max_actions_per_window =`
- `post_action_verification_wait_seconds =`

## 7. Incident and Recovery Notes

- Incident ID:
- Trigger condition:
- Evidence summary:
- Action executed:
- Post-action verification result:
- Follow-up:

## 8. Change History

| Date | Change | Reason | Evidence |
| --- | --- | --- | --- |
| YYYY-MM-DD |  |  |  |

## 9. Operational Commands (Private)

Document host-specific commands with real paths and service names.

```bash
# example
python3 /opt/raspi-revive/current/targets/raspi-zero-controller/scripts/preflight_runtime_imports.py --src-dir /opt/raspi-revive/current/src --config /etc/raspi-revive/controller.toml --check-runtime-writable --instantiate-controller
./scripts/deploy_controller_release.sh
systemctl status <controller-service> --no-pager
journalctl -u <controller-service> -n 200 --no-pager
```
