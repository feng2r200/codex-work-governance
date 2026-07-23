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
- Rollback review: when deviation occurred, inspect suspect artifacts and decide
  whether rollback, quarantine, or compensation is safe to propose.

If role isolation is unavailable:

- disclose the downgrade;
- strengthen deterministic checks where possible;
- lower conclusion strength for high-impact work unless the user accepts the
  downgrade.

Validation standard: every completion claim names the obligation, check, and
fresh evidence; gaps are reported as gaps.
