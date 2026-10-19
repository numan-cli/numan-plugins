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
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
README_PATH = REPO_ROOT / "README.md"
ROADMAP_PATH = REPO_ROOT / "docs" / "roadmap.md"

ACTIVE_HEADING = "## Currently active"


def read_manifest_active(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    active = data.get("active")
    if not isinstance(active, list):
        raise ValueError(f"{path}: active must be a list")
    return active


def expected_readme_lines(active: list[dict]) -> list[str]:
    lines: list[str] = []
    for entry in active:
        if not entry.get("verified_with"):
            continue
        tag_display = entry.get("tag") or f"commit {entry['source_commit'][:7]}"
        lines.append(
            f"- `{entry['repo']}` @ `{tag_display}` → `{entry['name']}` {entry['version']}"
        )
    return lines


def sync_readme(readme_text: str, expected: list[str]) -> tuple[str, bool]:
    lines = readme_text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.strip() == ACTIVE_HEADING:
            start = i
            break
    if start is None:
        raise ValueError(f"README missing '{ACTIVE_HEADING}' heading")

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break

    block = lines[start + 1 : end]
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

    new_block: list[str] = [lines[start]]
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

    old_block = lines[start:end]
    new_text = "".join(lines[:start]) + "".join(new_block) + "".join(lines[end:])
    changed = "".join(old_block) != "".join(new_block)
    return new_text, changed


def sync_roadmap(roadmap_text: str, count: int) -> tuple[str, bool]:
    pattern = re.compile(r"`manifest\.json` `active\[\]` currently holds \d+ plugins\.")
    replacement = f"`manifest.json` `active[]` currently holds {count} plugins."
    new_text, n = pattern.subn(replacement, roadmap_text)
    changed = n > 0 and new_text != roadmap_text
    return new_text, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args()

    active = read_manifest_active(MANIFEST_PATH)
    expected = expected_readme_lines(active)
    count = len(active)

    readme_text = README_PATH.read_text(encoding="utf-8")
    roadmap_text = ROADMAP_PATH.read_text(encoding="utf-8")

    new_readme, readme_changed = sync_readme(readme_text, expected)
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
