---
schema_version: 4
plan_id: PLAN-20260801-001
title: Work Governance session-safe receipt and intake stabilization
status: active
mode: autonomous
revision: 1
created_at: '2026-08-01T06:21:37Z'
updated_at: '2026-08-01T06:21:37Z'
goal:
  statement: Fix the confirmed non-tmux execution-flow defects in an isolated Git
    worktree, produce and genuinely exercise an immutable Work Governance 1.0.6
    Plugin candidate without affecting any running session, and stop at an exact-build
    confirmation gate before live Plugin installation.
  success_conditions:
  - SessionStart and UserPromptSubmit receipts are isolated by project and session,
    concurrent sessions cannot overwrite each other's trusted state, and same-session
    compaction preserves a still-current turn receipt under an explicit contract.
  - One user request can transition from explore or ask to proceed when its decision
    basis materially changes, while replay, rationale-only mutation, and stale-basis
    attempts remain fail-closed and auditable.
  - Active Plan intake stays bounded to a current chain anchor while immutable history
    remains reviewable and existing schema-v4 Plans continue to validate or migrate
    through an explicit compatibility path.
  - Controller locking has a bounded timeout and actionable holder diagnostics without
    weakening serialization or corrupting state.
  - The exact 1.0.6 candidate passes focused regressions, the full repository boundary,
    Plugin and Skill validators, static checks, privacy checks, and isolated real-use
    SessionStart/UserPromptSubmit probes.
  - The installed 1.0.5 Plugin, Codex configuration, irp_stocklens files, tmux state,
    and other sessions remain unchanged until C-LIVE-SWITCH is accepted.
  - At handoff, one immutable candidate commit and evidence basis make supported live
    installation the only required next action; live installation itself has not run.
contract:
  revision: 1
  confirmation_id: C-FIX-1-0-6
  confirmed_ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbbf6-f72a-7560-9b59-e4d4dd4cf813/sha256/1fafb502bc4cc0c315d8ddcaceb5846913fb5f961da3dc1f966de9a43145ac06
scope:
  include:
  - Create an isolated branch and linked worktree from the exact accepted repository
    baseline, preserving the main worktree and all unrelated user changes.
  - Add regression coverage and implement project/session-scoped bootstrap and turn
    receipt identity with safe same-session compaction continuity and legacy read
    compatibility.
  - Add auditable same-request intake supersession for material basis transitions and
    bounded active-Plan intake representation backed by immutable local history.
  - Add bounded controller lock acquisition with holder and timeout diagnostics.
  - Update directly affected lifecycle contracts, package and Plugin versions to the
    1.0.6 milestone, and use the supported cachebuster flow exactly once.
  - Validate and locally commit the immutable candidate, then exercise its hooks and
    controller only in isolated temporary projects and isolated runtime state.
  exclude:
  - description: Modify or add the proposed tmux output-capture helper or any tmux
      behavior.
    disposition: not_required
    resolution_ref: user:ignore-tmux-P1
  - description: Read from, write to, start commands in, or otherwise alter any tmux
      session or pane.
    disposition: forbidden
    resolution_ref: user:other-required-sessions-running
  - description: Modify files, Plan authority, receipts, runtime state, or processes
      under /Users/ld/Workspaces/HeXun/irp_stocklens.
    disposition: forbidden
    resolution_ref: user:no-impact-to-other-sessions
  - description: Install, reinstall, enable, disable, or switch the live Work Governance
      Plugin, marketplace registration, Codex configuration, or current shared Plugin
      cache before C-LIVE-SWITCH.
    disposition: pending_confirmation
    confirmation_id: C-LIVE-SWITCH
  - description: Use the live source repository as the runtime target of an extra Codex
      session or black-box probe that could overwrite shared receipt state.
    disposition: forbidden
    resolution_ref: user:no-impact-to-other-sessions
  - description: Push, publish Git refs, create a remote tag or release, open a pull
      request, or otherwise mutate Git remote state.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-push-boundary
  - description: Delete, move, prune, clean, reset, or overwrite existing branches,
      worktrees, user changes, runtime evidence, or unrelated governance state.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-change-protection
  - description: Rotate previously exposed external credentials or mutate external
      systems as part of this source-code route.
    disposition: forbidden
    resolution_ref: project:external-credential-rotation-outside-source-route
confirmations:
  required:
  - id: C-FIX-1-0-6
    description: Approve all confirmed non-tmux repairs, isolated implementation and
      validation, bounded local commits, and preparation of an exact 1.0.6 candidate
      without live installation or impact to other sessions.
    status: accepted
    ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbbf6-f72a-7560-9b59-e4d4dd4cf813/sha256/1fafb502bc4cc0c315d8ddcaceb5846913fb5f961da3dc1f966de9a43145ac06
    accepted_at: '2026-08-01T06:21:37Z'
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
      basis_ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbbf6-f72a-7560-9b59-e4d4dd4cf813/sha256/1fafb502bc4cc0c315d8ddcaceb5846913fb5f961da3dc1f966de9a43145ac06
      basis_sha256: 1fafb502bc4cc0c315d8ddcaceb5846913fb5f961da3dc1f966de9a43145ac06
  - id: C-LIVE-SWITCH
    description: Authorize supported installation and activation of the exact immutable
      1.0.6+codex.<UTC> candidate after its commit, validation, isolated real-use
      evidence, and unchanged-live-state evidence are fixed.
    status: pending
    intervention:
      kind: external_authority
      blocks:
      - task:T-008
      - activation
      - route
      basis_ref: evidence:pending-1.0.6-live-switch-basis
unknowns: []
obligations:
- id: O-001
  description: Trusted receipt identity is project- and session-scoped, concurrent
    sessions remain independent, and compaction continuity is explicit and safe.
  status: pending
- id: O-002
  description: Same-request intake can make one material, auditable decision transition
    without permitting rationale-only mutation, replay, or stale-basis bypass.
  status: pending
- id: O-003
  description: Active Plan intake remains bounded while immutable decision history and
    backward compatibility are preserved.
  status: pending
- id: O-004
  description: Controller locks time out deterministically with actionable holder
    diagnostics and preserve exclusive mutation semantics.
  status: pending
- id: O-005
  description: The exact 1.0.6 candidate is locally committed and passes the complete
    validation and isolated real-use boundary.
  status: pending
- id: O-006
  description: Current live Plugin, configuration, target project, tmux, and other
    session state remain unchanged through the pre-install handoff.
  status: pending
tasks:
- id: T-001
  description: Record exact repository, live Plugin, configuration, receipt, worktree,
    and target-project baselines; activate a dedicated branch and linked worktree from
    the governance-rollover commit without touching live runtime state.
  status: pending
  unknowns: []
  expected_evidence_delta: The isolated execution boundary is fixed and every protected
    live surface has a before-state fingerprint suitable for after comparison.
- id: T-002
  description: Add failing concurrency and compaction regression tests, then implement
    scoped receipt storage, trusted lookup, compatibility reads, and safe same-session
    turn continuity across SessionStart.
  status: pending
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: Focused tests prove two sessions cannot supersede each
    other and a same-session compaction does not invalidate the active user turn.
- id: T-003
  description: Add failing intake-transition and history-growth tests, then implement
    basis-bound same-request supersession and a bounded current intake anchor backed
    by immutable local decision records with compatibility handling.
  status: pending
  depends_on:
  - T-002
  unknowns: []
  expected_evidence_delta: Explore or ask can transition to proceed only on a material
    basis change, invalid variants fail closed, and Plan growth is bounded.
- id: T-004
  description: Add contention and stale-holder regression tests, then implement a
    bounded controller lock timeout with holder metadata and actionable diagnostics.
  status: pending
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: A held lock fails within the declared bound with holder
    evidence, while normal and recovered exclusive mutation still pass.
- id: T-005
  description: Update directly affected lifecycle documentation and run focused,
    compatibility, full-suite, Ruff, mypy, Plugin, Skill, privacy, and diff validations.
  status: pending
  depends_on:
  - T-003
  - T-004
  unknowns: []
  expected_evidence_delta: Behavior and documentation agree and the complete supported
    repository boundary passes without generated or unrelated pollution.
- id: T-006
  description: Set package and Plugin metadata to the 1.0.6 milestone, run the supported
    cachebuster helper exactly once, re-run release-boundary validation, and create one
    bounded local candidate commit on the isolated branch.
  status: pending
  depends_on:
  - T-005
  unknowns: []
  expected_evidence_delta: An immutable commit identifies one exact 1.0.6+codex.<UTC>
    candidate whose version authorities and lockfile agree.
- id: T-007
  description: Copy only the immutable candidate into isolated temporary Plugin and
    project roots, exercise SessionStart, UserPromptSubmit, intake, concurrent-session,
    compaction, and lock-contention flows, challenge the evidence, compare protected
    live baselines, and prepare the exact live-switch basis.
  status: pending
  depends_on:
  - T-006
  unknowns: []
  expected_evidence_delta: Isolated black-box evidence proves the candidate can really
    be used and protected live state is unchanged, leaving only C-LIVE-SWITCH.
- id: T-008
  description: After C-LIVE-SWITCH acceptance, use the supported local marketplace
    update flow to install and activate the exact candidate, then verify direct use in
    current sessions and fresh or reopened sessions before terminal closeout.
  status: pending
  depends_on:
  - T-007
  unknowns: []
  expected_evidence_delta: Live registration, cache, hook, controller, current-session,
    and fresh-session identities all bind the exact accepted build.
  completion_scope: route
  requires_confirmation: C-LIVE-SWITCH
validations:
- id: V-001
  description: Prove project/session receipt isolation, cross-session non-interference,
    legacy compatibility, and same-session compaction continuity.
  status: pending
  provenance:
    kind: observed-failure
    source_ref: runtime:2026-08-01-compaction-receipt-overwrite
- id: V-002
  description: Prove material same-request transition succeeds and replay,
    rationale-only mutation, unresolved blocker, and stale basis fail closed.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:confirmed-non-tmux-fixes
- id: V-003
  description: Prove bounded active Plan intake, immutable chain auditability, and
    compatibility for existing schema-v4 authorities.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:plan-intake-contract
- id: V-004
  description: Prove normal lock exclusivity, bounded contention timeout, holder
    diagnostics, and recovery behavior.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:confirmed-lock-fix
- id: V-005
  description: Run uv lock check, full pytest, Ruff format/check, strict mypy, Plugin
    validation, affected Skill validation, privacy scan, and Git boundary checks on
    the exact candidate.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:repository-validation-toolchain
- id: V-006
  description: In isolated roots, run the candidate's actual hooks and controller
    through concurrent-session, compaction, intake transition, and lock-contention
    scenarios without loading it into the live Codex cache.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:isolated-plugin-real-use-probe
- id: V-007
  description: Compare exact before/after fingerprints for live Plugin registration,
    configuration, installed cache, source main worktree, target project, tmux
    non-use, and protected session receipts.
  status: pending
  provenance:
    kind: code-invariant
    source_ref: user:no-impact-to-other-sessions
artifacts:
- id: A-001
  path: plugins/work-governance/hooks/session_start.py
  status: pending
- id: A-002
  path: plugins/work-governance/hooks/user_prompt_submit.py
  status: pending
- id: A-003
  path: plugins/work-governance/scripts/workctl.py
  status: pending
- id: A-004
  path: tests/test_bootstrap.py
  status: pending
- id: A-005
  path: tests/test_turn_intake.py
  status: pending
- id: A-006
  path: tests/test_workctl.py
  status: pending
- id: A-007
  path: plugins/work-governance/skills/work-lifecycle/SKILL.md
  status: pending
- id: A-008
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: pending
- id: A-009
  path: pyproject.toml
  status: pending
- id: A-010
  path: uv.lock
  status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260801-001
  sources: []
  confirmations: {}
delivery:
  status: pending
  boundary: immutable local 1.0.6 candidate commit and canonical pre-install evidence;
    no live Plugin installation and no Git remote publication
  evidence_ref: project:not-yet-delivered
activation:
  status: pending_confirmation
  current_ref: plugin:work-governance@1.0.5+codex.20260731091820
  target_ref: plugin:work-governance@1.0.6+codex.pending
  confirmation_id: C-LIVE-SWITCH
route:
  route_status: active
  slice_status: admission-pending
  next_phase: Activate the successor, establish isolation baselines, and execute T-001.
  validation_standard: Every non-tmux defect has focused and black-box evidence, the
    complete candidate boundary passes, and protected live state remains unchanged.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Complete T-001 through T-007 autonomously, then stop at the exact-build
    C-LIVE-SWITCH gate before any live Plugin installation.
revision_history:
- revision: 1
  kind: admission
  changed_at: '2026-08-01T06:21:37Z'
  rationale: Admit the user-confirmed non-tmux repair route with strict session
    non-interference and a separate exact-build live-install confirmation gate.
  confirmation_id: C-FIX-1-0-6
---
# Work Governance session-safe receipt and intake stabilization

This successor performs all confirmed repairs except the tmux helper. Implementation,
release preparation, and real-use probes stay inside a dedicated Git worktree and
isolated temporary runtime roots. The currently installed Plugin and all other active
sessions remain on 1.0.5 until the exact candidate is presented at `C-LIVE-SWITCH`.

The route intentionally remains non-terminal after the candidate is validated: live
installation and fresh or reopened live-session verification belong to T-008 and
cannot start without the user's next confirmation.
