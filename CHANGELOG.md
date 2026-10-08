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
- Optional code intelligence governance that routes structural source questions
  to CodeGraph, establishes a verified per-checkout index when safe and useful,
  and keeps literal or unsupported content on native inspection routes.
- An adaptive pre-alignment and execution-feedback loop with default user
  confirmation, task- or stage-scoped explicit decision delegation, and
  semantic-event-driven correction.

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
- Tool neutrality is now an explicit core-policy property: optional adapters
  may ship with the plugin when they remain isolated, scenario-triggered,
  safely degradable, and unable to install or repair global tooling implicitly.
- Goal discovery, Plan governance, project continuity, and reporting now share
  one bounded decision-authority contract: delegated judgment can adapt the
  route without unnecessary stops, but cannot expand scope, action authority,
  evidence, or completion claims.
- Durable provider operations are now owned through ordinary same-target
  delivery and readback by the task that created them, while historical open
  inventories require semantic-currentness and counterfactual-effect
  classification instead of user monitoring or batch replay.

## 2.0.0 release candidate

- Reframed Work Governance as a composable, tool-neutral policy layer.
- Split goal discovery, Plan governance, SubAgent governance, Git boundaries,
  validation, project truth, archive curation, and reporting into independent
  Skills behind a small lifecycle router.
- Removed the embedded state engine and mandatory persistence coupling.
