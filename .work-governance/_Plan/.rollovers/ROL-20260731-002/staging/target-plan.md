---
schema_version: 4
plan_id: PLAN-20260731-002
title: User intervention governance and independent audit contracts
status: active
mode: autonomous
revision: 1
created_at: '2026-07-31T05:00:00Z'
updated_at: '2026-07-31T05:00:00Z'
goal:
  statement: Make Work Governance ask for user input only at decision-owning boundaries,
    continue autonomously across dependency-ready execution, and enforce machine-readable
    independent review gates before high-impact completion.
  success_conditions:
  - Lifecycle guidance consistently distinguishes communication from waiting, routes
    agent-owned unknowns to exploration, and rejects decision-free continuation prompts.
  - Confirmations carry strict intervention metadata for plan contracts, external
    authority, and evidence-proven deviation recovery; legacy pending gates remain
    readable but cannot advance before classification.
  - Plan status deterministically projects intervention contract readiness and the
    exact user-intervention state, blockers, and typed basis.
  - Independent Plan challenge and artifact/evidence audit are first-class, hash-bound
    Plan evidence; blocker/high findings stop downstream work, activation, and closeout.
  - Focused behavioral tests, the full repository suite, static checks, Plugin and
    affected Skill validation, privacy scanning, and independent audit pass before
    a bounded local candidate commit.
  - Live installation, a new cachebuster, and fresh-session activation occur only
    after C-LIVE-SWITCH is separately accepted; no Push, remote mutation, or cleanup
    occurs.
contract:
  revision: 1
  confirmation_id: C-IMPLEMENT-INTERVENTION-GOVERNANCE
  confirmed_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
scope:
  include:
  - Preserve the single work-lifecycle entry and existing unknown, intake, confirmation,
    and L5 architecture while tightening when execution waits for the user.
  - Update lifecycle core, L0, L1, L3, L5, L6, independent-validation guidance, and
    README with the communication, intervention, continuous-execution, and audit contracts.
  - Add strict intervention metadata, confirmation classification, status projection,
    legacy compatibility, and fail-closed validation to workctl.py.
  - Add Plan-level independent_validation state, the plan independent-review record
    command, reviewer-isolation rules, finding severity gates, and activation/closeout
    blockers.
  - Add obligation-derived controller, Skill-contract, and end-to-end behavioral tests,
    including same-route multi-task execution without repeated continuation gates.
  - Create an isolated feature worktree from exact local main, complete independent
    Plan and artifact/evidence reviews, and create bounded local commits.
  - After separate C-LIVE-SWITCH acceptance, use supported helpers to refresh the
    cachebuster on base 1.0.4, reinstall from work-governance-local, and verify exact
    fresh-session activation before closeout.
  exclude:
  - description: Push, publish, create or update a remote branch, open a pull request,
      or otherwise mutate remote state.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-push-boundary
  - description: Delete, move, prune, or clean any existing worktree or branch, including
      intake-clarification.
    disposition: forbidden
    resolution_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
  - description: Reuse or structurally reopen PLAN-20260731-001.
    disposition: forbidden
    resolution_ref: project:terminal-plan-rollover-contract
  - description: Modify production systems, external projects, user data, or business
      runtime state.
    disposition: forbidden
    resolution_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
  - description: Install, enable, or live-activate a candidate before C-LIVE-SWITCH
      is accepted.
    disposition: pending_confirmation
    confirmation_id: C-LIVE-SWITCH
  - description: Increase the base Plugin version above 1.0.4 or hand-edit marketplace
      or Codex configuration state.
    disposition: forbidden
    resolution_ref: project:plugin-creator-cachebuster-policy
  - description: Treat same-context review as verified independent validation for
      a high-impact completion claim.
    disposition: forbidden
    resolution_ref: project:independent-validation-isolation-contract
confirmations:
  required:
  - id: C-IMPLEMENT-INTERVENTION-GOVERNANCE
    description: Approve the exact local implementation and validation contract for
      user-intervention governance and independent audit enforcement.
    status: accepted
    ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
    accepted_at: '2026-07-31T05:00:00Z'
    intervention:
      kind: plan_contract
      blocks:
      - route
      - task:T-001
      - task:T-002
      - task:T-003
      - task:T-004
      - task:T-005
      - task:T-006
      - task:T-007
      - task:T-008
      basis_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
      basis_sha256: 5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
  - id: C-LIVE-SWITCH
    description: Authorize the exact validated candidate commits and evidence basis,
      supported derivation of one new 1.0.4+codex.<UTC> build, local Plugin reinstall,
      and fresh-session activation verification without Push.
    status: pending
    intervention:
      kind: external_authority
      blocks:
      - task:T-007
      - activation
      - route
      basis_ref: evidence:pending-exact-live-switch-basis
  - id: C-PLAN-ROLLOVER
    description: Approve the terminal predecessor and exact successor Plan contract.
    status: accepted
    ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
    accepted_at: '2026-07-31T05:18:00Z'
    evidence_sha256: 1bada77af689ec9a547422dc939a683727508f1debd940eda0af4d326a463eb3
unknowns: []
obligations:
- id: O-001
  description: Lifecycle guidance asks only for user-owned requirement input, material
    Plan decisions, evidence-proven deviation recovery, or external authority, while
    ordinary progress communication never becomes a wait gate.
  status: pending
- id: O-002
  description: The controller validates strict intervention metadata, classifies legacy
    pending confirmations, and rejects generic continuation gates on new Plans, rollovers,
    reconciliation, and contract revision.
  status: pending
- id: O-003
  description: Plan status projects intervention_contract_state and user_intervention
    state with exact blocking targets and typed basis without changing the existing
    intake and target-coverage APIs.
  status: pending
- id: O-004
  description: A Plan-level independent_validation contract and independent-review
    command preserve reviewer isolation, artifact hashes, findings, evidence, and
    degraded-state limitations.
  status: pending
- id: O-005
  description: Each review mode blocks only its declared downstream targets; blocker/high
    findings and unaccepted degraded high-impact review preserve those blocks, while
    verified isolated review or separately accepted degraded-risk authority releases
    them.
  status: pending
- id: O-006
  description: Provenance-backed tests demonstrate continuous same-turn multi-slice
    execution and every required intervention, legacy, deviation, authority, and independence
    scenario.
  status: pending
- id: O-007
  description: The local candidate and any later activation metadata are committed
    in bounded reviewable commits, pass complete validation and independent audit,
    preserve unrelated state, and never Push.
  status: pending
tasks:
- id: T-001
  description: Run an isolated read-only Plan challenge against this successor contract,
    activate it through digest-bound rollover, record the challenge through the predecessor
    controller's existing evidence-bound V-001 and T-001 transitions without claiming
    the future strict review command ran, and create the exact feature/user-intervention-governance
    worktree from verified clean local main.
  status: pending
  unknowns: []
  expected_evidence_delta: An isolated reviewer reports no blocker/high Plan finding,
    the successor is GOVERNED_ACTIVE, canonical evidence verifies V-001 and T-001
    through supported current-controller transitions, and the new worktree is registered
    at the exact governed path without changing existing worktrees; independent_validation
    remains pending until the strict recorder is live.
- id: T-002
  description: Update lifecycle, independent-validation, and README contracts for
    communication versus waiting, four intervention classes, autonomous diagnosis,
    L5 direction shifts, continuous execution, and independent audit.
  status: pending
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: Skill contract tests and direct inspection show one lifecycle
    entry, no decision-free continuation prompt, and explicit audit isolation and
    degraded-state semantics.
- id: T-003
  description: Implement strict intervention schema, legacy pending-gate classification,
    status projections, Plan-level independent_validation, review recording, severity
    blocking, and activation/closeout integration in workctl.py.
  status: pending
  depends_on:
  - T-002
  unknowns: []
  expected_evidence_delta: Focused controller probes accept only typed interventions,
    deterministically project user intervention, preserve accepted legacy gates, and
    fail closed on missing review or isolation evidence.
- id: T-004
  description: Add and run focused controller, Skill-contract, and end-to-end behavior
    tests for all confirmed intervention and audit scenarios, then run the complete
    repository validation boundary.
  status: pending
  depends_on:
  - T-003
  unknowns: []
  expected_evidence_delta: Focused and full tests, Ruff, mypy, Plugin/Skill validation,
    privacy scanning, and Git diff checks pass on exact candidate bytes.
- id: T-005
  description: Run isolated artifact-review and evidence-audit passes over the raw
    candidate diff and validation evidence, fix every blocker/high finding, and record
    both reviews through the current controller's canonical V-007, V-008, and T-005
    evidence transitions without claiming the future strict review command ran.
  status: pending
  depends_on:
  - T-004
  unknowns: []
  expected_evidence_delta: Both isolated review modes report no unresolved blocker/high
    finding, canonical evidence verifies V-007, V-008, and T-005, the bootstrap release
    permits only candidate commit and gated installation preparation, and live Plugin,
    remote refs, and unrelated state remain unchanged.
- id: T-006
  description: Create bounded local candidate commit or commits containing only implementation,
    direct tests, and required documentation, then classify C-LIVE-SWITCH against
    an immutable basis manifest naming the exact candidate commits, validation and
    review evidence, supported cachebuster derivation rule, and intended activation
    boundary.
  status: pending
  depends_on:
  - T-005
  unknowns: []
  expected_evidence_delta: Exact candidate commits are reviewable, the live-switch
    basis digest binds those commits and the post-gate derivation rule, main and live
    Plugin remain unchanged, no Push occurs, and T-007 is the only current authority
    gate.
- id: T-007
  description: After C-LIVE-SWITCH acceptance bound to the exact candidate basis,
    use supported helpers to derive one exact 1.0.4+codex.<UTC> target, commit only
    expected metadata, reinstall the exact build, obtain a fresh SessionStart/UserPromptSubmit
    context, and use plan independent-review record as the only blocked-state migration
    command to convert the exact bootstrap evidence for all three review modes into
    strict records.
  status: pending
  depends_on:
  - T-006
  requires_confirmation: C-LIVE-SWITCH
  unknowns: []
  expected_evidence_delta: Exact source, cache, runtime, and hook identities agree;
    all three bootstrap reviews are migrated through the strict recorder; no activation
    promotion, closeout, Push, or unrelated mutation occurs in this task.
- id: T-008
  description: After strict review migration releases its exact blocks, run the final
    isolated activation evidence audit, promote activation, complete delivery evidence,
    verify every obligation, validation, and artifact, and close out the successor.
  status: pending
  depends_on:
  - T-007
  completion_scope: route
  unknowns: []
  expected_evidence_delta: Final isolated audit reports no blocker/high finding, exact
    build activation and all route evidence are complete, no Push occurred, and closeout
    is ready.
validations:
- id: V-001
  description: An isolated Plan challenge maps goal, obligations, dependencies, gates,
    stop conditions, test provenance, activation boundary, and closeout wording to
    the current user contract.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
- id: V-002
  description: Skill and README contract checks prove communication does not create
    a wait gate and only the four defined user-intervention boundaries can pause progress.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: project:O-001
- id: V-003
  description: Controller tests prove strict intervention validation, legacy classification,
    deterministic status projections, unchanged intake target coverage, and generic-gate
    refusal.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
- id: V-004
  description: Independent-review tests prove raw-artifact isolation, digest binding,
    degraded-state handling, blocker/high enforcement, risk acceptance, and activation/closeout
    blocking.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
- id: V-005
  description: End-to-end behavior tests prove one route-level proceed decision can
    cross multiple dependency-ready tasks, validations, and evidence states until
    a contract, unknown, or route-structure change invalidates the baseline.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
- id: V-006
  description: Full pytest, Ruff format and check, strict mypy, Plugin and affected
    Skill validation, privacy scan, and exact Git diff checks pass on candidate bytes.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:repository-validation-toolchain
- id: V-007
  description: An isolated artifact review examines the raw diff, schema behavior,
    generated outputs, and Git boundary with no unresolved blocker/high finding.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: project:root-AGENTS-independent-validation
- id: V-008
  description: An isolated evidence audit verifies that focused and full checks, test
    provenance, deterministic evidence, and proposed completion wording prove the
    exact obligations with no unresolved blocker/high finding.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: project:root-AGENTS-independent-validation
- id: V-009
  description: After C-LIVE-SWITCH, a fresh session and final isolated audit verify
    exact Plugin identity, both hooks, Plan authority, intervention projections, review
    evidence, and absence of Push.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:codex-plugin-activation-contract
artifacts:
- id: A-001
  path: plugins/work-governance/scripts/workctl.py
  status: pending
- id: A-002
  path: tests/test_workctl.py
  status: pending
- id: A-003
  path: tests/test_turn_intake.py
  status: pending
- id: A-004
  path: tests/test_work_lifecycle_skill.py
  status: pending
- id: A-005
  path: plugins/work-governance/skills/work-lifecycle
  status: pending
- id: A-006
  path: plugins/work-governance/skills/independent-validation
  status: pending
- id: A-007
  path: README.md
  status: pending
- id: A-008
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: pending
independent_validation:
  required: true
  state: pending
  required_modes:
  - plan_challenge
  - artifact_review
  - evidence_audit
  implementation_context_ref: context:pending-implementation
  reviews:
  - mode: plan_challenge
    state: pending
    blocks:
    - task:T-002
    - task:T-003
    - task:T-004
    - task:T-005
    - task:T-006
    - task:T-007
    - task:T-008
    - delivery
    - activation
    - route
    review_context_ref: context:pending-plan-challenge
    reviewed_contract_sha256: null
    reviewed_artifacts: []
    findings: []
    evidence_ref: project:pending-plan-challenge
    evidence_sha256: null
    release_condition: State is verified with no unresolved blocker/high finding,
      or state is degraded and a separate accepted risk-authority confirmation is
      bound to this exact review evidence.
    bootstrap_release:
      controller_build: plugin:work-governance@1.0.4+codex.20260731031511
      evidence_mapping:
      - validation:V-001
      - task:T-001
      releases:
      - task:T-002
      - task:T-003
      - task:T-004
      - task:T-005
      - task:T-006
      - task:T-007
      limitation: Release applies only when both mapped entries carry canonical evidence
        for the exact reviewed successor contract; it does not change review state,
        release task:T-008, delivery, activation, or route, or claim the strict recorder
        ran.
  - mode: artifact_review
    state: pending
    blocks:
    - task:T-006
    - task:T-007
    - task:T-008
    - delivery
    - activation
    - route
    review_context_ref: context:pending-artifact-review
    reviewed_contract_sha256: null
    reviewed_artifacts: []
    findings: []
    evidence_ref: project:pending-artifact-review
    evidence_sha256: null
    release_condition: State is verified with no unresolved blocker/high finding,
      or state is degraded and a separate accepted risk-authority confirmation is
      bound to this exact review evidence.
    bootstrap_release:
      controller_build: plugin:work-governance@1.0.4+codex.20260731031511
      evidence_mapping:
      - validation:V-007
      - task:T-005
      releases:
      - task:T-006
      - task:T-007
      limitation: Release permits only the reviewed candidate commit and the separately
        authorized installation/migration task; it does not release task:T-008, delivery,
        activation, or route and does not claim the strict recorder ran.
  - mode: evidence_audit
    state: pending
    blocks:
    - task:T-006
    - task:T-007
    - task:T-008
    - delivery
    - activation
    - route
    review_context_ref: context:pending-evidence-audit
    reviewed_contract_sha256: null
    reviewed_artifacts: []
    findings: []
    evidence_ref: project:pending-evidence-audit
    evidence_sha256: null
    release_condition: State is verified with no unresolved blocker/high finding,
      or state is degraded and a separate accepted risk-authority confirmation is
      bound to this exact review evidence.
    bootstrap_release:
      controller_build: plugin:work-governance@1.0.4+codex.20260731031511
      evidence_mapping:
      - validation:V-008
      - task:T-005
      releases:
      - task:T-006
      - task:T-007
      limitation: Release permits only the audited candidate commit and the separately
        authorized installation/migration task; it does not release task:T-008, delivery,
        activation, or route and does not claim the strict recorder ran.
  finding_gate:
    blocking_severities:
    - blocker
    - high
    behavior: Every unresolved blocking finding preserves all blocks declared by its
      review mode and freezes any already-started downstream target before activation
      or closeout.
  degraded_gate:
    high_impact_completion_allowed: false
    risk_acceptance_kind: external_authority
    requirement: A degraded review releases its declared blocks only through a separate
      accepted confirmation whose basis_ref and basis_sha256 bind the exact degraded
      review evidence.
  bootstrap_bridge:
    controller_build: plugin:work-governance@1.0.4+codex.20260731031511
    allowed_transitions:
    - plan evidence record
    - plan verify-entry V-001
    - task start T-001
    - task verify T-001
    - plan verify-entry V-007
    - plan verify-entry V-008
    - task start T-005
    - task verify T-005
    migration_exception:
      command: plan independent-review record
      allowed_while_blocked: true
      scope: The command may only migrate an exact bootstrap review whose controller
        build and canonical V/T evidence mapping match this contract; every other
        blocked-state mutation remains forbidden.
    limitation: These evidence-bound transitions activate only the per-mode bootstrap
      releases and do not set independent_validation.state or any review state to
      verified. The exact canonical evidence for all three modes must be migrated
      through the sole blocked-state command in task:T-007 before task:T-008, delivery,
      activation, or route can advance.
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260731-002
  rollover_id: ROL-20260731-002
  predecessor:
    path: .work-governance/_Plan/PLAN-20260731-001.md
    plan_id: PLAN-20260731-001
    revision: 35
    sha256: 940d1a841bf466898d845b091fa87523488a2523d85c8a7483ba1de00572bf71
  sources: []
  confirmations:
    rollover: C-PLAN-ROLLOVER
delivery:
  status: pending
  boundary: local feature candidate plus separately authorized Plugin metadata commit;
    no Push
  evidence_ref: project:not-yet-delivered
activation:
  status: pending_confirmation
  current_ref: plugin:work-governance@1.0.4+codex.20260731031511
  target_ref: plugin:work-governance@1.0.4+codex.pending
  confirmation_id: C-LIVE-SWITCH
route:
  route_status: active
  slice_status: admission-pending
  next_phase: Complete isolated Plan challenge, activate the successor, and establish
    the feature worktree.
  validation_standard: V-001 has verified isolated evidence, successor authority is
    GOVERNED_ACTIVE, and the exact worktree baseline is protected.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Continue all local candidate work through T-006; classify and bind the
    exact candidate basis, then stop only before T-007 at C-LIVE-SWITCH.
revision_history:
- revision: 1
  kind: admission
  changed_at: '2026-07-31T05:00:00Z'
  rationale: Admit the user-confirmed local implementation route while preserving
    a separate live-switch authority gate.
  confirmation_id: C-IMPLEMENT-INTERVENTION-GOVERNANCE
intake:
  protocol_version: 1
  records:
  - request_ref: user:session/019fb699-8cc4-71d3-9e68-f15601f4affb/turn/019fb699-8df7-7273-890f-c536be478228/sha256/5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
    request_sha256: 5174bab3869c416b351c61c09d0f3cb8e662b626f6d55af0aa72efd2eafb95ef
    classification: plan_controlled
    targets:
    - route
    decision: proceed
    rationale: The isolated Plan challenge passed with no blocker or high finding,
      and no user-owned unknown blocks successor rollover or local candidate execution.
    decision_basis_sha256: 90a647cd26fc520fd4988fff46e983ca4ae812ef3af89b73e773888e497b65f8
    previous_record_sha256: null
    recorded_at: '2026-07-31T05:15:50Z'
    record_sha256: faa9ef1018a0e9b2b9ba6e1fbb93446bea6228057675362932f013c5d916461b
---
# User intervention governance and independent audit contracts

This successor keeps `work-lifecycle` as the only lifecycle entry. It changes
when the lifecycle waits, not how many lifecycle systems exist.

Local candidate work remains continuously authorized through T-006 after the
isolated Plan challenge. T-007 is the only live-switch boundary and cannot
start until `C-LIVE-SWITCH` is separately accepted for the exact candidate.

The Plan-level `independent_validation` section is intentionally present in the
prepared contract before the controller implementation. The predecessor
controller must preserve it as forward-compatible metadata; the candidate
controller must make it strict, evidence-bound, and fail-closed.
