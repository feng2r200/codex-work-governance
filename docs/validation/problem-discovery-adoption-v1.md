# Problem Discovery Skill Adoption Evidence

## Purpose And Boundary

This record explains why problem discovery is a separate Work Governance
capability, how one project retrospective was generalized without becoming a
fixed universal checklist, and what validation the source candidate has
received.

The normative policy is
`plugins/work-governance/skills/problem-discovery/SKILL.md`. This document is
supporting evidence, not a second policy authority or an execution-state
ledger.

Source candidate version: `2.0.0+codex.20261009111424`.

The current delivery boundary includes source, package metadata, bilingual
documentation, policy tests, independent source review, and a read-only
forward scenario. Plugin installation, activation, Push, release, deployment,
production or paid calls, data changes, and destructive cleanup remain outside
this work.

## Source Learning And Generalization

The bounded source case was Codex thread
`01a11e46-3ce1-75f3-bdad-0119bf979e21`, which compared earlier Go Native
Runtime testing with a later phase that exposed more execution problems. Its
useful causal observations were:

- representative task distributions and contract-driven state challenges find
  different classes of problems;
- a recovery, concurrency, or rejection test can pass while missing a specific
  ordering, ownership transfer, late fact, mixed-validity input, or pre-error
  side effect;
- the acceptance method can accept a valid file whose business facts or input
  binding are wrong;
- deterministic counterexamples can expose shared execution defects before a
  real provider call;
- local integration is still needed for actual identity, persistence,
  transport, process, role, network, and service composition; and
- detecting an unknown result does not by itself diagnose its cause.

These observations do not establish a universal defect count, a fixed state
matrix, or a mandatory sequence of tests. The public Skill generalizes them
into a decision method: model relevant behavior and risk, derive explicit and
latent claims, choose the earliest trustworthy observation environment for
each affected risk dimension, and broaden only for behavior the earlier
environment cannot represent.

## Architecture Decision

Problem discovery is a separate Skill rather than a reference under
`independent-validation` because the responsibilities differ:

- `problem-discovery` designs coverage, falsifiers, observation points,
  oracles, valid controls, and stop conditions before or during implementation;
- `independent-validation` decides when a separate challenge of a plan,
  artifact, diagnosis, evidence set, or completion claim adds confidence; and
- `work-lifecycle` remains a small router and loads problem discovery only
  when test, validation, or evidence strategy is being designed or reviewed.

Running an already-defined routine test suite is an explicit anti-trigger.

## Policy Contract

The candidate requires a lightweight behavior and risk model covering relevant
actors and owners, states and transitions, data and assets, actions and
effects, dependencies and trust boundaries, and lifecycle or recovery paths.
Missing or contradictory expected behavior is a contract gap; test design
must return it to the current decision owner rather than inventing an oracle.

Observation environments and risk dimensions are orthogonal:

| Observation environment | Typical unique evidence |
| --- | --- |
| Design and static contract | Missing states, contradictions, unsafe ownership, compatibility and irreversible-effect assumptions |
| Isolated deterministic execution | Controlled ordering, transitions, exact effects, stale ownership, positive and negative controls |
| Local composed system | Real serialization, transport, identity, roles, persistence, networking, and multi-step flow |
| Authorized real dependency | Provider or environment semantics that local evidence cannot represent |
| Acceptance and operation | Business truth, artifact binding, drift, recovery evidence, observability, and acceptance-method accuracy |

Persistence, concurrency, authorization, recovery, side effects, schema drift,
and oracle quality can be challenged in more than one environment. They are
not later stages by definition.

The candidate prevents “comprehensive” from becoming exhaustive:

- representative distributions cover broad workload behavior;
- state matrices cover rare contract-driven interleavings;
- lower-risk interactions may use pairwise or sampled coverage;
- terminal, irreversible, ownership-transfer, and recovery sequences are named
  explicitly when ordering changes the expected result;
- valid neighboring behavior is protected alongside each counterexample; and
- broader or external probes stop when no unresolved claim is unique to that
  environment.

## Independent Challenge And Forward Scenario

An independent read-only review initially found that the candidate mixed
persistence and concurrency risks into a linear stage model, assumed the
important claims were already known, over-locked wording in policy tests, and
described later validation too narrowly as a binding check. The candidate was
revised to use a behavior model, latent-claim derivation, orthogonal
observation environments and risk dimensions, narrower policy invariants, and
coverage for composed and operational semantics. A second review found no
blocking issue for a local commit.

A separate read-only forward scenario applied the Skill to a third-party
payment callback processor with deduplication, duplicate and out-of-order
events, late results, refund or cancellation, schema evolution, and costly
sandbox calls. It produced:

- contract questions for state precedence and terminal semantics instead of
  inventing product behavior;
- deterministic challenges for deduplication, state convergence, downstream
  effect multiplicity, stale writers, and late facts;
- local-composition checks for raw input verification, routing, persistence,
  outgoing actions, and correlated evidence;
- a minimal authorized external probe only for provider-unique behavior; and
- explicit residual boundaries for sandbox and production semantics.

That scenario exposed useful generic omissions in the first draft. The revised
Skill now separates overloaded idempotency obligations, selects critical
ordered sequences, expands schema and representation boundaries, and requires
an exact target, uniquely unresolved claim, per-probe maximum effect or cost,
total budget, and first-anomaly stopping response before an external probe.
The follow-up read found those gaps closed and no new exhaustive-testing bias.
No real payment system or other external dependency was called.

## Source Validation

The revised candidate passed:

- 29 policy-contract tests with `uv run pytest`;
- Ruff lint and format checks for the policy suite;
- JSON parsing and manifest-parity policy checks;
- the bundled Skill validator for all 12 packaged Skills; and
- `git diff --check`.

The forward scenario used the source Skill directly; it is evidence for
candidate behavior, not proof of installed or remote adoption.

## Remaining Boundaries

The Skill cannot supply domain contracts such as business state precedence,
financial invariants, provider signature rules, version windows, or the exact
meaning of cancellation and late success. Those remain owned by current user
intent and project authority.

External targets, credentials, budgets, data effects, production-like
environments, installation, Push, release, and deployment retain their
existing authorization boundaries. A broad design and a passed source
candidate do not authorize any of those actions or prove that every future
trajectory will find every defect.
