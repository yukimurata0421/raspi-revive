from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os


def read_json(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, separators=(",", ":"))
    os.replace(tmp, path)


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")


def append_jsonl_with_rotation(
    path: Path,
    payload: dict,
    *,
    max_bytes: int,
    rotation_count: int,
) -> None:
    _rotate_jsonl_if_needed(path, max_bytes=max_bytes, rotation_count=rotation_count)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")


def _rotate_jsonl_if_needed(path: Path, *, max_bytes: int, rotation_count: int) -> None:
    if max_bytes <= 0 or rotation_count <= 0:
        return
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
    except OSError:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    for index in range(rotation_count, 0, -1):
        src = path.with_suffix(path.suffix + f".{index}")
        dst = path.with_suffix(path.suffix + f".{index + 1}")
        if src.exists():
            if index == rotation_count:
                src.unlink(missing_ok=True)
            else:
                os.replace(src, dst)
    if path.exists():
        os.replace(path, path.with_suffix(path.suffix + ".1"))


def parse_iso8601(ts: str) -> datetime | None:
    try:
        normalized = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
