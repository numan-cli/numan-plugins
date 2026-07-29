#!/usr/bin/env python3
"""Fail closed when a plugin Git tag or release already exists."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from urllib.parse import quote


def _require_not_found(
    result: subprocess.CompletedProcess[str],
    *,
    subject: str,
) -> None:
    """Accept a confirmed GitHub 404 and fail closed for every other result."""
    if result.returncode == 0:
        raise ValueError(f"{subject} already exists; published assets are immutable")
    combined = f"{result.stdout}\n{result.stderr}".lower()
    if result.returncode != 1 or not any(
        marker in combined for marker in ("release not found", "not found", "404")
    ):
        raise RuntimeError(
            f"could not prove absence of {subject}: "
            f"gh exited {result.returncode}: {result.stderr.strip()}"
        )


def ensure_absent(
    repo: str,
    tag: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Verify that neither a Git tag nor a release exists for ``tag``."""
    tag_result = runner(
        ["gh", "api", f"repos/{repo}/git/ref/tags/{quote(tag, safe='')}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    _require_not_found(tag_result, subject=f"tag {repo}@{tag}")

    release_result = runner(
        ["gh", "release", "view", tag, "--repo", repo],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    _require_not_found(release_result, subject=f"release {repo}@{tag}")


def main(argv: list[str] | None = None) -> int:
    """Run the release-absence check from command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    try:
        ensure_absent(args.repo, args.tag)
    except (RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: release {args.repo}@{args.tag} does not exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
