#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def run_command(cmd: list[str]) -> bool:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def run_capture(cmd: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def resolve_line(pin: int) -> tuple[str, int] | None:
    for line_name in (f"GPIO{pin}", f"gpio{pin}"):
        out = run_capture(["gpiofind", line_name])
        if not out:
            continue
        parts = out.replace("/dev/", "").split()
        if len(parts) != 2:
            continue
        chip, offset = parts
        if not chip.startswith("gpiochip"):
            continue
        try:
            return chip, int(offset)
        except ValueError:
            continue
    return None


def pulse_with_pinctrl(pin: int, hold_ms: int) -> bool:
    if not run_command(["pinctrl", "set", str(pin), "op", "dl"]):
        return False
    if not run_command(["pinctrl", "set", str(pin), "op", "dh"]):
        return False
    time.sleep(max(0.0, hold_ms / 1000.0))
    return run_command(["pinctrl", "set", str(pin), "op", "dl"])


def pulse_with_gpiod(pin: int, hold_ms: int) -> bool:
    resolved = resolve_line(pin)
    if resolved is None:
        return False
    chip, offset = resolved
    if not run_command(["gpioset", chip, f"{offset}=1"]):
        return False
    time.sleep(max(0.0, hold_ms / 1000.0))
    return run_command(["gpioset", chip, f"{offset}=0"])


def pulse_gpio(pin: int, hold_ms: int, backend: str) -> bool:
    if backend == "pinctrl":
        return pulse_with_pinctrl(pin, hold_ms)
    if backend == "gpiod":
        return pulse_with_gpiod(pin, hold_ms)
    return False


def get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit GPIO heartbeat pulses")
    parser.add_argument("--edge-output", required=True, help="JSON mirror for last edge timestamp")
    parser.add_argument("--interval-sec", type=float, default=get_env_float("HEARTBEAT_INTERVAL_SEC", 2.0))
    parser.add_argument("--pulse-hold-ms", type=int, default=get_env_int("GPIO_PULSE_HOLD_MS", 100))
    parser.add_argument("--pin", type=int, default=get_env_int("GPIO_PIN", 17))
    parser.add_argument(
        "--backend",
        choices=("pinctrl", "gpiod"),
        default=os.getenv("GPIO_BACKEND", "pinctrl"),
        help="GPIO backend used for pulse output",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.edge_output)
    existing = read_json(out)
    last_edge = None
    if isinstance(existing, dict):
        existing_last = existing.get("last_edge_wall_time")
        if isinstance(existing_last, str):
            last_edge = existing_last

    while True:
        emitted = True
        pulse_error: str | None = None
        if not args.dry_run:
            emitted = pulse_gpio(args.pin, args.pulse_hold_ms, args.backend)
            if not emitted:
                pulse_error = "pulse_failed"

        if emitted:
            last_edge = datetime.now(timezone.utc).isoformat()

        payload = {
            "service": "raspi-revive-gpio-heartbeat",
            "source": "gpio_emitter",
            "last_edge_wall_time": last_edge,
            "pulse_pin": args.pin,
            "pulse_hold_ms": args.pulse_hold_ms,
            "backend": args.backend,
            "dry_run": args.dry_run,
            "pulse_emitted": emitted,
            "emitter_status": "ok" if emitted else "error",
            "last_emit_wall_time": datetime.now(timezone.utc).isoformat(),
            "error": pulse_error,
        }
        atomic_write_json(out, payload)

        if args.once:
            return 0 if emitted or args.dry_run else 1
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    raise SystemExit(main())
