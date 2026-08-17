# L7 Context Governance

Use context governance when work crosses a role boundary, a long conversation
risks drift, or a future agent needs a compact handoff.

Build packages from explicit project-local sources. A context package should
name the role, task or target, summary, included file paths, reasons, hashes,
truncation state, and any short notes that are necessary for the receiver. It
should not include credentials, raw prompts, unrelated scrollback, generated
cache, dependency directories, or unstated assumptions.

Use role-specific packages:

- `implement`: facts, target files, constraints, and acceptance anchors needed
  to change the artifact;
- `check`: changed or high-risk files, expected invariants, command evidence,
  and failure modes to verify;
- `review`: the artifact under review, user-visible claims, known risks, and
  evidence boundaries, without leaking the intended verdict;
- `truth`: confirmed facts and authority locations that may deserve durable
  project documentation.

Prefer `workctl context lint --manifest PATH|--stdin [--role ROLE]` before
handoff when you need a cheap manifest safety check without source content.
Then use `workctl context build --role implement|check|review|truth --manifest
PATH|--stdin` for deterministic packages. Both commands are read-only and may
run before a Plan exists. If a Plan exists, the active Plan ID is metadata only;
context governance does not mutate the contract or runtime state.

Do not install automatic context-injection hooks by default. Hook-based
injection is a separate high-impact route because it can change token cost,
privacy exposure, and model behavior across every turn.

Validation standard: the receiver can trace each included fact to a project
path and SHA256, and omitted or truncated material is visible in the package
metadata.
