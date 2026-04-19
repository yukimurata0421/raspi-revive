#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import time


def copy_atomic(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export runtime facts for controller collection")
    parser.add_argument("--host-heartbeat", required=True)
    parser.add_argument("--gpio-heartbeat", required=True)
    parser.add_argument("--sentinel-stats", required=True)
    parser.add_argument("--sentinel-state", required=True)
    parser.add_argument("--sentinel-events", required=False)
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--interval-sec", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.export_dir)

    while True:
        copy_atomic(Path(args.host_heartbeat), out / "host-heartbeat.json")
        copy_atomic(Path(args.gpio_heartbeat), out / "gpio-heartbeat.json")
        copy_atomic(Path(args.sentinel_stats), out / "sentinel" / "stats.json")
        copy_atomic(Path(args.sentinel_state), out / "sentinel" / "state.json")
        if args.sentinel_events:
            copy_atomic(Path(args.sentinel_events), out / "sentinel" / "events.jsonl")

        if args.once:
            return 0
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    raise SystemExit(main())
