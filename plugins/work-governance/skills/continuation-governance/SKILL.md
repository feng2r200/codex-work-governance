---
name: continuation-governance
description: Use during sustained Codex work when accumulated context, repeated compaction, unchanged replay, or coordination drag may justify continuing the same Work in a new normal conversation. Decide whether rotation has clear net benefit, preserve continuity and authority, and prevent SubAgent, side-chat, listener duplication, or hidden-session handoffs. Do not use merely because one compaction occurred.
---

# Continuation Governance

Decide whether one active Work should continue in a new conversation without
turning every compaction into a new task or allowing one conversation to grow
forever. This Skill owns the decision and handoff contract. It does not create
conversations by itself, replace durable project state, or grant product,
messaging, archive, Push, release, deployment, or destructive authority.

## Preserve The Exact Work Lane

Identify the exact continued scope before considering rotation: Project,
Workspace, Work Branch, primary Task, current Work carrier, and its exclusive
Claim. Other Tasks, Claims, Branches, Sessions, and Git worktrees remain
independent. Never infer one Project-wide writer, owner, listener, or epoch.
The Project must explicitly opt in to continuation rotation with a stable,
durably recorded provider Project-policy receipt and monotonic revision. The
provider adapter must verify a trusted product-control-plane authorization
envelope which separately binds the user authorization receipt, Project
membership receipt, product actor, and authorization time. Caller-authored
fields cannot self-prove opt-in authority. Missing, disabled, revoked, stale,
or unavailable durable-provider state means `stay`; it is never permission to
infer or recreate the state from chat text.

One exact monitored Work has at most one active listener. The listener may act
as the creation actor for a replacement Work conversation, but it must not
create a replacement listener or rotate its own listener conversation. A
SubAgent or side chat may return bounded evidence; neither may be the source,
creation actor, or target of the rotation. A pre-commit candidate cannot start
another rotation. After an earlier rotation commits, that same Session may
remain immutably labeled `work_candidate`, but it is eligible as a later source
only while durable state proves it is the current carrier with the exact
exclusive Claim. The phase label alone never grants source authority.

If the current conversation is itself a SubAgent or side chat, continue within
its parent ownership and do not start continuation rotation from that surface.
If the current conversation is the listener, it may create a Work candidate for
the monitored scope but must keep the listener identity unchanged.

## Require Material Net Benefit

Treat compaction as one pressure signal, never as the trigger. Review rotation
only at a safe semantic point such as a completed implementation slice, verified
milestone, stable diagnosis, or explicit handoff boundary. Prefer staying in the
current conversation unless all of these are true:

- the listener binding and revision, current carrier, exclusive Claim, scope
  epoch/currentness, and relevant project binding are verified and unchanged;
- no other rotation is active or externally unresolved for the scope;
- the previous rotation, if any, is terminal and the cooldown is satisfied;
- the Work has made meaningful progress since the last rotation;
- a current, bounded handoff can preserve the necessary goal, decisions,
  authority, state, evidence, unresolved risks, and exact next action;
- expected benefit is high enough to clearly exceed continuation and handoff
  risk; and
- at least two independent pressure classes are present, such as current
  context pressure, repeated compaction, unchanged-history replay, or measured
  coordination drag.

Stay in the current conversation when the benefit is low, handoff risk is high,
the work is about to finish, the scope is unstable, or compaction is the only
signal. Do not manufacture a large Token-consuming conversation to test this
policy. Use the deterministic contract and small replay fixtures in
[Decision contract](references/decision-contract.md), then learn from a later
natural pilot without promising a fixed saving.

## Separate Recommendation From Product Effects

The deterministic evaluator can return `stay` or `prepare_rotation`. A positive
decision authorizes neither creation nor Claim transfer. Before the product
effect, preserve a fresh handoff and the immutable decision basis in the
selected durable provider. Use its own Skill for persistence and exact
readback. Bind the decision to the exact scope ID, provider currentness digest,
listener identity and revision, carrier Claim and owner epoch, handoff digest,
Project-policy kind/revision/receipt/verification time, bounded
continuation-packet digest/size/item-count/token budget, initial-message
digest, product-adapter kind and version, deterministic evaluator version,
complete gate summary, bounded evidence references, and the complete canonical
evaluator result. Persist the evaluator receipt inside the canonical policy
decision so the rationale is self-contained, durable, and recoverable, and
changes to a gate or evidence reference change both result and receipt digests. Persist a
correlated creation request and then a durable dispatch record before invoking
the product API. The request and dispatch must declare
`source_transcript_included=false`. At dispatch, reread the exact Project
policy and revalidate the exact admitted scope currentness against a fresh
Handoff/Branch projection so revocation or relevant drift prevents the product
call. A process loss after
dispatch is an unknown external outcome, not permission to create again.

The creation actor may create only one `work_candidate` for the exact monitored
scope. If creation returns an unknown outcome, retain that one attempt and
reconcile it against its immutable receipt digest and pending client identity;
do not blindly retry with a new identity. Reserve a resolved target thread from
its first successful receipt, even if the attempt later aborts before
attachment. That reserved thread can never re-enter as a listener or ordinary
Work source/carrier; only its exact committed candidate Session carrying the
exact resulting Claim in the exact scope may later source a rotation. An unresolved
`clientThreadId`, hidden/background task, SubAgent, side chat, internal
candidate ID, or durable-provider row is not a created continuation target.

A candidate is ready only after the product runtime proves all of the following:

- it has a resolved, stable `thread_id` rather than only a pending
  `clientThreadId`, and is a normal Work conversation;
- it was produced by a non-forking `create_thread` operation correlated to the
  admitted creation operation ID and request digest;
- it exists under the exact specified Project;
- the user can see it, audit it, and continue interacting with it; and
- its canonical Project/workspace or worktree binding matches the handoff; and
- the product receipt and current listener revision are preserved for
  readback, unknown-result reconciliation, and stale-listener fencing.

After that evidence is attached, the target conversation must consume the
bounded handoff/reference packet, verify the bound initial-message digest,
preserve a concrete next-action digest, and author durable acceptance from its
own Session/thread against the current listener revision. Only then may a state adapter atomically transfer the
exact exclusive Claim and advance the scope epoch. The source remains the
carrier on any failure. Conversation creation itself cannot be rolled back; a
known non-authoritative candidate must be reported and handled under a separate
archive or cleanup authority. Do not clear an attached attempt until its
external disposition (`archived` or explicitly retained non-authoritative) is
confirmed with evidence.

Listener loss does not stop the monitored Work. A replacement listener may
normally recover the same active attempt through a compare-and-swap of the
listener identity, monotonic listener revision, and owner epoch only when the
non-listener currentness basis has not drifted. Normal recovery must never
silently rebase the decision basis. The old revision remains fenced even if an
earlier listener identity later reappears. If the candidate had already
accepted, keep that acceptance as immutable history, return the live attempt
to attached, and require the same target to accept again under the replacement
revision before commit.

If the listener is inactive and non-listener currentness has drifted, use only
an irreversible `abort_only` listener recovery. Preserve the original
decision, Handoff, currentness, Claim, candidate, receipts, and acceptance as
history; record the newly observed currentness and trusted recovery authority
under a monotonic recovery revision. The recovery listener is not a new
listener Work and cannot dispatch creation, attach or accept a candidate, or
commit the old rotation. It may only reconcile the original immutable product
operation and supply the state-specific evidence needed to abort. Another
lost recovery listener may be compare-and-swap replaced, but the attempt stays
`abort_only`. Start a fresh rotation only after the old attempt is terminal.

## Hand Off Without Losing Meaning

The target receives the Work scope and Claim, not the listener lineage. Carry
only the compact continuation packet needed to act:

- goal, current stage, exact Project and work lane;
- binding user decisions and authority boundaries;
- verified current state and immutable evidence references;
- completed changes and validation results;
- open risks, failures, unknown external effects, and prohibited claims; and
- the next concrete action and stop conditions.

The packet is bounded to 8,192 bytes, 64 items, and a 4,096-token budget. Do
not copy or inject the source transcript. Do not treat a summary as project
authority or omit a fact merely to reduce Tokens. After transfer, read back the
new carrier, Claim, scope epoch, target Project binding, and target
conversation identity, creation correlation, product receipt, and listener
revision before describing the rotation as complete.

## Report The Evidence Boundary

Distinguish five outcomes:

- policy evaluation passed in deterministic fixtures;
- the stable provider runtime read actual policy and exact-scope state from an
  isolated durable-provider Store and detected meaningful state changes;
- a trusted product adapter completed durable pre-call dispatch, correlated
  product creation, and acceptance authored by the actual target;
- a real visible Work conversation was created and bound; and
- a natural pilot demonstrated useful quality and resource behavior.

Never promote an earlier layer into a later claim. Local tests can prove role,
fencing, idempotency, unknown-result, binding-schema, and atomic-transfer
behavior; they cannot prove that a real Codex Work conversation exists.
