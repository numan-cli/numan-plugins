#!/usr/bin/env python3
"""Fail closed when a plugin Git tag or release already exists."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from urllib.parse import quote

COMMAND_TIMEOUT_SECONDS = 30


def _require_not_found(
    result: subprocess.CompletedProcess[str],
    *,
    subject: str,
) -> None:
    """
    Validate that a command result confirms the specified subject is absent.
    
    Parameters:
        result (subprocess.CompletedProcess[str]): The completed GitHub CLI result to validate.
        subject (str): Description of the tag or release being checked.
    
    Raises:
        ValueError: If the subject exists.
        RuntimeError: If the result does not reliably confirm that the subject is absent.
    """
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
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    _require_not_found(tag_result, subject=f"tag {repo}@{tag}")

    release_result = runner(
        ["gh", "release", "view", tag, "--repo", repo],
        check=False,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    _require_not_found(release_result, subject=f"release {repo}@{tag}")


def main(argv: list[str] | None = None) -> int:
    """
    Run the release-absence check using command-line arguments and report its outcome.
    
    Parameters:
        argv (list[str] | None): Arguments to parse, or None to use the process command line.
    
    Returns:
        int: 0 when the release is absent, or 1 when the check fails.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    try:
        ensure_absent(args.repo, args.tag)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: release {args.repo}@{args.tag} does not exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
