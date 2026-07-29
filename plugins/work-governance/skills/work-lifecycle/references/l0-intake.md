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
source, and confirmation gates are clear.
