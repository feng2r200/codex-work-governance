# L4 Independent Validation

Use independent validation for high-impact work, contract changes, tricky tests,
completion claims, or self-certification risk.

Validation roles:

- Plan challenge: check that obligations, scope, dependencies, gates, and stop
  conditions match the user request.
- Artifact review: inspect diffs and generated outputs for wrong placement,
  missing behavior, hidden side effects, or untracked generated files.
- Evidence audit: confirm that checks prove the obligations rather than nearby
  facts.
- Reality audit: confirm that a safe real-boundary probe was run when the target
  depends on runtime or integration behavior, or that a concrete reason makes
  it infeasible.
- Test-provenance audit: map every material new case to a confirmed obligation,
  observed failure, code invariant, or supported integration boundary; reject
  invented scenarios and case-count or coverage-only work.
- Causal audit: challenge whether the proposed fix breaks the demonstrated
  causal chain or merely suppresses the observed symptom.
- Rollback review: when deviation occurred, inspect suspect artifacts and decide
  whether rollback, quarantine, or compensation is safe to propose.

At admission and closeout, challenge the Plan boundary itself. Compare the
current user goal, structured exclusions, declared delivery/activation state,
current runtime evidence, and proposed completion wording. A Plan can be
internally consistent while still hiding a required future action in
`scope.exclude`.

Record accepted results through the dedicated evidence transitions. Ordinary
Plan revision must not promote obligations or validations to verified,
artifacts to final, or delivery to complete. Each transition carries a typed
evidence reference and SHA256 for later challenge.

If role isolation is unavailable:

- disclose the downgrade;
- strengthen deterministic checks where possible;
- lower conclusion strength for high-impact work unless the user accepts the
  downgrade.

Validation standard: every completion claim names the obligation, check, and
fresh evidence; every material test has provenance; reality-bound gaps are
reported as gaps.
