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

## DevBooks-Derived Skill Hardening

The candidate selectively absorbs ideas from `dev-playbooks-cn` as
Codex-native guidance, not as a parallel authority system. The imported pattern
is lightweight:

- use Value, Impact, Cognition, and Verification as intake decision gates;
- bind each must obligation to an acceptance anchor and evidence boundary;
- model docs, templates, CLI help, migration notes, rollback information,
  activation steps, and handoff wording as weak-link obligations when they are
  in scope;
- keep weak-link and deviation observations in runtime or review evidence until
  they prove a material contract change;
- audit final candidate claims against the executable `workctl help <workflow>`
  and generated `docs/CLI_REFERENCE.md` surface.

The candidate intentionally does not adopt DevBooks change packages, fixed
stage tables, Archiver promotion, non-Codex platform paths, default remote-CI
trigger assumptions, or a rule that the main Codex agent may only orchestrate
SubAgents.

## Evidence Capture

Use direct capture for command output or project-local artifacts:

```sh
some_command | <workctl> evidence capture \
  --task T-001 \
  --kind command-output \
  --summary "validation output" \
  --idempotency-key task-T-001-validation

<workctl> evidence capture \
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

In these examples, `<workctl>` means the registered direct executable from the
installed Plugin, or this source candidate's
`plugins/work-governance/scripts/workctl` wrapper during local validation. Do
not derive a relative `plugins/.../workctl` path from an arbitrary project cwd.

The wrapper selects Python >= 3.12 and invokes `workctl.py` directly. It does
not call `uv run`, does not prewarm script dependencies, and does not maintain a
project-local `.work-governance/cache/uv` directory. Runtime Python dependency
closure is packaged with the Plugin: `scripts/vendor/yaml` contains
`pyyaml==6.0.3`, and `workctl.py` prepends that vendor directory before loading
the controller. If PyYAML is absent from the installed Plugin package or
resolves from outside `scripts/vendor`, the controller fails fast with
`WORKCTL_PACKAGED_DEPENDENCY_MISSING` instead of falling back to a system
package or a local parser.

The legacy canonical Plan evidence path remains supported for compatibility:

```sh
<workctl> plan evidence record --stdin
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

## Reviewer Acquisition

The candidate adds runtime-only reviewer acquisition caching so unavailable
external reviewers do not consume repeated attempts:

```sh
<workctl> review acquisition check \
  --target-ref route \
  --mechanism codex-exec-review \
  --review-input-sha256 <sha256>

codex exec review 2>&1 | \
  <workctl> review acquisition record-failure \
    --target-ref route \
    --mechanism codex-exec-review \
    --review-input-sha256 <sha256> \
    --attempt-ref runtime:reviewer/codex-exec/attempt-1 \
    --exit-code 1

<workctl> review acquisition status
```

`record-failure` stores a redacted bounded excerpt, stable failure class,
failure fingerprint, cooldown, and idempotency key under runtime state. It does
not modify the Plan contract. `check` returns `VALIDATOR_UNAVAILABLE_CACHED`
while the same target, mechanism, and input digest remain in cooldown. For
environment-level classes (`network_proxy_blocked`, `auth_unavailable`,
`command_missing`, `timeout`, and `attestor_untrusted`), `check` also suppresses
fresh attempts for the same reviewer mechanism even when the reviewed input
digest changes; callers must change the mechanism or wait out the cooldown.
`record-failure --dry-run` reports the same rejection without writing runtime
state, so a caller can classify a failure while still seeing an existing
cooldown. This supports deterministic self-challenge only for ordinary
reversible local tasks. Activation, route closeout, external actions, and
confirmation-bound targets remain fail-closed without verified review or
explicit risk acceptance.

## High-Impact Route Authority

The candidate keeps `action authorize` and `action consume` as the exact,
single-use envelope for one high-impact external action. It also adds an
optional route authority lease for repeated same-kind actions after the user
has already accepted a bounded route decision:

```sh
<workctl> action lease prepare \
  --action-kind production_change \
  --target-prefix project:service/example-production/ \
  --allowed-action-sha256 <sha256>

<workctl> action lease issue \
  --confirmation-id C-ROUTE-ACTION-LEASE \
  --basis-sha256 <lease-basis-sha256> \
  --ref <current-request-ref> \
  --turn-receipt-sha256 <current-turn-receipt> \
  --action-kind production_change \
  --target-prefix project:service/example-production/ \
  --allowed-action-sha256 <sha256>

<workctl> action lease authorize \
  --lease-id LEASE-... \
  --action-kind production_change \
  --target-ref project:service/example-production/deploy \
  --action-sha256 <sha256> \
  --idempotency-key deploy-attempt-1
```

The lease is runtime state, not a Plan contract revision. It is scoped by action
kind, exact target refs or typed target prefixes, action digest policy, expiry,
maximum authorization count, Plan contract SHA256, and review/artifact blockers.
Authorization is idempotent by default; a retry of the same target and digest after
consumption must use a new `--idempotency-key` and consumes another lease slot. It
can reduce repeated confirmation prompts, but it does not waive action consumption,
validation evidence, pilot evidence, activation evidence, or drift checks.

## Migration

Use explicit current-schema refresh commands:

```sh
<workctl> migrate inspect
<workctl> migrate apply --dry-run
<workctl> migrate apply --expected-contract-revision <revision>
<workctl> migrate recover --migration-id MIG-YYYYMMDD-NNN
<workctl> migrate rollback-info --migration-id MIG-YYYYMMDD-NNN
<workctl> doctor
```

`migrate inspect`, `migrate apply --dry-run`, `migrate rollback-info`, and the
default `doctor` report do not write project state and do not require Hook
receipts. Durable `migrate apply`, `migrate recover`, `evidence capture`, and
`doctor --clean-stale-transactions` are guarded mutations. Apply treats outdated
active Plans as read-only legacy input: it
writes backup, staging, a versioned archive of the legacy Plan, fresh runtime
state, event ledger, and journal data before replacing the active Plan with the
current schema contract. Durable apply requires the expected contract revision
guard, but it does not require a fixed migration confirmation gate and does not
adapt legacy task status into runtime state. Refresh inspection, dry-run, and
apply expose `legacy_summary`, `state_reset`, `legacy_state_migrated: false`,
`not_migrated`, and `next_model_action` as `NON_AUTHORITY` model guidance.
After refresh, `plan status` exposes `legacy_refresh` with archive health and
the same state-reset boundary. Recovery rolls forward only the authenticated
refresh journal. `rollback-info` exposes archive and backup paths plus manual
recovery boundaries; it is not an automatic rollback command.

`doctor --clean-stale-transactions` cleans only stale generic runtime
transaction directories that have no journal. It never deletes schema refresh
journals, legacy archives, or backup/staging bundles; incomplete refresh journals
must be recovered or investigated.

## Validation

Before presenting the candidate for activation, run:

```sh
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m pytest
.venv/bin/python plugins/work-governance/scripts/generate_cli_reference.py --check
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

The historical 1.0.7 friction re-audit is recorded in
`docs/WORK_GOVERNANCE_1_1_0_HISTORY_FRICTION_AUDIT.md`. It is a release-readiness
mapping, not a claim that every item in the destructive redesign draft is
implemented.

## Confirmation Gate

Stop before live activation and ask for:

```text
CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0
```

Do not install, reinstall, enable, disable, switch, publish, push, tag, or
mutate remote state without that explicit confirmation and the matching
high-impact authority path.
