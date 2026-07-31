---
schema_version: 4
plan_id: PLAN-20260731-001
title: Local main integration and work-governance Plugin activation
status: active
mode: autonomous
revision: 1
created_at: '2026-07-31T02:37:45Z'
updated_at: '2026-07-31T02:37:45Z'
goal:
  statement: Integrate the exact validated commit 2ef97091ea819ed53aa6a072e68a16e6f2bc4ab2
    into local main, validate the merged result, update and commit the Plugin cachebuster
    through the supported helper, reinstall from work-governance-local, and verify
    exact fresh-session activation without Push or remote publication.
  success_conditions:
  - Local main contains a normal merge commit whose second parent is the exact validated
    feature commit 2ef97091ea819ed53aa6a072e68a16e6f2bc4ab2, while unrelated governance
    and worktree state is preserved.
  - The merged main bytes and behavior pass focused transaction tests, the full repository
    suite, static checks, Plugin validation, and affected skill validation.
  - The supported cachebuster helper preserves base version 1.0.4 and produces exactly
    one +codex.<UTC token> suffix; only intended version metadata is committed locally.
  - Reinstallation uses the verified work-governance-local marketplace and exact local
    source; enabled registration, cache bytes, and runtime bundle identity agree.
  - A fresh SessionStart and fresh UserPromptSubmit attest the exact target build
    with READY, LAYOUT_READY, PLAN authority, work-lifecycle availability, and a current-turn
    receipt; independent validation reports no blocker-level finding and no Push occurs.
contract:
  revision: 1
  confirmation_id: C-LIVE-SWITCH
  confirmed_ref: user:session/019fb21f-0f66-7d92-959b-2921547dff49/turn/019fb5c9-6b33-7fa0-bc78-ff10461ef673/sha256/a33b10c2ba21f5dfd1b36da41c51cdd4b4d4e7216c866afc06268609c037be13
scope:
  include:
  - Recheck the exact local main and feature-commit baselines, then integrate commit
    2ef97091ea819ed53aa6a072e68a16e6f2bc4ab2 through one normal non-fast-forward local
    merge commit.
  - Preserve all unrelated governance evidence, ignored runtime state, retained worktrees,
    branches, and user changes while staging and committing only the intended boundaries.
  - Validate the merged main with exact parent and path checks, focused transaction
    coverage, the full repository suite, static checks, Plugin validation, and affected
    skill validation.
  - Run the supported Plugin cachebuster helper with its default UTC suffix, verify
    the single-suffix base-version invariant, and create a bounded local metadata
    commit.
  - Resolve the current marketplace name with the supported helper, reinstall work-governance
    from work-governance-local, and verify source, cache, enabled registration, and
    runtime identities.
  - Verify the exact target build in a fresh session through SessionStart, UserPromptSubmit,
    work-lifecycle availability, bootstrap receipt, and independent evidence review.
  exclude:
  - description: Push, publish, create or update a remote branch, open a pull request,
      or otherwise mutate remote state.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-push-boundary
  - description: Modify production systems, external projects, user data, or business
      runtime state.
    disposition: forbidden
    resolution_ref: user:session/019fb21f-0f66-7d92-959b-2921547dff49/turn/019fb5c9-6b33-7fa0-bc78-ff10461ef673/sha256/a33b10c2ba21f5dfd1b36da41c51cdd4b4d4e7216c866afc06268609c037be13
  - description: Hand-edit marketplace registration or Codex configuration, or add
      a second marketplace entry.
    disposition: forbidden
    resolution_ref: project:plugin-creator-supported-update-flow
  - description: Delete worktrees or branches, clean unrelated files, reset user changes,
      or overwrite unrelated governance evidence.
    disposition: forbidden
    resolution_ref: project:root-AGENTS-change-protection
  - description: Change base version 1.0.4 or append more than one cachebuster suffix.
    disposition: forbidden
    resolution_ref: project:plugin-creator-cachebuster-policy
confirmations:
  required:
  - id: C-LIVE-SWITCH
    description: Authorize local main integration of commit 2ef97091ea819ed53aa6a072e68a16e6f2bc4ab2,
      exact cachebuster reinstall from work-governance-local, and fresh-session activation
      verification, without Push or remote publication.
    status: accepted
    ref: user:session/019fb21f-0f66-7d92-959b-2921547dff49/turn/019fb5c9-6b33-7fa0-bc78-ff10461ef673/sha256/a33b10c2ba21f5dfd1b36da41c51cdd4b4d4e7216c866afc06268609c037be13
    accepted_at: '2026-07-31T01:34:26+00:00'
  - id: C-PLAN-ROLLOVER
    description: Approve the terminal predecessor and exact successor Plan contract.
    status: accepted
    ref: user:session/019fb21f-0f66-7d92-959b-2921547dff49/turn/019fb617-e621-7561-970f-831ed9a4cf9d/sha256/ade4f6e5d23efebe7f28664fcdd185d626a960bc7a30155b7b2b02e1b2957fa9
    accepted_at: '2026-07-31T02:54:07Z'
    evidence_sha256: 3791ff016f802d2438612adecab84e804e8f35d30f7a1e00d31906ffd406a560
unknowns: []
obligations:
- id: O-001
  description: The exact validated feature commit is integrated into local main by
    a reviewable merge commit without absorbing or overwriting unrelated state.
  status: pending
- id: O-002
  description: The merged main retains the validated feature bytes and behavior and
    passes the complete repository validation boundary.
  status: pending
- id: O-003
  description: The supported helper creates one cachebuster on base version 1.0.4,
    and the intended metadata change is committed locally.
  status: pending
- id: O-004
  description: The Plugin is reinstalled from the verified work-governance-local marketplace
    with exact source, cache, enabled-registration, and runtime identity.
  status: pending
- id: O-005
  description: Fresh SessionStart and UserPromptSubmit evidence attests the exact
    target build and mandatory work-lifecycle capability.
  status: pending
- id: O-006
  description: Independent review confirms the integration and activation evidence,
    while Push, remote mutation, destructive cleanup, and unrelated changes remain
    absent.
  status: pending
tasks:
- id: T-001
  description: Recheck local main, feature commit, merge base, working-tree protection,
    and remote boundary; create one normal local merge commit with the exact feature
    commit as second parent.
  expected_evidence_delta: The merge commit has the reviewed main parent and exact
    feature second parent, only intended feature paths enter main, unrelated governance
    state remains present, and no remote reference changes.
  status: pending
  unknowns: []
- id: T-002
  description: Validate the exact merged main bytes and behavior with focused transaction
    tests, the full repository suite, static checks, Plugin validation, affected skill
    validation, and exact path-hash comparison.
  expected_evidence_delta: All supported integration checks pass on the merge commit,
    and the five validated feature paths retain their intended content.
  status: pending
  unknowns: []
  depends_on:
  - T-001
- id: T-003
  description: Run the supported cachebuster helper with its default UTC suffix, validate
    the single-suffix base-version invariant, and create a bounded local metadata
    commit.
  expected_evidence_delta: The target version is 1.0.4+codex.<UTC token>, only intended
    version metadata changed, Plugin and skill validators pass, and the exact target
    commit is recorded.
  status: pending
  unknowns: []
  depends_on:
  - T-002
- id: T-004
  description: Resolve the verified marketplace name with the supported helper, reinstall
    work-governance from work-governance-local, and verify enabled source, cache,
    registration, and runtime identities.
  expected_evidence_delta: codex plugin state names the exact target build and the
    installed cache and runtime bytes match the locally committed source.
  status: pending
  unknowns: []
  depends_on:
  - T-003
- id: T-005
  description: In a fresh session, verify SessionStart, UserPromptSubmit, bootstrap
    receipt, Plan authority, work-lifecycle availability, and the exact target build;
    complete independent evidence review and successor closeout.
  expected_evidence_delta: Fresh-session evidence attests the exact build and both
    hooks, independent review has no blocker-level finding, all O/V/A/delivery/activation
    surfaces are evidence-complete, and no Push occurred.
  status: pending
  unknowns: []
  depends_on:
  - T-004
validations:
- id: V-001
  description: Verify merge-commit parents, exact integrated path set, pre/post local
    status, and unchanged remote references.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:git-merge-and-dirty-state-protection
- id: V-002
  description: Run focused composed-transaction tests, the full repository suite,
    Ruff format and check, strict mypy, Plugin validation, and affected skill validation
    on the exact merged main.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:repository-validation-toolchain
- id: V-003
  description: Verify the cachebuster helper preserved base version 1.0.4, emitted
    exactly one UTC suffix, and changed only intended metadata before local commit.
  status: pending
  provenance:
    kind: code-invariant
    source_ref: project:plugin-creator-cachebuster-policy
- id: V-004
  description: Verify the supported marketplace lookup, reinstall result, enabled
    Plugin registration, source-cache byte identity, and exact runtime bundle.
  status: pending
  provenance:
    kind: supported-integration-boundary
    source_ref: project:codex-plugin-installation-contract
- id: V-005
  description: Verify a fresh SessionStart and fresh UserPromptSubmit for the exact
    target, mandatory work-lifecycle availability, independent review, and absence
    of Push or remote mutation.
  status: pending
  provenance:
    kind: confirmed-obligation
    source_ref: user:session/019fb21f-0f66-7d92-959b-2921547dff49/turn/019fb5c9-6b33-7fa0-bc78-ff10461ef673/sha256/a33b10c2ba21f5dfd1b36da41c51cdd4b4d4e7216c866afc06268609c037be13
artifacts:
- id: A-001
  path: plugins/work-governance/scripts/workctl.py
  status: pending
- id: A-002
  path: tests/test_workctl.py
  status: pending
- id: A-003
  path: plugins/work-governance/skills/work-lifecycle
  status: pending
- id: A-004
  path: README.md
  status: pending
- id: A-005
  path: plugins/work-governance/.codex-plugin/plugin.json
  status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260731-001
  rollover_id: ROL-20260731-001
  predecessor:
    path: .work-governance/_Plan/PLAN-20260730-001.md
    plan_id: PLAN-20260730-001
    revision: 48
    sha256: d07233b1b7791bc81776ffbd4a7417989316aa1a2b38c30572715981a01a7108
  sources: []
  confirmations:
    rollover: C-PLAN-ROLLOVER
delivery:
  status: pending
  boundary: local main merge commit plus bounded Plugin cachebuster metadata commit;
    no Push
  evidence_ref: project:PLAN-20260731-001-not-yet-delivered
activation:
  status: pending_confirmation
  current_ref: plugin:work-governance@1.0.4+codex.20260730081627
  target_ref: plugin:work-governance@1.0.4+codex.pending
  confirmation_id: C-LIVE-SWITCH
route:
  route_status: active
  slice_status: t-001-ready
  next_phase: Execute T-001 local main merge preflight and create the exact bounded
    non-fast-forward merge commit.
  validation_standard: T-001 requires exact main and feature baselines, merge-parent
    verification, intended-path scope, preserved unrelated state, and unchanged remote
    references before T-002 can start.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Execute T-001 under the accepted C-LIVE-SWITCH boundary; do not start
    T-002 until the exact merge-parent, path-scope, dirty-state, and remote-boundary
    evidence is verified.
revision_history:
- revision: 1
  kind: admission
  changed_at: '2026-07-31T02:37:45Z'
  rationale: Prepare the bounded local main integration and exact Plugin activation
    route after the completed predecessor.
  confirmation_id: C-LIVE-SWITCH
intake:
  protocol_version: 1
  records:
  - request_ref: user:session/019fb21f-0f66-7d92-959b-2921547dff49/turn/019fb617-e621-7561-970f-831ed9a4cf9d/sha256/ade4f6e5d23efebe7f28664fcdd185d626a960bc7a30155b7b2b02e1b2957fa9
    request_sha256: ade4f6e5d23efebe7f28664fcdd185d626a960bc7a30155b7b2b02e1b2957fa9
    classification: plan_controlled
    targets:
    - route
    decision: proceed
    rationale: The user accepted the exact stable rollover digest; predecessor, index,
      corrected successor contract, and v2 confirmation payload remain unchanged,
      so apply the bound rollover and continue with the successor route.
    decision_basis_sha256: 3d07800895de0483e7a61de3e84845ee7ce6387be6372b52081c08ef1cdc1662
    previous_record_sha256: null
    recorded_at: '2026-07-31T02:54:07Z'
    record_sha256: 822a78cd0ea96013b6c1bea757b9c945a194506f6459de9d3407b1dd84daa1e1
---
# PLAN-20260731-001

This prepared successor is not active authority until the exact
`C-PLAN-ROLLOVER` digest is accepted and the controller completes the index-last
rollover transaction.

The route separates local integration, merged-main validation, cachebuster
generation, Plugin reinstallation, and fresh-session activation into dependency-
ordered slices. It preserves the existing accepted `C-LIVE-SWITCH` authority while
forbidding Push, remote publication, destructive cleanup, hand-edited Plugin
registration, and unrelated-state absorption.
