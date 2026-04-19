from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
EMITTER_PATH = REPO_ROOT / "targets/raspi-5-agent/scripts/emit_gpio_heartbeat.py"
OBSERVER_PATH = REPO_ROOT / "targets/raspi-zero-controller/scripts/observe_gpio_heartbeat.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_emitter_parse_args_uses_env_defaults(monkeypatch, tmp_path: Path) -> None:
    mod = _load_module(EMITTER_PATH, "emit_gpio_heartbeat_args")
    out = tmp_path / "gpio-heartbeat.json"
    monkeypatch.setenv("GPIO_PIN", "22")
    monkeypatch.setenv("GPIO_PULSE_HOLD_MS", "150")
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SEC", "1.5")
    monkeypatch.setenv("GPIO_BACKEND", "pinctrl")
    monkeypatch.setattr(
        sys,
        "argv",
        ["emit_gpio_heartbeat.py", "--edge-output", str(out)],
    )
    args = mod.parse_args()
    assert args.pin == 22
    assert args.pulse_hold_ms == 150
    assert args.interval_sec == 1.5
    assert args.backend == "pinctrl"


def test_emitter_once_dry_run_writes_mirror(monkeypatch, tmp_path: Path) -> None:
    mod = _load_module(EMITTER_PATH, "emit_gpio_heartbeat_once")
    out = tmp_path / "gpio-heartbeat.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "emit_gpio_heartbeat.py",
            "--edge-output",
            str(out),
            "--once",
            "--dry-run",
            "--pin",
            "17",
        ],
    )
    rc = mod.main()
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["service"] == "raspi-revive-gpio-heartbeat"
    assert payload["source"] == "gpio_emitter"
    assert payload["pulse_pin"] == 17
    assert payload["dry_run"] is True
    assert payload["pulse_emitted"] is True
    assert isinstance(payload["last_edge_wall_time"], str)


def test_observer_parse_args_uses_env_defaults(monkeypatch) -> None:
    mod = _load_module(OBSERVER_PATH, "observe_gpio_heartbeat_args")
    monkeypatch.setenv("GPIO_OBSERVER_MIRROR_PATH", "/tmp/test-gpio-heartbeat.json")
    monkeypatch.setenv("GPIO_OBSERVER_PIN", "17")
    monkeypatch.setenv("GPIO_OBSERVER_PULL", "down")
    monkeypatch.setenv("GPIO_OBSERVER_INTERVAL_SEC", "0.25")
    monkeypatch.setenv("GPIO_OBSERVER_BACKEND", "pinctrl")
    monkeypatch.setattr(sys, "argv", ["observe_gpio_heartbeat.py"])
    args = mod.parse_args()
    assert args.mirror_output == "/tmp/test-gpio-heartbeat.json"
    assert args.pin == 17
    assert args.pull == "down"
    assert args.interval_sec == 0.25
    assert args.backend == "pinctrl"


def test_observer_once_dry_run_writes_mirror(monkeypatch, tmp_path: Path) -> None:
    mod = _load_module(OBSERVER_PATH, "observe_gpio_heartbeat_once")
    out = tmp_path / "gpio-heartbeat.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "observe_gpio_heartbeat.py",
            "--mirror-output",
            str(out),
            "--once",
            "--dry-run",
            "--pin",
            "17",
            "--pull",
            "down",
        ],
    )
    rc = mod.main()
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["service"] == "raspi-revive-gpio-observer"
    assert payload["source"] == "gpio_observer"
    assert payload["observer_status"] == "dry_run"
    assert payload["input_pin"] == 17
    assert payload["pull"] == "down"
    assert isinstance(payload["last_edge_wall_time"], str)


def test_observer_recovers_from_malformed_mirror_json(monkeypatch, tmp_path: Path) -> None:
    mod = _load_module(OBSERVER_PATH, "observe_gpio_heartbeat_malformed")
    out = tmp_path / "gpio-heartbeat.json"
    out.write_text("{bad-json", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "observe_gpio_heartbeat.py",
            "--mirror-output",
            str(out),
            "--once",
            "--dry-run",
        ],
    )
    rc = mod.main()
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"] == "gpio_observer"
    assert "last_edge_wall_time" in payload
