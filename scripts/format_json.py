#!/usr/bin/env python3
"""Format managed JSON files with the repo's compact-array style.

Writes indent-2 JSON and collapses leaf arrays of primitives onto one line
when the result fits within ``--max-width``. Use ``--check`` in CI/pre-commit
to fail when a file would change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = (
    REPO_ROOT / "manifest.json",
    REPO_ROOT / "docs" / "backlog.json",
)


def _is_primitive(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _format_primitive(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def format_value(value: object, indent: int, level: int, max_width: int) -> str:
    """Render ``value`` with indent-2 nesting and compact leaf arrays."""
    pad = " " * (indent * level)
    child_pad = " " * (indent * (level + 1))

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        items = list(value.items())
        for index, (key, child) in enumerate(items):
            comma = "," if index < len(items) - 1 else ""
            rendered = format_value(child, indent, level + 1, max_width)
            lines.append(f"{child_pad}{json.dumps(key)}: {rendered}{comma}")
        lines.append(f"{pad}}}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return "[]"
        if all(_is_primitive(item) for item in value):
            compact = "[" + ", ".join(_format_primitive(item) for item in value) + "]"
            # Compare the array body alone; parent key indentation is separate.
            if len(compact) <= max_width:
                return compact
        lines = ["["]
        for index, item in enumerate(value):
            comma = "," if index < len(value) - 1 else ""
            rendered = format_value(item, indent, level + 1, max_width)
            lines.append(f"{child_pad}{rendered}{comma}")
        lines.append(f"{pad}]")
        return "\n".join(lines)

    return _format_primitive(value)


def format_text(text: str, *, max_width: int = 100) -> str:
    """Return canonical JSON text for an existing JSON document."""
    data = json.loads(text)
    return format_value(data, indent=2, level=0, max_width=max_width) + "\n"


def format_path(path: Path, *, check: bool, max_width: int) -> bool:
    """Format ``path`` in place, or return whether it already matches in check mode."""
    original = path.read_text(encoding="utf-8")
    formatted = format_text(original, max_width=max_width)
    if original == formatted:
        return True
    if check:
        return False
    path.write_text(formatted, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="JSON files to format (default: manifest.json and docs/backlog.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any file would change; do not write",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=100,
        help="Collapse primitive arrays onto one line when they fit (default: 100)",
    )
    args = parser.parse_args(argv)
    paths = args.paths or list(DEFAULT_PATHS)

    dirty: list[Path] = []
    for path in paths:
        if not path.is_file():
            print(f"error: missing file: {path}", file=sys.stderr)
            return 2
        if not format_path(path, check=args.check, max_width=args.max_width):
            dirty.append(path)

    if dirty:
        joined = ", ".join(str(path) for path in dirty)
        print(f"JSON format check failed: {joined}", file=sys.stderr)
        print("Run: python3 scripts/format_json.py", file=sys.stderr)
        return 1

    action = "checked" if args.check else "formatted"
    print(f"OK: {action} {len(paths)} JSON file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
