---
schema_version: 4
plan_id: PLAN-20260731-003
title: Work Governance 1.0.5 local milestone release
status: active
mode: autonomous
revision: 1
created_at: '2026-07-31T09:13:04Z'
updated_at: '2026-07-31T09:13:04Z'
goal:
  statement: Mark the completed optimization milestone as Work Governance 1.0.5, validate
    the exact release bytes, install the release from the existing local marketplace,
    and prove fresh-session activation without remote publication.
  success_conditions:
  - pyproject.toml and uv.lock declare base version 1.0.5, while the Plugin manifest
    declares exactly one 1.0.5+codex.<UTC> build suffix.
  - The release-only diff is bounded to intended version metadata and passes lock,
    repository, static, Plugin, Skill, privacy, and Git-diff validation.
  - The release metadata is recorded in one reviewable local commit without absorbing
    unrelated worktree or governance state.
  - After exact-build live-switch authority, Codex reports the 1.0.5 build installed
    and enabled from work-governance-local with source and cache identity agreement.
  - A fresh SessionStart and UserPromptSubmit report READY for the exact 1.0.5 build,
    after which the Plan closes terminally.
contract:
  revision: 1
  confirmation_id: C-RELEASE-1-0-5
  confirmed_ref: user:session/019fb747-68b1-70b3-9974-d2dbd38cd476/turn/019fb770-a591-7a11-ae42-14a83bb76daf/sha256/ae3c6168a64689b36fb0ed0375b6e319956419028cfaedcc66bf7eb3201a4a08
scope:
  include:
  - Change the package base version from 1.0.4 to 1.0.5 in pyproject.toml and regenerate
    uv.lock through uv.
  - Change the Plugin manifest to base version 1.0.5 and run the supported cachebuster
    helper once to derive the exact 1.0.5+codex.<UTC> build.
  - Validate the exact release bytes with the repository's established validation
    boundary and create a bounded local release commit.
  - After exact-build live-switch confirmation, reinstall from the existing work-governance-local
    marketplace and verify enabled registration plus source, cache, controller, and
    hook identity.
  - Verify the exact release in a fresh session and commit the versioned governance
    closeout boundary locally.
  exclude:
  - description: Push, publish Git refs, create a remote tag or release, open a pull
      request, or otherwise inspect or mutate Git remote state.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-push-boundary
  - description: Create a new marketplace entry or hand-edit marketplace or Codex
      configuration files.
    disposition: forbidden
    resolution_ref: project:plugin-creator-supported-update-flow
  - description: Change implementation behavior, tests, lifecycle contracts, or documentation
      content beyond version-consistency adjustments proven necessary.
    disposition: forbidden
    resolution_ref: user:release-1.0.5-milestone-only
  - description: Delete, move, prune, clean, reset, or overwrite existing branches,
      worktrees, user changes, or unrelated governance evidence.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-change-protection
  - description: Install or activate the exact 1.0.5 candidate before C-LIVE-SWITCH
      is accepted against its immutable candidate evidence.
    disposition: pending_confirmation
    confirmation_id: C-LIVE-SWITCH
confirmations:
  required:
  - id: C-RELEASE-1-0-5
    description: Approve the exact local 1.0.5 milestone release preparation, validation,
      bounded commits, supported reinstall, and fresh-session verification without
      Git remote publication.
    status: accepted
    ref: user:session/019fb747-68b1-70b3-9974-d2dbd38cd476/turn/019fb770-a591-7a11-ae42-14a83bb76daf/sha256/ae3c6168a64689b36fb0ed0375b6e319956419028cfaedcc66bf7eb3201a4a08
    accepted_at: '2026-07-31T09:13:04Z'
    intervention:
      kind: plan_contract
      blocks:
      - route
      - task:T-001
      - task:T-002
      - task:T-003
      - task:T-004
      basis_ref: user:session/019fb747-68b1-70b3-9974-d2dbd38cd476/turn/019fb770-a591-7a11-ae42-14a83bb76daf/sha256/ae3c6168a64689b36fb0ed0375b6e319956419028cfaedcc66bf7eb3201a4a08
      basis_sha256: ae3c6168a64689b36fb0ed0375b6e319956419028cfaedcc66bf7eb3201a4a08
  - id: C-LIVE-SWITCH
    description: Authorize reinstall and activation of the exact validated 1.0.5+codex.<UTC>
      candidate after its commit and evidence are fixed.
    status: pending
    intervention:
      kind: external_authority
      blocks:
      - task:T-003
      - task:T-004
      - activation
      - route
      basis_ref: evidence:pending-1.0.5-live-switch-basis
  - id: C-PLAN-ROLLOVER
    description: Approve the terminal predecessor and exact successor Plan contract.
    status: accepted
    ref: user:session/019fb747-68b1-70b3-9974-d2dbd38cd476/turn/019fb775-b06e-7e71-bea0-df8250dcbb39/sha256/36f33adaf0942634a8ece1eec4a6f30d44dec73e1ef8704b29d983a57f2e09ae
    accepted_at: '2026-07-31T09:16:11Z'
    evidence_sha256: e20a0c803dfcd40ab053b08a7a9218857d551dba23769002b75e018dc33ba098
    intervention:
      kind: plan_contract
      blocks:
      - route
      basis_ref: project:confirmation-basis/e20a0c803dfcd40ab053b08a7a9218857d551dba23769002b75e018dc33ba098
      basis_sha256: e20a0c803dfcd40ab053b08a7a9218857d551dba23769002b75e018dc33ba098
unknowns: []
obligations:
- id: O-001
  description: All package and Plugin version authorities consistently represent the
    1.0.5 milestone with one supported cachebuster suffix.
  status: pending
- id: O-002
  description: The exact release-only diff passes the complete validation boundary
    and is preserved in a bounded local commit.
  status: pending
- id: O-003
  description: The exact 1.0.5 build is installed and enabled from the existing local
    marketplace with source-cache-runtime identity agreement.
  status: pending
- id: O-004
  description: Fresh-session evidence proves exact 1.0.5 activation and supports terminal
    closeout without remote publication or unrelated mutation.
  status: pending
tasks:
- id: T-001
  description: Bump pyproject.toml and uv.lock to base version 1.0.5, set the Plugin
    manifest base to 1.0.5, derive one supported UTC cachebuster, inspect the exact
    diff, and create a bounded local release metadata commit.
  status: pending
  unknowns: []
  expected_evidence_delta: The three version authorities are consistent, only intended
    release metadata changed, and one local commit records the exact candidate build.
- id: T-002
  description: Run lock consistency, the complete repository suite, Ruff format/check,
    strict mypy, Plugin and affected Skill validation, privacy scanning, and Git boundary
    checks on the exact candidate commit.
  status: pending
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: Every supported validation passes on the immutable release
    candidate, with no generated pollution or unrelated state change.
- id: T-003
  description: After C-LIVE-SWITCH acceptance against exact candidate evidence, reinstall
    work-governance from work-governance-local and verify installed, enabled, source,
    cache, controller, and hook identities.
  status: pending
  depends_on:
  - T-002
  unknowns: []
  expected_evidence_delta: Codex registers the exact 1.0.5 build as enabled and source,
    cache, controller, and hook bytes agree.
  requires_confirmation: C-LIVE-SWITCH
- id: T-004
  description: Obtain a fresh SessionStart and UserPromptSubmit for the exact 1.0.5
    build, verify Plan authority and work-lifecycle availability, complete canonical
    evidence and terminal closeout, and create the bounded governance commit.
  status: pending
  depends_on:
  - T-003
  unknowns: []
  expected_evidence_delta: Fresh-session READY evidence binds the exact release build,
    all O/V/A surfaces are verified, the route is terminal, and the worktree is clean.
  completion_scope: route
  requires_confirmation: C-LIVE-SWITCH
validations:
- id: V-001
  description: Verify pyproject.toml and uv.lock equal 1.0.5 and the Plugin manifest
    matches 1.0.5+codex.<single UTC token>.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:release-1.0.5
- id: V-002
  description: Run uv lock check, full pytest, Ruff format/check, strict mypy, Plugin
    validation, affected Skill validation, privacy scan, and Git diff checks.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:repository-validation-toolchain
- id: V-003
  description: Verify supported marketplace resolution, exact reinstall output, enabled
    Plugin registration, and recursive source-cache-runtime identity.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:codex-plugin-installation-contract
- id: V-004
  description: Verify fresh SessionStart and UserPromptSubmit receipts name the exact
    1.0.5 build and preserve READY, LAYOUT_READY, Plan authority, and lifecycle access.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:codex-plugin-fresh-session-contract
artifacts:
- id: A-001
  path: pyproject.toml
  status: pending
- id: A-002
  path: uv.lock
  status: pending
- id: A-003
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260731-003
  rollover_id: ROL-20260731-003
  predecessor:
    path: .work-governance/_Plan/PLAN-20260731-002.md
    plan_id: PLAN-20260731-002
    revision: 72
    sha256: 232115ad8f1aca6c7ead59b26635221028eab6ab8cbe73fd7478d2616b484c04
  sources: []
  confirmations:
    rollover: C-PLAN-ROLLOVER
delivery:
  status: pending
  boundary: local 1.0.5 release metadata commit plus versioned governance closeout;
    no Git remote publication
  evidence_ref: project:not-yet-delivered
activation:
  status: pending_confirmation
  current_ref: plugin:work-governance@1.0.4+codex.20260731075947
  target_ref: plugin:work-governance@1.0.5+codex.pending
  confirmation_id: C-LIVE-SWITCH
route:
  route_status: active
  slice_status: admission-pending
  next_phase: Activate the successor, prepare the exact 1.0.5 candidate, and validate
    it.
  validation_standard: Version authorities agree, the release diff is bounded, and
    the complete validation boundary passes before the live-switch gate.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Complete T-001 and T-002, then stop only at C-LIVE-SWITCH for the exact
    validated candidate.
revision_history:
- revision: 1
  kind: admission
  changed_at: '2026-07-31T09:13:04Z'
  rationale: Admit the user-confirmed 1.0.5 milestone release while preserving a separate
    exact-build live-switch gate.
  confirmation_id: C-RELEASE-1-0-5
intake:
  protocol_version: 1
  records:
  - request_ref: user:session/019fb747-68b1-70b3-9974-d2dbd38cd476/turn/019fb775-b06e-7e71-bea0-df8250dcbb39/sha256/36f33adaf0942634a8ece1eec4a6f30d44dec73e1ef8704b29d983a57f2e09ae
    request_sha256: 36f33adaf0942634a8ece1eec4a6f30d44dec73e1ef8704b29d983a57f2e09ae
    classification: plan_controlled
    targets:
    - route
    decision: proceed
    rationale: The user confirmed rollover proposal e20a0c803dfcd40ab053b08a7a9218857d551dba23769002b75e018dc33ba098;
      activate the exact successor and prepare the local 1.0.5 candidate.
    decision_basis_sha256: e84b2f301142b093c46bc597e180212500e7bbd21f576ef3325345c31d318960
    previous_record_sha256: null
    recorded_at: '2026-07-31T09:16:11Z'
    record_sha256: 4d7153540ed48a939fa62bfc7c6e3393258c2a6a13519269dbf4a723530f7986
---
# Work Governance 1.0.5 local milestone release

This successor treats 1.0.5 as the completed optimization milestone. It changes
only release metadata, validates the immutable candidate, then uses the supported
local marketplace reinstall flow.

Git remote publication is outside this route. The only execution pause after
rollover is the exact-build `C-LIVE-SWITCH` boundary before local reinstall.
