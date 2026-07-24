# L2 Plan Control

Use Plan control when the work affects future execution, handoff, task queues,
facts, confirmation gates, artifacts, acceptance criteria, or rollback state.

## Authority discovery

Every project uses a single active execution authority. Before Plan-controlled
work, the Agent discovers:

- a Plan explicitly named by the current user;
- a Plan designated as current, authoritative, or mandatory by `AGENTS.md` or
  `CLAUDE.md`;
- the active Plan located by `_Plan/index.yaml`;
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

- `UNMANAGED_EMPTY`: no authority; `plan init` is allowed.
- `MIGRATION_REQUIRED`: only a confirmed historical authority exists.
- `AUTHORITY_REGISTRATION_REQUIRED`: an indexed legacy Plan lacks authority
  metadata.
- `AUTHORITY_REVIEW_REQUIRED`: a likely second authority needs human review.
- `RECONCILIATION_REQUIRED`: confirmed authorities compete.
- `GOVERNED_ACTIVE`: exactly one canonical authority and valid lineage exist.
- `MIGRATION_RECOVERY_REQUIRED`: a journal is incomplete or deterministic
  migration evidence is invalid.

Only `GOVERNED_ACTIVE` permits ordinary Plan writes or real task progress. All
other states are fail-closed and permit only inspection, schema/full
validation, reconciliation, and recovery.

Plan files:

- `_Plan/index.yaml`: active plan index.
- `_Plan/<plan-id>.md`: Markdown with YAML frontmatter as the only machine
  authority.
- `_Plan/archive/<migration-id>/`: immutable original migration sources.
- `_Plan/.migrations/<migration-id>.yaml`: recoverable transaction journal.
- `.logs/`: append-only process evidence; add it to `.git/info/exclude` in Git
  projects.

Schema-v3 Plans also carry:

- structured `scope.exclude` dispositions;
- `delivery.status`, boundary, and evidence;
- `activation.status`, current and target references, and its decision or
  confirmation reference;
- route state `active`, `awaiting_confirmation`, or `terminal`.

Schema version is immutable through ordinary Plan revision. Legacy schema
upgrade is performed only by reconciliation; schema-v3 cannot be downgraded to
disable delivery, activation, or exclusion gates.

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
- logs are append-only and must not overwrite existing entries.

Allowed structural changes:

- `plan authority inspect|check`: inspect candidates or return the current
  authority state.
- `plan init`: initialize a governed Plan only from `UNMANAGED_EMPTY`.
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
- `plan revise`: increment revision and change structure after confirmation
  when required. Activation, confirmation-bound exclusions, and terminal route
  transitions must use their own field-bound decision; an unrelated accepted
  gate cannot authorize them. Existing task status and task removal are not
  structural patches; use the dedicated task commands. Existing task gates are
  immutable, closeout-affecting evidence/state changes use the current slice
  gate, and resolved exclusion decisions cannot be silently removed or
  rewritten. Existing artifact records are immutable to generic revision so
  their state confirmation and evidence cannot be rebound.
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
- `log append`: preserve process evidence.

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

Validation standard: `plan validate` passes; archives hash to the recorded
sources; historical paths are pointers; the index names only the canonical
active Plan; no incomplete journal remains; and the first resumed task is the
first dependency-ready unfinished task in the merged Plan.
