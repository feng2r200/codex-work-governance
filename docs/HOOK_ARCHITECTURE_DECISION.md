# Hook Architecture Decision

Status: accepted for hookless runtime implementation.

## Decision Question

Determine whether Work Governance needs Codex lifecycle hooks for normal
runtime execution after `workctl` is installed as a direct executable.

## Decision

Remove Hook registration from the runtime contract. Work Governance now runs
through the registered direct `workctl` executable. The controller performs
layout readiness checks, Plan authority checks, state-sequence guards, evidence
validation, and confirmation checks without requiring `SessionStart` or
`UserPromptSubmit`.

## Former Hook Responsibilities

`SessionStart` previously provided automatic project discovery, layout
bootstrap, runtime bundle snapshotting, receipt generation, and injected a
receipt-bound controller command.

`UserPromptSubmit` previously issued a prompt-bound current-turn receipt used by
schema-v4 intake and turn-bound confirmation provenance.

## Replacement Contract

- Direct `workctl layout migrate|recover|validate|status` is the bootstrap and
  recovery surface.
- Direct `workctl intake status` reports layout and Plan authority without a
  required bootstrap receipt.
- Ordinary schema-v5 task, evidence, scheduling, and closeout writes use
  `state_sequence`, dependencies, confirmations, and evidence guards.
- Legacy receipt files remain readable compatibility artifacts when explicitly
  supplied, but they are not normal execution authority.
- Active authority remains `.work-governance/_Plan/index.yaml`; conventional
  files such as `docs/Plan.md` are historical candidates unless explicitly
  promoted by the current user or project rules.

## Verification

- The plugin hook registry is empty.
- `scripts/workctl` invokes Python directly and contains no UV prewarm path.
- A fresh temporary project can run `layout migrate`, `goal init`, and
  `intake status` with a PATH that does not contain `uv`.
- A historical `docs/Plan.md` is classified as `NON_AUTHORITY` while an active
  Plan exists under `.work-governance/_Plan/index.yaml`.
