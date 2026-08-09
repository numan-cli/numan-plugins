#!/usr/bin/env python3
"""Validate manifest.json structure and optionally verify upstream tags exist."""
import json
import subprocess
import sys
from pathlib import Path

REQUIRED_FIELDS = [
    "repo", "name", "owner", "plugin_bin", "tag", "version",
    "nu_version", "description", "tags"
]

def validate_structure(manifest):
    """Check required fields and value types."""
    errors = []
    
    if "active" not in manifest:
        errors.append("Missing 'active' array")
        return errors
    
    for i, entry in enumerate(manifest["active"]):
        for field in REQUIRED_FIELDS:
            if field not in entry:
                errors.append(f"active[{i}] ({entry.get('name', '?')}): missing '{field}'")
        
        # Check nu_version format
        nv = entry.get("nu_version", "")
        if nv and not (nv.startswith(">=") and "<" in nv):
            errors.append(f"active[{i}] ({entry.get('name', '?')}): nu_version should be '>=X.Y.Z <X.Y.Z' format, got '{nv}'")
    
    return errors


def verify_upstream(manifest):
    """Verify that each active entry's tag exists on its upstream repo."""
    errors = []
    
    for entry in manifest["active"]:
        repo = entry.get("repo", "")
        tag = entry.get("tag", "")
        name = entry.get("name", "?")
        
        if not repo or not tag:
            continue
        
        url = f"https://github.com/{repo}"
        result = subprocess.run(
            ["git", "ls-remote", "--tags", url, tag],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            errors.append(f"{name}: failed to query {url}")
        elif tag not in result.stdout:
            errors.append(f"{name}: tag '{tag}' not found at {url}")
        else:
            print(f"  ✓ {name}: tag '{tag}' exists at {repo}")
    
    return errors


def main():
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    verify = "--verify-upstream" in sys.argv
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    print(f"Validating manifest ({len(manifest.get('active', []))} active entries)...")
    
    errors = validate_structure(manifest)
    if errors:
        print("\n❌ Structure errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    
    print("✓ Structure valid")
    
    if verify:
        print("\nVerifying upstream tags...")
        errors = verify_upstream(manifest)
        if errors:
            print("\n❌ Upstream verification errors:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print("✓ All upstream tags verified")
    
    print(f"\n✅ Manifest valid ({len(manifest['active'])} plugins)")
    sys.exit(0)


if __name__ == "__main__":
    main()
