---
name: project-development-governance
description: Use when an explicitly enrolled project or ongoing software or product development spans multiple tasks, sessions, or phases and needs a durable project contract, bounded startup recovery, or end-of-task state reconciliation. Do not use for isolated edits or one-off investigations outside an enrolled project.
---

# Project Development Governance

Govern continuity across development tasks without turning each task into a
project ceremony. This skill owns the project entry, authority map, startup
recovery, and closeout reconciliation policy. A separate persistence-provider
Skill owns storage commands, identifiers, and recovery mechanics.

## Enter Project Mode Deliberately

Apply this skill when either:

- current project authority explicitly enrolls the project in this continuity
  contract; or
- the work clearly spans multiple tasks, sessions, or dependent phases and
  cannot be reconstructed cheaply from the current request and repository.

Do not infer enrollment merely because a repository exists, the task is
important, or an external state provider is available. Keep isolated edits and
one-off investigations outside an enrolled project on the ordinary lifecycle
path.

An enrolled project has one small project entry that routes readers to current
authority and state. Prefer an existing project convention and point to it from
project instructions. When no convention exists and creating one is in scope,
`docs/project/INDEX.md` is a reasonable default. The entry is a map, not a
second status report. Use [the project contract](references/project-contract.md)
when creating or reviewing it.

## Separate Project Authority From Execution State

Keep durable project meaning in project-native authority:

- goals, scope, boundaries, and non-goals;
- architecture, module relationships, interfaces, and accepted decisions;
- constraints, prohibitions, acceptance methods, and acceptance criteria; and
- durable risk policy and boundary conditions.

Select exactly one mutable execution-state provider for current progress,
status, prioritized next work, open execution risks, pending decisions, and
task evidence. It may be an external durable-state provider or a project-local
ledger, never both. Provider records may point to project authority but do not
silently replace it. Route any proposed promotion into project authority
through `work-governance:project-truth-governance`.

The same provider also carries the active task or stage decision-authority
envelope when the user explicitly delegates judgment. Record activation,
revocation, scope changes, and material delegated route decisions as narrow
semantic checkpoints. Do not create a parallel permissions ledger: long-lived
authority remains in project-native contracts, while the provider records only
the current execution effect and evidence. An unchanged envelope or review
outcome does not justify another provider read, report, or write.

A stage baseline is a project-native accepted snapshot, not a second mutable
execution-state provider. Between stage boundaries, the selected provider owns
live work state and receives narrow semantic deltas. Update the stage baseline
only at the project-defined stage boundary after the required acceptance
evidence exists, unless the user explicitly asks for an earlier update or a
current authority error must be corrected.

## Recover At Task Start

For enrolled work, do this before material implementation. If work becomes
eligible during a task, do it when the continuity need becomes clear:

1. Identify the logical project from explicit project authority, the primary
   artifact, and the relevant repository roots. Do not let an ambient working
   directory or shared backend choose it implicitly.
2. Read the project entry first and verify that its authority locations,
   single state-provider locator, and state-isolation boundary still resolve.
   A stable locator proves where to look, not that the returned state belongs
   only to this logical project. If several projects use shared provider state with
   no enforced partition, treat reads as candidate context and fail closed on
   provider writes until a dedicated target or verified partition is restored.
3. Load the configured persistence-provider Skill. When it exposes a read-only
   aggregate health or readiness snapshot that covers the required route,
   binding, isolation, capability, and integrity obligations, inspect that
   snapshot once. Do not repeat equivalent focused status reads; expand only
   for a reported gap, an uncovered claim, or an exact guard required by an
   authorized mutation. For a project-local ledger, read its bounded
   current-state, queue, decision, risk, and evidence records. When project
   policy requires that provider and an accepted stage baseline exists but no
   relevant provider state exists, reconstruct the minimum supported state
   from the baseline with explicit source and as-of provenance, then read it
   back. Do not fabricate historical events or treat stale baseline text as
   current fact.
4. Recover a bounded current-state packet once, identified by the provider's
   current revision, head, cursor, or equivalent snapshot identity: current
   objective, relevant scope and constraints, present status, prioritized next
   work, pending decisions, any active task or stage decision-authority
   envelope, open risks, and acceptance evidence needed for this task.
5. Read only the task-relevant authority documents named by the entry, then
   compare important claims with current artifacts or runtime evidence.

Do not scan all project history at every start. Do not initialize a provider,
bind an ambient workspace, or repair continuity records unless that mutation is
within the current authority. If required continuity is cleanly missing,
continue only with a slice that remains safe without it and report the degraded
boundary.

A cleanly inactive route or missing capability is a degraded authority
boundary: preserve the exact missing operation, continue independent work when
safe, and do not activate it implicitly. Stale, malformed, ambiguous, or
integrity-failed control state is blocked for the affected provider path: fail
closed on dependent claims and mutations while safe unrelated work continues.
Use the provider Skill for focused diagnosis or separately authorized repair;
neither state expands authority.

## Keep The Task Contract Independent

A project entry is not a Plan, and project enrollment never creates a
mega-Plan. Use `work-governance:plan-governance` only when the current task or
delivery route independently benefits from a Plan. A small task inside an
enrolled project may remain No-Plan while still honoring startup recovery and
closeout reconciliation.

During execution, write evidenced state changes to the selected provider at
narrow semantic checkpoints instead of collecting all state until closeout.
Coalesce mechanical operations that do not change meaning. Put accepted,
long-lived architecture or contract changes in project authority; keep
temporary execution state and pending choices in the selected provider. Do not
roll the stage baseline forward during ordinary in-stage work.

Semantic events include new evidence, a failed material assumption, validation
failure, milestone completion, scope or relevant external-state change, and a
receipt mismatch. Under explicit decision delegation, record only material
autonomous corrections such as a changed route, priority, Plan, validation
boundary, or delivery claim. The user regains the confirmation gate when the
delegation expires, is narrowed or revoked, or the correction would exceed its
scope, environment, decision classes, or action permissions.

Reuse the recovered provider snapshot until an explicit invalidation trigger:
logical owner or route changes; provider revision, head, or cursor advances;
task scope changes; an external writer is observed; relevant evidence identity
changes; status becomes unknown; or a mutation receipt and exact target
readback disagree. After a provider mutation, a precise typed receipt plus
direct readback of the changed target updates the packet without an immediate
broad recovery read. On mismatch, reopen the affected target or dependency
first; broaden recovery only when the changed head, route, scope, or evidence
cannot be bounded.

At a stage boundary, do not turn an unconfirmed material solution assumption
into the next stage's definition merely to make the work concrete. An approach
or feasibility boundary that can change the outcome, architecture, data,
authority, cost, risk, or acceptance must be routed through
`work-governance:goal-discovery` and `work-governance:plan-governance`. Carry it
as a pending decision in the selected state provider until confirmed. Bounded
feasibility checks may support a recommendation, but they do not select the
path.

## Reconcile Before Closeout

After validating the work and before making the final continuity claim:

1. Compare the recovered packet with the verified end state.
2. Reconcile material changes to progress and status, remaining work and
   priority, material decisions and reasons, open risks and boundary cases, and
   acceptance evidence in the single state provider. Include any material
   delegated decision or changed decision-authority envelope; omit routine
   choices and unchanged review outcomes.
3. Reconcile every durable operation created by the current task through the
   provider's bounded delivery and exact readback when existing authority
   already covers that operation and target. The responsible task, not the
   user, monitors ordinary same-target completion. A need for new authority,
   target or owner change, semantic-currentness judgment, or another guarded
   provider mutation remains an explicit boundary.
4. If a historical open inventory becomes relevant, classify each candidate's
   present semantic value and the effect of acting now before any recovery.
   Do not batch-replay it or treat an open-looking control-plane status as
   evidence that old content is still current. Distinguish already-delivered
   operations, deterministic failures, superseded undelivered intent, and
   immutable target changes, then act only within the current task's scope and
   authority.
5. Update project-native authority only when the task actually changed it and
   the change is within scope. Update a stage baseline only when the declared
   stage is complete and accepted; build it from the verified artifacts,
   conversation, and provider state, then link the resulting snapshot back to
   the provider instead of maintaining two live copies.
6. Read back or otherwise verify the exact state changes using the provider's
   own mechanics. Prefer the mutation receipt and exact target readback; do not
   reload unrelated provider state merely to reconfirm an unchanged snapshot.
7. Report the technical result and the durable continuity result separately.

No material delta means no state churn. If persistence or readback fails,
retain one bounded pending-reconciliation packet in the handoff, identify the
exact failed boundary, and state that durable handoff is incomplete. Do not
claim project continuity merely because implementation or tests succeeded, and
do not claim implementation success merely because a record was updated.
