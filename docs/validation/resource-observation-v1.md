# Development Resource Observation

Status: implemented, source-validated, and locally installed
Date: 2026-10-12
Version: 2.3.0

## Intended behavior

Develop and verify the accepted capability while assessing and recording useful
resource evidence. Token or monetary estimates do not become numerical ceilings,
confirmation gates, evidence-truncation rules, or independent acceptance targets.
Protection and savings mechanisms are later enhancements unless an observed
failure makes a bounded remedy necessary for the current capability.

This contract follows a development incident in which a research context budget
became a default retrieval restriction and reduced supporting-evidence recall.
The user explicitly requested capability implementation before cost controls,
with development consumption assessed and recorded rather than used to cause
unexpected pauses. The incident motivates this distinction; it does not define
a universal retrieval size, resource allowance, or measured savings claim.

## Constraint and authority boundaries

| Evidence | Required response |
| --- | --- |
| High consumption, a changed estimate, or unknown pricing without a binding limit | Record the relevant evidence and uncertainty; continue within existing authority |
| A research budget or another task's allowance | Preserve its original scope; do not adopt it as the current development contract |
| An applicable explicit spending cap or enforced platform quota | Retain its source, scope, period, unit, and remaining allowance; contain actions that would breach it |
| Observed memory, disk, context, request, or retry failure | Diagnose and validate a bounded remedy; preserve capability completeness and continue independent work |
| A requested top-K result or real interface constraint | Preserve its functional meaning and retrievable evidence rather than treating every finite result as a savings cap |
| A new paid commitment, larger authorized allowance, new target, or other guarded effect | Use the existing authority boundary before that action |
| Missing telemetry or an unavailable persistence route | Preserve truthful unknowns and report the affected route; do not silently claim accounting or durable delivery |

## Assessment and recording

`resource-observation` is scenario-triggered. The lifecycle router retains only
the default behavior and routing trigger; it does not require every task to load
a resource workflow. Goal and Plan governance distinguish estimates from
binding contracts. Problem discovery keeps external targets and effects
authorized without demanding that the Agent invent a numerical per-probe or
total allowance. Reporting explains consumption only when it matters.

Use existing counters, receipts, logs, and inexpensive observations. Distinguish
returned-context Tokens, model-request usage, whole-task usage, actual charges,
estimates, and account-level constraints. Preserve source, units, measurement
window, counting method, and unknowns. Token subsets and repeated cumulative
snapshots must not be counted twice; usage without applicable pricing does not
establish a monetary amount or avoidable waste.

Align response identities, measurement windows, units, and source field
definitions before aggregating. Partial or unaligned data remains a scoped
source report. Automatic usage collection or cost attribution does not grant
authority to initiate charges or purchase services.

Record the smallest useful assessment at an existing semantic checkpoint in
the selected durable execution-state provider. No second ledger, per-call
capture, global audit, background Hook, accounting service, or Plan solely for
resource recording is added by this plugin.

If the provider route is unavailable, retain one bounded pending semantic packet
in active context and an actual handoff when necessary. The selected provider
owns authorized recovery, currentness, delivery, and exact readback; a second
durable queue or implicit control-plane repair is not a fallback.

## Deferred enhancement candidates

These are follow-up scopes, not implemented or activated capabilities:

- automatic collection and deduplication of task-level usage with evidence
  attribution and missing-data handling;
- price-source and currency-aware cost estimation or actual-charge correlation;
- configurable protection, quotas, retry or concurrency controls based on an
  explicit operational contract; and
- evidence-preserving retrieval, caching, compression, batching, or model
  selection after comparing equivalent accepted capabilities.

Re-enter a candidate after capability acceptance when a concrete consumer and
observed consumption, failure, or operational requirement justify it. Define
the same representative inputs and quality/completeness constraints for the
baseline and candidate. Obtain separate authority for any activation or new
commitment. A smaller output or fewer calls alone does not prove savings.

## Validation boundary

Policy contracts validate module discovery, metadata, links, tool neutrality,
packaging, and existing governance boundaries. Behavioral forward-testing must
separately challenge execution decisions with high estimated consumption,
missing billing data, explicit caps, actual failures, external probes, and later
enhancement candidates. Source tests alone do not prove installed behavior,
accounting automation, old-chat hot reload, or actual Token or monetary savings.

Validation and local adoption evidence will distinguish those claims explicitly.

### Source validation

- 31 existing policy contracts passed, covering module discovery, link and
  metadata validity, tool neutrality, package parity, and prior boundaries.
- Lint, formatting, semantic version progression from 2.2.0 to 2.3.0, new Skill
  validation, and whitespace checks passed.
- An independent evaluator applied the policy to nine isolated decision
  scenarios: high estimates, inherited evidence truncation, explicit spending
  caps, authorized probes with unknown charges, OOM recovery, new paid
  commitments, usage deduplication, accepted-capability follow-ups, and unavailable
  persistence. The decisions preserved the expected authority and evidence
  distinctions. This was hypothetical forward-testing, not service execution.
- Review clarified pending-packet continuity, aggregation identity and window
  alignment, and the distinction between cost observation and financial actions.
  Capability completeness still depends on its own accepted oracle; this policy
  cannot declare a retrieval metric or batch sample sufficient by itself.

### Local adoption

- The validated implementation was committed as
  `a60ed10d8bfe55492f6e7023151e0f29149e38e5` and fast-forward integrated into the
  verified local default branch. No unrelated source changes were included.
- Version 2.3.0 was installed through the existing local marketplace and read
  back as installed and enabled. All 30 plugin files matched the source tree
  byte for byte, including the new resource-observation Skill and metadata.
- Independent narrow review confirmed that the recording and aggregation
  clarifications preserve the original nine decisions. External billing-system
  access still requires its applicable target, credential, and data authority;
  an active-context pending packet is not durable storage.
- Existing long-chat hot reload was not verified. New conversations are the
  recommended adoption entry. No actual service probe, automated accounting,
  protection engine, measured savings, remote Push, or public release was part
  of this adoption. Existing caches and unrelated worktrees were preserved.

Ongoing delivery and exact readback belong to the selected durable provider;
this document is the accepted local phase snapshot, not an execution ledger.
