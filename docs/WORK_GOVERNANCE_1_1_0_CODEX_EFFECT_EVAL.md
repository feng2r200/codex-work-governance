# Work Governance 1.1.0 Codex Effect Evaluation

Date: 2026-08-05

## Purpose

This report records a temporary Codex effect evaluation for the isolated
`work-governance` 1.1.0 candidate before
`CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0`.

The purpose is to test whether the candidate improves the user's historical
friction in real Codex and controller-adjacent paths. It is not an activation
report, not a marketplace switch, and not a claim that the full target
architecture draft has already been implemented.

## Boundary

- Evaluated source before these report assets: `7372acb` on
  `feat/goal-driven-light-governance`.
- Live plugin observed during the live smoke remained
  `1.0.7+codex.20260804122047`.
- Candidate plugin was installed only into a temporary `CODEX_HOME`
  represented below as `<system-temp>/wg-codex-effect-home-20260805b`.
- Temporary workspaces were under the system temporary directory.
- No user authentication material was copied into the temporary `CODEX_HOME`.
- No live plugin, marketplace, cache, branch, remote, or activation pointer was
  replaced.
- Push remains out of scope.

## Evidence Grades

| Grade | Meaning |
| --- | --- |
| `real_codex_live` | A real `codex exec` run against the current live environment. |
| `real_codex_candidate_degraded` | A real `codex exec` run using isolated candidate config, blocked by missing auth before model response. |
| `real_hook_candidate` | The candidate SessionStart hook ran against a temporary project and returned a concrete bootstrap result. |
| `controller_replay` | Receipt-bound pytest/controller replay of candidate behavior. |
| `static_contract` | Source, docs, generated help, or scan evidence. |

## Durable Evidence Binding

The machine-readable fixture
`tests/fixtures/work_governance_1_1_0_codex_effect_eval.json` binds every
scenario below to one or more `EV-*` records. Each record includes a source
type, evidence grade, command summary, exit code, redacted output excerpt,
excerpt SHA256, support result, and redaction policy. The regression test
recomputes those excerpt hashes and checks that every scenario has a matching
evidence reference.

## Scenario Matrix

| Case | Historical friction target | Result | Evidence grade | Observed effect |
| --- | --- | --- | --- | --- |
| CE-001 | Ordinary No-Plan work caused Plan churn. | Passed | `real_codex_live` | `codex exec --ephemeral --skip-git-repo-check --cd <system-temp>/wg-codex-effect-eval-live-1` returned `WG_CODEX_EFFECT_SMOKE_OK`; bootstrap/runtime/cache were created by live hooks, but `.work-governance/_Plan` was not created. |
| CE-002 | Candidate must stay isolated before activation. | Passed | `static_contract` | `CODEX_HOME=<system-temp>/wg-codex-effect-home-20260805b codex plugin add work-governance@work-governance-local --json` installed `1.1.0+codex.20260805000000` from the candidate worktree. `codex plugin list` in that home showed only the candidate plugin. |
| CE-003 | Candidate real Codex smoke should not require copying user auth. | Degraded | `real_codex_candidate_degraded` | Candidate `codex exec` entered the real Codex startup path but stopped with `401 Unauthorized`; no candidate workspace `.work-governance` directory was created before the auth failure. |
| CE-004 | Candidate hook should produce a real READY receipt when dependency access exists. | Passed | `real_hook_candidate` | A normal sandbox run first hit `CONTROLLER_PREWARM_FAILED` due PyPI tunnel failure; one elevated retry with the same valid SessionStart input returned `WORK_GOVERNANCE_BOOTSTRAP READY`, `layout=LAYOUT_READY`, and build `1.1.0+codex.20260805000000`. |
| CE-005 | No-Plan and bootstrap must not silently admit a Plan. | Passed | `real_hook_candidate` | After the candidate SessionStart READY receipt, the temporary project still had no `.work-governance/_Plan` directory. A naked `plan create` was rejected with `PLAN_ADMISSION_REQUIRED`, so Plan admission remains explicit. |
| CE-006 | Evidence should be captured directly, not through a temp manifest handoff. | Passed | `controller_replay` | `tests/test_schema_v5.py::test_direct_capture_handles_binary_large_and_corrupt_ledger_boundaries` is included in the passing schema-v5 suite. It covers file capture, blob redaction, ledger append, oversized input rejection, and corrupt ledger fail-closed behavior. |
| CE-007 | A blocked task should not freeze unrelated ready work. | Passed | `controller_replay` | `tests/test_schema_v5.py::test_v5_status_and_scheduler_keep_blocked_work_visible_and_bounded` is included in the passing schema-v5 suite and keeps ready siblings visible while reporting blocker propagation. |
| CE-008 | Repeated route-authorized actions should not force repeated user turns. | Passed | `controller_replay` | Route lease tests in `tests/test_schema_v5.py` cover prepare, issue, per-action single-use authorization, consumed retry idempotency, max-use enforcement, and freeze on Plan contract drift. |
| CE-009 | Reviewer acquisition failures should not create an infinite same-agent retry path. | Passed | `controller_replay` | Reviewer acquisition cache tests in `tests/test_schema_v5.py` cover redacted failure recording, exact and environment-level cooldown matching, duplicate refusal, expiry, and `review acquisition status`. |
| CE-010 | Models should be able to discover current command usage without reading all of `workctl.py`. | Passed | `static_contract` | `workctl help migrate`, `workctl help action`, `workctl help review`, `workctl help evidence`, and `workctl help plan` all returned stable JSON command summaries. |
| CE-011 | Candidate notes must not overclaim the unfinished target architecture. | Passed | `static_contract` | Static scan found the activation gate references and did not find draft-done claim phrases in README, docs, or skills. |
| CE-012 | Candidate still must not claim live activation. | Passed | `static_contract` | This report and the existing candidate docs keep activation deferred to `CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0`. |

## Metric Summary

| Metric | Current evidence | Interpretation |
| --- | --- | --- |
| Plan contract churn | Live No-Plan smoke and candidate hook probe created no `_Plan`; schema-v5 tests keep runtime/evidence transitions out of contract revision churn. | Improved by design and replay evidence, but not yet proven after the user's live home switches to 1.1.0. |
| Temporary evidence dependency | Direct capture tests cover stdin/file capture into ledger/blob storage; docs and skills no longer recommend a temp-manifest handoff for evidence. | Improved for implemented evidence capture paths. |
| Ready task progress | Scheduler tests keep independent ready siblings visible while blocked tasks report real blockers. | Improved at controller level. |
| Repeated user confirmation prompts | Route leases reduce repeated same-kind action prompts after one exact confirmed lease basis. | Improved at controller level; still fail-closed on scope drift, review blockers, artifact blockers, or lease expiry. |
| Reviewer retry loop | Reviewer acquisition cache turns repeated unavailable reviewer paths into bounded `VALIDATOR_UNAVAILABLE_CACHED` state. | Improved at controller level; it does not verify independent review. |
| Help-first usability | Runtime help returned command summaries for migrate/action/review/evidence/plan. | Improved, while the broad architecture CRUD surface is still partial. |
| Overclaim prevention | Candidate docs state activation is deferred and the executable surface is narrower than the architecture draft. | Improved; this remains a release-note discipline requirement. |

## Commands Run

```text
codex exec --ephemeral --skip-git-repo-check --cd <system-temp>/wg-codex-effect-eval-live-1 "Answer exactly: WG_CODEX_EFFECT_SMOKE_OK"
CODEX_HOME=<system-temp>/wg-codex-effect-home-20260805b codex plugin marketplace add /Users/example/Repositories/Skills/work-governance/.work-governance/worktrees/goal-driven-light-governance --json
CODEX_HOME=<system-temp>/wg-codex-effect-home-20260805b codex plugin add work-governance@work-governance-local --json
CODEX_HOME=<system-temp>/wg-codex-effect-home-20260805b codex plugin list --json
CODEX_HOME=<system-temp>/wg-codex-effect-home-20260805b codex exec --ephemeral --skip-git-repo-check --cd <system-temp>/wg-codex-effect-eval-candidate-20260805b "Answer exactly: WG_CANDIDATE_CODEX_EFFECT_SMOKE_OK"
PLUGIN_ROOT=/Users/example/Repositories/Skills/work-governance/.work-governance/worktrees/goal-driven-light-governance/plugins/work-governance python3 plugins/work-governance/hooks/session_start.py
uv run pytest tests/test_schema_v5.py -q
uv run pytest tests/test_work_lifecycle_skill.py -q
uv run python plugins/work-governance/scripts/workctl.py help migrate
uv run python plugins/work-governance/scripts/workctl.py help action
uv run python plugins/work-governance/scripts/workctl.py help review
uv run python plugins/work-governance/scripts/workctl.py help evidence
uv run python plugins/work-governance/scripts/workctl.py help plan
```

## Limitations

- Candidate real model response was not obtained because the isolated temporary
  `CODEX_HOME` intentionally had no authentication state. This is a degraded
  real-boundary result, not a pass for activated candidate behavior.
- The initial candidate SessionStart hook attempt could not prewarm dependencies
  inside the normal sandbox because PyPI access failed through the tunnel. A
  single elevated retry with the same valid hook input succeeded and stayed
  confined to the temporary project.
- The broad 1.1.0 architecture draft remains partially implemented. In
  particular, the current executable candidate surface does not yet provide the
  full Bash-first CRUD surface described in the draft; `task add` is not an
  implemented command in the candidate.
- This evaluation does not replace the need for a fresh activated-plugin replay
  after `CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0`.

## Conclusion

The candidate shows meaningful improvement against the historical friction
classes that were measurable before activation: Plan churn, evidence handoff,
blocked/ready scheduling, repeated action authorization, reviewer acquisition
loops, help-first usage, and overclaim discipline.

The evidence is strong enough to continue toward activation validation, but it
does not prove live 1.1.0 behavior under the user's active Codex home. The next
formal gate remains `CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0`.
