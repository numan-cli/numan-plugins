#!/usr/bin/env python3
"""Shared manifest.json helpers for documentation consistency checks.

Used by both check_repo_consistency.py and sync_docs.py so the two CI checks
cannot silently disagree about what "in sync" means.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ENTRY_LINE_RE = re.compile(
    r"^- `(?P<repo>[^`]+)` @ `(?P<tag>[^`]+)` → `(?P<name>[^`]+)` (?P<version>\S+)(?:\s+(?P<note>.*))?$"
)


def read_manifest_active(path: Path) -> list[dict]:
    """Return manifest.json ``active[]`` as a list, raising on a non-list shape."""
    data = json.loads(path.read_text(encoding="utf-8"))
    active = data.get("active")
    if not isinstance(active, list):
        raise ValueError(f"{path}: active must be a list")
    return active


def entry_tag_display(entry: dict) -> str:
    """Return the display tag for an entry (either tag or 'commit <sha7>')."""
    tag = entry.get("tag")
    if tag:
        return tag
    source_commit = entry.get("source_commit")
    if source_commit:
        return f"commit {source_commit[:7]}"
    raise ValueError(f"Entry missing both 'tag' and 'source_commit': {entry}")


def format_entry_line(entry: dict, note: str | None = None) -> str:
    """Format one README entry line: - `repo` @ `tag_display` → `name` version [note]."""
    tag_display = entry_tag_display(entry)
    repo = entry.get("repo")
    name = entry.get("name")
    version = entry.get("version")
    if not repo or not name or not version:
        raise ValueError(f"Entry missing required field(s) (repo/name/version): {entry}")
    line = f"- `{repo}` @ `{tag_display}` → `{name}` {version}"
    if note:
        line += f" {note.strip()}"
    return line


def parse_readme_entry_line(line: str) -> dict[str, str | None] | None:
    """Parse one README bullet line into repo, tag, name, version, and optional note."""
    m = ENTRY_LINE_RE.match(line.strip())
    if not m:
        return None
    return {
        "repo": m.group("repo"),
        "tag": m.group("tag"),
        "name": m.group("name"),
        "version": m.group("version"),
        "note": m.group("note").strip() if m.group("note") else None,
    }


def expected_readme_lines(active: list[dict]) -> list[str]:
    """Return the README 'Currently active' bullet lines for ``active[]``.

    Entries with an empty ``verified_with`` belong in the "Pending" section,
    not "Currently active", so they are skipped. Malformed entries raise a
    clear ValueError rather than an opaque KeyError traceback.
    """
    return [format_entry_line(entry) for entry in active if entry.get("verified_with")]


def expected_pending_lines(
    active: list[dict],
    existing_notes: dict[str, str] | None = None,
) -> list[str]:
    """Return the README 'Pending first build' bullet lines for ``active[]``.

    Entries with a non-empty ``verified_with`` belong in 'Currently active',
    so only unverified entries are included.
    """
    notes = existing_notes or {}
    return [
        format_entry_line(entry, note=notes.get(entry.get("name", "")))
        for entry in active
        if not entry.get("verified_with")
    ]
