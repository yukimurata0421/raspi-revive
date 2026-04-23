from __future__ import annotations

from pathlib import Path

from raspi_revive.io import append_jsonl_with_rotation


def test_append_jsonl_with_rotation(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"

    # Keep threshold tiny so a couple of writes trigger rotation.
    for idx in range(8):
        append_jsonl_with_rotation(
            path,
            {"idx": idx, "message": "x" * 32},
            max_bytes=120,
            rotation_count=2,
        )

    assert path.exists()
    assert (tmp_path / "events.jsonl.1").exists()
    # Rotation count is capped at 2 backups.
    assert (tmp_path / "events.jsonl.3").exists() is False
