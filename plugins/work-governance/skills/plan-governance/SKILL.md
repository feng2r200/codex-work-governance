---
name: plan-governance
description: Use when deciding whether a task needs a Plan, creating or admitting a Plan, promoting No-Plan work into one, coordinating dependent stages, or deciding whether new evidence requires a material Plan revision.
---

# Plan Governance

A Plan governs an evolving route to a goal. It remains usable without any
particular persistence tool; when a Plan-recording tool is available, use that
tool's own Skill for storage and recovery mechanics.

Persistence readiness does not decide whether a Plan is warranted. Admit or
promote based on coordination value even when the active persistence provider
is temporarily unavailable; keep a bounded working Plan contract and carry it
forward when the provider recovers. Conversely, provider availability never
forces a Plan.

## Plan Admission

Create a Plan only when it adds durable coordination value, such as:

- recovery across turns, context loss, or long pauses;
- multiple dependent stages or independently owned work;
- a confirmed contract or confirmation gate that must survive handoff;
- a long-running delivery whose state cannot be reconstructed cheaply.

Complexity or impact alone does not force a Plan. A high-impact one-step action
still needs exact authority and evidence, and may deserve a separate record or
retrospective, without being converted into a Plan.

No-Plan means no Plan entity or Plan ceremony. It does not forbid independent
knowledge, decision, risk, evidence, or retrospective records when a relevant
persistence capability exists.

## Plan Contract

Capture only what controls execution and review:

- the goal and meaningful non-goals;
- current evidence, assumptions, constraints, and unresolved questions;
- stages, dependencies, ownership, and the next executable action;
- acceptance evidence, confirmation gates, and stop or revision conditions.

Depth should match uncertainty and consequence. Do not manufacture phases,
task hierarchies, roles, or test matrices to make the Plan look complete.

## No-Plan To Plan

When work evolves into needing a Plan, use the available Plan-recording tool on
the first admission and explain the evolution. Carry forward the useful prior
context rather than pretending the Plan began at admission:

- original request or a faithful digest;
- relevant findings, decisions, constraints, and evidence;
- open assumptions, questions, risks, and failed attempts;
- why durable coordination became valuable now;
- the current goal, contract, next action, and confirmation boundary.

Do this once. Do not backfill noise or recreate every conversational step.

## Revision

Revise the Plan when evidence changes the confirmed goal, Plan contract, data
strategy, delivery form, acceptance boundary, stage dependency, or another
choice that invalidates the active route. Record the cause, prior route, new
route, affected work, and revalidation needed through the available Plan tool.

Ordinary code structure changes, local implementation choices, and corrected
estimates do not require a user confirmation gate unless they materially alter
the agreed outcome or authority. Preserve meaningful supersession history, but
do not maintain compatibility behavior or per-version test suites without an
independently proven need.

## Close

A completed Plan is evidence of tracked execution, not proof of the user's
outcome. Judge completion using current artifacts and validation, then use the
persistence tool for mechanical closeout if one is active.
