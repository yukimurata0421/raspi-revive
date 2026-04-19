from __future__ import annotations

import argparse
import time

from .config import load_controller_config
from .controller import ReviveController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="raspi-revive controller")
    parser.add_argument("--config", required=True, help="Path to controller TOML config")
    parser.add_argument("--once", action="store_true", help="Run a single cycle")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_controller_config(args.config)
    controller = ReviveController(config)

    if args.once:
        controller.run_cycle()
        return 0

    while True:
        controller.run_cycle()
        time.sleep(config.loop.cycle_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
