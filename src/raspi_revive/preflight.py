from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from pathlib import Path


RESTART_PREVENT_EXIT_CODE = 75
_PACKAGE_PREFIX = "raspi_revive"
_REQUIRED_MODULES = (
    "raspi_revive.io",
    "raspi_revive.audit",
    "raspi_revive.notifier",
    "raspi_revive.controller",
    "raspi_revive.cli",
)
_REQUIRED_IO_SYMBOLS = (
    "append_jsonl",
    "read_json",
    "write_json_atomic",
)
_WRITABLE_DIR_LABELS = (
    ("controller_state_dir", "controller_state_path"),
    ("observations_log_dir", "observations_log_path"),
    ("events_log_dir", "events_log_path"),
)


def _purge_cached_package_modules() -> dict[str, object]:
    cached: dict[str, object] = {}
    for name in list(sys.modules):
        if name == _PACKAGE_PREFIX or name.startswith(f"{_PACKAGE_PREFIX}."):
            cached[name] = sys.modules.pop(name)
    return cached


def _restore_cached_modules(cached: dict[str, object]) -> None:
    for name in list(sys.modules):
        if name == _PACKAGE_PREFIX or name.startswith(f"{_PACKAGE_PREFIX}."):
            sys.modules.pop(name, None)
    for name, module in cached.items():
        sys.modules[name] = module


def run_runtime_preflight(
    src_dir: Path,
    *,
    config_path: Path | None = None,
    check_runtime_writable: bool = False,
    instantiate_controller: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not src_dir.exists() or not src_dir.is_dir():
        return [f"source directory not found: {src_dir}"]

    src_path = str(src_dir)
    had_path = src_path in sys.path
    if not had_path:
        sys.path.insert(0, src_path)

    cached = _purge_cached_package_modules()
    try:
        importlib.invalidate_caches()
        for module_name in _REQUIRED_MODULES:
            try:
                importlib.import_module(module_name)
            except Exception as exc:
                tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
                errors.append(f"failed to import {module_name}: {tb}")

        controller_config = None
        if not errors:
            io_module = importlib.import_module("raspi_revive.io")
            for symbol in _REQUIRED_IO_SYMBOLS:
                value = getattr(io_module, symbol, None)
                if not callable(value):
                    errors.append(f"raspi_revive.io missing callable: {symbol}")
        if not errors and config_path is not None:
            try:
                config_module = importlib.import_module("raspi_revive.config")
                controller_config = config_module.load_controller_config(config_path)
            except Exception as exc:
                tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
                errors.append(f"failed to load config {config_path}: {tb}")
        if (
            not errors
            and controller_config is not None
            and check_runtime_writable
        ):
            for label, attr_name in _WRITABLE_DIR_LABELS:
                target_path = getattr(controller_config.paths, attr_name).parent
                try:
                    target_path.mkdir(parents=True, exist_ok=True)
                    probe = target_path / ".preflight_write_test"
                    probe.write_text("ok", encoding="utf-8")
                    probe.unlink(missing_ok=True)
                except OSError as exc:
                    errors.append(f"{label} not writable: {target_path} ({exc})")
        if (
            not errors
            and controller_config is not None
            and instantiate_controller
        ):
            try:
                controller_module = importlib.import_module("raspi_revive.controller")
                controller_module.ReviveController(controller_config)
            except Exception as exc:
                tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
                errors.append(f"failed to instantiate ReviveController: {tb}")
    finally:
        _restore_cached_modules(cached)
        if not had_path:
            try:
                sys.path.remove(src_path)
            except ValueError:
                pass

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate raspi-revive runtime import consistency before service restart."
    )
    parser.add_argument(
        "--src-dir",
        default="/opt/raspi-revive/current/src",
        help="Path that contains the raspi_revive package directory.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success output.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional controller TOML path for config/load checks.",
    )
    parser.add_argument(
        "--check-runtime-writable",
        action="store_true",
        help="Verify runtime output directories are writable.",
    )
    parser.add_argument(
        "--instantiate-controller",
        action="store_true",
        help="Instantiate ReviveController after config load.",
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config) if args.config else None
    errors = run_runtime_preflight(
        Path(args.src_dir),
        config_path=config_path,
        check_runtime_writable=args.check_runtime_writable,
        instantiate_controller=args.instantiate_controller,
    )
    if errors:
        print("[preflight] FAILED")
        for line in errors:
            print(f"[preflight] {line}")
        return RESTART_PREVENT_EXIT_CODE

    if not args.quiet:
        suffix = f" config={config_path}" if config_path is not None else ""
        print(f"[preflight] OK src={args.src_dir}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
