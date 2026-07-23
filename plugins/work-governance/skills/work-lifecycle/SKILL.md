---
name: work-lifecycle
description: Mandatory lifecycle entry for every Codex work request when the work-governance plugin is available. Use when Codex receives or continues any request; route single low-risk answers as No-Plan and govern intake, unknowns, demand contract, Plan admission, execution gates, evidence, deviation handling, validation, completion claims, handoff, and fail-closed behavior for code, docs, data, remote, Git, or project-governance work.
---

# Work Lifecycle

Use this skill first for every work request. Route a single low-risk answer
through `L0 Intake` as No-Plan. If this skill cannot be loaded when
work-governance is required, stop and report `ENVIRONMENT_BLOCKED`, the missing
component, and the recovery condition.

## Non-Delegable Rules

- Communicate in the user's requested language and lead with the conclusion.
- Treat the current user instruction as the highest task authority.
- Keep root `AGENTS.md` thin: route and hard constraints live there; reusable
  method lives in this plugin.
- Use `workctl.py` for deterministic Plan mutations when a Plan is admitted.
- Do not create `_Plan/` or `.logs/` for No-Plan tasks.
- Keep `_Plan/index.yaml` as the active Plan locator and
  `_Plan/<plan-id>.md` frontmatter as the sole mutable machine authority;
  Markdown body is only explanation and handoff.
- In Git projects, version `_Plan/` by default and add `.logs/` to
  `.git/info/exclude` by default.
- High-impact, destructive, remote, production, data, structure-revision, and
  substantive rollback decisions require confirmation before action.
- A SubAgent may execute only within an explicit delegation contract. The parent
  agent owns the Plan, confirmation gates, and logs.
- Completion, fix, test-pass, commit-ready, or merge-ready claims require fresh
  evidence from the current run.

## Lifecycle States

- `L0 Intake`: map current instruction, knowns, unknowns, authority, risk, and
  whether the task is No-Plan or Plan-controlled. Read
  `references/l0-intake.md` when the task is not clearly low-risk.
- `L1 Demand Contract`: define obligations, acceptance, scope, no-go boundaries,
  and confirmation gates. Read `references/l1-demand-contract.md`.
- `L2 Plan Control`: admit, validate, revise, confirm, or recover a Plan. Read
  `references/l2-plan-control.md` before any Plan mutation.
- `L3 Execution`: execute the next verified slice, preserve evidence, and avoid
  widening scope. Read `references/l3-execution.md` for file, data, remote, or
  role-isolated work.
- `L4 Independent Validation`: challenge the Plan, review artifacts, audit
  evidence, and decide closeout strength. Read `references/l4-validation.md`.
- `L5 Deviation and Rollback`: freeze downstream tasks, mark suspect artifacts,
  and require confirmation for rollback, quarantine, or compensation. Read
  `references/l5-deviation-rollback.md`.
- `L6 Closeout and Handoff`: report obligations, checks, evidence, changed files,
  residual risk, and the next step. Read `references/l6-closeout-handoff.md`.

## Plan Admission

Classify the request:

- `No-Plan`: single-step query, explanation, pure information confirmation, or
  low-risk tiny edit with no handoff value. Do not create `_Plan/` or `.logs/`.
- `Plan-controlled`: file edits with verification, multiple obligations,
  cross-module work, long-running work, role isolation, high-impact choices,
  remote/data/production actions, structural governance changes, or work that
  must be handed to a future agent.

When admitting a Plan, create or use `_Plan/index.yaml` and `_Plan/<plan-id>.md`.
Use IDs `PLAN-YYYYMMDD-NNN`, `O-`, `T-`, `V-`, and `A-`.

## Controller

Run the controller from the project root:

```bash
uv run --script plugins/work-governance/scripts/workctl.py plan status
```

All Plan writes must use the controller or an equivalent atomic write path with
revision checks, short lock, and validation.

## SubAgent Delegation

Before delegating, write a delegation contract with:

- task id, scope, allowed reads/writes, no-go boundaries, evidence required;
- whether the SubAgent may propose or only inspect;
- expiration condition;
- exact artifacts it may create or modify.

SubAgent output is evidence input, not authority. The parent validates and
performs any Plan/log update.
