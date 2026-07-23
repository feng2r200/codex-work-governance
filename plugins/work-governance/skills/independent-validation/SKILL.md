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
- `rollback-review`: whether suspect artifacts are identified and whether a
  proposed rollback, quarantine, or compensation is safe to recommend.

## Independence Rules

- Prefer a separate context or SubAgent when available.
- Give validators raw artifacts and the demand contract, not the implementer's
  intended answer.
- Treat validator output as evidence input. The parent agent decides Plan/log
  updates and final wording.
- If independence is unavailable, disclose the downgrade and lower conclusion
  strength for high-impact work unless the user accepts the risk.

## Output Shape

Lead with findings ordered by severity:

- finding;
- evidence location or command output;
- affected obligation;
- required correction or confirmation gate.

If no issues are found, say what was checked and what residual risk remains.
