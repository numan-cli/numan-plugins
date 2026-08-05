# Repo-local roadmap for numan-plugins

> **Default branch:** `main` (aligned with `numan-registry`). The legacy `master` branch remains temporarily for URL compatibility.

This repo owns CI-built plugin binaries for upstreams without compliant
release assets. The roadmap that covers the entire three-repo plan —
catalog intake, signing, plugin backfills, client compat, lifecycle
evidence, and the active-plugin gate — lives in the consolidated
cross-repo plan:

[**`numan/docs/plans/consolidated-multi-repo-roadmap.md`**](https://github.com/tonythethompson/numan/blob/master/docs/plans/consolidated-multi-repo-roadmap.md)

Repo-local roadmaps keep operational detail. The cross-repo drill is enforced by
[`scripts/check-roadmap-drift.py`](https://github.com/tonythethompson/numan/blob/master/scripts/check-roadmap-drift.py),
which CI runs at `.github/workflows/roadmap-drift.yml` and which fails the
workflow run if this page drifts from the consolidated truth.

## Repo-local detail

Use this page for **operational** detail that belongs only to
`numan-plugins`:

- Workflow manifests under `.github/workflows/` (`build.yml`,
  `repo-safety.yml`, `windows-recheck` / release paths).
- Per-upstream build matrix decisions (`docs/upstream-build-decisions.md`).
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
  [`numan-registry/docs/catalog-compat.md`](https://github.com/tonythethompson/numan-registry/blob/main/docs/catalog-compat.md).
  Source: awesome-nu + manual discovery.
- Wave 1 and Wave 2 Nu 0.114 CI-built plugins are on **`main`**, published, and
  ingested into the official registry. `manifest.json` `active[]` currently holds
  20 plugins.
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
  `source_commit`.
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

- [x] `FMotalleb/nu_plugin_port_extension@0.113.1`
- [x] `FMotalleb/nu_plugin_image@0.112.2`

Assets published; registry intake complete;
production + client smoke complete 2026-07-31.

### Wave 2 Completion (Nu 0.114 CI-built)

- [x] `fdncred/nu_plugin_jwalk@0.26.0`
- [x] `fdncred/nu_plugin_strutils@0.22.0`
- [x] `fdncred/nu_plugin_query_git@0.24.0`
- [x] `lizclipse/nu_plugin_ulid@0.23.0`
- [x] `rhino-linux/nu_plugin_nutext@0.6.2`

Assets published ([build 30985049217](https://github.com/tonythethompson/numan-plugins/actions/runs/30985049217));
registry intake complete;
production [30996546918](https://github.com/tonythethompson/numan-registry/actions/runs/30996546918);
lifecycle-prove OK Linux x86_64 and Windows x64 / Nu 0.114.1.

### Wave 2 Research

Use `docs/backlog.json` as the starting queue. Good next research candidates
are source-only plugins with tags and enough demand to justify CI-built assets:

- [x] `devyn/nu_plugin_dbus` — researched 2026-07-30: `PRE_0_112` (nu-plugin 0.101.0; libdbus; not Windows)
- [x] `PhotonBursted/nu_plugin_vec` — researched 2026-07-30: `PRE_0_112` (nu-plugin 0.105.1; pure Rust; Windows expected)
- [x] `drbrain/nu_plugin_prometheus` — promoted 2026-07-31 to `active[]` as `v0.12.0` (nu-plugin/nu-protocol 0.114.1; commit `3fed1d934ba201ce1d9b78ecb727695588de7ef9`). Windows locked green; `aarch64-unknown-linux-gnu` excluded (openssl-sys cross). Awaiting successful `build-plugins` release. `v0.11.0` was `PRE_0_112` (0.110.0).
- [ ] `galuszkak/nu_plugin_bigquery` — peeked 2026-07-31: `v0.2.0` pins nu-plugin 0.112.2 (eligible) but needs Google credentials for meaningful lifecycle proof
- [x] `jcornaz/nu_plugin_from_beancount` — researched 2026-07-31: `PRE_0_112` (nu-plugin 0.76)
- [x] `dam4rus/nu_plugin_nuts` — researched 2026-07-31: `PRE_0_112` (nu-plugin 0.110.0)
- [x] `FMotalleb/nu_plugin_audio_hook` — researched 2026-07-31: `PRE_0_112` (nu-plugin 0.110.0; rodio decoders)

For each, record whether the current tag is compatible with a supported Nu
minor, whether native system dependencies are required, whether Windows builds,
and whether the package has a simple command-discovery smoke.

### Deferred Until Upstream Changes

- [ ] Pre-0.112 plugins stay deferred unless Numan chooses to support older Nu
  minors again.
- [ ] Repositories with no release tag stay deferred unless a maintainer cuts a
  tag or Numan explicitly chooses a commit snapshot policy for CI-built plugins.
- [ ] Packages with bare binary uploads or unsupported layouts should remain in
  backlog until the archive/package shape is made compliant.
- [ ] Plugins needing heavy native services or credentials should wait until the
  lifecycle proof can be meaningfully automated.

## Pipeline Maintenance

- [ ] Keep all third-party GitHub Actions pinned to reviewed commit SHAs.
- [ ] Keep workflow permissions read-only except the release publication job.
- [ ] Keep macOS runner labels current and covered by tests.
- [ ] Keep deterministic archive tests for `.zip` and `.tar.gz`.
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
