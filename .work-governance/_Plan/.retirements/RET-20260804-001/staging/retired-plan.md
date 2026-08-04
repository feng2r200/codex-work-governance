---
schema_version: 4
plan_id: PLAN-20260801-002
title: Work Governance flow alignment, reviewer availability, and atomic closeout
status: retired
mode: autonomous
revision: 22
created_at: '2026-08-01T08:46:41Z'
updated_at: '2026-08-04T08:20:24+00:00'
goal:
  statement: Remove the confirmed work-flow friction around inserted user requirements,
    reviewer unavailability, controller-caused intake drift, and live-gate closeout;
    produce and genuinely exercise an immutable 1.0.7 candidate that can resume the
    existing irp_stocklens session without disturbing it or any other running session,
    then stop at an exact-build live-install gate.
  success_conditions:
  - 'A new request is classified by goal alignment: unrelated bounded work runs as
    a resumable NO_PLAN interruption, aligned non-material work reprioritizes the
    current route, and aligned material work adapts the Plan without mechanical churn
    or loss of the prior resume anchor.'
  - A pending or unavailable plan-challenge reviewer does not block ordinary reversible
    local tasks; concrete open blocker or high findings and all delivery, activation,
    route, and high-impact decisions remain fail-closed.
  - Reviewer acquisition is bounded to one initial attempt and one materially changed
    retry, after which VALIDATOR_UNAVAILABLE is explicit and a deterministic self-challenge
    may support only eligible local work.
  - The same trusted proceed request may refresh its intake after a controller-caused
    decision-basis change while target, request, rationale, stale-turn, and replay
    conflicts remain fail-closed and auditable.
  - Successful activation resolves only explicitly bound live exclusions, with exact
    single-match compatibility for legacy Plans; accepting a live gate alone never
    claims the external action or exclusion complete.
  - One atomic terminal-closeout operation can finalize route and handoff and complete
    a ready Plan without demanding a synthetic extra user turn.
  - Focused, full-suite, static, Plugin, Skill, privacy, target-shaped, and isolated
    old-session resume probes pass on one immutable 1.0.7 candidate.
  - irp_stocklens files and runtime state, tmux, existing worktrees, other sessions,
    live Plugin registration, and shared cache remain unchanged until the exact C-LIVE-1-0-7
    gate is accepted.
contract:
  revision: 1
  confirmation_id: C-FLOW-1-0-7
  confirmed_ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc79-97ac-7ac0-a764-d389ff72fe8b/sha256/50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
scope:
  include:
  - Document and enforce alignment-aware NO_PLAN interruption, automatic resumption,
    in-Plan reprioritization, and material Plan adaptation rules.
  - Repair independent-review enforcement so unavailable confidence language cannot
    stall eligible local execution while genuine findings and high-impact boundaries
    remain blocking.
  - Add same-request proceed intake refresh for controller-caused basis drift, preserving
    immutable history and conflict protections.
  - Bind activation to exact exclusion reconciliation and add an atomic terminal closeout
    path that does not need an artificial follow-up turn.
  - Add target-shaped compatibility coverage for the existing irp_stocklens Plan and
    isolated hook coverage for reopening a session created on an older build.
  - Implement and validate in a dedicated linked worktree, update release authorities
    to 1.0.7, create one immutable local commit, and prepare exact live-install evidence.
  exclude:
  - description: Read from, write to, start commands in, capture output from, or otherwise
      alter any tmux session or pane.
    disposition: forbidden
    resolution_ref: user:ignore-tmux-P1
  - description: Modify files, Plan authority, receipts, runtime state, or processes
      under /Users/ld/Workspaces/HeXun/irp_stocklens during implementation and pre-install
      validation.
    disposition: forbidden
    resolution_ref: user:no-impact-to-other-sessions
  - description: Install, reinstall, enable, disable, or switch the live Work Governance
      Plugin, marketplace registration, Codex configuration, or shared Plugin cache
      before C-LIVE-1-0-7 is accepted for the exact immutable candidate.
    disposition: pending_confirmation
    confirmation_id: C-LIVE-1-0-7
  - description: Use the source repository or target project as the runtime root of
      an additional Codex session before the isolated candidate boundary is fixed.
    disposition: forbidden
    resolution_ref: user:no-impact-to-other-sessions
  - description: Push, publish Git refs, create a remote tag or release, open a pull
      request, or mutate any Git remote state.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-push-boundary
  - description: Delete, move, prune, clean, reset, overwrite, or submit existing
      branches, worktrees, user changes, runtime evidence, or unrelated governance
      state.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-change-protection
confirmations:
  required:
  - id: C-FLOW-1-0-7
    description: Approve the 1.0.7 flow-repair contract, isolated implementation,
      bounded local commits, validation, and exact pre-install preparation without
      live Plugin mutation.
    status: accepted
    ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc79-97ac-7ac0-a764-d389ff72fe8b/sha256/50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
    accepted_at: '2026-08-01T08:46:41Z'
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
      basis_ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc79-97ac-7ac0-a764-d389ff72fe8b/sha256/50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
      basis_sha256: 50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
  - id: C-LIVE-1-0-7
    description: Authorize supported installation and activation only after the exact
      immutable 1.0.7+codex.<UTC> candidate and its complete validation evidence replace
      this preliminary basis.
    status: pending
    intervention:
      kind: external_authority
      blocks:
      - task:T-008
      - activation
      - route
      basis_ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc79-97ac-7ac0-a764-d389ff72fe8b/sha256/50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
      basis_sha256: 50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
  - id: C-LIVE-SWITCH-1-0-7
    description: Supersede the preliminary C-LIVE-1-0-7 basis and authorize supported
      live installation only for immutable build 1.0.7+codex.20260801093722 at source
      commit b91efbd581a582bdf2ed25fc8e463786819e135e with exact evidence 581c5c730f30dc38b4eb5358844873f73909c83cf935112fdec936fdd23871b3.
    status: accepted
    intervention:
      kind: external_authority
      blocks:
      - task:T-008
      - activation
      - route
      basis_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-002/581c5c730f30dc38b4eb5358844873f73909c83cf935112fdec936fdd23871b3.json
      basis_sha256: 581c5c730f30dc38b4eb5358844873f73909c83cf935112fdec936fdd23871b3
    ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbd4f-bc6f-7680-9191-282b8c68c206/sha256/f8176737a3dc579422c88de39554ecee014e4af5fdd867fa0f111c029a77d720
    accepted_at: '2026-08-01T12:35:16+00:00'
    evidence_sha256: 581c5c730f30dc38b4eb5358844873f73909c83cf935112fdec936fdd23871b3
  - id: C-GOAL-DRIVEN-LIGHT-2026
    description: Authorize replacing the stale active flow-repair route with the user-requested
      goal-driven light-governance implementation, preserving all no-go boundaries
      and deferring live activation.
    status: accepted
    intervention:
      kind: plan_contract
      blocks:
      - route
      basis_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
      basis_sha256: dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    accepted_at: '2026-08-04T08:16:02+00:00'
    evidence_sha256: dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
  - id: C-PLAN-RETIREMENT
    description: Approve retirement of the exact obsolete Plan without claiming completion.
    status: accepted
    ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    accepted_at: '2026-08-04T08:20:08Z'
    evidence_sha256: ae3e8b956bee54d7479d60e300b02d7f1f8405f730cd2a13d875d810a6001f3e
    intervention:
      kind: external_authority
      blocks:
      - route
      basis_ref: project:confirmation-basis/ae3e8b956bee54d7479d60e300b02d7f1f8405f730cd2a13d875d810a6001f3e
      basis_sha256: ae3e8b956bee54d7479d60e300b02d7f1f8405f730cd2a13d875d810a6001f3e
unknowns: []
obligations:
- id: O-001
  description: Inserted requests are routed by goal alignment and resume semantics
    instead of being rejected or forcing unrelated Plan churn.
  status: pending
- id: O-002
  description: Reviewer unavailability is bounded and explicit; eligible local work
    can progress while real high-impact review blockers remain enforced.
  status: pending
- id: O-003
  description: Controller-caused basis changes and completed live actions reconcile
    without synthetic user turns, false completion, or weakened authority binding.
  status: pending
- id: O-004
  description: Existing schema-v4 Plans, old session receipts, and the irp_stocklens
    target shape remain compatible with the repaired controller and hooks.
  status: pending
- id: O-005
  description: One immutable 1.0.7 candidate passes the complete repository and isolated
    real-use boundary without mutating protected live surfaces.
  status: pending
tasks:
- id: T-001
  description: Fix repository, worktree, live Plugin, session, and irp_stocklens read-only
    baselines; create the dedicated implementation branch and linked worktree.
  status: verified
  unknowns: []
  expected_evidence_delta: The implementation boundary and protected before-state
    hashes are fixed and independently reproducible.
  note: Dedicated branch/worktree and protected baselines fixed by evidence 6c2a8cfe.
- id: T-002
  description: Add lifecycle routing rules and tests for unrelated NO_PLAN interruption,
    automatic resume, aligned reprioritization, and material Plan adaptation.
  status: verified
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: Contract examples distinguish the three routes and prevent
    plan mechanics from becoming the goal.
  note: Alignment routing and automatic resume contract verified by focused documentation
    tests (evidence 070936dc).
- id: T-003
  description: Add failing reviewer regressions and implement advisory pending plan-challenge
    semantics plus bounded VALIDATOR_UNAVAILABLE handling without releasing high-impact
    targets or concrete blocker and high findings.
  status: verified
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: A target-shaped Plan can start ordinary local work, while
    delivery, activation, route, gated tasks, and concrete high findings remain blocked.
  note: Advisory pending plan challenge, protected-target, high-finding, and irp_stocklens-shaped
    regressions pass (evidence aebf0d1d).
- id: T-004
  description: Add failing same-turn intake, activation-exclusion, and terminal-closeout
    regressions; implement basis-safe proceed refresh, exact exclusion binding, legacy
    single-match compatibility, and atomic closeout.
  status: verified
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: The previously observed extra-turn defects reproduce before
    the repair and close atomically after it without permitting replay or ambiguous
    matching.
  note: Controller-bound proceed refresh, activation exclusion reconciliation, ambiguity
    guard, and strict atomic closeout regressions pass (evidence 845b99e6).
- id: T-005
  description: Update lifecycle, reviewer, controller, and migration documentation
    and add target-shaped irp_stocklens Plan compatibility tests.
  status: verified
  depends_on:
  - T-002
  - T-003
  - T-004
  unknowns: []
  expected_evidence_delta: Documentation and executable contracts agree, and the existing
    target Plan shape no longer stalls ordinary progress.
  note: Lifecycle, reviewer, basis refresh, exact-gate rebind, exclusion, and atomic-closeout
    contracts align; target Plan schema and focused compatibility regressions pass
    (evidence 0458137a).
- id: T-006
  description: Run focused and full pytest, Ruff formatting and lint, strict mypy,
    Plugin and Skill validation, privacy checks, compatibility checks, and a deterministic
    self-challenge because role-isolated validation is unavailable.
  status: verified
  depends_on:
  - T-005
  unknowns: []
  expected_evidence_delta: All supported validation boundaries pass and the degraded
    independence limit is explicit rather than mislabeled as low confidence.
  note: Full suite 384 passed/1 skipped; Ruff, strict mypy, Plugin/Skill validators,
    privacy and lock checks pass. Independent role unavailable; deterministic self-challenge
    is explicitly degraded (evidence bf14034a).
- id: T-007
  description: Set all release authorities to 1.0.7, run the supported cachebuster
    exactly once, commit one immutable candidate, exercise isolated SessionStart and
    UserPromptSubmit resumption from an older receipt, compare protected baselines,
    and replace C-LIVE-1-0-7 with exact evidence.
  status: verified
  depends_on:
  - T-006
  unknowns: []
  expected_evidence_delta: One immutable exact build is genuinely usable, the target-shaped
    session can reopen, and no protected live surface has changed.
  note: Immutable 1.0.7+codex.20260801093722 candidate b91efbd passed 385 tests, static/plugin/lock
    checks, isolated old-session resume, protected baseline comparison, and exact
    switch evidence 581c5c73.
- id: T-008
  description: After exact C-LIVE-1-0-7 acceptance, use the supported Plugin update
    flow to install and activate only the accepted build, verify current and fresh
    or reopened sessions, then perform atomic terminal closeout.
  status: pending
  depends_on:
  - T-007
  completion_scope: route
  requires_confirmation: C-LIVE-1-0-7
  unknowns: []
  expected_evidence_delta: Live registration, cache identity, hooks, controller, current
    session, and reopened irp_stocklens use all bind the accepted exact build.
validations:
- id: V-001
  description: Verify alignment-aware routing examples and automatic resumption preserve
    the parent goal and current execution anchor.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:C-FLOW-1-0-7
- id: V-002
  description: Verify pending or unavailable plan-challenge releases only eligible
    local tasks and never releases concrete high findings or high-impact targets.
  status: pending
  provenance:
    kind: observed-failure
    source_ref: runtime:irp-stocklens-plan-review-block
- id: V-003
  description: Verify same-request proceed refresh permits only controller-caused
    basis drift and keeps request, targets, rationale, replay, and trusted-turn guards
    closed.
  status: pending
  provenance:
    kind: observed-failure
    source_ref: runtime:plan-20260801-001-intake-conflict
- id: V-004
  description: Verify activation reconciles explicit or unambiguous legacy exclusion
    bindings only after runtime evidence, and atomic closeout needs no extra turn.
  status: pending
  provenance:
    kind: observed-failure
    source_ref: runtime:plan-20260801-001-live-exclusion
- id: V-005
  description: Verify current schema-v4 fixtures and an irp_stocklens target-shaped
    Plan remain valid and execute eligible tasks under the new controller.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:irp-stocklens-read-only-plan-shape
- id: V-006
  description: Verify full repository tests, Ruff, strict mypy, Plugin and Skill validators,
    privacy checks, lock consistency, and diff scope.
  status: pending
  provenance:
    kind: code-invariant
    source_ref: project:repository-validation-contract
- id: V-007
  description: Verify immutable 1.0.7 hooks and controller resume an older isolated
    session, preserve protected baselines, and bind exact pre-install evidence.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: runtime:isolated-old-session-resume-probe
artifacts:
- id: A-001
  path: plugins/work-governance/skills/work-lifecycle/SKILL.md
  status: pending
- id: A-002
  path: plugins/work-governance/scripts/workctl.py
  status: pending
- id: A-003
  path: tests/test_workctl.py
  status: pending
- id: A-004
  path: tests/test_turn_intake.py
  status: pending
- id: A-005
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: pending
- id: A-006
  path: pyproject.toml
  status: pending
- id: A-007
  path: uv.lock
  status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260801-002
  sources: []
  confirmations: {}
delivery:
  status: pending
  boundary: immutable local 1.0.7 candidate and canonical pre-install evidence; no
    live Plugin installation or Git remote publication
  evidence_ref: project:not-yet-delivered
activation:
  status: pending_confirmation
  current_ref: plugin:work-governance@1.0.6+codex.20260801071322
  target_ref: plugin:work-governance@1.0.7+codex.pending
  confirmation_id: C-LIVE-1-0-7
route:
  route_status: active
  slice_status: admitted
  next_phase: Execute T-001 through T-007 in the isolated worktree, then stop at C-LIVE-1-0-7
    with exact evidence.
  validation_standard: Every obligation and validation has current subject-specific
    evidence, the immutable candidate passes isolated real use, and protected live
    baselines are unchanged before live installation.
  confirmation_gate: C-LIVE-1-0-7
handoff:
  route_status: active
  next_step: Execute T-001 in the isolated worktree without touching protected live
    state.
revision_history:
- revision: 1
  kind: admission
  changed_at: '2026-08-01T08:46:41Z'
  rationale: Admit the explicitly confirmed 1.0.7 flow-repair contract after recoverably
    retiring the obsolete 1.0.6 bookkeeping surface.
  confirmation_id: C-FLOW-1-0-7
- revision: 2
  kind: controlled-transition
  changed_at: '2026-08-01T08:54:01+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 3
  kind: controlled-transition
  changed_at: '2026-08-01T08:56:31+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 4
  kind: controlled-transition
  changed_at: '2026-08-01T08:56:43+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 5
  kind: controlled-transition
  changed_at: '2026-08-01T08:56:44+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 6
  kind: controlled-transition
  changed_at: '2026-08-01T08:56:45+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 7
  kind: controlled-transition
  changed_at: '2026-08-01T09:19:16+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 8
  kind: controlled-transition
  changed_at: '2026-08-01T09:19:17+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 9
  kind: controlled-transition
  changed_at: '2026-08-01T09:19:18+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 10
  kind: controlled-transition
  changed_at: '2026-08-01T09:21:50+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 11
  kind: controlled-transition
  changed_at: '2026-08-01T09:30:10+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 12
  kind: controlled-transition
  changed_at: '2026-08-01T09:30:25+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 13
  kind: controlled-transition
  changed_at: '2026-08-01T09:36:35+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 14
  kind: controlled-transition
  changed_at: '2026-08-01T09:36:55+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 15
  kind: confirmation-added
  changed_at: '2026-08-01T12:29:55+00:00'
  rationale: Create explicit confirmation C-LIVE-SWITCH-1-0-7.
- revision: 16
  kind: intake-recorded
  changed_at: '2026-08-01T12:34:51+00:00'
  rationale: Record intake for user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbd4f-bc6f-7680-9191-282b8c68c206/sha256/f8176737a3dc579422c88de39554ecee014e4af5fdd867fa0f111c029a77d720.
- revision: 17
  kind: controlled-transition
  changed_at: '2026-08-01T12:35:04+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 18
  kind: confirmation-decided
  changed_at: '2026-08-01T12:35:16+00:00'
  rationale: Record the explicit decision for C-LIVE-SWITCH-1-0-7.
  confirmation_id: C-LIVE-SWITCH-1-0-7
- revision: 19
  kind: intake-recorded
  changed_at: '2026-08-04T08:14:57+00:00'
  rationale: Record intake for user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b.
  decision_basis_sha256: 2b924ba2c57ae2af8eac49b2b5c2f2904b6db003a263e20b282c0a1bfa56fb99
- revision: 20
  kind: confirmation-added
  changed_at: '2026-08-04T08:15:23+00:00'
  rationale: Create explicit confirmation C-GOAL-DRIVEN-LIGHT-2026.
  decision_basis_sha256: 2b924ba2c57ae2af8eac49b2b5c2f2904b6db003a263e20b282c0a1bfa56fb99
- revision: 21
  kind: confirmation-decided
  changed_at: '2026-08-04T08:16:02+00:00'
  rationale: Record the explicit decision for C-GOAL-DRIVEN-LIGHT-2026.
  confirmation_id: C-GOAL-DRIVEN-LIGHT-2026
  decision_basis_sha256: 2b924ba2c57ae2af8eac49b2b5c2f2904b6db003a263e20b282c0a1bfa56fb99
- revision: 22
  kind: retirement
  changed_at: '2026-08-04T08:20:24+00:00'
  rationale: Supersede the stale flow-repair Plan after the current user authorized
    the goal-driven light-governance implementation.
  confirmation_id: C-PLAN-RETIREMENT
  decision_basis_sha256: 2b924ba2c57ae2af8eac49b2b5c2f2904b6db003a263e20b282c0a1bfa56fb99
intake:
  protocol_version: 2
  current:
    request_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    request_sha256: dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    classification: plan_controlled
    targets:
    - route
    decision: proceed
    rationale: "\u672C\u8F6E\u7ED3\u6784\u6027\u76EE\u6807\u5DF2\u660E\u786E\uFF1A\
      \u5148\u5EFA\u7ACB\u65B0\u76EE\u6807\u5951\u7EA6\u4E0E\u9694\u79BB\u6267\u884C\
      \u8FB9\u754C\uFF0C\u65E7 Plan \u4E0D\u6267\u884C live gate"
    decision_basis_sha256: 2b924ba2c57ae2af8eac49b2b5c2f2904b6db003a263e20b282c0a1bfa56fb99
    previous_record_sha256: f4d69f9d910f8c034f157be463dc61d4e3c4899bfc345f80961da85bda3b4328
    recorded_at: '2026-08-04T08:10:11Z'
    record_sha256: 899ec6e3a75060bf4ad1caf453a23c7063a5ecff86c655e50740277acc553424
  history:
    storage: project-local-immutable
    head_sha256: 899ec6e3a75060bf4ad1caf453a23c7063a5ecff86c655e50740277acc553424
    record_count: 3
retirement:
  retirement_id: RET-20260804-001
  reason: Supersede the stale flow-repair Plan after the current user authorized the
    goal-driven light-governance implementation.
  retired_at: '2026-08-04T08:20:08Z'
  proposal_sha256: ae3e8b956bee54d7479d60e300b02d7f1f8405f730cd2a13d875d810a6001f3e
  original_path: .work-governance/_Plan/.retirements/RET-20260804-001/original.md
  original_sha256: f970b6f2012f1f019aa6020c179be0b8ec30fc889a269e05ab7a1fe0bf1718d2
  confirmation:
    id: C-PLAN-RETIREMENT
    ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    evidence_sha256: ae3e8b956bee54d7479d60e300b02d7f1f8405f730cd2a13d875d810a6001f3e
  dispositions:
    exclusions:
    - description: Install, reinstall, enable, disable, or switch the live Work Governance
        Plugin, marketplace registration, Codex configuration, or shared Plugin cache
        before C-LIVE-1-0-7 is accepted for the exact immutable candidate.
      disposition: superseded
      reason: The old live-install exclusion remains preserved in the retired Plan
        and is not acted upon
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    obligations:
    - id: O-001
      disposition: superseded
      reason: Replaced by the new goal-driven contract
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: O-002
      disposition: superseded
      reason: Replaced by the new goal-driven contract
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: O-003
      disposition: superseded
      reason: Replaced by the new goal-driven contract
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: O-004
      disposition: superseded
      reason: Replaced by the new goal-driven contract
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: O-005
      disposition: superseded
      reason: Replaced by the new goal-driven contract
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    tasks:
    - id: T-008
      disposition: superseded
      reason: The old live-install route is explicitly deferred and replaced by the
        new local implementation route
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    validations:
    - id: V-001
      disposition: superseded
      reason: Replaced by the new acceptance matrix
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: V-002
      disposition: superseded
      reason: Replaced by the new acceptance matrix
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: V-003
      disposition: superseded
      reason: Replaced by the new acceptance matrix
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: V-004
      disposition: superseded
      reason: Replaced by the new acceptance matrix
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: V-005
      disposition: superseded
      reason: Replaced by the new acceptance matrix
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: V-006
      disposition: superseded
      reason: Replaced by the new acceptance matrix
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: V-007
      disposition: superseded
      reason: Replaced by the new acceptance matrix
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    artifacts:
    - id: A-001
      disposition: superseded
      reason: New implementation will establish fresh artifact evidence
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: A-002
      disposition: superseded
      reason: New implementation will establish fresh artifact evidence
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: A-003
      disposition: superseded
      reason: New implementation will establish fresh artifact evidence
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: A-004
      disposition: superseded
      reason: New implementation will establish fresh artifact evidence
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: A-005
      disposition: superseded
      reason: New implementation will establish fresh artifact evidence
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: A-006
      disposition: superseded
      reason: New implementation will establish fresh artifact evidence
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    - id: A-007
      disposition: superseded
      reason: New implementation will establish fresh artifact evidence
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    confirmations:
    - id: C-LIVE-1-0-7
      disposition: superseded
      reason: The old live gate is not reused for this implementation
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    delivery:
      disposition: superseded
      reason: The old delivery boundary is replaced by the new phased local delivery
        boundary
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    activation:
      disposition: superseded
      reason: Live activation is not part of this implementation turn
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    route:
      disposition: superseded
      reason: The stale route is replaced by the goal-driven light-governance route
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
    handoff:
      disposition: superseded
      reason: The successor Plan will carry the new implementation handoff
      resolution_ref: user:session/019fcbd2-7d1e-7613-a612-10fc66b019ea/turn/019fcbd2-7e6a-7ed1-8cdc-5356721b1fda/sha256/dc01e20283aa73d62fdda74f579e58b3ef8a14c102aeefe20eaf55b66012759b
---
# Work Governance flow alignment, reviewer availability, and atomic closeout

This Plan treats the goal as authority and the Plan as a revisable map. It keeps
implementation and all real-use probes isolated until an exact immutable build is
presented at `C-LIVE-1-0-7`.
