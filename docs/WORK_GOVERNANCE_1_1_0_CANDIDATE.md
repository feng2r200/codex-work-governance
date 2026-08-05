# Work Governance 1.1.0 Candidate Notes

## Scope

The 1.1.0 candidate is a local source candidate for goal-driven light
governance. It keeps the Codex plugin shape, adds a Bash-first public
`workctl` wrapper, keeps the Python controller as a private transaction
engine, and separates durable Plan contracts from runtime state and evidence
capture.

This is a candidate implementation of the core 1.1.0 control plane, not a
claim that every command and storage concept in the destructive redesign draft
is present in this source tree. The candidate supports the implemented public surface in
`workctl help <workflow>` and `docs/CLI_REFERENCE.md`; broader CRUD surfaces
such as full `task add|split|link`, `evidence show|link|redact|verify`, and
typed TruthRef validation remain future 1.1.x work. Current `truth add` and
`truth resolve`, when listed by the generated CLI reference, are guarded
contract-revision aliases rather than standalone TruthRef CRUD.

This candidate must not replace the user's live plugin, marketplace entry,
shared cache, Codex configuration, or active sessions before explicit
confirmation.

## Evidence Capture

Use direct capture for command output or project-local artifacts:

```sh
some_command | plugins/work-governance/scripts/workctl evidence capture \
  --task T-001 \
  --kind command-output \
  --summary "validation output" \
  --idempotency-key task-T-001-validation

plugins/work-governance/scripts/workctl evidence capture \
  --task T-001 \
  --kind artifact \
  --summary "validation report" \
  --from-file reports/validation.json
```

The controller applies conservative redaction before persistence, writes
redacted bytes to `.work-governance/evidence/blobs/<sha256>`, appends a
content-addressed metadata record to
`.work-governance/evidence/records/<sha256>.json`, appends the same metadata to
`.work-governance/evidence/ledger.ndjson`, and returns a content-addressed
`evidence_ref`. Schema-v5 task binding updates runtime state and the event
ledger only; the Plan contract bytes remain stable.

The legacy canonical Plan evidence path remains supported for compatibility:

```sh
plugins/work-governance/scripts/workctl plan evidence record --stdin
```

Direct capture is conservative rather than omniscient. Text evidence is
redacted with default secret patterns, oversized input fails closed, and
non-UTF-8 binary input is represented by a digest placeholder instead of being
persisted verbatim.

## Scheduling

Schema-v5 scheduler reads merge contract tasks with runtime state. Compact
status now exposes:

- `ready`: tasks that can advance now;
- `parallel_ready`: the same ready set, ordered by runtime priority;
- `blocked`: task targets that cannot advance now;
- `blocked_details`: dependency, explicit-block, artifact, independent-review,
  and confirmation reasons plus downstream propagation.

The scheduler explains blockers but does not waive them. A task blocked by an
artifact or independent review will not be advertised as ready only to fail on
`task start`.

## Migration

Use explicit schema-v5 migration commands:

```sh
plugins/work-governance/scripts/workctl migrate inspect
plugins/work-governance/scripts/workctl migrate apply --dry-run
plugins/work-governance/scripts/workctl migrate apply \
  --confirmation C-MIGRATION-SCHEMA-V5 \
  --expected-contract-revision <revision>
plugins/work-governance/scripts/workctl migrate recover --migration-id MIG-YYYYMMDD-NNN
plugins/work-governance/scripts/workctl migrate rollback-info --migration-id MIG-YYYYMMDD-NNN
plugins/work-governance/scripts/workctl doctor
```

`migrate inspect`, `migrate apply --dry-run`, `migrate rollback-info`, and the
default `doctor` report do not write project state and do not require a
SessionStart READY receipt. Durable `migrate apply`, `migrate recover`,
`evidence capture`, and `doctor --clean-stale-transactions` are receipt-bound
mutations. Apply writes backup, staging, runtime state, event ledger, and
journal data before replacing the active Plan. Durable apply accepts only the
exact `C-MIGRATION-SCHEMA-V5` gate; unrelated accepted confirmations cannot
authorize migration. Recovery rolls forward only the authenticated migration
journal. `rollback-info` exposes backup paths and manual recovery boundaries;
it is not an automatic rollback command.

`doctor --clean-stale-transactions` cleans only stale generic runtime
transaction directories that have no journal. It never deletes schema-v5
migration journals or backup/staging bundles; incomplete migration journals
must be recovered or investigated.

## Validation

Before presenting the candidate for activation, run:

```sh
uv run ruff check .
uv run mypy
uv run pytest
uv run python plugins/work-governance/scripts/generate_cli_reference.py --check
```

Activation requires a separate fresh-session validation after the user accepts
the candidate.

Candidate activation evidence must include a review record or explicit degraded
review explanation, a test report, and a replay validation summary. Unit tests
alone do not prove live plugin activation.

The temporary pre-activation Codex evaluation is recorded in
`docs/WORK_GOVERNANCE_1_1_0_TEMP_EVAL.md`. That report validates the isolated
candidate controller and temporary Codex installation path, but it intentionally
does not claim live activation.

## Confirmation Gate

Stop before live activation and ask for:

```text
CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0
```

Do not install, reinstall, enable, disable, switch, publish, push, tag, or
mutate remote state without that explicit confirmation and the matching
high-impact authority path.
