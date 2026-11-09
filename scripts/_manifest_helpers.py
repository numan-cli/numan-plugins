#!/usr/bin/env python3
"""Shared manifest.json helpers for documentation consistency checks.

Used by both check_repo_consistency.py and sync_docs.py so the two CI checks
cannot silently disagree about what "in sync" means.
"""

from __future__ import annotations

import json
from pathlib import Path


def read_manifest_active(path: Path) -> list[dict]:
    """Return manifest.json ``active[]`` as a list, raising on a non-list shape."""
    data = json.loads(path.read_text(encoding="utf-8"))
    active = data.get("active")
    if not isinstance(active, list):
        raise ValueError(f"{path}: active must be a list")
    return active


def expected_readme_lines(active: list[dict]) -> list[str]:
    """Return the README 'Currently active' bullet lines for ``active[]``.

    Entries with an empty ``verified_with`` belong in the "Pending" section,
    not "Currently active", so they are skipped. Malformed entries raise a
    clear ValueError rather than an opaque KeyError traceback.
    """
    lines: list[str] = []
    for entry in active:
        if not entry.get("verified_with"):
            continue
        tag_display = entry.get("tag")
        source_commit = entry.get("source_commit")
        if not tag_display and not source_commit:
            raise ValueError(f"Entry missing both 'tag' and 'source_commit': {entry}")
        if not tag_display:
            tag_display = f"commit {source_commit[:7]}"
        repo = entry.get("repo")
        name = entry.get("name")
        version = entry.get("version")
        if not repo or not name or not version:
            raise ValueError(f"Entry missing required field(s) (repo/name/version): {entry}")
        lines.append(f"- `{repo}` @ `{tag_display}` → `{name}` {version}")
    return lines