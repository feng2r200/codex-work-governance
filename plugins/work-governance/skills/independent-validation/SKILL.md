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
- If independence is unavailable, disclose the downgrade and lower conclusion
  strength for high-impact work unless the user accepts the risk.
- For layout/bootstrap claims, inspect the exact Plugin build, READY receipt,
  version contract, local evidence record, offline command evidence, and both
  layout and Plan-authority axes. A hook's self-report is not sufficient.
- Prefer evidence from the cheapest safe real boundary that determines the user
  result. Treat synthetic tests as support, not a substitute, and require an
  explicit infeasibility reason when the real boundary was not probed.
- Challenge materially plausible minimal containment, causal correction, and
  alternate-route options. Report when sunk cost, test volume, or a preferred
  implementation is being mistaken for truth.

## Output Shape

Lead with findings ordered by severity:

- finding;
- evidence location or command output;
- affected obligation;
- required correction or confirmation gate.

If no issues are found, say what was checked and what residual risk remains.
