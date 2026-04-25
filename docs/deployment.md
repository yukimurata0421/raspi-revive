# Controller Deployment (Atomic Release Switch)

This document defines the controller deployment contract that prevents partial-file rollout incidents.

## Goals

- prevent partial reflection of runtime Python sources
- validate the next release before service restart
- make rollback and post-deploy verification deterministic

## Release Layout

- deployment root: `/opt/raspi-revive`
- immutable release directories: `/opt/raspi-revive/releases/<release-id>/`
- active symlink: `/opt/raspi-revive/current -> /opt/raspi-revive/releases/<release-id>`

Controller service paths are bound to `/opt/raspi-revive/current/...` so release activation is a single atomic symlink switch.

## Deploy Command

Run on the controller host from this repository checkout:

```bash
./scripts/deploy_controller_release.sh
```

## What The Script Enforces

1. Copies `src/` and `targets/` into a new release directory that is not yet active.
2. Runs staged preflight against the new release:
   - import chain check
   - config load check
   - controller constructor check
3. Atomically switches `/opt/raspi-revive/current` via `mv -T`.
4. Reloads systemd and restarts `raspi-revive-controller.service`.
5. Performs post-deploy sanity checks:
   - service is active
   - `controller_state_path` freshness is within threshold
   - no recent `controller_state_write_failed` event
6. Prunes old releases and keeps the newest N generations.

## Key Options

- `--release-id <id>`
- `--config <path>`
- `--service <name>`
- `--deploy-root <path>`
- `--keep-releases <n>`
- `--verify-wait-sec <sec>`
- `--state-max-age-sec <sec>`
- `--skip-install-unit`

## Rollback

Rollback is one symlink switch and restart:

```bash
sudo ln -sfn /opt/raspi-revive/releases/<previous-release-id> /opt/raspi-revive/current.new
sudo mv -Tf /opt/raspi-revive/current.new /opt/raspi-revive/current
sudo systemctl daemon-reload
sudo systemctl restart raspi-revive-controller.service
```

## Operational Rule

Do not deploy by writing files directly into `/opt/raspi-revive/current/src/raspi_revive` or `/opt/raspi-revive/src/raspi_revive`.
Always deploy as a full release snapshot and switch `current` atomically.
