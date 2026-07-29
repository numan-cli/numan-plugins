#!/usr/bin/env python3
"""Claim, verify, publish, and safely clean up a plugin draft release."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

Runner = Callable[..., subprocess.CompletedProcess[str]]
COMMAND_TIMEOUT_SECONDS = 30


def run_gh(args: list[str], runner: Runner = subprocess.run) -> dict:
    """Run a GitHub CLI command and decode its optional JSON response."""
    result = runner(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gh failed")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def delete_tag(repo: str, tag: str, runner: Runner) -> None:
    """Delete a repository tag previously claimed by this transaction."""
    run_gh(
        ["api", "--method", "DELETE", f"repos/{repo}/git/refs/tags/{quote(tag, safe='')}"],
        runner,
    )


def claim(
    repo: str,
    tag: str,
    commit: str,
    name: str,
    body: str,
    runner: Runner = subprocess.run,
) -> int:
    """Atomically claim a tag, create its draft release, and return the release ID."""
    run_gh(
        [
            "api",
            "--method",
            "POST",
            f"repos/{repo}/git/refs",
            "--raw-field",
            f"ref=refs/tags/{tag}",
            "--raw-field",
            f"sha={commit}",
        ],
        runner,
    )
    try:
        release = run_gh(
            [
                "api",
                "--method",
                "POST",
                f"repos/{repo}/releases",
                "--raw-field",
                f"tag_name={tag}",
                "--raw-field",
                f"target_commitish={commit}",
                "--raw-field",
                f"name={name}",
                "--raw-field",
                f"body={body}",
                "-F",
                "draft=true",
            ],
            runner,
        )
    except Exception:
        delete_tag(repo, tag, runner)
        raise
    if not release.get("draft") or release.get("tag_name") != tag or not isinstance(release.get("id"), int):
        if isinstance(release.get("id"), int):
            run_gh(
                ["api", "--method", "DELETE", f"repos/{repo}/releases/{release['id']}"],
                runner,
            )
        delete_tag(repo, tag, runner)
        raise RuntimeError("GitHub did not return the claimed draft release")
    return release["id"]


def expected_assets(assets_dir: Path) -> dict[str, int]:
    """Return the exact filename-to-size mapping for local release assets."""
    assets = {path.name: path.stat().st_size for path in assets_dir.iterdir() if path.is_file()}
    if not assets:
        raise ValueError(f"no release assets found in {assets_dir}")
    return assets


def finalize(
    repo: str,
    release_id: int,
    tag: str,
    commit: str,
    assets_dir: Path,
    runner: Runner = subprocess.run,
) -> None:
    """Verify draft ownership and assets before publishing the release."""
    release = run_gh(["api", f"repos/{repo}/releases/{release_id}"], runner)
    if release.get("draft") is not True or release.get("tag_name") != tag:
        raise ValueError("release is not the claimed draft")
    ref = run_gh(["api", f"repos/{repo}/git/ref/tags/{quote(tag, safe='')}"], runner)
    if ref.get("object", {}).get("sha") != commit:
        raise ValueError("claimed release tag no longer points to the workflow commit")
    actual = {asset["name"]: asset["size"] for asset in release.get("assets", [])}
    expected = expected_assets(assets_dir)
    if actual != expected:
        raise ValueError(f"release asset set mismatch: expected {expected}, got {actual}")
    published = run_gh(
        ["api", "--method", "PATCH", f"repos/{repo}/releases/{release_id}", "-F", "draft=false"],
        runner,
    )
    if published.get("draft") is not False or published.get("id") != release_id:
        raise RuntimeError("GitHub did not confirm release publication")


def cleanup(
    repo: str,
    release_id: int,
    tag: str,
    commit: str,
    runner: Runner = subprocess.run,
) -> None:
    """Delete only the still-draft release and tag owned by this transaction."""
    release = run_gh(["api", f"repos/{repo}/releases/{release_id}"], runner)
    if release.get("draft") is not True or release.get("tag_name") != tag:
        print("release is not the claimed draft; refusing cleanup", file=sys.stderr)
        return
    ref = run_gh(["api", f"repos/{repo}/git/ref/tags/{quote(tag, safe='')}"], runner)
    if ref.get("object", {}).get("sha") != commit:
        print("release tag ownership changed; refusing cleanup", file=sys.stderr)
        return
    run_gh(["api", "--method", "DELETE", f"repos/{repo}/releases/{release_id}"], runner)
    delete_tag(repo, tag, runner)


def main(argv: list[str] | None = None) -> int:
    """Execute a claim, finalize, or cleanup release transaction command."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    claim_parser = sub.add_parser("claim")
    claim_parser.add_argument("--repo", required=True)
    claim_parser.add_argument("--tag", required=True)
    claim_parser.add_argument("--commit", required=True)
    claim_parser.add_argument("--name", required=True)
    claim_parser.add_argument("--body", required=True)
    for command in ("finalize", "cleanup"):
        child = sub.add_parser(command)
        child.add_argument("--repo", required=True)
        child.add_argument("--release-id", required=True, type=int)
        child.add_argument("--tag", required=True)
        child.add_argument("--commit", required=True)
        if command == "finalize":
            child.add_argument("--assets-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "claim":
            release_id = claim(args.repo, args.tag, args.commit, args.name, args.body)
            output = os.environ.get("GITHUB_OUTPUT")
            if not output:
                raise RuntimeError("GITHUB_OUTPUT is not set")
            with Path(output).open("a", encoding="utf-8") as stream:
                stream.write(f"release_id={release_id}\n")
        elif args.command == "finalize":
            finalize(args.repo, args.release_id, args.tag, args.commit, args.assets_dir)
        else:
            cleanup(args.repo, args.release_id, args.tag, args.commit)
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
