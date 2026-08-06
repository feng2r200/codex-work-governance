---
schema_version: 4
plan_id: PLAN-20260806-001
title: Governance friction reduction round 1
status: active
mode: autonomous
revision: 1
created_at: "2026-08-06T08:20:17Z"
updated_at: "2026-08-06T08:20:17Z"
goal:
  statement: "Implement the first-round Work Governance friction reduction so the controller exposes model-friendly workflow commands, minimal active contracts, read-only historical tolerance, model-owned confirmation judgment support, and non-authoritative worktree logs without weakening local evidence, receipt, layout, recovery, and regression guarantees."
  success_conditions:
    - "High-level `goal init`, `plan adapt --intent-stdin`, `task done`, `plan history`, `risk inspect`, and `worktree` workflow surfaces are executable or deliberately bounded compatibility aliases with generated CLI documentation."
    - "Active schema-v5 validation accepts the minimal contract fields named by the user plan and keeps task runtime state, evidence, dependencies, notes, and history out of the required contract."
    - Historical Plan reads are tolerant and do not block active intake because older or malformed historical records are summarized read-only.
    - "Lifecycle guidance removes route/action lease as a default repeated-action recommendation and explains confirmation as a model judgment based on current authority, reversibility, risk, and project rules."
    - "Worktree logs are explicitly `NON_AUTHORITY` and only their close summaries can be referenced by the main Plan evidence."
    - "Focused tests, generated CLI reference checks, static checks, and a deterministic validation pass prove the changed executable and documentation surfaces."
contract:
  revision: 1
  confirmation_id: C-GOVERNANCE-FRICTION-PLAN-2026
  confirmed_ref: user:session/019fd628-853b-7121-b41b-03885bff6197/turn/019fd628-866a-7a30-86ac-4ad644f8f449/sha256/e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
scope:
  include:
    - "Add model-friendly workflow commands while preserving existing low-level `--manifest` command compatibility."
    - Reduce schema-v5 active contract requirements to the minimal user-approved contract and move task runtime facts to runtime state/event/evidence ledgers.
    - Add read-only historical Plan list/show behavior that tolerates legacy or malformed history without active schema validation.
    - Replace lease-centered lifecycle recommendations with model-owned confirmation judgment principles and read-only risk inspection.
    - Add non-authoritative worktree begin/record/close logging and summary references.
    - "Update docs, generated CLI reference, and tests for the implemented first-round surface."
  exclude:
    -
      description: "Remove uv, hooks, or replace the Plugin runtime in this first round."
      disposition: forbidden
      resolution_ref: user:current-plan-no-uv-hooks-runtime-replacement
    -
      description: "Install, reinstall, enable, disable, or activate the live Work Governance Plugin in this round."
      disposition: forbidden
      resolution_ref: user:local-implementation-boundary
    -
      description: "Push, publish Git refs, create a remote tag or release, open a pull request, or mutate any Git remote state."
      disposition: forbidden
      resolution_ref: project:root-AGENTS-push-boundary
    -
      description: "Delete, reset, clean, prune, overwrite, or submit unrelated user changes, worktrees, runtime evidence, caches, or logs."
      disposition: forbidden
      resolution_ref: project:root-AGENTS-change-protection
confirmations:
  required:
    -
      id: C-GOVERNANCE-FRICTION-PLAN-2026
      description: "Authorize the local first-round governance friction reduction implementation, focused verification, and local commit while preserving explicit no-go boundaries."
      status: accepted
      ref: user:session/019fd628-853b-7121-b41b-03885bff6197/turn/019fd628-866a-7a30-86ac-4ad644f8f449/sha256/e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
      accepted_at: "2026-08-06T08:20:17Z"
      evidence_sha256: e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
      intervention:
        kind: plan_contract
        blocks:
          - route
          - task:T-001
          - task:T-002
          - task:T-003
          - task:T-004
          - task:T-005
          - delivery
        basis_ref: user:session/019fd628-853b-7121-b41b-03885bff6197/turn/019fd628-866a-7a30-86ac-4ad644f8f449/sha256/e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
        basis_sha256: e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
    -
      id: C-PLAN-ROLLOVER
      description: Approve the terminal predecessor and exact successor Plan contract.
      status: accepted
      ref: user:session/019fd628-853b-7121-b41b-03885bff6197/turn/019fd628-866a-7a30-86ac-4ad644f8f449/sha256/e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
      accepted_at: "2026-08-06T08:20:17Z"
      evidence_sha256: 8a6da666f43b73ced724e520252a9bbe6a80c1c37ed5fa51f3fac72c318ef74d
      intervention:
        kind: plan_contract
        blocks:
          - route
        basis_ref: project:confirmation-basis/8a6da666f43b73ced724e520252a9bbe6a80c1c37ed5fa51f3fac72c318ef74d
        basis_sha256: 8a6da666f43b73ced724e520252a9bbe6a80c1c37ed5fa51f3fac72c318ef74d
unknowns: []
obligations:
  -
    id: O-001
    description: Controller workflow surfaces reduce model command/schema burden without removing low-level compatibility.
    status: pending
  -
    id: O-002
    description: Active schema-v5 validation accepts the minimal contract and separates runtime task/evidence/history state.
    status: pending
  -
    id: O-003
    description: Historical Plan commands summarize legacy or malformed Plans read-only without active schema enforcement.
    status: pending
  -
    id: O-004
    description: Confirmation guidance is model-owned and risk-informed rather than controller-enforced through route/action lease defaults.
    status: pending
  -
    id: O-005
    description: Worktree ledgers are non-authoritative and can emit close summaries for main Plan evidence.
    status: pending
  -
    id: O-006
    description: "Regression coverage preserves layout ready, receipt checks, read-only views, direct evidence capture, doctor, and migration recovery."
    status: pending
tasks:
  -
    id: T-001
    description: "Capture current code, docs, tests, CLI, schema, and governance baselines for the first-round friction reduction."
    status: pending
    unknowns: []
    expected_evidence_delta: "Baseline evidence identifies exact implementation points and confirms no live Plugin, remote, or unrelated worktree action is required."
  -
    id: T-002
    description: "Implement controller changes for high-level workflow commands, minimal active schema validation, tolerant history reads, risk inspection, and non-authoritative worktree logging."
    status: pending
    depends_on:
      - T-001
    unknowns: []
    expected_evidence_delta: Focused controller tests prove the new command surfaces and schema/history/worktree/risk behavior.
  -
    id: T-003
    description: "Update lifecycle, generated CLI reference, and model-first documentation so command usage and confirmation judgment match the executable surface."
    status: pending
    depends_on:
      - T-002
    unknowns: []
    expected_evidence_delta: Documentation and generated reference describe implemented behavior and no longer recommend lease-first confirmation control.
  -
    id: T-004
    description: "Run focused regression, CLI generation checks, static checks, schema tests, and recovery/read-only smoke probes; fix evidence-backed defects only."
    status: pending
    depends_on:
      - T-003
    unknowns: []
    expected_evidence_delta: Fresh validation output covers all must-have obligations and reports any residual gaps honestly.
  -
    id: T-005
    description: "Perform independent validation or deterministic self-challenge, review changed-file scope, record local delivery evidence, and create one local commit without Push or activation."
    status: pending
    depends_on:
      - T-004
    unknowns: []
    expected_evidence_delta: "Review evidence, git diff checks, and local commit identity prove the first-round local delivery boundary."
validations:
  -
    id: V-001
    description: Validate high-level workflow command behavior and compatibility with existing low-level manifest commands.
    status: pending
    provenance:
      kind: confirmed-obligation
      source_ref: project:O-001
  -
    id: V-002
    description: "Validate minimal active schema-v5 contracts, tolerant history reads, runtime-state separation, and worktree non-authority."
    status: pending
    provenance:
      kind: confirmed-obligation
      source_ref: project:O-002
  -
    id: V-003
    description: Validate lifecycle and CLI documentation freshness against parser-generated output and implemented behavior.
    status: pending
    provenance:
      kind: confirmed-obligation
      source_ref: project:O-004
  -
    id: V-004
    description: "Validate existing read-only, layout, receipt, evidence capture, doctor, migration, and core controller regression behavior remains intact."
    status: pending
    provenance:
      kind: code-invariant
      source_ref: project:regression-suite
  -
    id: V-005
    description: "Validate changed-file scope, independent/self-review findings, and local commit boundary."
    status: pending
    provenance:
      kind: confirmed-obligation
      source_ref: project:root-AGENTS-change-protection
artifacts:
  -
    id: A-001
    path: plugins/work-governance/scripts/workctl.py
    status: pending
  -
    id: A-002
    path: plugins/work-governance/scripts/workctl_modules/
    status: pending
  -
    id: A-003
    path: plugins/work-governance/skills/work-lifecycle/
    status: pending
  -
    id: A-004
    path: docs/CLI_REFERENCE.md
    status: pending
  -
    id: A-005
    path: docs/MODEL_FIRST.md
    status: pending
  -
    id: A-006
    path: tests/
    status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260806-001
  rollover_id: ROL-20260806-001
  predecessor:
    path: .work-governance/_Plan/PLAN-20260804-001.md
    plan_id: PLAN-20260804-001
    revision: 80
    sha256: af340717aceeee349730562688de7f9e7cb52ed1ec5bd983ac977fbe4ad41e3e
  sources: []
  confirmations:
    rollover: C-PLAN-ROLLOVER
delivery:
  status: pending
  boundary: local-branch-and-local-commit
  evidence_ref: project:not-yet-delivered
activation:
  status: not_required
  current_ref: not-applicable
  target_ref: not-applicable
  decision_ref: user:local-implementation-boundary
route:
  route_status: active
  slice_status: admitted
  next_phase: Execute T-001 baseline and implementation mapping.
  validation_standard: Fresh local command and file evidence covers the selected task before advancement.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Execute T-001 baseline and implementation mapping.
revision_history:
  -
    revision: 1
    kind: admission
    changed_at: "2026-08-06T08:20:17Z"
    rationale: Admit the user-confirmed first-round friction reduction contract.
    confirmation_id: C-GOVERNANCE-FRICTION-PLAN-2026
intake:
  protocol_version: 1
  records:
    -
      request_ref: user:session/019fd628-853b-7121-b41b-03885bff6197/turn/019fd628-866a-7a30-86ac-4ad644f8f449/sha256/e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
      request_sha256: e78ca93088d4915c5fafe5c70fc3373b850257b133bdd3dde1c5988b930afa3a
      classification: plan_controlled
      targets:
        - route
      decision: proceed
      rationale: "User supplied an explicit implementation plan; local first-round delivery has no current user-owned blocker."
      decision_basis_sha256: 6658a47b0e813a2898e38e775ab00118bdbcbbde5a058c5ea26840ceecc32952
      previous_record_sha256: null
      recorded_at: "2026-08-06T08:20:17Z"
      record_sha256: d37938c38fb5f82334f410d38edc62a30171a303b486d7339bc49c2755c844b8
---
# Governance Friction Reduction Round 1

This Plan tracks the local implementation of the first-round governance friction
reduction described by the current user instruction. It intentionally separates
local delivery from live Plugin activation and remote publication.
