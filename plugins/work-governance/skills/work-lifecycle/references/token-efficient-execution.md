# Token-efficient execution without quality loss

Use this route when observed cost comes from repeated model turns, polling,
fine-grained deterministic actions, or repeatedly carrying a large unchanged
history. The objective is to remove avoidable coordination work. It is not a
license to reduce reasoning, acceptance, evidence, or independent challenge.

## Invariants

- Keep the accepted validation matrix, raw evidence, artifact integrity, and
  Reviewer/Validator independence unchanged.
- Do not save Tokens by selecting a weaker model or reasoning mode, shrinking
  required tests, sampling evidence that was previously complete, or replacing
  a real UI or integration flow with source inspection.
- Preserve exact failures, unknowns, Hook faults, uncovered paths, and partial
  results. Reduction is an observation, never a pass condition.
- Keep original evidence retrievable by stable artifact, command, log, or
  provider reference. A compact context packet points to evidence; it does not
  rewrite or discard it.

## Batch deterministic work

Before another model turn, group independent, already-decided operations that
share the same authority and failure boundary. Examples include literal reads,
formatting, compilation, focused test groups, manifest validation, and exact
readbacks. Preserve per-operation exit status and output identity inside the
batch so one failure cannot be hidden by a later success.

Do not batch decisions whose second action depends on the first result,
guarded mutations with different authority, destructive targets, or checks
whose isolation is part of the acceptance contract. Split at the first
semantic failure and reassess only the affected path.

## Carry an active context packet

At a real phase boundary or before compaction, carry one bounded delta with:

- current goal, scope, authority, and explicit non-goals;
- exact input revision or evidence identities;
- decisions and invariants that still constrain the next slice;
- achieved state and validation already applicable;
- unresolved risks, failures, next action, and stop conditions; and
- pointers to full logs or artifacts instead of copied payloads.

Send the packet only when it is new or changed. Never include transcript bodies,
large tool outputs, secrets, or a replay of facts the receiver can retrieve by
exact reference. Rebuild the packet when its input revision, authority, scope,
or relevant evidence changes.

## Stage coordination at semantic boundaries

Schedule Reviewer and Validator at the accepted independent boundaries: after
an implementation slice has stable inputs, after findings are corrected, and
before the corresponding completion claim. Do not commission them after every
mechanical edit, and do not merge their roles or reduce their scope to save
Tokens.

Use event-driven or bounded waits with cursors. An unchanged status does not
need another model interpretation. Missing, malformed, failed, or uncertain
status is not unchanged and must remain visible.

For UI validation, group deterministic setup and assertions into a reproducible
flow while retaining the same interaction coverage, screenshots or artifacts,
and failure diagnostics. A batch runner may reduce turns; it cannot substitute
mock or source evidence for required real behavior.

## Measure honestly

Compare aligned response identities and windows. Report input, cached input,
output, reasoning, call count, latency, and deterministic runtime observations
only when the source exposes them. Do not double-count cached input or reasoning
subsets. If exact Token telemetry is unavailable, label byte, event, or latency
data as supporting observations rather than Token totals.

An optimization is acceptable only when the original quality invariants still
pass. A Token decrease is useful evidence, not acceptance.
