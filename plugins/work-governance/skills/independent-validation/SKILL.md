---
name: independent-validation
description: Challenge plans, artifacts, evidence, testing strategy, and completion claims only when independent review adds real confidence.
---

# Independent Validation

Load `work-governance:work-lifecycle` first unless the user explicitly asked for
a standalone review. Validation challenges claims; it does not own the parent
Plan, WorkVCS records, or final wording.

## When To Use

Use independent validation when at least one of these is true:

- high-impact, destructive, remote, production, data, or security-sensitive
  work is in scope;
- the implementer is also judging a completion claim;
- a contract, testing strategy, state transition, release, activation, or rollback
  claim can fail in subtle ways;
- evidence is indirect, degraded, stale, or easy to overstate;
- the user or parent agent asked for a challenge pass.

Do not run validation as a default tax on every No-Plan answer or routine
reversible local edit.

## Modes

- `plan-challenge`: obligations, scope, gates, dependencies, stop conditions,
  and acceptance evidence.
- `artifact-review`: diff, generated output, docs, schema, UI, or data artifact
  against the demand contract.
- `evidence-audit`: whether commands, tests, logs, samples, screenshots, or
  WorkVCS closeout output prove the exact claim.
- `causal-challenge`: whether a stated root cause is falsifiable and the fix
  removes the cause instead of hiding a symptom.
- `rollback-review`: whether suspect artifacts are identified and a proposed
  rollback, quarantine, or compensation is safe to recommend.

## Independence

Prefer a separate context when available and useful. Give validators the demand
contract and raw artifacts, not the implementer's intended answer. Treat
validator output as evidence input; the parent decides any WorkVCS update,
confirmation gate, and final claim.

If independence is unavailable, say so plainly. For ordinary reversible local
work, a deterministic self-challenge may still be useful. For high-impact
completion, activation, route closeout, or external actions, unavailable
validation remains a gap unless the user accepts that risk.

## Output

Lead with findings ordered by severity:

- finding;
- evidence location or command output;
- affected obligation;
- required correction, validation, or confirmation gate.

If no issues are found, state what was checked and what residual risk remains.
