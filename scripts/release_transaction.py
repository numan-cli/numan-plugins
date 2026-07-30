#!/usr/bin/env python3
"""Claim, verify, publish, and safely clean up a plugin draft release."""

from __future__ import annotations

import argparse
import hashlib
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
    """
    Run a GitHub CLI command and decode its optional JSON response.
    
    Parameters:
        args (list[str]): Arguments passed to the GitHub CLI.
    
    Returns:
        dict: The decoded JSON response, or an empty dictionary when the command produces no output.
    
    Raises:
        RuntimeError: If the GitHub CLI command fails.
    """
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
    """
    Claim the specified tag and create a matching draft release.
    
    Parameters:
    	repo (str): GitHub repository in `owner/name` format.
    	tag (str): Tag to claim and associate with the release.
    	commit (str): Commit SHA the tag must reference.
    	name (str): Release name.
    	body (str): Release description.
    
    Returns:
    	int: ID of the created draft release.
    
    Raises:
    	RuntimeError: If GitHub does not return a matching draft release.
    """
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


def expected_assets(assets_dir: Path) -> dict[str, dict[str, int | str]]:
    """Return each local asset's size and SHA-256 digest keyed by filename."""
    assets = {
        path.name: {
            "size": path.stat().st_size,
            "digest": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
        }
        for path in assets_dir.iterdir()
        if path.is_file()
    }
    if not assets:
        raise ValueError(f"no release assets found in {assets_dir}")
    return assets


def upload_assets(
    repo: str,
    release_id: int,
    assets_dir: Path,
    runner: Runner = subprocess.run,
) -> None:
    """
    Upload every file in assets_dir to the claimed draft release by ID.

    Uses the Releases API with the numeric release id so softprops cannot create
    a second draft when the tag is briefly undiscoverable.
    """
    assets = sorted(path for path in assets_dir.iterdir() if path.is_file())
    if not assets:
        raise ValueError(f"no release assets found in {assets_dir}")
    for path in assets:
        name = quote(path.name, safe="")
        result = runner(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repo}/releases/{release_id}/assets?name={name}",
                "-H",
                "Content-Type: application/octet-stream",
                "--input",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(COMMAND_TIMEOUT_SECONDS, 120),
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or f"failed to upload {path.name}"
            )
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
        if payload.get("name") != path.name:
            raise RuntimeError(f"unexpected upload response for {path.name}: {payload}")
        if payload.get("state") not in (None, "uploaded", "new"):
            raise RuntimeError(
                f"upload of {path.name} ended in state {payload.get('state')!r}"
            )


def finalize(
    repo: str,
    release_id: int,
    tag: str,
    commit: str,
    assets_dir: Path,
    runner: Runner = subprocess.run,
) -> None:
    """
    Verify the claimed draft release and its assets before publishing it.
    
    Parameters:
        repo (str): GitHub repository in `owner/name` format.
        release_id (int): ID of the draft release to verify.
        tag (str): Expected release tag.
        commit (str): Expected commit associated with the tag.
        assets_dir (Path): Directory containing the expected release assets.
    
    Raises:
        ValueError: If release ownership, tag reference, or assets do not match.
        RuntimeError: If GitHub does not confirm publication.
    """
    release = run_gh(["api", f"repos/{repo}/releases/{release_id}"], runner)
    if release.get("draft") is not True or release.get("tag_name") != tag:
        raise ValueError("release is not the claimed draft")
    ref = run_gh(["api", f"repos/{repo}/git/ref/tags/{quote(tag, safe='')}"], runner)
    if ref.get("object", {}).get("sha") != commit:
        raise ValueError("claimed release tag no longer points to the workflow commit")
    actual = {
        asset["name"]: {
            "size": asset["size"],
            "digest": asset.get("digest"),
        }
        for asset in release.get("assets", [])
    }
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


def record_release_id(output: Path, release_id: int) -> None:
    """Append the claimed release ID to the GitHub Actions output file."""
    with output.open("a", encoding="utf-8") as stream:
        stream.write(f"release_id={release_id}\n")


def main(argv: list[str] | None = None) -> int:
    """
    Execute a claim, finalize, or cleanup release transaction command.
    
    Parameters:
        argv (list[str] | None): Command-line arguments to parse, or None to use
            the process arguments.
    
    Returns:
        int: 0 on success, or 1 when the transaction fails.
    """
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    claim_parser = sub.add_parser("claim")
    claim_parser.add_argument("--repo", required=True)
    claim_parser.add_argument("--tag", required=True)
    claim_parser.add_argument("--commit", required=True)
    claim_parser.add_argument("--name", required=True)
    claim_parser.add_argument("--body", required=True)
    for command in ("finalize", "cleanup", "upload"):
        child = sub.add_parser(command)
        child.add_argument("--repo", required=True)
        child.add_argument("--release-id", required=True, type=int)
        if command in ("finalize", "cleanup"):
            child.add_argument("--tag", required=True)
            child.add_argument("--commit", required=True)
        if command in ("finalize", "upload"):
            child.add_argument("--assets-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "claim":
            output = os.environ.get("GITHUB_OUTPUT")
            if not output:
                raise RuntimeError("GITHUB_OUTPUT is not set")
            output_path = Path(output)
            with output_path.open("a", encoding="utf-8"):
                pass
            release_id = claim(args.repo, args.tag, args.commit, args.name, args.body)
            try:
                record_release_id(output_path, release_id)
            except OSError:
                cleanup(args.repo, release_id, args.tag, args.commit)
                raise
        elif args.command == "upload":
            upload_assets(args.repo, args.release_id, args.assets_dir)
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
