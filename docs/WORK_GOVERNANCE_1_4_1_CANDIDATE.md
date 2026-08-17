# Work Governance 1.4.1 Candidate

This candidate promotes the 1.4.0 lightweight work surface plus the
Skill-layer pre-implementation contract. It does not install, enable, or switch
the user's live Codex plugin by itself.

## Candidate Scope

- `work-governance:work-lifecycle` now requires a compact
  `Pre-Implementation Contract` before non-trivial implementation or
  Plan-controlled mutation.
- The contract names the goal anchor, scoped slice, evidence basis, remaining
  evidence, user-owned frontier if needed, exact intended actions, validation
  anchors, and stop or revision triggers.
- L0, L1, L3, L4, and L6 references now connect intake, demand contract,
  execution, validation, and closeout around planned-versus-actual evidence.
- The 1.4.0 executable surfaces remain in scope: decision frontier, context
  lint/build, compact work status, and JSON closeout output.

## Non-Activation Boundary

Preparing or merging this candidate does not update existing sessions or the
active plugin cache. Actual release and activation remain blocked on
`CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_4_1`.

## Validation Focus

The candidate must prove:

- the source plugin declares a single `1.4.1+codex.<cachebuster>` version;
- Skill-layer contract text is present and covered by tests;
- generated `docs/CLI_REFERENCE.md` matches the parser;
- direct source `workctl` can run in an isolated runtime project;
- repository tests pass before local merge to `main`.
