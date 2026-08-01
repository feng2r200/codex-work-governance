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

Prefer exploration over questions when the answer is discoverable locally.
Ask only the path-changing question when user choice is required.

Classify ownership before deciding:

- facts discoverable from files, code, commands, logs, runtime, or supported
  external inspection are `owner=agent`; choose `explore`, investigate, then
  re-evaluate without transferring the research burden to the user;
- only an unresolved `owner=user` requirement whose `blocks` cover the next
  target permits `ask`; ask one question with the largest path-changing effect;
- when no blocker covers the next target, choose `proceed` and execute every
  dependency-ready target in the current turn instead of asking between
  slices.

The trusted `UserPromptSubmit` context binds this intake to one current-turn
receipt. Except for a simple low-risk No-Plan answer, explicitly choose:

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
replay unless a changed decision basis materially transitions `ask` or
`explore` to `proceed`; the new record must link the superseded record.
Changing only rationale, targets, or other content under the same basis is a
conflict and fails closed.

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
source, confirmation gates, target references, and current-turn receipt are
clear.
