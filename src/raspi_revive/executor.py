from __future__ import annotations

from dataclasses import dataclass
import subprocess

from .config import ActionConfig
from .models import RecoveryAction


@dataclass(slots=True)
class ActionExecutionResult:
    executed: bool
    success: bool
    command: list[str]
    detail: str


@dataclass(slots=True)
class ActionExecutor:
    config: ActionConfig

    def run_action(self, action: RecoveryAction) -> ActionExecutionResult:
        cmd = self._command_for(action)
        if action == RecoveryAction.NO_ACTION:
            return ActionExecutionResult(executed=False, success=True, command=[], detail="no action")

        if self.config.dry_run:
            return ActionExecutionResult(
                executed=False,
                success=True,
                command=cmd,
                detail="dry-run enabled",
            )

        if not cmd:
            return ActionExecutionResult(executed=False, success=False, command=cmd, detail="command not configured")

        try:
            proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except OSError as exc:
            return ActionExecutionResult(executed=True, success=False, command=cmd, detail=f"exec error: {exc}")

        success = proc.returncode == 0
        detail = proc.stdout.strip() or proc.stderr.strip() or f"exit={proc.returncode}"
        return ActionExecutionResult(executed=True, success=success, command=cmd, detail=detail)

    def _command_for(self, action: RecoveryAction) -> list[str]:
        if action == RecoveryAction.RESTART_SENTINEL:
            return self.config.restart_sentinel_cmd
        if action == RecoveryAction.REMOTE_REBOOT:
            return self.config.remote_reboot_cmd
        if action == RecoveryAction.GPIO_REBOOT:
            return self.config.gpio_reboot_cmd
        if action == RecoveryAction.POWER_BUTTON_PULSE:
            return self.config.power_button_pulse_cmd
        return []
