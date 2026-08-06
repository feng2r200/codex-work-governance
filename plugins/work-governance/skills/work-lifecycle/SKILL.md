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
- When a new request arrives while a Plan is active, classify it against the
  user-visible goal before changing the Plan. Run unrelated bounded work as a
  `NO_PLAN_INTERRUPTION`, preserve the parent Plan/task/revision/next-action
  resume anchor, and resume it automatically when the interruption ends.
  Reprioritize dependency-ready tasks for aligned non-material requests; adapt
  or revise the Plan only for aligned material change. Apply the same routing
  test to findings from slice audits and validation.
- Keep root `AGENTS.md` thin: route and hard constraints live there; reusable
  method lives in this plugin.
- Use the receipt-bound runtime `workctl.py` for deterministic Plan mutations.
- Require the current SessionStart context and its emitted session-scoped
  bootstrap receipt to report `READY` for the exact
  Plugin build, `session_id`, `runtime_bundle_ref`, `controller_ref`,
  `controller_sha256`, and `receipt_sha256` before Plan-controlled work. If the hook is
  untrusted, disabled, skipped by managed policy, absent, or stale, report
  `ENVIRONMENT_BLOCKED` and the recovery condition.
- Treat the emitted session-scoped bootstrap capability as a separate,
  SessionStart-only authority for exact layout migration or recovery commands.
  It never authorizes Plan-controlled work or satisfies the READY requirement.
- Treat `.work-governance/bootstrap-state.json` only as a legacy compatibility
  surface. It never overrides the exact session-scoped receipt emitted by the
  current hook.
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
  substantive rollback decisions are confirmation-risk signals. The model owns
  the ask/proceed judgment using current user authorization, project rules,
  reversibility, blast radius, and fresh evidence; ask before action whenever
  that authority is ambiguous or insufficient.
- Communication is not waiting. Discuss and summarize frequently during
  discovery, then continue across every dependency-ready execution slice.
  Progress reports, completed-slice summaries, phase transitions, and a stated
  next step do not create confirmation gates.
- Collect user input only for a blocking user-owned requirement unknown, the
  exact Plan contract that establishes a material solution, an
  evidence-proven material direction change in L5, or authority outside the
  Agent's local boundary. Investigate agent-owned facts and diagnose ordinary
  execution failures without asking the user.
- Treat local exploration, continuation requests, network recovery, and
  credential-ready notices as runtime signals by default. Do not create a
  speculative Plan unknown or revise the contract until evidence shows that
  the goal, scope, acceptance, safety, or required authority must change.
- Never ask a decision-free continuation question such as "should I continue"
  or "confirm the next phase." `下一步` is information unless it names a real
  user-owned decision and its blocked targets.
- Bulk or blanket authorization may reduce repeated prompts only when the model
  judges the current authorization still covers the repeated work. When repeated
  work can amplify a shared defect, keep the pilot task and validation as
  explicit dependencies; authorization cannot satisfy the pilot gate. Freeze
  downstream batches on observed quality drift and enter L5 before resuming.
- When a current user decision becomes future authority, prefer
  `user:session/<SessionId>/turn/<TurnId>/sha256/<digest>` over a date-only
  reference. Preserve existing typed references for backward compatibility.
- A SubAgent may execute only within an explicit delegation contract. The parent
  agent owns the Plan, confirmation gates, and logs.
- Completion, fix, test-pass, commit-ready, or merge-ready claims require fresh
  evidence from the current run.
- Treat reviewer acquisition failure as `VALIDATOR_UNAVAILABLE`, not as a
  confidence judgment about the work. After one initial attempt and at most one
  materially changed retry, a deterministic self-challenge may release only
  ordinary reversible local tasks; concrete blocker/high findings and delivery,
  activation, route, confirmation-bound, or other high-impact targets remain
  fail-closed. Before trying the same external reviewer path again, use
  `review acquisition check`; after a failed attempt, record the redacted failure
  with `review acquisition record-failure` so the runtime cooldown can return
  `VALIDATOR_UNAVAILABLE_CACHED` instead of repeating an unavailable path. For
  proxy, auth, missing-command, timeout, and attestor failures, treat a fresh
  cache for the same reviewer mechanism as matching even when the reviewed input
  digest changed.
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

For a new unmanaged project, prefer `goal init --stdin|--from-file` with a
minimal goal contract; the controller writes the canonical schema-v5 Plan,
runtime state, event ledger, and index. For strict legacy admission, use
`plan admit apply --manifest`; recover interruption through `plan admit recover`.
Do not create an empty Plan or index first. Use `plan confirmation add` for a
new explicit gate when the model determines a decision must be durable.
Schema v4 uses IDs `PLAN-YYYYMMDD-NNN`, `O-`, `T-`, `V-`, `A-`, and `U-`;
tasks name linked unknowns and their expected evidence delta.

Explore first when the missing fact is discoverable within the Agent's safe
boundary. Promote the result to a Plan unknown only when it blocks a named
target or proves a material contract decision is needed. Use the bounded
`plan status` view for routine progress; pass `--full` only when closeout
detail is needed. Use `plan history list|show` for loose historical Plan
inspection; it must not validate old Plans against the active schema. Use
`plan adapt --intent-stdin` to record adaptation intent without hand-writing a
strict patch manifest. When the active Plan is still schema v4, that high-level
intent path still requires `--expected-revision`, current turn receipt, and the
latest matching `--expected-intake-sha256` because it bumps Plan revision. Use
`task done --task-id T-001 --evidence-stdin` when raw evidence capture and task
verification are the same workflow. Keep
`evidence capture`, `plan evidence record`, and `task verify` for lower-level
or compatibility cases.

The public command aliases are generated from the controller parser. Read
`docs/MODEL_FIRST.md` first for the short model-facing workflow, then use
`docs/CLI_REFERENCE.md` for the complete option surface and `workctl help
<workflow>` for the short runtime view; do not maintain a second handwritten
option table in this Skill. Schema-v5 Plans keep the contract revision in the
Plan and task, event, and evidence runtime state in the ignored bundle
referenced by `state_ref`, `event_ref`, and `evidence_store_ref`.

Never infer a second execution authority from a filename, Git history, a phase
design, or text such as "next step" alone. A likely second authority requires
review; a confirmed second authority requires reconciliation.

## Controller

Run the exact `intake_command` injected by SessionStart from the project root.
It reads the versioned runtime snapshot named by `runtime_bundle_ref`, verifies
`controller_ref` against `controller_sha256`, and binds the command to the
current `receipt_sha256`:

```bash
uv run --no-project --offline --cache-dir .work-governance/cache/uv \
  --no-python-downloads --script <absolute-controller_ref> \
  --receipt-sha256 <receipt_sha256> intake status
```

Never derive a controller path from the repository, current branch, Plugin
cache, or this skill's source path. Reuse the same absolute controller and
receipt digest for every command in this session; pass `--receipt-sha256`
before the command domain. A replacement SessionStart in the same session
supersedes the digest when its trusted runtime identity changes; a different
session has its own receipt and cannot supersede this one. All controller commands require `LAYOUT_READY`
except for layout inspection/recovery. A blocked SessionStart may inject an exact
capability-bound `layout_command_prefix`; use it only for the reported layout
recovery, never for Plan writes. An active schema-v3 Plan reports
`PLAN_CONTRACT_UPGRADE_REQUIRED` until `plan contract upgrade apply|recover`
commits schema v4. When one confirmed workflow must reconcile schema-v3
authority and then upgrade that exact result, use
`plan reconcile-upgrade apply|recover`; its parent journal fixes
reconciliation before contract upgrade while both child journals remain
independently recoverable. If exact staging exists without its journal, re-run
parent `apply` for the parent window or parent `recover` for a child window;
unexpected or drifted partial staging fails closed. Any incomplete parent or
contract-upgrade journal makes authority recovery-only and blocks ordinary
Plan or task writes plus fresh structural Plan transactions; only the bound
workflow may resume. Use `plan adapt`, `plan contract revise`, and `plan unknown
add|resolve` for their separate responsibilities. For schema-v5 runtime work,
prefer direct `evidence capture` for command output and project-local artifacts;
small structured compatibility evidence can still be recorded under
`.work-governance/_Plan/.evidence/` and passed by `--evidence-manifest`.
`.work-governance/logs/` is local process detail only.
All mutations still use the stable `.work-governance/workctl.lock`, expected
revision checks, candidate validation, bounded lock acquisition with holder
diagnostics, and atomic writes.

`UserPromptSubmit` separately injects the current `turn_receipt_sha256`.
For mutable schema-v4 Plan work, run controller `intake receipt`, state an explicit
`proceed|explore|ask` decision, then append it with `plan intake record`.
Non-simple No-Plan work shows the reply-level `INTAKE_RECEIPT` but does not call
the Plan controller or persist an intake record. Schema-v5 ordinary exploration,
scheduling, evidence, task-state, and reprioritization commands do not consume the
turn receipt or persist intake; they use the READY session receipt, state sequence,
dependencies, confirmation gates, and evidence rules. Schema-v4 advancing commands
still require the turn digest plus the latest `expected_intake_sha256`. Never reuse
a prior turn decision for v4 or a high-impact action.

Schema-v4 and schema-v5 `plan confirm` decisions bind the exact current-turn
`request_ref` and basis; only schema v4 additionally requires current Plan
intake. For remote write, production change, destructive work, secret handling,
substantive rollback, and similar high-impact actions, use `risk inspect` when
you want controller-normalized facts about action kind, target, reversibility,
digest, evidence, and risk factors. The controller does not decide whether the
model must ask the user. If the model judges durable authorization is required,
use `plan confirm`, then `action authorize` and `action consume` for the exact
kind, target, and action digest. `action lease prepare|issue|authorize` remains
an advanced compatibility path for explicitly bounded repeated external work;
it is not the default prompt-reduction mechanism and does not waive pilot
evidence, review/artifact blockers, Plan contract drift checks, action
consumption, or success evidence.

The Plan keeps one bounded `intake.current` anchor and a digest/count summary.
Complete canonical records live in ignored, project-local, content-addressed
history. A repeated request is idempotent unless a changed controller-bound
decision basis either materially moves `ask` or `explore` to `proceed`, or
refreshes an otherwise identical `proceed` decision after a controller-caused
Plan revision. Every refresh records an explicit supersession link; direct
unbound edits, rationale changes, target changes, stale turns, and same-basis
mutation still fail closed.

An accepted external gate records authority but never claims the external
action happened. Reconcile a live exclusion only after successful activation
evidence and only through its explicit `activation.resolves_exclusions`
binding, with exact single-match compatibility for legacy Plans. When the
route, handoff, evidence, intake, and accepted confirmation are all ready, use
the atomic terminal closeout path instead of manufacturing a decision-free
extra user turn.

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
