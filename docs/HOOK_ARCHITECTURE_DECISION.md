# Hook architecture decision package

Status: accepted for staged implementation. T-010 keeps both Hook registrations;
the final deletion decision is deferred until all optimizations and validations finish.

## Decision question

Determine the smallest Hook surface that preserves trusted bootstrap and explicit
high-impact authorization without putting ordinary exploration, continuation, or
runtime task transitions behind a per-turn governance pipeline.

## Current responsibilities

### `SessionStart`

- Discovers the physical project root and validates the local governance layout.
- Creates and validates the exact hash-bound runtime controller/skill bundle.
- Prewarms the pinned controller dependency and runs layout migration/recovery.
- Issues a session-scoped READY receipt bound to the Plugin build, session, controller,
  lifecycle skill, and runtime bundle.
- Injects the exact receipt-bound controller command into the session.

These are bootstrap and runtime-identity responsibilities. They do not require a
per-user-turn event, but the current controller has no other trusted source for the
official session identity or exact installed build.

### `UserPromptSubmit`

- Receives the official session ID, turn ID, and exact prompt bytes.
- Invalidates the previous turn receipt and atomically issues a new prompt-bound receipt.
- Provides a typed `request_ref` used by schema-v4 intake and confirmation provenance.

These are current-turn provenance responsibilities. Schema-v5 ordinary task state
transitions already use `state_sequence` and do not call the schema-v4 current-intake
gate, while the lifecycle documentation still describes every advancement as turn-bound.
That mismatch must be removed before activation.

Two compatibility/security constraints prevent immediate deletion:

- Mutable schema-v4 Plan paths still call the current-turn intake gate. Removing the
  Hook would make those supported writes fail closed rather than provide a smooth
  dual-read transition.
- Before T-010, schema-v5 task state already avoided per-turn intake but high-impact
  authorization was incomplete. T-010 binds v5 Plan decisions to the exact trusted turn
  and adds a short-lived `action authorize/consume` envelope for remote, production,
  destructive, secret, and rollback actions. It binds kind, typed target, action digest,
  the unchanged Plan contract SHA256, a same-turn accepted Plan gate, session/turn,
  expiry, and one-time consumption without storing raw commands or secrets.

## Options

| Option | Ordinary-turn cost | Trusted bootstrap | Trusted high-impact decision | Decision |
| --- | ---: | --- | --- | --- |
| Keep both Hooks unchanged | High | Preserved | Preserved | Reject |
| Keep minimal `SessionStart`; make `UserPromptSubmit` compatibility/confirmation-only | Low | Preserved | Preserved after T-010 | Recommend |
| Remove `UserPromptSubmit` without replacement | Low | Preserved | Lost | Reject |
| Remove all Hooks after platform-backed replacements exist | Lowest | Replacement required | Replacement required | Future target |

## Recommended contract

1. Keep a minimal `SessionStart` Hook for session/build identity, runtime-bundle
   discovery, layout readiness, and recovery capability. It must not create or revise a
   Plan, record ordinary intake, or authorize high-impact actions.
2. Remove `UserPromptSubmit` receipts and intake records from the authorization path for
   ordinary schema-v5 exploration, continuation, scheduling, evidence recording, and
   runtime-state transitions. During compatibility, the Hook may still issue an ignored
   local receipt; that receipt must not block or mutate ordinary v5 work.
3. Keep the current Hook registration for mutable schema-v4 compatibility until active
   v4 Plans can be explicitly migrated or the v4 write surface is intentionally retired.
4. Retain trusted current-turn provenance for structural contract decisions and
   immediate remote, production, destructive, secret, or substantive rollback
   authorization. Schema-v5 `plan confirm` now keeps the existing exact-turn requirement
   without requiring schema-v4 intake; external actions use the one-shot envelope only
   after an exact same-turn Plan confirmation is accepted.
   Expected revisions alone remain insufficient.
5. Delete `UserPromptSubmit` completely only when mutable v4 compatibility no longer
   depends on it and Codex exposes an equivalent trusted action-authorization input that
   binds user intent, session/turn identity, action target, expiry, and replay semantics.
6. Delete `SessionStart` completely only when controller discovery, exact build hashes,
   project layout bootstrap/recovery, and trusted session identity have another
   fail-closed source.

## Required verification before activation

- Repeated ordinary prompts, continuation, credential readiness, and read-only
  exploration do not write Plan intake, contract revision, or runtime state. A local
  compatibility turn receipt may change while v4 writes remain supported, but ordinary
  v5 work neither requires nor consumes it.
- Schema-v5 task start/block/unblock/verify/reprioritize uses only the expected
  `state_sequence`, task gates, and durable evidence rules.
- Contract revisions and high-impact actions fail closed without trusted, target-bound
  action authorization and cannot replay an old decision.
- A missing `UserPromptSubmit` Hook does not block ordinary local work.
- Mutable v4 compatibility either retains its trusted turn receipt or fails with an
  explicit migration/retirement condition; it is never silently weakened.
- A missing bootstrap trust source still blocks Plan mutation with a precise recovery
  condition.
- Fresh-session and compaction tests prove the exact runtime bundle remains stable and
  recoverable.

## Full Hook removal criteria

Full removal is permitted only after all of the following are demonstrably available:

- platform-authenticated session and action identity;
- immutable or hash-verified controller/skill discovery;
- atomic project-layout initialization and recovery outside the Hook path;
- explicit target-scoped, expiring, non-replayable authorization for high-impact work;
- no supported mutable v4 path that still requires the current-turn receipt;
- forward tests showing fail-closed behavior when any replacement input is absent.

Until those criteria are met, removing both Hooks would trade visible friction for an
untrusted caller-controlled authorization path and is not an acceptable light-governance
implementation.
