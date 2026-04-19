#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import time


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)
    os.replace(tmp, path)


def read_boot_id(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write host heartbeat JSON")
    parser.add_argument("--output", required=True)
    parser.add_argument("--service", default="raspi-revive-host-heartbeat")
    parser.add_argument("--host", default=socket.gethostname())
    parser.add_argument("--boot-id-path", default="/proc/sys/kernel/random/boot_id")
    parser.add_argument("--interval-sec", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    boot_id_path = Path(args.boot_id_path)
    seq = 0

    while True:
        payload = {
            "service": args.service,
            "host": args.host,
            "boot_id": read_boot_id(boot_id_path),
            "seq": seq,
            "monotonic_sec": time.monotonic(),
            "wall_time": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_json(output, payload)
        seq += 1
        if args.once:
            return 0
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    raise SystemExit(main())
