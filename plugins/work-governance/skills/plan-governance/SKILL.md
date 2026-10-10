---
name: plan-governance
description: Use when deciding whether a task needs a Plan, creating or admitting a Plan, promoting No-Plan work into one, coordinating dependent stages, or deciding whether new evidence requires a material Plan revision.
---

# Plan Governance

A Plan governs an evolving route to a goal. It remains usable without any
particular persistence tool; when a Plan-recording tool is available, use that
tool's own Skill for storage and recovery mechanics.

Persistence readiness does not decide whether a Plan is warranted. Admit or
promote based on coordination value even when the active persistence provider
is temporarily unavailable; keep a bounded working Plan contract and carry it
forward when the provider recovers. Conversely, provider availability never
forces a Plan.

## Plan Admission

Create a Plan only when it adds durable coordination value, such as:

- recovery across turns, context loss, or long pauses;
- multiple dependent stages or independently owned work;
- a confirmed contract or confirmation gate that must survive handoff;
- a long-running delivery whose state cannot be reconstructed cheaply.

Complexity or impact alone does not force a Plan. A high-impact one-step action
still needs exact authority and evidence, and may deserve a separate record or
retrospective, without being converted into a Plan.

No-Plan means no Plan entity or Plan ceremony. It does not forbid independent
knowledge, decision, risk, evidence, or retrospective records when a relevant
persistence capability exists.

## Plan Contract

Capture only what controls execution and review:

- the goal and meaningful non-goals;
- current evidence, assumptions, constraints, and unresolved questions;
- material solution strategies and feasibility assumptions, each marked as
  confirmed, evidenced, or gated;
- the current decision owner, any explicit decision-authority envelope, and
  when that delegation ends, narrows, or must return to confirmation;
- stages, dependencies, ownership, and the next executable action;
- acceptance evidence, semantic-event handling, confirmation gates, and stop
  or revision conditions.

Depth should match uncertainty and consequence. Do not manufacture phases,
task hierarchies, roles, or test matrices to make the Plan look complete.

## Executable Stage Gate

Before presenting or delegating a stage as executable, distinguish confirmed
user choices from implementation assumptions. If a proposed approach or
critical feasibility assumption materially changes the outcome, architecture,
data or authority boundary, cost, risk, or acceptance, the Plan must either:

- use an explicit confirmed choice with bounded feasibility evidence; or
- keep the choice pending and place a confirmation gate before the first
  dependent design, delegation, or mutation.

Do not hard-code one approach into a stage definition or acceptance criteria
and then ask only about its prerequisites. Feasibility discovery supports a
recommendation; it does not make a user-owned direction choice. Ordinary
reversible implementation details remain agent-owned and must not create a
confirmation ceremony.

If explicit decision delegation covers the material choice, the Plan may mark
that choice as Codex-owned within the stated task or stage envelope instead of
creating a user gate. Compare the material effects, select an evidence-backed
route, and preserve the decision and its impact. Delegation never expands Plan
scope or authorizes a target, environment, or guarded action not named in the
authorization contract.

Decision delegation does not require a Plan. The same authority envelope and
semantic-review rules apply to No-Plan work without creating a Plan entity or
second permissions record.

## No-Plan To Plan

When work evolves into needing a Plan, use the available Plan-recording tool on
the first admission and explain the evolution. Carry forward the useful prior
context rather than pretending the Plan began at admission:

- original request or a faithful digest;
- relevant findings, decisions, constraints, and evidence;
- open assumptions, questions, risks, and failed attempts;
- why durable coordination became valuable now;
- the current goal, contract, next action, and confirmation boundary.

Do this once. Do not backfill noise or recreate every conversational step.

## Revision

Revise the Plan when evidence changes the confirmed goal, Plan contract, data
strategy, delivery form, material solution strategy, feasibility boundary,
acceptance, stage dependency, or another choice that invalidates the active
route. Record the cause, prior route, new route, affected work, and revalidation
needed through the available Plan tool.

New evidence, a failed material assumption, validation failure, milestone,
scope or relevant external-state change, and a receipt mismatch are semantic
events. In the default mode, reopen a compact user confirmation frontier when
the required revision changes a user-owned route or contract. Under explicit
decision delegation, Codex may decide the review depth and evolve the Plan,
replace or reorder the route, or expand validation without asking while the
change remains inside the active decision-authority envelope. Preserve the
cause, prior route, new route, affected work, and revalidation needed.

Reopen confirmation only when the revision must change the goal, exceed the
delegated scope or decision classes, enter an unauthorized environment, or use
an unlisted guarded action. A delegation that expires, is narrowed, or is
revoked restores the corresponding confirmation gate. No semantic change means
no Plan revision or repeated review merely to refresh the record.

Ordinary code structure changes, local implementation choices, and corrected
estimates do not require a user confirmation gate unless they materially alter
the agreed outcome or authority. Preserve meaningful supersession history, but
do not maintain compatibility behavior or per-version test suites without an
independently proven need.

### Plan Exit And Task Disposition

Replacing, abandoning, cancelling, or otherwise retiring a Plan is not complete
until its affected execution graph has been explicitly assessed. An unassessed
Task must not be assumed current merely because the exiting Plan was current;
the assessment does not require every Task to change state. `retain-original`
is a valid result when the original identity, status, version, references, and
execution meaning remain accurate.

Build one bounded exit-scope inventory from the exiting Plan by recursively
following primary-containment edges through directly nested Plans and Tasks and
then through their nested Plans and Tasks. For each reached Task, inspect only
the current effective references and dependants needed to assess its exit. This
includes current Goal or Plan references and current external Tasks whose
`depends_on` relation requires the Task. Do not turn this into a project-wide
task scan. Preserve terminal Tasks and their evidence as history; never reopen,
relabel, or duplicate them merely because an ancestor Plan exits.

Complete and validate that inventory before any exit mutation. Traverse by
stable Plan and Task identity and visit each identity once. A primary-containment
cycle, a reached Plan or Task without a stable identity, or one identity claimed
by conflicting primary parents makes the affected Plan exit incomplete. Stop
only that exit, preserve its current Plan and Task state, report the offending
edge or unidentified node, and continue independent work. Do not guess a
retirement, repair the graph implicitly, or widen into a project-wide scan.
Valid secondary references from another Goal or Plan, and external `depends_on`
relations, are not conflicting primary parents.

Assess every affected nonterminal Task with one explicit result:

- **retain-original:** preserve the Task as-is when its identity, status, and
  version remain accurate. Record or verify its effective currentness, effective
  carrier or explicit absence of one, responsible owner, applicable authority,
  and next executable entry or re-entry condition. A shared current Task can
  remain unchanged; a historical or deferred Task can preserve its original
  state without becoming terminal or joining a replacement Plan;
- **replace:** only for a Task that is genuinely replaced, create a distinct
  successor identity in the replacement route, record a machine-readable
  handoff whose successor `supersedes` the old Task, and make the old Task leave
  the executable current set after its current references and dependants have
  been preserved or rebound;
- **cancel or abandon:** record the reason and the effective terminal outcome;
  a parent Plan's exit is not by itself a sufficient Task reason; or
- **continue or defer:** record the effective carrier or explicit absence,
  responsible owner, applicable authority, and next executable entry or
  explicit re-entry condition. Deferral can leave the Task's nonterminal status
  and version unchanged while removing it from the executable current scope.

Task status and version are separate from executable currentness and scope.
A later return from deferred or noncurrent history to executable currentness is
a new explicit currentness transition. Verify the re-entry condition, authority,
and carrier; do not infer currentness from old Plan ancestry or from a generic
active marker.

Resolve bounded current effective references before replacement, cancellation,
abandonment, or a currentness change. A Goal or Plan reference is current only
when it is reachable from a valid nonterminal current root; an active marker
whose only ancestor is terminal does not make the reference current. When the
same Task is referenced by another current Goal or Plan, preserve the original
Task when accurate and remove or replace only the exiting Plan's relation. Do
not retire it by parent-Plan cascade. When a current external Task depends on it,
do not silently terminalize the dependency or remove it from executable scope;
retain it or rebind that dependency to a verified successor or continuation.

When a Task is in progress or has a live claim, `retain-original` may preserve
the claim only after verifying that its owner, carrier, authority, and scope
remain valid. Otherwise, explicitly continue it, complete an acknowledged
handoff, or release or fence the claim before replacement, cancellation,
abandonment, or deferral. A status-only edit is insufficient.

Apply ordinary dispositions directly when existing authority already covers
the same goal, budget, permissions, target, and effects. The Plan exit decision
does not need a second confirmation ceremony. Reopen confirmation only when a
disposition changes the goal or budget, expands permissions or scope, enters an
unauthorized environment, or requires another guarded action.

After assessment and any mutation, require exact readback of the exiting Plan
and every affected Task. Verify retained identity, status, version, effective
currentness, carrier, next entry or re-entry condition, current Goal or Plan and
`depends_on` references, each successor relation, and any live-claim transition
that applies. A mismatch leaves the exit incomplete and reopens only the
affected item. When the accurate result retains existing state, do not create a
Task mutation or version churn merely to prove the assessment. No meaningful
disposition or currentness delta means no write or revision churn. This Skill
owns these semantics; the active persistence-provider Skill owns schemas,
commands, transactions, retries, and other storage mechanics.

## Close

A completed Plan is evidence of tracked execution, not proof of the user's
outcome. Judge completion using current artifacts and validation, then use the
persistence tool for mechanical closeout if one is active.
