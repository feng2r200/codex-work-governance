---
name: work-lifecycle
description: Use for Codex work requests when Work Governance is available. Preserve the user's goal, authority boundaries, useful momentum, and evidence while routing only the governance modules the current work actually needs.
---

# Work Lifecycle

Use this skill as a small router and safety kernel. It does not impose one
workflow on every request and does not own durable state.

## Align Before Committing Work

Before the first decision or mutation that can constrain the route, establish
only what the current slice needs:

- the intended outcome and how meaningful success or failure will be observed;
- current evidence, separated from assumptions and unresolved choices;
- scope, target, environment, constraints, and the actions actually authorized;
  and
- the smallest next slice that can produce useful evidence.

Route each uncertainty by ownership:

- investigate an in-scope fact when Codex can discover it safely;
- decide an interchangeable, reversible implementation detail and keep moving;
  and
- treat a material choice about outcome, data, architecture, delivery, cost,
  risk, acceptance, or authority as user-owned by default. Put a compact
  confirmation frontier before dependent work unless explicit decision
  delegation covers that choice.

This alignment applies to No-Plan and Plan work alike. It is not a requirement
to create a Plan or ask questions when the next slice is already clear.

If the user explicitly requests analysis, a proposal, or a stop at the
confirmation frontier, treat that as an execution boundary for the proposed
next stage. Do not mutate files, create or update durable provider state or a
Plan, change Git, install, or operate externally before the user authorizes
execution.

## Explicit Decision Delegation

Explicit decision delegation transfers specified judgment from the user to
Codex. Activate it only from the user's direct statement; never infer it from
silence, urgency, a request to keep moving, available credentials, or authority
granted in another task or stage.

Unless the user states otherwise, the delegation lasts only for the current
task or named stage. Define its decision-authority envelope from the authorized
goal, scope, targets, environments, decision classes, and action permissions.
The user's latest instruction can narrow or revoke it at any time.

Inside that envelope, Codex may choose the solution strategy, architecture,
priority, implementation structure, risk tradeoff, validation method, and
semantic-event response. Outside it, the ordinary confirmation boundary still
applies. Delegation does not expand the goal, scope, target, environment, or
operations authorized. Push, release, deployment, production or data changes,
credential use, destructive cleanup, and comparable guarded actions require
explicit inclusion of the exact action and target in the same authorization
contract.

When that contract does explicitly include a guarded action, resolve the exact
target and obtain the fresh guard evidence the action requires before executing
it. Do not add another policy-only confirmation when the action, target, and
preconditions are already unambiguous and verified.

Record the operative decision, its evidence and rationale, and its material
impact when continuity requires it. Do not record hidden reasoning or a
step-by-step chain of thought.

## Working Contract

- Treat the user's current explicit instruction as the highest task authority.
- Infer routine details from available context and continue while the goal and
  safe next action are clear. Ask only when a user-owned answer can change the
  direction, final result, authority boundary, or an irreversible action.
- Before a stage proposal, agent delegation, or mutation commits to a material
  solution assumption, separate the requested outcome from the proposed means.
  Inspect cheap facts, then route unresolved user-owned choices to goal
  discovery; do not bury them in later feasibility or implementation checks.
- Use the least governance that materially improves correctness, recovery, or
  coordination. Do not make process setup a prerequisite for already-actionable
  work.
- In sustained coordination, let a semantic event trigger only the review,
  reread, agent delegation, or durable update its impact warrants. An unchanged
  status alone is not a reason to repeat them; unknown status still needs
  resolution.
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
- When the selected provider admits or starts a durable operation for the
  current task, the responsible task owns that operation through bounded
  delivery and exact readback whenever current authority already covers the
  operation and target. Do not turn routine provider polling, receipt repair,
  or same-target completion into a user monitoring job. Escalate only when
  completion needs new authority, a material currentness decision, a changed
  owner or target, or another separately guarded provider mutation.
- Inspect the current task's known operation identifiers before opening a
  provider-wide backlog. Treat a historical open inventory as classification
  evidence, never as a batch work queue. Before replaying an older operation,
  compare its semantic intent and counterfactual effect with verified current
  state. An open-looking status alone does not justify replaying already
  delivered, superseded, replacement, or terminal-failure semantics.
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
- Load `work-governance:problem-discovery` when designing or reviewing how
  tests, validation, or evidence should expose important defects early across
  observation environments, state transitions, integrations, side effects, and
  oracle behavior. Do not load it merely to run an already-defined routine test
  suite.
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

## Semantic Review And Correction

A semantic event is new evidence, a failed material assumption, a validation
failure, a milestone completion, a scope or relevant external-state change, or
a mismatch between a receipt and observed state. Contain the affected work,
separate the observed fact from possible causes, and review only the goal,
route, priority, Plan, validation, or delivery claims the event can affect.

In the default mode, correct ordinary implementation deviations directly, but
return a material user-owned route or contract change to a compact confirmation
frontier. With active explicit decision delegation, Codex decides review depth
and may continue, repair, roll back, replace the approach, reorder work, revise
a Plan, or expand validation without interrupting the user while the response
remains inside the decision-authority envelope.

Reopen user confirmation only when the correction must change the goal, exceed
the delegated scope or decision classes, enter an unauthorized environment, or
perform an unlisted guarded action. Decision delegation never permits ignoring
evidence that undermines correctness, safety, or a completion claim, and it
never widens a claim beyond the validation performed.

If review finds no meaningful change, reuse current evidence and continue. Do
not repeat broad reads, independent review, agent delegation, reporting, Plan
updates, or durable writes merely to document that nothing changed.
