# L2 Plan Control

Use Plan control when the work affects future execution, handoff, task queues,
facts, confirmation gates, artifacts, acceptance criteria, or rollback state.

## Authority discovery

Every project uses a single active execution authority under a separately
validated project layout. Before Plan-controlled work, require a current READY
bootstrap receipt, require `layout status` to report `LAYOUT_READY`, then the
Agent discovers:

- a Plan explicitly named by the current user;
- a Plan designated as current, authoritative, or mandatory by `AGENTS.md` or
  `CLAUDE.md`;
- the active Plan located by `.work-governance/_Plan/index.yaml`;
- conventional paths such as `Plan.md` and `docs/Plan.md` as candidates only;
- historical sources already recorded in migration lineage.

Classify open text as:

- `CONFIRMED_AUTHORITY` only when the user or project rules explicitly grants
  current execution authority;
- `LIKELY_AUTHORITY` when the document claims current or sole authority and
  also controls multiple execution surfaces such as goals, phases, queue,
  gates, stop conditions, or next steps;
- `NON_AUTHORITY` for designs, phase plans, evidence, logs, archives, completed
  Plans, and valid migration pointers.

Filenames, "next step" text, Git history, and a phase proposal never confirm
authority by themselves. Pass an Agent classification to `plan authority
inspect --candidate PATH=CLASSIFICATION` when project rules cannot encode the
semantic decision.

The controller validates existence, SHA256, Plan revision, Git baseline,
confirmation references, archived bytes, pointer state, lineage, and migration
journals. Its states are:

- `UNMANAGED_EMPTY`: no authority; transactional `plan admit apply` is allowed.
- `MIGRATION_REQUIRED`: only a confirmed historical authority exists.
- `AUTHORITY_REGISTRATION_REQUIRED`: an indexed legacy Plan lacks authority
  metadata.
- `AUTHORITY_REVIEW_REQUIRED`: a likely second authority needs human review.
- `RECONCILIATION_REQUIRED`: confirmed authorities compete.
- `GOVERNED_ACTIVE`: exactly one canonical authority and valid lineage exist.
- `MIGRATION_RECOVERY_REQUIRED`: a journal is incomplete or deterministic
  migration evidence is invalid.

Prefer this exact form for new user decisions:
`user:session/<SessionId>/turn/<TurnId>/sha256/<digest>`. The digest should bind
the exact user message bytes or an immutable evidence manifest. Existing typed
references remain valid; this is a provenance-strength preference, not a
retroactive schema migration.

Only `GOVERNED_ACTIVE` permits ordinary Plan writes or real task progress. All
other states are fail-closed and permit only inspection, schema/full
validation, reconciliation, and recovery.

Plan files:

- `.work-governance/_Plan/index.yaml`: active plan index.
- `.work-governance/_Plan/<plan-id>.md`: Markdown with YAML frontmatter as the only machine
  authority.
- `.work-governance/_Plan/archive/<migration-id>/`: immutable original migration sources.
- `.work-governance/_Plan/.migrations/<migration-id>.yaml`: recoverable transaction journal.
- `.work-governance/_Plan/.rollovers/<rollover-id>.yaml`: recoverable terminal-Plan rollover
  journal.
- `.work-governance/_Plan/.retirements/<retirement-id>.yaml`: recoverable
  active-Plan retirement journal; its sibling directory preserves the exact
  original and staged retired bytes.
- `.work-governance/_Plan/.evidence/<plan-id>/<sha256>.json`: versionable,
  immutable canonical evidence metadata.
- `.work-governance/logs/`: append-only local process detail, never completion
  evidence.

The project-root `_Plan/` is not an authority candidate after layout 1.0. Only
the bootstrap legacy classifier may inspect it. Layout state is independent
from Plan authority:

- `LAYOUT_READY`: the version and ignore contracts are committed.
- `LEGACY_CLASSIFICATION_REQUIRED`: old-root evidence is incomplete or mixed.
- `LAYOUT_MIGRATION_REQUIRED`: a safe bootstrap action remains.
- `LAYOUT_RECOVERY_REQUIRED`: a durable layout transaction must recover.
- `RECONCILIATION_REQUIRED`: old and new authorities coexist.
- `LEGACY_ROOT_REAPPEARED`: old Plugin behavior recreated a governed old root.
- `ENVIRONMENT_BLOCKED`: the layout, receipt, trust, dependency, or control
  path is invalid.

Only `layout status|validate|migrate|recover` are available until
`LAYOUT_READY`. During SessionStart, these layout mutations may use only the
exact controller and digest bound by the current ignored
`runtime/bootstrap-capability.json`; that capability never authorizes Plan
writes. No-Plan bootstrap does not create a Plan or index.

Schema-v4 Plans carry:

- a goal statement and measurable success conditions;
- a revisioned, confirmation-bound demand contract;
- append-only intake protocol v1 records bound to trusted current turns;
- first-class unknowns with owner, impact, exact blockers, expected evidence,
  and task-level compatibility projection;
- validation provenance;
- structured `scope.exclude` dispositions;
- `delivery.status`, boundary, and evidence;
- `activation.status`, current and target references, and its decision or
  confirmation reference;
- route state `active`, `awaiting_confirmation`, or `terminal`.

Schema version is immutable through ordinary Plan revision. An active
schema-v3 Plan is readable but ordinary writes fail closed with
`PLAN_CONTRACT_UPGRADE_REQUIRED`; use the recoverable
`plan contract upgrade apply|recover` transaction with an embedded
current-turn intake proposal. A completed inactive
schema-v3 Plan remains readable historical evidence.

`deferred`, `pending_confirmation`, and `in_progress` activation block terminal
closeout. A terminal route requires complete delivery and either verified
activation or an explicitly confirmed `not_required` or `declined`
disposition.

Controller gates:

- authority state must be `GOVERNED_ACTIVE` for ordinary writes;
- expected revision must match before writes;
- active Plan scope must not conflict with the requested Plan;
- task dependencies must be `verified` before dependent task start;
- confirmation references must exist and be accepted before high-impact steps;
- suspect, quarantined, or rollback-pending artifacts block closeout;
- only a task that explicitly lists affected IDs in `resolves_artifacts` may
  progress while all blocking artifacts are `suspect`; quarantine and
  rollback-pending states never use this exception;
- task state changes follow the controller transition graph; a pending task
  cannot be declared verified without first entering execution;
- logs are append-only and must not overwrite existing entries, but log hashes
  cannot certify terminal state.

Allowed structural changes:

- `plan authority inspect|check`: inspect candidates or return the current
  authority state.
- `plan admit apply --manifest ...`: validate the exact prepared schema-v4 Plan
  and accepted admission reference plus embedded current-turn intake, inject
  the first record in staging, bind request/turn/basis/record/target digests,
  install the strict Plan, and activate the index last.
- `plan admit recover`: deterministically roll an interrupted admission
  forward. `plan init` is not a normal public admission path.
- `plan confirmation add`: create a pending or explicitly accepted gate before
  a later decision depends on it.
- `plan schema-validate`: validate one candidate document without granting it
  authority.
- `plan validate`: validate schema, index, unique authority, lineage, archives,
  pointers, confirmations, and migration state.
- `plan reconcile apply --manifest ... --dry-run`: show normalized sources,
  hashes, target, a stable proposal digest, required confirmations, and the
  exact `AGENTS.md` diff with its own digest.
- `plan reconcile apply --manifest ...`: after confirmation, prehash and stage
  every input, archive both legacy and unmerged sources, replace their original
  paths with non-authoritative pointers, apply a separately confirmed
  `AGENTS.md` rewrite, write the new Plan, and activate the index last.
- `plan reconcile recover`: idempotently roll an interrupted staged migration
  forward. Recovery never resumes the old queue automatically.
- `plan rollover apply --manifest ... --dry-run`: require the indexed source
  Plan to be complete, terminal, and closeout-ready; verify its ID, revision,
  SHA256 and exact index baseline; validate a new schema-v4 successor; and
  print the stable proposal digest for `C-PLAN-ROLLOVER`.
- `plan rollover apply --manifest ...`: after the digest-bound confirmation,
  preserve the predecessor bytes, record predecessor lineage in the successor,
  stage the successor and replacement index, and activate the index last.
- `plan rollover recover --rollover-id ...`: recheck the journal, predecessor,
  staged target and index hashes, then idempotently finish an interrupted
  rollover. Ordinary work remains frozen in `MIGRATION_RECOVERY_REQUIRED`
  until recovery commits.
- `plan retire apply --manifest ... --dry-run`: require an active schema-v4
  source, verify its ID, revision, SHA256 and exact index baseline, require an
  explicit disposition for every unfinished Plan surface, and print the stable
  proposal digest for `C-PLAN-RETIREMENT`.
- `plan retire apply --manifest ...`: after digest-bound confirmation, preserve
  the exact original bytes, write a distinct `status: retired` record, and
  remove the active index last so authority becomes `UNMANAGED_EMPTY` rather
  than falsely complete.
- `plan retire recover --retirement-id ...`: authenticate the original,
  staged retired Plan, journal, proposal, source and index state, then
  idempotently converge an interrupted retirement. Ordinary work remains
  frozen in `MIGRATION_RECOVERY_REQUIRED` until it commits.
- `plan revise`: increment revision and change structure after confirmation
  when required. Activation, confirmation-bound exclusions, and terminal route
  transitions must use their own field-bound decision; an unrelated accepted
  gate cannot authorize them. Existing task status and task removal are not
  structural patches; use the dedicated task commands. Existing task gates are
  immutable, closeout-affecting evidence/state changes use the current slice
  gate, and resolved exclusion decisions cannot be silently removed or
  rewritten. Existing artifact records are immutable to generic revision so
  their state confirmation and evidence cannot be rebound.
- `plan adapt --manifest ...`: preserve the confirmed goal while changing the
  evidence-backed execution method and recording an immutable revision-history
  entry.
- `plan contract revise --manifest ...`: revise goal or demand-contract
  authority only through its explicit confirmation binding.
- `plan unknown add|resolve`: make an unresolved question explicit, then close
  it only with a subject-matching immutable evidence manifest.
- `plan unknown classify --manifest ...`: repair owner, impact, authoritative
  blockers, expected evidence, and exact task projection on a readable legacy
  schema-v4 unknown.
- `intake receipt`: produce a normalized read-only proposal for the current
  trusted turn and exact target set.
- `plan intake record`: append the proposal idempotently; conflicting content
  for the same request reference is rejected.
- `plan evidence record --manifest ...`: canonicalize bounded typed evidence
  metadata under the active Plan and return its exact path and SHA256.
- `plan confirm`: resolve a pending gate as `accepted` or `declined` with a
  typed authority reference. Generic Plan patches cannot edit confirmations.
- `plan closeout-check|complete`: compute full route readiness and set Plan
  status complete only through the dedicated closeout command; `plan revise`
  cannot assign complete directly.
- `plan verify-entry`: mark one obligation or validation verified only with a
  typed evidence reference, reviewed SHA256, and accepted current-slice gate.
- `plan finalize-artifact`: change an artifact to final only with the same
  evidence binding and an in-progress owning task; suspect artifacts must be
  listed in that task's `resolves_artifacts`.
- `plan artifact-state`: immediately fail safe from pending/final to suspect;
  entering or leaving quarantine/rollback-pending requires the recorded
  recovery confirmation, and stronger states cannot jump directly to final.
- `plan delivery-complete`: complete delivery only after its boundary is known
  and evidence reference/digest are recorded under an accepted slice gate.
- `task start|block|verify|skip`: update task state.
- `log append`: preserve local process detail without granting it completion
  authority.

The reconciliation manifest must identify a new target Plan; every confirmed
or likely source with its Agent-confirmed classification, path, role, SHA256,
and optional revision; the reviewed Git baseline when applicable; and accepted
confirmation records. The baseline confirmation's `evidence_sha256` must equal
the dry-run proposal digest. When routing changes, the independent AGENTS
confirmation's `evidence_sha256` must equal the exact diff digest. Both records
also carry their stable `accepted_at` and user reference. Missing authority
sources, unresolved likely candidates, changed prepared Plans or AGENTS
replacements, source drift, and Git-baseline drift abort before activation.
Recovery rechecks every staged hash and the reviewed Git baseline; the journal
becomes `committed` only after post-activation authority validation succeeds.

A rollover manifest must name a new target Plan and a `ROL-YYYYMMDD-NNN` ID;
record the current Plan path, ID, revision and SHA256; record the index active
ID and SHA256; embed a current-turn intake proposal; hash the prepared
schema-v4 target contract; and bind an accepted
`C-PLAN-ROLLOVER` record to the dry-run proposal digest. The completed
predecessor remains unchanged and becomes non-authoritative by classification;
the strict successor becomes the sole indexed authority and recursively preserves the
predecessor path, ID, revision and SHA256. An `AGENTS.md` or `CLAUDE.md` rule
that explicitly names the predecessor path must be revised under its own
authority before rollover; otherwise the controller rejects the proposal
instead of activating a competing authority.

A retirement manifest must name a `RET-YYYYMMDD-NNN` ID, exact active
schema-v4 Plan path, ID, revision and SHA256, the active index ID and SHA256, a
reason, and explicit dispositions for every unfinished obligation, task,
validation, artifact, unknown, blocking exclusion, pending confirmation,
delivery, activation, route, and handoff surface. `C-PLAN-RETIREMENT` must bind
the dry-run proposal digest. The transaction archives the original bytes,
records the decision without converting unfinished work to verified, writes
the retired Plan, removes the index last, and ends at `UNMANAGED_EMPTY`. A new
route is admitted separately through `plan admit apply`; retirement never
silently resumes or invents a successor queue. Project rules that explicitly
name the retiring Plan path must be revised under their own authority first.

Validation standard: `plan validate` passes; archives hash to the recorded
sources; historical paths are pointers; the index names only the canonical
active Plan; no incomplete journal remains; and the first resumed task is the
first dependency-ready unfinished task in the merged Plan.
