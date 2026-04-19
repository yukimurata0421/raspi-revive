from __future__ import annotations

import argparse

from .config import load_controller_config
from .scenario_harness import (
    assert_scenario_expectations,
    load_scenario_definitions_from_dir,
    replay_definition,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay validation scenarios from JSON fixtures")
    parser.add_argument("--config", required=True, help="Path to controller TOML config")
    parser.add_argument("--scenario-dir", required=True, help="Directory that contains scenario JSON fixtures")
    parser.add_argument(
        "--scenario-id",
        action="append",
        default=[],
        help="Optional scenario id filter. Can be specified multiple times.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print each step result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_controller_config(args.config)
    definitions = load_scenario_definitions_from_dir(args.scenario_dir)

    selected = definitions
    if args.scenario_id:
        wanted = set(args.scenario_id)
        selected = [x for x in definitions if x.scenario_id in wanted]

    if not selected:
        print("No scenarios selected.")
        return 2

    failures: list[str] = []

    for scenario in selected:
        results = replay_definition(config, scenario)
        try:
            assert_scenario_expectations(scenario.steps, results)
        except AssertionError as exc:
            failures.append(f"{scenario.scenario_id}: {exc}")
            print(f"[FAIL] {scenario.scenario_id}: {exc}")
            continue

        print(f"[PASS] {scenario.scenario_id} ({len(results)} steps)")
        if args.verbose:
            for item in results:
                print(
                    f"  - {item.step_id}: state={item.actual_state} "
                    f"action={item.actual_action.value} incident={item.incident_key}"
                )

    if failures:
        print(f"{len(failures)} scenario(s) failed.")
        return 1

    print(f"All {len(selected)} scenario(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
