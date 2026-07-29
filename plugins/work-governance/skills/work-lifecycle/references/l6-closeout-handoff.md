# L6 Closeout and Handoff

Close out by separating local completion, route status, and remaining gates.

Use these claim levels:

- `in_progress`: the current delivery is incomplete;
- `local_delivery_complete`: the bounded artifact is locally complete, but a
  route-level decision, integration, activation, publication, or validation
  remains;
- `route_complete`: the entire governed route is terminal.

Report:

- current slice status and project route status;
- next phase, its validation standard, and its confirmation gate;
- changed files and delivery boundary;
- obligations covered and the check for each;
- validation commands and key outputs;
- unverified areas and residual risks;
- Git status, commit hash, and excluded files when Git was used;
- whether the formal next step is action, verification, confirmation, or none.

For every completed slice, present the reply contract below before any
next-step statement:

```text
当前子任务：<T-ID 或 NO_PLAN>
完成与作用：完成了什么，以及它如何服务父任务/项目目标
验证：验证方式、当前结果和未覆盖项
决定与依据：实质决定、来源与取舍；没有则写“无新增决策”
修改：文件、配置、数据或外部状态；没有则写“无”
下一步：动作、验证标准和确认门
```

Use `无` when no file, configuration, data, or external state changed. Multiple
completed slices require separate summaries in execution order. Do not use the
completion-summary shape for `in_progress`, `blocked`, unverified, or
SubAgent-only results; report their actual state and evidence gap instead.

Do not claim complete when:

- authority is not `GOVERNED_ACTIVE`;
- verification was skipped, failed, or only adjacent;
- any must obligation lacks evidence;
- any required confirmation is missing;
- suspect, quarantined, or rollback-pending artifacts remain;
- live switch or remote mutation remains unconfirmed.
- a structured exclusion is `deferred` or `pending_confirmation`;
- activation is `deferred`, `pending_confirmation`, or `in_progress`;
- local delivery is complete but route-level activation is unresolved.

Use `plan closeout-check` before a terminal claim. `plan complete` is legal only
when `route.route_status=terminal`, every obligation/task/validation is
verified or skipped, every artifact is final, every required confirmation is
consistently resolved, and both route and handoff have no remaining next phase,
next step, or confirmation gate. A declined decision is resolved only when its
bound tasks are skipped, exclusion disposition is resolved, and activation is
`declined` where applicable. Schema-v4 terminal closeout additionally requires
complete delivery, no unresolved exclusion disposition, and resolved
activation with typed decision or runtime evidence.

Do not reopen or structurally revise a completed terminal Plan to admit later
work. When a distinct route is required, prepare a new schema-v4 Plan contract
and use the digest-bound `plan rollover apply` flow. The completed predecessor
remains unchanged; the successor becomes authority only after index-last
activation.

Do not call an obsolete or user-withdrawn route complete. Use the
digest-bound `plan retire apply` flow to preserve the original bytes, record
every unfinished disposition, mark the Plan retired, and remove its index
authority last. After retirement the project is `UNMANAGED_EMPTY`; admit any
fresh route separately instead of reusing the retired queue.

Verified obligations and validations, final artifacts, and complete delivery
must be produced by their dedicated evidence-bound transitions. A declined
activation decision may resolve only its bound activation, exclusion, route,
and handoff; it cannot certify delivery or validation evidence.

Use this final line only when accurate for the current scope:

`本轮已完成，暂无必须下一步`

If a route continues beyond the local slice, distinguish:

- local slice next step;
- route-level next step;
- confirmation gate and validation standard.

`plan status` reports `completion_claims`. Use
`no_required_next_step_allowed=true` as the deterministic eligibility signal
for an absolute no-next claim. “No currently authorized action” is not the same
as “no required next step.”
