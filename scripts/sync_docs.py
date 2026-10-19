#!/usr/bin/env python3
"""Sync auto-managed documentation sections from manifest.json.

Updates:
- README.md ``## Currently active`` block (generated from manifest active[])
- docs/roadmap.md ``active[] currently holds N plugins`` count

Usage:
    python scripts/sync_docs.py --check   # exit non-zero if out of sync (CI)
    python scripts/sync_docs.py --write    # apply updates in place
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _manifest_helpers import expected_readme_lines, read_manifest_active

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
README_PATH = REPO_ROOT / "README.md"
ROADMAP_PATH = REPO_ROOT / "docs" / "roadmap.md"

ACTIVE_HEADING = "## Currently active"
SNAPSHOT_COUNT_RE = re.compile(r"The (\w+) commit snapshots above passed")
_ORDINAL_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
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


def _build_new_block(
    heading_line: str, leading: list[str], expected: list[str], trailing: list[str]
) -> list[str]:
    """Rebuild a section from its heading, leading blanks, bullets, and trailing lines."""
    new_block: list[str] = [heading_line]
    if not new_block[0].endswith("\n"):
        new_block[0] += "\n"
    new_block.extend(leading if leading else ["\n"])
    for el in expected:
        new_block.append(el + "\n")
    if trailing:
        if new_block and new_block[-1].strip() != "" and trailing[0].strip() != "":
            new_block.append("\n")
        new_block.extend(trailing)
    else:
        if new_block and not new_block[-1].endswith("\n"):
            new_block.append("\n")
    return new_block


def _snapshot_count_repl(match: re.Match, count: int) -> str:
    """Return the replacement for one 'N commit snapshots above passed' match.

    Preserves the existing spelling when the number already matches so --check
    does not flag a synced README for using 'six' instead of '6'.
    """
    token = match.group(1)
    current = int(token) if token.isdigit() else _ORDINAL_WORDS.get(token.lower())
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
        return lines
    return new_text.splitlines(keepends=True)


def sync_readme(
    readme_text: str, expected: list[str], snapshot_count: int
) -> tuple[str, bool]:
    """Return README text with the 'Currently active' block rebuilt from `expected`."""
    lines = readme_text.splitlines(keepends=True)
    start, end = _find_section(lines, ACTIVE_HEADING)

    block = lines[start + 1 : end]
    leading, _list_lines, trailing = _split_block(block)
    trailing = _sync_afterword(trailing, snapshot_count)

    heading_line = lines[start]
    new_block = _build_new_block(heading_line, leading, expected, trailing)

    old_block = lines[start:end]
    new_text = "".join(lines[:start]) + "".join(new_block) + "".join(lines[end:])
    changed = "".join(old_block) != "".join(new_block)
    return new_text, changed


def sync_roadmap(roadmap_text: str, count: int) -> tuple[str, bool]:
    """Return roadmap text with the ``active[]`` plugin count synced to `count`.

    The count sentence may wrap across lines, so the pattern matches intervening
    whitespace and the replacement preserves the existing line wrap.
    """
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
    expected = expected_readme_lines(active)
    count = len(active)
    snapshot_count = sum(1 for e in active if e.get("verified_with") and not e.get("tag"))

    readme_text = README_PATH.read_text(encoding="utf-8")
    roadmap_text = ROADMAP_PATH.read_text(encoding="utf-8")

    new_readme, readme_changed = sync_readme(readme_text, expected, snapshot_count)
    new_roadmap, roadmap_changed = sync_roadmap(roadmap_text, count)

    changed = readme_changed or roadmap_changed

    if args.write:
        if readme_changed:
            README_PATH.write_text(new_readme, encoding="utf-8")
            print("Updated README.md active section.")
        if roadmap_changed:
            ROADMAP_PATH.write_text(new_roadmap, encoding="utf-8")
            print("Updated docs/roadmap.md plugin count.")
        if not changed:
            print("Already in sync.")
        return 0

    if changed:
        print("Docs are out of sync with manifest.json.")
        if readme_changed:
            print("  - README.md 'Currently active' section")
        if roadmap_changed:
            print("  - docs/roadmap.md active[] count")
        print("Run: python scripts/sync_docs.py --write")
        return 1
    print("Docs are in sync with manifest.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
