# Security policy

This repository cross-compiles and publishes Nushell plugin binaries as GitHub
Release assets for later intake into the official Numan registry. It builds and
hosts artifacts only. It never holds registry signing keys.

Companion policies:

- Signed index, yanks, and key incidents:
  [tonythethompson/numan-registry SECURITY.md](https://github.com/tonythethompson/numan-registry/blob/main/SECURITY.md)
- Numan CLI verification and install/activate behavior:
  [tonythethompson/numan SECURITY.md](https://github.com/tonythethompson/numan/blob/main/SECURITY.md)

## Report a vulnerability

Do not publish exploit details, credentials, or unverified malware samples in a
public issue.

Preferred: open a private GitHub security advisory at
<https://github.com/tonythethompson/numan-plugins/security/advisories/new>.

Fallback: open a public issue titled **Security contact request** with no
technical details. The maintainer will establish a private channel before
collecting the report.

Helpful report contents:

- Package name / manifest entry and release tag or build revision
- Target triple and asset URL
- Expected vs observed digest when known
- Whether the asset is already listed in a signed registry index
- Reproduction or build logs sufficient for independent verification

## Scope

**In scope for this repo**

- Compromised, tampered, or incorrectly built release assets produced here
- CI / release workflow issues that could publish wrong or unexpected bytes
- Manifest provenance mistakes (wrong upstream commit, tag, or source pin)
- Secret leakage in this repository or its workflows (tokens, deploy keys)
- Immutable-release policy failures (overwrite of an existing tagged asset)

**Out of scope here (report elsewhere)**

- A bad artifact that is already pinned and signed in the official index
  (including yank / user remediation):
  [numan-registry](https://github.com/tonythethompson/numan-registry)
- Client-side verification, path, or activation bugs:
  [numan](https://github.com/tonythethompson/numan)
- Security bugs in upstream plugin source (report upstream; open an issue here
  only if our pinned commit or rebuild process needs to change)
- Registry private-key or signature issues (this repo does not sign indexes)

When unsure, report here. We will route it.

## Trust model (summary)

1. This repo never holds the official registry private key. Signing happens only
   in `numan-registry` after intake.
2. Upstream sources are pinned to immutable commits in `manifest.json`. Tags are
   human-facing provenance, not the sole install pin.
3. Digests for registry intake are computed from downloaded release assets by
   registry tooling (`add-package.py`), not hand-typed in this repo.
4. Release tags and assets are immutable. Changed bytes require a new package
   version or an explicit new build revision.
5. Presence of a release asset here does not make it trusted for install. Clients
   trust only a signed registry index entry that pins the URL and SHA-256.

## Supported versions

Security response focuses on currently published release assets still referenced
(or about to be referenced) by the catalog tooling on `main`. Bad assets are
not silently overwritten; remediation is a new build/revision plus registry
intake or yank as appropriate.

## Related docs

- Trust boundary overview: [README.md](README.md#trust-boundary)
- Reviewer trust checklist: [REVIEW.md](REVIEW.md)
- Registry incident procedures:
  [numan-registry incident-response](https://github.com/tonythethompson/numan-registry/blob/main/docs/incident-response.md)
