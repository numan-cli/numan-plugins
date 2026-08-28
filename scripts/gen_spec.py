#!/usr/bin/env python3
"""Generate a numan-registry package spec from packaged plugin assets.

Consumes the `PACKAGED\\t<target>\\t<filename>\\t<sha256>\\t<exe>` lines emitted
by package_plugin.py (collected across all matrix jobs) plus the plugin's
manifest.json entry, and writes a spec JSON in the exact shape numan-registry's
scripts/add-package.py expects for a `kind: binary` artifact.

The spec intentionally OMITS sha256: add-package.py re-downloads each asset and
computes the hash itself (never hand-typed). The sha256 in the PACKAGED lines is
only used here to sanity-check the uploaded asset matches what we built.

Provenance is emitted as a top-level `source: {git, rev, cargo_name}` block
(from the manifest entry) so numan-registry `add-package.py` can pass it into
the signed index.

`--provisional --deferral-reason "<why>"` emits the provisional evidence tier
(`evidence_tier` plus `deferral_reason`) and drops `verified_with`, for a plugin
that builds but whose lifecycle-prove is deferred (e.g. it needs cloud
credentials). numan-registry's `add-package.py --provisional` accepts that spec.

Usage:
  python scripts/gen_spec.py \\
    --name nu_plugin_regex \\
    --packaged packaged.tsv \\
    --assets-dir dl \\
    --release-base https://github.com/<org>/numan-plugins/releases/download/nu_plugin_regex-0.22.0 \\
    --out spec.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from validate_manifest import expected_targets, validate_upstream_repo

REPO_ROOT = Path(__file__).resolve().parent.parent
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_manifest_entry(name: str, manifest_path: Path | None = None) -> dict:
    """
    Find the active manifest entry with the specified name.
    
    Parameters:
        name (str): Manifest entry name to find.
        manifest_path (Path | None): Path to the manifest file, or the repository manifest when omitted.
    
    Returns:
        dict: The matching active manifest entry.
    
    Raises:
        SystemExit: If no active manifest entry matches the specified name.
    """
    path = manifest_path or (REPO_ROOT / "manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for entry in manifest.get("active", []):
        if entry["name"] == name:
            return entry
    print(f"FAIL: '{name}' not in manifest.json active[]", file=sys.stderr)
    raise SystemExit(1)


def parse_packaged(path: Path) -> list[dict]:
    """
    Parse and validate packaged artifact records from a TSV file.
    
    Returns:
    	list[dict]: Unique target records containing the target, filename, SHA-256 hash, and executable path.
    
    Raises:
    	SystemExit: If a record is malformed, contains a duplicate target or invalid SHA-256 hash, or no records are found.
    """
    rows = []
    targets = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("PACKAGED\t"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            print(f"FAIL: malformed PACKAGED row: {line}", file=sys.stderr)
            raise SystemExit(1)
        _, target, filename, sha256, exe = parts
        if target in targets:
            print(f"FAIL: duplicate PACKAGED target: {target}", file=sys.stderr)
            raise SystemExit(1)
        if not SHA256_RE.fullmatch(sha256):
            print(f"FAIL: invalid sha256 for {target}: {sha256}", file=sys.stderr)
            raise SystemExit(1)
        targets.add(target)
        rows.append({"target": target, "filename": filename, "sha256": sha256, "exe": exe})
    if not rows:
        print(f"FAIL: no PACKAGED rows in {path}", file=sys.stderr)
        raise SystemExit(1)
    return rows


def verify_packaged_assets(rows: list[dict], assets_dir: Path) -> None:
    """Verify packaged assets match records and reject orphan archives.

    Every record must resolve to a file whose SHA-256 matches. Every file in
    ``assets_dir`` must also be named by a record — otherwise a successful
    archive upload paired with a failed package-record upload would leave an
    orphan that ``release_transaction upload`` would publish outside the spec.
    """
    if not assets_dir.is_dir():
        raise ValueError(f"assets dir not found: {assets_dir}")
    expected_names = {row["filename"] for row in rows}
    unexpected = sorted(
        path.name
        for path in assets_dir.iterdir()
        if path.is_file() and path.name not in expected_names
    )
    if unexpected:
        raise ValueError(
            "orphan assets without package records: " + ", ".join(unexpected)
        )
    for row in rows:
        asset = assets_dir / row["filename"]
        if not asset.is_file():
            raise ValueError(f"packaged asset not found: {asset}")
        actual = hashlib.sha256(asset.read_bytes()).hexdigest()
        if actual != row["sha256"]:
            raise ValueError(
                f"packaged asset hash mismatch for {asset.name}: "
                f"expected {row['sha256']}, got {actual}"
            )


def derive_snapshot_version(source_commit: str, date: str) -> str:
    """Derive a synthetic prerelease version for a commit-snapshot entry.

    Format: 0.0.0-snapshot.<YYYYMMDD>.<7-char-sha>. The date prefix guarantees
    snapshots sort monotonically under SemVer prerelease rules regardless of
    SHA ordering, which the resolver and update command depend on.
    """
    return f"0.0.0-snapshot.{date}.{source_commit[:7]}"


def build_spec(
    entry: dict,
    packaged_rows: list[dict],
    release_base: str,
    expected: list[str],
    *,
    partial: bool = False,
    snapshot_date: str | None = None,
    provisional: bool = False,
    deferral_reason: str | None = None,
) -> dict:
    """
    Build a registry specification from manifest metadata and packaged artifact records.
    
    Parameters:
        entry (dict): Manifest metadata for the plugin.
        packaged_rows (list[dict]): Validated packaged artifacts keyed by target.
        release_base (str): Base URL for released artifact files.
        expected (list[str]): Target names required in the specification.
        partial (bool): When True, allow the spec to ship with only the targets
            that succeeded instead of requiring every expected target.
        snapshot_date (str | None): Override for the YYYYMMDD date used in a
            commit-snapshot version; defaults to today (UTC). Exists for
            deterministic testing.
        provisional (bool): When True, emit `evidence_tier` and `deferral_reason`
            in place of `verified_with` because lifecycle-prove is deferred.
        deferral_reason (str | None): Why lifecycle-prove is deferred. Required
            when `provisional` is True, rejected otherwise.

    Returns:
        dict: Registry specification containing plugin metadata and binary artifact targets.
    
    Raises:
        ValueError: If packaged targets include unexpected targets, if targets are
            missing and `partial` is False, if `partial` is True but no target
            succeeded, if `provisional` is True without a non-blank
            `deferral_reason`, if a `deferral_reason` is given without
            `provisional`, or if `provisional` is True while `entry` already
            records `verified_with` evidence.
    """
    actual = {row["target"] for row in packaged_rows}
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    if extra:
        details = [f"unexpected targets: {', '.join(extra)}"]
        if missing:
            details.append(f"missing targets: {', '.join(missing)}")
        raise ValueError("; ".join(details))
    if partial and not actual:
        raise ValueError("no targets packaged; at least one target must succeed")
    if missing:
        if not partial:
            raise ValueError(f"missing targets: {', '.join(missing)}")
        print(
            f"WARN: partial spec — missing target(s): {', '.join(missing)}",
            file=sys.stderr,
        )
    base = release_base.rstrip("/")
    targets = {}
    for r in packaged_rows:
        targets[r["target"]] = {
            "url": f"{base}/{r['filename']}",
            "executable_path": r["exe"],
        }

    validate_upstream_repo(entry)
    upstream_repo = entry.get("upstream_repo")

    intake_mode = entry.get("intake_mode", "tagged")
    if intake_mode == "commit-snapshot":
        date = snapshot_date or datetime.now(timezone.utc).strftime("%Y%m%d")
        if not re.fullmatch(r"\d{8}", date):
            raise ValueError(f"snapshot_date must be YYYYMMDD, got: {date!r}")
        version = derive_snapshot_version(entry["source_commit"], date)
        description_suffix = (
            f" CI-built from {entry['repo']}@{entry['source_commit'][:7]} "
            "(commit snapshot, no tagged release) and pinned + hash-verified + signed downstream in numan-registry."
        )
    else:
        version = entry["version"]
        description_suffix = (
            f" CI-built from {entry['repo']}@{entry['tag']} and pinned + hash-verified + signed downstream in numan-registry."
        )

    description = entry["description"] + description_suffix
    source = {
        "git": f"https://github.com/{entry['repo']}",
        "rev": entry["source_commit"],
        "cargo_name": entry["plugin_bin"],
    }
    if upstream_repo is not None:
        description += f" (numan-maintained fork; upstream: {upstream_repo})"
        source["upstream"] = f"https://github.com/{upstream_repo}"

    if provisional:
        if not (deferral_reason or "").strip():
            raise ValueError(
                "provisional intake requires a non-blank deferral reason "
                "(--deferral-reason)"
            )
        if entry["verified_with"]:
            raise ValueError(
                "provisional intake rejected: verified_with is non-empty "
                f"({', '.join(entry['verified_with'])}), so the plugin already has "
                "lifecycle evidence"
            )
    elif deferral_reason is not None:
        raise ValueError(
            "a deferral reason is only recorded for provisional intake; "
            "pass --provisional or drop --deferral-reason"
        )

    # numan-registry's add-package.py aborts when --provisional is combined with a
    # spec that merely CONTAINS verified_with, and its validate_spec only waives the
    # lifecycle-evidence check when the key is absent, so a provisional spec has to
    # omit verified_with rather than carry an empty list.
    evidence = (
        {"evidence_tier": "provisional", "deferral_reason": deferral_reason.strip()}
        if provisional
        else {"verified_with": entry["verified_with"]}
    )

    spec = {
        "owner": entry["owner"],
        "name": entry["name"],
        "description": description,
        "repo": f"https://github.com/{entry['repo']}",
        "type": "plugin",
        "tags": entry["tags"],
        "version": version,
        "nu_version": entry["nu_version"],
        **evidence,
        "source": source,
        "artifact": {
            "kind": "binary",
            "targets": {k: targets[k] for k in sorted(targets)},
        },
    }
    if intake_mode == "commit-snapshot":
        spec["provenance"] = "commit-snapshot"
    return spec


def main() -> int:
    """Validate packaged records and write a registry intake specification."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--packaged", required=True, type=Path)
    ap.add_argument("--assets-dir", required=True, type=Path)
    ap.add_argument("--release-base", required=True, help="release asset download base URL (no trailing slash)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--partial",
        action="store_true",
        help="Emit a spec with only the targets that packaged successfully instead of failing on missing targets",
    )
    ap.add_argument(
        "--snapshot-date",
        help="YYYYMMDD override for commit-snapshot versions; must match the "
        "date the workflow used to derive the package/release version, or "
        "the generated spec's version won't match the published release tag",
    )
    ap.add_argument(
        "--provisional",
        action="store_true",
        help="Emit evidence_tier + deferral_reason instead of verified_with, for a "
        "plugin that builds but whose lifecycle-prove is deferred",
    )
    ap.add_argument(
        "--deferral-reason",
        default=None,
        help="Why lifecycle-prove is deferred; required with --provisional and "
        "rejected without it",
    )
    args = ap.parse_args()

    manifest = json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf-8"))
    entry = load_manifest_entry(args.name)
    rows = parse_packaged(args.packaged)
    try:
        verify_packaged_assets(rows, args.assets_dir)
        spec = build_spec(
            entry,
            rows,
            args.release_base,
            expected_targets(manifest, entry),
            partial=args.partial,
            snapshot_date=args.snapshot_date,
            provisional=args.provisional,
            deferral_reason=args.deferral_reason,
        )
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    args.out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out} with {len(spec['artifact']['targets'])} target(s): "
        f"{', '.join(sorted(spec['artifact']['targets']))}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
