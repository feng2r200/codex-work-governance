# Task-triggered Skill discovery and CodeGraph attribution correction

Collected: 2026-11-07, local Pi installation and repository checkout.
Scope: Work Governance's 15 shipped Skills; no global third-party Skill edits,
no input sent to the other running Pi session, and no adapter installation.

## Findings and correction

Two different claims must remain separate:

1. **Confirmed discovery defect:** all 13 scenario modules described task-based
   activation but declared `disable-model-invocation: true`. The installed Pi
   loader discovered them but its prompt formatter excluded them. Only
   `work-lifecycle` and `execution-kernel` were advertised. The lifecycle's
   indirect links still made manual reading possible; hiding is not proof that
   a module was never read.
2. **Withdrawn attribution:** the original `NativeAgentTurn` query failure was
   initially attributed to an omitted sync. The source session contradicts
   that attribution. It had read code-intelligence and performed sync and a
   successful status readback before the failing query. Removing the discovery
   defect does not by itself explain or eliminate this failure.

The read-only `program:1.1` terminal capture showed the storage-contract task,
not the older tool error: its alternate screen had no scrollback history.
The relevant durable source was the matching task session
`2026-11-06T07-58-37-284Z_01a1afdd-e4e4-71fb-ba55-b5d083cc9221.jsonl`
in the local Pi project session directory. Line numbers below are physical JSONL
lines observed on the collection date:

| UTC time, 2026-11-07 | Session lines | Observation |
| --- | --- | --- |
| 02:16:10–02:16:18 | 284–285 | Explicit sync completed: 38 changed files |
| 02:16:26–02:16:27 | 286–287 | Status reported complete, matching extraction versions, no reindex recommendation, and pending changes 0/0/0 |
| 02:16:36 | 288–289 | Original search was refused for pending changes or unknown freshness |
| 02:16:45 | 290 | Caller continued through direct source reads rather than retrying the graph |

The same session explicitly read code-intelligence on 2026-11-06 (line 10).
The later diagnostic status reported pending changes 1/2/0. The exact changed
files and writer responsible for the interval were not recovered. Concurrent
writes are plausible because other sessions shared the checkout, but their
causal ownership is **unknown**, not established by the terminal inventory.
The defensible mechanism is point-in-time freshness invalidation, not proof
of a forgotten sync or a broken executable. Native inspection after refusal
is a valid degraded route, not itself a failure to recover.

## Decision and bounded change

All 13 hidden modules have task triggers and are routed by work-lifecycle;
none is documented as an operator-only command. Remove their explicit-only
frontmatter setting. Keep the two already discoverable entries unchanged.
Do not load every Skill body eagerly or bypass any scenario/authority gate.
The router remains useful but is not the sole discovery path.

Code intelligence now explains that source changes can invalidate a successful
status before a query. For ordinary new pending changes, repeat authorized
incremental sync and readback before retrying; when active writers keep
invalidating readiness, use native inspection rather than racing them with
refresh loops or forced rebuilds. Unknown status, locks and integrity issues
remain separate diagnoses.

Version: 3.2.1, a discoverability and guidance fix. No CLI behavior, adapter
runtime, global package registration, remote publication or running-session
reload was changed. Rollback is the inverse of this task's diff, not a reset
of unrelated repository work.

## Refutation and measured host-loader evidence

- Premise: task-triggered scenario modules should be advertised independently
  of whether the lifecycle was already read. Every affected module's current
  description and lifecycle route supports that premise.
- Refutation: use the installed Pi `loadSkillsFromDir` and
  `formatSkillsForPrompt` on the real shipped directory. A missing module,
  diagnostics, or an absent advertised name fails discovery acceptance.
- Benefit basis: advertised entries increased from 2/15 to 15/15, with zero
  loader diagnostics. Bodies remain lazy-loaded; discoverability is not proof
  that a model chooses or follows the right Skill.
- Cost basis: formatted metadata grew from 1,198 to 7,621 UTF-8 bytes, a 6,423-byte
  increase per generated Skill catalog. This is metadata, not all Skill bodies;
  no billed token or monetary estimate was inferred from bytes.
- Reversal: restore only the affected frontmatter/docs/guidance diff and check
  the formatter returns to the prior two-entry catalog.

The initial Python regression failed and listed all 13 hidden modules.
After editing the actual files, the installed Pi loader/formatter returned all
15 names. A same-shape negative control changed only code-intelligence's
in-memory `disableModelInvocation` to true: its advertised name disappeared
while work-lifecycle remained visible. Thus the measurement distinguishes the
setting at the actual host boundary rather than merely checking YAML text.

The probe imported `dist/core/skills.js` from the explicitly installed Pi
package; it did not use a reimplementation of the formatter or send a paid
model prompt. Readback checked the emitted prompt string itself.

## Repository verification (2026-11-07)

- `uv run --locked pytest -q`: **50 passed**.
- `uv run --locked ruff check tests/test_policy_contract.py`: passed.
- `uv run --locked ruff format --check tests/test_policy_contract.py`: passed.
- `uv run --locked mypy --strict --follow-untyped-imports --untyped-calls-exclude=yaml tests/test_policy_contract.py`:
  passed. An initial strict run without the YAML exclusion reported the two
  existing untyped `yaml.safe_load` calls, not the new regression test. The
  exclusion is a command-line boundary for that untyped dependency; no typing
  configuration or dependencies were changed.
- `bash scripts/validate-version-bump.sh --base-ref HEAD`: verified 3.2.0 to
  3.2.1, including the release-impacting-change guard.
- `git diff --check`: passed.
- Active LSP probe of the changed Python file: inconclusive, no primary server
  answer. This is not a clean LSP result; the executable checks above are the
  available validation evidence.

## Applicability limits

This evidence establishes current source configuration and the installed
loader's catalog generation, not hot reload of any existing conversation,
automatic Skill selection quality, or successful model-driven sync/retry under
concurrent edits. Start a new session or reload an idle one to pick up changes;
do not interrupt another session's active work. Re-probe after host upgrades.
Fresh runtime observations outrank this dated record.
