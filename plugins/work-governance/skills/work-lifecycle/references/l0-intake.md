# L0 Intake

Start by stating the bottom-line interpretation of the user's request.

Write a one-sentence goal anchor before choosing the route: name the
user-visible target, not the planned method, test suite, or current failure.
When prior work is already in progress, identify which next action can change
the most decision-relevant evidence with the least effort that remains safe.

Build a compact cognition map:

- Explicit knowns: current instruction, paths, constraints, deliverables, and
  acceptance criteria supplied by the user.
- Authority: current user instruction, project `AGENTS.md` or `CLAUDE.md`,
  current files, current command output, Plan, logs, memory, inference.
- Dark areas: user-owned choices that can change goal, cost, behavior, data
  safety, irreversibility, or delivery shape.
- Exploratory unknowns: facts that must be discovered by reading files, running
  commands, checking logs, data, browser state, official docs, or runtime.

For non-trivial work, use four lightweight decision gates before admitting or
expanding governance:

- Value: what user-visible result changes if this succeeds?
- Impact: what behavior, cost, data, irreversibility, authority, or delivery
  surface can change?
- Cognition: what missing fact would change the route, and who owns it?
- Verification: what check or evidence boundary can prove the result?

These gates are an intake thinking aid, not a required Plan artifact. Persist
only the answers that become obligations, scope boundaries, blockers, or
confirmation bases. If any gate cannot be answered compactly and the missing
fact is agent-owned, choose `explore`; if it is user-owned and blocks the next
target, choose `ask`.

Prefer exploration over questions when the answer is discoverable locally.
Ask only the path-changing question when user choice is required.

Routine exploration, a request to continue, a recovered network, or a
credential-ready notice is not a contract revision by itself. Keep those
signals in session/runtime evidence and promote them to a Plan unknown only
when they block a named target or demonstrate a material change to the goal,
scope, acceptance, safety, or authority boundary.

Classify ownership before deciding:

- facts discoverable from files, code, commands, logs, runtime, or supported
  external inspection are `owner=agent`; choose `explore`, investigate, then
  re-evaluate without transferring the research burden to the user;
- only an unresolved `owner=user` requirement whose `blocks` cover the next
  target permits `ask`; ask one question with the largest path-changing effect;
- when no blocker covers the next target, choose `proceed` and execute every
  dependency-ready target in the current turn instead of asking between
  slices.

When a new request arrives during an active Plan, classify its alignment with
the goal before treating it as a deviation:

- unrelated, bounded work is a `NO_PLAN_INTERRUPTION`; preserve the parent
  Plan ID, task, revision, and next-action resume anchor, finish the bounded
  request without mutating Plan structure, then resume automatically;
- aligned work that changes only execution order or priority stays inside the
  current Plan and reprioritizes the dependency-ready queue without a contract
  revision;
- aligned work that materially changes obligations, scope, behavior, cost,
  safety, delivery form, or acceptance evidence adapts or revises the Plan on
  the strongest current authority.

Apply the same classifier to audit findings discovered between slices. The
Plan is a revisable route map, not a requirement that useful work conform to
an obsolete ordering. Ask only when the aligned material change is itself
ambiguous or crosses a real confirmation boundary.

The trusted `UserPromptSubmit` context binds mutable schema-v4 intake and
high-impact authorization to one current-turn receipt. Schema-v5 ordinary runtime
work does not consume that receipt. Except for a simple low-risk No-Plan answer,
explicitly choose:

- `proceed` when no open blocker covers the next exact target;
- `explore` for an open agent-owned unknown that blocks the target; local or
  safe discoverability is the reason to explore, not a reason to call it
  proceed;
- `ask` for an open user-owned unknown that blocks the target.

Show one `INTAKE_RECEIPT` when first classifying the request. Show
`INTAKE_REVISION` only when the demand contract materially changes. A later
turn or structural contract, unknown, task, or route change invalidates the
prior decision. Completing a task, validation, evidence transition, slice, or
phase does not invalidate a route-level `proceed` decision by itself.

There are only four user-intervention boundaries:

- requirement input: one blocking user-owned `U-NNN`; do not also create a
  confirmation for the same question;
- Plan decision: the exact material solution contract;
- deviation decision: an evidence-proven L5 change to goal, scope, behavior,
  cost, safety, or delivery shape;
- external authority: system, remote, production, destructive, or otherwise
  out-of-bound permission.

Ordinary failures, missing local evidence, reversible implementation choices,
progress summaries, and "the next phase" are not user-intervention boundaries.

Keep rationale minimal. Never copy raw prompt content, credentials, tokens, or
other secrets into a Plan intake record.

The active Plan stores one bounded `intake.current` record plus the immutable
history head and count. Full canonical records are content-addressed under the
ignored project-local runtime history. Protocol-v1 Plans remain readable and
migrate on their next successful intake write. A repeated request is an exact
replay unless a changed decision basis materially transitions
`ask|explore -> proceed`, or refreshes the same `proceed` after a
controller-authorized structural change. A proceed refresh must preserve
request bytes, targets, rationale, and current-unknown binding; the new record
links the latest superseded record. Changing only rationale, targets, or other
content under the same basis is a conflict and fails closed.

When a current user instruction or decision will become future execution
authority, capture its strongest available provenance. Prefer
`user:session/<SessionId>/turn/<TurnId>/sha256/<digest>`, where the digest binds
the exact user message bytes or an immutable evidence manifest, instead of a
date-only label. Do not invalidate a historical typed reference merely because
it predates this preferred form.

Decide the entry route:

- answer directly for low-risk single-step work;
- explore before action when facts are missing;
- enter confirmation when high-impact ambiguity exists;
- admit a Plan when execution state, handoff, evidence, or multiple obligations
  must be tracked.

Validation standard: intake is sufficient only when the next action, evidence
source, confirmation gates, and target references are clear. A current-turn receipt
is additionally required only for mutable schema-v4 intake or high-impact authority.
