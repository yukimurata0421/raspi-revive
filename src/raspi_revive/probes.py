from __future__ import annotations

from pathlib import Path
import subprocess

from .io import read_json


def file_age_seconds(path: Path, now_ts: float) -> float | None:
    if not path.exists():
        return None
    return max(0.0, now_ts - path.stat().st_mtime)


def run_bool_command(cmd: list[str], timeout_sec: float) -> bool:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_sec,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return proc.returncode == 0


def ping_probe(target: str, timeout_sec: float, retries: int) -> bool:
    for _ in range(max(1, retries)):
        if run_bool_command(["ping", "-c", "1", "-W", str(int(timeout_sec)), target], timeout_sec + 0.5):
            return True
    return False


def ssh_probe(target: str, timeout_sec: float, retries: int, options: list[str]) -> bool:
    base = ["ssh", *options, "-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(timeout_sec)}", target, "true"]
    for _ in range(max(1, retries)):
        if run_bool_command(base, timeout_sec + 1.0):
            return True
    return False


def read_host_heartbeat(path: Path) -> dict | None:
    return read_json(path)
