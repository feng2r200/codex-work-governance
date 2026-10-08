---
name: goal-discovery
description: Use when a request starts from a proposed solution, vague idea, or incomplete requirement and unresolved product intent, data strategy, delivery form, material solution or feasibility strategy, acceptance, or user-owned tradeoff could materially change the right path.
---

# Goal Discovery

Discover enough of the real goal to choose a sound path without turning clear
work into a requirements ceremony.

## Build The Smallest Useful Model

Establish, to the degree the decision needs:

- the user-visible outcome and why it matters;
- the current state and evidence, including what is merely assumed;
- constraints, non-goals, and authority boundaries;
- how success and important failure would be observed;
- material solution alternatives and feasibility evidence when they can change
  the outcome, boundary, cost, risk, or acceptance; and
- which unknowns are agent-discoverable and which are genuine user choices.

Investigate cheap, in-scope facts before asking the user. If a proposed
technical solution already determines a correct, reversible path and the goal
is clear, proceed.

## Establish Decision Authority

Material choices are user-owned by default. Explicit decision delegation lets
Codex own only the choices inside a stated task or stage envelope. It must come
from the user's direct instruction and must not be inferred from silence,
urgency, available credentials, or authority from another task or stage.

When delegation is active, compare the same material effects required for a
recommendation, choose the evidence-backed route, record the decision and its
impact when continuity requires it, and proceed. Reopen the frontier only if
the choice would change the goal, exceed the delegated scope or decision
classes, enter an unauthorized environment, or require an unlisted guarded
action. A later user instruction may narrow or revoke the delegation.

## Separate Outcome From Proposed Means

When the same outcome can be delivered through materially different
approaches, treat their selection as a decision rather than a hidden
implementation default.

Before a stage or implementation contract fixes one path:

1. Preserve any explicit user choice; do not replace it with the easiest
   or most visible option.
2. Inspect cheap, in-scope evidence about prerequisites, constraints, and
   feasibility.
3. Compare only material effects: outcome, architecture, data handling, cost,
   operational and authority boundaries, reversibility, risk, and acceptance
   evidence.
4. If the choice remains unresolved and those effects matter, route it through
   its current owner. In the default mode, keep it as a user-owned decision and
   place confirmation before the first design, agent delegation, or mutation
   that commits to one path. Under explicit decision delegation, select and
   proceed when the choice is inside the active envelope. Continue work that is
   genuinely independent of any still-gated choice.

Do not infer a material choice from labels, the most visible artifact, the
incumbent environment, or the easiest path to start. Do not postpone an
unresolved direction until one assumed path fails a prerequisite or feasibility
check.

Do not open this frontier for an ordinary, reversible implementation detail
whose alternatives are interchangeable for the current slice.

## Decision Frontier

Use a compact frontier only when one unresolved choice would change the product
goal, data strategy, delivery form, material solution strategy, feasibility
boundary, acceptance, cost, risk, data exposure, or irreversible outcome.
State:

- the decision;
- the viable paths and their material effects;
- the evidence-backed recommendation;
- the current decision owner and any active delegation boundary; and
- what work is actually blocked.

Do not ask for preferences that can be deferred without affecting the current
slice. Record non-blocking ideas or risks for later reporting instead of
interrupting execution.

Representative routes:

| Current evidence | Expected route |
| --- | --- |
| The user explicitly selected a material approach | Preserve it and verify only the prerequisites needed for the current slice |
| The outcome is clear, but materially different approaches remain viable | Compare their effects and ask the direction question before dependent work commits to one |
| The user explicitly delegated this material choice for the current task or stage | Compare the material effects, choose the evidence-backed route, record its impact, and proceed |
| Evidence invalidates a confirmed approach | Contain the affected work and reopen the choice only when the replacement changes a user-owned boundary |
| Evidence invalidates a delegated approach but the replacement remains inside the envelope | Reassess and choose the correction without automatically interrupting the user |
| The choice is an interchangeable, reversible implementation detail | Proceed without a confirmation gate |

## Finish Discovery

Discovery is complete when the goal, any material solution strategy, the safe
next action, and the evidence needed to judge success are clear enough for the
current scope. A strategy may remain open only when the next slice is genuinely
independent and its confirmation gate is explicit. Hand any need for a durable
multi-stage Plan to `work-governance:plan-governance`; otherwise return directly
to execution.
