#!/usr/bin/env python3
"""Validate the plugin build manifest and optional upstream tag mappings."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_REPO_SLUG_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
COMMAND_TIMEOUT_SECONDS = 30
REQUIRED_FIELDS = {
    "repo",
    "name",
    "owner",
    "plugin_bin",
    "source_commit",
    "version",
    "nu_version",
    "verified_with",
    "description",
    "tags",
}
INTAKE_MODES = {"tagged", "commit-snapshot"}


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
    """Validate target declarations and return the targets required for the entry.
    
    Parameters:
    	manifest (dict): Manifest containing the default target list.
    	entry (dict): Active entry containing optional excluded targets.
    
    Returns:
    	list[str]: The default targets remaining after exclusions."""
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


def validate_intake_fields(name: str, entry: dict) -> None:
    """Validate intake_mode and tag rules for a single active entry."""
    intake_mode = entry.get("intake_mode", "tagged")
    if not isinstance(intake_mode, str):
        raise ValueError(f"{name}: intake_mode must be one of {sorted(INTAKE_MODES)}")
    if intake_mode not in INTAKE_MODES:
        raise ValueError(f"{name}: intake_mode must be one of {sorted(INTAKE_MODES)}")
    tag = entry.get("tag")
    if intake_mode == "tagged":
        if not isinstance(tag, str) or not tag:
            raise ValueError(f"{name}: tag is required and must be non-empty")
    elif tag is not None and not isinstance(tag, str):
        raise ValueError(f"{name}: tag must be a string or null")


def validate_upstream_repo(entry: dict) -> None:
    """Enforce ADR 0001 fork-identity invariants: only 'numan-maintained' may
    set upstream_repo, it must be required (not optional) for that owner, and
    it must not equal repo (a fork can't claim to be its own upstream)."""
    name = entry["name"]
    upstream_repo = entry.get("upstream_repo")
    if upstream_repo is not None:
        if not isinstance(upstream_repo, str) or not upstream_repo:
            raise ValueError(f"{name}: upstream_repo must be a non-empty string when present")
        if not GITHUB_REPO_SLUG_RE.fullmatch(upstream_repo):
            raise ValueError(
                f"{name}: upstream_repo must be 'owner/name', got {upstream_repo!r}"
            )
        if entry.get("owner") != "numan-maintained":
            raise ValueError(
                f"{name}: upstream_repo requires owner 'numan-maintained' "
                "(a fork must not claim the original owner's identity)"
            )
        if upstream_repo.lower() == str(entry.get("repo", "")).lower():
            raise ValueError(f"{name}: upstream_repo must not be the same as repo")
    elif entry.get("owner") == "numan-maintained":
        raise ValueError(f"{name}: owner 'numan-maintained' requires upstream_repo")


def validate_active_entry(manifest: dict, entry: dict, names: set[str]) -> str:
    """Validate one active entry and record its name in ``names``.

    Returns:
        str: The entry's plugin name.
    """
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
    source_commit = entry["source_commit"]
    if not isinstance(source_commit, str) or not SHA_RE.fullmatch(source_commit):
        raise ValueError(f"{name}: source_commit must be 40 lowercase hex characters")
    validate_intake_fields(name, entry)
    validate_upstream_repo(entry)
    expected_targets(manifest, entry)
    return name


def validate_manifest(manifest: dict, only: list[str] | None = None) -> list[dict]:
    """
    Validate active manifest entries and optionally select named plugins.
    
    Parameters:
        manifest (dict): Manifest data containing the active plugin entries.
        only (list[str] | None): Plugin names to include; when omitted, includes all
            active entries.
    
    Returns:
        list[dict]: Validated active entries, filtered to the requested names when
            provided.
    
    Raises:
        ValueError: If the active entries or their required fields are invalid, a
            plugin name is duplicated or unknown, or a source commit is malformed.
    """
    active = manifest.get("active")
    if not isinstance(active, list) or not active:
        raise ValueError("active must be a non-empty list")

    names: set[str] = set()
    for entry in active:
        validate_active_entry(manifest, entry, names)

    if only is None:
        return active
    missing_names = sorted(set(only) - names)
    if missing_names:
        raise ValueError(f"unknown active plugins: {', '.join(missing_names)}")
    wanted = set(only)
    return [entry for entry in active if entry["name"] in wanted]


def resolve_tag(repo: str, tag: str) -> str:
    """
    Resolve an upstream tag to its commit SHA.
    
    Parameters:
        repo (str): GitHub repository in `owner/name` format.
        tag (str): Tag name to resolve.
    
    Returns:
        str: The commit SHA referenced by the tag.
    
    Raises:
        ValueError: If the remote lookup fails or the tag cannot be found.
    """
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


def verify_commit_exists(repo: str, sha: str) -> None:
    """Confirm a commit-snapshot's source_commit is fetchable from repo.

    ls-remote can't confirm an arbitrary unadvertised commit, so this does a
    scoped shallow fetch instead -- a bad SHA fails fast here rather than
    after a full cross-platform build.
    """
    url = f"https://github.com/{repo}.git"
    with tempfile.TemporaryDirectory() as tmp:
        init = subprocess.run(
            ["git", "init", "--quiet", tmp],
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        if init.returncode != 0:
            raise ValueError(f"failed to init temp git repo: {init.stderr.strip()}")
        result = subprocess.run(
            ["git", "-C", tmp, "fetch", "--quiet", "--depth", "1", url, sha],
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise ValueError(f"source_commit not found upstream: {repo}@{sha}")
        result = subprocess.run(
            ["git", "-C", tmp, "cat-file", "-t", sha],
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0 or result.stdout.strip() != "commit":
            raise ValueError(f"source_commit is not a commit object: {repo}@{sha}")


def verify_upstream(entries: list[dict]) -> None:
    """Require every entry's upstream tag to match its immutable source commit.

    Entries with intake_mode 'commit-snapshot' have no tag to verify against;
    source_commit's existence upstream is checked instead so a bad SHA fails
    here rather than after a full cross-platform build.
    """
    for entry in entries:
        if entry.get("intake_mode", "tagged") == "commit-snapshot":
            verify_commit_exists(entry["repo"], entry["source_commit"])
            print(f"OK: {entry['repo']} (commit-snapshot) -> {entry['source_commit']}")
            continue
        actual = resolve_tag(entry["repo"], entry["tag"])
        expected = entry["source_commit"]
        if actual != expected:
            raise ValueError(
                f"{entry['name']}: {entry['tag']} resolves to {actual}, expected {expected}"
            )
        print(f"OK: {entry['repo']}@{entry['tag']} -> {expected}")


def main(argv: list[str] | None = None) -> int:
    """
    Validate a manifest and optionally verify upstream tag provenance.
    
    Parameters:
        argv (list[str] | None): Command-line arguments to parse, or None to use
            the process arguments.
    
    Returns:
        int: 0 on success or 1 when validation or upstream verification fails.
    """
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
