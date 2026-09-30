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
stable locator.

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
| Current progress and status | Execution-state provider |
| Remaining work and priority | Execution-state provider |
| Open execution risk or question | Execution-state provider |
| Durable risk rule or boundary condition | Project-native authority |
| Acceptance method and standard | Project-native authority |
| Task verification result and evidence pointer | Execution-state provider |

When a pending decision becomes durable project authority, promote it once and
replace provider detail with a pointer plus any still-live execution impact.
Do not leave two independently mutable copies.

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

## Bounded Startup Packet

Recover only what controls the current task:

- current objective and relevant scope;
- current status and last verified milestone;
- prioritized next work and dependencies;
- material constraints and prohibited actions;
- pending decisions, open questions, risks, and boundary cases; and
- applicable acceptance criteria and existing evidence.

The read order is entry, selected provider, task-relevant authority, then live
evidence. Historical transcripts and broad repository scans are escalation
paths, not the default startup routine.

## Material Closeout Delta

Reconcile only state made stale by the task:

- what became complete, partial, blocked, superseded, or newly active;
- what remains, in what order, with which dependency or owner;
- material decisions made and why;
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
| Fix an isolated typo in a project with no enrollment | Skip; use the ordinary lifecycle |
| Perform a one-off investigation with no durable continuation | Skip unless the result later creates a continuity need |
| External provider is unresolved but an authorized local ledger is selected | Apply using only the local provider |
| Shared storage contains several possible logical projects | Stop before state writes until the stable locator resolves |
