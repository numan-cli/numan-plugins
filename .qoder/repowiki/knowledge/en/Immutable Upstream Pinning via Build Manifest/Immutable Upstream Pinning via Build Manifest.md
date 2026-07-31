---
kind: dependency_management
name: Immutable Upstream Pinning via Build Manifest
category: dependency_management
scope:
    - '**'
source_files:
    - manifest.json
    - .github/workflows/build.yml
    - scripts/validate_manifest.py
    - scripts/package_plugin.py
    - scripts/gen_spec.py
    - scripts/release_transaction.py
    - scripts/ensure_release_absent.py
---

This repository does not manage its own third-party dependencies through a package manager. Instead, it implements a **build-manifest-driven dependency pinning strategy** for the Nushell plugins it cross-compiles and distributes.

### What system/approach is used
- A single `manifest.json` file declares each active plugin with an immutable `source_commit` (40-character SHA), a human-facing `tag`, and the upstream `repo` URL. The manifest schema is `numan-plugin-build-manifest-v0`.
- The CI workflow (`.github/workflows/build.yml`) checks out each plugin at exactly that commit (`ref: ${{ matrix.source_commit }}`), then runs `cargo build --release --locked --target <triple>` to enforce deterministic builds from pinned sources.
- Python scripts in `scripts/` validate the manifest, verify that each tag resolves to the declared commit (`validate_manifest.py --verify-upstream`), package per-target binaries into stable archives (`package_plugin.py`), and emit a numan-registry spec (`gen_spec.py`).
- There are no `go.mod`, `Cargo.lock`, `package.json`, `requirements.txt`, or similar lockfiles in this repo; all external code is pulled at build time from upstream Git repositories and never vendored here.

### Key files and packages
- `manifest.json` — canonical source of truth for which plugins to build, their versions, target triples, and immutable source commits.
- `.github/workflows/build.yml` — orchestrates checkout at `source_commit`, Rust toolchain setup, cross-compilation, packaging, and release publishing.
- `scripts/validate_manifest.py` — validates required fields, uniqueness, target exclusions, and optionally verifies upstream tag → commit mapping via `git ls-remote`.
- `scripts/package_plugin.py` — produces byte-stable `.tar.gz` / `.zip` archives with fixed mtime/mode/uid/gid so rebuilds yield identical sha256 digests.
- `scripts/gen_spec.py` — generates a `kind: binary` registry spec consumed by `numan-registry`'s `add-package.py`; hashes are recomputed downstream, never hand-typed.
- `scripts/release_transaction.py`, `scripts/ensure_release_absent.py` — atomic claim/upload/finalize/cleanup of GitHub releases to prevent duplicate publishes.

### Architecture and conventions
- **Immutable pins**: every entry requires a 40-hex `source_commit`; the workflow asserts `git rev-parse HEAD == SOURCE_COMMIT` after checkout.
- **Tag provenance**: `--verify-upstream` calls `git ls-remote https://github.com/<repo>.git refs/tags/<tag>` and fails if the resolved SHA differs from `source_commit`.
- **Target matrix**: `default_targets` lists five triples; each entry may declare `exclude_targets` (validated against defaults) with an `exclude_reason` explaining why a platform is omitted.
- **Deterministic artifacts**: archives use fixed mtime (1980-01-01 UTC), Unix mode `0o755`, uid/gid 0, and gzip mtime=0 so the same source always produces the same sha256.
- **Separation of concerns**: this repo only builds and publishes assets; signing and index pinning happen downstream in `numan-registry` via `scripts/add-package.py`, and this repo "never holds signing keys".

### Conventions and constraints
- Each `active[]` entry must contain `repo`, `name`, `owner`, `plugin_bin`, `tag`, `source_commit`, `version`, `nu_version`, `verified_with`, `description`, and `tags` (enforced by `REQUIRED_FIELDS` in `validate_manifest.py`).
- `source_commit` must be exactly 40 lowercase hex characters; duplicates in `active[]` names are rejected.
- `exclude_targets` must be a subset of `default_targets` and unique; excluding all targets is rejected.
- `--only` selects a comma-separated list of plugin names; duplicates are rejected and unknown names cause failure.
- The workflow uses `cargo build --release --locked`, requiring upstream crates to have a `Cargo.lock` that pins transitive dependencies.
- Release publishing is guarded: `ensure_release_absent.py` refuses to publish if a release with the same tag already exists, and `release_transaction.py` enforces asset-set equality between claimed and uploaded releases.