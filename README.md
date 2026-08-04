# Work Governance Plugin

Work Governance is a Codex plugin that helps Codex move from an idea or
unclear request to exploration, goal clarification, an auditable plan,
execution, correction, validation, and handoff. The 1.1.0 candidate keeps the
plugin goal-driven: Plan, Skill, script, and Hook behavior support the user
goal instead of turning every turn into a heavy governance ritual.

The repository-local marketplace is `.agents/plugins/marketplace.json` and the
plugin source is `plugins/work-governance`.

This repository can prepare a local 1.1.0 candidate, but candidate preparation
does not install, enable, or switch the user's live Codex plugin. Live
activation remains blocked on `CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0`.

## Skills

- `work-governance:work-lifecycle` is the mandatory lifecycle entry.
- `work-governance:git-change-governance` controls Git isolation and delivery
  boundaries.
- `work-governance:project-truth-governance` selects durable project authority
  locations.
- `work-governance:independent-validation` challenges plans, artifacts, and
  completion evidence.

When Git isolation needs a new worktree, the default location is
`<project-root>/.work-governance/worktrees/<task-or-branch-slug>`. Existing
Git-registered legacy `.worktree/<slug>` paths remain at their registered
locations until removed; 1.0 never creates new entries there. An external
worktree path requires an explicit user choice or a verified technical
constraint. Git still writes shared metadata in the repository's common Git
directory, whose permission boundary must also be checked.

## Slice Completion Reporting

After each independently verifiable execution slice, the lifecycle requires an
ordered reply summary covering the slice identifier, completion and purpose,
validation and gaps, material decisions and their basis, modifications, and
the next step. Plan-controlled work uses its `T-ID`; a No-Plan request uses
`NO_PLAN`. In-progress, blocked, unverified, and SubAgent-only results cannot be
reported as completed slices.

## Communication and user intervention

Work Governance separates communication from waiting. Discovery and planning
stay conversational; execution reports progress and completed slices while
continuing through every dependency-ready target covered by the current
route-level `proceed` decision. A task boundary, validation result, phase
change, or stated next step never creates a "continue" gate.

User input is collected only at four boundaries:

- one blocking user-owned requirement unknown (`U-NNN`);
- confirmation of the exact material Plan contract;
- an evidence-proven L5 direction or recovery decision;
- system, remote, production, destructive, or other external authority.

Agent-owned facts are explored locally. Ordinary failures, evidence gaps, and
reversible implementation adjustments are diagnosed by the Agent. New
confirmations use machine-readable `intervention` metadata with a kind, exact
blocked targets, typed basis, and the required basis digest; generic
continuation gates are invalid.

`plan status` projects both the intervention-contract readiness and the exact
current user-intervention state. A future live-switch gate may block only its
target task, activation, and route while earlier local work remains active.

High-impact Plans also carry per-mode independent review records for Plan
challenge, artifact review, and evidence audit. The controller preserves
reviewer isolation, reviewed digests, findings, and evidence; unresolved
blocker/high findings stop their declared downstream targets. Same-context or
unproven isolation is `degraded` and cannot support high-impact completion
without separately accepted, evidence-bound risk authority.

## Goal-first stop-loss

Work stays anchored to the user-visible target rather than test volume. After
the smallest viable slice, the lifecycle prefers the cheapest safe real
boundary probe. New tests must come from a confirmed obligation, observed
failure, code invariant, or supported integration boundary; exhaustive
coverage and invented scenarios are not delivery goals.

A failed action cannot be repeated with materially identical inputs and state.
One changed-input retry is allowed only with an expected evidence delta. Two
consecutive attempts without material evidence or target progress produce
`INEFFECTIVE_LOOP_DETECTED`, freeze downstream work, and require an L5
root-cause challenge. Monitoring and explicit wait requests remain valid when
unchanged external state is the evidence being requested.

Before a fix is selected, the lifecycle separates the symptom, falsifiable
cause hypothesis, causal chain, contradicting evidence, and discriminating
probe. It then compares materially plausible containment, causal correction,
and alternate routes so a workaround is not mislabeled as a root-cause fix.

## Install

Add the repository root as a local marketplace, then install the plugin:

```sh
codex plugin marketplace add /path/to/codex-work-governance
codex plugin add work-governance@work-governance-local
```

Review and trust the bundled SessionStart hook, then start a new Codex thread.
Plugin installation or enabling does not itself trust non-managed hooks.

## Project Layout

Work Governance 1.0 owns exactly one project-level root:

```text
.work-governance/
├── version.yaml
├── .gitignore
├── _Plan/
│   └── .evidence/<plan-id>/<sha256>.json
├── logs/
├── worktrees/
├── cache/uv/
├── proposals/
├── evidence/
├── runtime/
├── bootstrap-state.json
└── workctl.lock
```

`_Plan/` (including immutable evidence records), `version.yaml`, `.gitignore`,
and committed migration proofs are versionable. The exact
`.work-governance/.gitignore` ignores only `logs/`,
`worktrees/`, `cache/`, `proposals/`, `evidence/`, `runtime/`,
`bootstrap-state.json`, and `workctl.lock`. A No-Plan bootstrap creates the
layout contract and local infrastructure but no Plan or index.

Canonical runtime identity is session-scoped under
`.work-governance/runtime/sessions/<session_id>/`: `bootstrap-state.json`,
`bootstrap-capability.json`, and `current-turn-receipt.json`. The root
bootstrap receipt and the old runtime capability/current-turn paths remain
compatibility surfaces for older installed sessions; a newer session never
overwrites a READY or current-turn compatibility record owned by another
session. Always use the exact receipt digest emitted by the hook instead of
deriving a path or choosing the newest file.

The SessionStart hook is a short wakener. Its standard-library runner
fingerprints the bootstrap action, installed Plugin payload, and relevant
project layout inputs. Before issuing READY it snapshots the exact controller
and `work-lifecycle` skill into
`.work-governance/runtime/plugin-builds/<plugin-manifest-sha256>/`, then binds
receipt schema v2 to those paths and hashes plus the current session. It
first writes an ignored
`.work-governance/runtime/sessions/<session_id>/bootstrap-capability.json` with
`BOOTSTRAPPING` state. That capability authorizes only the exact bundled
controller to perform layout migration or recovery for this SessionStart; it
cannot authorize Plan or other ordinary writes. A same-session SessionStart
replaces it, so an older capability for that session fails closed; capabilities
from different sessions neither authorize nor supersede one another.
The hook then prewarms the controller's pinned PEP 723 dependency
in `.work-governance/cache/uv`, trying the existing cache offline before using
permitted dependency access, disables Python downloads, and runs migration,
validation, and status commands offline. Exact Plugin builds and incremental
state live in the ignored session-scoped bootstrap receipt; detailed command
evidence stays under `.work-governance/evidence/`. The runtime snapshot remains
available if the Codex Plugin cache entry is replaced or removed after
SessionStart.

When a same-session compaction emits another SessionStart and the trusted
runtime identity is unchanged, the hook preserves the exact READY receipt
bytes. The active turn therefore remains valid. A structural or build identity
change produces a new receipt and correctly invalidates the prior turn.

The local bootstrap action revision and the versioned legacy layout-migration
revision are independent. Bootstrap action revision 5 introduces the runtime
bundle and receipt v2 while layout version remains 1 and legacy migration
action revision remains 4. When a supported earlier layout action revision is already committed, the next
SessionStart treats it as `LAYOUT_MIGRATION_REQUIRED` and runs a recoverable
action upgrade before issuing a new `READY` receipt. Action revision 4 corrects
only active Plan scope entries exactly equal to `_Plan` or `_Plan/`; paths such
as `_Plan/business-output` remain project-owned and unchanged. A changed active
Plan receives one revision bump, the original migration commitment remains
unchanged, and a separate versionable action-upgrade proof is written under
`.work-governance/_Plan/.migrations/`. The local runtime journal and byte
snapshots support deterministic recovery, while `version.yaml` is still written
last. No-Plan layouts upgrade the action contract without creating a Plan.

If no SessionStart hook ran because it is untrusted, disabled, skipped by
managed policy, or absent, a current `READY` receipt cannot be established and
Plan-controlled work is `ENVIRONMENT_BLOCKED`. If the hook itself emits an
`ENVIRONMENT_BLOCKED` result, that output proves the hook ran: it reports
`hook=executed`, the startup or resume source, the observed failure, a local
evidence reference, the exact capability-bound `layout_command_prefix` when
layout recovery is available, and the cause-specific next recovery action. The
prefix is valid only for layout commands and is not a READY receipt. Do not
reinterpret such output as a hook-trust failure. Restore the reported
precondition and obtain a current `READY` receipt in a fresh session.

Every trusted `UserPromptSubmit` atomically replaces its session-scoped
`.work-governance/runtime/sessions/<session_id>/current-turn-receipt.json`.
The ignored receipt binds
the installed build, current SessionStart receipt hash, official `session_id`
and `turn_id`, exact UTF-8 prompt SHA256, project root, and
`request_ref=user:session/<session>/turn/<turn>/sha256/<prompt-sha256>`. A new
turn supersedes the old receipt without creating a project history log.
Missing, disabled, mismatched, or stale hooks block Plan advancement; simple
No-Plan answers remain ephemeral and create no Plan, index, or project log.

## Controller

The public CLI entrypoint is the Bash wrapper
`plugins/work-governance/scripts/workctl`; it routes to the receipt-bound
private Python transaction engine. In a governed session, use the exact
controller path and receipt emitted by SessionStart. The stable
high-frequency workflow surface is available through
`<receipt-bound-workctl> help <workflow>`. The complete parser-generated
command and option reference is [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md);
regenerate it after changing `build_parser()`:

```sh
.venv/bin/python plugins/work-governance/scripts/generate_cli_reference.py
.venv/bin/python plugins/work-governance/scripts/generate_cli_reference.py --check
```

Schema v5 separates the durable Plan contract (`goal`, scope, success criteria,
truth references, task definitions, hard dependencies, and confirmation
gates) from ignored runtime state (task status, dynamic priority, current task,
state sequence, event ledger, and redacted evidence snapshots). Reads accept
v1-v4 and v5; new writes use v5, while `migrate inspect` is read-only and
`migrate apply` requires an explicit confirmation, expected contract revision,
backup, atomic replacement, and recoverable staging.

Run only the exact `intake_command` emitted by the current SessionStart. It uses
`controller_ref`, `controller_sha256`, and `receipt_sha256` from the READY
receipt; do not derive a controller from a repository or Plugin-cache path:

```sh
uv run --no-project --offline --cache-dir .work-governance/cache/uv \
  --no-python-downloads --script <absolute-runtime-controller> \
  --receipt-sha256 <current-receipt-sha256> intake status
```

Use the same absolute controller and receipt digest for subsequent commands.
Every write is bound to that session's receipt; after a replacement
SessionStart for the same session, the old receipt is superseded. An unrelated
session cannot supersede it. The bootstrap-only capability
described above is a separate fail-closed channel for SessionStart layout
mutation and never satisfies this READY requirement.

For each non-simple request, show a fresh `proceed`, `explore`, or `ask`
decision. Mutable schema-v4 Plan work also generates and records it:

```sh
<receipt-bound-workctl> intake receipt \
  --turn-receipt-sha256 <turn-receipt-sha256> \
  --classification plan_controlled --decision proceed \
  --rationale "<decision basis>" --targets task:T-001
<receipt-bound-workctl> plan intake record \
  --manifest /path/to/intake.json --expected-revision <revision>
```

Schema-v4 advancing commands also require `--turn-receipt-sha256` and
`--expected-intake-sha256`. The latest record must match the current request,
decision basis, and every exact command target. `route` covers all targets;
other target types do not imply cross-layer coverage.
Schema-v5 ordinary exploration, scheduling, evidence recording, task transitions,
and reprioritization do not consume a UserPromptSubmit receipt or persist intake.
They use the SessionStart READY receipt plus `state_sequence`, dependency,
confirmation, and evidence guards. A compatibility turn receipt may still be
emitted while mutable schema-v4 writes remain supported, but ordinary v5 work
does not consume it.
Non-simple No-Plan work keeps only the current runtime receipt and visible
reply; it does not call the Plan controller or persist an intake record.
Intake rationale records only a minimal decision summary; never copy raw prompt
content, credentials, tokens, or other secrets into the Plan.

Direct evidence capture does not require the model to hand-author an evidence
manifest. The controller reads stdin or a project-local file, applies
conservative redaction, writes the redacted bytes to
`.work-governance/evidence/blobs/<sha256>`, writes content-addressed metadata
to `.work-governance/evidence/records/<sha256>.json`, appends metadata to
`.work-governance/evidence/ledger.ndjson`, and returns an `evidence_ref`.
For schema-v5 Plans, task-bound capture updates only runtime state and event
ledger entries; it does not rewrite the Plan contract:

```sh
some_command | <receipt-bound-workctl> evidence capture \
  --task T-001 \
  --kind command-output \
  --summary "focused validation output" \
  --idempotency-key task-T-001-validation

<receipt-bound-workctl> evidence capture \
  --task T-001 \
  --kind artifact \
  --summary "generated validation report" \
  --from-file reports/validation.json \
  --expected-state-sequence 3
```

Protocol-v2 Plans keep one bounded `intake.current` anchor and a history head
plus count. Complete canonical records are stored as ignored,
content-addressed files below
`.work-governance/runtime/intake-history/<plan-id>/`. Existing protocol-v1
Plans remain valid and migrate on their next intake write. A same-request
`ask|explore -> proceed` transition is accepted only when its decision basis
changes and the new record explicitly supersedes the prior digest;
rationale-only or same-basis mutation remains `INTAKE_REQUEST_CONFLICT`.

Controller writes wait only for the configured bounded interval on
`.work-governance/workctl.lock`. Timeout diagnostics include the last observed
holder PID and acquisition time when available. Tests may reduce the interval
with `WORK_GOVERNANCE_LOCK_TIMEOUT_SECONDS`; normal callers use the supported
default.

The controller uses `.work-governance/_Plan/index.yaml` only to locate the
active Plan. `.work-governance/_Plan/<plan-id>.md` frontmatter is the sole
mutable execution authority. The
controller enforces one active execution authority, expected revisions,
dependency and confirmation gates, migration lineage, artifact quarantine
states, atomic Plan writes, recoverable Plan admission, reconciliation and
terminal Plan rollover, explicit active-Plan retirement, terminal closeout,
and immutable evidence records.

Confirmations are created through `plan confirmation add` with a typed
intervention kind, exact blocked targets, and an immutable basis;
`plan confirmation classify --manifest ...` repairs a readable legacy pending
gate. Decisions are made through `plan confirm`, may be `accepted` or
`declined`, and must bind the required basis digest. Schema-v4 gates are always
created pending; their decisions require a current intake covering the blocked
targets plus the trusted current turn's exact `request_ref`. Schema-v5 decisions
also require that exact trusted turn and basis, but do not recreate Plan intake.
Activation,
confirmation-bound exclusions, and
terminal-route transitions are bound to their own decision ID; another
accepted gate cannot authorize them. Activation declared `active` also
requires typed, current runtime evidence whose `observed_ref` exactly matches
the frozen target. For schema-v4 Plans, when an accepted activation still names
its matching `plugin:<name>@<version>+codex.pending` placeholder,
`plan activation-promote --state in_progress --target-ref <exact-ref>` binds
the same plugin/version prefix to one non-pending cachebuster under the
activation gate. Generic Plan patches and the later `active` transition cannot
rebind that target. Generic Plan patches also cannot rebind an activation gate,
remove an existing task, change an existing task's status, or assign Plan
status `complete`; existing task gates and resolved exclusion decisions are
stable, while delivery/evidence/route mutations bind to the current slice
gate. Completion uses the dedicated closeout command.

External high-impact work uses `action authorize` immediately before execution and
`action consume` for the exact action. The authorization records only action kind,
typed target, action SHA256, Plan contract SHA256, trusted session/turn identity,
expiry, and consumption state. Issuance requires a same-turn accepted
`external_authority` Plan gate whose basis action kind, reference, and digest exactly
match the action kind, target, and action; substantive rollback uses a matching
`deviation_recovery` gate. It is short-lived, cannot be reminted from the same turn
after consumption,
and rejects missing, superseded, target-mismatched, expired, or replayed authority.
The supported kinds are remote write, production change, destructive operation,
secret handling, and substantive rollback. This envelope authorizes an action; it
does not claim that the external action succeeded.

Schema v4 cannot be downgraded through ordinary revision. Verified
obligations/validations, final artifacts, and completed delivery use dedicated
commands that validate a bounded canonical evidence manifest stored under
`.work-governance/_Plan/.evidence/<plan-id>/<sha256>.json`; mutable process logs
cannot self-certify completion. Generic structural patches cannot self-promote
these states. Once an activation decision is resolved,
target/current/evidence changes require that activation's own gate.
Artifacts can fail safe from final to suspect; quarantine/rollback-pending
transitions retain a recovery gate and cannot jump directly to final. Suspect
finalization also requires the in-progress task that declares recovery
ownership. Existing artifact records cannot be rewritten by generic Plan
patches.

New Plans use schema v5 to separate durable contract concerns from runtime state:

- a stable goal statement and measurable success conditions;
- a revisioned demand contract bound to an accepted confirmation;
- a bounded current intake anchor backed by project-local immutable,
  hash-linked records for trusted user turns;
- open or resolved unknowns with `owner`, `impact`, authoritative `blocks`,
  and non-empty expected evidence;
- task-level expected evidence deltas;
- validation provenance from a confirmed obligation, observed failure, code
  invariant, or supported integration boundary;
- the current execution slice;
- local or integrated delivery state;
- route-level activation state and current/target references;
- structured exclusions that are not required, deferred, confirmation-bound,
  transferred, or forbidden.

An active schema-v3 Plan is readable but reports
`PLAN_CONTRACT_UPGRADE_REQUIRED`; ordinary writes remain blocked until
`plan contract upgrade apply --manifest <upgrade.yaml>` completes or
`plan contract upgrade recover` deterministically rolls the transaction
forward. The upgrade manifest embeds the current-turn intake proposal, and the
staged schema-v4 target binds its first record in the recovery journal.
Completed inactive schema-v3 Plans remain readable historical
records. Goal or contract changes use `plan contract revise`; evidence-backed
method changes that preserve the goal use `plan adapt`. Unknowns are managed
through `plan unknown add`, `plan unknown classify`, and
`plan unknown resolve`. `plan status` reports independent contract, intake,
unknown-contract, intervention-contract, and exact current user-intervention
state axes. Required Plan challenge, artifact review, and evidence audit
records are installed through `plan independent-review record --manifest ...`;
same-context review is recorded only as degraded and unresolved blocker/high
findings preserve every declared downstream block. Different context strings
or caller-authored canonical records do not prove isolation. Verified state
requires a controller-authenticated platform attestor; because this build has
no such attestor, it rejects `verified` and permits only the separately
risk-accepted `degraded` route. Review evidence bytes are revalidated before
any target release. Each degraded record reserves one exact risk-confirmation
ID, rejects any pre-existing ID, and can be released only when that same ID is
then created pending and decided through current-turn `plan confirm`; the controller never scans
for a matching accepted authority. Bootstrap mappings accept only canonical
evidence whose subject equals the mapped target.

Missing authority for a live action creates a pending confirmation and keeps
the project route open. It cannot be converted into an absolute no-next claim
by placing the action in `scope.exclude`.

Start Plan-controlled work with the exact receipt-bound controller prefix from
the current `intake_command`:

```sh
<receipt-bound-workctl> layout status
<receipt-bound-workctl> plan authority inspect
<receipt-bound-workctl> plan authority check
```

Only `LAYOUT_READY` plus `GOVERNED_ACTIVE` permits ordinary Plan writes or task
progress. Before layout readiness, only `layout status`, `layout validate`,
`layout adopt`, `layout migrate`, and `layout recover` are available. The project-root
`_Plan/` is inspected only by the bootstrap legacy classifier and is never a
normal authority candidate or write target.

A strictly recognized old Work Governance layout first requires an explicit
worktree-local adoption receipt:

```sh
<receipt-bound-workctl> layout adopt \
  --expected-manifest-sha256 <digest-from-layout-status> \
  --expected-active-plan-id PLAN-YYYYMMDD-NNN \
  --ref user:<confirmation-reference>
```

The ignored receipt binds the physical project root, linked-worktree Git
identity, active Plan, complete legacy manifest, controller digest, and user
reference. It cannot be replayed from main into a sibling worktree. Generated
historical pointers and `AGENTS.md`/`CLAUDE.md` never authorize adoption, and
layout migration never generates or rewrites project-rule files.

On the first RC session for a recognized legacy layout, SessionStart creates
only the local governance infrastructure and fails closed with
`LEGACY_CLASSIFICATION_REQUIRED`. Review `layout status`, run the exact
`layout adopt` command above, and start a new session. That new session may
complete the migration; later unchanged sessions remain incremental and
offline.

After adoption, migration runs through a durable transaction: stable new lock,
legacy lock, complete manifest and Git baseline, staged field-level conversion,
staged validation, old-root backup, new Plan activation, and `version.yaml`
commitment last. Interruptions before activation can discard staging; once
activation starts, recovery only rolls forward.

A legacy `_Plan/proposals/` side tree is migratable only when every
`MIG-YYYYMMDD-NNN` directory satisfies the closed reconciliation proposal
contract: a valid manifest, a supported prepared Plan, validated source
records, optional validated Git/AGENTS proposal metadata, no symlink or extra
entry, and an empty pending confirmation map. The transaction preserves its
bytes and pending state, proves its manifest separately, and activates it at
`.work-governance/proposals/`; it never places proposals under the canonical
Plan root, applies an AGENTS replacement, or accepts the proposal.

The directory name `proposals/` alone is not ownership evidence. Confirmed,
malformed, mixed, drifting, or symlinked proposal content remains
`LEGACY_CLASSIFICATION_REQUIRED` for explicit review rather than being guessed
into the migration.

Partial, mixed, symlinked, coexisting, drifted, or incomplete-journal layouts
fail closed. Ordinary business `_Plan/` content is left untouched.

Legacy, ambiguous, competing, or interrupted authority returns a fail-closed state.
Use `plan schema-validate` for a candidate document, `plan validate` for the
full project contract, and `plan status` for authority candidates, blockers,
obligations, validations, confirmations, artifacts, route, handoff, and
closeout readiness. Status also reports delivery, activation, and
`completion_claims`; only `no_required_next_step_allowed=true` supports a
terminal no-next statement.

Creating initial authority is also manifest-driven. `plan init` is not a
normal admission path:

```sh
<receipt-bound-workctl> plan admit apply --manifest /path/to/admission.yaml
<receipt-bound-workctl> plan admit recover
```

Admission validates the prepared schema-v4 Plan, its exact hash, accepted
confirmation, and embedded current-turn intake proposal. It injects the first
record only in staging, binds request, turn receipt, decision basis, intake
record and target Plan hashes in the durable journal, installs the strict Plan,
and activates `.work-governance/_Plan/index.yaml` last. Recovery authenticates
the bound journal without pretending that the recovery turn is the original
request.

Completion evidence is recorded separately before it is consumed:

```sh
<receipt-bound-workctl> plan evidence record --manifest /path/to/evidence.yaml
<receipt-bound-workctl> plan validate --evidence-manifest /path/to/evidence.yaml
```

The manifest contains bounded typed metadata, not arbitrary payloads or log
transcripts. The canonical record path and SHA256 must match exactly; later log
appends cannot alter or invalidate the stored evidence.

Reconciliation is manifest-driven:

```sh
<receipt-bound-workctl> plan reconcile apply \
  --manifest /path/to/reconcile.yaml --dry-run
<receipt-bound-workctl> plan reconcile apply \
  --manifest /path/to/reconcile.yaml
<receipt-bound-workctl> plan reconcile recover
```

The transaction verifies source hashes/revisions and an optional Git baseline,
requires each source's semantic classification, binds the migration
confirmation to the dry-run proposal digest, and binds a separate confirmation
to any exact `AGENTS.md` routing diff digest. It archives exact source bytes,
writes non-authoritative pointers with path-correct links, and activates the
new index last. Recovery rechecks staged hashes and the Git baseline.

When one user decision must both reconcile schema-v3 authority and immediately
upgrade that exact result to schema v4, use the composed controller entry:

```sh
<receipt-bound-workctl> plan reconcile-upgrade apply \
  --manifest /path/to/reconcile-upgrade.yaml
<receipt-bound-workctl> plan reconcile-upgrade recover \
  --workflow-id RCU-YYYYMMDD-NNN
```

The parent manifest fixes an `RCU-YYYYMMDD-NNN` workflow ID plus the paths and
SHA256 digests of one ordinary reconciliation manifest and one ordinary
contract-upgrade manifest. Apply fully prepares the parent, schema-v3 target,
schema-v4 target, and both child transactions before the reconciliation child
can mutate authority. The legal order is always reconciliation followed by
contract upgrade; each child retains its own authenticated journal and
recovery contract.

If interruption occurs after parent staging but before the parent journal is
published, re-run `apply`. If it occurs after a child stages bytes but before
that child journal is published, parent `recover` validates and fills only
missing exact staging bytes before publishing the missing child journal.
Unexpected paths, symlinks, changed bytes, or changed inputs fail closed.
Recovery then resumes only the incomplete child. An interruption during
reconciliation may leave schema v3 uncommitted or active; an interruption
between children leaves schema v3 active; an interruption during contract
upgrade may leave authenticated schema-v4 bytes active with an uncommitted
upgrade journal. Parent recovery validates the parent binding, child journals,
index, lineage, intake binding, and final schema-v4 hash. A committed recovery
call is read-only validation and cannot advance a forged or incomplete child.
While either the parent or contract-upgrade journal is incomplete,
`plan status` reports `MIGRATION_RECOVERY_REQUIRED`; ordinary Plan and task
mutations and fresh structural Plan transactions remain blocked until the bound
parent recovery commits. Re-running `apply` for that same workflow remains an
idempotent recovery entry.

`plan closeout-check` and `plan complete` include full Plan validation and
enforce route-level terminal completion.

A complete terminal Plan starts a distinct successor through a confirmed
rollover instead of reopening or overwriting the predecessor:

```sh
<receipt-bound-workctl> plan rollover apply \
  --manifest /path/to/rollover.yaml --dry-run
<receipt-bound-workctl> plan rollover apply \
  --manifest /path/to/rollover.yaml
<receipt-bound-workctl> plan rollover recover \
  --rollover-id ROL-YYYYMMDD-NNN
```

The manifest fixes the predecessor ID, revision, path and SHA256, the exact
`.work-governance/_Plan/index.yaml` baseline, a prepared schema-v4 successor
contract, and its embedded current-turn intake. Apply requires
`C-PLAN-ROLLOVER` to carry the dry-run proposal digest.
The transaction preserves the completed predecessor bytes, records recursive
predecessor lineage in the successor, binds the first intake and unsigned
target contract hash, stages the strict successor and replacement index, and
activates the index last. Historical terminal predecessors use their
completion-time contract; only the successor must satisfy the new strict
intake contract. An incomplete rollover freezes ordinary
work in `MIGRATION_RECOVERY_REQUIRED` until the named recovery converges. If
`AGENTS.md` or `CLAUDE.md` explicitly names the predecessor path as authority,
that routing must be separately revised before rollover so it cannot recreate
competing authority after activation.

An obsolete active Plan is retired rather than falsely completed:

```sh
<receipt-bound-workctl> plan retire apply \
  --manifest /path/to/retirement.yaml --dry-run
<receipt-bound-workctl> plan retire apply \
  --manifest /path/to/retirement.yaml
<receipt-bound-workctl> plan retire recover \
  --retirement-id RET-YYYYMMDD-NNN
```

The manifest fixes the active Plan and index hashes, records a reason and an
explicit disposition for every unfinished Plan surface, and binds
`C-PLAN-RETIREMENT` to the dry-run proposal digest. Apply archives the exact
original bytes, records `status: retired` without promoting unfinished work,
and removes the index last. The result is `UNMANAGED_EMPTY`; a fresh route uses
normal Plan admission. Explicit project-rule routing to the retired path must
be revised before retirement.

For repeated work that can amplify a shared defect, bulk authorization waives
only repeated prompts. A pilot task and validation remain dependencies, and
observed quality drift freezes every dependent batch through
`QUALITY_DRIFT_DETECTED`. New user-decision authority references should prefer
`user:session/<SessionId>/turn/<TurnId>/sha256/<digest>`; existing typed
references remain valid.

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
