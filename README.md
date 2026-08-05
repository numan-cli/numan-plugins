# numan-plugins

CI build pipeline feeder for the [numan](https://github.com/tonythethompson/numan)
official registry — implements the binary-delivery half of
[numan #30](https://github.com/tonythethompson/numan/issues/30).

**Default branch:** `main` (aligned with `numan-registry`; client stays on `master`).

## Why this repo exists

numan installs plugins from **signed, hash-pinned binary artifacts** (a plugin
install bails if `sha256` is missing). Many popular Nushell plugins still ship
source-only — no prebuilt release binaries — so users would need a full Rust
toolchain to install them.

This repo closes that gap for selected plugins: it cross-compiles from immutable
upstream commits (with tags retained for human-facing provenance), packages one
archive per target, and publishes them as GitHub release assets.
[`numan-registry`](https://github.com/tonythethompson/numan-registry)
then pins those URLs and signs the index with the official trust root.

Plugins that already publish compliant upstream release assets can be intaken
directly in `numan-registry` without a stop here. For the live catalog × Nu
matrix, see
[`docs/catalog-compat.md`](https://github.com/tonythethompson/numan-registry/blob/main/docs/catalog-compat.md)
in the registry. For demand-ranked candidates **not yet** built, see
[`docs/backlog.json`](docs/backlog.json) here.

## Trust boundary

- This repo **builds and hosts binaries only**. It never holds signing keys.
- Signing stays in `numan-registry` (`production.yml` + the Ed25519 trust root).
- Every hash is computed at intake by `numan-registry`'s `add-package.py` from
  the uploaded asset — never hand-typed here.
- Provenance (upstream repo + full commit + tag) is pinned in `manifest.json`
  and each release.
- Release tags and assets are immutable. The publishing workflow refuses an
  existing release; changed bytes require a new package version or explicit
  build revision. New releases are assembled and verified as run-owned drafts,
  then made public only after the complete asset set is confirmed.

## Layout

| Path | Purpose |
|------|---------|
| `manifest.json` | `active[]` = plugins built now; build matrix + target→runner map |
| `docs/backlog.json` | Demand-ranked plugin candidates (statuses, Nu deps per tag) |
| `docs/roadmap.md` | Repo-local build/handoff plan (points at consolidated 1.0 roadmap) |
| Registry [`catalog-compat.md`](https://github.com/tonythethompson/numan-registry/blob/main/docs/catalog-compat.md) | Master list of **live** official packages × Nu constraints |
| `.github/workflows/build.yml` | manual matrix build → package → release → emit spec |
| `.github/workflows/repo-safety.yml` | required manifest, test, archive, spec, and workflow checks |
| `.pre-commit-config.yaml` | local JSON format + README/backlog consistency hooks |
| `scripts/package_plugin.py` | normalize a built binary into a `.tar.gz`/`.zip` |
| `scripts/gen_spec.py` | emit a `numan-registry` `kind:binary` spec (no sha256) |
| `scripts/release_transaction.py` | claim, verify, finalize, or clean up an owned draft release |

## Build matrix

`x86_64`/`aarch64` Linux (gnu), `x86_64`/`aarch64` macOS, `x86_64` Windows.
Linux aarch64 cross-compiles via `taiki-e/setup-cross-toolchain-action`; the
rest build on native runners.

## Flow (per plugin)

1. Add the plugin to `manifest.json` `active[]` (repo, immutable upstream
   `source_commit`, human-facing tag, bin, Nu version compat).
2. Run the **build-plugins** workflow manually with a non-empty `only=` package
   list. It verifies every tag-to-commit mapping, builds all expected targets,
   refuses pre-existing releases/assets, publishes `<name>-<version>`, and
   uploads a `spec-<name>.json` artifact. Pushes and pull requests cannot
   publish.
3. Drop `spec-<name>.json` into `numan-registry/specs/`, run
   `python scripts/add-package.py --spec … --write` there (computes every
   sha256, merges + schema-validates the index).
4. Lifecycle-prove on a clean `NUMAN_ROOT`
   (`search → info → install → activate → doctor → list → remove → gc`) on each
   target OS against a real Nu binary.
5. Open the registry PR; staging signs ephemerally, production signs with the
   trust root and publishes.

## Currently active

- `cptpiepmatz/nu-plugin-highlight` @ `v1.4.16+0.114.1` → `nu_plugin_highlight` 1.4.16
- `fdncred/nu_plugin_regex` @ `v0.23.0` → `nu_plugin_regex` 0.23.0
- `dead10ck/nu_plugin_dns` @ `v4.0.10` → `nu_plugin_dns` 4.0.10
- `idanarye/nu_plugin_skim` @ `v0.29.1` → `nu_plugin_skim` 0.29.1
- `FMotalleb/nu_plugin_desktop_notifications` @ `v0.114.1` → `nu_plugin_desktop_notifications` 0.114.1
- `FMotalleb/nu_plugin_port_extension` @ `v0.114.1` → `nu_plugin_port_extension` 0.114.1
- `fdncred/nu_plugin_file` @ `v0.26.0` → `nu_plugin_file` 0.26.0
- `Yethal/nu_plugin_hcl` @ `0.114.1` → `nu_plugin_hcl` 0.114.1
- `FMotalleb/nu_plugin_image` @ `v0.112.2` → `nu_plugin_image` 0.112.2
- `drbrain/nu_plugin_prometheus` @ `v0.12.0` → `nu_plugin_prometheus` 0.12.0
- `fdncred/nu_plugin_emoji` @ `v0.23.0` → `nu_plugin_emoji` 0.23.0
- `fdncred/nu_plugin_json_path` @ `v0.24.0` → `nu_plugin_json_path` 0.24.0
- `fdncred/nu_plugin_parquet` @ `v0.24.0` → `nu_plugin_parquet` 0.24.0
- `Kissaki/nu_plugin_bson` @ `v26.1140.0` → `nu_plugin_bson` 26.1140.0
- `fnuttens/nu_plugin_hmac` @ `0.27.0` → `nu_plugin_hmac` 0.27.0
- `fdncred/nu_plugin_jwalk` @ `v0.26.0` → `nu_plugin_jwalk` 0.26.0
- `fdncred/nu_plugin_strutils` @ `v0.22.0` → `nu_plugin_strutils` 0.22.0
- `fdncred/nu_plugin_query_git` @ `v0.24.0` → `nu_plugin_query_git` 0.24.0
- `lizclipse/nu_plugin_ulid` @ `v0.23.0` → `nu_plugin_ulid` 0.23.0
- `rhino-linux/nu_plugin_nutext` @ `0.6.2` → `nu_plugin_nutext` 0.6.2

## Registry-side follow-up

Generated specs include the schema's `source` block with the immutable upstream
commit in `source.rev`. Registry intake must preserve that provenance in the
signed index and independently download and hash every release asset.

## Development

Local checks mirror CI:

```bash
python3 scripts/format_json.py --check
python3 scripts/check_repo_consistency.py
python3 -m unittest discover -s scripts -p "test_*.py" -v
python3 scripts/validate_manifest.py --verify-upstream
```

Optional: `pip install pre-commit && pre-commit install` to run the
JSON format and consistency hooks on commit.

## PR review

Reviewers follow [`REVIEW.md`](REVIEW.md) for severity labels, trust-boundary
invariants, and the review checklist.
