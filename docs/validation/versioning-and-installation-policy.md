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
and source tree. A Hook runtime is a separate explicit adoption surface: install
its immutable package under `$HOME/.local/libexec/work-governance/<digest>/`,
validate the stable `$HOME/.local/bin/work-governance-hook` launcher against
both old and candidate package digests, then use `user-hook install` to atomically
merge the exact definition into `$HOME/.codex/hooks.json`. The installer must
preserve unrelated user hooks, replace only verified prior Work Governance
definitions, and restore the prior bytes when its own readback fails. For an
upgrade, verify the old exact Hook still runs before trusting the candidate; for
a first adoption, the package and configuration checks replace that old-event
precondition. In both cases, review and trust the candidate exact Hook hash in
Codex. If the candidate trust or real-event check fails, `user-hook rollback`
must compare the managed candidate definition against its receipt, verify the
previous immutable package(s), and preserve unrelated user-Hook changes rather
than overwriting the whole configuration. Plugin installation does
not imply Hook trust. The Hook command must not execute through a plugin cache,
`latest` or `current` link, CWD, PATH, or PYTHONPATH.

After adoption, retain only the current semantic version in
the exact local cache root. Use `scripts/prune-local-plugin-cache.sh` with the
explicit cache root and `--keep-version`; it removes only direct child
directories whose plugin name and version match their directory name. Historical
versions, source checkouts, marketplace metadata, and unrelated caches are not
silently removed.

An immutable Hook package is retained while any installed Hook definition
references its digest or a live process may be using it. Cleanup may target
only one exact validated digest and remains a separate explicit action.

Work Governance is a policy plugin, not WorkVCS development code. It must not
introduce or retain a second WorkVCS CLI version as part of ordinary plugin
installation.
