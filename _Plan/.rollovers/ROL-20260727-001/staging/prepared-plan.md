---
schema_version: 3
plan_id: PLAN-20260727-001
title: Subtask completion reporting and plugin activation
status: active
mode: autonomous
revision: 1
created_at: '2026-07-27T02:17:31Z'
updated_at: '2026-07-27T02:17:31Z'
scope:
  include:
  - Require a structured completion summary after every independently verifiable execution slice.
  - Define the reporting contract in work-lifecycle core guidance and L3/L6 references.
  - Add public README guidance and behavioral contract tests.
  - Run static, unit, plugin, skill, isolated-install, and independent validation.
  - Update the plugin cachebuster, create bounded local commits, and fast-forward local main.
  - Preserve live activation as a separately confirmed route-level decision.
  exclude:
  - description: Push, publish, create remote branches, or open a pull request.
    disposition: forbidden
    resolution_ref: user:implementation-plan-2026-07-27
  - description: Reinstall or switch the live Codex plugin before explicit approval.
    disposition: pending_confirmation
    confirmation_id: C-LIVE-SWITCH
  - description: Delete the retained feature branch or isolated worktree.
    disposition: forbidden
    resolution_ref: user:implementation-plan-2026-07-27
confirmations:
  required:
  - id: C-LIVE-SWITCH
    description: Decide whether to reinstall and activate the validated candidate in the live Codex installation.
    status: pending
obligations:
- id: O-001
  description: Every independently verifiable execution slice reports completion and purpose, validation, material decisions and basis, modifications, then the next step in that order.
  status: pending
- id: O-002
  description: Plan-controlled summaries name the T-ID, No-Plan work maps to one slice, and multiple completed slices are reported separately without hiding decisions or validation gaps.
  status: pending
- id: O-003
  description: In-progress, blocked, unverified, or SubAgent-only results cannot be presented as completed summaries, and no-change or no-decision cases use explicit wording.
  status: pending
- id: O-004
  description: The reporting contract remains a reply protocol and does not add Plan task-schema fields or turn the Plan into a process log.
  status: pending
- id: O-005
  description: README, lifecycle guidance, and behavioral tests describe and enforce the same contract.
  status: pending
- id: O-006
  description: The locally integrated candidate has fresh static, regression, plugin, isolated-install, and independent-review evidence before any live activation decision.
  status: pending
tasks:
- id: T-001
  description: Implement the subtask completion summary contract in work-lifecycle core guidance and L3/L6.
  status: pending
- id: T-002
  description: Add README guidance and behavioral contract tests for order, triggers, mappings, multi-slice reporting, explicit no-change/no-decision wording, and false-completion rejection.
  status: pending
  depends_on:
  - T-001
- id: T-003
  description: Run complete static, regression, plugin, skill, isolated-install, and independent validation and resolve findings.
  status: pending
  depends_on:
  - T-002
- id: T-004
  description: Update the plugin cachebuster, commit the validated candidate, record Plan startup and final state in bounded commits, and fast-forward local main.
  status: pending
  depends_on:
  - T-003
- id: T-005
  description: Decide live activation; if accepted, reinstall and verify Plan and No-Plan replies in a fresh Codex session, otherwise record the declined route.
  status: pending
  completion_scope: route
  depends_on:
  - T-004
  requires_confirmation: C-LIVE-SWITCH
validations:
- id: V-001
  description: Contract tests prove required fields, order, trigger boundaries, T-ID and No-Plan mapping, multi-slice behavior, explicit no-change/no-decision wording, and false-completion rejection.
  status: pending
- id: V-002
  description: Ruff format/check, mypy strict, and the complete pytest suite pass.
  status: pending
- id: V-003
  description: Plugin validator and every skill validator pass.
  status: pending
- id: V-004
  description: An isolated installation discovers the exact candidate cachebuster and its lifecycle/controller smoke passes.
  status: pending
- id: V-005
  description: Independent review finds no unresolved Blocker, High, or Medium issue in the contract, tests, evidence, or completion claims.
  status: pending
- id: V-006
  description: Local main is a clean fast-forward of the validated commits, and live activation is either freshly verified or explicitly declined.
  status: pending
artifacts:
- id: A-001
  path: plugins/work-governance/skills/work-lifecycle
  status: pending
- id: A-002
  path: tests
  status: pending
- id: A-003
  path: README.md
  status: pending
- id: A-004
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: pending
- id: A-005
  path: _Plan
  status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260727-001
  sources: []
  confirmations: {}
delivery:
  status: pending
  boundary: local-main-fast-forward
  evidence_ref: project:not-yet-delivered
activation:
  status: pending_confirmation
  current_ref: work-governance@0.1.0+codex.20260725015600
  target_ref: work-governance@candidate-undetermined
  confirmation_id: C-LIVE-SWITCH
route:
  route_status: active
  slice_status: initialized
  next_phase: Execute T-001 after the rollover is confirmed and committed.
  validation_standard: Fresh evidence directly proves every obligation and validation before local integration; live evidence is required only after C-LIVE-SWITCH acceptance.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Execute T-001 after the rollover is confirmed and committed.
---
# Subtask completion reporting

This Plan governs the reply-level completion summary contract, its tests and
documentation, candidate validation, local integration, and the separate live
activation decision.

The terminal rollover controller bootstrap is predecessor evidence delivered
by local commit `d47f821`; it is not reopened as work in this successor Plan.

The route must stop at `C-LIVE-SWITCH` after local `main` integration. No Push,
remote branch, pull request, live reinstall, or branch/worktree deletion is
authorized by this Plan.
