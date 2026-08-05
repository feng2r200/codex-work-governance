# Work Governance 1.1.0 Temporary Codex Evaluation

Date: 2026-08-05

## Scope

This report records a temporary release-validation pass for the local
`work-governance` 1.1.0 candidate. The evaluation does not replace, activate,
publish, push, or redirect the user's live plugin. The live plugin remained
`1.0.7+codex.20260804122047`; the candidate source remained in the isolated
worktree `feat/goal-driven-light-governance`.

## Evaluation Boundary

The evaluation used two layers:

- Codex smoke layer: real `codex exec` sessions in system temporary workspaces
  to check runtime channel behavior and local side effects.
- Controller layer: repeatable candidate `workctl` and pytest checks to cover
  schema-v5 migration, evidence, scheduler blockers, help surface, and
  candidate-scope claims.

The candidate was also installed into an isolated temporary `CODEX_HOME`.
That temporary home was not given the user's real authentication state, so
model execution with the candidate stopped at `401 Unauthorized`. This is a
validation limitation, not a candidate behavior failure.

## Results

| Case | Target | Result | Evidence |
| --- | --- | --- | --- |
| EVAL-001 | Confirm real `codex exec` channel works when not blocked by sandbox networking. | Passed | Non-sandbox smoke returned `CODEX_EVAL_SMOKE_OK`. |
| EVAL-002 | Check live 1.0.7 No-Plan behavior in an isolated temporary workspace. | Passed | `codex exec --ephemeral --skip-git-repo-check --cd <temp-eval-workspace> ...` returned `4`; hooks ran, but no `.work-governance/_Plan` directory was created. |
| EVAL-003 | Install candidate 1.1.0 into an isolated Codex home without changing live config. | Passed | `CODEX_HOME=<temp-codex-home> codex plugin add work-governance@work-governance-local --json` installed `1.1.0+codex.20260805000000`. |
| EVAL-004 | Run candidate real model smoke from the isolated Codex home. | Degraded | Candidate home had no auth by design; `codex exec` stopped with `401 Unauthorized` before hooks/model response. |
| EVAL-005 | Validate candidate schema-v5 behavior surface. | Passed | `uv run pytest tests/test_schema_v5.py -q` passed: `24 passed`. |
| EVAL-006 | Validate candidate static quality after the eval-discovered fix. | Passed | `uv run ruff check .`, `uv run mypy`, and `uv run python plugins/work-governance/scripts/generate_cli_reference.py --check` passed. |
| EVAL-007 | Scan for forbidden temporary evidence recommendations and overclaiming. | Passed | No documentation or skill recommendation was found for a temp-manifest handoff; accepted-status parser rendering remains covered by a negative test assertion. |

## Finding Fixed During Evaluation

`workctl help migrate` failed even though the public command domain is
`migrate`. The generated help only accepted `migration`, which was accurate
internally but mismatched the CLI users naturally reach for.

Fix applied:

- Added `migrate` as an alias for `migration` in the workflow-help surface.
- Exported the alias from `workctl_modules`.
- Updated parser choices and regenerated `docs/CLI_REFERENCE.md`.
- Added a regression assertion that `workctl help migrate` and
  `workctl help migration` return the same payload.

## Follow-up Historical Friction Fix

After this temporary evaluation, the 1.0.7 historical friction re-audit found
one activation-relevant gap: repeated high-impact actions could still force
new user turns even after the route and safety boundary were clear. The
candidate now includes bounded route authority leases:

- `action lease prepare` computes the exact lease basis for confirmation.
- `action lease issue` records the confirmed lease in runtime state.
- `action lease authorize` mints one single-use authorization per concrete
  action inside the lease scope, with an explicit idempotency key for same
  target/same digest retries after consumption.
- `action consume` remains required immediately before execution.

The lease does not waive pilot evidence, validation evidence, action success
evidence, Plan contract drift checks, review blockers, artifact blockers, or
activation confirmation.

## Residual Risk

- Full candidate `codex exec` with hooks and model response was not run because
  the isolated temporary Codex home intentionally did not copy real auth.
- The current live plugin was not replaced or redirected, so this report does
  not prove live activation.
- The broader destructive redesign draft remains partially implemented by
  design; the executable surface is the generated CLI reference and
  `workctl help`.

## Recommendation

The candidate remains suitable for continued release validation. The temporary
evaluation found one actionable help-surface friction point and fixed it. No
new P1/P2 governance bypass was found in the candidate controller layer.

Do not activate yet. The next activation-phase validation still needs a fresh
session after explicit `CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0`, including
exact source/cache identity, hook receipt, candidate `intake status`, and a
live candidate No-Plan smoke under the real activated plugin.
