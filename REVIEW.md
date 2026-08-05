# numan-plugins PR review

Use this file when reviewing pull requests (human or automated). The [README](README.md) remains the source for layout and build flow; this file focuses on **what to flag in review**.

## CI gates (must pass)

- `python3 -m compileall -q scripts`
- `python3 -m unittest discover -s scripts -p "test_*.py" -v`
- `python3 scripts/validate_manifest.py --verify-upstream`
- Workflow lint (`actionlint`) via repo-safety

Publishing builds run only via manual `build-plugins` dispatch with a non-empty package list. Pushes and pull requests must not publish releases.

## Severity labels

| Label | Meaning |
|-------|---------|
| **P0** | Signing-key material in this repo, mutable/replaced release assets, publish from PR/push, trust-boundary break |
| **P1** | Wrong upstream pin, tag/commit mismatch, incomplete target matrix, broken release transaction, fake readiness |
| **P2** | Spec/manifest doc drift, missing tests for packaging scripts, maintainability |
| **P3** | Style, naming, non-blocking suggestions |

## Architecture invariants (flag violations)

1. **Builds only, never signs** — this repo hosts binaries; Ed25519 signing and the official trust root stay in `numan-registry`.
2. **No private keys** — never add signing keys, PEM private material, or registry secrets here.
3. **Immutable upstream pins** — `manifest.json` `active[]` entries pin human-facing tags and immutable `source_commit`; workflow must verify tag-to-commit.
4. **Release assets are immutable** — refuse existing release tags/assets; changed bytes require a new package version or explicit build revision.
5. **Draft-then-finalize** — new releases assemble as run-owned drafts, verify the full asset set, then publish; no half-published public releases.
6. **Hashes are not authored here** — generated specs omit sha256; `numan-registry` `add-package.py` downloads and hashes assets at intake.
7. **Provenance in specs** — generated specs must preserve `source.rev` as the immutable upstream commit.
8. **Manual publish only** — non-empty `only=` package list on workflow_dispatch; PR/push paths validate, they do not release.
9. **No registry mutation** — never publish registry index changes from this repo.

## Review checklist

- [ ] Trust boundary intact (no keys, no registry signing, no hand-typed artifact hashes).
- [ ] Manifest changes pin `source_commit` and compatible `nu_version`; upstream tag verification still makes sense.
- [ ] Packaging / release scripts keep draft ownership, refuse overwrite, and fail closed on incomplete asset sets.
- [ ] Cross-platform assumptions are explicit (Windows-only paths only at Windows boundaries).
- [ ] Tests cover failure modes for packaging and release transaction helpers.
- [ ] Scope matches PR description; backlog-only edits do not silently change `active[]` publish set.

## Handoff notes (for reviewers of build/manifest PRs)

Successful waves hand off to `numan-registry`:

- generated `spec-*.json` artifacts
- release URLs hosted by this repo
- immutable upstream `source.rev` values
- upstream tags for human-facing provenance
- target list / exclusions
- Nu compatibility and `verified_with` values
