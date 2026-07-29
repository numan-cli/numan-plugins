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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_manifest_entry(name: str, manifest_path: Path | None = None) -> dict:
    """Return the active manifest entry named ``name`` or exit with an error."""
    path = manifest_path or (REPO_ROOT / "manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for entry in manifest.get("active", []):
        if entry["name"] == name:
            return entry
    print(f"FAIL: '{name}' not in manifest.json active[]", file=sys.stderr)
    raise SystemExit(1)


def parse_packaged(path: Path) -> list[dict]:
    """Parse and validate unique target records emitted by package_plugin.py."""
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


def expected_targets(manifest: dict, entry: dict) -> list[str]:
    """Return the manifest targets expected for a plugin after exclusions."""
    excluded = set(entry.get("exclude_targets", []))
    return [target for target in manifest["default_targets"] if target not in excluded]


def build_spec(
    entry: dict,
    packaged_rows: list[dict],
    release_base: str,
    expected: list[str],
) -> dict:
    """Build a registry spec dict from a manifest entry and PACKAGED rows."""
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

    return {
        "owner": entry["owner"],
        "name": entry["name"],
        "description": entry["description"]
        + f" CI-built from {entry['repo']}@{entry['tag']} and signed under the official trust root.",
        "repo": f"https://github.com/{entry['repo']}",
        "type": "plugin",
        "tags": entry["tags"],
        "version": entry["version"],
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


def main() -> int:
    """Validate packaged records and write a registry intake specification."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--packaged", required=True, type=Path)
    ap.add_argument("--assets-dir", required=True, type=Path)
    ap.add_argument("--release-base", required=True, help="release asset download base URL (no trailing slash)")
    ap.add_argument("--out", required=True, type=Path)
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
