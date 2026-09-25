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

## Recover At Task Start

For enrolled work, do this before material implementation. If work becomes
eligible during a task, do it when the continuity need becomes clear:

1. Identify the logical project from explicit project authority, the primary
   artifact, and the relevant repository roots. Do not let an ambient working
   directory or shared backend choose it implicitly.
2. Read the project entry first and verify that its authority locations and
   single state-provider locator still resolve.
3. Load the configured persistence-provider Skill. For a project-local ledger,
   read its bounded current-state, queue, decision, risk, and evidence records.
4. Recover a bounded current-state packet: current objective, relevant scope
   and constraints, present status, prioritized next work, pending decisions,
   open risks, and acceptance evidence needed for this task.
5. Read only the task-relevant authority documents named by the entry, then
   compare important claims with current artifacts or runtime evidence.

Do not scan all project history at every start. Do not initialize a provider,
bind an ambient workspace, or repair continuity records unless that mutation is
within the current authority. If continuity is missing or stale, continue only
with a slice that remains safe without it and report the degraded boundary.

## Keep The Task Contract Independent

A project entry is not a Plan, and project enrollment never creates a
mega-Plan. Use `work-governance:plan-governance` only when the current task or
delivery route independently benefits from a Plan. A small task inside an
enrolled project may remain No-Plan while still honoring startup recovery and
closeout reconciliation.

During execution, keep material deltas available for closeout. Put accepted,
long-lived architecture or contract changes in project authority; keep
temporary execution state and pending choices in the selected provider.

## Reconcile Before Closeout

After validating the work and before making the final continuity claim:

1. Compare the recovered packet with the verified end state.
2. Reconcile material changes to progress and status, remaining work and
   priority, material decisions and reasons, open risks and boundary cases, and
   acceptance evidence in the single state provider.
3. Update project-native authority only when the task actually changed it and
   the change is within scope; link provider state to that authority instead of
   copying it.
4. Read back or otherwise verify the exact state changes using the provider's
   own mechanics.
5. Report the technical result and the durable continuity result separately.

No material delta means no state churn. If persistence or readback fails,
retain one bounded pending-reconciliation packet in the handoff, identify the
exact failed boundary, and state that durable handoff is incomplete. Do not
claim project continuity merely because implementation or tests succeeded, and
do not claim implementation success merely because a record was updated.
