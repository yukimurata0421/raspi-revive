#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
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


def resolve_line(pin: int, chip_hint: str | None = None) -> tuple[str, int] | None:
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
    if chip_hint:
        # Fallback for environments without gpiofind; Pi GPIO offsets map to BCM IDs.
        return chip_hint, pin
    return None


def configure_input(pin: int, pull: str, backend: str, gpiod_chip: str) -> bool:
    if backend == "pinctrl":
        mode = {"down": "pd", "up": "pu", "off": "pn"}[pull]
        return run_command(["pinctrl", "set", str(pin), "ip", mode])
    if backend == "gpiod":
        resolved = resolve_line(pin, chip_hint=gpiod_chip)
        if resolved is None:
            return False
        chip, offset = resolved
        bias_flag = {"down": "pull-down", "up": "pull-up", "off": "disabled"}[pull]
        return run_capture(["gpioget", "-c", chip, "--bias", bias_flag, "--numeric", str(offset)]) is not None
    return False


def read_level_pinctrl(pin: int) -> int | None:
    out = run_capture(["pinctrl", "get", str(pin)])
    if not out:
        return None
    normalized = out.lower()
    if re.search(r"\bhi\b", normalized):
        return 1
    if re.search(r"\blo\b", normalized):
        return 0
    if "level=1" in normalized:
        return 1
    if "level=0" in normalized:
        return 0
    return None


def read_level_gpiod(pin: int, pull: str, gpiod_chip: str) -> int | None:
    resolved = resolve_line(pin, chip_hint=gpiod_chip)
    if resolved is None:
        return None
    chip, offset = resolved
    bias_flag = {"down": "pull-down", "up": "pull-up", "off": "disabled"}[pull]
    out = run_capture(["gpioget", "-c", chip, "--bias", bias_flag, "--numeric", str(offset)])
    if out is None:
        return None
    token = out.strip().split()[-1]
    if token in {"0", "1"}:
        return int(token)
    return None


def read_level(pin: int, pull: str, backend: str, gpiod_chip: str) -> int | None:
    if backend == "pinctrl":
        return read_level_pinctrl(pin)
    if backend == "gpiod":
        return read_level_gpiod(pin, pull, gpiod_chip)
    return None


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
    parser = argparse.ArgumentParser(description="Observe GPIO heartbeat and write mirror JSON")
    parser.add_argument(
        "--mirror-output",
        default=os.getenv("GPIO_OBSERVER_MIRROR_PATH", "/var/lib/raspi-revive-agent/gpio-heartbeat.json"),
        help="Output path for heartbeat mirror JSON",
    )
    parser.add_argument("--pin", type=int, default=get_env_int("GPIO_OBSERVER_PIN", 17))
    parser.add_argument(
        "--pull",
        choices=("down", "up", "off"),
        default=os.getenv("GPIO_OBSERVER_PULL", "down"),
        help="Input bias for observer pin",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=get_env_float("GPIO_OBSERVER_INTERVAL_SEC", 0.2),
    )
    parser.add_argument(
        "--backend",
        choices=("pinctrl", "gpiod"),
        default=os.getenv("GPIO_OBSERVER_BACKEND", "pinctrl"),
        help="GPIO backend used for observer input",
    )
    parser.add_argument(
        "--gpiod-chip",
        default=os.getenv("GPIO_OBSERVER_GPIOD_CHIP", "gpiochip0"),
        help="GPIO chip used when backend=gpiod and gpiofind is unavailable",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.mirror_output)

    existing = read_json(output)
    last_edge_wall_time = None
    if isinstance(existing, dict):
        edge = existing.get("last_edge_wall_time")
        if isinstance(edge, str):
            last_edge_wall_time = edge

    last_level: int | None = None
    if not args.dry_run and not configure_input(args.pin, args.pull, args.backend, args.gpiod_chip):
        payload = {
            "service": "raspi-revive-gpio-observer",
            "source": "gpio_observer",
            "observer_status": "config_error",
            "last_edge_wall_time": last_edge_wall_time,
            "last_read_wall_time": datetime.now(timezone.utc).isoformat(),
            "input_pin": args.pin,
            "pull": args.pull,
            "backend": args.backend,
            "gpiod_chip": args.gpiod_chip,
            "last_level": None,
            "dry_run": args.dry_run,
        }
        atomic_write_json(output, payload)
        return 1

    while True:
        now_wall = datetime.now(timezone.utc).isoformat()
        edge_seen = False
        status = "ok"
        level: int | None

        if args.dry_run:
            level = 1 if last_level in (None, 0) else 0
        else:
            level = read_level(args.pin, args.pull, args.backend, args.gpiod_chip)

        if level is None:
            status = "read_error"
        else:
            if last_level is not None and level != last_level:
                edge_seen = True
                last_edge_wall_time = now_wall
            if last_level is None and args.dry_run:
                edge_seen = True
                last_edge_wall_time = now_wall
            last_level = level

        payload = {
            "service": "raspi-revive-gpio-observer",
            "source": "gpio_observer",
            "observer_status": status if not args.dry_run else "dry_run",
            "last_edge_wall_time": last_edge_wall_time,
            "last_read_wall_time": now_wall,
            "input_pin": args.pin,
            "pull": args.pull,
            "backend": args.backend,
            "gpiod_chip": args.gpiod_chip,
            "last_level": last_level,
            "edge_seen": edge_seen,
            "dry_run": args.dry_run,
        }
        atomic_write_json(output, payload)

        if args.once:
            return 0 if status == "ok" or args.dry_run else 1
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    raise SystemExit(main())
