#!/usr/bin/env python3
"""Local consistency checks for numan-plugins catalog docs.

Validates:
- README ``Currently active`` matches ``manifest.json`` ``active[]``
- README ``Pending first build`` matches ``manifest.json`` unverified ``active[]``
- Managed notes do not embed transient PR references
- Backlog ``PROMOTED`` is not used while registry intake is still pending
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _manifest_helpers import (
    expected_readme_lines,
    parse_readme_entry_line,
    read_manifest_active,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
BACKLOG_PATH = REPO_ROOT / "docs" / "backlog.json"
README_PATH = REPO_ROOT / "README.md"
ARCHIVES_PATH = REPO_ROOT / "manifest-archives.json"

ACTIVE_HEADING = "## Currently active"
PENDING_HEADING = "## Pending first build"
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


def parse_readme_pending(readme_text: str) -> list[str]:
    lines = readme_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == PENDING_HEADING)
    except StopIteration:
        return []

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


def _check_pending_preconditions(
    unverified_count: int, actual_lines: list[str], readme_text: str
) -> list[str] | None:
    """Validate existence and non-emptiness preconditions for pending plugins."""
    if unverified_count and not actual_lines:
        if PENDING_HEADING not in readme_text:
            return [
                f"README missing '{PENDING_HEADING}' heading while manifest has unverified plugins"
            ]
        return [
            f"README Pending section is empty but manifest has {unverified_count} unverified plugins"
        ]
    if not unverified_count and actual_lines:
        return [
            f"README Pending section has {len(actual_lines)} entries but manifest has 0 unverified plugins"
        ]
    if not unverified_count and not actual_lines:
        return []
    return None


def _check_pending_membership(
    actual_names: list[str], expected_names: list[str]
) -> list[str]:
    """Report list mismatches, missing names, or extra names in README pending."""
    if actual_names == expected_names:
        return []
    errors = [
        "README Pending first build plugins do not match manifest.json unverified active[] "
        f"(readme={len(actual_names)} entries, manifest={len(expected_names)} entries)"
    ]
    missing = [name for name in expected_names if name not in actual_names]
    if missing:
        errors.append(f"  missing from README Pending: {', '.join(missing)}")
    extra = [name for name in actual_names if name not in expected_names]
    if extra:
        errors.append(f"  extra in README Pending: {', '.join(extra)}")
    return errors


def _verify_pending_entry(parsed: dict, entry: dict) -> list[str]:
    """Verify repo, tag, and version alignment for a single pending plugin."""
    name = parsed["name"]
    errors = []
    if parsed["repo"] != entry.get("repo"):
        errors.append(
            f"README Pending repo mismatch for {name}: "
            f"readme='{parsed['repo']}', manifest='{entry.get('repo')}'"
        )
    expected_tag = entry.get("tag") or f"commit {entry.get('source_commit', '')[:7]}"
    if parsed["tag"] != expected_tag:
        errors.append(
            f"README Pending tag mismatch for {name}: "
            f"readme='{parsed['tag']}', manifest='{expected_tag}'"
        )
    if parsed["version"] != entry.get("version"):
        errors.append(
            f"README Pending version mismatch for {name}: "
            f"readme='{parsed['version']}', manifest='{entry.get('version')}'"
        )
    return errors


def check_readme_pending(manifest_path: Path, readme_path: Path) -> list[str]:
    """Verify that README 'Pending first build' matches manifest.json unverified active[]."""
    active = read_manifest_active(manifest_path)
    unverified = [e for e in active if not e.get("verified_with")]
    readme_text = readme_path.read_text(encoding="utf-8")
    actual_lines = parse_readme_pending(readme_text)

    precond_errors = _check_pending_preconditions(len(unverified), actual_lines, readme_text)
    if precond_errors is not None:
        return precond_errors

    errors: list[str] = []
    actual_entries = []
    for line in actual_lines:
        parsed = parse_readme_entry_line(line)
        if not parsed:
            errors.append(f"README pending line has unexpected shape: {line}")
        else:
            actual_entries.append(parsed)

    actual_names = [e["name"] for e in actual_entries]
    expected_names = [e["name"] for e in unverified]
    errors.extend(_check_pending_membership(actual_names, expected_names))

    unverified_by_name = {e["name"]: e for e in unverified}
    for parsed in actual_entries:
        entry = unverified_by_name.get(parsed["name"])
        if entry:
            errors.extend(_verify_pending_entry(parsed, entry))

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


def check_archives(file_path: Path) -> list[str]:
    """Validate archive manifest schema."""
    if not file_path.exists():
        return [f"missing: {file_path}"]
    raw = file_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if type(parsed) is not list:
        return [f"{file_path}: must be list"]
    result = []
    fields = ["git", "ref", "resolved_sha", "entry", "owner", "name", "type"]
    for n, el in enumerate(parsed):
        if not isinstance(el, dict):
            result.append(f"{file_path}[{n}] must be object")
            continue
        for fld in fields:
            if fld not in el:
                result.append(f"{file_path}[{n}] missing {fld}")
    return result


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
    errors.extend(check_readme_pending(args.manifest, args.readme))
    errors.extend(check_no_pr_refs(args.manifest, args.backlog, ROADMAP_PATH))
    errors.extend(check_backlog_promoted(args.backlog))
    errors.extend(check_archives(ARCHIVES_PATH))

    if errors:
        print("Repo consistency check failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print("OK: repo consistency checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
