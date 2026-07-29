#!/usr/bin/env python3
"""Validate the plugin build manifest and optional upstream tag mappings."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COMMAND_TIMEOUT_SECONDS = 30
REQUIRED_FIELDS = {
    "repo",
    "name",
    "owner",
    "plugin_bin",
    "tag",
    "source_commit",
    "version",
    "nu_version",
    "verified_with",
    "description",
    "tags",
}


def load_manifest(path: Path) -> dict:
    """Load and decode a plugin build manifest from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))


def selected_names(value: str) -> list[str]:
    """Parse a required comma-separated selection into unique package names."""
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names:
        raise ValueError("--only must name at least one active plugin")
    if len(names) != len(set(names)):
        raise ValueError("--only contains duplicate plugin names")
    return names


def expected_targets(manifest: dict, entry: dict) -> list[str]:
    """Validate target declarations and return the targets required for ``entry``."""
    defaults = manifest.get("default_targets")
    if not isinstance(defaults, list) or not defaults or len(defaults) != len(set(defaults)):
        raise ValueError("default_targets must be a non-empty unique list")
    excluded = entry.get("exclude_targets", [])
    if not isinstance(excluded, list) or len(excluded) != len(set(excluded)):
        raise ValueError(f"{entry.get('name', '<unknown>')}: exclude_targets must be unique")
    unknown = sorted(set(excluded) - set(defaults))
    if unknown:
        raise ValueError(
            f"{entry.get('name', '<unknown>')}: unknown excluded targets: {', '.join(unknown)}"
        )
    targets = [target for target in defaults if target not in set(excluded)]
    if not targets:
        raise ValueError(f"{entry.get('name', '<unknown>')}: all targets are excluded")
    return targets


def validate_manifest(manifest: dict, only: list[str] | None = None) -> list[dict]:
    """Validate active entries and return all or the explicitly selected entries."""
    active = manifest.get("active")
    if not isinstance(active, list) or not active:
        raise ValueError("active must be a non-empty list")

    names: set[str] = set()
    for entry in active:
        if not isinstance(entry, dict):
            raise ValueError("active entries must be objects")
        missing = sorted(REQUIRED_FIELDS - set(entry))
        if missing:
            raise ValueError(f"active entry missing fields: {', '.join(missing)}")
        name = entry["name"]
        if not isinstance(name, str) or not name:
            raise ValueError("active entry name must be non-empty")
        if name in names:
            raise ValueError(f"duplicate active plugin name: {name}")
        names.add(name)
        if not SHA_RE.fullmatch(entry["source_commit"]):
            raise ValueError(f"{name}: source_commit must be 40 lowercase hex characters")
        expected_targets(manifest, entry)

    if only is None:
        return active
    missing_names = sorted(set(only) - names)
    if missing_names:
        raise ValueError(f"unknown active plugins: {', '.join(missing_names)}")
    wanted = set(only)
    return [entry for entry in active if entry["name"] in wanted]


def resolve_tag(repo: str, tag: str) -> str:
    """Resolve an upstream annotated or lightweight tag to its commit SHA."""
    url = f"https://github.com/{repo}.git"
    for ref in (f"refs/tags/{tag}^{{}}", f"refs/tags/{tag}"):
        result = subprocess.run(
            ["git", "ls-remote", url, ref],
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise ValueError(f"failed to resolve {repo}@{tag}: {result.stderr.strip()}")
        if result.stdout.strip():
            return result.stdout.split()[0]
    raise ValueError(f"upstream tag not found: {repo}@{tag}")


def verify_upstream(entries: list[dict]) -> None:
    """Require every entry's upstream tag to match its immutable source commit."""
    for entry in entries:
        actual = resolve_tag(entry["repo"], entry["tag"])
        expected = entry["source_commit"]
        if actual != expected:
            raise ValueError(
                f"{entry['name']}: {entry['tag']} resolves to {actual}, expected {expected}"
            )
        print(f"OK: {entry['repo']}@{entry['tag']} -> {expected}")


def main(argv: list[str] | None = None) -> int:
    """Validate a manifest and optionally verify upstream tag provenance."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("manifest.json"))
    parser.add_argument("--only", default=None)
    parser.add_argument("--verify-upstream", action="store_true")
    args = parser.parse_args(argv)
    try:
        only = selected_names(args.only) if args.only is not None else None
        entries = validate_manifest(load_manifest(args.manifest), only)
        if args.verify_upstream:
            verify_upstream(entries)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: validated {len(entries)} active plugin(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
