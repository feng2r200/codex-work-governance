---
schema_version: 2
plan_id: PLAN-20260724-002
title: Plan authority reconciliation and closeout governance
status: active
mode: autonomous
revision: 1
created_at: '2026-07-24T00:00:00+08:00'
updated_at: '2026-07-24T00:00:00+08:00'
scope:
  include:
  - Detect semantic and deterministic Plan authority before controlled work.
  - Enforce single-active authority states, lineage, migration journals, and write
    gates.
  - Reconcile confirmed dual authority with prehashing, archives, pointers, and index-last
    activation.
  - Separate schema validation from full authority validation and add closeout gates.
  - Update lifecycle documentation, controller documentation, and regression coverage.
  - Validate the plugin in isolation and create one local feature commit.
  exclude:
  - Modify or migrate PharmaceuticalGroup project files.
  - Reinstall or switch the live Codex plugin.
  - Push, publish, or create remote branches or pull requests.
confirmations:
  required:
  - id: C-MIGRATION-BASELINE
    description: Approve the migration baseline, classifications, hashes, and merged
      Plan.
    status: accepted
    ref: user:implementation-plan-2026-07-24
    accepted_at: '2026-07-24T11:05:37+00:00'
obligations:
- id: O-001
  description: Authority discovery distinguishes confirmed, likely, and non-authority
    candidates without filename-only false positives.
  status: pending
- id: O-002
  description: All controlled writes fail closed outside GOVERNED_ACTIVE and expose
    the specified authority states and validation commands.
  status: pending
- id: O-003
  description: Reconciliation preserves both sources, validates hashes and revisions,
    journals each atomic step, rewrites pointers and optional AGENTS routing, and
    activates the index last.
  status: pending
- id: O-004
  description: Status and closeout report route, obligations, validations, confirmations,
    artifacts, handoff, and terminal readiness.
  status: pending
- id: O-005
  description: Lifecycle and public controller documentation describe discovery, migration,
    recovery, and closeout behavior.
  status: pending
- id: O-006
  description: Fresh static, unit, plugin, isolated-install, and independent challenge
    evidence supports the delivery.
  status: pending
tasks:
- id: T-001
  description: Implement authority discovery, classification input, state resolution,
    schema validation, and write gates.
  status: in_progress
- id: T-002
  description: Implement reconcile apply, prehashing, dual confirmation, archive pointers,
    journal recovery, and index-last activation.
  status: in_progress
- id: T-003
  description: Implement expanded status, closeout-check, complete, and update lifecycle
    and README documentation.
  status: pending
  depends_on:
  - T-001
- id: T-004
  description: Add regression fixtures for every authority state, migration failure,
    recovery, and closeout path.
  status: pending
  depends_on:
  - T-001
  - T-002
- id: T-005
  description: Run full static, unit, plugin, and isolated installation validation.
  status: pending
  depends_on:
  - T-003
  - T-004
- id: T-006
  description: Perform an independent plan, artifact, and evidence challenge and resolve
    findings.
  status: pending
  depends_on:
  - T-005
- id: T-007
  description: Complete route closeout and create the local delivery commit without
    Push.
  status: pending
  depends_on:
  - T-006
validations:
- id: V-001
  description: Ruff format and lint pass.
  status: pending
- id: V-002
  description: mypy strict passes for controller and tests.
  status: pending
- id: V-003
  description: Full pytest suite passes including the PharmaceuticalGroup-shaped reconciliation
    fixture.
  status: pending
- id: V-004
  description: Plugin and all skill validators pass.
  status: pending
- id: V-005
  description: Isolated plugin installation and fresh lifecycle/controller smoke pass.
  status: pending
- id: V-006
  description: Independent challenge finds no unresolved high-impact blocker.
  status: pending
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
  path: _Plan
  status: pending
authority:
  model: single-active
  state: governed
  canonical_plan_id: PLAN-20260724-002
  migration_id: MIG-20260724-001
  sources:
  - path: _Plan/PLAN-20260724-001.md
    role: unmerged-source
    sha256: 36a2bcb856ef5b1ce03bb0f7f59ef5a181b0f6b5462c5dea2b93661d72a579dc
    revision: 1
    archive_path: _Plan/archive/MIG-20260724-001/unmerged/PLAN-20260724-001.md
  confirmations:
    baseline: C-MIGRATION-BASELINE
route:
  route_status: active
  slice_status: implementation
  next_phase: Complete docs and full validation after controller regression passes.
  validation_standard: Every obligation has direct fresh evidence plus an independent
    challenge.
  confirmation_gate: none
handoff:
  route_status: active
  next_step: Complete docs, full validation, independent challenge, and local commit.
---
# Decision Summary

Adopt one active execution Plan per project. Semantic discovery proposes candidate
classifications; the controller deterministically enforces hashes, revisions,
lineage, confirmations, journal recovery, and terminal closeout.

# Migration Notes

The bootstrap Plan is archived as an unmerged source because the previous
controller could initialize only a schema-v1 shell. The earlier completed
plugin-release Plan remains non-authoritative historical evidence.

# Handoff

Resume from the first dependency-ready unfinished task in this Plan. Do not
modify PharmaceuticalGroup, live plugin installation, or any remote state.
