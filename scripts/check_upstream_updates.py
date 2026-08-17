#!/usr/bin/env python3
"""Stage 1: Audit and check active plugins in manifest.json for upstream releases & Nu version bumps.

The audit fails closed: any upstream API error marks the entry FETCH_ERROR and the
script exits non-zero rather than reporting a possibly false "up to date" signal.

Usage:
  python scripts/check_upstream_updates.py [--manifest manifest.json] [--report report.md] [--json]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"
USER_AGENT = "numan-plugins-checker/1.0"
HTTP_SCHEMES = frozenset({"https", "http"})


class FetchError(Exception):
    """Raised when a GitHub API request fails.

    Attributes:
        status_code: HTTP status code when the failure is an HTTP error response,
            otherwise None.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def ensure_http_url(url: str) -> None:
    """Raise ValueError unless *url* is an http(s) URL with a host."""
    if not isinstance(url, str):
        raise ValueError(f"URL must use http(s), got {url!r}")
    parsed = urllib.parse.urlparse(url)
    try:
        has_host = bool(parsed.hostname)
    except ValueError:
        has_host = False
    if parsed.scheme.lower() not in HTTP_SCHEMES or not has_host:
        raise ValueError(f"URL must use http(s), got {url!r}")


class _HttpOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject any redirect whose target fails the http(s) scheme guard."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ensure_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_opener() -> urllib.request.OpenerDirector:
    """Return an opener whose redirects are also constrained to http(s)."""
    return urllib.request.build_opener(_HttpOnlyRedirectHandler())


def fetch_github_json(endpoint: str) -> dict | list:
    """Fetch JSON from GitHub API with optional auth token.

    Raises:
        FetchError: If the request fails or the response cannot be decoded.
    """
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    ensure_http_url(url)
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
        with http_opener().open(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} from {url}", status_code=e.code) from e
    except urllib.error.URLError as e:
        raise FetchError(f"network error for {url}: {e.reason}") from e
    except Exception as e:
        raise FetchError(f"failed to fetch {url}: {e}") from e


def fetch_cargo_toml_nu_dep(repo: str, ref: str = "HEAD") -> str | None:
    """Fetch Cargo.toml and extract nu-plugin / nu-protocol dependency version.

    A 404 (no Cargo.toml at the repository root) is treated as "unknown" rather
    than a failure; all other API errors propagate.

    Raises:
        FetchError: If the request fails for a reason other than a missing file.
    """
    endpoint = f"repos/{repo}/contents/Cargo.toml"
    if ref != "HEAD":
        endpoint += f"?ref={ref}"
    try:
        data = fetch_github_json(endpoint)
    except FetchError as e:
        if e.status_code == 404:
            return None
        raise
    if isinstance(data, dict) and "content" in data:
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        # match nu-plugin = "0.115.0" or nu-plugin = { version = "0.115" }
        m = re.search(r'nu-plugin\s*=\s*(?:\{[^}]*version\s*=\s*)?["\']([^"\']+)["\']', content)
        if m:
            return m.group(1)
        # fallback to nu-protocol
        m_proto = re.search(r'nu-protocol\s*=\s*(?:\{[^}]*version\s*=\s*)?["\']([^"\']+)["\']', content)
        if m_proto:
            return m_proto.group(1)
    return None


def fetch_latest_tags(repo: str) -> list[dict]:
    """Fetch recent tags for repository with the commit each tag points at."""
    data = fetch_github_json(f"repos/{repo}/tags?per_page=5")
    tags = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict) or "name" not in item:
                continue
            commit_sha = None
            commit = item.get("commit")
            if isinstance(commit, dict) and isinstance(commit.get("sha"), str):
                commit_sha = commit["sha"]
            tags.append({"name": item["name"], "commit_sha": commit_sha})
    return tags


def resolve_tag_commit(repo: str, tag: str) -> str | None:
    """Resolve a git tag name to the commit SHA it currently points at.

    Returns:
        The target commit SHA, or None when the tag no longer exists upstream
        (HTTP 404).

    Raises:
        FetchError: If the resolution request fails for another reason.
    """
    quoted = urllib.parse.quote(tag, safe="")
    try:
        data = fetch_github_json(f"repos/{repo}/commits/{quoted}")
    except FetchError as e:
        if e.status_code == 404:
            return None
        raise
    if isinstance(data, dict) and isinstance(data.get("sha"), str):
        return data["sha"]
    raise FetchError(f"unexpected response resolving {repo}@{tag}")


def parse_version(version: str) -> tuple[int, ...] | None:
    """Parse a dotted numeric version into a 3-component comparable tuple.

    Missing components are padded with zeros so "0.115" == (0, 115, 0).
    """
    m = re.match(r"(\d+(?:\.\d+){0,3})", version.strip())
    if not m:
        return None
    parts = [int(part) for part in m.group(1).split(".")]
    return tuple((parts + [0, 0, 0])[:3])


def manifest_nu_upper_bound(nu_version: str) -> tuple[int, ...] | None:
    """Extract the exclusive upper bound (X.Y.Z) from a manifest nu_version range.

    e.g. '>=0.114.0 <0.115.0' -> (0, 115, 0). Falls back to parsing the whole
    value when the range has no '<' constraint.
    """
    for part in re.split(r"[\s,]+", nu_version):
        m = re.match(r"<(\d+(?:\.\d+){0,3})", part.strip())
        if m:
            return parse_version(m.group(1))
    return parse_version(nu_version)


def nu_needs_bump(manifest_nu: str, upstream_nu: str) -> bool:
    """Return True when upstream's Cargo.toml nu dep is at or beyond the manifest's supported range."""
    bound = manifest_nu_upper_bound(manifest_nu)
    upstream = parse_version(upstream_nu)
    if bound is None or upstream is None:
        return False
    return upstream >= bound


def _error_result(entry: dict, error: str) -> dict:
    """Build an audit result that fails closed for an upstream API error."""
    current_commit = entry.get("source_commit", "")
    return {
        "repo": entry["repo"],
        "name": entry["name"],
        "current_tag": entry.get("tag"),
        "current_commit": current_commit[:7] if current_commit else "",
        "current_nu": entry.get("nu_version", ""),
        "latest_tags": [],
        "newest_tag": None,
        "cargo_nu_dep": "unknown",
        "has_new_tag": False,
        "nu_bump": False,
        "error": error,
        "status": "FETCH_ERROR",
    }


def _check_tag_moved(repo: str, current_tag: str | None, current_commit: str) -> bool:
    """Check if current tag moved to a different commit or no longer exists."""
    if not current_tag:
        return False
    resolved = resolve_tag_commit(repo, current_tag)
    return resolved is None or bool(current_commit and resolved.lower() != current_commit.lower())


def _check_has_new_tag(
    repo: str,
    current_tag: str | None,
    current_commit: str,
    newest_tag: str | None,
) -> bool:
    """Check if upstream has a newer tag than the current entry."""
    if not newest_tag:
        return False
    if not current_tag:
        # commit-snapshot entries pin no tag; any upstream tag that does not
        # already point at the snapshot commit is a re-intake candidate.
        resolved_newest = resolve_tag_commit(repo, newest_tag)
        snapshot_matches = bool(
            resolved_newest and current_commit and resolved_newest.lower() == current_commit.lower()
        )
        return not snapshot_matches
    return newest_tag != current_tag


def _determine_status(tag_moved: bool, nu_bump: bool, has_new_tag: bool) -> str:
    """Determine audit status from tag movement, Nu bump requirement, and new tag availability."""
    if tag_moved:
        return "TAG_PROVENANCE_MISMATCH"
    if nu_bump and has_new_tag:
        return "READY_FOR_BUMP"
    if nu_bump:
        return "UPSTREAM_NU_BUMP_NO_TAG"
    if has_new_tag:
        return "NEW_TAG_AVAILABLE"
    return "UP_TO_DATE"


def audit_entry(entry: dict) -> dict:
    """Audit single manifest entry against upstream repository."""
    repo = entry["repo"]
    name = entry["name"]
    current_tag = entry.get("tag")
    current_nu = entry.get("nu_version", "")
    current_commit = entry.get("source_commit", "")

    try:
        tags = fetch_latest_tags(repo)
        cargo_nu = fetch_cargo_toml_nu_dep(repo)
        newest_tag = tags[0]["name"] if tags else None
        tag_moved = _check_tag_moved(repo, current_tag, current_commit)
        has_new_tag = _check_has_new_tag(repo, current_tag, current_commit, newest_tag)
    except FetchError as e:
        return _error_result(entry, str(e))

    nu_bump = bool(cargo_nu) and nu_needs_bump(current_nu, cargo_nu)
    status = _determine_status(tag_moved, nu_bump, has_new_tag)

    return {
        "repo": repo,
        "name": name,
        "current_tag": current_tag,
        "current_commit": current_commit[:7] if current_commit else "",
        "current_nu": current_nu,
        "latest_tags": [t["name"] for t in tags[:3]],
        "newest_tag": newest_tag,
        "cargo_nu_dep": cargo_nu or "unknown",
        "has_new_tag": has_new_tag,
        "nu_bump": nu_bump,
        "status": status,
    }


def _truncate(text: str, limit: int) -> str:
    """Flatten and shorten a message for use inside a markdown table cell."""
    text = text.replace("\n", " ").replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def generate_markdown_report(results: list[dict]) -> str:
    lines = [
        "# Upstream Plugin Audit Report",
        "",
        f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}_",
        "",
        "| Package | Upstream Repo | Current Tag | Cargo.toml nu-dep | Latest Upstream Tags | Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    badges = {
        "READY_FOR_BUMP": "🚀 **READY_FOR_BUMP**",
        "UPSTREAM_NU_BUMP_NO_TAG": "⚡ _NU_BUMP (no tag)_",
        "NEW_TAG_AVAILABLE": "🏷️ _NEW_TAG_",
        "TAG_PROVENANCE_MISMATCH": "⚠️ **TAG_MOVED**",
        "FETCH_ERROR": "❌ **FETCH_ERROR**",
    }

    for r in results:
        tags_str = ", ".join(f"`{t}`" for t in r["latest_tags"]) if r["latest_tags"] else "—"
        cur_tag = f"`{r['current_tag']}`" if r["current_tag"] else "—"
        status_badge = badges.get(r["status"], r["status"])
        if r.get("error"):
            status_badge += f"<br><small>{_truncate(r['error'], 90)}</small>"

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
        print(
            f"  • {res['name']}: {res['status']} "
            f"(Cargo nu-dep: {res['cargo_nu_dep']}, newest tag: {res['newest_tag']})"
        )
        if res["status"] == "FETCH_ERROR":
            print(f"      {res['error']}", file=sys.stderr)

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

    failures = sum(1 for r in results if r["status"] == "FETCH_ERROR")
    if failures:
        print(
            f"ERROR: {failures} upstream fetch(es) failed; audit is incomplete and "
            "cannot report readiness",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
