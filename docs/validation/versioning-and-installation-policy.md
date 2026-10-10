# Semantic Versioning and Local Installation Policy

Status: Accepted and enforced by CI
Date: 2026-10-10

## Version authority

`pyproject.toml` is the single semantic version authority for Work Governance.
Both plugin manifests must report the same `X.Y.Z` value. A local package
directory, Git commit, or `+codex.<timestamp>` build label is not a substitute
for changing that semantic version.

## Bump rules

- Patch: compatible fixes, performance work, internal implementation changes
  that alter the delivered behavior, and installation or operational guards.
- Minor: new compatible Skills, new compatible policy capabilities, or a
  compatible delivery/migration mechanism.
- Major: incompatible Skill/plugin interfaces, authority boundaries, or state
  and migration contracts.
- No bump: strictly non-functional wording, formatting, or historical-record
  maintenance that does not change the delivered package.

The release-impacting paths are the Skills, plugin manifests, project/lock
metadata, packaging scripts, and release workflow. CI compares the current
version with the exact change base and rejects an unchanged or lower version.

## Installation and cleanup

Install from the repository marketplace, then verify the enabled plugin version
and source tree. After adoption, retain only the current semantic version in
the exact local cache root. Use `scripts/prune-local-plugin-cache.sh` with the
explicit cache root and `--keep-version`; it removes only direct child
directories whose plugin name and version match their directory name. Historical
versions, source checkouts, marketplace metadata, and unrelated caches are not
silently removed.

Work Governance is a policy plugin, not WorkVCS development code. It must not
introduce or retain a second WorkVCS CLI version as part of ordinary plugin
installation.
