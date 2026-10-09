---
name: problem-discovery
description: Use when designing or reviewing a test, validation, or evidence strategy to expose important defects early across observation environments, state transitions, integrations, side effects, and the validator itself. Do not use merely to run an already-defined routine test suite.
---

# Problem Discovery

Design the smallest evidence portfolio that can expose important failures early.
This Skill owns what to challenge, where to observe it, and how to know the
challenge worked. It does not own product requirements, implementation, action
authority, persistence, or the decision to use an independent reviewer.

## Build A Lightweight Behavior And Risk Model

Do not assume the important claims have already been written down. First map
only the parts relevant to the current change or risk:

- actors, current and replacement owners, and trust boundaries;
- states, transitions, terminal conditions, and time or ordering assumptions;
- data, assets, provenance, and compatibility windows;
- actions, externally visible effects, and irreversible boundaries;
- component handoffs, dependencies, protocols, and deployment bindings; and
- startup, upgrade, cancellation, failure, recovery, and retirement paths.

Derive explicit and latent claims from the user's outcome, current project
authority, the model above, changed seams, prior failures, and high-consequence
boundaries. Look for negative obligations such as what must never happen, not
only expected success.

If the expected behavior, priority between states, ownership, or acceptance
semantics is missing or contradictory, record a contract gap and route it to
`work-governance:goal-discovery` or the current decision owner. Test design
must not invent a material product rule merely to obtain an oracle.

Break overloaded qualities into separately observable obligations. For
example, idempotency can require distinct proof for admission or deduplication,
state convergence, downstream effect multiplicity, and an unknown outcome
after a request may already have been sent.

## Turn The Model Into Falsifiable Claims

Identify what actually changed: behavior, data, state ownership, ordering,
recovery, authorization, protocol, dependency, deployment binding, or
acceptance logic. Reuse earlier evidence only while the claim, implementation
basis, environment, and observation boundary that made it applicable remain
unchanged.

For each material claim, define:

- the invariant or outcome that must hold;
- the smallest stimulus that could falsify it;
- the earliest observation environment where that stimulus can be controlled
  and the real effect can be observed;
- the observation point and oracle;
- an adjacent valid control that must continue to work; and
- the residual conditions the check still cannot establish.

Cover correct success, safe rejection, legitimate recovery, and diagnosability
when each is part of the contract. A test name, executed line, final status, or
large sample count is not a substitute for the semantic assertion.

## Choose The Earliest Trustworthy Observation Environment

Observation environments provide different evidence; a later or broader
environment does not automatically replace an earlier, more controllable one.
They are orthogonal to risk dimensions such as persistence, concurrency,
ownership, recovery, authorization, and side effects. Concurrency is not a
later stage: a controlled barrier and clock may expose it in isolated execution,
while a local composed system is needed only when actual storage or transport
semantics are part of the claim.

| Observation environment | Prefer to discover and observe |
| --- | --- |
| Design and static contract | Missing states, contradictory obligations, unsafe ownership, irreversible-effect assumptions, schema and compatibility gaps |
| Isolated deterministic execution | Boundary values, state transitions, ordering, stale ownership, exact calls and effects, positive and negative controls using controlled time, scheduling, storage, or transport |
| Local composed system | Actual serialization, transport, identity, roles, persistence, networking, dependency wiring, and multi-step or multi-round flow |
| Authorized real dependency | Provider- or environment-specific behavior with the smallest useful probe, explicit budget, and stop conditions |
| Acceptance and operation | Business truth, artifact and input binding, drift, recovery evidence, observability, and the accuracy of the acceptance method itself |

Choose the earliest environment that can produce trustworthy evidence for the
claim and affected risk dimensions. Add a broader environment only for a
binding, composed behavior, or environmental or operational semantic that the
earlier one cannot represent. Do not force every task through every
environment.

## Expand The Discovery Space Deliberately

Consider dimensions that can change the result:

- input shape, boundary values, data provenance, producer and consumer version
  skew, unknown fields, removed or redefined semantics, and stored raw versus
  normalized representations;
- initial and later attempts, success, failure, unknown, and late arrival;
- current, stale, concurrent, and replacement owners, including persistence
  and takeover effects;
- complete, partial, duplicated, omitted, reordered, and mixed-validity work;
- stable, compatible, and incompatible dependency or contract changes;
- no control, cancellation, revocation, timeout, retry, and recovery;
- authorization, quota, resource, and irreversible-effect boundaries;
- protocol, transport, persistence, process, role, network, and external-service
  composition; and
- oracle quality, evidence binding, and diagnostic visibility.

Do not multiply every dimension into an exhaustive Cartesian product. Use
representative workload or input distributions for broad behavior, and a
contract-driven state matrix for rare interleavings; neither replaces the
other. Use pairwise or sampled coverage for lower-risk interactions, but name
and test combinations that threaten money, permissions, externally visible
effects, or durable correctness.

Select critical sequences deliberately. Start with the shortest paths that
cross terminal, irreversible, ownership-transfer, or recovery boundaries.
Cover each high-risk transition, then add named two- or three-event
interactions where order changes the expected outcome. Do not rely on generic
pairwise coverage for those sequences.

## Construct Falsifiers And Controls

Prefer the smallest counterexample that separates the claim from plausible
alternatives. Change one decisive condition when testing the oracle. Use
controlled clocks, barriers, deterministic transports, and explicit fault
points for timing and ordering claims instead of hoping repetition or sleep
will produce the state.

Pair a negative case with the nearest valid case. A mixed-validity batch should
not only be rejected correctly; the all-valid batch and any promised legal
partial recovery must remain valid. A stale writer should be fenced without
destroying the replacement owner's state. A repaired recovery path should also
be checked against cancellation, revocation, or a later round when those
interactions are affected.

Preserve the original falsifying input and result before correcting the
implementation or checker. Re-run that evidence after the correction, then
check the adjacent valid behavior.

## Observe Effects, Not Only Returned Errors

For a rejection or unknown result, inspect relevant effects before and after
the reported outcome: physical requests, handler calls, durable writes,
actions, events, budget or quota use, and external changes. Assert zero effect
only when the contract can decide the rejection before that effect; do not
promise rollback of an unpredictable downstream failure.

Keep unknown distinct from failure and success. Missing a provider receipt does
not prove that no request was sent, and a visible error does not prove that no
earlier side effect occurred. Prepare bounded boundary evidence and correlation
identifiers that distinguish guard, connection, request write, response,
terminal, persistence, and reconciliation boundaries without recording
secrets or sensitive payloads.

## Challenge The Oracle

The acceptance method is another system under test. Give it valid controls and
single-variable counterexamples that a weak checker might accept:

- byte or file integrity with wrong business facts, input binding, or
  references;
- authentication that is cryptographically valid but wrong for the intended
  audience, tenant, role, or action;
- a structurally valid envelope with missing or contradictory semantics;
- duplicate, conflicting, or post-terminal events; and
- two implementations that agree because they share the same faulty source.

Separate build, mechanism, scenario, suite, and campaign claims. A compiled
target, non-skipped test, or green helper proves only its own boundary. When an
independent challenge adds material confidence, load
`work-governance:independent-validation` and give it the contract and raw
artifacts rather than the intended answer.

## Learn From Discoveries Without Inflating Them

Classify each distinct finding before generalizing:

- a latent defect that existed before the current change;
- a defect introduced by a new integration or environment boundary;
- a repair-derived regression or newly created obligation;
- a faulty test, oracle, fixture, or evidence extractor;
- an environment or preparation problem; or
- an observed anomaly whose cause remains unresolved.

Detection and diagnosis are separate claims. Several progress updates or fixes
for one cause are not several independent defects. Record the earliest
observation environment where the issue could have been triggered, the
environment where it was actually found, the falsifier, the oracle, the
correction, and the remaining evidence boundary. Use that comparison to improve
the next design, not to manufacture a universal rule from one incident.

## Scale And Stop By Risk

Prioritize high-consequence claims and newly changed boundaries. Reuse
still-applicable evidence, and expand validation only when a change, failure,
unresolved risk, or new binding invalidates it. Deterministic and local
evidence should precede expensive or external probes, but they do not replace
the real dependency behavior they cannot represent.

Real services, paid calls, production-like environments, credentials, and data
effects remain within their existing authorization, budget, and stop
conditions. Before an external probe, name the exact target and uniquely
unresolved claim, the maximum effect or cost per probe, the total budget, and
the stopping response to the first unexplained result or unexpected effect.
Stop when no remaining claim is unique to that environment. More tests, calls,
retries, Agents, or progress messages are not evidence of better discovery by
themselves.

A compact discovery design can be expressed as:

| Claim | Risk dimensions | Earliest useful observation environment | Falsifier | Observation and oracle | Valid control | Residual scope |
| --- | --- | --- | --- | --- | --- | --- |

The design is complete enough when every material explicit or derived
high-risk claim has a trustworthy challenge in the earliest useful
environment, broader environments cover only the bindings, composed behavior,
or environmental and operational semantics they uniquely expose, and the
remaining uncertainty is visible rather than silently converted into success.
