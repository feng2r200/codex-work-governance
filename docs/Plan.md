# Historical Hook Reduction Plan

Status: historical non-authority fixture.

This document intentionally describes an older and slightly different approach
from the active implementation goal.

## Historical Goal

Keep a minimal `SessionStart` hook for runtime identity and layout readiness,
remove ordinary `UserPromptSubmit` dependency, and continue using the
receipt-bound controller command emitted by startup.

## Historical Tasks

- Preserve the startup hook as the canonical runtime identity source.
- Reduce per-turn prompt receipts for ordinary schema-v5 work.
- Keep `.work-governance/cache/uv` as the runtime script dependency cache.
- Revisit full hook removal only after a platform-provided replacement exists.

## Authority Boundary

This file is a compatibility and evaluation fixture only. It must be classified
as historical `NON_AUTHORITY` when an active Plan exists under
`.work-governance/_Plan/index.yaml`.
