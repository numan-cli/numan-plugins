#!/usr/bin/env python3
"""Local consistency checks for numan-plugins catalog docs.

Validates:
- README ``Currently active`` matches ``manifest.json`` ``active[]``
- Managed notes do not embed transient PR references
- Backlog ``PROMOTED`` is not used while registry intake is still pending
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
BACKLOG_PATH = REPO_ROOT / "docs" / "backlog.json"
README_PATH = REPO_ROOT / "README.md"

ACTIVE_HEADING = "## Currently active"
PR_REF_RE = re.compile(
    r"(?:"
    r"\bthis\s+pr\b|"
    r"\bPR\s*#\s*\d+|"
    r"\bnuman-(?:registry|plugins)#\d+|"
    r"https?://github\.com/[^\s)]+/pull/\d+"
    r")",
    re.IGNORECASE,
)
ROADMAP_PATH = REPO_ROOT / "docs" / "roadmap.md"
PENDING_REGISTRY_RE = re.compile(r"pending\s+registry", re.IGNORECASE)
ACTIVE_LINE_RE = re.compile(
    r"^- `(?P<repo>[^`]+)` @ `(?P<tag>[^`]+)` → `(?P<name>[^`]+)` (?P<version>\S+)\s*$"
)


def read_manifest_active(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    active = data.get("active")
    if not isinstance(active, list):
        raise ValueError(f"{path}: active must be a list")
    return active


def expected_readme_lines(active: list[dict]) -> list[str]:
    lines: list[str] = []
    for entry in active:
        # Entries with empty verified_with go in the "Pending" section, not "Currently active"
        if not entry.get("verified_with"):
            continue
        lines.append(
            f"- `{entry['repo']}` @ `{entry['tag']}` → `{entry['name']}` {entry['version']}"
        )
    return lines


def parse_readme_active(readme_text: str) -> list[str]:
    lines = readme_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == ACTIVE_HEADING)
    except StopIteration as exc:
        raise ValueError(f"README missing '{ACTIVE_HEADING}' heading") from exc

    collected: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if not line.strip():
            continue
        if line.startswith("- "):
            collected.append(line.rstrip())
    return collected


def check_readme_active(manifest_path: Path, readme_path: Path) -> list[str]:
    active = read_manifest_active(manifest_path)
    expected = expected_readme_lines(active)
    actual = parse_readme_active(readme_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if actual != expected:
        errors.append(
            "README Currently active does not match manifest.json active[] "
            f"(readme={len(actual)} entries, manifest={len(expected)} entries)"
        )
        for index, (left, right) in enumerate(zip(actual, expected)):
            if left != right:
                errors.append(f"  mismatch at item {index + 1}:")
                errors.append(f"    readme:   {left}")
                errors.append(f"    manifest: {right}")
                break
        else:
            if len(actual) < len(expected):
                errors.append(f"  missing from README: {expected[len(actual)]}")
            elif len(actual) > len(expected):
                errors.append(f"  extra in README: {actual[len(expected)]}")
    for line in actual:
        if not ACTIVE_LINE_RE.match(line):
            errors.append(f"README active line has unexpected shape: {line}")
    return errors


def check_no_pr_refs(*paths: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        # Manifest: only scan backlog_note. Backlog: scan c1_note + top-level note.
        if path.name == "manifest.json":
            data = json.loads(text)
            note = data.get("backlog_note", "")
            if isinstance(note, str) and PR_REF_RE.search(note):
                errors.append(f"{path}: backlog_note embeds a transient PR reference")
            continue
        if path.name == "backlog.json":
            data = json.loads(text)
            top = data.get("note", "")
            if isinstance(top, str) and PR_REF_RE.search(top):
                errors.append(f"{path}: top-level note embeds a transient PR reference")
            for plugin in data.get("plugins", []):
                c1 = plugin.get("c1_note", "")
                if isinstance(c1, str) and PR_REF_RE.search(c1):
                    name = plugin.get("name", "<unknown>")
                    errors.append(f"{path}: {name} c1_note embeds a transient PR reference")
            continue
        if PR_REF_RE.search(text):
            errors.append(f"{path}: embeds a transient PR reference")
    return errors


def check_backlog_promoted(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for plugin in data.get("plugins", []):
        name = plugin.get("name", "<unknown>")
        status = plugin.get("status")
        note = plugin.get("c1_note") or ""
        if status != "PROMOTED":
            continue
        if PENDING_REGISTRY_RE.search(note):
            errors.append(
                f"{path}: {name} is PROMOTED but c1_note still says pending registry intake"
            )
        # Non-empty backfill_targets with an explicit pending-registry note is
        # already covered above. Stale backfill rows without that wording are
        # left for manual backlog hygiene so historical minors can remain listed.
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="Path to manifest.json",
    )
    parser.add_argument(
        "--backlog",
        type=Path,
        default=BACKLOG_PATH,
        help="Path to docs/backlog.json",
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=README_PATH,
        help="Path to README.md",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    errors.extend(check_readme_active(args.manifest, args.readme))
    errors.extend(check_no_pr_refs(args.manifest, args.backlog, ROADMAP_PATH))
    errors.extend(check_backlog_promoted(args.backlog))

    if errors:
        print("Repo consistency check failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print("OK: repo consistency checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
