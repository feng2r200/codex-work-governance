# Changelog

All notable changes to Work Governance are documented here. The project follows
[Semantic Versioning](https://semver.org/) for public releases.

## Unreleased

No unreleased changes.

## 2.8.0 - 2026-10-26

### Added

- Randomized final-outcome continuity and Project-conversation routing trials
  whose Runner owns the real Codex process, execution receipt, and private
  post-process Oracle. Offline traces remain observational and cannot certify a
  behavior pass.
- A read-only continuation readiness handler that consumes the stable WorkVCS
  native atomic JSON aggregate for one exact scope, including readonly-open,
  policy, Session, Claim, Branch, Task, rotation, gap, and currentness evidence.
- Runner-owned forward trials with source-bound Oracles, raw workspace-boundary
  enforcement, complete delivery and routing conditions, adversarial validator
  controls, repeated no-outcome stimulus, and duplicate-decision rejection.

### Changed

- Goal, Plan, project-development, and reporting governance now preserve the
  user's final outcome across intermediate repair, validation, commit, and
  handoff work, and distinguish blocking route changes from non-blocking
  findings.
- Work Branch selection follows Project conversation relationships independently
  of Git branches, and shared Project truth no longer imports unrelated task
  authority or default bindings into the active conversation.
- Continuation evaluation is explicitly a non-authoritative policy
  recommendation. Product dispatch remains unavailable until a trusted product
  adapter proves actor authorization, exact Project placement, a normal visible
  conversation, and target-authored acceptance.
- Continuation readiness validates native exact-Project scope provenance and
  current policy independently across policy revisions, rejects unknown Branch
  lifecycle values as typed errors, and distinguishes persistent Store/WAL
  invariants from SQLite SHM reader coordination. Explicit false product
  membership and dispatch fields prevent provider readiness from becoming
  product authority by omission.

## 2.7.0 - 2026-10-17

### Added

- Continuation Governance for deciding when one exact Work should move to a
  new visible, auditable, interactive conversation in the same Project without
  making every compaction a rotation trigger.
- A deterministic, side-effect-free continuation evaluator, compact replay
  fixtures, and a validation dossier that separates local contract coverage
  from real-product and natural resource acceptance.

### Changed

- Listener, Work carrier, committed-candidate, SubAgent, and side-chat roles
  now have explicit asymmetric continuation rules. A listener may create a
  Work candidate for monitored Work but cannot duplicate itself; SubAgents and
  side chats cannot act as rotation source, actor, or target.
- Candidate readiness now requires non-forking creation-operation correlation,
  exact Project-binding provenance, a resolved stable thread identity, product
  receipt, visibility, auditability, and interactivity.
- Continuation decisions now carry a deterministic evaluator receipt whose
  digest binds the complete canonical result, gate summary, and bounded
  evidence references.
- Dispatch must freshly revalidate exact-scope currentness before the product
  effect. A created target thread is globally excluded from listener and
  ordinary Work roles; only its exact committed candidate/Claim/scope may later
  source another rotation.
- An inactive lost listener with drifted Work currentness can only be replaced
  through irreversible abort-only recovery: the original attempt may be
  reconciled and terminated, but it cannot create, attach, accept, or commit.

## 2.6.0 - 2026-10-13

### Added

- A stable user-level Hook adoption route that atomically manages only Work
  Governance definitions in `$HOME/.codex/hooks.json`, preserves unrelated
  Hooks, reads back the installed bytes, records a private CAS-protected
  rollback receipt, and reports Codex trust as a separate required review
  boundary.

### Changed

- Hook activation can now use the official user-level configuration surface
  when a Plugin-bundled definition is not enumerated by the host. Commands
  continue to execute only the stable launcher and one immutable package digest.

## 2.5.1 - 2026-10-13

### Fixed

- Treat GitHub's all-zero `before` sentinel for a new branch as an absent base
  so the release gate compares against the parent commit instead of rejecting
  the sentinel as an unresolved revision.

## 2.5.0 - 2026-10-13

### Added

- Optional SessionStart, PreCompact, and bounded PostToolUse hooks backed by an
  explicitly installed, immutable user-level runtime package.
- A stable launcher and two-stage installer with exact package digests,
  per-invocation owner/mode/tree verification, old-and-new package probes, and
  deterministic no-change output.

### Changed

- The former blanket prohibition on Plugin hooks and scripts is replaced by a
  stable-runtime boundary: hook commands never execute from the mutable Plugin
  cache, current directory, PATH, or PYTHONPATH.
- Context injection is opt-in, bounded, digest-deduplicated, and measured.
  Tool observations retain only small identifiers and latency metadata, never
  transcript or tool payload content.
- Hook installation and Hook adoption are reported separately. A host loader
  that exposes no installed events remains blocked/degraded; a package probe or
  trust bypass is not treated as successful activation.

## 2.4.0 - 2026-10-12

### Added

- Scenario-triggered frontend governance connecting reference applicability,
  required behavior, product copy, and scoped runtime acceptance. Includes a
  conditional reference with examples of observable effects and evidence limits.

### Changed

- The lifecycle routes frontend delivery obligations to the new module while
  project and tool Skills retain implementation and browser mechanics. Small
  edits do not acquire a full-site capture, fixed document, or Plan requirement.
- Frontend acceptance distinguishes prototypes, mocked checks, and real
  integration; removing development copy cannot conceal a missing function.

## 2.3.0 - 2026-10-12

### Added

- Scenario-triggered resource observation for development consumption,
  evidence scope, meaningful checkpoint recording, applicable binding limits,
  and later protection or efficiency enhancement candidates.

### Changed

- Capability development and acceptance proceed without invented Token,
  spending, or other savings ceilings. Estimates and unavailable billing data
  do not become execution gates; explicit limits, actual technical failures,
  and new spending or other guarded actions retain their authority boundaries.
- External validation no longer requires an agent-created numerical budget for
  an already authorized probe. Resource savings remain separate from evidence
  completeness and capability acceptance.

## 2.2.0 - 2026-10-10

### Added

- Tool-neutral Plan-exit Task assessment for retain-original, replacement,
  abandonment, cancellation, continuation, and deferral, including bounded
  nested Plan and Task containment, fail-closed graph-integrity stops, current
  Goal, Plan, and external dependency protection, live-claim handoff, explicit
  currentness recovery, and exact readback closure without no-delta version
  churn.

## 2.1.0 - 2026-10-10

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
- Problem-discovery governance for designing stage-appropriate falsifiers,
  state and boundary coverage, side-effect observations, oracle challenges, and
  bounded escalation from deterministic evidence to real dependencies.
- Semantic version-bump enforcement for release-impacting Skills, plugin
  metadata, packaging, installation, and release-workflow changes.
- Exact local plugin-cache cleanup for removing verified historical versions
  after adoption.

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
- Code intelligence now treats local `.codegraph` state as refreshable derived
  state even during source-read-only structural work: stale, mismatched, or
  extraction-version-old indexes are synchronized and, when necessary, fully
  reindexed before any CodeGraph query is used.
- Durable provider operations are now owned through ordinary same-target
  delivery and readback by the task that created them, while historical open
  inventories require semantic-currentness and counterfactual-effect
  classification instead of user monitoring or batch replay.
- Authorized repository changes now include coherent, validated,
  non-rewriting local commits as ordinary stage checkpoints without a separate
  confirmation, while read-only gates, remote delivery, history rewriting, and
  destructive Git operations remain independently protected.
- The portable and compatibility manifests now use the semantic version from
  the project metadata instead of timestamp-only `2.0.0+codex.*` identities.

## 2.0.0 release candidate

- Reframed Work Governance as a composable, tool-neutral policy layer.
- Split goal discovery, Plan governance, SubAgent governance, Git boundaries,
  validation, project truth, archive curation, and reporting into independent
  Skills behind a small lifecycle router.
- Removed the embedded state engine and mandatory persistence coupling.
