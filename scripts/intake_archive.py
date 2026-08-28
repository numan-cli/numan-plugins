#!/usr/bin/env python3
"""Archive a non-binary package (module, script, completion) for registry intake.

The plugin lane cross-compiles Rust; modules, scripts, and completions need no
compilation at all, so their intake is:

  1. Resolve the requested ref (tag, branch, or commit) to its full 40-character
     commit SHA with `git ls-remote`, the same immutable provenance anchor the
     plugin lane records as `source_commit`.
  2. Shallow-clone the upstream repository and check out exactly that SHA.
  3. Verify the declared entry file exists inside the checkout.
  4. Archive the checkout (minus .git) as a deterministic `.tar.gz` -- sorted
     entries, fixed mtime, gzip mtime=0 -- with package_plugin.py's parameters,
     so re-archiving the same commit produces identical bytes.
  5. Emit a spec JSON in the shape numan-registry's scripts/add-package.py
     expects for an `artifact.kind: archive` package, and record the intake in
     manifest-archives.json for repeatable re-intake on a version bump.

The archive spec carries an inline `artifact.sha256`, unlike gen_spec.py's binary
spec which omits it because add-package.py re-downloads and hashes every target
itself; for an archive it pins the single URL it is handed. The spec also omits a
top-level `source` block: the registry index's source field is Rust-shaped (it
requires cargo_name) and non-binary entries leave it out, so re-intake provenance
lives in manifest-archives.json instead.

This script publishes nothing. .github/workflows/intake-archive.yml publishes the
archive through ensure_release_absent.py and release_transaction.py, so this
script stays hermetically testable and the audited release transaction is not
duplicated here.

Usage:
  python3 scripts/intake_archive.py \\
    --git-url https://github.com/owner/repo --ref v1.0.0 \\
    --entry mod.nu --owner owner --name cool-module --type module \\
    --description "..." --tags '["module"]' --nu-version ">=0.114.0" \\
    --release-root https://github.com/numan-cli/numan-plugins/releases/download \\
    --archive-out dist --out spec-owner-cool-module.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

Runner = Callable[..., subprocess.CompletedProcess[str]]

REPO_ROOT = Path(__file__).resolve().parent.parent
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COMMAND_TIMEOUT_SECONDS = 120
FIXED_MTIME = 315532800  # 1980-01-01 UTC; matches package_plugin.py
VALID_TYPES = ("module", "script", "completion")
VALID_GIT_URL_RE = re.compile(r"^(https?://|git://|ssh://|git@[\w.-]+:)")
MAX_ARCHIVE_FILES = 10_000
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024


def normalize_git_url(value: str) -> str:
    """Return a clone URL, expanding a bare `owner/name` slug to a GitHub URL."""
    if VALID_GIT_URL_RE.match(value):
        return value
    return f"https://github.com/{value}"


def validate_git_url(git_url: str) -> None:
    """
    Validate that a clone URL uses a supported scheme and is not option-like.

    Raises:
        ValueError: If the URL starts with '-' (which git would read as an
            option) or does not use https://, http://, git://, ssh://, or git@.
    """
    if git_url.startswith("-"):
        raise ValueError(f"git URL may not start with '-': {git_url!r}")
    if not VALID_GIT_URL_RE.match(git_url):
        raise ValueError(
            f"git URL must use https://, http://, git://, ssh://, or git@: {git_url!r}"
        )


def resolve_ref(git_url: str, ref: str, runner: Runner = subprocess.run) -> str:
    """
    Resolve a tag, branch, or commit ref to its full 40-character commit SHA.

    Annotated tags resolve to the commit they point at, then lightweight tags,
    then branches, then any remaining ref shape.

    Returns:
        str: The resolved commit SHA, or ``ref`` itself when it is already a
            full SHA that the remote does not advertise.

    Raises:
        ValueError: If the ref matches more than one remote ref, or cannot be
            resolved and is not a full commit SHA.
    """
    for candidate in (
        f"refs/tags/{ref}^{{}}",
        f"refs/tags/{ref}",
        f"refs/heads/{ref}",
        ref,
    ):
        result = runner(
            ["git", "ls-remote", git_url, candidate],
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0 or not result.stdout.strip():
            continue
        lines = result.stdout.strip().splitlines()
        if len(lines) > 1:
            raise ValueError(f"ref {ref!r} is ambiguous on {git_url}: {len(lines)} matches")
        return lines[0].split()[0]
    if SHA_RE.fullmatch(ref):
        return ref
    raise ValueError(f"could not resolve ref {ref!r} on {git_url}")


def run_git(args: list[str], runner: Runner, *, failure: str) -> None:
    """Run a git command, raising ValueError with ``failure`` and git's stderr."""
    result = runner(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise ValueError(f"{failure}: {result.stderr.strip()}")


def shallow_clone_at(
    git_url: str,
    sha: str,
    dest: Path,
    runner: Runner = subprocess.run,
) -> None:
    """Clone ``git_url`` into ``dest`` at depth 1 and check out exactly ``sha``."""
    run_git(["init", "--quiet", str(dest)], runner, failure=f"failed to init {dest}")
    run_git(
        ["-C", str(dest), "remote", "add", "origin", git_url],
        runner,
        failure=f"failed to add origin {git_url}",
    )
    run_git(
        ["-C", str(dest), "fetch", "--quiet", "--depth", "1", "origin", sha],
        runner,
        failure=f"failed to fetch {sha} from {git_url}",
    )
    run_git(
        ["-C", str(dest), "checkout", "--quiet", sha],
        runner,
        failure=f"failed to check out {sha}",
    )


def verify_entry(src_dir: Path, entry: str) -> Path:
    """
    Resolve the declared entry file inside a checkout.

    Returns:
        Path: The resolved entry file.

    Raises:
        ValueError: If the entry path is absolute, resolves outside the
            checkout, or is not a regular file.
    """
    if Path(entry).is_absolute():
        raise ValueError(f"entry path must be relative to the checkout: {entry}")
    resolved = (src_dir / entry).resolve()
    try:
        resolved.relative_to(src_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"entry path escapes checkout: {entry}") from exc
    if not resolved.is_file():
        raise ValueError(f"entry file not found in checkout: {entry}")
    return resolved


def sorted_files(root: Path) -> list[Path]:
    """
    List the regular files under ``root`` (excluding .git) in archive order.

    Returns:
        list[Path]: Paths relative to ``root``, sorted by POSIX path.

    Raises:
        ValueError: If a symlink is present, or a path resolves outside ``root``.
    """
    resolved_root = root.resolve()
    files: list[Path] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_symlink():
            raise ValueError(f"symlink not allowed in archive source: {rel.as_posix()}")
        if not path.is_file():
            continue
        try:
            path.resolve().relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(
                f"archive source path resolves outside checkout: {rel.as_posix()}"
            ) from exc
        if rel.parts[0] == ".git":
            continue
        files.append(rel)
    return sorted(files, key=lambda rel: rel.as_posix())


def build_archive(src_dir: Path, out: Path) -> None:
    """
    Write a deterministic .tar.gz of ``src_dir``: sorted entries, fixed metadata.

    Raises:
        ValueError: If the tree exceeds MAX_ARCHIVE_FILES or MAX_ARCHIVE_BYTES.
    """
    rels = sorted_files(src_dir)
    if len(rels) > MAX_ARCHIVE_FILES:
        raise ValueError(f"{len(rels)} files exceeds the archive limit of {MAX_ARCHIVE_FILES}")
    total = sum((src_dir / rel).stat().st_size for rel in rels)
    if total > MAX_ARCHIVE_BYTES:
        raise ValueError(f"{total} bytes exceeds the archive limit of {MAX_ARCHIVE_BYTES}")

    with out.open("wb") as fh:
        gz = gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0)
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for rel in rels:
                full = src_dir / rel
                stat = full.stat()
                info = tarfile.TarInfo(name=rel.as_posix())
                info.size = stat.st_size
                info.mtime = FIXED_MTIME
                info.mode = 0o755 if stat.st_mode & 0o111 else 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                with full.open("rb") as src:
                    tar.addfile(info, src)
        gz.close()


def derive_version(ref: str, resolved_sha: str) -> str:
    """
    Derive the intake version when the caller supplies no explicit one.

    A semver-shaped ref (optionally 'v'-prefixed) becomes the version itself;
    anything else falls back to the 0.1.0-<short-sha> convention the registry
    already uses for branch-pinned script and completion entries.
    """
    match = re.fullmatch(r"v?(\d+\.\d+\.\d+(?:[-+].+)?)", ref)
    if match:
        return match.group(1)
    return f"0.1.0-{resolved_sha[:7]}"


def archive_filename(owner: str, name: str, version: str) -> str:
    """Return the release asset filename for this intake."""
    return f"{owner}-{name}-{version}.tar.gz"


def release_tag(owner: str, name: str, version: str) -> str:
    """Return the release tag for this intake."""
    return f"archive-{owner}-{name}-{version}"


def validate_activation(
    *,
    entry: str,
    activation_kind: str | None,
    activation_import: str | None,
    provisional: bool,
    deferral_reason: str | None,
) -> None:
    """
    Check activation and provisional coherence before any work is done.

    Raises:
        ValueError: If an activation is declared without provisional intake, if
            provisional intake has no non-blank deferral reason, if a deferral
            reason is given without provisional intake, or if a `mod.nu` entry
            is activated with import mode 'module'.
    """
    if activation_kind and not provisional:
        raise ValueError(
            "an activation requires provisional intake (no lifecycle evidence "
            "was provided); pass --provisional with --deferral-reason"
        )
    if provisional:
        if not (deferral_reason or "").strip():
            raise ValueError(
                "provisional intake requires a non-blank deferral reason "
                "(--deferral-reason)"
            )
    elif deferral_reason is not None:
        raise ValueError(
            "a deferral reason is only recorded for provisional intake; "
            "pass --provisional or drop --deferral-reason"
        )
    # Numan activates a module with `use "<entry file>"`, the file form, so Nu's
    # directory-name-becomes-module-name convention for mod.nu never applies: a
    # mod.nu entry imported as 'module' would expose commands under a module
    # literally named 'mod'. Import mode 'all' imports them unprefixed instead.
    if (
        activation_kind == "nu-module"
        and Path(entry).name == "mod.nu"
        and (activation_import or "module") == "module"
    ):
        raise ValueError(
            "a 'mod.nu' entry requires activation import 'all'; import 'module' "
            "would activate a module named 'mod'"
        )


def parse_tags(raw: str) -> list[str]:
    """
    Parse the --tags JSON array.

    Raises:
        ValueError: If the value is not a JSON array of strings.
        json.JSONDecodeError: If the value is not valid JSON.
    """
    tags = json.loads(raw)
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("--tags must be a JSON array of strings")
    return tags


def build_spec(
    *,
    owner: str,
    name: str,
    description: str,
    git_url: str,
    pkg_type: str,
    tags: list[str],
    version: str,
    nu_version: str,
    entry: str,
    url: str,
    sha256: str,
    activation_kind: str | None = None,
    activation_import: str | None = None,
    provisional: bool = False,
    deferral_reason: str | None = None,
) -> dict:
    """
    Build the numan-registry intake spec for an archive-kind package.

    `verified_with` is never emitted: add-package.py aborts when --provisional is
    combined with a spec that merely contains the key, and a non-provisional
    archive intake records its lifecycle evidence downstream after prove.
    """
    evidence = (
        {"evidence_tier": "provisional", "deferral_reason": (deferral_reason or "").strip()}
        if provisional
        else {}
    )
    spec: dict = {
        "owner": owner,
        "name": name,
        "description": description,
        "repo": git_url,
        "type": pkg_type,
        "tags": tags,
        "version": version,
        "nu_version": nu_version,
        **evidence,
        "artifact": {
            "kind": "archive",
            "url": url,
            "entry": entry,
            "sha256": sha256,
        },
    }
    if activation_kind:
        activation = {"kind": activation_kind}
        if activation_import:
            activation["import"] = activation_import
        spec["activation"] = activation
    return spec


def record_archive_manifest(
    path: Path,
    *,
    git_url: str,
    ref: str,
    resolved_sha: str,
    entry: str,
    name: str,
    owner: str,
    pkg_type: str,
) -> None:
    """
    Upsert this intake's re-intake record into manifest-archives.json.

    Raises:
        ValueError: If the existing file is not a JSON array of objects.
        json.JSONDecodeError: If the existing file is not valid JSON.
    """
    entries: list[dict] = []
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list) or not all(
            isinstance(entry_record, dict) for entry_record in entries
        ):
            raise ValueError(f"{path} must contain a JSON array of objects")
    record = {
        "git": git_url,
        "ref": ref,
        "resolved_sha": resolved_sha,
        "entry": entry,
        "name": name,
        "owner": owner,
        "type": pkg_type,
    }
    entries = [
        existing
        for existing in entries
        if not (existing.get("owner") == owner and existing.get("name") == name)
    ]
    entries.append(record)
    entries.sort(key=lambda existing: (existing.get("owner", ""), existing.get("name", "")))
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Archive an upstream ref, emit its registry spec, and record the intake."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--git-url", default=None, help="upstream clone URL")
    ap.add_argument("--repo", default=None, help="upstream clone URL or owner/name slug")
    ap.add_argument("--ref", required=True, help="upstream tag, branch, or commit to archive")
    ap.add_argument("--entry", required=True, help="entry file path inside the repository")
    ap.add_argument("--owner", required=True, help="registry package owner")
    ap.add_argument("--name", required=True, help="registry package name")
    ap.add_argument("--type", required=True, choices=VALID_TYPES, dest="pkg_type")
    ap.add_argument("--description", required=True)
    ap.add_argument("--tags", required=True, help="JSON array of tag strings")
    ap.add_argument("--nu-version", required=True, help="Nu compatibility range")
    ap.add_argument(
        "--version",
        default=None,
        help="version for this intake; derived from --ref when omitted "
        "(semver-shaped refs keep their version, others become 0.1.0-<short-sha>)",
    )
    ap.add_argument("--activation-kind", default=None, help="activation kind, e.g. nu-module")
    ap.add_argument("--activation-import", default=None, choices=("module", "all"))
    ap.add_argument(
        "--provisional",
        action="store_true",
        help="Emit evidence_tier + deferral_reason for an intake whose "
        "lifecycle-prove is deferred",
    )
    ap.add_argument(
        "--deferral-reason",
        default=None,
        help="Why lifecycle-prove is deferred; required with --provisional and "
        "rejected without it",
    )
    ap.add_argument(
        "--release-root",
        required=True,
        help="releases DOWNLOAD ROOT, e.g. "
        "https://github.com/numan-cli/numan-plugins/releases/download; the "
        "spec URL appends /<tag>/<archive> once the version is derived",
    )
    ap.add_argument("--archive-out", type=Path, default=Path("dist"))
    ap.add_argument("--out", type=Path, required=True, help="spec JSON destination")
    ap.add_argument(
        "--manifest-archives",
        type=Path,
        default=REPO_ROOT / "manifest-archives.json",
    )
    args = ap.parse_args(argv)

    try:
        if not (args.git_url or args.repo):
            raise ValueError("either --git-url or --repo is required")
        git_url = normalize_git_url(args.git_url or args.repo)
        validate_git_url(git_url)
        validate_activation(
            entry=args.entry,
            activation_kind=args.activation_kind,
            activation_import=args.activation_import,
            provisional=args.provisional,
            deferral_reason=args.deferral_reason,
        )
        tags = parse_tags(args.tags)

        resolved_sha = resolve_ref(git_url, args.ref)
        version = args.version or derive_version(args.ref, resolved_sha)
        tag = release_tag(args.owner, args.name, version)
        archive_name = archive_filename(args.owner, args.name, version)

        args.archive_out.mkdir(parents=True, exist_ok=True)
        archive_path = args.archive_out / archive_name
        if archive_path.exists():
            raise ValueError(f"archive already exists, refusing to overwrite: {archive_path}")

        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "src"
            shallow_clone_at(git_url, resolved_sha, src_dir)
            verify_entry(src_dir, args.entry)
            build_archive(src_dir, archive_path)

        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        spec = build_spec(
            owner=args.owner,
            name=args.name,
            description=args.description,
            git_url=git_url,
            pkg_type=args.pkg_type,
            tags=tags,
            version=version,
            nu_version=args.nu_version,
            entry=args.entry,
            url=f"{args.release_root.rstrip('/')}/{tag}/{archive_name}",
            sha256=digest,
            activation_kind=args.activation_kind,
            activation_import=args.activation_import,
            provisional=args.provisional,
            deferral_reason=args.deferral_reason,
        )
        args.out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        record_archive_manifest(
            args.manifest_archives,
            git_url=git_url,
            ref=args.ref,
            resolved_sha=resolved_sha,
            entry=args.entry,
            name=args.name,
            owner=args.owner,
            pkg_type=args.pkg_type,
        )

        # Machine-readable line for the workflow to collect, like package_plugin.py's
        # PACKAGED row: resolved_sha|version|tag|archive|sha256
        print(f"ARCHIVED\t{resolved_sha}\t{version}\t{tag}\t{archive_name}\t{digest}")
        print(
            f"  archived {git_url}@{args.ref} -> {resolved_sha}\n"
            f"  wrote {archive_path} ({archive_path.stat().st_size} bytes) sha256={digest}\n"
            f"  wrote {args.out} and recorded re-intake in {args.manifest_archives}",
            file=sys.stderr,
        )
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
