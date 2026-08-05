# Work Governance 1.1.0 Historical Friction Audit

Date: 2026-08-05

## Scope

This audit maps the user's 1.0.7 usage friction notes to the current 1.1.0
candidate. It is intentionally narrower than the destructive redesign draft:
it checks whether the candidate improves the observed workflow failures before
activation, and it names residual work without claiming it is already done.

## Coverage Matrix

| Historical friction | Candidate status | Evidence or remaining boundary |
| --- | --- | --- |
| Plan writes were too frequent for ordinary inputs, receipts, and evidence. | Improved | Schema v5 separates `contract_revision` from `state_sequence`; scheduler, task runtime, and evidence binding no longer require Plan contract rewrites for ordinary runtime changes. |
| Evidence capture used a fragile temporary-manifest handoff. | Improved | `workctl evidence capture` accepts stdin or explicit files and persists redacted, content-addressed evidence records and blobs. |
| Scripts behaved like rigid execution strategy instead of structured Plan tools. | Improved | Public `workctl help <workflow>` documents the implemented surface; scheduler commands expose ready, blocked, next, and priority without forcing a contract revision. |
| One blocked task could stall unrelated ready work. | Improved | Schema-v5 scheduler reports `ready`, `parallel_ready`, `blocked`, and `blocked_details` with dependency and downstream propagation. |
| Model repeatedly searched `workctl.py` to understand usage. | Improved, not eliminated | The generated CLI reference and `workctl help` are the supported entrypoints. The controller is still large, so deeper implementation changes may still require code inspection. |
| Goal clarification and fog exploration sometimes displaced delivery. | Partially improved | Lifecycle docs now favor No-Plan, bounded Explore, and Freeze after decision-relevant evidence. This remains partly model behavior, so activation validation must include real workflow replay. |
| Previously clarified business facts could be lost across long work. | Partially improved | Goal/Plan contracts, TruthRefs, evidence refs, and runtime events give durable anchors; full standalone TruthRef CRUD is deferred to later 1.1.x work. |
| High-impact routes asked for repeated user turns even after a route was clear. | Improved by this follow-up | Route authority leases let one current-turn confirmation create a bounded runtime authority for repeated same-kind actions. Each action still mints and consumes a single-use capability. |
| Confirmation and receipt constraints blocked progress after target expansion. | Improved, still fail-closed | Leases reduce repeated prompts inside the confirmed scope. Scope expansion, contract drift, review blockers, artifact blockers, or expired leases still require a fresh decision. |
| The candidate might overclaim the destructive redesign draft. | Guarded | Candidate notes now identify implemented control-plane behavior and explicitly defer broader CRUD surfaces and full TruthRef validation. |

## Route Authority Lease Decision

The high-value residual issue before activation was repeated high-impact
authorization friction. The chosen correction is a bounded route authority
lease:

- `action lease prepare` prints a canonical scope digest and typed basis ref.
- The user still confirms that basis through `plan confirm`.
- `action lease issue` writes runtime lease state without changing the Plan
  contract.
- `action lease authorize` mints a single-use action capability only when kind,
  target, digest policy, expiry, max count, Plan contract SHA256, and blockers
  still match. Repeating a consumed same-target/same-digest action requires a
  new idempotency key and consumes another lease slot.
- `action consume` remains the atomic gate immediately before the external
  action.

This improves goal throughput without turning a broad statement into unlimited
remote, production, destructive, secret, or rollback authority.

## Deferred Work

- Split the large private controller into smaller transaction engines after
  activation confidence is established.
- Add full standalone `task add|split|link`, `evidence show|link|redact|verify`,
  and typed TruthRef CRUD in a later 1.1.x slice.
- Run a fresh activated-plugin replay after `CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0`;
  isolated controller tests and temporary Codex evaluation do not prove live
  activation.
