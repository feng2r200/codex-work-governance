---
schema_version: 3
plan_id: PLAN-20260728-001
title: Work Governance 1.0.2 legacy proposal migration and bootstrap diagnostics
status: active
mode: autonomous
revision: 1
created_at: '2026-07-28T01:41:31Z'
updated_at: '2026-07-28T01:41:31Z'
scope:
  include:
  - Deliver a 1.0.2 candidate that safely recognizes and migrates strictly valid work-governance
    reconciliation proposals from legacy _Plan/proposals/.
  - Keep migrated Plan authority under .work-governance/_Plan/ and move validated
    pending proposals separately to .work-governance/proposals/.
  - Preserve worktree-bound adoption, complete transaction manifests, input-drift
    protection, deterministic recovery, original bytes, and fail-closed classification.
  - Make SessionStart bootstrap failures report the observed layout cause and allowed
    recovery action without claiming that the hook which emitted the message did not
    run.
  - Preserve hook source and bounded session correlation in blocked bootstrap evidence.
  - Derive tests from the observed PharmaceuticalGroup failure, transaction invariants,
    and the supported SessionStart boundary.
  - Produce independently validated local commits and integrate the candidate into
    local main without Push.
  exclude:
  - description: Push, publish, create remote branches, or open a pull request.
    disposition: forbidden
    resolution_ref: user:2026-07-28-approve-1.0.2-candidate
  - description: Reinstall or activate the 1.0.2 candidate in the live Codex Plugin.
    disposition: pending_confirmation
    confirmation_id: C-LIVE-SWITCH-1-0-2
  - description: Mutate or migrate the PharmaceuticalGroup project in place.
    disposition: pending_confirmation
    confirmation_id: C-LIVE-SWITCH-1-0-2
  - description: Auto-apply, accept, or reinterpret a migrated reconciliation proposal.
    disposition: forbidden
    resolution_ref: user:2026-07-28-approve-1.0.2-candidate
  - description: Restore migration authority through a hardcoded AGENTS.md or CLAUDE.md
      override.
    disposition: forbidden
    resolution_ref: user:2026-07-27-remove-hardcoded-project-rules
  - description: Expand testing to hypothetical exhaustive coverage without a confirmed
      obligation, observed failure, code invariant, or supported integration boundary.
    disposition: not_required
    resolution_ref: user:2026-07-27-goal-first-stop-loss
confirmations:
  required:
  - id: C-LIVE-SWITCH-1-0-2
    description: Decide whether to reinstall the validated 1.0.2 candidate and run
      the live PharmaceuticalGroup migration probe.
    status: pending
  - id: C-PLAN-ROLLOVER
    description: Approve the terminal predecessor and exact successor Plan contract.
    status: accepted
    ref: user:2026-07-28-approve-1.0.2-candidate
    accepted_at: '2026-07-28T01:43:04Z'
    evidence_sha256: 35d700fe65854066e5cc9f61b4f7216b5bcd90fc039229878557b0e389051533
obligations:
- id: O-001
  description: A closed, non-symlinked legacy reconciliation proposal with supported
    schema and validated referenced files is classified as governance-owned without
    weakening the worktree-bound adoption requirement.
  status: pending
- id: O-002
  description: The recoverable layout transaction stages, validates, journals, activates,
    and proves the legacy proposal side tree separately at .work-governance/proposals/
    while Plan authority remains exclusively under .work-governance/_Plan/.
  status: pending
- id: O-003
  description: Proposal bytes and pending confirmation state are preserved, operational
    paths are changed only by explicit field-level conversion, and migration never
    applies or silently accepts a proposal.
  status: pending
- id: O-004
  description: Unknown, malformed, mixed, drifting, or symlinked legacy proposal content
    remains fail-closed and cannot be made migratable by a directory-name-only allowlist.
  status: pending
- id: O-005
  description: SessionStart blocked output distinguishes a hook-executed layout failure
    from hook absence and provides the exact state, blocker summary, evidence reference,
    and next allowed recovery action.
  status: pending
- id: O-006
  description: Blocked bootstrap evidence preserves hook source and a bounded session
    correlation value through durable failure-journal recovery without broadening
    the versioned receipt or leaking arbitrary hook input.
  status: pending
- id: O-007
  description: The exact 1.0.2 candidate passes scoped reality-bound migration probes,
    full regression and static validation, plugin and skill validation, independent
    review, and bounded local Git delivery while Push and live activation remain separate.
  status: pending
tasks:
- id: T-001
  description: Admit this successor Plan as a governance-only commit, create the isolated
    work-governance-1.0.2 branch/worktree from that exact baseline, and verify clean
    LAYOUT_READY and GOVERNED_ACTIVE state inside it.
  status: pending
- id: T-002
  description: Implement strict legacy proposal classification and separate journaled
    proposal staging, activation, proof, and recovery while preserving adoption and
    fail-closed behavior.
  status: pending
  depends_on:
  - T-001
- id: T-003
  description: Implement cause-specific SessionStart blocked messages and durable
    hook-source/session-correlation evidence, including interrupted failure-record
    recovery.
  status: pending
  depends_on:
  - T-001
- id: T-004
  description: Add only provenance-backed migration, recovery, drift, malformed-content,
    and startup/resume bootstrap tests; update the public contract where behavior
    changed.
  status: pending
  depends_on:
  - T-002
  - T-003
- id: T-005
  description: Run the cheapest exact failure-derived probe, full validation, causal
    and artifact independent review, set the 1.0.2 cachebuster, commit the candidate,
    and fast-forward local main with exact-path staging.
  status: pending
  depends_on:
  - T-004
- id: T-006
  description: If C-LIVE-SWITCH-1-0-2 is accepted, reinstall the exact candidate in
    live Codex, start a fresh target-project session, complete its adoption/migration
    path, and verify READY, separated Plan/proposal roots, preserved proposal state,
    and worktree isolation.
  status: pending
  completion_scope: route
  depends_on:
  - T-005
  requires_confirmation: C-LIVE-SWITCH-1-0-2
validations:
- id: V-001
  description: The exact legacy Plan plus MIG-20260727-001 proposal shape observed
    in PharmaceuticalGroup reaches only the adoption gate before confirmation and
    migrates to the two canonical roots after an exact worktree-bound adoption receipt.
  status: pending
- id: V-002
  description: Manifest correspondence proves every proposal file is preserved or
    explicitly field-converted, no confirmation becomes accepted, and no proposal
    remains under .work-governance/_Plan/.
  status: pending
- id: V-003
  description: Interruptions before and after proposal activation recover deterministically;
    proposal source or staging drift blocks activation without guessing.
  status: pending
- id: V-004
  description: Malformed manifests, broken references, mixed business files, and symlinked
    proposal paths remain LEGACY_CLASSIFICATION_REQUIRED.
  status: pending
- id: V-005
  description: Startup and resume blocked runs record source/correlation and emit
    the actual classification/adoption recovery path rather than a false hook-trust
    claim.
  status: pending
- id: V-006
  description: Ruff, strict mypy, full pytest, plugin/skill validators, source-to-candidate
    equality, and independent causal/artifact/evidence review pass for the exact candidate.
  status: pending
- id: V-007
  description: Plan admission, candidate implementation, and any later live activation
    remain separate Git and confirmation boundaries; local main contains no unrelated
    changes and Push is untouched.
  status: pending
artifacts:
- id: A-001
  path: plugins/work-governance/scripts/workctl.py
  status: pending
- id: A-002
  path: plugins/work-governance/hooks/session_start.py
  status: pending
- id: A-003
  path: tests
  status: pending
- id: A-004
  path: README.md
  status: pending
- id: A-005
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: pending
- id: A-006
  path: .work-governance/_Plan
  status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260728-001
  rollover_id: ROL-20260728-001
  predecessor:
    path: .work-governance/_Plan/PLAN-20260727-002.md
    plan_id: PLAN-20260727-002
    revision: 110
    sha256: e904880adb47fca991906d69c6f21676150ad794ac19e86a2cfc6901c5ebec4f
  sources: []
  confirmations:
    rollover: C-PLAN-ROLLOVER
delivery:
  status: pending
  boundary: local-main-fast-forward
  evidence_ref: project:PLAN-20260728-001-not-yet-delivered
activation:
  status: pending_confirmation
  current_ref: work-governance@1.0.1+codex.20260727181800
  target_ref: work-governance@1.0.2+codex.pending-cachebuster
  confirmation_id: C-LIVE-SWITCH-1-0-2
route:
  route_status: active
  slice_status: initialized
  next_phase: Admit T-001 and implement the smallest migration and bootstrap slices.
  validation_standard: The observed legacy proposal reaches a deterministic safe migration
    path, blocked SessionStart evidence names the real cause, the candidate passes
    fresh validation, and live activation remains confirmation-bound.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Execute T-001 from the admitted governance baseline.
---
# Work Governance 1.0.2 candidate

This successor fixes the first real legacy project that exercised 1.0.1 after
release. The observed SessionStart hook ran correctly, but the legacy classifier
treated an existing work-governance reconciliation proposal as unknown content
and the generic blocked message incorrectly advised restoring the same hook.

The causal correction is not a `proposals/` name allowlist. A valid legacy
proposal is a separate non-authoritative side tree: it must be proven
governance-owned, bound to the worktree adoption snapshot, journaled and staged
separately, then activated at `.work-governance/proposals/` without accepting or
applying it. Anything outside that closed contract remains fail-closed.

Local implementation and candidate delivery are authorized by
`user:2026-07-28-approve-1.0.2-candidate`. Reinstallation and in-place migration
of PharmaceuticalGroup remain behind `C-LIVE-SWITCH-1-0-2`; Push is forbidden.
