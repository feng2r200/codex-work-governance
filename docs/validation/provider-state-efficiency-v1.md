# Provider State Isolation And Efficient Recovery Evidence

Status: Source, exact CI, plugin installation, and live isolated-provider adoption complete
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

## Validation

The 21 policy-contract tests pass and assert the isolation distinction,
invalidation triggers, bounded snapshot reuse, exact receipt/readback rule,
affected-path reopening, and updated scenario matrix. Ruff lint and formatting
checks pass. The Skill Creator structural validator passes for all ten packaged
Skills in an isolated `uv` environment.

## Delivery and live adoption

| Gate | Exact evidence |
| --- | --- |
| Source delivery | Commit `e178ee1c219430a8af00e9fac1260d5b28f51c55` was pushed normally to the repository's default branch. |
| Remote verification | Exact [CI run 37553940420](https://github.com/feng2r200/work-governance/actions/runs/37553940420) succeeded. |
| Installed plugin | Version `2.0.0+codex.20261007002945` is installed and enabled from `/Users/ld/.codex/plugins/cache/work-governance-local/work-governance/2.0.0+codex.20261007002945`; the installed tree matches the delivered source exactly. |
| Provider isolation | ProjectRef `01a0e2e6-f2e6-77a2-b858-7690808a81a7` now resolves to dedicated Store `/Users/ld/.codex/workvcs/stores/projects/work-governance-76995749aeb47b240ac15702cf64bbbe1f3dd4bc74ee571b703ab53a4f3d69fd.sqlite`, Store `01a113dd-b621-77b9-8034-f838133213d5`, Workspace `01a113dd-b62a-750c-8d02-1beada96c911`, and Branch `01a113dd-b62a-750c-8d02-1bedd4a7728c`. |
| Durable use | Journal capture `01a113df-4b8a-75f8-9abc-b48956997039` admitted a typed Plan into that dedicated Store and returned a durable receipt, proving the isolated route is active and writable. |

Already-running Codex tasks retain the Skill snapshot loaded when they began;
new tasks load the installed version above. The current repair used the new
policy as its acceptance contract and verified the underlying WorkVCS state
isolation directly rather than treating installation alone as adoption.

## Measurement boundary

Future outcome measurement should compare equivalent tasks and count provider
calls by kind: broad recovery reads, targeted reads, writes, exact readbacks,
and mismatches, together with input, cached input, output, and elapsed time.
This source contract does not claim a fixed token, latency, or monetary saving.

## Boundaries

The plugin remains tool-neutral and adds no state engine, provider command,
hook, fallback ledger, or automatic repair. Provider isolation, activation,
migration, recovery delivery, and other mutations keep their own authorization
and evidence requirements.
