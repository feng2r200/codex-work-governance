# Work Governance 1.3.0 Candidate

## Claim

The 1.3.0 candidate adds lightweight decision-frontier guidance and a
deterministic `workctl context build` workflow for role-scoped context packages.
It keeps the existing direct `workctl` controller, schema-v5 Plan authority, and
hookless default path.

## Borrowed Ideas

- From grill-me style interaction: ambiguous requirements become compact
  choices with a recommended answer, not a long speculative planning essay.
- From Trellis context governance: handoff and review context should be explicit,
  role-scoped, bounded, and auditable by source path and digest.

## Implemented Surface

- `workctl help context`
- `workctl context build --role implement|check|review|truth --manifest PATH|--stdin`
- default `workctl doctor` reports the PATH-registered `workctl` shim and its
  static cache target when one can be determined.
- `work-lifecycle` routes ambiguous intake to
  `references/l0-decision-frontier.md`.
- `work-lifecycle` routes delegation and long-context handoff to
  `references/l7-context-governance.md`.

`context build` is read-only. It may run before a Plan exists, rejects project
escape paths, records source SHA256 values, reports truncation and omission, and
does not create Plan authority or mutate runtime state.

## Root-Cause Fix Note

Session `01a00d5c-f473-7ed0-b2a0-cc58a2d0569e` exposed an installation-state
mismatch: the enabled Plugin was 1.3.0, but the registered direct `workctl`
shim still targeted a deleted 1.2.0 cache path. The candidate now records this
as stale local shim state through default `doctor` output and lifecycle recovery
guidance.

## Deliberate Non-Goals

- No default context-injection hooks.
- No Trellis worker/channel runtime.
- No automatic summarization of the whole conversation into durable Plan facts.
- No live plugin activation or Push as part of candidate preparation.

## Validation Focus

- Context package path containment and truncation behavior.
- No implicit Plan creation in unmanaged projects.
- Active Plan ID is metadata only and does not mutate Plan/runtime state.
- Stale registered `workctl` shims are diagnosed as installation-state
  mismatch, not as a missing source command or Plan failure.
- Public help, generated CLI reference, README, model-first docs, metadata, and
  lifecycle references stay aligned with the implemented surface.
