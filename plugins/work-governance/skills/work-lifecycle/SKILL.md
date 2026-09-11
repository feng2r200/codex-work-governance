---
name: work-lifecycle
description: Use for Codex work requests when Work Governance is available. Preserve the user's goal, authority boundaries, useful momentum, and evidence while routing only the governance modules the current work actually needs.
---

# Work Lifecycle

Use this skill as a small router and safety kernel. It does not impose one
workflow on every request and does not own durable state.

## Working Contract

- Treat the user's current explicit instruction as the highest task authority.
- Infer routine details from available context and continue while the goal and
  safe next action are clear. Ask only when a user-owned answer can change the
  direction, final result, authority boundary, or an irreversible action.
- Use the least governance that materially improves correctness, recovery, or
  coordination. Do not make process setup a prerequisite for already-actionable
  work.
- Keep goal, scope, evidence, and authority distinct. A tool record, old plan,
  memory, test result, or reviewer opinion is evidence; none silently expands
  the user's authority or replaces current project truth.
- Match validation to the claim and risk. Completion, activation, deployment,
  data change, and other consequential claims require fresh evidence for the
  exact boundary claimed.
- Preserve unrelated work. Do not overwrite, delete, publish, deploy, or make
  other externally consequential changes without authority for the exact
  target.
- Continue through useful non-blocking discoveries. Surface them in progress or
  completion reporting, and interrupt only when ignoring them would change the
  direction or final result, cross authority, or risk irreversible harm.
- Add a compatibility layer only after evidence establishes its necessity.
  Make the compatibility decision and its cost visible to the user.

## Route Only When Needed

- Load `work-governance:goal-discovery` when the stated solution may hide an
  unresolved goal, data strategy, delivery form, or acceptance choice.
- Load `work-governance:plan-governance` when deciding whether a Plan adds
  value, admitting one, or materially revising one.
- Load `work-governance:subagent-governance` before multi-agent delegation or
  when diagnosing delegation overhead, ownership, or handoff quality.
- Load `work-governance:git-change-governance` for branch, worktree, staging,
  commit, push, or Git cleanup decisions.
- Load `work-governance:independent-validation` only when a separate challenge
  adds meaningful confidence.
- Load `work-governance:project-truth-governance` when deciding whether and
  where a finding should become durable project authority.
- Load `work-governance:work-reporting` for sustained progress reporting,
  phase handoff, or a full completion report.
- Load scene- or tool-specific Skills only when their actual scenario or tool
  is in scope. Their operating details do not belong in this lifecycle router.

## Deviation

If evidence shows the current route no longer serves the goal, contain only the
affected work, distinguish the observed failure from its possible causes, and
choose the smallest causal correction. Return to the user only for a material
change to an agreed goal or contract, data strategy, delivery form, authority,
or irreversible outcome. Ordinary implementation structure changes remain an
execution decision.
