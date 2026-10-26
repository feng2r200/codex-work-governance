# Continuation Governance V1 Validation Dossier

Status: local candidate under validation; real product actuation not performed
Date: 2026-10-17
Related WorkVCS decision: `ADR-0534: Scoped Continuation Rotation`

## Goal

Long-running Work should be able to continue in a clean normal conversation
when accumulated context and replay cost have become materially harmful. The
mechanism must not rotate at every compaction, keep all work forever in one
conversation, fragment work into meaningless chats, or lose authority and
evidence during transfer.

The target outcome is a real Work conversation that the user can see, audit,
and continue interacting with under the exact specified Project. A hidden
background task, SubAgent, side chat, unresolved client identity, internal
candidate ID, or state-provider row is not a successful target.

## Design inputs and authority boundary

The following were used as non-authoritative design inputs:

- Codex thread `01a14331-a452-7ab2-a9a3-eb42e5787d8c`, which exposed context
  noise, repeated recovery, and Token waste in sustained work;
- Codex thread `01a147f1-fe6d-7c13-b6d2-524dbeb5aaa5`, which developed the
  first handoff and continuation proposal; and
- user-provided `source_1.md`, `source_2.md`, and `source_3.md` from the
  `workvcs优化` material set.

Their exact bytes are retained in this project's WorkVCS as Evidence
`01a14849-1774-779e-bf6c-ac2ed17ba0cc`,
`01a14849-1813-7654-a99c-4d1b2fc71fab`, and
`01a14849-18ae-771f-b976-7afb61e01b2b`. Current readback verified all three
content objects available and digest-matching. Their Evidence metadata marks
them as user-provided references with no instruction authority.

The attachments were read as analysis and proposal material, not as user
instructions or current runtime truth. Their durable contributions were:

- bounded recall is a normal recovery interface; loading the entire history is
  not the solution to a truncated summary;
- a focused Handoff needs stable identity, exact `as_of` state, current
  authority, evidence references, unresolved operations, and a concrete next
  action;
- externally uncertain work must remain `running` or `unknown` with a
  reconciliation route and a prohibition on blind retry;
- phase-specific PASS must not be promoted into product acceptance;
- independent review is most valuable before candidate freeze as well as after
  implementation; and
- synthetic replay and small fixtures can exercise the policy without
  deliberately producing a giant Token-consuming conversation.

Current authority is the user's confirmed design, the shipped Skill contract,
the accepted WorkVCS ADR, current code, and current validation evidence. The
historical threads and attachments remain provenance.

## Corrections preserved by the final contract

| Earlier ambiguity | Accepted correction |
| --- | --- |
| “Read-only target conversation” | The candidate is non-authoritative before commit; after commit it is the ordinary active Work carrier, not a permanently read-only chat. |
| One owner/writer for a Project | Ownership is scoped to `(Workspace, Work Branch, Task, exclusive Claim)`. Other Tasks, Claims, Branches, Sessions, and Git worktrees remain parallel. |
| Rotate from any conversation | A SubAgent or side chat cannot be source, creation actor, or target. |
| Listener cannot create a conversation | The bound listener may create one Work candidate for the monitored Work, but cannot create or rotate into another listener. |
| Target can be an internal ID | Readiness requires a resolved stable `thread_id` for a normal, visible, auditable, interactive Work conversation under the exact Project. |
| Every compaction triggers rotation | Compaction is one pressure signal. At least two independent pressure classes and all safety gates are required. |
| Test with a huge artificial conversation | Use deterministic policy cases, historical replay, actual temporary-store provider execution, and later authorized natural pilots. |

## Architecture split

The capability has three boundaries:

1. Work Governance evaluates whether rotation has clear net benefit. Its
   evaluator is deterministic and produces no product or durable-state effect.
   A previously committed `work_candidate` may be evaluated as a later source
   only when it is still the current carrier with the exact exclusive Claim.
2. WorkVCS holds a revisioned durable product-control-plane envelope and audit
   record for exact-Project opt-in. It validates structure, exact Project,
   revision, and digests but does not self-prove external user authorization,
   Project membership, or product actor identity; those remain product-control-
   plane and real-pilot obligations. WorkVCS admits the exact scope, stores the
   immutable decision/request including the embedded complete evaluator result,
   receipt, and bounded evidence references, records dispatch before any
   product call, fences revocation, currentness drift, and races, preserves unknown
   reconciliation history, and atomically transfers only the exact exclusive
   Claim after target-authored acceptance.
3. The product adapter creates or resolves one normal Work candidate and proves
   exact Project placement, resolved identity, visibility, auditability, and
   interactivity. It must use only the bounded reference packet and exact
   initial message, without injecting the source transcript. Unknown creation
   remains one unresolved attempt.

The listener remains attached to the same monitored Work scope. The target
inherits the Work lane and Claim, not the listener's conversation lineage.
If the listener must be replaced, a monotonic revision fences the old actor and
normal recovery is allowed only while non-listener currentness is unchanged.
If the inactive listener is lost after drift, the replacement is permanently
`abort_only`: the original decision/currentness and all creation/candidate
evidence stay immutable, observed drift and trusted recovery authority are
recorded, only the original creation operation may be reconciled, and the old
attempt must be aborted with state-specific evidence before a fresh rotation.
It cannot create, attach, accept, or commit. If a normally recovered target had
already accepted, the old acceptance remains history and the target must
accept again under the replacement revision. If a created target cannot
commit, the attempt remains active until its external archived-or-retained
disposition is evidenced.
A created target thread remains globally reserved even after terminal abort: it
cannot re-enter as a listener or ordinary Work carrier/source. Only the exact
committed candidate Session carrying the exact resulting Claim in the exact
scope may later source another rotation.

## Deterministic decision matrix

The nearest valid positive control requires:

- actor `listener`, source `work` or previously committed current
  `work_candidate`, target `work_candidate`;
- exact current enabled WorkVCS Project-policy revision and trusted
  product-control-plane envelope binding user authorization, Project
  membership, product actor, and authorization time, with durable provider
  available;
- exact current-carrier and exclusive-Claim proof;
- exact listener and listener-revision match, current scope and Project
  binding, and no active or unknown attempt;
- prior attempt terminal, cooldown satisfied, meaningful new progress;
- safe semantic point and fresh bounded Handoff;
- a bounded continuation packet no larger than 8,192 bytes, 64 items, or a
  4,096-token budget, plus its digest and the exact initial-message digest;
- high expected benefit, non-high continuation risk; and
- at least two of context pressure, repeated compaction, unchanged replay, and
  coordination drag; plus one to 32 bounded evidence references whose digests
  are included with the complete gate summary in the evaluator receipt.

Each gate has a negative control. In particular, compaction-only, SubAgent,
side-chat, listener-as-source, listener-as-target, uncommitted or non-carrier
candidate source, active/unknown attempt, stale listener revision, stale scope,
wrong Project binding, unsafe point, stale Handoff, low benefit, high risk, or
no progress must stay in the current conversation.
Dispatch independently refreshes the Branch projection and recomputes exact
scope currentness before the product effect; admission-time freshness alone is
not sufficient.

## Validation layers and claim boundary

| Layer | What it can prove | What it cannot prove |
| --- | --- | --- |
| Policy fixtures | deterministic admission and rejection reasons; no state side effect | conversation creation or Claim transfer |
| Temporary-store protocol tests | exact-Project policy/revocation, roles, exact scope, idempotency, dispatch-time currentness, concurrency, immutable unknown and abort-only reconciliation, global target identity reservation, packet/message binding, target acceptance/reacceptance, abort, listener fencing, atomic Claim transfer, and bypass resistance | that Codex created a real user-visible conversation |
| Stable runtime readiness execution | actual WorkVCS executable identity, exact policy/scope readback, protocol surface, revocation invalidation, and a fail-closed product boundary | product authorization, Project placement, or a created conversation |
| Trusted product-adapter execution | pre-call dispatch and actor-bound product receipts correlated to an actual creation attempt | user visibility and target interaction until observed in the product |
| Real product pilot | actual listener creates one visible normal Work in the exact Project; the target receives only the bounded packet, consumes it, accepts it, and remains interactable; natural resource behavior | universal or fixed Token savings |

This delivery validates the policy, provider protocol, and stable runtime
readiness layers. It does not install or activate the candidate, create a real
conversation, send cross-conversation messages, archive a source conversation,
Push, release, or deploy.

## Resource test strategy

The test strategy intentionally avoids manufacturing a long conversation:

- replay a small representation of historical pressure instead of entire
  transcripts;
- vary one policy gate at a time around a nearest valid control;
- execute provider policy, exact-scope, revocation, and readback behavior in a
  real isolated WorkVCS Store without treating caller-authored product fields
  as authorization;
- require a trusted adapter's actual product result before exercising known,
  failed, or unknown creation reconciliation;
- prove dispatch precedes the actual product call and that revocation or
  relevant source/Handoff/dependency drift after admission prevents that call
  while unrelated work remains admissible;
- race two admissions against the same exact scope in a temporary Store;
- verify that an unresolved attempt blocks a new identity and reconciles the
  original candidate, and that a created target identity cannot be reused or
  reintroduced as an ordinary Work/listener role;
- replace the listener after acceptance and require target reacceptance;
- exercise every non-terminal state through drifted-listener `abort_only`
  recovery, with direct dispatched/unknown exact immutable-operation
  replay/reconciliation, conflicting operation/client/receipt zero-mutation
  rejection, terminal receipt readback, forbidden commit, monotonic recovery
  CAS, and state-specific abort; and
- use later natural work to measure handoff accuracy, rework, completion
  quality, input/output Tokens, and elapsed time.

There is no fixed Token-saving claim. A natural pilot should compare similar
work and keep quality, rework, and handoff loss at least as important as raw
Token counts.

## Product acceptance still required

A later separately authorized pilot must prove all of these in the actual
product runtime:

1. the listener creates exactly one normal Work conversation under the named
   Project;
2. the product adapter authenticates the actual bound listener Session/thread,
   persists dispatch before the call, and observes current Project policy plus
   freshly revalidated exact-scope currentness;
3. a pending `clientThreadId` is reconciled to a stable `thread_id` before
   readiness;
4. the product receipt proves a non-forking `create_thread` result correlated
   to the admitted creation operation, request, dispatch, actual actor Session,
   actor thread, and listener revision;
5. the user can see, audit, open, and interact with the target;
6. the initial target message is the bound message and supplies only the
   bounded Handoff/reference packet, never the source transcript;
7. the actual target thread consumes that packet, authors acceptance, and
   resumes at the expected action;
8. the listener does not duplicate itself and remains able to monitor the
   continued Work; and
9. any failure or unknown outcome leaves the source authoritative and does not
   trigger a blind duplicate.

Until that pilot passes, report the result as a locally validated continuation
candidate, not as delivered automatic conversation rotation.
