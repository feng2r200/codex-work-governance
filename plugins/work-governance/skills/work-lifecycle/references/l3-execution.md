# L3 Execution

Execute only the next authorized slice.

Before edits:

- require `plan authority check` to return `GOVERNED_ACTIVE` for
  Plan-controlled work;
- read the current authority files and relevant current code/docs;
- protect user changes and unrelated dirty worktree state;
- identify the exact files to edit and why those are the authority locations;
- define the command or inspection that will prove the slice.

During execution:

- keep changes scoped to the obligation;
- avoid parallel writes to the same data or remote surface;
- use deterministic scripts for repeated fragile work;
- record key evidence in `.work-governance/logs/` only when a Plan exists and the record has
  handoff value;
- never promote `.work-governance/logs` content into Plan facts without
  confirmation.

When recovering suspect artifacts, identify the repair task with
`resolves_artifacts`. This exception permits only the declared recovery work;
it does not clear the suspect state or make adjacent tasks executable. It
never permits progress through a `quarantined` or `rollback-pending` artifact.
Blocking the affected task remains legal after an artifact becomes suspect;
the fail-safe transition must not be prevented by the artifact blocker itself.

For SubAgents, pass only a delegation contract and raw artifacts. Do not pass the
intended answer unless the validation explicitly requires it.

Validation standard: the changed artifact can be tied to a task, obligation, and
planned check.

## Completion Boundary

Treat a bounded execution unit as a completed slice only when it has an
independent acceptance point and the parent agent has fresh evidence for that
point. After completing it, emit the mandatory slice completion summary before
describing or starting the next step.

```text
当前子任务：<T-ID 或 NO_PLAN>
完成与作用：完成了什么，以及它如何服务父任务/项目目标
验证：验证方式、当前结果和未覆盖项
决定与依据：实质决定、来源与取舍；没有则写“无新增决策”
修改：文件、配置、数据或外部状态；没有则写“无”
下一步：动作、验证标准和确认门
```

- For Plan-controlled work, `当前子任务` is the corresponding `T-ID`.
- For No-Plan work, the whole request is one slice and `当前子任务` is
  `NO_PLAN`.
- When one response completes multiple slices, emit one summary per slice in
  execution order. Do not merge them in a way that hides a decision or
  validation gap.
- `in_progress`, `blocked`, failed, partially verified, or unverified work is
  not a completed slice and must not be formatted as one.
- A SubAgent's report alone cannot complete a slice. The parent agent must
  validate the result before including it in a completion summary.

In `决定与依据`, record only decisions that materially affect the goal, scope,
behavior, cost, safety, or delivery form. Name the basis as user confirmation,
project rule, current evidence, technical constraint, or agent tradeoff.
Mechanical steps are not decisions; when there is no material decision, write
`无新增决策`.
