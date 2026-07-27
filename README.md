# Work Governance Plugin

Work Governance is a Codex plugin that governs a task from intake through
planning, execution, evidence review, independent validation, and handoff.

The repository-local marketplace is `.agents/plugins/marketplace.json` and the
plugin source is `plugins/work-governance`.

## Skills

- `work-governance:work-lifecycle` is the mandatory lifecycle entry.
- `work-governance:git-change-governance` controls Git isolation and delivery
  boundaries.
- `work-governance:project-truth-governance` selects durable project authority
  locations.
- `work-governance:independent-validation` challenges plans, artifacts, and
  completion evidence.

When Git isolation needs a new worktree, the default location is
`<project-root>/.worktree/<task-or-branch-slug>`. The directory must be ignored;
an external worktree path requires an explicit user choice or a verified
technical constraint. This default reduces target-path sandbox crossings; Git
still writes shared metadata in the repository's common Git directory, whose
permission boundary must also be checked.

## Install

Add the repository root as a local marketplace, then install the plugin:

```sh
codex plugin marketplace add /path/to/codex-work-governance
codex plugin add work-governance@work-governance-local
```

Start a new Codex thread after installation so the plugin skills are loaded.

## Controller

`plugins/work-governance/scripts/workctl.py` is a PEP 723 script. Run it from a
governed project with:

```sh
uv run --script /path/to/workctl.py plan status
```

The controller uses `_Plan/index.yaml` only to locate the active Plan.
`_Plan/<plan-id>.md` frontmatter is the sole mutable execution authority. The
controller enforces one active execution authority, expected revisions,
dependency and confirmation gates, migration lineage, artifact quarantine
states, atomic Plan writes, recoverable reconciliation and terminal Plan
rollover, terminal closeout, and append-only logs.

Confirmation decisions are made only through `plan confirm` and may be
`accepted` or `declined`. Activation, confirmation-bound exclusions, and
terminal-route transitions are bound to their own decision ID; another
accepted gate cannot authorize them. Activation declared `active` also
requires typed, current runtime evidence. Generic Plan patches cannot rebind an
activation gate, remove an existing task, change an existing task's status, or
assign Plan status `complete`; existing task gates and resolved exclusion
decisions are stable, while delivery/evidence/route mutations bind to the
current slice gate. Completion uses the dedicated closeout command.

Schema v3 cannot be downgraded through ordinary revision. Verified
obligations/validations, final artifacts, and completed delivery use dedicated
commands that record a typed evidence reference and SHA256; generic structural
patches cannot self-promote these states. Once an activation decision is
resolved, target/current/evidence changes require that activation's own gate.
Artifacts can fail safe from final to suspect; quarantine/rollback-pending
transitions retain a recovery gate and cannot jump directly to final. Suspect
finalization also requires the in-progress task that declares recovery
ownership. Existing artifact records cannot be rewritten by generic Plan
patches.

New Plans use schema v3 to separate:

- the current execution slice;
- local or integrated delivery state;
- route-level activation state and current/target references;
- structured exclusions that are not required, deferred, confirmation-bound,
  transferred, or forbidden.

Missing authority for a live action creates a pending confirmation and keeps
the project route open. It cannot be converted into an absolute no-next claim
by placing the action in `scope.exclude`.

Start Plan-controlled work with:

```sh
uv run --script /path/to/workctl.py plan authority inspect
uv run --script /path/to/workctl.py plan authority check
```

Only `GOVERNED_ACTIVE` permits ordinary Plan writes or task progress. Legacy,
ambiguous, competing, or interrupted authority returns a fail-closed state.
Use `plan schema-validate` for a candidate document, `plan validate` for the
full project contract, and `plan status` for authority candidates, blockers,
obligations, validations, confirmations, artifacts, route, handoff, and
closeout readiness. Status also reports delivery, activation, and
`completion_claims`; only `no_required_next_step_allowed=true` supports a
terminal no-next statement.

Reconciliation is manifest-driven:

```sh
uv run --script /path/to/workctl.py plan reconcile apply \
  --manifest /path/to/reconcile.yaml --dry-run
uv run --script /path/to/workctl.py plan reconcile apply \
  --manifest /path/to/reconcile.yaml
uv run --script /path/to/workctl.py plan reconcile recover
```

The transaction verifies source hashes/revisions and an optional Git baseline,
requires each source's semantic classification, binds the migration
confirmation to the dry-run proposal digest, and binds a separate confirmation
to any exact `AGENTS.md` routing diff digest. It archives exact source bytes,
writes non-authoritative pointers with path-correct links, and activates the
new index last. Recovery rechecks staged hashes and the Git baseline.
`plan closeout-check` and `plan complete` include full Plan validation and
enforce route-level terminal completion.

A complete terminal Plan starts a distinct successor through a confirmed
rollover instead of reopening or overwriting the predecessor:

```sh
uv run --script /path/to/workctl.py plan rollover apply \
  --manifest /path/to/rollover.yaml --dry-run
uv run --script /path/to/workctl.py plan rollover apply \
  --manifest /path/to/rollover.yaml
uv run --script /path/to/workctl.py plan rollover recover \
  --rollover-id ROL-YYYYMMDD-NNN
```

The manifest fixes the predecessor ID, revision, path and SHA256, the exact
`_Plan/index.yaml` baseline, and a prepared schema-v3 successor contract. Apply
requires `C-PLAN-ROLLOVER` to carry the dry-run proposal digest. The transaction
preserves the completed predecessor bytes, records recursive predecessor
lineage in the successor, stages the successor and replacement index, and
activates the index last. An incomplete rollover freezes ordinary work in
`MIGRATION_RECOVERY_REQUIRED` until the named recovery converges. If
`AGENTS.md` or `CLAUDE.md` explicitly names the predecessor path as authority,
that routing must be separately revised before rollover so it cannot recreate
competing authority after activation.

## Validate

```sh
uv run --group dev ruff check .
uv run --group dev mypy --strict plugins/work-governance/scripts/workctl.py tests
uv run --group dev pytest -q
```

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.

The plugin itself does not provide a hosted service or telemetry. See
`PRIVACY.md` and `TERMS.md` for the public policy boundary.
