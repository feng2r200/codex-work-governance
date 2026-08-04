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
`runtime/sessions/<session_id>/bootstrap-capability.json`; that capability never authorizes Plan
writes. No-Plan bootstrap does not create a Plan or index.

Schema-v4 Plans carry:

- a goal statement and measurable success conditions;
- a revisioned, confirmation-bound demand contract;
- a bounded protocol-v2 current intake anchor backed by project-local
  immutable history, with protocol-v1 compatibility;
- first-class unknowns with owner, impact, exact blockers, expected evidence,
  and task-level compatibility projection;
- pending confirmations with a typed `intervention.kind`, exact `blocks`,
  immutable `basis_ref`, and the required `basis_sha256`;
- optional Plan-level `independent_validation` records for Plan challenge,
  artifact review, and evidence audit, including context isolation, reviewed
  digests, findings, and exact audit evidence;
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
- schema-v4 pending confirmations must be `STRICT_READY`; legacy pending gates
  remain readable but cannot decide, advance, or close out until classified;
- every high-impact target named by a required independent review stays blocked
  until the review is verified by a controller-authenticated platform attestor
  and has no unresolved blocker/high findings, or is degraded and separately
  covered by exact evidence-bound risk authority. A pending `plan_challenge`
  without blocker/high findings is advisory only for an ordinary local task
  whose `completion_scope` is local and which has no `requires_confirmation`;
  it never releases delivery, activation, route, a route-scoped task, or a
  confirmation-gated task. Other pending review modes remain blocking. This
  controller exposes no authenticated attestor and therefore rejects `verified`
  instead of trusting caller-authored evidence. A degraded review reserves one
  exact risk-confirmation ID before the confirmation exists, then requires that
  exact pending confirmation to be created and decided after the review; it
  cannot adopt a pre-existing or unrelated authority;
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
- `plan confirmation add`: create a gate with `--intervention-kind`,
  repeatable exact `--blocks`, `--basis-ref`, and the digest required for
  Plan-contract or deviation decisions. A gate intended for `action authorize`
  also carries the exact `--action-kind`. Schema v4 creates it only as pending;
  accepted legacy records remain compatible.
- `plan confirmation classify --manifest ...`: repair one legacy pending gate
  into the strict intervention contract. During the live-controller bootstrap
  only, it may also replace an accepted external-authority placeholder when
  the already-recorded decision evidence digest exactly matches the new basis.
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
- `plan reconcile-upgrade apply --manifest ...`: fully prepare one parent
  workflow, schema-v3 reconciliation target, schema-v4 upgrade target, and both
  authenticated child transactions before mutation; execute only the fixed
  reconciliation-then-contract-upgrade order. Re-run apply after exact parent
  staging was interrupted before parent-journal publication; drifted partial
  staging fails closed.
- `plan reconcile-upgrade recover --workflow-id ...`: authenticate the parent
  binding and existing child journals; validate and fill exact child staging
  when interruption preceded a child journal; then resume only the incomplete
  child and require the exact final schema-v4 authority. A committed call
  performs read-only revalidation and never advances an incomplete child.
  Until both parent and contract-upgrade journals commit, authority reports
  `MIGRATION_RECOVERY_REQUIRED`; ordinary Plan or task writes and fresh
  structural Plan transactions fail closed, while the same bound workflow may
  resume through apply or recover.
- `plan structural-rebase apply --manifest ... --dry-run`: show the exact
  same-Plan source and index hashes, derived target hash, authorization ID, and
  changed fields for one confirmed material route rebase. The manifest may only
  change declared contract/route fields, add pending work, rebind named pending
  confirmations, and move still-pending independent-review blocks.
- `plan structural-rebase apply --manifest ...`: stage the candidate and write
  a durable journal before atomically replacing the indexed active Plan. The
  controller derives a new accepted audit confirmation and contract revision
  from the manifest's exact user authority; completed facts, existing task
  states, decided confirmations, and recorded review evidence remain immutable.
- `plan structural-rebase recover --transaction-id ...`: idempotently complete
  only the named interrupted rebase after rechecking the source/target and index
  hashes. An incomplete journal reports `MIGRATION_RECOVERY_REQUIRED` and
  blocks ordinary work until recovery commits.
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
  for the same request reference is rejected, except for a basis-changing
  `ask|explore -> proceed` supersession or a same-request `proceed` refresh
  after controller-authorized basis drift with identical request, targets,
  rationale, and unknown binding. The Plan retains one current anchor; full
  canonical records remain in project-local immutable runtime history.
- `plan evidence record --manifest ...|--stdin`: canonicalize bounded typed
  evidence metadata under the active Plan and return its exact path and SHA256.
  `task verify --evidence-stdin` performs the same bounded record and task
  transition as one controller command.
- `plan confirm`: resolve a pending gate as `accepted` or `declined` with a
  typed authority reference and the exact basis digest. Generic Plan patches
  cannot edit confirmations, unclassified gates cannot decide, and a pending
  basis placeholder cannot authorize work. Schema-v4 and schema-v5 decisions bind
  the trusted current turn and its exact `request_ref`; schema v4 additionally
  requires current intake covering every blocked target. Schema-v5 confirmation
  revisions are recorded in the event ledger without changing runtime state sequence.
- `plan independent-review record --manifest ...`: record one isolated
  `plan_challenge`, `artifact_review`, or `evidence_audit` against exact
  contract and artifact digests. This is the only command allowed to migrate a
  matching bootstrap review while its declared targets remain review-blocked;
  it cannot mutate the parent Plan contract or reviewed artifacts. Verified
  state requires a future controller-authenticated platform attestor; this
  build fails closed without one, and different context strings or
  caller-authored evidence never satisfy the gate.
- `plan closeout-check|complete`: compute full route readiness and set Plan
  status complete only through the dedicated closeout command; `plan revise`
  cannot assign complete directly. When every non-route obligation is ready,
  `plan complete --finalize-route --confirmation C-...` binds the accepted
  current slice gate and atomically terminalizes route and handoff with Plan
  completion, avoiding a structural intermediate state that would stale intake.
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
- `plan activation-promote`: for schema-v4, enter activation under its accepted
  gate and optionally replace the matching `+codex.pending` plugin placeholder
  with an exact cachebuster while entering `in_progress`; promotion to `active`
  requires canonical evidence whose `observed_ref` equals the frozen target.
  `activation.resolves_exclusions` may bind exact exclusion descriptions to the
  same confirmation; only the successful `active` transition marks them
  `completed` with that decision ref. Legacy Plans without the field receive
  this reconciliation only when exactly one pending exclusion matches the
  activation confirmation; multiple matches fail closed. Gate acceptance alone
  never resolves an exclusion. Generic Plan patches and the active transition
  cannot rebind that target.
- When an undecided external-authority gate was created before its immutable
  candidate existed, re-run `plan confirmation classify` with the exact same
  `kind` and `blocks`, the previous `supersedes_basis_sha256`, and a changed
  exact `basis_ref` plus `basis_sha256`. This may rebind only a still-pending
  strict gate. It cannot change protected targets, revise an accepted decision,
  or serve as evidence that the external action happened.
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
