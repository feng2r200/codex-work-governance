---
name: independent-validation
description: Provide role-isolated validation for plans, artifacts, evidence, completion claims, rollback proposals, and suspicious outputs. Use when high-impact work, self-certification risk, testing strategy, contract changes, code review, or completion evidence needs a challenge pass.
---

# Independent Validation

Load `work-governance:work-lifecycle` first unless this is an isolated review
request. Validation challenges claims; it does not own the parent Plan.

## Validation Modes

- `plan-challenge`: obligations, scope, gates, dependencies, stop conditions,
  and acceptance evidence.
- `artifact-review`: diff, generated output, schema, docs, UI, or data artifact
  against the demand contract.
- `evidence-audit`: whether commands, tests, logs, samples, or screenshots prove
  the exact obligation.
- `causal-challenge`: whether the stated root cause is falsifiable, supported
  and contradicting evidence was considered, the probe discriminates competing
  explanations, and the correction removes the causal link rather than hiding
  a symptom.
- `stop-loss-audit`: whether retries changed inputs or evidence, whether an
  ineffective loop should already have stopped, and whether test additions
  have real provenance instead of serving coverage count.
- `batch-gate-audit`: whether bulk authorization waived only repeated prompts,
  the pilot dependency was verified before fan-out, and
  `QUALITY_DRIFT_DETECTED` froze every dependent downstream batch.
- `rollback-review`: whether suspect artifacts are identified and whether a
  proposed rollback, quarantine, or compensation is safe to recommend.

## Independence Rules

- Prefer a separate context or SubAgent when available.
- Give validators raw artifacts and the demand contract, not the implementer's
  intended answer.
- Treat validator output as evidence input. The parent agent decides Plan/log
  updates and final wording.
- Do not assume the Plan boundary is correct. At Plan admission and closeout,
  compare the current user goal, exclusions and their dispositions, declared
  delivery/activation state, current runtime evidence, and proposed completion
  wording. Challenge any route that is internally closed but externally
  unapplied.
- If independence is unavailable, disclose `VALIDATOR_UNAVAILABLE`; absence of
  a reviewer is an availability fact, not evidence that the artifact itself is
  low confidence. Keep high-impact completion blocked unless the exact degraded
  risk is accepted.
- Make reviewer acquisition bounded: one initial attempt and at most one retry
  after materially changing the review input, context, or mechanism. If neither
  returns a final review, report `VALIDATOR_UNAVAILABLE` rather than inventing a
  confidence score or requesting an open-ended retry loop. A deterministic
  self-challenge may support only ordinary reversible local tasks; delivery,
  activation, route closeout, external actions, and any task with a confirmation
  gate remain blocked, as do all targets covered by an open blocker or high
  finding. Use `review acquisition check` before retrying the same target,
  mechanism, and reviewed input digest. Treat a fresh same-mechanism cache as
  matching for proxy, auth, missing-command, timeout, and attestor failures even
  when the reviewed input digest changed. When acquisition fails, pipe the
  redacted command output to `review acquisition record-failure`; the resulting
  runtime cooldown is availability evidence only, not an independent review.
- For layout/bootstrap claims, inspect the exact Plugin build, READY receipt,
  version contract, local evidence record, offline command evidence, and both
  layout and Plan-authority axes. A hook's self-report is not sufficient.
- For candidate release, migration, activation, or governance-framework claims,
  inspect the executable surface named by `workctl help <workflow>` and
  generated `docs/CLI_REFERENCE.md`, then compare it with the proposed wording.
  Flag any wording that treats target architecture, historical plans, replay
  summaries, or adjacent tests as proof of unimplemented capability.
- For evidence audits, check obligation-to-anchor coverage, command freshness,
  artifact digests, changed-file scope, skipped/flaky tests, absence of
  `FAIL`/`ERROR` indicators in cited logs, and whether manual or degraded
  evidence is labeled with its residual risk.
- Prefer evidence from the cheapest safe real boundary that determines the user
  result. Treat synthetic tests as support, not a substitute, and require an
  explicit infeasibility reason when the real boundary was not probed.
- Challenge materially plausible minimal containment, causal correction, and
  alternate-route options. Report when sunk cost, test volume, or a preferred
  implementation is being mistaken for truth.

## Plan-level Review Contract

High-impact Plans carry `independent_validation` with `required`, aggregate
`state`, required modes, the implementation context, and one review record per
mode. Required modes are `plan_challenge`, `artifact_review`, and
`evidence_audit`.

Each review record names:

- `state`: `pending`, `verified`, or `degraded`;
- exact shared target `blocks` and their release condition;
- implementation and review context references;
- the reviewed contract and artifact SHA256 digests;
- findings with severity and resolution state;
- a canonical evidence reference and SHA256.

Record a result only through `plan independent-review record --manifest`.
Reviewers receive the demand contract and raw artifacts, remain read-only, and
cannot modify the parent Plan or delivery. An unresolved `blocker` or `high`
finding preserves every declared block and prevents dependent task progress,
live switching, activation, delivery completion, and closeout.

Different free-form context labels and caller-authored canonical evidence are
not isolation evidence. A `verified` record requires an authenticated platform
attestor that the controller can validate outside the caller-controlled
evidence recorder. This controller has no such attestor capability, so it
fails closed with `INDEPENDENT_REVIEW_TRUSTED_ATTESTATION_UNAVAILABLE` and
records the review only as `degraded`. Matching contexts or review evidence
whose producer differs from the declared review context also cannot verify.

A degraded review cannot support a high-impact completion claim. It releases
blocks only when a separate `external_authority` risk-acceptance confirmation
binds the exact degraded review evidence and is accepted through `plan confirm`
under the trusted current user turn. The degraded review manifest must reserve
the exact `risk_acceptance_confirmation_id`; that ID must not exist when the
review is recorded. Create the pending confirmation after the review and decide
that exact ID through
`plan confirm`. The controller never scans for or adopts another accepted
confirmation. Schema-v4/v5 `plan confirmation add` cannot pre-accept the decision.

For a bootstrap Plan created by a controller that predates the review command,
only exact canonical V/T evidence whose subject equals every declared mapped
target may temporarily release its bounded pre-install targets. It does not
change review state. The new recorder is the sole allowed blocked-state
migration command and must migrate that exact evidence before activation,
delivery, or closeout.

## Output Shape

Lead with findings ordered by severity:

- finding;
- evidence location or command output;
- affected obligation;
- required correction or confirmation gate.

If no issues are found, say what was checked and what residual risk remains.
