---
schema_version: 4
plan_id: PLAN-20260801-001
title: Work Governance session-safe receipt and intake stabilization
status: active
mode: autonomous
revision: 48
created_at: '2026-08-01T06:21:37Z'
updated_at: '2026-08-01T08:40:50+00:00'
goal:
  statement: Fix the confirmed non-tmux execution-flow defects in an isolated Git
    worktree, produce and genuinely exercise an immutable Work Governance 1.0.6 Plugin
    candidate without affecting any running session, and stop at an exact-build confirmation
    gate before live Plugin installation.
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
  - Add auditable same-request intake supersession for material basis transitions
    and bounded active-Plan intake representation backed by immutable local history.
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
  - description: Use the live source repository as the runtime target of an extra
      Codex session or black-box probe that could overwrite shared receipt state.
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
    status: accepted
    intervention:
      kind: external_authority
      blocks:
      - task:T-008
      - activation
      - route
      basis_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/38b69e66c78b01457c47b02ae03b1e65009ad299289dff7d2069296dabcf32fe.json
      basis_sha256: 38b69e66c78b01457c47b02ae03b1e65009ad299289dff7d2069296dabcf32fe
    ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc5f-0193-71c0-9a57-90b8dd00ee6a/sha256/90ccf57c7d75704dc7ee0d7d9476974503171218f554fe41076eaf531478da45
    accepted_at: '2026-08-01T08:12:53+00:00'
    evidence_sha256: 38b69e66c78b01457c47b02ae03b1e65009ad299289dff7d2069296dabcf32fe
  - id: C-PLAN-ROLLOVER
    description: Approve the terminal predecessor and exact successor Plan contract.
    status: accepted
    ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbbf6-f72a-7560-9b59-e4d4dd4cf813/sha256/1fafb502bc4cc0c315d8ddcaceb5846913fb5f961da3dc1f966de9a43145ac06
    accepted_at: '2026-08-01T06:25:38Z'
    evidence_sha256: 79f4203a0157b1455799e9f12d2d1549c70a5b501ed423c218387cb5edf0a690
    intervention:
      kind: plan_contract
      blocks:
      - route
      basis_ref: project:confirmation-basis/79f4203a0157b1455799e9f12d2d1549c70a5b501ed423c218387cb5edf0a690
      basis_sha256: 79f4203a0157b1455799e9f12d2d1549c70a5b501ed423c218387cb5edf0a690
unknowns: []
obligations:
- id: O-001
  description: Trusted receipt identity is project- and session-scoped, concurrent
    sessions remain independent, and compaction continuity is explicit and safe.
  status: verified
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/626d9dd5c940042574db8b83c4db99befaa0982f6807734fbc0c9d3fc9026fdf.json
  evidence_sha256: 626d9dd5c940042574db8b83c4db99befaa0982f6807734fbc0c9d3fc9026fdf
  verified_at: '2026-08-01T07:35:57+00:00'
- id: O-002
  description: Same-request intake can make one material, auditable decision transition
    without permitting rationale-only mutation, replay, or stale-basis bypass.
  status: verified
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/12a32a8f4c27491ed4d1eed1551aba0fb3e886e3b94aaed21d7981dab5ed81de.json
  evidence_sha256: 12a32a8f4c27491ed4d1eed1551aba0fb3e886e3b94aaed21d7981dab5ed81de
  verified_at: '2026-08-01T07:35:58+00:00'
- id: O-003
  description: Active Plan intake remains bounded while immutable decision history
    and backward compatibility are preserved.
  status: verified
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/69a5d2b12e00c2541900c3a96ac92a8fb8dc39e408b3cea5b373cd1b1868810b.json
  evidence_sha256: 69a5d2b12e00c2541900c3a96ac92a8fb8dc39e408b3cea5b373cd1b1868810b
  verified_at: '2026-08-01T07:35:59+00:00'
- id: O-004
  description: Controller locks time out deterministically with actionable holder
    diagnostics and preserve exclusive mutation semantics.
  status: verified
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/94ec3978827fd66725585915e7ce931c1389e74e839bba40d6df5785bc049251.json
  evidence_sha256: 94ec3978827fd66725585915e7ce931c1389e74e839bba40d6df5785bc049251
  verified_at: '2026-08-01T07:36:00+00:00'
- id: O-005
  description: The exact 1.0.6 candidate is locally committed and passes the complete
    validation and isolated real-use boundary.
  status: verified
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/aaed0cd35828efaff0925c710ac7e4a97948b65817c0c760fbc9c67ca2b2906c.json
  evidence_sha256: aaed0cd35828efaff0925c710ac7e4a97948b65817c0c760fbc9c67ca2b2906c
  verified_at: '2026-08-01T07:36:01+00:00'
- id: O-006
  description: Current live Plugin, configuration, target project, tmux, and other
    session state remain unchanged through the pre-install handoff.
  status: verified
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/95d6bdca64e0fcb7e5258dcdc6b63d87002033551693fd63311640763e3ed020.json
  evidence_sha256: 95d6bdca64e0fcb7e5258dcdc6b63d87002033551693fd63311640763e3ed020
  verified_at: '2026-08-01T07:36:02+00:00'
tasks:
- id: T-001
  description: Record exact repository, live Plugin, configuration, receipt, worktree,
    and target-project baselines; activate a dedicated branch and linked worktree
    from the governance-rollover commit without touching live runtime state.
  status: verified
  unknowns: []
  expected_evidence_delta: The isolated execution boundary is fixed and every protected
    live surface has a before-state fingerprint suitable for after comparison.
  note: Isolated worktree and protected live-state baselines were fixed before implementation.
- id: T-002
  description: Add failing concurrency and compaction regression tests, then implement
    scoped receipt storage, trusted lookup, compatibility reads, and safe same-session
    turn continuity across SessionStart.
  status: verified
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: Focused tests prove two sessions cannot supersede each
    other and a same-session compaction does not invalidate the active user turn.
  note: Focused and full tests prove cross-session non-interference and compaction
    continuity.
- id: T-003
  description: Add failing intake-transition and history-growth tests, then implement
    basis-bound same-request supersession and a bounded current intake anchor backed
    by immutable local decision records with compatibility handling.
  status: verified
  depends_on:
  - T-002
  unknowns: []
  expected_evidence_delta: Explore or ask can transition to proceed only on a material
    basis change, invalid variants fail closed, and Plan growth is bounded.
  note: Transition, conflict, compatibility, and bounded-history tests pass.
- id: T-004
  description: Add contention and stale-holder regression tests, then implement a
    bounded controller lock timeout with holder metadata and actionable diagnostics.
  status: verified
  depends_on:
  - T-001
  unknowns: []
  expected_evidence_delta: A held lock fails within the declared bound with holder
    evidence, while normal and recovered exclusive mutation still pass.
  note: Contention timeout, exclusivity, diagnostics, and stale-holder tests pass.
- id: T-005
  description: Update directly affected lifecycle documentation and run focused, compatibility,
    full-suite, Ruff, mypy, Plugin, Skill, privacy, and diff validations.
  status: verified
  depends_on:
  - T-003
  - T-004
  unknowns: []
  expected_evidence_delta: Behavior and documentation agree and the complete supported
    repository boundary passes without generated or unrelated pollution.
  note: Ruff, strict mypy, 369 tests, lock check, Plugin and Skill validators, privacy
    and diff checks pass.
- id: T-006
  description: Set package and Plugin metadata to the 1.0.6 milestone, run the supported
    cachebuster helper exactly once, re-run release-boundary validation, and create
    one bounded local candidate commit on the isolated branch.
  status: verified
  depends_on:
  - T-005
  unknowns: []
  expected_evidence_delta: An immutable commit identifies one exact 1.0.6+codex.<UTC>
    candidate whose version authorities and lockfile agree.
  note: Exact candidate 1.0.6+codex.20260801071322 is commit fc63fc83c96c8918091fd271d562fe8036a8cbbd.
- id: T-007
  description: Copy only the immutable candidate into isolated temporary Plugin and
    project roots, exercise SessionStart, UserPromptSubmit, intake, concurrent-session,
    compaction, and lock-contention flows, challenge the evidence, compare protected
    live baselines, and prepare the exact live-switch basis.
  status: verified
  depends_on:
  - T-006
  unknowns: []
  expected_evidence_delta: Isolated black-box evidence proves the candidate can really
    be used and protected live state is unchanged, leaving only C-LIVE-SWITCH.
  note: Immutable candidate real-use, full validation, and protected-state comparison
    passed; live install remains pending.
- id: T-008
  description: After C-LIVE-SWITCH acceptance, use the supported local marketplace
    update flow to install and activate the exact candidate, then verify direct use
    in current sessions and fresh or reopened sessions before terminal closeout.
  status: verified
  depends_on:
  - T-007
  unknowns: []
  expected_evidence_delta: Live registration, cache, hook, controller, current-session,
    and fresh-session identities all bind the exact accepted build.
  completion_scope: route
  requires_confirmation: C-LIVE-SWITCH
  note: Exact live registration, source-cache identity, 1.0.6 SessionStart and UserPromptSubmit
    receipts, same-session continuity, current-controller usability, and protected
    irp_stocklens hashes are verified by activation evidence b4316240.
validations:
- id: V-001
  description: Prove project/session receipt isolation, cross-session non-interference,
    legacy compatibility, and same-session compaction continuity.
  status: verified
  provenance:
    kind: observed-failure
    source_ref: runtime:2026-08-01-compaction-receipt-overwrite
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ff75ceafc82ff60dd3bb9b53388431403ea24f8a736d1a7ae185d8d4530334ca.json
  evidence_sha256: ff75ceafc82ff60dd3bb9b53388431403ea24f8a736d1a7ae185d8d4530334ca
  verified_at: '2026-08-01T07:36:04+00:00'
- id: V-002
  description: Prove material same-request transition succeeds and replay, rationale-only
    mutation, unresolved blocker, and stale basis fail closed.
  status: verified
  provenance:
    kind: confirmed-obligation
    source_ref: user:confirmed-non-tmux-fixes
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/fa314ea49057060f1b310a9ca1b8a0ce912e3de3b8f79be1a8f76399b402020f.json
  evidence_sha256: fa314ea49057060f1b310a9ca1b8a0ce912e3de3b8f79be1a8f76399b402020f
  verified_at: '2026-08-01T07:36:05+00:00'
- id: V-003
  description: Prove bounded active Plan intake, immutable chain auditability, and
    compatibility for existing schema-v4 authorities.
  status: verified
  provenance:
    kind: supported-integration-boundary
    source_ref: project:plan-intake-contract
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/834fa282dd84c821cc8a4ec313d060093c5c0f1f9724b397da005368f88d097c.json
  evidence_sha256: 834fa282dd84c821cc8a4ec313d060093c5c0f1f9724b397da005368f88d097c
  verified_at: '2026-08-01T07:36:06+00:00'
- id: V-004
  description: Prove normal lock exclusivity, bounded contention timeout, holder diagnostics,
    and recovery behavior.
  status: verified
  provenance:
    kind: confirmed-obligation
    source_ref: user:confirmed-lock-fix
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/5b62c9b94c778af6da4fbe0f0235e115a82ed41df1bdd9df811297c980ae8d53.json
  evidence_sha256: 5b62c9b94c778af6da4fbe0f0235e115a82ed41df1bdd9df811297c980ae8d53
  verified_at: '2026-08-01T07:36:07+00:00'
- id: V-005
  description: Run uv lock check, full pytest, Ruff format/check, strict mypy, Plugin
    validation, affected Skill validation, privacy scan, and Git boundary checks on
    the exact candidate.
  status: verified
  provenance:
    kind: supported-integration-boundary
    source_ref: project:repository-validation-toolchain
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/fb4b1fd5ffa35178a5784c1e9a65932389a131725c69277eb9d7b5858f671251.json
  evidence_sha256: fb4b1fd5ffa35178a5784c1e9a65932389a131725c69277eb9d7b5858f671251
  verified_at: '2026-08-01T07:36:08+00:00'
- id: V-006
  description: In isolated roots, run the candidate's actual hooks and controller
    through concurrent-session, compaction, intake transition, and lock-contention
    scenarios without loading it into the live Codex cache.
  status: verified
  provenance:
    kind: supported-integration-boundary
    source_ref: project:isolated-plugin-real-use-probe
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ffd4ec99c7b86c98d1ea0bed50b88ed71383bd1260ebbd89cd72e67eb54afd02.json
  evidence_sha256: ffd4ec99c7b86c98d1ea0bed50b88ed71383bd1260ebbd89cd72e67eb54afd02
  verified_at: '2026-08-01T07:36:09+00:00'
- id: V-007
  description: Compare exact before/after fingerprints for live Plugin registration,
    configuration, installed cache, source main worktree, target project, tmux non-use,
    and protected session receipts.
  status: verified
  provenance:
    kind: code-invariant
    source_ref: user:no-impact-to-other-sessions
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/7ff066e2e5b95b71bffd615e78bddfc3437151a49731213e2b80bb9c6f8ab2c0.json
  evidence_sha256: 7ff066e2e5b95b71bffd615e78bddfc3437151a49731213e2b80bb9c6f8ab2c0
  verified_at: '2026-08-01T07:36:10+00:00'
artifacts:
- id: A-001
  path: plugins/work-governance/hooks/session_start.py
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/0871571efac37e84c09a6e2ce023eddd0b39c8296a86fbe34894856c257070fb.json
  evidence_sha256: 0871571efac37e84c09a6e2ce023eddd0b39c8296a86fbe34894856c257070fb
  finalized_at: '2026-08-01T07:36:11+00:00'
- id: A-002
  path: plugins/work-governance/hooks/user_prompt_submit.py
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/e59efc20943c24d8a87e65123869e0cad40bd2d6e6ca7ddfa9400341460cf69c.json
  evidence_sha256: e59efc20943c24d8a87e65123869e0cad40bd2d6e6ca7ddfa9400341460cf69c
  finalized_at: '2026-08-01T07:36:12+00:00'
- id: A-003
  path: plugins/work-governance/scripts/workctl.py
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ec9d3a72c30668c10c259f2d488ae47fd33f71199ea9e4711c5133598b331944.json
  evidence_sha256: ec9d3a72c30668c10c259f2d488ae47fd33f71199ea9e4711c5133598b331944
  finalized_at: '2026-08-01T07:36:14+00:00'
- id: A-004
  path: tests/test_bootstrap.py
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/dc02d805348412b73c2ca7c34afcc7ed11cb44bd8d3af21595a614ae276d5257.json
  evidence_sha256: dc02d805348412b73c2ca7c34afcc7ed11cb44bd8d3af21595a614ae276d5257
  finalized_at: '2026-08-01T07:36:15+00:00'
- id: A-005
  path: tests/test_turn_intake.py
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/07faeaf8493a7c197cd9c16fef6bd2ba42e622f4b577979b80d9f6aa0e3acde1.json
  evidence_sha256: 07faeaf8493a7c197cd9c16fef6bd2ba42e622f4b577979b80d9f6aa0e3acde1
  finalized_at: '2026-08-01T07:36:16+00:00'
- id: A-006
  path: tests/test_workctl.py
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/c5e6e4d74e9ca2177fba3f214d615b32bd41a1bac619f1834c59c9695a83836b.json
  evidence_sha256: c5e6e4d74e9ca2177fba3f214d615b32bd41a1bac619f1834c59c9695a83836b
  finalized_at: '2026-08-01T07:36:17+00:00'
- id: A-007
  path: plugins/work-governance/skills/work-lifecycle/SKILL.md
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/961cf653b600308f781c84387f86f0f663ecdd1bdfa466ff6d30b912107f634f.json
  evidence_sha256: 961cf653b600308f781c84387f86f0f663ecdd1bdfa466ff6d30b912107f634f
  finalized_at: '2026-08-01T07:36:18+00:00'
- id: A-008
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/9cd3a30a3c921d18097af20608dde1ca8e8b1fe373a31d47f8aeeb822281debf.json
  evidence_sha256: 9cd3a30a3c921d18097af20608dde1ca8e8b1fe373a31d47f8aeeb822281debf
  finalized_at: '2026-08-01T07:36:19+00:00'
- id: A-009
  path: pyproject.toml
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/c5a632f82df2879b9a801cf1560deb168324e3b319f0a4710137fe90d083faff.json
  evidence_sha256: c5a632f82df2879b9a801cf1560deb168324e3b319f0a4710137fe90d083faff
  finalized_at: '2026-08-01T07:36:20+00:00'
- id: A-010
  path: uv.lock
  status: final
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/2dcda8e0271045f185418814e8b70d0f203b3271e055beb0592c420e76c00bad.json
  evidence_sha256: 2dcda8e0271045f185418814e8b70d0f203b3271e055beb0592c420e76c00bad
  finalized_at: '2026-08-01T07:36:21+00:00'
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260801-001
  rollover_id: ROL-20260801-001
  predecessor:
    path: .work-governance/_Plan/PLAN-20260731-003.md
    plan_id: PLAN-20260731-003
    revision: 33
    sha256: 5bf36697dc076465a2c6108387f93395d14c4dc8e98cc13ebc6154a07ca535bd
  sources: []
  confirmations:
    rollover: C-PLAN-ROLLOVER
delivery:
  status: complete
  boundary: immutable local 1.0.6 candidate commit and canonical pre-install evidence;
    no live Plugin installation and no Git remote publication
  evidence_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ad066d0c55b471bcc7a8a566d24abcede910806a758a9d3eee2c023a079caf6f.json
  evidence_sha256: ad066d0c55b471bcc7a8a566d24abcede910806a758a9d3eee2c023a079caf6f
  completed_at: '2026-08-01T07:36:24+00:00'
activation:
  status: active
  current_ref: plugin:work-governance@1.0.6+codex.20260801071322
  target_ref: plugin:work-governance@1.0.6+codex.20260801071322
  confirmation_id: C-LIVE-SWITCH
  evidence:
    observed_ref: plugin:work-governance@1.0.6+codex.20260801071322
    source_ref: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/b431624030798a9dedfd10be143b174e7c99ce925dd2a06def2f1b218ea1ae10.json
    checked_at: '2026-08-01T08:14:52+00:00'
    sha256: b431624030798a9dedfd10be143b174e7c99ce925dd2a06def2f1b218ea1ae10
route:
  route_status: awaiting_confirmation
  slice_status: preinstall-ready
  next_phase: After C-LIVE-SWITCH acceptance, integrate the exact candidate onto the
    then-current compatible local main, run the supported local marketplace update,
    and verify current and fresh or reopened sessions.
  validation_standard: The installed registration, cache, hooks, runtime controller,
    current-session compatibility, and fresh-session identity all bind 1.0.6+codex.20260801071322;
    any new main or live-state conflict fails closed before installation.
  confirmation_gate: C-LIVE-SWITCH
handoff:
  route_status: awaiting_confirmation
  next_step: Await explicit acceptance of C-LIVE-SWITCH for evidence basis 38b69e66c78b01457c47b02ae03b1e65009ad299289dff7d2069296dabcf32fe;
    do not install before acceptance.
revision_history:
- revision: 1
  kind: admission
  changed_at: '2026-08-01T06:21:37Z'
  rationale: Admit the user-confirmed non-tmux repair route with strict session non-interference
    and a separate exact-build live-install confirmation gate.
  confirmation_id: C-FIX-1-0-6
- revision: 2
  kind: controlled-transition
  changed_at: '2026-08-01T06:27:22+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 3
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:02+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 4
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:03+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 5
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:04+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 6
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:05+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 7
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:06+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 8
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:07+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 9
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:08+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 10
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:09+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 11
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:10+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 12
  kind: controlled-transition
  changed_at: '2026-08-01T07:21:11+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 13
  kind: controlled-transition
  changed_at: '2026-08-01T07:23:50+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 14
  kind: controlled-transition
  changed_at: '2026-08-01T07:23:51+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 15
  kind: controlled-transition
  changed_at: '2026-08-01T07:35:57+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/626d9dd5c940042574db8b83c4db99befaa0982f6807734fbc0c9d3fc9026fdf.json
- revision: 16
  kind: controlled-transition
  changed_at: '2026-08-01T07:35:58+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/12a32a8f4c27491ed4d1eed1551aba0fb3e886e3b94aaed21d7981dab5ed81de.json
- revision: 17
  kind: controlled-transition
  changed_at: '2026-08-01T07:35:59+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/69a5d2b12e00c2541900c3a96ac92a8fb8dc39e408b3cea5b373cd1b1868810b.json
- revision: 18
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:00+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/94ec3978827fd66725585915e7ce931c1389e74e839bba40d6df5785bc049251.json
- revision: 19
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:01+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/aaed0cd35828efaff0925c710ac7e4a97948b65817c0c760fbc9c67ca2b2906c.json
- revision: 20
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:02+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/95d6bdca64e0fcb7e5258dcdc6b63d87002033551693fd63311640763e3ed020.json
- revision: 21
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:04+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ff75ceafc82ff60dd3bb9b53388431403ea24f8a736d1a7ae185d8d4530334ca.json
- revision: 22
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:05+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/fa314ea49057060f1b310a9ca1b8a0ce912e3de3b8f79be1a8f76399b402020f.json
- revision: 23
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:06+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/834fa282dd84c821cc8a4ec313d060093c5c0f1f9724b397da005368f88d097c.json
- revision: 24
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:07+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/5b62c9b94c778af6da4fbe0f0235e115a82ed41df1bdd9df811297c980ae8d53.json
- revision: 25
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:08+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/fb4b1fd5ffa35178a5784c1e9a65932389a131725c69277eb9d7b5858f671251.json
- revision: 26
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:09+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ffd4ec99c7b86c98d1ea0bed50b88ed71383bd1260ebbd89cd72e67eb54afd02.json
- revision: 27
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:10+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/7ff066e2e5b95b71bffd615e78bddfc3437151a49731213e2b80bb9c6f8ab2c0.json
- revision: 28
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:11+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/0871571efac37e84c09a6e2ce023eddd0b39c8296a86fbe34894856c257070fb.json
- revision: 29
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:12+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/e59efc20943c24d8a87e65123869e0cad40bd2d6e6ca7ddfa9400341460cf69c.json
- revision: 30
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:14+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ec9d3a72c30668c10c259f2d488ae47fd33f71199ea9e4711c5133598b331944.json
- revision: 31
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:15+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/dc02d805348412b73c2ca7c34afcc7ed11cb44bd8d3af21595a614ae276d5257.json
- revision: 32
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:16+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/07faeaf8493a7c197cd9c16fef6bd2ba42e622f4b577979b80d9f6aa0e3acde1.json
- revision: 33
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:17+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/c5e6e4d74e9ca2177fba3f214d615b32bd41a1bac619f1834c59c9695a83836b.json
- revision: 34
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:18+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/961cf653b600308f781c84387f86f0f663ecdd1bdfa466ff6d30b912107f634f.json
- revision: 35
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:19+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/9cd3a30a3c921d18097af20608dde1ca8e8b1fe373a31d47f8aeeb822281debf.json
- revision: 36
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:20+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/c5a632f82df2879b9a801cf1560deb168324e3b319f0a4710137fe90d083faff.json
- revision: 37
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:21+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/2dcda8e0271045f185418814e8b70d0f203b3271e055beb0592c420e76c00bad.json
- revision: 38
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:23+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 39
  kind: controlled-transition
  changed_at: '2026-08-01T07:36:24+00:00'
  rationale: Apply one controller-validated state transition.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/ad066d0c55b471bcc7a8a566d24abcede910806a758a9d3eee2c023a079caf6f.json
- revision: 40
  kind: confirmation-classified
  changed_at: '2026-08-01T07:37:03+00:00'
  rationale: Classify intervention contract for C-LIVE-SWITCH.
- revision: 41
  kind: adaptation
  changed_at: '2026-08-01T07:38:10+00:00'
  rationale: All pre-install work is complete; expose only the exact external live-switch
    gate while preserving concurrent external state.
  confirmation_id: C-FIX-1-0-6
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/80f16ba2cc7aecd3acd0442c41b2bb985d406b946da76e9b51b2045bb19dea2d.json
- revision: 42
  kind: intake-recorded
  changed_at: '2026-08-01T08:12:39+00:00'
  rationale: Record intake for user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc5f-0193-71c0-9a57-90b8dd00ee6a/sha256/90ccf57c7d75704dc7ee0d7d9476974503171218f554fe41076eaf531478da45.
- revision: 43
  kind: confirmation-decided
  changed_at: '2026-08-01T08:12:53+00:00'
  rationale: Record the explicit decision for C-LIVE-SWITCH.
  confirmation_id: C-LIVE-SWITCH
- revision: 44
  kind: controlled-transition
  changed_at: '2026-08-01T08:13:03+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 45
  kind: controlled-transition
  changed_at: '2026-08-01T08:13:15+00:00'
  rationale: Promote activation to in_progress.
  confirmation_id: C-LIVE-SWITCH
- revision: 46
  kind: controlled-transition
  changed_at: '2026-08-01T08:14:52+00:00'
  rationale: Promote activation to active.
  confirmation_id: C-LIVE-SWITCH
  evidence_manifest: evidence:.work-governance/_Plan/.evidence/PLAN-20260801-001/b431624030798a9dedfd10be143b174e7c99ce925dd2a06def2f1b218ea1ae10.json
- revision: 47
  kind: controlled-transition
  changed_at: '2026-08-01T08:15:03+00:00'
  rationale: Apply one controller-validated state transition.
- revision: 48
  kind: intake-recorded
  changed_at: '2026-08-01T08:40:50+00:00'
  rationale: Record intake for user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc79-97ac-7ac0-a764-d389ff72fe8b/sha256/50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718.
intake:
  protocol_version: 2
  current:
    request_ref: user:session/019fbbe3-53ee-75c0-8a5f-db76f0c68349/turn/019fbc79-97ac-7ac0-a764-d389ff72fe8b/sha256/50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
    request_sha256: 50b21f7b0afde50475c687dc8b6bb2135a8430a268246aaef32340cc1b2a8718
    classification: plan_controlled
    targets:
    - route
    decision: proceed
    rationale: C-FLOW-1-0-7 authorizes truthful predecessor closeout, exact successor
      rollover, isolated implementation, validation, and preinstall preparation.
    decision_basis_sha256: 2e175df68eb0e6b69a598f94d125810bb16dd4fa7833821758565169fb55bbb0
    previous_record_sha256: 48bac2168397fbbe4fec3652745aee88c41688a7a701e5b0ac6a41ac68707cd3
    recorded_at: '2026-08-01T08:38:33Z'
    record_sha256: c8f18f2f46aa2f258da033813dc502b0c2ceb069e67a36713f9755edf1ee15ac
  history:
    storage: project-local-immutable
    head_sha256: c8f18f2f46aa2f258da033813dc502b0c2ceb069e67a36713f9755edf1ee15ac
    record_count: 3
---
# Work Governance session-safe receipt and intake stabilization

This successor performs all confirmed repairs except the tmux helper. Implementation,
release preparation, and real-use probes stay inside a dedicated Git worktree and
isolated temporary runtime roots. The currently installed Plugin and all other active
sessions remain on 1.0.5 until the exact candidate is presented at `C-LIVE-SWITCH`.

The route intentionally remains non-terminal after the candidate is validated: live
installation and fresh or reopened live-session verification belong to T-008 and
cannot start without the user's next confirmation.
