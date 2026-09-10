---
name: work-lifecycle
description: Use for Codex work requests when Work Governance is available. Choose the minimum useful governance level, preserve goal and authority boundaries, admit WorkVCS-backed Plans only when durable state is valuable, and close work with evidence.
---

# Work Lifecycle

Use this skill first for work requests. It is a router and safety kernel, not a
fixed workflow that every task must execute.

## Core Rules

- Treat the current user instruction as the highest task authority.
- Use the minimum governance level that can satisfy the goal safely.
- `No-Plan` is for low-risk answers, tiny reversible edits, and bounded work
  with no handoff value. It makes zero WorkVCS calls and zero durable writes.
- `Plan-controlled` is for work with durable value: cross-turn recovery,
  multi-person or multi-agent coordination, multi-stage delivery, confirmation
  gates that must survive context loss, high-impact actions, or long-running
  deliverables.
- Work Governance decides policy. WorkVCS records durable state. Do not create a
  second mutable state authority in the plugin.
- A SubAgent may execute only inside an explicit delegation contract. The parent
  owns the user authority, parent Plan, confirmation gates, and final claim.
- Ask the user only for a blocking user-owned requirement, material Plan
  contract choice, evidence-proven direction change, or authority outside the
  current local boundary.
- If the goal, acceptance, and safe next action are already clear, do not block
  implementation on a Plan, frontier, role matrix, model choice, or process
  ceremony.
- High-impact, destructive, remote, production, data, structure-revision, and
  substantive rollback actions require an explicit authority judgment before
  action.
- Completion, fix, test-pass, commit-ready, merge-ready, activation, and route
  completion claims require fresh evidence from the current run.

## Plan Admission

When a No-Plan task evolves into Plan-controlled work, admit it through WorkVCS
once and carry forward the useful prior context. The first admission manifest
must include:

- original request text or digest;
- confirmed facts and decisions;
- explored evidence and freshness;
- unresolved agent-owned and user-owned unknowns;
- why escalation is needed now;
- goal, scope, non-goals, acceptance anchors, and validation requirements;
- confirmation gates and stop or revision triggers;
- authoritative repository, HEAD, project, and state digests when relevant;
- the next action.

Use WorkVCS high-level commands only after Plan-controlled routing is chosen:

- `workvcs project discover` and `workvcs project bind` for project authority;
- `workvcs plan admit` for first Plan admission;
- `workvcs plan evolve` for material route changes;
- `workvcs resume --cwd` for low-token recovery;
- `workvcs receipt issue` and `workvcs receipt consume` for mechanical
  target-bound authorization records;
- `workvcs closeout inspect` before completion claims.

WorkVCS receipts are records, not policy decisions. The model still decides
whether current authority is sufficient before issuing or consuming one.

If a needed WorkVCS command is missing, unsafe, or inconsistent with the desired
workflow, stop relying on that command. When current authorization covers local
tool repair, fix WorkVCS, rebuild and install the CLI, verify the real command
boundary, then continue. Otherwise report the blocker to the parent or user.

## Lifecycle References

- `L0 Intake`: read `references/l0-intake.md` when the route is not obviously
  No-Plan.
- `L0 Decision Frontier`: read `references/l0-decision-frontier.md` when the
  user supplied a solution but product goal, data strategy, delivery form, or
  acceptance evidence can still change the route.
- `L1 Demand Contract`: read `references/l1-demand-contract.md` before
  non-trivial edits or Plan-controlled mutation.
- `L2 Plan Control`: read `references/l2-plan-control.md` before WorkVCS Plan
  admission, evolution, resume, receipts, or closeout inspection.
- `L3 Execution`: read `references/l3-execution.md` for file, data, remote,
  Git, or role-isolated work.
- `L4 Independent Validation`: read `references/l4-validation.md` when the work
  has self-certification risk or high-impact claims.
- `L5 Deviation and Rollback`: read `references/l5-deviation-rollback.md` when
  evidence shows the route no longer serves the goal.
- `L6 Closeout and Handoff`: read `references/l6-closeout-handoff.md` before a
  completion claim.
- `L7 Context Governance`: read `references/l7-context-governance.md` before
  delegation or compact handoff.

Detailed Git, validation, and project-truth policy lives in the corresponding
skills. CodeGraph, Obsidian, image/Pinterest, concrete agent-role routing, and
model reasoning levels are scene-specific concerns; use the relevant skill or
project instruction only when that scene is actually in scope.

## Slice Completion Summary

After every independently verifiable execution slice, report these fields in
this exact order:

```text
当前子任务：<T-ID、ADMISSION、GOVERNANCE 或 NO_PLAN>
完成与作用：完成了什么，以及它如何服务父任务/项目目标
验证：验证方式、当前结果和未覆盖项
决定与依据：实质决定、来源与取舍；没有则写“无新增决策”
修改：文件、配置、数据或外部状态；没有则写“无”
下一步：动作、验证标准和确认门
```

This is a reply protocol, not a WorkVCS schema. Do not use it for incomplete,
blocked, unverified, or SubAgent-only results.
