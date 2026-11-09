#!/usr/bin/env python3
"""Sync auto-managed documentation sections from manifest.json.

Updates:
- README.md ``## Currently active`` block (generated from manifest active[])
- README.md ``## Pending first build`` block (generated from manifest active[] unverified entries)
- docs/roadmap.md ``active[] currently holds N plugins`` count

Usage:
    python scripts/sync_docs.py --check   # exit non-zero if out of sync (CI)
    python scripts/sync_docs.py --write   # apply updates in place
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _manifest_helpers import (
    expected_pending_lines,
    expected_readme_lines,
    parse_readme_entry_line,
    read_manifest_active,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
README_PATH = REPO_ROOT / "README.md"
ROADMAP_PATH = REPO_ROOT / "docs" / "roadmap.md"

ACTIVE_HEADING = "## Currently active"
PENDING_HEADING = "## Pending first build"
SNAPSHOT_COUNT_RE = re.compile(r"The (\w+) commit snapshots above passed")
_ORDINAL_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}


def _find_section(lines: list[str], heading: str) -> tuple[int, int]:
    """Return (start, end) line indexes of the section headed by `heading`."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i
            break
    if start is None:
        raise ValueError(f"README missing '{heading}' heading")

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return start, end


def _split_block(block: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Split a section's lines into leading blanks, bullet lines, and trailing lines."""
    leading: list[str] = []
    i = 0
    while i < len(block) and not block[i].strip():
        leading.append(block[i])
        i += 1
    list_lines: list[str] = []
    while i < len(block) and block[i].startswith("- "):
        list_lines.append(block[i])
        i += 1
    trailing = block[i:]
    return leading, list_lines, trailing


def _split_pending_block(block: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Split pending section lines into preamble, bullet lines, and trailing lines."""
    bullets_start = next((i for i, line in enumerate(block) if line.startswith("- ")), None)
    if bullets_start is None:
        return block, [], []
    preamble = block[:bullets_start]
    bullets = []
    trailing = []
    in_trailing = False
    for line in block[bullets_start:]:
        if not in_trailing and line.startswith("- "):
            bullets.append(line)
        else:
            in_trailing = True
            trailing.append(line)
    return preamble, bullets, trailing


def _format_section_block(
    heading_line: str,
    leading_or_preamble: list[str],
    bullets: list[str],
    trailing: list[str],
) -> list[str]:
    """Assemble a markdown section from its heading, preamble, bullets, and trailing lines."""
    heading = heading_line if heading_line.endswith("\n") else f"{heading_line}\n"
    pre = leading_or_preamble if leading_or_preamble else ["\n"]
    formatted_bullets = [f"{b.rstrip()}\n" for b in bullets]
    post = trailing if trailing else ["\n"]
    return [heading, *pre, *formatted_bullets, *post]


def _build_new_block(
    heading_line: str, leading: list[str], expected: list[str], trailing: list[str]
) -> list[str]:
    """Rebuild the currently active section."""
    return _format_section_block(heading_line, leading, expected, trailing)


def _build_new_pending_block(
    heading_line: str, preamble: list[str], expected: list[str], trailing: list[str]
) -> list[str]:
    """Rebuild the pending section preserving preamble narrative and trailing blanks."""
    return _format_section_block(heading_line, preamble, expected, trailing)


def _snapshot_count_repl(match: re.Match, count: int) -> str:
    """Return the replacement for one 'N commit snapshots above passed' match."""
    token = match.group(1)
    if token.isdigit():
        current = int(token)
    else:
        current = _ORDINAL_WORDS.get(token.lower())
    if current == count:
        return match.group(0)
    return f"The {count} commit snapshots above passed"


def _sync_afterword(lines: list[str], count: int) -> list[str]:
    """Rewrite the 'N commit snapshots above passed' count in the trailing narrative."""
    if not lines:
        return lines
    text = "".join(lines)
    new_text, n = SNAPSHOT_COUNT_RE.subn(lambda m: _snapshot_count_repl(m, count), text)
    if n == 0:
        if count:
            raise ValueError(
                "README 'Currently active' afterword missing "
                "'The N commit snapshots above passed' sentence"
            )
        return lines
    return new_text.splitlines(keepends=True)


def _parse_section_entries(lines: list[str], heading: str) -> list[dict]:
    """Extract parsed entry dicts from lines within a section."""
    try:
        start, end = _find_section(lines, heading)
    except ValueError:
        return []
    entries = []
    for line in lines[start + 1 : end]:
        if not line.startswith("- "):
            continue
        parsed = parse_readme_entry_line(line)
        if parsed and parsed.get("name") and parsed.get("version"):
            entries.append(parsed)
    return entries


def extract_readme_notes_and_versions(
    readme_text: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Return (active_versions, pending_versions, pending_notes) by plugin name."""
    lines = readme_text.splitlines(keepends=True)
    active_entries = _parse_section_entries(lines, ACTIVE_HEADING)
    pending_entries = _parse_section_entries(lines, PENDING_HEADING)

    active_versions = {e["name"]: e["version"] for e in active_entries}
    pending_versions = {e["name"]: e["version"] for e in pending_entries}
    pending_notes = {e["name"]: e["note"] for e in pending_entries if e.get("note")}

    return active_versions, pending_versions, pending_notes


def _resolve_single_note(
    name: str,
    new_version: str,
    active_versions: dict[str, str],
    pending_versions: dict[str, str],
    pending_notes: dict[str, str],
) -> str | None:
    """Resolve annotation note for a single unverified plugin."""
    if name in pending_notes:
        note = pending_notes[name]
        old_ver = pending_versions.get(name)
        if note.startswith("_(") and "bumped from" in note and old_ver and old_ver != new_version:
            return f"_(bumped from {old_ver})_"
        return note
    if name in active_versions:
        return f"_(bumped from {active_versions[name]})_"
    return None


def resolve_pending_notes(
    active: list[dict],
    active_versions: dict[str, str],
    pending_versions: dict[str, str],
    pending_notes: dict[str, str],
) -> dict[str, str]:
    """Resolve the appropriate annotation note for each unverified plugin."""
    resolved: dict[str, str] = {}
    for entry in active:
        if entry.get("verified_with"):
            continue
        name = entry.get("name")
        new_version = entry.get("version")
        if not name or not new_version:
            continue
        note = _resolve_single_note(
            name, new_version, active_versions, pending_versions, pending_notes
        )
        if note:
            resolved[name] = note
    return resolved


def sync_readme(
    readme_text: str,
    expected_active: list[str],
    expected_pending: list[str] | None = None,
    snapshot_count: int = 0,
) -> tuple[str, bool]:
    """Return README text with 'Currently active' and 'Pending first build' blocks rebuilt."""
    lines = readme_text.splitlines(keepends=True)
    start, end = _find_section(lines, ACTIVE_HEADING)

    block = lines[start + 1 : end]
    leading, _list_lines, trailing = _split_block(block)
    trailing = _sync_afterword(trailing, snapshot_count)

    heading_line = lines[start]
    new_block = _build_new_block(heading_line, leading, expected_active, trailing)

    new_lines = lines[:start] + new_block + lines[end:]

    if expected_pending is not None:
        try:
            p_start, p_end = _find_section(new_lines, PENDING_HEADING)
            p_block = new_lines[p_start + 1 : p_end]
            p_leading, _p_bullets, p_trailing = _split_pending_block(p_block)
            p_heading_line = new_lines[p_start]
            new_p_block = _build_new_pending_block(
                p_heading_line, p_leading, expected_pending, p_trailing
            )
            new_lines = new_lines[:p_start] + new_p_block + new_lines[p_end:]
        except ValueError:
            pass

    new_text = "".join(new_lines)
    changed = new_text != readme_text
    return new_text, changed


def sync_roadmap(roadmap_text: str, count: int) -> tuple[str, bool]:
    """Return roadmap text with the ``active[]`` plugin count synced to `count`."""
    pattern = re.compile(r"(`manifest\.json` `active\[\]` currently\s+holds )\d+( plugins\.)")
    new_text, n = pattern.subn(
        lambda m: f"{m.group(1)}{count}{m.group(2)}", roadmap_text
    )
    if n == 0:
        raise ValueError(
            "docs/roadmap.md missing 'active[] currently holds N plugins' sentence"
        )
    changed = new_text != roadmap_text
    return new_text, changed


def main() -> int:
    """Entry point: run the sync in --check or --write mode."""
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args()

    active = read_manifest_active(MANIFEST_PATH)
    expected_active = expected_readme_lines(active)
    count = len(active)
    snapshot_count = sum(1 for e in active if e.get("verified_with") and not e.get("tag"))

    readme_text = README_PATH.read_text(encoding="utf-8")
    roadmap_text = ROADMAP_PATH.read_text(encoding="utf-8")

    act_v, pend_v, pend_notes = extract_readme_notes_and_versions(readme_text)
    resolved_notes = resolve_pending_notes(active, act_v, pend_v, pend_notes)
    expected_pending = expected_pending_lines(active, resolved_notes)

    new_readme, readme_changed = sync_readme(
        readme_text, expected_active, expected_pending, snapshot_count
    )
    new_roadmap, roadmap_changed = sync_roadmap(roadmap_text, count)

    changed = readme_changed or roadmap_changed

    if args.write:
        if readme_changed:
            README_PATH.write_text(new_readme, encoding="utf-8")
            print("Updated README.md active and pending sections.")
        if roadmap_changed:
            ROADMAP_PATH.write_text(new_roadmap, encoding="utf-8")
            print("Updated docs/roadmap.md plugin count.")
        if not changed:
            print("Already in sync.")
        return 0

    if changed:
        print("Docs are out of sync with manifest.json.")
        if readme_changed:
            print("  - README.md 'Currently active' or 'Pending first build' section")
        if roadmap_changed:
            print("  - docs/roadmap.md active[] count")
        print("Run: python scripts/sync_docs.py --write")
        return 1
    print("Docs are in sync with manifest.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
