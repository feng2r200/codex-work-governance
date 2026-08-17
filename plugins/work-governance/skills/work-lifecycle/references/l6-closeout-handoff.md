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
- acceptance anchors for every must-have obligation;
- weak-link surfaces checked, their artifact digests or freshness evidence, and
  any deferred disposition;
- validation commands and key outputs;
- unverified areas and residual risks;
- Git status, commit hash, and excluded files when Git was used;
- whether the formal next step is action, verification, confirmation, or none.

`下一步` is an informational routing field, not an implicit confirmation.
Never append "是否继续", "确认进入下一阶段", or an equivalent question unless
the next target is blocked by a real user-owned unknown or a typed intervention
contract. If earlier dependency-ready work remains authorized, report the next
action and continue it in the same turn.

For every completed slice, present the reply contract below before any
next-step statement:

```text
当前子任务：<T-ID、ADMISSION、GOVERNANCE 或 NO_PLAN>
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

- authority is not current-schema `GOVERNED_ACTIVE` for ordinary work, or is
  still `PLAN_SCHEMA_REFRESH_REQUIRED` after a legacy refresh slice;
- verification was skipped, failed, or only adjacent;
- any must obligation lacks evidence;
- any must obligation lacks an acceptance anchor;
- an in-scope weak-link artifact was not checked for existence, digest, or
  freshness;
- any required confirmation is missing;
- suspect, quarantined, or rollback-pending artifacts remain;
- live switch or remote mutation remains unconfirmed.
- a structured exclusion is `deferred` or `pending_confirmation`;
- activation is `deferred`, `pending_confirmation`, or `in_progress`;
- local delivery is complete but route-level activation is unresolved.

Use `plan closeout-check` before a terminal claim. Schema-v5 closeout is
runtime-backed: task completion comes from the runtime state bundle, not Plan
frontmatter, and `plan complete --expected-state-sequence <state_sequence>`
records the terminal contract event, emits a JSON completion payload, releases
the active pointer, and leaves the completed Plan as history after readiness is
true. `goal close` is the same closeout path and returns the same JSON shape.
For schema v4, `plan complete` remains revision/intake guarded and is legal only when
`route.route_status=terminal`, every obligation/task/validation is verified or
skipped, every artifact is final, every required confirmation is consistently
resolved, and both route and handoff have no remaining next phase, next step,
or confirmation gate. A declined decision is resolved only when its bound tasks
are skipped, exclusion disposition is resolved, and activation is `declined`
where applicable. Schema-v4 terminal closeout additionally requires complete
delivery, no unresolved exclusion disposition, and resolved activation with
typed decision or runtime evidence.

For schema v4, when all non-route readiness conditions already hold and the
current route gate is resolved, use
`plan complete --finalize-route --confirmation C-... --evidence-manifest ...`
to terminalize route and handoff and complete the Plan in one atomic write. Do
not insert a separate route-adaptation write that stales the current intake and
forces a decision-free extra user turn. The command still requires current-turn
intake, exact confirmation binding, independent route release, activation and
exclusion resolution, and canonical closeout evidence.

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

For a candidate release, plugin activation, migration, or governance-framework
claim, do a claim-boundary check before writing the final wording. The claim
must name the exact implemented executable surface, the current validation
evidence, and the still-deferred target-architecture items. `workctl help
<workflow>` and generated `docs/CLI_REFERENCE.md` define implemented CLI
surface; design drafts, historical plans, replay reports, or tests for adjacent
behavior do not prove unimplemented commands or full architecture completion.

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
