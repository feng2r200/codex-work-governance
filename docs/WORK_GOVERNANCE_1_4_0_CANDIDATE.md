# Work Governance 1.4.0 Candidate

This candidate keeps the 1.3.0 live-use boundary intact while adding executable
lightweight governance surfaces that reduce planning overhead before a durable
Plan is needed.

## Candidate Scope

- `workctl frontier draft --manifest PATH|--stdin` turns Socratic clarification
  into a deterministic read-only JSON draft with goal anchor, agent-owned facts
  or unknowns, user-owned questions, recommended answers, blocked targets, and
  a stable digest.
- `workctl context lint --manifest PATH|--stdin [--role ROLE]` validates context
  manifests without emitting source file content. It rejects known secret paths
  and checks role visibility before a package is built.
- `workctl work status [--full]` aggregates layout, intake, active Plan queue,
  registered `workctl` shim health, and the release candidate boundary into one
  model-facing status object.
- `workctl context build` remains bounded and redacted; 1.4.0 preserves the
  1.3.0 secret-path rejection and stream-before-budget behavior.

## Non-Activation Boundary

Preparing this candidate in a source branch does not install, enable, or switch
the user's live Codex plugin. Actual release and activation remain blocked on
`CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_4_0`.

## Validation Focus

The candidate must prove:

- every new command is read-only and can run without Plan mutation;
- decision frontiers ask only user-owned path-changing questions;
- context lint never emits source content or secrets;
- work status reports candidate non-activation explicitly;
- generated `docs/CLI_REFERENCE.md` matches the parser.
