---
kind: build_system
name: Numan Plugin Binary Delivery Pipeline
category: build_system
scope:
    - '**'
source_files:
    - .github/workflows/build.yml
    - manifest.json
    - scripts/package_plugin.py
    - scripts/gen_spec.py
    - scripts/release_transaction.py
    - scripts/validate_manifest.py
    - scripts/ensure_release_absent.py
---

This repository implements a CI-driven binary delivery pipeline for Nushell plugins. It cross-compiles source-only upstream Rust plugins from immutable commits, packages per-target binaries as deterministic GitHub release assets, and emits registry specifications consumed by `numan-registry` for signed index publication.

**System and tools**
- Build orchestration: GitHub Actions workflow `.github/workflows/build.yml` defines three jobs — `setup`, `build`, and `release` — with no Makefile or Dockerfile; everything is scripted in Python.
- Cross-compilation: Rust toolchain via `dtolnay/rust-toolchain` with `cargo build --release --locked` against explicit target triples. Linux aarch64 uses `taiki-e/setup-cross-toolchain-action` for cross-linking.
- Packaging: `scripts/package_plugin.py` produces byte-stable archives (`.tar.gz` on Unix, `.zip` on Windows) with fixed mtime/mode/uid/gid so rebuilds yield identical sha256 digests.
- Registry spec generation: `scripts/gen_spec.py` consumes the PACKAGED TSV lines plus manifest metadata to produce a `kind: binary` JSON spec for `numan-registry`'s `add-package.py`.
- Release transaction safety: `scripts/release_transaction.py` provides atomic claim/finalize/cleanup subcommands that create draft releases, verify asset sets and tag ownership, publish only on success, and clean up on failure.
- Manifest-driven configuration: `manifest.json` declares schema `numan-plugin-build-manifest-v0`, default targets, and each plugin's `repo`, `name`, `owner`, `plugin_bin`, `tag`, `source_commit`, `version`, `exclude_targets`, `nu_version`, `verified_with`, description, and tags.

**Key files**
- `.github/workflows/build.yml` — end-to-end CI pipeline orchestrating checkout, validation, cross-build, packaging, artifact upload, spec generation, and safe release publishing.
- `manifest.json` — single source of truth for active plugins, target matrix, and provenance metadata.
- `scripts/package_plugin.py` — deterministic archive builder producing stable sha256 artifacts.
- `scripts/gen_spec.py` — validates packaged records against expected targets and emits the numan-registry intake spec.
- `scripts/release_transaction.py` — atomic draft-release lifecycle manager (claim → finalize/publish or cleanup).
- `scripts/validate_manifest.py` — invoked by CI to validate selection and verify upstream tag→commit immutability (`--verify-upstream`).
- `scripts/ensure_release_absent.py` — prevents duplicate release tags before claiming.

**Architecture and conventions**
- Immutable sources: Each plugin entry pins both a human-facing `tag` and an immutable `source_commit`; the workflow checks out `ref: ${{ matrix.source_commit }}` and asserts `git rev-parse HEAD == SOURCE_COMMIT`.
- Target matrix: Five triples are built per plugin — `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu` (cross), `x86_64-apple-darwin`, `aarch64-apple-darwin`, `x86_64-pc-windows-msvc` — with per-plugin `exclude_targets` support.
- Deterministic artifacts: Archives use fixed timestamps (1980-01-01 epoch), fixed Unix mode `0o755`, uid/gid 0, and gzip mtime=0 so the same source always yields the same sha256.
- Separation of concerns: This repo never holds signing keys; it publishes unsigned assets and specs. Signing happens downstream in `numan-registry` via `add-package.py` under the official trust root.
- Transactional releases: Draft releases are claimed first, assets uploaded, then `finalize` verifies ownership and asset set before publishing; `cleanup` removes stale drafts on failure.
- Spec contract: `gen_spec.py` intentionally omits `sha256` from the emitted spec because `add-package.py` re-downloads and hashes assets itself; the local sha256 is only used to verify the uploaded asset matches what was built.

**Conventions and constraints**
- Plugins must be Rust projects buildable via `cargo build --release --locked --target <triple>` without interactive prompts.
- Each plugin entry in `manifest.json` must include `repo`, `name`, `owner`, `plugin_bin`, `tag`, `source_commit`, `version`, `nu_version`, `verified_with`, `description`, and `tags`.
- Per-plugin `exclude_targets` lists triples that should not be built for that plugin, with an `exclude_reason` explaining why.
- The workflow is triggered manually via `workflow_dispatch` with an `only` input (comma-separated plugin names); only selected plugins are built and released.
- Artifact naming follows `<name>-<version>-<triple>.tar.gz` (Unix) or `.zip` (Windows); executable path recorded in the spec is just the binary filename.
- Release tags follow `<name>-<version>` and must not already exist (`ensure_release_absent.py` enforces this before claiming).