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

from validate_manifest import expected_targets

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
    """Verify that every recorded asset exists and matches its recorded SHA-256."""
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
    snapshot_date: str | None = None,
) -> dict:
    """
    Build a registry specification from manifest metadata and packaged artifact records.
    
    Parameters:
        entry (dict): Manifest metadata for the plugin.
        packaged_rows (list[dict]): Validated packaged artifacts keyed by target.
        release_base (str): Base URL for released artifact files.
        expected (list[str]): Target names required in the specification.
        snapshot_date (str | None): Override for the YYYYMMDD date used in a
            commit-snapshot version; defaults to today (UTC). Exists for
            deterministic testing.
    
    Returns:
        dict: Registry specification containing plugin metadata and binary artifact targets.
    
    Raises:
        ValueError: If packaged targets are missing or include unexpected targets.
    """
    actual = {row["target"] for row in packaged_rows}
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing targets: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected targets: {', '.join(extra)}")
        raise ValueError("; ".join(details))
    base = release_base.rstrip("/")
    targets = {}
    for r in packaged_rows:
        targets[r["target"]] = {
            "url": f"{base}/{r['filename']}",
            "executable_path": r["exe"],
        }

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

    spec = {
        "owner": entry["owner"],
        "name": entry["name"],
        "description": entry["description"] + description_suffix,
        "repo": f"https://github.com/{entry['repo']}",
        "type": "plugin",
        "tags": entry["tags"],
        "version": version,
        "nu_version": entry["nu_version"],
        "verified_with": entry["verified_with"],
        "source": {
            "git": f"https://github.com/{entry['repo']}",
            "rev": entry["source_commit"],
            "cargo_name": entry["plugin_bin"],
        },
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
        "--snapshot-date",
        help="YYYYMMDD override for commit-snapshot versions; must match the "
        "date the workflow used to derive the package/release version, or "
        "the generated spec's version won't match the published release tag",
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
            snapshot_date=args.snapshot_date,
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
