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
- Require the current SessionStart context and
  `.work-governance/bootstrap-state.json` to report `READY` for the exact
  installed Plugin build before Plan-controlled work. If the hook is
  untrusted, disabled, skipped by managed policy, absent, or stale, report
  `ENVIRONMENT_BLOCKED` and the recovery condition.
- Do not create a Plan, index, or log entry for No-Plan tasks. Layout bootstrap
  may create `.work-governance/version.yaml` and ignored local infrastructure.
- Keep `.work-governance/_Plan/index.yaml` as the active Plan locator and
  `.work-governance/_Plan/<plan-id>.md` frontmatter as the sole mutable machine authority;
  Markdown body is only explanation and handoff.
- Separate local slice completion, delivery completion, and route-level
  activation. Missing authority for a required future action creates a
  confirmation gate; it does not make that action disappear from the route.
- Before Plan-controlled work, inspect Plan authority. Continue real work only
  in `GOVERNED_ACTIVE`; use only inspect, validation, reconciliation, or
  recovery commands in every other authority state.
- In Git projects, version `.work-governance/_Plan/`, `version.yaml`, and
  `.gitignore` by default. The exact `.work-governance/.gitignore` contract
  excludes only local runtime content.
- High-impact, destructive, remote, production, data, structure-revision, and
  substantive rollback decisions require confirmation before action.
- A SubAgent may execute only within an explicit delegation contract. The parent
  agent owns the Plan, confirmation gates, and logs.
- Completion, fix, test-pass, commit-ready, or merge-ready claims require fresh
  evidence from the current run.
- Keep a goal anchor before repeating an action or expanding validation: restate
  the user-visible target, the unresolved fact, and the next action expected to
  change evidence. Tests and coverage are support tools, not the target.
- Do not repeat a failed action with materially identical inputs and state. One
  retry is allowed only after naming the changed assumption or input and the
  expected evidence delta. Two consecutive attempts without a material
  evidence delta require `INEFFECTIVE_LOOP_DETECTED`, downstream freeze, and L5
  root-cause review. An explicit monitoring or wait request is exempt while the
  observed external state remains the intended evidence.
- After the smallest viable vertical slice, run the cheapest safe reality-bound
  probe when feasible. Derive every added test from a confirmed obligation,
  observed failure, code invariant, or supported integration boundary. Do not
  invent hypothetical use cases or pursue exhaustive coverage as an end state.
- Before selecting a correction, distinguish symptom from a falsifiable root
  cause, state the causal chain and discriminating probe, and challenge whether
  the proposed change removes the cause or only hides it. Compare materially
  plausible containment, causal correction, and alternate-route options.
- After every independently verifiable execution slice, report the slice using
  the mandatory completion summary before describing or starting the next
  step. A Plan-controlled summary names its `T-ID`; a No-Plan request uses
  `NO_PLAN`.

## Lifecycle States

- `L0 Intake`: map current instruction, knowns, unknowns, authority, risk, and
  whether the task is No-Plan or Plan-controlled. For Plan-controlled work,
  discover user-designated, project-rule-designated, indexed, conventional,
  and lineage-recorded Plan candidates before execution. Read
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
  low-risk tiny edit with no handoff value. Do not create a Plan, index, or log
  entry.
- `Plan-controlled`: file edits with verification, multiple obligations,
  cross-module work, long-running work, role isolation, high-impact choices,
  remote/data/production actions, structural governance changes, or work that
  must be handed to a future agent.

When admitting a Plan, create or use `.work-governance/_Plan/index.yaml` and
`.work-governance/_Plan/<plan-id>.md`.
Use IDs `PLAN-YYYYMMDD-NNN`, `O-`, `T-`, `V-`, and `A-`.

Never infer a second execution authority from a filename, Git history, a phase
design, or text such as "next step" alone. A likely second authority requires
review; a confirmed second authority requires reconciliation.

## Controller

Run the controller from the project root:

```bash
uv run --offline --cache-dir .work-governance/cache/uv --no-python-downloads \
  --script plugins/work-governance/scripts/workctl.py plan status
```

Run `layout status` first. Except for `layout status|validate|migrate|recover`,
controller commands require `LAYOUT_READY`. READY bootstrap uses
`.work-governance/cache/uv` and invokes the controller offline. All Plan writes
must use the controller or an equivalent atomic write path with revision checks,
the stable `.work-governance/workctl.lock`, and validation.

## SubAgent Delegation

Before delegating, write a delegation contract with:

- task id, scope, allowed reads/writes, no-go boundaries, evidence required;
- whether the SubAgent may propose or only inspect;
- expiration condition;
- exact artifacts it may create or modify.

SubAgent output is evidence input, not authority. The parent validates and
performs any Plan/log update.

## Slice Completion Summary

An execution slice is a bounded unit with its own acceptance point. After such
a slice is complete and validated, report these fields in this exact order:

```text
当前子任务：<T-ID 或 NO_PLAN>
完成与作用：完成了什么，以及它如何服务父任务/项目目标
验证：验证方式、当前结果和未覆盖项
决定与依据：实质决定、来源与取舍；没有则写“无新增决策”
修改：文件、配置、数据或外部状态；没有则写“无”
下一步：动作、验证标准和确认门
```

This is a reply protocol, not a Plan task-schema extension or a requirement to
turn the Plan into a process log. If one response completes multiple slices,
report each slice separately and in execution order.
