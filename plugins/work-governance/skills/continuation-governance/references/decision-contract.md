# Continuation Decision Contract

The P1 deterministic evaluator accepts one bounded JSON object. It is a policy
oracle for tests and Agent decisions, not a conversation-creation service.

Required fields:

- `schema_version`: `1`;
- `continuation_enabled`: boolean backed by a current enabled durable-provider
  Project policy; it must be true to prepare;
- `durable_provider_available`: boolean; false returns `stay` rather than
  degrading to chat-only state;
- `project_opt_in_receipt_kind`: the exact durable-provider Project-policy
  receipt kind;
- `project_opt_in_revision` and `project_opt_in_verified_at_us`: positive
  integers identifying the current durable policy read;
- `project_opt_in_receipt_digest`, `handoff_digest`,
  `continuation_packet_digest`, `initial_message_digest`, and
  `scope_currentness_digest`: canonical lowercase digests;
- `continuation_packet_bytes`, `continuation_packet_items`, and
  `continuation_packet_token_budget`: positive integers no larger than 8,192,
  64, and 4,096 respectively;
- `project_id`, `scope_id`, `workspace_id`, `branch_id`, `task_entity_id`,
  `listener_session_id`, `source_session_id`, and `source_claim_id`: exact
  bounded identities for this one Work lane;
- `listener_revision`, `owner_epoch`, and `evaluated_at_us`: positive integers;
- `adapter_kind` and `adapter_version`: the exact product adapter that will
  consume the decision;
- `actor_role`: `listener`;
- `source_role`: `work` or `work_candidate`;
- `target_role`: `work_candidate`;
- `source_committed`: boolean; it must be true when `source_role` is
  `work_candidate`;
- `source_is_current_carrier`, `source_has_exclusive_claim`,
  `listener_matches`, `listener_revision_matches`,
  `scope_currentness_matches`, `project_binding_matches`,
  `prior_rotation_terminal`, `cooldown_satisfied`, `safe_semantic_point`,
  `handoff_fresh`, and `progress_since_last_rotation`: booleans that must be
  true;
- `active_rotation`: boolean that must be false;
- `expected_benefit`: `low`, `medium`, or `high`; only `high` can prepare;
- `continuation_risk`: `low`, `medium`, or `high`; `high` stays; and
- `signals`: an object containing boolean `context_pressure`,
  `repeated_compaction`, `unchanged_context_replay`, and `coordination_drag`;
  and
- `evidence_references`: one to 32 bounded objects containing exact `kind`,
  `reference`, and canonical lowercase `digest` fields. Duplicates are
  rejected.

At least two pressure signals must be true. This makes compaction-only replay a
negative control. The result contains `action`, ordered `reasons`, the pressure
count, the exact canonical `policy_decision` for durable admission, and a target
contract. The decision remains bound to the Project-policy
kind/revision/receipt/read time, scope ID, currentness digest, listener
revision, handoff, owner epoch, bounded packet and initial message, and adapter.
It also embeds the canonical evaluator receipt and contains its deterministic
evaluator version plus result and receipt digests. The evaluator receipt
preserves the complete canonical result, complete gate summary, and bounded
evidence references, so
changing one gate or evidence item changes the bound rationale rather than
leaving only an unexplained `prepare_rotation` result.
`prepare_rotation` still requires durable admission and separately authorized
product actuation.

Representative fixture matrix:

| Case | Result |
| --- | --- |
| Compaction only | `stay` |
| Listener mismatch | `stay` |
| Active or unresolved prior attempt | `stay` |
| Unsafe semantic point or stale handoff | `stay` |
| No meaningful progress or cooldown | `stay` |
| Project not opted in or durable provider unavailable | `stay` |
| Low benefit or high risk | `stay` |
| SubAgent or side-chat actor/source/target | `stay` |
| Pre-commit or non-carrier Work candidate source | `stay` |
| Listener + Work source + Work candidate, all gates, two pressures | `prepare_rotation` |
| Listener + previously committed current Work candidate source, all gates, two pressures | `prepare_rotation` |

Historical replay should map existing evidence into this small contract rather
than replaying entire transcripts. A future natural pilot should compare
handoff accuracy, rework, completion quality, input/output Tokens, and elapsed
time against comparable continued-in-place work; no fixed saving is assumed.

The evaluator stops at `prepare_rotation`. Its target contract requires a
non-forking `create_thread` result, current listener revision, creation
operation/request correlation, exact Project-binding provenance, a durable
dispatch record written before the product call, and a product receipt bound to
the actual actor Session, thread, revision, and dispatch digest. A product
adapter may report a candidate ready only when it has
resolved a stable `thread_id` for a normal Work conversation under the exact
requested Project and verified that the conversation is user-visible,
auditable, and interactive. The creation request, durable dispatch, and receipt
must all bind the packet/message digests and record
`source_transcript_included=false`; dispatch must reread the enabled Project
policy, refresh the Branch projection, and recompute exact admitted scope
currentness before the product call. A pending
`clientThreadId`, hidden/background task, SubAgent, side chat, internal
candidate identity, or durable-state row is not successful creation evidence.
Before Claim transfer, the attached target must consume the exact bounded
handoff/reference packet and author durable acceptance with its own
Session/thread, current listener revision, packet/message digests, and
next-action digest. A created target identity is reserved from the first
successful receipt and cannot later become a listener or ordinary Work
carrier/source; only its exact committed candidate Session with the exact
resulting Claim in the exact scope may source another rotation.
Unknown-to-created reconciliation must bind the immutable
unknown receipt digest and pending identity. Listener replacement after target
acceptance archives the old acceptance and requires the same target to accept
again. If an
attached candidate cannot accept or commit, the rotation remains active until
the product layer proves the target was archived or deliberately retained as
non-authoritative. Listener recovery uses a monotonic revision and must not
rebase other scope currentness.

Normal listener replacement remains legal only when non-listener currentness
has not drifted. If an inactive listener is lost after drift, recovery is
irreversibly `abort_only`: it preserves the original decision/currentness and
all product receipts, records the newly observed currentness and trusted
recovery authority, permits only reconciliation of the original immutable
creation operation plus state-specific abort, and forbids new creation,
attachment, acceptance, or commit. A fresh rotation begins only after that
attempt is terminal.
