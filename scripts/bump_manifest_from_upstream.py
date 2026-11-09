#!/usr/bin/env python3
"""Automatically bump tagged active plugins in manifest.json to newer upstream minor/patch tags.

Fails closed on tag provenance mismatches, major version bumps, prerelease tags,
unresolvable commits, or upstream Nu dependency downgrades.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from check_upstream_updates import (
    FetchError,
    _check_tag_moved,
    fetch_cargo_toml_nu_dep,
    fetch_latest_tags,
    manifest_nu_upper_bound,
    parse_version,
    resolve_tag_commit,
)
from format_json import format_text

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"
SEMVER_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\+[0-9A-Za-z.-]+)?$", re.IGNORECASE)
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def parse_strict_semver_tag(tag: str) -> tuple[int, int, int] | None:
    """Parse a clean vX.Y.Z or X.Y.Z tag (rejecting prereleases; optional +build metadata is allowed)."""
    m = SEMVER_TAG_RE.match(tag.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def format_nu_constraint(cargo_nu: str) -> tuple[tuple[int, int], str] | None:
    """Convert a Cargo.toml nu-plugin version into ((major, minor), '>=M.m.0 <M.(m+1).0')."""
    parsed = parse_version(cargo_nu)
    if parsed is None:
        return None
    major, minor, _ = parsed
    return (major, minor), f">={major}.{minor}.0 <{major}.{minor + 1}.0"


def _extract_tag_names(tags: list[dict]) -> list[str]:
    """Return non-empty string tag names from raw GitHub tag objects."""
    names: list[str] = []
    for item in tags:
        tname = item.get("name")
        if isinstance(tname, str) and tname:
            names.append(tname)
    return names


def _parse_stable_tags(tag_names: list[str]) -> list[tuple[tuple[int, int, int], str]]:
    """Filter tag names down to clean semver tags with their parsed (major, minor, patch) tuples."""
    stable: list[tuple[tuple[int, int, int], str]] = []
    for tname in tag_names:
        parsed = parse_strict_semver_tag(tname)
        if parsed is not None:
            stable.append((parsed, tname))
    return stable


def _pick_best_stable_tag(
    stable: list[tuple[tuple[int, int, int], str]],
    current_ver: tuple[int, int, int],
) -> tuple[tuple[int, int, int], str]:
    """Pick the highest newer tag in the current major, or fall back to highest overall stable tag."""
    same_major = [pair for pair in stable if pair[0][0] == current_ver[0]]
    eligible = [pair for pair in same_major if pair[0] > current_ver]
    pool = eligible if eligible else stable
    return max(pool, key=lambda pair: pair[0])


def _classify_selected_tag(
    new_ver: tuple[int, int, int],
    newest_tag: str,
    current_tag: str,
    current_ver: tuple[int, int, int],
) -> tuple[tuple[int, int, int] | None, str | None, str]:
    """Classify whether the selected tag is an eligible minor/patch bump."""
    if newest_tag == current_tag:
        return None, None, "up to date"
    if new_ver <= current_ver:
        return None, None, f"up to date (newest tag {newest_tag} <= {current_ver})"
    if new_ver[0] != current_ver[0]:
        return (
            None,
            None,
            f"skipped (major version bump {current_tag} -> {newest_tag} requires review)",
        )
    return new_ver, newest_tag, ""


def _select_candidate_tag(
    tags: list[dict],
    current_tag: str,
    current_ver: tuple[int, int, int],
) -> tuple[tuple[int, int, int] | None, str | None, str]:
    """Select the highest eligible stable tag in the current major, or explain why skipped."""
    if not tags:
        return None, None, "up to date (no upstream tags)"

    tag_names = _extract_tag_names(tags)
    if not tag_names:
        return None, None, "up to date (empty tag)"

    stable = _parse_stable_tags(tag_names)
    if not stable:
        return None, None, f"skipped (non-stable tag {tag_names[0]})"

    new_ver, newest_tag = _pick_best_stable_tag(stable, current_ver)
    return _classify_selected_tag(new_ver, newest_tag, current_tag, current_ver)


def _is_nu_downgrade(new_pair: tuple[int, int], current_nu_str: str) -> bool:
    """Return True if new_pair (major, minor) is older than the current manifest nu_version range."""
    bound = manifest_nu_upper_bound(current_nu_str)
    if bound is None:
        return False
    cur_nu_maj, cur_nu_upper_min, _ = bound
    cur_nu_min = max(0, cur_nu_upper_min - 1)
    return new_pair < (cur_nu_maj, cur_nu_min)


def _resolve_validated_nu_version(
    cargo_nu: str | None,
    current_nu_str: str,
    newest_tag: str,
) -> tuple[str | None, str]:
    """Validate upstream Cargo.toml Nu dependency and check for minor downgrades."""
    if not cargo_nu:
        return None, f"refused (could not determine upstream Nu dependency for {newest_tag})"

    formatted = format_nu_constraint(cargo_nu)
    if formatted is None:
        return None, f"refused (unparsable Cargo.toml nu dependency {cargo_nu!r})"

    new_pair, candidate_nu_str = formatted
    if _is_nu_downgrade(new_pair, current_nu_str):
        return (
            None,
            f"refused (upstream Nu dependency {cargo_nu} downgrades current {current_nu_str})",
        )
    return candidate_nu_str, ""


def _is_valid_sha40(sha: str | None) -> bool:
    """Return True when sha is a 40-char hexadecimal commit hash."""
    if not sha:
        return False
    return bool(SHA40_RE.match(sha))


def _fetch_validated_candidate(
    repo: str,
    current_tag: str,
    current_ver: tuple[int, int, int],
    current_commit: str,
) -> tuple[tuple[tuple[int, int, int], str, str, str | None] | None, str]:
    """Fetch and validate upstream tag, commit SHA, and Cargo.toml Nu dependency."""
    if _check_tag_moved(repo, current_tag, current_commit):
        return None, f"refused (current tag {current_tag} moved upstream)"

    tags = fetch_latest_tags(repo)
    new_ver, newest_tag, skip_reason = _select_candidate_tag(tags, current_tag, current_ver)
    if new_ver is None or newest_tag is None:
        return None, skip_reason

    new_sha = resolve_tag_commit(repo, newest_tag)
    if not _is_valid_sha40(new_sha):
        return None, f"refused (could not resolve 40-char commit for {newest_tag})"

    cargo_nu = fetch_cargo_toml_nu_dep(repo, ref=newest_tag)
    return (new_ver, newest_tag, str(new_sha), cargo_nu), ""


def _validate_entry_for_bump(entry: dict) -> tuple[tuple[str, tuple[int, int, int]] | None, str]:
    """Validate that a manifest entry is eligible for tagged bumping."""
    if entry.get("intake_mode", "tagged") != "tagged":
        return None, "skipped (commit-snapshot)"

    current_tag = entry.get("tag")
    if not isinstance(current_tag, str) or not current_tag:
        return None, "skipped (no current tag)"

    current_ver = parse_strict_semver_tag(entry.get("version", "")) or parse_strict_semver_tag(
        current_tag
    )
    if current_ver is None:
        return None, f"skipped (unparsable current version {entry.get('version')!r})"

    return (current_tag, current_ver), ""


@dataclass(frozen=True)
class BumpCandidate:
    new_ver: tuple[int, int, int]
    newest_tag: str
    new_sha: str
    new_nu_str: str


def _sanitize_exclude_reason_on_bump(reason: str | None) -> str | None:
    """Strip stale build run references or green run assertions when bumping a plugin."""
    if not reason:
        return reason
    cleaned = re.sub(
        r";?\s*(?:the\s+)?(?:remaining\s+\w+\s+)?targets\s+are\s+green\s+on\s+build\s+run\s+\d+",
        "",
        reason,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r";?\s*(?:the\s+)?(?:remaining\s+)?green\s+on\s+build\s+run\s+\d+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r";?\s*(?:verified|green)\s+on\s+(?:build\s+)?run\s+\d+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip().rstrip(";,")


def _apply_bump_to_entry(entry: dict, candidate: BumpCandidate) -> dict:
    """Mutate entry in place with bumped values and return the summary dictionary."""
    new_version_str = f"{candidate.new_ver[0]}.{candidate.new_ver[1]}.{candidate.new_ver[2]}"
    new_sha_lower = candidate.new_sha.lower()
    summary = {
        "name": entry.get("name", "<unknown>"),
        "repo": str(entry.get("repo", "")).strip(),
        "old_tag": entry.get("tag"),
        "new_tag": candidate.newest_tag,
        "old_version": entry.get("version"),
        "new_version": new_version_str,
        "old_commit": entry.get("source_commit", ""),
        "new_commit": new_sha_lower,
        "old_nu_version": entry.get("nu_version", ""),
        "new_nu_version": candidate.new_nu_str,
    }
    entry["tag"] = candidate.newest_tag
    entry["version"] = new_version_str
    entry["source_commit"] = new_sha_lower
    entry["nu_version"] = candidate.new_nu_str
    entry["verified_with"] = []
    if "exclude_reason" in entry and isinstance(entry["exclude_reason"], str):
        entry["exclude_reason"] = _sanitize_exclude_reason_on_bump(entry["exclude_reason"])
    return summary


def bump_entry(entry: dict) -> tuple[bool, str, dict | None]:
    """Attempt to bump a single active manifest entry in place."""
    validated, skip_reason = _validate_entry_for_bump(entry)
    if validated is None:
        return False, skip_reason, None

    current_tag, current_ver = validated
    repo = str(entry.get("repo", "")).strip()
    current_commit = entry.get("source_commit", "")
    try:
        candidate, err_reason = _fetch_validated_candidate(
            repo, current_tag, current_ver, current_commit
        )
    except FetchError as exc:
        return False, f"fetch error: {exc}", None

    if candidate is None:
        return False, err_reason, None

    new_ver, newest_tag, new_sha, cargo_nu = candidate
    current_nu_str = entry.get("nu_version", "")
    new_nu_str, nu_err = _resolve_validated_nu_version(cargo_nu, current_nu_str, newest_tag)
    if new_nu_str is None:
        return False, nu_err, None

    candidate_obj = BumpCandidate(new_ver, newest_tag, new_sha, new_nu_str)
    summary = _apply_bump_to_entry(entry, candidate_obj)
    new_sha_short = summary["new_commit"][:7]
    return True, f"bumped {current_tag} -> {newest_tag} ({new_sha_short})", summary


def _should_process_entry(name: str, only: set[str] | None) -> bool:
    """Return True if entry name matches optional filter set."""
    if only is None:
        return True
    return name in only


def bump_manifest(manifest: dict, only: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Run bump_entry across active plugins in manifest."""
    bumped: list[dict] = []
    decisions: list[dict] = []
    for entry in manifest.get("active", []):
        name = entry.get("name", "")
        if not _should_process_entry(name, only):
            continue
        did_bump, reason, summary = bump_entry(entry)
        decisions.append({"name": name, "bumped": did_bump, "reason": reason})
        if summary is not None:
            bumped.append(summary)
    return bumped, decisions


def write_json_atomic(path: Path, data: dict) -> None:
    """Atomically write canonically formatted JSON to path."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    rendered = format_text(json.dumps(data, ensure_ascii=False))
    tmp.write_text(rendered, encoding="utf-8")
    os.replace(tmp, path)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=MANIFEST_PATH, help="Path to manifest.json"
    )
    parser.add_argument("--only", default="", help="Optional comma-separated plugin names")
    parser.add_argument("--write", action="store_true", help="Write updated manifest.json in place")
    parser.add_argument(
        "--json-out", type=Path, default=None, help="Optional JSON summary output path"
    )
    return parser.parse_args(argv)


def _write_outputs(
    args: argparse.Namespace,
    manifest: dict,
    bumped: list[dict],
    decisions: list[dict],
) -> None:
    """Write optional manifest updates, JSON summary, and GitHub Actions outputs."""
    if args.write and bumped:
        write_json_atomic(args.manifest, manifest)
        print(f"Updated {args.manifest} ({len(bumped)} plugin(s) bumped).")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(args.json_out, {"bumped": bumped, "decisions": decisions})

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        names = ",".join(item["name"] for item in bumped)
        with open(gh_output, "a", encoding="utf-8") as fh:
            fh.write(f"bumped_plugins={names}\n")
            fh.write(f"bumped_count={len(bumped)}\n")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.manifest.is_file():
        print(f"error: manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    only_set = {item.strip() for item in args.only.split(",") if item.strip()} or None

    bumped, decisions = bump_manifest(manifest, only=only_set)
    for item in decisions:
        status = "BUMPED" if item["bumped"] else "SKIP"
        print(f"  [{status}] {item['name']}: {item['reason']}")

    _write_outputs(args, manifest, bumped, decisions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
