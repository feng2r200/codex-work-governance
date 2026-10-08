# Project Continuity Contract

Use this reference to create or review the small entry contract for a
long-running development project. Reuse existing project documents and naming;
do not create parallel copies merely to match this example.

## Minimum Project Entry

The entry should answer these routing questions without reproducing the
underlying content:

```markdown
# Project Continuity

- Enrollment: active | paused | retired
- Logical project: <stable name or identifier>
- Project roots: <one or more authoritative roots>
- Execution-state provider: external | project-local
- Provider locator: <stable provider identifiers or local ledger path>
- Provider isolation: dedicated target | enforced project partition and key | unresolved
- Stage baseline: <authoritative snapshot paths and update boundary>
- Routing last checked: <date or revision>
- Known routing drift: <none or a bounded description>

## Authority Map

| Concern | Authoritative location |
| --- | --- |
| Goals, scope, boundaries, non-goals | <path or durable source> |
| Architecture and module relationships | <path or durable source> |
| Accepted decisions and rationale | <ADR/index path or durable source> |
| Constraints and prohibited actions | <path or durable source> |
| Acceptance methods and criteria | <path or durable source> |
| Durable risks and boundary conditions | <path or durable source> |
```

The entry may name a provider-specific Skill and stable project, workspace,
branch, session, or record identifiers when the provider requires them. A
display name, current directory, or shared storage location alone is not a
stable locator. A stable locator answers where to query; it does not prove that
the selected state is isolated to this logical project.

The project entry must not become a second status report. Current progress,
next work, priorities, open execution risks, pending decisions, and task
evidence belong to the selected mutable provider.

The stage baseline is also not a live status report. It captures the accepted
project state at a declared stage boundary and remains unchanged during normal
in-stage execution. The provider may point to that snapshot while continuing
to record later live state.

## Authority And State Ownership

Use project-native authority for content that future contributors and tools are
expected to obey. Use the single execution-state provider for changing work
state. Typical ownership is:

| Information | Owner |
| --- | --- |
| Goal, scope, boundary, non-goal | Project-native authority |
| Architecture, modules, interfaces | Project-native authority |
| Accepted durable decision and rationale | Project-native ADR or decision log |
| Pending execution choice and rationale | Execution-state provider |
| Active task or stage decision-authority envelope | Execution-state provider |
| Current progress and status | Execution-state provider |
| Remaining work and priority | Execution-state provider |
| Open execution risk or question | Execution-state provider |
| Durable risk rule or boundary condition | Project-native authority |
| Acceptance method and standard | Project-native authority |
| Task verification result and evidence pointer | Execution-state provider |

When a pending decision becomes durable project authority, promote it once and
replace provider detail with a pointer plus any still-live execution impact.
Do not leave two independently mutable copies.

## Decision Authority And Semantic Review

Material choices remain user-owned unless the user explicitly delegates named
judgment for the current task or stage. Keep durable action permissions and
long-lived project boundaries in project-native authority. Keep the active
decision-authority envelope and its current execution effects in the single
execution-state provider; do not establish a second permission ledger.

At minimum, a delegated envelope identifies the authorized goal and scope,
applicable target and environment, decision classes Codex may own, any guarded
actions explicitly included, and its task or stage expiry. Never infer it from
silence, urgency, credentials, or an older task. The latest user instruction
may narrow or revoke it.

Activation, revocation, scope change, and a material autonomous route change
are semantic checkpoints. Record the decision, evidence, reason, and execution
impact, not hidden reasoning or a step-by-step chain of thought. New evidence,
a failed material assumption, validation failure, milestone completion, scope
or relevant external-state change, and a receipt mismatch trigger only the
bounded review their impact warrants. With active delegation, Codex may correct
or replan inside the envelope; beyond it, restore the confirmation gate. No
semantic change means no repeated read, review, report, or provider write.

If the project opens with an accepted stage baseline but no relevant state in
its required provider, reconstruct only the state the baseline supports. Record
the exact source, revision or digest when available, and as-of boundary; mark
historical or unresolved statements honestly and verify the created state by
reading it back. After that bootstrap, the provider is authoritative for live
execution state. The baseline remains the prior stage snapshot until the next
accepted stage boundary.

## Provider Modes

Choose one mode for the project:

- **External durable-state provider:** the entry names the provider Skill and
  stable retrieval identifiers. Startup uses bounded recall for the exact
  logical project. Closeout uses the provider's own update and readback
  mechanics.
- **Project-local ledger:** the entry names one repository-owned ledger
  location. It may contain separate status, backlog, decision, risk, and
  evidence records, but together they are one provider with one declared
  ownership boundary.

Use the project-local ledger as the fallback when no suitable external provider
is selected and repository changes are authorized. Do not silently create it
only because external lookup fails. If changing provider modes, declare a
cutover point, freeze or retire the old mutable state, verify the new source,
and then update the project entry. Never operate both as live authorities.

## Logical Project And Shared Storage

Multiple repositories may form one logical project, and one backend may hold
several logical projects. A shared backend does not identify the logical
project. Resolve the target in this order:

1. explicit project authority and stable project identifier;
2. the primary artifact or operation named by the task;
3. the relevant repository root or declared set of roots.

If those signals disagree, stop before writing state. Do not initialize or bind
an ambient mirror merely to make persistence available. Safe implementation
may continue only when it cannot write or report against the wrong project; the
durable handoff remains incomplete until the locator is resolved.

Prove logical ownership and provider-state isolation separately. A shared
backend is acceptable only when a dedicated target or enforced partition key
keeps current state, mutations, and receipts attributable to one logical
project. If distinct projects expose the same unpartitioned mutable state, its
contents are candidate context rather than current project authority. Fail
closed on writes, retain one bounded pending-reconciliation packet, and use the
provider's separately authorized repair path. Do not copy ambiguous history
into a new target. After isolation or partition repair, recover one fresh
bounded snapshot before reconstruction or mutation.

## Provider Control-Plane Readiness

When the selected provider offers one read-only aggregate health or readiness
snapshot, use it once for the control-plane obligations it actually covers.
Do not repeat separate route, binding, isolation, capability, or integrity
status reads merely to reproduce the same evidence. Open a focused status only
when the aggregate reports a gap, the current claim falls outside its coverage,
or an authorized mutation requires an exact fresh guard.

Keep the issue class precise:

- a cleanly inactive route or missing capability is **degraded** for the named
  operation; preserve the missing authority and continue independent work when
  safe, without activating or repairing it implicitly;
- stale, malformed, ambiguous, or integrity-failed control state is **blocked**
  for the affected provider path; fail closed on dependent claims and writes
  while safe unrelated work continues; and
- either class requires provider-specific evidence and separate authority
  before any control-plane mutation.

A healthy aggregate is bounded evidence, not universal proof. Retain its
provider snapshot identity and declared coverage with the startup packet.

## Provider Operation Ownership

A durable operation admitted or started by the current task remains owned by
that task until bounded delivery and exact readback complete, provided existing
authority still covers the same operation and target. Ordinary provider
polling, receipt repair, and same-target completion are Agent responsibilities,
not work the user must notice and resume manually. Stop only when the next step
needs new authority, changes the owner or target, requires a material
currentness decision, or crosses another guarded provider boundary.

Begin reconciliation with the current task's known operation identifiers. A
provider-wide historical inventory is classification evidence, not a batch
queue. Before acting on an older entry, compare its semantic intent with
verified current state and state the counterfactual effect of acting now.
Separate at least: delivery already completed but control-plane evidence is
stale; deterministic terminal failure; admitted but never delivered intent
that later evidence superseded; and immutable target change. An effective
status that merely looks open cannot by itself authorize replay or prove that
the payload remains current.

## Bounded Startup Packet

Recover only what controls the current task:

- current objective and relevant scope;
- current status and last verified milestone;
- prioritized next work and dependencies;
- material constraints and prohibited actions;
- pending decisions, including any material solution or feasibility choice,
  any active task or stage decision-authority envelope, plus open questions,
  risks, and boundary cases;
- applicable acceptance criteria and existing evidence.

The read order is entry, selected provider, task-relevant authority, then live
evidence. Historical transcripts and broad repository scans are escalation
paths, not the default startup routine.

Keep the recovered provider revision, head, cursor, or equivalent snapshot
identity with the packet. Reuse it while logical owner, route, scope, relevant
evidence identity, and observed external-write state are unchanged. Invalidate
only the affected path when one changes or becomes unknown. A precise mutation
receipt plus exact readback of the changed target advances the packet without a
second broad read; a mismatch reopens the affected target first.

## Material Closeout Delta

Reconcile only state made stale by the task:

- what became complete, partial, blocked, superseded, or newly active;
- what remains, in what order, with which dependency or owner;
- material decisions made and why;
- explicit decision-delegation activation, revocation, scope change, or
  material autonomous correction;
- new, changed, retired, or realized risks and boundary conditions;
- acceptance checks performed, their exact result, and evidence locations;
- authority documents changed or still awaiting promotion; and
- the safest next executable action.

No material delta means no write. If the provider update or readback fails,
keep this list as one bounded pending-reconciliation packet rather than
scattering provisional state across comments, files, and competing tools.

Task closeout and stage closeout are different. Reconcile live provider state
at every meaningful task or handoff closeout. Rewrite the stage baseline only
after stage completion and acceptance, using verified artifacts, relevant
conversation decisions, and provider records; then preserve a provider-side
reference or evidence pointer to that snapshot.

## Trigger And Anti-Trigger Scenarios

| Scenario | Expected route |
| --- | --- |
| Continue an explicitly enrolled project, even for a small slice | Apply; read the entry and bounded state |
| Resume the next priority after a prior task or long pause | Apply; recover before material work |
| Start a delivery that will span dependent phases or handoffs | Apply once continuity becomes valuable |
| The next stage depends on a material solution choice that remains unresolved | Keep the strategy pending and confirm it before dependent design, delegation, or mutation |
| Project authority explicitly selects the material approach | Preserve that choice and perform only bounded feasibility checks needed for the next slice |
| Fix an isolated typo in a project with no enrollment | Skip; use the ordinary lifecycle |
| Perform a one-off investigation with no durable continuation | Skip unless the result later creates a continuity need |
| External provider is unresolved but an authorized local ledger is selected | Apply using only the local provider |
| Shared storage contains several possible logical projects | Stop before state writes until the stable locator resolves |
| A stable project locator resolves, but several projects expose the same unpartitioned mutable state | Treat reads as candidate context and fail closed on provider writes until dedicated or partitioned state is verified |
| One aggregate provider snapshot proves the required route, binding, isolation, capability, and integrity obligations | Reuse it; do not repeat equivalent focused status reads |
| A route is cleanly inactive or a required capability is absent | Mark the named operation degraded, continue only independent work, and do not activate implicitly |
| Provider control state is stale, malformed, ambiguous, or integrity-failed | Block the affected provider path and use focused diagnosis before any separately authorized repair |
| A current-task operation is awaiting ordinary same-target delivery or receipt work already covered by authority | The responsible task completes and reads it back; do not assign monitoring to the user |
| A historical provider inventory contains open-looking operations | Classify currentness and the effect of acting now; do not batch-replay the inventory |
| An older operation is already delivered, terminal, replaced, or semantically superseded | Preserve that distinction and do not replay it merely to clear an open status |
| A precise mutation receipt and exact target readback match the recovered snapshot | Advance the bounded packet; do not repeat broad recovery |
| Provider owner, route, revision, head, scope, external-write state, or evidence identity changes | Invalidate and reread the affected path; broaden only when the change cannot be bounded |
