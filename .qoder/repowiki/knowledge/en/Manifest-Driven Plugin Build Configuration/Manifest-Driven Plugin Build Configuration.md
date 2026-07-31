---
kind: configuration_system
name: Manifest-Driven Plugin Build Configuration
category: configuration_system
scope:
    - '**'
source_files:
    - manifest.json
    - scripts/validate_manifest.py
    - scripts/gen_spec.py
    - scripts/package_plugin.py
    - scripts/release_transaction.py
    - .github/workflows/build.yml
---

This repository uses a single JSON manifest file (`manifest.json`) as the authoritative configuration source for its Nushell plugin delivery pipeline. There is no separate application config system — configuration is declarative and consumed directly by Python build scripts and GitHub Actions workflows.

**What system/approach is used**
The configuration approach is a schema-driven JSON manifest combined with CLI argument parsing in Python scripts. The `manifest.json` file declares the build matrix, target platforms, and per-plugin metadata. Python scripts validate and consume this manifest using `argparse` for runtime overrides and environment variables (e.g., `GITHUB_OUTPUT`, `GITHUB_TOKEN`, `GH_TOKEN`) for secrets and CI context. No dedicated configuration framework or library is used — validation is implemented inline via regex patterns and field checks.

**Key files and packages**
- `manifest.json` — Central build manifest defining `default_targets`, `active[]` plugin entries, and `target_runner_map`
- `scripts/validate_manifest.py` — Manifest schema validator with required field enforcement, duplicate detection, and upstream tag verification
- `scripts/gen_spec.py` — Consumes manifest entries to generate numan-registry specs
- `scripts/package_plugin.py` — Uses manifest-derived parameters to produce deterministic archives
- `scripts/release_transaction.py` — Manages release lifecycle using GitHub API, reading `GITHUB_OUTPUT` from environment
- `.github/workflows/build.yml` — Hardcoded target matrix that mirrors `manifest.json` defaults, orchestrating the pipeline

**Architecture and conventions**
- The manifest follows a fixed schema (`numan-plugin-build-manifest-v0`) with required fields: `repo`, `name`, `owner`, `plugin_bin`, `tag`, `source_commit`, `version`, `nu_version`, `verified_with`, `description`, `tags`
- Target exclusions are declared per-plugin via `exclude_targets` (subset of `default_targets`) with explanatory `exclude_reason` comments
- Upstream provenance is enforced: each entry must have an immutable `source_commit` matching the resolved `tag` SHA, verified via `git ls-remote`
- The workflow duplicates the target matrix definition rather than reading it dynamically, creating a tight coupling between `build.yml` and `manifest.json`
- Environment variables are the only mechanism for runtime configuration — no config file loading beyond the manifest itself
- All scripts use `argparse` with explicit `required=True` arguments, making configuration failures explicit and early

**Conventions and constraints**
- Every active plugin must specify both a human-facing `tag` and an immutable `source_commit`; the validator enforces they resolve to the same SHA
- Target triples must be valid Rust targets; exclusions must be subsets of `default_targets` with no duplicates
- Archive formats are platform-specific: `.tar.gz` for Unix targets, `.zip` for Windows, with deterministic timestamps (1980-01-01) and permissions for reproducible builds
- Release assets are never signed in this repo — signing happens downstream in `numan-registry` after hash verification
- The `--only` flag allows selective processing of plugins from the manifest, validated against active names with duplicate detection
- GitHub Actions integration relies on `gh` CLI commands with timeout protection (30 seconds) and structured error handling