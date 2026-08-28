# Repo-local roadmap for numan-plugins

> **Default branch:** `main` (aligned with `numan-registry`). The legacy `master` branch remains temporarily for URL compatibility.

This repo owns CI-built plugin binaries for upstreams without compliant
release assets. The roadmap that covers the entire three-repo plan —
catalog intake, signing, plugin backfills, client compat, lifecycle
evidence, and the active-plugin gate — lives in the consolidated
cross-repo plan:

[**`numan/docs/plans/consolidated-multi-repo-roadmap.md`**](https://github.com/numan-cli/numan/blob/master/docs/plans/consolidated-multi-repo-roadmap.md)

Repo-local roadmaps keep operational detail. The cross-repo drill is enforced by
[`scripts/check-roadmap-drift.py`](https://github.com/numan-cli/numan/blob/master/scripts/check-roadmap-drift.py),
which CI runs at `.github/workflows/roadmap-drift.yml` and which fails the
workflow run if this page drifts from the consolidated truth.

## Repo-local detail

Use this page for **operational** detail that belongs only to
`numan-plugins`:

- Workflow manifests under `.github/workflows/` (`build.yml`,
  `intake-archive.yml`, `repo-safety.yml`, `windows-recheck` / release paths).
- Per-package target exclusions and reasons in `manifest.json`
  (`exclude_targets` / `exclude_reason`).
- Backlog triage notes (`docs/backlog.json` schema + review log).
- Completed catalog-wave checklists and registry handoff notes below.

Promote any cross-repo claim back into the consolidated roadmap via a
coordinated contract bump (`numan/scripts/bump-contract.sh`), not by editing
contract pins in this repo alone.

## Current Baseline

- The hardened build pipeline requires manual dispatch with a non-empty
  package list.
- Manifest entries pin a human-facing tag and should pin a full immutable
  `source_commit`.
- Publication refuses existing release tags/assets; changed bytes require a new
  package version or an explicit build revision.
- Generated registry specs preserve upstream provenance and leave SHA256
  computation to `numan-registry`.
- `docs/backlog.json` (schema v1) is the comprehensive **plugin candidate** list
  (not the live catalog). It tracks release versions per plugin with Nu minor
  compatibility via `versions[]` / `backfill_targets`. Live catalog × Nu overview:
  [`numan-registry/docs/catalog-compat.md`](https://github.com/numan-cli/numan-registry/blob/main/docs/catalog-compat.md).
  Source: awesome-nu + manual discovery.
- Wave 1 and Wave 2 CI-built plugins are on **`main`**, published, and intaken
  into the official registry. Wave 2 targets Nu 0.114; Wave 1 includes Nu
  0.113.1 and Nu 0.112.2. `manifest.json` `active[]` currently holds 20 plugins.
- Release upload uses claim-ID upload (upload-by-id) to avoid softprops
  creating a second draft.

## Immediate Work: Grow Catalog Depth For 1.0

Wave 1 and Wave 2 checklists are closed. Next: promote one or two backlog
candidates at a time through build → registry intake → lifecycle-prove. Keep
README `Currently active` and `docs/backlog.json` statuses in the same PR.

Historical Wave 1 checklist (complete):

- [x] Merge wave-1 promote into `main`.
- [x] Merge Windows Recheck `shell: bash` fix.
- [x] Dispatch `build-plugins` for `nu_plugin_port_extension,nu_plugin_image`.
- [x] Confirm tag↔`source_commit` checks and immutable releases.
- [x] Registry intake + lifecycle-prove + production + client smoke.
- [x] Merge release upload-by-id fix for future waves.

## Candidate Promotion Gates

A plugin should move from `docs/backlog.json` to `manifest.json` `active[]`
only after these facts are recorded:

- [ ] Upstream repo is reachable and not archived, or the archive state is
  explicitly accepted.
- [ ] Tag exists and resolves to the recorded 40-character lowercase
  `source_commit` (or `intake_mode` is `"commit-snapshot"` with `tag: null`
  pinning a validated 40-character lowercase `source_commit`).
- [ ] `nu-plugin` and `nu-protocol` dependency versions are known.
- [ ] Nu compatibility range is minor-scoped and matches the dependency version.
- [ ] `plugin_bin` is confirmed.
- [ ] Windows locked build succeeds or Windows is excluded with a concrete
  reason.
- [ ] Linux and macOS builds are expected to work, or excluded with concrete
  target-specific reasons.
- [ ] Exact-version Nu command discovery smoke succeeds where practical.
- [ ] This repository has no existing release tag/assets for that package
  version.
- [ ] README active list and backlog notes are updated in the same PR.

## Next Candidate Waves

Do not promote a whole batch blindly. Pick one or two candidates, prove them,
then hand them to `numan-registry`.

### Wave 1 Completion

- [x] `FMotalleb/nu_plugin_port_extension@0.114.1` (earlier `0.113.1` retained in registry history)
- [x] `FMotalleb/nu_plugin_image@0.112.2`

Assets published; registry intake complete;
production + client smoke complete 2026-07-31 (the port_extension Nu 0.114 bump
occurred during the Wave 1 Nu 0.114 intake).

### Wave 2 Completion (Nu 0.114 CI-built)

- [x] `fdncred/nu_plugin_jwalk@0.26.0`
- [x] `fdncred/nu_plugin_strutils@0.22.0`
- [x] `fdncred/nu_plugin_query_git@0.24.0`
- [x] `lizclipse/nu_plugin_ulid@0.23.0`
- [x] `rhino-linux/nu_plugin_nutext@0.6.2`

Assets published ([build 30985049217](https://github.com/numan-cli/numan-plugins/actions/runs/30985049217));
registry intake complete;
production [30996546918](https://github.com/numan-cli/numan-registry/actions/runs/30996546918);
lifecycle-prove OK Linux x86_64 and Windows x64 / Nu 0.114.1.

### Wave 2 Research

Use `docs/backlog.json` as the starting queue. Good next research candidates
are source-only plugins with tags and enough demand to justify CI-built assets:

- [x] `devyn/nu_plugin_dbus` — researched 2026-07-30: `PRE_0_112` (nu-plugin 0.101.0; libdbus; not Windows)
- [x] `PhotonBursted/nu_plugin_vec` — researched 2026-07-30: `PRE_0_112` (nu-plugin 0.105.1; pure Rust; Windows expected)
- [x] `drbrain/nu_plugin_prometheus` — promoted 2026-07-31 to `active[]` as `v0.12.0` (nu-plugin/nu-protocol 0.114.1; commit `3fed1d934ba201ce1d9b78ecb727695588de7ef9`). Windows locked green; `aarch64-unknown-linux-gnu` excluded (openssl-sys cross). CI-built release published; in official registry. `v0.11.0` was `PRE_0_112` (0.110.0).
- [x] `galuszkak/nu_plugin_bigquery` — researched 2026-07-31: `v0.2.0` pins nu-plugin 0.112.2; eligible for intake via P6 Provisional Tier with deferral reason.

### Intake Reform Wave (P1 Commit-Snapshot, P2 Non-Binary Archive, P4 Maintained Forks, P6 Provisional)

With the intake reform tooling merged into `numan-plugins` (commit-snapshot intake mode `#80`, fork identity `#82`):

#### 1. High-Demand Tag-less Plugins (P1 Commit-Snapshot)

Build directly from an immutable 40-character lowercase `source_commit` with `intake_mode: "commit-snapshot"` and `tag: null`, producing SemVer prereleases (`0.0.0-snapshot.<YYYYMMDD>.<sha>`):

- [x] `Euphrasiologist/nu_plugin_plot` (⭐ 71) — terminal plotting
- [x] `Euphrasiologist/nu_plugin_bio` (⭐ 31) — bioinformatics format parsing
- [ ] `fdncred/nu_plugin_pnet` (⭐ 9) — network interface inspection (deferred to Lane 5; upstream path dependency requires maintained fork)
- [x] `WindSoilder/nu_plugin_mongo` (⭐ 8) — MongoDB client
- [x] `hulthe/nu_plugin_msgpack` (⭐ 7) — MsgPack converter
- [x] `kik4444/nu_plugin_mime` (⭐ 6) — in-memory MIME inspection
- [x] `oderwat/nu_plugin_logfmt` (⭐ 5) — logfmt parser
- [x] `yybit/nu_plugin_x509` (⭐ 5) — X.509 certificates

#### 2. Maintained Forks (P4 Lane 3)

Proposed forks evaluate under ADR 0001 stewardship criteria (requiring `numan-maintained` owner, `upstream_repo` attribution, and named stewardship):

- [ ] `tonythethompson/nu_plugin_qr_maker` — proposed fork of `FMotalleb/nu_plugin_qr_maker`
- [ ] `tonythethompson/nu_plugin_explore` — proposed fork of `nushell/nu_plugin_explore`
- [ ] `FMotalleb/nu_plugin_clipboard` (⭐ 85) — evaluate bumping from Nu 0.110 to Nu 0.114.1
- [ ] `yybit/nu_plugin_compress` (⭐ 42) — evaluate bumping from Nu 0.103 to Nu 0.114.1
- [ ] `fdncred/nu_plugin_pnet` (⭐ 9) — evaluate bumping from Nu 0.97 to Nu 0.114.1

#### 3. Provisional Tier (P6)

- [ ] `galuszkak/nu_plugin_bigquery` — build and package normally in `numan-plugins`, then intake into `numan-registry` using `scripts/add-package.py --provisional --deferral-reason "..."`

`scripts/gen_spec.py --provisional --deferral-reason "<why>"` emits the provisional
evidence tier (`evidence_tier` plus `deferral_reason`, and no `verified_with`), so
the generated spec is accepted by `add-package.py --provisional` unchanged.
`build.yml` has no dispatch input for the flags, because one build run is a matrix
over many plugins and the tier is per package: generate a provisional binary spec
by running `gen_spec.py` against a completed run's `packaged.tsv` and downloaded
assets. Either way the tier reaches the index from `add-package.py --provisional
--deferral-reason "..."`, which is what writes `evidence_tier` on the version entry.

#### 4. Non-Binary Archive Intake (P2)

Modules, scripts, and completions need no compilation, so they take the archive
lane instead of the cross-compile matrix: `scripts/intake_archive.py`, driven by
`.github/workflows/intake-archive.yml` (manual dispatch only).

- Resolves the requested ref to a full 40-character upstream commit,
  shallow-clones it, and verifies the declared entry file exists in the checkout.
- Builds a deterministic `.tar.gz` with `scripts/package_plugin.py`'s parameters
  (sorted entries, fixed mtime, gzip mtime=0), so re-archiving the same commit
  reproduces identical bytes.
- Publishes the archive as a release asset on this repository through the existing
  release transaction (`ensure_release_absent.py`, then `release_transaction.py`
  claim → upload → finalize, with cleanup on a failed run). The release tag is
  `archive-<owner>-<name>-<version>` and the asset is
  `<owner>-<name>-<version>.tar.gz`.
- Emits an `artifact.kind: archive` spec carrying an inline `sha256`. That value is
  not what the registry trusts — `add-package.py` downloads the asset and computes
  the index hash itself — it is the digest of the archived bytes, which the publish
  job re-hashes the collected artifact against before it claims a release, closing
  the gap between what was archived and what gets published.
- Stages every activatable package provisionally: `add-package.py` requires
  lifecycle evidence for any entry with an `activation`, and that evidence can only
  come from proving the published asset, which does not exist until the release
  completes. `numan-registry` replaces the provisional tier once prove succeeds.
- Records re-intake provenance (upstream URL, requested ref, resolved commit,
  entry, owner, name, type) in `manifest-archives.json`. The workflow uploads the
  updated file as an artifact instead of pushing a commit, so a maintainer commits
  it alongside the registry handoff.
- Supports `--provisional` / `--deferral-reason` for a package whose
  lifecycle-prove is deferred.

### Deferred Until Upstream Changes

- [ ] Pre-0.112 plugins stay deferred unless upstream bumps Nu minor or Numan elects a maintained fork under ADR 0001.
- [ ] Repositories with bare binary uploads or unsupported archive shapes.

## Pipeline Maintenance

- [ ] Keep all third-party GitHub Actions pinned to reviewed commit SHAs.
- [ ] Keep workflow permissions read-only except the release publication job.
- [ ] Keep macOS runner labels current and covered by tests.
- [ ] Keep deterministic archive tests for `.zip` and `.tar.gz`.
- [ ] Keep the non-binary archive lane's deterministic parameters, release tag
  shape, and emitted spec shape covered by tests.
- [ ] Keep release absence tests proving existing tags/assets fail before
  upload.
- [ ] Keep manifest validation strict about duplicate package names, duplicate
  target records, missing targets, malformed commits, and tag-to-commit drift.
- [ ] Keep generated spec validation strict about packaged SHA records and
  complete target coverage.

## Registry Handoff Contract

Every successful build wave should hand the registry:

- generated `spec-*.json` artifacts;
- release URLs hosted by this repository;
- immutable upstream `source.rev` values;
- upstream tags retained for human-facing provenance;
- target list and exclusions;
- Nu compatibility and `verified_with` values.

The registry then independently downloads assets, computes hashes, merges the
catalog entry, signs the index, publishes staging/production, and records
lifecycle evidence.

## Success Gate

This repo is healthy when:

- catalog expansion can add one or two plugins without touching publication
  safety code;
- every active manifest entry can be traced to an upstream tag and immutable
  commit;
- every release asset is immutable and hash-pinned downstream;
- the backlog tells the next maintainer why each candidate is promoted,
  deferred, or blocked;
- the registry receives specs that require no manual repair before intake.
