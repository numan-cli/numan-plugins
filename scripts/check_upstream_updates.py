#!/usr/bin/env python3
"""Stage 1: Audit and check active plugins in manifest.json for upstream releases & Nu version bumps.

Usage:
  python scripts/check_upstream_updates.py [--manifest manifest.json] [--report report.md] [--json]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"
USER_AGENT = "numan-plugins-checker/1.0"


def fetch_github_json(endpoint: str) -> dict | list | None:
    """Fetch JSON from GitHub API with optional auth token."""
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github.v3+json",
        },
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Warning: failed to fetch {url}: {e}", file=sys.stderr)
        return None


def fetch_cargo_toml_nu_dep(repo: str, ref: str = "HEAD") -> str | None:
    """Fetch Cargo.toml and extract nu-plugin / nu-protocol dependency version."""
    endpoint = f"repos/{repo}/contents/Cargo.toml"
    if ref != "HEAD":
        endpoint += f"?ref={ref}"
    data = fetch_github_json(endpoint)
    if isinstance(data, dict) and "content" in data:
        try:
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            # match nu-plugin = "0.115.0" or nu-plugin = { version = "0.115" }
            m = re.search(r'nu-plugin\s*=\s*(?:\{[^}]*version\s*=\s*)?["\']([^"\']+)["\']', content)
            if m:
                return m.group(1)
            # fallback to nu-protocol
            m_proto = re.search(r'nu-protocol\s*=\s*(?:\{[^}]*version\s*=\s*)?["\']([^"\']+)["\']', content)
            if m_proto:
                return m_proto.group(1)
        except Exception:
            return None
    return None


def fetch_latest_tags(repo: str) -> list[str]:
    """Fetch recent tags for repository."""
    data = fetch_github_json(f"repos/{repo}/tags?per_page=5")
    if isinstance(data, list):
        return [item.get("name", "") for item in data if isinstance(item, dict) and "name" in item]
    return []


def audit_entry(entry: dict) -> dict:
    """Audit single manifest entry against upstream repository."""
    repo = entry["repo"]
    name = entry["name"]
    current_tag = entry.get("tag")
    current_nu = entry.get("nu_version", "")
    current_commit = entry.get("source_commit", "")

    tags = fetch_latest_tags(repo)
    cargo_nu = fetch_cargo_toml_nu_dep(repo)

    has_new_tag = False
    newest_tag = tags[0] if tags else None
    if newest_tag and current_tag and newest_tag != current_tag:
        has_new_tag = True

    status = "UP_TO_DATE"
    if cargo_nu and ("0.115" in cargo_nu or "0.116" in cargo_nu):
        if has_new_tag:
            status = "READY_FOR_BUMP"
        else:
            status = "UPSTREAM_NU_BUMP_NO_TAG"
    elif has_new_tag:
        status = "NEW_TAG_AVAILABLE"

    return {
        "repo": repo,
        "name": name,
        "current_tag": current_tag,
        "current_commit": current_commit[:7] if current_commit else "",
        "current_nu": current_nu,
        "latest_tags": tags[:3],
        "newest_tag": newest_tag,
        "cargo_nu_dep": cargo_nu or "unknown",
        "has_new_tag": has_new_tag,
        "status": status,
    }


def generate_markdown_report(results: list[dict]) -> str:
    lines = [
        "# Upstream Plugin Audit Report",
        "",
        f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}_",
        "",
        "| Package | Upstream Repo | Current Tag | Cargo.toml nu-dep | Latest Upstream Tags | Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in results:
        tags_str = ", ".join(f"`{t}`" for t in r["latest_tags"]) if r["latest_tags"] else "—"
        cur_tag = f"`{r['current_tag']}`" if r["current_tag"] else "—"
        status_badge = r["status"]
        if r["status"] == "READY_FOR_BUMP":
            status_badge = "🚀 **READY_FOR_BUMP**"
        elif r["status"] == "UPSTREAM_NU_BUMP_NO_TAG":
            status_badge = "⚡ _NU_BUMP (no tag)_"
        elif r["status"] == "NEW_TAG_AVAILABLE":
            status_badge = "🏷️ _NEW_TAG_"

        lines.append(
            f"| `{r['name']}` | [{r['repo']}](https://github.com/{r['repo']}) | {cur_tag} | `{r['cargo_nu_dep']}` | {tags_str} | {status_badge} |"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check active plugins for upstream updates.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help="Path to manifest.json")
    parser.add_argument("--report", type=Path, default=None, help="Path to output markdown report")
    parser.add_argument("--json", action="store_true", help="Output JSON results to stdout")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Error: manifest file {args.manifest} does not exist", file=sys.stderr)
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    active = manifest.get("active", [])

    print(f"Auditing {len(active)} active plugins from {args.manifest.name}...")
    results = []
    for entry in active:
        res = audit_entry(entry)
        results.append(res)
        print(f"  • {res['name']}: {res['status']} (Cargo nu-dep: {res['cargo_nu_dep']}, newest tag: {res['newest_tag']})")

    report_md = generate_markdown_report(results)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report_md, encoding="utf-8")
        print(f"\nReport written to {args.report}")

    gh_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary:
        with open(gh_summary, "a", encoding="utf-8") as f:
            f.write(report_md)

    updates_found = any(r["status"] in ("READY_FOR_BUMP", "NEW_TAG_AVAILABLE") for r in results)
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"updates_found={'true' if updates_found else 'false'}\n")

    if args.json:
        print(json.dumps(results, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
