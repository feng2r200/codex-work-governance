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
- Before a stage proposal, delegation, or mutation commits to a material
  solution assumption, separate the requested outcome from the proposed means.
  Inspect cheap facts, then route unresolved user-owned choices to goal
  discovery; do not bury them in later feasibility or implementation checks.
- Use the least governance that materially improves correctness, recovery, or
  coordination. Do not make process setup a prerequisite for already-actionable
  work.
- In sustained coordination, let new evidence or a changed obligation trigger
  another full read, review, delegation, or durable update. An unchanged status
  alone is not a reason to repeat them; unknown status still needs resolution.
- Reuse one verified, bounded provider snapshot while its logical owner,
  provider revision or head, task scope, and relevant evidence identity remain
  unchanged. Invalidate only the affected path after an owner or route change,
  provider advance, external write, scope change, evidence change, uncertain
  status, or mutation/readback mismatch. A precise mutation receipt plus exact
  target readback satisfies that checkpoint; do not immediately repeat a broad
  recovery read when they agree.
- When a provider offers one read-only aggregate health or readiness snapshot
  that covers the required control-plane obligations, prefer it over repeating
  equivalent focused status reads. Expand only when the aggregate reports a
  gap, does not cover the claim being made, or an authorized mutation requires
  an exact fresh guard.
- Treat a cleanly inactive or missing capability as a degraded authority
  boundary, not proof that the provider is invalid. Treat stale, malformed,
  ambiguous, or integrity-failed control state as blocked for the affected
  path. Neither classification authorizes activation, repair, or another
  control-plane mutation.
- When a higher-priority policy requires a durable state provider, select that
  provider at task start and keep its participation independent from Plan
  admission, documentation cadence, and the ambient working directory. Route
  storage mechanics to the provider's own Skill.
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
  unresolved goal, data strategy, delivery form, material solution strategy,
  or acceptance choice.
- Load `work-governance:plan-governance` when deciding whether a Plan adds
  value, admitting one, or materially revising one.
- Load `work-governance:subagent-governance` before multi-agent delegation or
  when diagnosing delegation overhead, ownership, or handoff quality.
- Load `work-governance:git-change-governance` for branch, worktree, staging,
  commit, push, or Git cleanup decisions.
- Load `work-governance:code-intelligence` when source-code work needs
  structural symbol, call-path, impact, affected-test, or cross-layer
  understanding, including safe per-checkout CodeGraph readiness. Keep literal
  text, prose, logs, and configuration on native inspection routes.
- Load `work-governance:independent-validation` only when a separate challenge
  adds meaningful confidence.
- Load `work-governance:project-development-governance` when an explicitly
  enrolled project or ongoing development across tasks, sessions, or phases
  needs a durable entry contract, bounded recovery, live-state reconciliation,
  or stage-baseline cadence.
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
solution strategy, feasibility boundary, or irreversible outcome. Ordinary
implementation structure changes remain an execution decision.
