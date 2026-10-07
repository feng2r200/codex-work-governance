# Provider State Isolation And Efficient Recovery Candidate

Status: Source implemented and locally validated; delivery, installation, and live adoption pending
Date: 2026-10-07

## Why this policy changed

A stable provider locator can identify the correct logical project while still
routing several projects to the same unpartitioned mutable state. Treating
locator success as state isolation makes bounded recovery appear successful but
allows later reads and writes to cross project boundaries.

The prior efficiency rules also prevented unchanged-status coordination churn,
but did not define when one recovered provider snapshot remained reusable or
when a precise write receipt eliminated the need for another broad read.

## New contract

- Logical-project ownership and provider-state isolation are independent
  proofs. Shared unpartitioned state is candidate context only and blocks
  provider writes.
- Startup recovers one bounded packet with its provider revision, head, cursor,
  or equivalent snapshot identity.
- The packet remains reusable while owner, route, snapshot, task scope,
  relevant evidence identity, and observed external-write state are unchanged.
- Owner or route change, provider advance, scope change, external write,
  evidence change, unknown status, or receipt/readback mismatch invalidates the
  affected path.
- A precise typed mutation receipt plus exact target readback advances the
  packet without an immediate broad recovery read.
- A mismatch reopens the affected target or dependency first; broad recovery
  is reserved for a change whose head, route, scope, or evidence cannot be
  bounded.
- No material semantic delta still means no provider write.

## Controlled semantic cases

| Case | Required behavior | Guard retained |
| --- | --- | --- |
| Two logical projects expose one unpartitioned mutable target | Treat returned state as candidate context and stop provider writes | Stable locator is not misreported as isolation |
| Same owner, provider snapshot, scope, and evidence | Reuse the bounded packet | No repeated broad recall or invented delta |
| Precise mutation receipt and exact target readback agree | Advance only the changed target in the packet | Mutation is verified without unrelated reread |
| Receipt or readback differs | Reopen the affected target first | Mismatch is not hidden by cached state |
| Owner, route, head, revision, cursor, scope, external-write state, or evidence changes | Invalidate the affected path | Stale evidence is not reused |
| No semantic delta after mechanical work | Make no provider write | Durable state does not churn |

## Validation and measurement boundary

The 21 policy-contract tests pass and assert the isolation distinction,
invalidation triggers, bounded snapshot reuse, exact receipt/readback rule,
affected-path reopening, and updated scenario matrix. Ruff lint and formatting
checks pass. The Skill Creator structural validator passes for all ten packaged
Skills in an isolated `uv` environment. Delivery, installation, installed-copy
verification, and live use remain separate gates.

Future outcome measurement should compare equivalent tasks and count provider
calls by kind: broad recovery reads, targeted reads, writes, exact readbacks,
and mismatches, together with input, cached input, output, and elapsed time.
This source contract does not claim a fixed token, latency, or monetary saving.

## Boundaries

The plugin remains tool-neutral and adds no state engine, provider command,
hook, fallback ledger, or automatic repair. Provider isolation, activation,
migration, recovery delivery, and other mutations keep their own authorization
and evidence requirements.
