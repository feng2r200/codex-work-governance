# Continuation Runtime Readiness V1

Status: native provider aggregate wired; product conversation actuation unavailable

## Delivered boundary

The stable Hook runtime exposes `continuation-readiness` as a read-only
admission probe. Its only provider query is:

```text
workvcs continuation readiness STORE --scope-id ID
```

The runtime resolves the current operating-system user's owner-controlled
`~/.local/bin/workvcs`; caller `PATH`, `HOME`, executable paths, Project ids,
Workspace ids, Branch ids, Task ids, policy fields, authorization claims, and
readiness facts are not accepted as authority. The request contains only the
absolute Store path, exact continuation scope id, and an optional prior
currentness digest.

The WorkVCS command opens the Store with `Engine::open_readonly` and returns one
typed JSON snapshot containing `read_only`, `store_opened_readonly`,
`provider_protocol_ready`, `product_membership_verified`,
`product_dispatch_authorized`, `currentness_digest`, and the native scope,
policy, listener, carrier, Claim, Branch, Task, rotation, and gap layers. The
Hook requires both product fields to exist and equal false; a missing field is
not treated as a safe default. It validates the typed envelope and exact scope
identity but does not reconstruct readiness from focused commands or maintain
another continuation state machine.

The result separates provider state from product membership and action authority:

- `provider_protocol_ready` is copied from the native atomic snapshot;
- `product_membership_verified=false` says that a native explicit Project id
  and immutable scope receipt do not prove product-adapter membership;
- `product_dispatch_authorized=false` says that provider readiness grants no
  product action authority;
- `automatic_rotation_ready` remains false because no trusted product adapter
  is connected; and
- `safe_to_dispatch_product_effect` remains false, so the read cannot authorize
  conversation creation, dispatch, acceptance, or Claim transfer.

The provider's structured gaps remain available as `{code, detail}` objects.
The runtime separately reports its fixed product-adapter gaps; neither class is
promoted into caller authorization.

## Currentness and read-only evidence

The native `currentness_digest` covers all readiness-relevant facts in the
returned scope, policy, listener, carrier, Claim, Branch, Task, rotation, and
gap layers. An optional prior digest produces `baseline`, `unchanged`, or
`changed` monitoring in the Hook response. The digest is an invalidation token,
not an authorization receipt.

`scripts/run-continuation-readiness-eval.sh` creates a temporary real WorkVCS
Store and a complete continuation scope. Each measured readiness query
snapshots every direct member of the Store directory before and after the
query, including the main SQLite file, `-wal`, and `-shm`.

The persistent-state contract requires unchanged persistent-member membership
and byte-identical main database, WAL, and every other persistent member. SQLite's
`-shm` file is the shared wal-index used for reader coordination, so its bytes
or presence can change during a read without a database transaction or WAL
write. The evaluation reports that observation separately instead of calling
it a persistent Store mutation. It also opens the same fixture with SQLite
`mode=ro`, enables `query_only`, and proves that an actual row update is
rejected as `attempt to write a readonly database`. It does not use
`immutable=1`: SQLite documents that immutable mode disables locking and
change detection and can return incorrect results when the database changes.
See SQLite's official [WAL documentation](https://sqlite.org/wal.html) and
[database-open contract](https://sqlite.org/c3ref/open.html).

All readiness and currentness claims come from the single native aggregate;
directory observation is a separate side-effect boundary.

The executable evaluation proves these transitions when the stable WorkVCS
installation includes the native command:

- an enabled, current exact scope reports provider ready;
- an unchanged Store returns the same currentness meaning;
- Project-policy revocation changes currentness and returns
  `project_policy_disabled`; and
- a legal closed Branch returns a normal not-ready snapshot with
  `branch_not_active`, while an injected unknown lifecycle returns non-zero
  typed `continuation_invalid` and no readiness JSON; and
- ending the listener Session changes currentness and returns
  `listener_not_active` instead of reporting ready.

No Hook readiness cache, rotation state, or authorization receipt is persisted.

The 2026-10-26 composed execution passed through the installed stable Hook
launcher and its verified immutable package, with no development arguments.
The Hook selected the fixed stable entry `/Users/ld/.local/bin/workvcs`. Runtime identity
is WorkVCS 1.7.0, build commit
`b607916f4b47c1270565672c329c5d6c8a093036`, `build_dirty=false`,
SHA-256 `c64a14f184367ed9119ea6bf6cf3c1e4ceb5a2c01abd3dc04525340db9a99440`,
and BLAKE3-256
`f0730d6427c10755e9b2b40ec895fdf234b41def69a4b2dc722190ae49e7ec96`.
The installed binary and complete ten-file Skill tree match the verified local
package. The execution passed the temporary protocol, persistent member and
membership invariants, SHM observation, write rejection, exact Project binding,
baseline/unchanged/revoked currentness, closed and invalid Branch lifecycle
cases, and ended-listener rejection. Its report declares
`evidence_kind=stable_hook_consumer`, `requires_stable_rerun=false`,
`automatic_rotation_ready=false`, and `product_effects_performed=false`.

The report is
`/Users/ld/Documents/Codex/2026-10-26/work-governance-goal-context/continuation-readiness-stable.json`,
SHA-256 `4fe380b8d3090527d6a10364d4be84fe23270987356349e3f36baee6e866f60d`.
Its schema-version-3 receipt embeds the native runtime status, evaluated binary
SHA-256, evaluator/source/installed Hook and manifest SHA-256 values, launcher
identity, and immutable package digest. The probe verifies that those identities
remain unchanged through the measured execution. The installed Hook package is
`4079c966b13c9c063f211def8620da6857e6ba207247486a2730e2749184ac20`.
The separate installed-runtime receipt is `workvcs-installed-runtime.json` in
the same evidence directory, SHA-256
`8650c82e65f5b672e0b7394cef41afd795c5b6d21583820083ab36d78b2a8190`.

## Product capability boundary

OpenAI's App Server API overview documents persisted thread mechanics such as
`thread/start`, `thread/read`, `thread/list`, and `turn/start`. It does not
document an App Server contract that places a newly started thread into an
exact ChatGPT Project or proves that the desktop product exposes it as a normal
user-visible, auditable, interactive Project conversation. See the official
[App Server API overview](https://developers.openai.com/codex/app-server/#api-overview).

The shipped Hook runtime has no direct capability to invoke the Codex app's
product-level `create_thread` operation. A hidden `codex exec` session,
background task, fork, caller-authored receipt, or unresolved `clientThreadId`
therefore cannot satisfy the target contract.

A complete adapter must independently provide all of the following before the
runtime may report automatic rotation ready:

1. authenticate the currently bound listener Session and visible source thread
   through the product control plane;
2. bind an actual user authorization receipt and current exact-Project
   membership receipt to the WorkVCS Project policy;
3. persist WorkVCS creation dispatch after a fresh native exact-scope snapshot
   and before the product call;
4. use a non-forking product `create_thread` operation that returns or
   reconciles to a stable `thread_id` under the exact Project;
5. prove the target is normal, user-visible, auditable, and interactive;
6. persist the correlated product creation result without blind retry;
7. start the target with only the bounded continuation packet;
8. obtain acceptance authored by that actual target Session/thread; and
9. let WorkVCS atomically transfer the exact exclusive Claim only after the
   acceptance and currentness gates pass.

Until those product facts are available from a trusted adapter and verified in
a separately authorized real-product pilot, the continuation mechanism is a
provider-readiness integration, not an automatic conversation-rotation
feature.

## Evidence boundary

`tests/test_continuation_readiness.py` checks the closed request schema, native
typed response, exact scope Project binding, same-Project policy revision
advance, conflicting Project rejection, read-only proof fields, structured
gaps, and rejection of legacy key-value output. The real temporary-Store script
supplies stable-provider evidence through the Hook consumer's fixed executable
selection. Installed Plugin and Hook package identity and actual Hook event
execution are separate adoption observations; direct launcher dispatch does not
prove that Codex emitted a Hook event or trusted its definition.
Neither test layer proves external user authorization, exact Project placement,
conversation visibility, target acceptance, or Claim takeover in the product.
