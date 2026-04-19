#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import re
from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]

TEXT_FILE_EXTENSIONS = {
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".jsonl",
    ".py",
    ".txt",
    ".service",
    ".env",
    "",
}

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}

# Public docs/config should not contain these private-environment literals.
FORBIDDEN_LITERALS = (
    "yuki@",
    "/home/yuki/",
    "/home/pi5-guard/",
)

SSH_IDENTITY_PATH_RE = re.compile(r"/home/[^\s\"']+/.ssh/id_[A-Za-z0-9_-]+")
KNOWN_HOSTS_PATH_RE = re.compile(r"/home/[^\s\"']+/.ssh/known_hosts")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

SCAN_ROOTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.ja.md",
    REPO_ROOT / "docs",
    REPO_ROOT / "targets",
    REPO_ROOT / "examples",
)

RUNTIME_ARTIFACTS = (
    "observations.jsonl",
    "decisions.jsonl",
    "actions.jsonl",
    "controller-state.json",
)


def _is_text_file(path: Path) -> bool:
    return path.suffix in TEXT_FILE_EXTENSIONS


def _iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if _is_text_file(path):
            yield path


def _is_private_ipv4(candidate: str) -> bool:
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return isinstance(parsed, ipaddress.IPv4Address) and parsed.is_private


def _check_private_runbook_presence(errors: list[str]) -> None:
    docs_dir = REPO_ROOT / "docs"
    if not docs_dir.exists():
        return
    for path in docs_dir.glob("private-runbook*.md"):
        if path.name in {"private-runbook.template.md", "private-runbook.template.ja.md"}:
            continue
        errors.append(
            f"{path.relative_to(REPO_ROOT)}: private runbook concrete file should not exist in public repo"
        )


def _check_runtime_artifacts_presence(errors: list[str]) -> None:
    for artifact in RUNTIME_ARTIFACTS:
        matches = list(REPO_ROOT.rglob(artifact))
        for path in matches:
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: runtime artifact should not exist in public repo"
            )


def _check_phase_config_consistency(errors: list[str]) -> None:
    phase_paths = sorted((REPO_ROOT / "targets/raspi-zero-controller/config/phases").glob("controller.phase-*.toml"))
    if len(phase_paths) < 2:
        return
    baseline_path = phase_paths[0]
    with baseline_path.open("rb") as f:
        baseline = tomllib.load(f)
    baseline_without_actions = {k: v for k, v in baseline.items() if k != "actions"}

    for path in phase_paths[1:]:
        with path.open("rb") as f:
            payload = tomllib.load(f)
        payload_without_actions = {k: v for k, v in payload.items() if k != "actions"}
        if payload_without_actions != baseline_without_actions:
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: phase config drift detected outside [actions] section"
            )


def main() -> int:
    errors: list[str] = []

    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in _iter_files(root):
            rel = path.relative_to(REPO_ROOT)
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for literal in FORBIDDEN_LITERALS:
                if literal in text:
                    errors.append(f"{rel}: contains forbidden literal '{literal}'")

            for match in SSH_IDENTITY_PATH_RE.finditer(text):
                errors.append(f"{rel}: contains concrete SSH identity path '{match.group(0)}'")
            for match in KNOWN_HOSTS_PATH_RE.finditer(text):
                errors.append(f"{rel}: contains concrete known_hosts path '{match.group(0)}'")

            for match in IPV4_RE.finditer(text):
                ip_text = match.group(0)
                if _is_private_ipv4(ip_text):
                    errors.append(f"{rel}: contains private IPv4 '{ip_text}'")

    _check_private_runbook_presence(errors)
    _check_runtime_artifacts_presence(errors)
    _check_phase_config_consistency(errors)

    if errors:
        print("[FAIL] public safety check")
        for line in sorted(set(errors)):
            print(f" - {line}")
        return 1

    print("[PASS] public safety check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
