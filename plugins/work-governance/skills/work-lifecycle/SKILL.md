---
name: work-lifecycle
description: Use for any work request when Work Governance is available. Preserve the user's goal, authority boundaries, useful momentum, and evidence while routing only the governance modules the current work actually needs.
---

# Work Lifecycle

Use this skill as a small router. It decides which governance module the
current work actually needs. It does not impose one workflow on every request,
does not own durable state, and does not hold the execution constraints
themselves.

## Align Before Committing Work

Before the first decision or mutation that can constrain the route, establish
only what the current slice needs:

- the intended outcome and how meaningful success or failure will be observed;
- current evidence, separated from assumptions and unresolved choices;
- scope, target, environment, constraints, and the actions actually authorized;
  and
- the smallest next slice that can produce useful evidence.

Route each uncertainty by ownership:

- investigate an in-scope fact when the agent can discover it safely;
- decide an interchangeable, reversible implementation detail and keep moving;
  and
- treat a material choice about outcome, data, architecture, delivery, cost,
  risk, acceptance, or authority as user-owned by default. Put a compact
  confirmation frontier before dependent work unless explicit decision
  delegation covers that choice.

This alignment applies to No-Plan and Plan work alike. It is not a requirement
to create a Plan or ask questions when the next slice is already clear.

## Route Only When Needed

- Load `work-governance:execution-kernel` before any decision, proposal, or
  mutation that can constrain the route. It owns the refutable-route gate,
  explicit decision delegation, the working contract, final-outcome
  continuity, and semantic review and correction. These constraints are not
  scoped to a scenario, so do not wait for one to match before loading it.
- Load `work-governance:goal-discovery` when the stated solution may hide an
  unresolved goal, data strategy, delivery form, material solution strategy,
  or acceptance choice.
- Load `work-governance:plan-governance` when deciding whether a Plan adds
  value, admitting one, or materially revising one.
- Load `work-governance:git-change-governance` for branch, worktree, staging,
  commit, push, or Git cleanup decisions.
- Load `work-governance:code-intelligence` when source-code work needs
  structural symbol, call-path, impact, affected-test, or cross-layer
  understanding, including safe per-checkout CodeGraph readiness. Keep literal
  text, prose, logs, and configuration on native inspection routes.
- Load `work-governance:causal-attribution` when an observed symptom in a
  running system needs a confirmed cause before anything is changed, including
  cost or performance blowups, a capability that never activates, a channel
  that appears to carry nothing, or a suspicion that one component is to blame.
- Load `work-governance:problem-discovery` when designing or reviewing how
  tests, validation, or evidence should expose important defects early across
  observation environments, state transitions, integrations, side effects, and
  oracle behavior. Do not load it merely to run an already-defined routine test
  suite.
- Load `work-governance:frontend-governance` for rendered frontend work whose
  reference, required controls, product copy, or interaction acceptance needs
  an explicit delivery contract. Keep its implementation and browser mechanics
  with the relevant project and tool Skills.
- Load `work-governance:independent-validation` only when a separate challenge
  adds meaningful confidence, including when a proposed route's own refutation
  was designed by the same party that proposed it.
- Load `work-governance:project-development-governance` when work continues
  across tasks, sessions, or phases and needs an entry contract, bounded
  recovery, live-state reconciliation, or a stage baseline. A resumed session,
  a compacted context, or a second phase of the same goal is enough; do not
  wait for a separate enrollment step.
- Load `work-governance:project-truth-governance` when a finding would change
  how later work decides, including a corrected assumption, a measured
  constraint, or a rejected route. Deciding that it does not belong in durable
  authority is also this module's call.
- Load `work-governance:work-reporting` for sustained progress reporting,
  phase handoff, or a full completion report.
- Load `work-governance:resource-observation` when work consumes or is about
  to consume a meaningful amount of a measurable resource, when a restriction
  on one is proposed, or when an efficiency change is being scoped. Report what
  authorized work cost here. Send only an anomalous total that needs a
  confirmed driver before any change to causal attribution.
- Load `work-governance:project-archive-curation` when material from finished
  work accumulates, duplicates existing records, or has outlived its purpose,
  and its retention, consolidation, retirement, or location must be decided.
- Load scene- or tool-specific Skills only when their actual scenario or tool
  is in scope. Their operating details do not belong in this lifecycle router.
