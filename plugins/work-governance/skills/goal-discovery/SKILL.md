---
name: goal-discovery
description: Use when a request starts from a proposed solution, vague idea, or incomplete requirement and unresolved product intent, data strategy, delivery form, acceptance, or user-owned tradeoff could materially change the right path.
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
- which unknowns are agent-discoverable and which are genuine user choices.

Investigate cheap, in-scope facts before asking the user. If a proposed
technical solution already determines a correct, reversible path and the goal
is clear, proceed.

## Decision Frontier

Use a compact frontier only when one unresolved choice would change the product
goal, data strategy, delivery form, acceptance boundary, cost, or irreversible
outcome. State:

- the decision;
- the viable paths and their material effects;
- the evidence-backed recommendation;
- what work is actually blocked.

Do not ask for preferences that can be deferred without affecting the current
slice. Record non-blocking ideas or risks for later reporting instead of
interrupting execution.

## Finish Discovery

Discovery is complete when the goal, safe next action, and evidence needed to
judge success are clear enough for the current scope. Hand any need for a
durable multi-stage Plan to `work-governance:plan-governance`; otherwise return
directly to execution.
