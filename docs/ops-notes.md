# Ops Notes (Public Template)

This document defines what can be kept in the public repository and what must stay in a private runbook.

## Keep in Public

- topology and role boundaries
- state/action policy and safety gates
- phased rollout policy
- placeholder-based config examples
- operational checklists without personal identifiers

## Keep Private

- real usernames and account names
- real hostnames, private IP addresses, and tunnel endpoints
- real home paths and SSH key paths
- real known_hosts location
- exact deployment paths and host-local service layout notes
- date-specific operational logs and incident traces

## Placeholder Conventions

Use placeholders in public docs/config examples.

- SSH target: `<agent-user>@<agent-host>`
- Ping target: `<agent-host-or-ip>`
- Controller SSH key path: `<controller-user-home>/.ssh/id_ed25519`
- Controller known_hosts path: `<controller-user-home>/.ssh/known_hosts`
- Deployment root: `<deployment-root>`
- Local facts mirror root: `<local-facts-mirror-root>/remote/`
- Agent export root: `<agent-export-root>`

## Publication Checklist

1. Scan docs/examples for real usernames, IPs, and hostnames.
2. Replace host-local home/deploy paths with placeholders.
3. Keep rationale (`why`) and policy (`what`) unchanged.
4. Move date-specific operations history to private runbook.

## Runtime State Freshness Check Notes

- Canonical state path is configured by `controller_state_path` in controller config.
- If runtime has both `/var/lib/raspi-revive/state/` and `/run/raspi-revive/state/`, verify freshness at the canonical path.
- When checking `/run/.../controller-state.json`, use `stat -L` to follow symlinks.
- Use `journalctl --since "5 min ago"` format; `--since "now-5min"` is not valid.

## Private Runbook Template

Use `docs/private-runbook.template.md` as the base for your private runbook.
Keep the filled runbook in a non-public location.
