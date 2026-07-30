# Numan Plugins Roadmap

**Status date:** 2026-07-30

This repository builds binary plugin artifacts for Numan's official registry.
It is the controlled escape hatch for useful Nushell plugins whose upstreams
ship source-only tags or incomplete release assets.

## Current Baseline

- The hardened build pipeline requires manual dispatch with a non-empty
  package list.
- Manifest entries pin a human-facing tag and should pin a full immutable
  `source_commit`.
- Publication refuses existing release tags/assets; changed bytes require a new
  package version or an explicit build revision.
- Generated registry specs preserve upstream provenance and leave SHA256
  computation to `numan-registry`.
- `docs/backlog.json` is the demand-ranked source-only candidate list.
- PR #4 (`feature/catalog-expansion-wave-1`) is **merged**. `master` includes
  `FMotalleb/nu_plugin_port_extension@0.113.1` and
  `FMotalleb/nu_plugin_image@0.112.2`, plus macOS-15 runner labels.
- Wave 1 release assets are published:
  `nu_plugin_port_extension-0.113.1` and `nu_plugin_image-0.112.2`.
- Release upload now uses claim-ID upload ([PR #12](https://github.com/tonythethompson/numan-plugins/pull/12))
  to avoid softprops creating a second draft.

## Immediate Work: Finish Catalog Wave 1

Checklist after PR #4 merges:

- [x] Pull the merge commit into `master`.
- [x] Merge Windows Recheck `shell: bash` fix (PR #8).
- [x] Dispatch `build-plugins` manually with only:
  `nu_plugin_port_extension,nu_plugin_image`.
- [x] Confirm the workflow checks each upstream tag against its recorded
  `source_commit`.
- [x] Confirm all expected target assets are present and no pre-existing release
  or asset was replaced.
- [x] Download the generated `spec-*.json` artifacts for registry intake.
- [x] Do not rebuild existing releases unless a new package version or explicit
  build revision has been chosen.
- [x] Do not publish any registry changes from this repo.
- [ ] Merge release upload-by-id fix (PR #12) for future waves.

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

Assets published; registry intake is [numan-registry#32](https://github.com/tonythethompson/numan-registry/pull/32).

### Wave 2 Research

Use `docs/backlog.json` as the starting queue. Good next research candidates
are source-only plugins with tags and enough demand to justify CI-built assets:

- [x] `devyn/nu_plugin_dbus` — researched 2026-07-30: `PRE_0_112` (nu-plugin 0.101.0; libdbus; not Windows)
- [x] `PhotonBursted/nu_plugin_vec` — researched 2026-07-30: `PRE_0_112` (nu-plugin 0.105.1; pure Rust; Windows expected)
- [ ] `drbrain/nu_plugin_prometheus`
- [ ] `galuszkak/nu_plugin_bigquery`
- [ ] `jcornaz/nu_plugin_from_beancount`
- [ ] `dam4rus/nu_plugin_nuts`

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
