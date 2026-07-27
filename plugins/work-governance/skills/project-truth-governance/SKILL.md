---
name: project-truth-governance
description: Discover, rank, and maintain long-term project truth sources. Use when Codex must decide where confirmed project facts, requirements, architecture, constraints, business rules, evidence indexes, or handoff baselines belong, or when current docs, Plans, logs, memory, and code disagree.
---

# Project Truth Governance

Load `work-governance:work-lifecycle` first when this is part of a task.

## Truth Source Order

Prefer current, explicit, and executable authorities:

1. Current user instruction for this task.
2. Current project `AGENTS.md`, then `CLAUDE.md`.
3. Current code, configuration, data, logs, tests, and runtime evidence.
4. Active `.work-governance/_Plan` for future execution and handoff.
5. Confirmed project docs, product contracts, architecture docs, schemas, or
   Vault notes.
6. `.work-governance/logs` as process evidence only.
7. Memory and old session summaries as leads only.

When sources conflict, use current evidence by default. If the conflict changes
goal, behavior, cost, data safety, irreversibility, or delivery shape, stop at a
confirmation gate.

## Placement Rule

Enhance the existing authority when it can carry the fact. Add an adjacent
section or helper inside the same boundary when the original authority should
stay lean. Create a new authority only when lifecycle, audience, compatibility,
or ownership requires it.

Do not create `_Truth/` by default. If no authority exists, propose the smallest
project-native location and ask for confirmation before making it authoritative.

## Promotion Rule

Discussion, logs, candidate plans, and memory do not become project truth by
being written down. To promote them:

- state the exact fact or rule to promote;
- name the evidence and source file;
- explain the effect on future work;
- obtain confirmation when promotion changes future execution.

## Reporting

Report the selected authority, why alternatives were rejected, what remains
unconfirmed, and how the placement can be verified later.
