---
name: independent-validation
description: Use when a plan, artifact, causal diagnosis, evidence set, activation, or completion claim has enough risk or self-certification uncertainty that an independent challenge would materially increase confidence.
---

# Independent Validation

Validation challenges a claim; it does not own the parent goal, plan,
authorization, persistence records, or final wording.

## Use It Selectively

Independent review is useful when:

- consequential, destructive, remote, production, data, security, migration,
  activation, or rollback work is being claimed complete;
- the implementer is also the only judge of a subtle contract or causal claim;
- evidence is indirect, degraded, stale, sampled, or easy to overstate;
- a test strategy or state transition can pass while the user goal still fails;
- the user or governing task explicitly requests independent review.

Do not impose independent review on a routine reversible edit when a direct,
meaningful check proves the claim. Do not repeat broader tests after relevant
checks pass unless new edits, failures, or unresolved risks justify it.

## Keep The Proof Applicable

Tie a validation result to its claim, input revision, evidence, and scope.
Reuse it while that basis remains applicable; a changed input requires checking
the affected obligations, not automatically restarting every review.

Choose the smallest observation that proves the claim. Source text containing a
read or write does not prove that execution reached it, and a successful
synthetic probe does not prove actual adoption or task quality. Use an isolated
behavioral probe or direct observation when static inspection cannot establish
the behavior; preserve the project's actual acceptance criteria.

Separate a product failure from a faulty acceptance method. Preserve the exact
counterexample before another fix. When the same cause recurs or the chosen
method is repeatedly falsified, reassess its fitness and the agreed resource
budget before expanding it. Pause only the affected claim or path, keep safe
independent work moving, and return material changes to the parent decision.
A demonstrated invalid claim needs correction immediately; a retry budget is
an upper bound, not permission to keep relying on disproven evidence.

## Challenge Modes

- **Plan challenge:** missing obligations, dependencies, gates, stop conditions,
  and acceptance evidence.
- **Artifact review:** diff, generated artifact, schema, UI, or data result
  against the actual contract.
- **Evidence audit:** whether tests, logs, samples, screenshots, or records prove
  the exact stated boundary.
- **Causal challenge:** whether a diagnosis distinguishes plausible causes and
  whether the correction removes the cause instead of hiding the symptom.
- **Rollback review:** whether affected artifacts are known and containment,
  compensation, or rollback is safe.

## Independence And Output

Prefer a separate context only when independence adds value. Give the reviewer
the goal, contract, and raw artifacts rather than the implementer's intended
answer. Treat its result as evidence for the owning agent to judge.

Lead with actionable findings ordered by consequence. For each, identify the
evidence, affected obligation, and required correction or missing validation.
If no issue is found, state what was examined and the residual risk; absence of
a finding is not proof outside the reviewed boundary.
