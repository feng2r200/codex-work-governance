# Changelog

All notable changes to Work Governance are documented here. The project follows
[Semantic Versioning](https://semver.org/) for public releases.

## Unreleased

### Added

- A complete Simplified Chinese README with bidirectional language navigation.
- Portable Agent Plugins manifest alongside the Codex compatibility manifest.
- Public installation, contribution, security, support, and community guidance.
- Continuous integration for policy contracts and lint checks.
- Project development governance for enrolled long-running work, including a
  small project entry, bounded startup recovery, one mutable execution-state
  provider, and material closeout reconciliation.

### Changed

- Publisher metadata now credits `feng2r200` explicitly.
- Goal discovery and Plan stage gates now expose unresolved material solution
  and feasibility choices before dependent design or implementation instead of
  deferring them until an assumed path fails.
- Repository history no longer carries project-local governance runtime data or
  personal absolute paths on the rewritten `main` lineage.
- Continuous-integration Actions are pinned to verified full commit SHAs, with
  a policy contract that prevents mutable tags from being reintroduced.
- Project continuity now separates a stable provider locator from verified
  logical-project state isolation, fails closed on shared unpartitioned state,
  reuses one bounded provider snapshot until explicit invalidation, and accepts
  a precise mutation receipt plus exact target readback instead of requiring an
  immediate broad reread.
- Provider continuity now prefers one aggregate read-only health or readiness
  snapshot over repeated equivalent status calls, treats cleanly missing
  authority as degraded, and blocks only the affected path for invalid control
  state without silently authorizing activation or repair.

## 2.0.0 release candidate

- Reframed Work Governance as a composable, tool-neutral policy layer.
- Split goal discovery, Plan governance, SubAgent governance, Git boundaries,
  validation, project truth, archive curation, and reporting into independent
  Skills behind a small lifecycle router.
- Removed the embedded state engine and mandatory persistence coupling.
