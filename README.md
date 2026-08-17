# Work Governance Plugin

Work Governance is a Codex plugin that helps Codex move from an idea or
unclear request to exploration, goal clarification, an auditable plan,
execution, correction, validation, and handoff. The 1.4.0 candidate keeps the
plugin goal-driven and lighter at the interaction boundary: Plan, Skill,
context-package, and direct script behavior support the user goal instead of
turning every turn into a heavy governance ritual.

The repository-local marketplace is `.agents/plugins/marketplace.json` and the
plugin source is `plugins/work-governance`.

This repository can prepare a local 1.4.0 candidate, but candidate preparation
does not install, enable, or switch the user's live Codex plugin. Live
activation remains blocked on `CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_4_0`.
The candidate implements the documented core control plane; it does not claim
that every command named in the architecture draft is already present. Treat
`workctl help <workflow>` and [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) as
the current executable surface.

## Skills

- `work-governance:work-lifecycle` is the mandatory lifecycle entry.
- `work-governance:git-change-governance` controls Git isolation and delivery
  boundaries.
- `work-governance:project-truth-governance` selects durable project authority
  locations.
- `work-governance:independent-validation` challenges plans, artifacts, and
  completion evidence.

## 1.4.0 Lightweight Work Surface

The 1.4.0 candidate turns the useful part of lightweight Socratic planning into
small executable read-only surfaces. Unclear requirements should become a
decision frontier, not a long essay. The model investigates agent-owned facts
first, then asks one path-changing user-owned question with a recommended answer
when a real decision blocks the next target.

`workctl frontier draft --manifest PATH|--stdin` builds a deterministic decision
frontier from an explicit manifest. It records the goal anchor, blocked targets,
agent-owned facts or unknowns, user-owned questions, recommended answers, and a
stable digest without creating Plan authority.

`workctl context lint --manifest PATH|--stdin [--role ROLE]` validates context
manifest paths and role visibility without emitting source content. It rejects
known secret paths before handoff.

`workctl context build --role implement|check|review|truth --manifest PATH|--stdin`
builds a bounded, deterministic context package from explicit project-local
files. It is read-only, works before or during a Plan, records file hashes and
truncation state, and does not install hooks, create Plan authority, or mutate
runtime state.

`workctl work status [--full]` aggregates layout, intake, active Plan queue,
registered `workctl` shim health, and the candidate-release boundary. It makes
the non-activation state explicit so preparing 1.4.0 does not imply the live
Codex plugin has switched from 1.3.0.

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

## Pre-Implementation Contract

For non-trivial work, the Skill layer now requires a compact
pre-implementation contract before mutation. The model must name the goal
anchor, scoped slice, evidence basis, remaining evidence to gather,
user-owned uncertainty and recommended frontier answer when needed, exact
actions or files to touch, validation anchors, and stop or revision triggers.
If no user-owned blocker remains, the agent reports the contract briefly and
continues; if a blocker remains, it asks the smallest frontier question before
implementation.

Slice verification then compares actual results against that contract: intended
action versus actual change, expected evidence versus observed evidence, and
declared stop triggers versus any deviation. This keeps the lightweight path
Socratic and plan-first without moving every rule into the controller before
the behavior has been proven useful.

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

Reviewer acquisition failures are runtime state, not Plan contract changes.
Before retrying an external reviewer, use `review acquisition check` with the
target, mechanism, and reviewed input digest. If the exact reviewer input is in
cooldown, or if the same reviewer mechanism has a fresh environment-level
failure such as proxy, auth, missing command, timeout, or untrusted attestor, it
reports `VALIDATOR_UNAVAILABLE_CACHED` so the agent can stop repeating the same
unavailable path. A failed acquisition can be recorded by piping the redacted
command output into `review acquisition record-failure`; the record stores a
stable failure class, fingerprint, cooldown, and bounded excerpt.
This supports deterministic self-challenge for ordinary reversible local work,
but it never turns unavailable review into verified independent validation.

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

## Candidate Claim And Weak-Link Checks

For candidate releases, migrations, activation handoffs, and governance-rule
changes, Work Governance treats the final wording as an artifact that must be
checked. The claim may describe only the implemented executable surface and the
current validation evidence. Architecture drafts, historical Plans, replay
reports, and adjacent tests are useful context, but they do not prove full
implementation of commands or storage concepts that are not present in
`workctl help <workflow>` and [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md).

High-impact plans should also name weak-link obligations when they touch
documentation, templates, public help, plugin metadata, migrations, activation
steps, rollback information, or handoff wording. These checks run at review or
closeout boundaries and require artifact existence, digest, or freshness
evidence. They are modeled as ordinary obligations/checks so they do not
recreate a second process ledger or per-turn Plan churn.

## Install

Add the repository root as a local marketplace, then install the plugin:

```sh
codex plugin marketplace add /path/to/codex-work-governance
codex plugin add work-governance@work-governance-local
```

After installation, use the registered `workctl` executable directly. The
runtime does not require Codex lifecycle hooks or a project-local UV cache.
Verify the direct entrypoint before governed work:

```sh
command -v workctl
workctl doctor
```

If `workctl` fails before the controller starts with `No such file or
directory` for an old Plugin cache path, the local installation shim is stale.
Use `codex plugin list --json` and, for read-only diagnosis from the candidate
source or enabled cache, `plugins/work-governance/scripts/workctl doctor` to
compare the enabled version with `registered_workctl`. Do not use a derived
source or cache path for Plan mutations; repair or reinstall the registered
executable first.
The plugin source keeps only `hooks/hooks.json` as an empty registry; dormant
Hook implementation scripts are not shipped.
Plugin installation or enabling still does not perform a live activation switch;
activate or replace a live plugin only after a separate confirmation.

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
├── cache/
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

Runtime bootstrap is explicit and hookless. `workctl layout migrate` commits
the layout contract without creating a Plan or index, and `workctl goal init`
admits the first schema-v5 Plan when authority is `UNMANAGED_EMPTY`. Legacy
`bootstrap-state.json`, session receipt, bootstrap capability, and current-turn
receipt files may remain under `.work-governance/` from older installed
versions, but they are compatibility artifacts only. They do not override
`.work-governance/_Plan/index.yaml`, and ordinary schema-v5 commands do not
require them.

The local bootstrap action revision and the versioned legacy layout-migration
revision are independent. Bootstrap action revision 5 introduces the runtime
bundle and receipt v2 while layout version remains 1 and legacy migration
action revision remains 4. When a supported earlier layout action revision is
already committed, direct `workctl layout migrate` treats it as
`LAYOUT_MIGRATION_REQUIRED` and runs a recoverable action upgrade. Action
revision 4 corrects
only active Plan scope entries exactly equal to `_Plan` or `_Plan/`; paths such
as `_Plan/business-output` remain project-owned and unchanged. A changed active
Plan receives one revision bump, the original migration commitment remains
unchanged, and a separate versionable action-upgrade proof is written under
`.work-governance/_Plan/.migrations/`. The local runtime journal and byte
snapshots support deterministic recovery, while `version.yaml` is still written
last. No-Plan layouts upgrade the action contract without creating a Plan.

Hook execution is no longer part of the normal runtime contract. A missing
`SessionStart` or `UserPromptSubmit` hook does not block ordinary local work.
For high-impact decisions, the model still asks at the appropriate boundary
and records the explicit user authority selected by the Plan/controller
workflow. Legacy schema-v4 compatibility paths may still validate explicitly
provided current-turn receipt files, but the preferred route is to migrate
active work to schema-v5.

## Controller

The public CLI entrypoint is the Bash wrapper
`plugins/work-governance/scripts/workctl`; it selects Python >= 3.12 and routes
directly to the private Python transaction engine without `uv run`. The stable
high-frequency workflow surface is available through
`workctl help <workflow>`. The complete parser-generated
command and option reference is [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md);
regenerate it after changing `build_parser()`:

Runtime Python dependencies are solved by the Plugin package, not by the target
project. The installed Plugin carries `scripts/vendor/yaml` from
`pyyaml==6.0.3`, and `workctl.py` prepends `scripts/vendor` to `sys.path`
before loading the controller. Missing or externally resolved PyYAML is treated
as `WORKCTL_PACKAGED_DEPENDENCY_MISSING`; `workctl` does not install packages,
read PEP 723 metadata, or create `.work-governance/cache/uv` at runtime.

```sh
.venv/bin/python plugins/work-governance/scripts/generate_cli_reference.py
.venv/bin/python plugins/work-governance/scripts/generate_cli_reference.py --check
```

Schema v5 separates the durable Plan contract (`goal`, scope, success criteria,
truth references, task definitions, hard dependencies, and confirmation
gates) from ignored runtime state (task status, dynamic priority, current task,
state sequence, event ledger, and redacted evidence snapshots). Reads accept
v1-v4 and v5; new writes use v5. `migrate inspect`, `migrate apply --dry-run`,
`migrate rollback-info`, `frontier draft`, `context build`, `context lint`,
`work status`, and default `doctor` are read-only. Durable
`migrate apply` requires the expected contract revision, archives the legacy
Plan, replaces the active contract atomically, and stages recoverable runtime
state and event bytes. It does not require a fixed migration confirmation and
does not adapt legacy task status into the refreshed runtime state.
`migrate inspect`, dry-run, and durable apply include a non-authoritative
`legacy_summary`, `state_reset`, `legacy_state_migrated: false`,
`not_migrated`, and `next_model_action` so the model can read old progress
without treating it as current runtime authority. After refresh, `plan status`
exposes `legacy_refresh` with the archive path, archive health, and the same
state-reset warning. `migrate recover` can finish an interrupted replacement
and remains guarded by layout, lock, journal, and expected-contract checks.

```sh
workctl intake status
```

For each non-simple request, show a fresh `proceed`, `explore`, or `ask`
decision. Mutable schema-v4 Plan work also generates and records it:

```sh
workctl intake receipt \
  --turn-receipt-sha256 <turn-receipt-sha256> \
  --classification plan_controlled --decision proceed \
  --rationale "<decision basis>" --targets task:T-001
workctl plan intake record \
  --manifest /path/to/intake.json --expected-revision <revision>
```

Schema-v4 advancing commands also require `--turn-receipt-sha256` and
`--expected-intake-sha256`. The latest record must match the current request,
decision basis, and every exact command target. `route` covers all targets;
other target types do not imply cross-layer coverage.
Schema-v5 ordinary exploration, scheduling, evidence recording, task transitions,
and reprioritization do not consume a UserPromptSubmit receipt or persist intake.
They use `state_sequence`, dependency, confirmation, and evidence guards. A
compatibility turn receipt may still be present from older sessions, but
ordinary v5 work does not consume it.
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
some_command | workctl evidence capture \
  --task T-001 \
  --kind command-output \
  --summary "focused validation output" \
  --idempotency-key task-T-001-validation

workctl evidence capture \
  --task T-001 \
  --kind artifact \
  --summary "generated validation report" \
  --from-file reports/validation.json \
  --expected-state-sequence 3
```

Oversized capture input fails closed. Non-UTF-8 binary input is represented by
a digest placeholder instead of being persisted verbatim. Corrupt direct
evidence ledgers fail closed for idempotency checks instead of silently
minting ambiguous records.

Scheduler views are read-only and explain both progress and blockers. Compact
`plan status` includes `ready`, `parallel_ready`, `blocked`, and
`blocked_details`, where blocker details cover dependencies, explicit blocked
state, artifact quarantine/suspect rules, independent-review blocks, and
pending task confirmations.

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
after consumption, and rejects missing, superseded, target-mismatched, expired, or
replayed authority.

For repeated high-impact actions already covered by a clear route decision, use a
bounded route authority lease instead of asking the user for each identical class of
permission. `action lease prepare` prints the exact lease basis digest and typed
`basis_ref`; create and accept an `external_authority` gate for that basis, then
`action lease issue` records the lease in runtime. Each later action still calls
`action lease authorize` to mint a single-use capability and then `action consume`
for the concrete action digest and target. Authorization is idempotent by default;
if the same target and action digest must be retried after a consumed attempt, pass a
new `--idempotency-key` and the lease consumes another bounded authorization slot. A
lease is scoped by kind, exact targets or typed target prefixes, digest policy,
expiry, max authorization count, Plan contract SHA256, and review/artifact blockers.
It reduces repeated confirmation prompts; it does not waive pilot evidence,
validation, execution evidence, activation evidence, or drift checks. The supported
kinds are remote write, production change, destructive operation, secret handling,
and substantive rollback.
This envelope authorizes an action; it does not claim that the external action
succeeded.

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
- a revisioned demand contract with confirmations recorded only when needed;
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

The Plugin release declares one current active Plan schema. This release uses
schema v5. An active V3/V4 or otherwise outdated Plan is readable but reports
`PLAN_SCHEMA_REFRESH_REQUIRED`; ordinary writes remain blocked until
`migrate apply --expected-contract-revision <revision>` archives the legacy Plan
and rebuilds a fresh current-schema contract. The refresh does not adapt legacy
task status, evidence notes, or runtime state. Controller outputs surface
`legacy_summary` before refresh and `legacy_refresh` after refresh only as
`NON_AUTHORITY` guidance for choosing the next current-schema task. Completed
inactive legacy Plans remain readable historical records. Goal or contract changes use
`plan contract revise`; evidence-backed
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

Start Plan-controlled work with the registered `workctl` executable:

```sh
workctl layout status
workctl plan authority inspect
workctl plan authority check
```

Only `LAYOUT_READY` plus `GOVERNED_ACTIVE` permits ordinary Plan writes or task
progress. Before layout readiness, only `layout status`, `layout validate`,
`layout adopt`, `layout migrate`, and `layout recover` are available. The project-root
`_Plan/` is inspected only by the bootstrap legacy classifier and is never a
normal authority candidate or write target.

A strictly recognized old Work Governance layout first requires an explicit
worktree-local adoption receipt:

```sh
workctl layout adopt \
  --expected-manifest-sha256 <digest-from-layout-status> \
  --expected-active-plan-id PLAN-YYYYMMDD-NNN \
  --ref user:<confirmation-reference>
```

The ignored receipt binds the physical project root, linked-worktree Git
identity, active Plan, complete legacy manifest, controller digest, and user
reference. It cannot be replayed from main into a sibling worktree. Generated
historical pointers and `AGENTS.md`/`CLAUDE.md` never authorize adoption, and
layout migration never generates or rewrites project-rule files.

For a recognized legacy layout, direct bootstrap creates only the local
governance infrastructure and reports `LEGACY_CLASSIFICATION_REQUIRED`. Review
`layout status`, run the exact `layout adopt` command above, then run
`layout migrate` again. Later unchanged runs remain incremental.

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
workctl plan admit apply --manifest /path/to/admission.yaml
workctl plan admit recover
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
workctl plan evidence record --manifest /path/to/evidence.yaml
workctl plan validate --evidence-manifest /path/to/evidence.yaml
```

The manifest contains bounded typed metadata, not arbitrary payloads or log
transcripts. The canonical record path and SHA256 must match exactly; later log
appends cannot alter or invalidate the stored evidence.

Reconciliation is manifest-driven:

```sh
workctl plan reconcile apply \
  --manifest /path/to/reconcile.yaml --dry-run
workctl plan reconcile apply \
  --manifest /path/to/reconcile.yaml
workctl plan reconcile recover
```

The transaction verifies source hashes/revisions and an optional Git baseline,
requires each source's semantic classification, binds the migration
confirmation to the dry-run proposal digest, and binds a separate confirmation
to any exact `AGENTS.md` routing diff digest. It archives exact source bytes,
writes non-authoritative pointers with path-correct links, and activates the
new index last. Recovery rechecks staged hashes and the Git baseline.

The historical schema-v3-to-v4 upgrade and composed reconcile-upgrade entries
remain only for recovering or auditing journals created by older releases. New
work must not route active legacy Plans through state-preserving upgrade.
When the active Plan is older than the Plugin-declared current schema, treat it
as read-only input, archive its exact bytes, and rebuild the current schema with
`migrate apply --expected-contract-revision <revision>`.

For historical recovery only, the composed schema-v3 reconciliation plus
schema-v4 upgrade entry remains available:

```sh
workctl plan reconcile-upgrade apply \
  --manifest /path/to/reconcile-upgrade.yaml
workctl plan reconcile-upgrade recover \
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
workctl plan rollover apply \
  --manifest /path/to/rollover.yaml --dry-run
workctl plan rollover apply \
  --manifest /path/to/rollover.yaml
workctl plan rollover recover \
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
workctl plan retire apply \
  --manifest /path/to/retirement.yaml --dry-run
workctl plan retire apply \
  --manifest /path/to/retirement.yaml
workctl plan retire recover \
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
.venv/bin/ruff check .
.venv/bin/mypy --strict plugins/work-governance/scripts/workctl.py tests
.venv/bin/python -m pytest -q
```

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.

The plugin itself does not provide a hosted service or telemetry. See
`PRIVACY.md` and `TERMS.md` for the public policy boundary.
