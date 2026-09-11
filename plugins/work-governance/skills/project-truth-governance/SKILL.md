---
name: project-truth-governance
description: Use when deciding which source currently governs a project fact, whether a finding should become long-term authority, where to place it, or how to resolve conflicts among live evidence, work records, history, and memory.
---

# Project Truth Governance

This skill decides meaning and authority. A persistence-tool Skill, when
available, owns the mechanics of reading or recording state.

## Rank Sources By Claim

Start with the source that can authoritatively answer the specific claim:

1. the user's current instruction for this task;
2. current project instructions and explicit product or data contracts;
3. current code, configuration, schemas, runtime, data, and fresh validation;
4. confirmed project-native architecture, decision, operations, or domain docs;
5. active work-state, decision, finding, knowledge, evidence, and handoff
   records from an available persistence system;
6. historical plans, logs, prior conversations, and memory as leads.

The order is not mechanical. Code does not override an explicit intended
contract merely because it is current, and a recorded decision is not project
truth merely because it is durable. Name the type and scope of the claim before
choosing its authority.

When sources conflict, investigate cheap current evidence first. Ask the user
only when the unresolved conflict changes intended behavior, cost, data safety,
delivery form, or another material outcome.

## Promotion

Promote a finding only when future work benefits from treating it as stable:

- state the exact fact, decision, constraint, or practice;
- distinguish observation, inference, assumption, and confirmed conclusion;
- identify supporting evidence and known scope limits;
- check for an existing authority that should be updated instead of duplicated;
- choose a location with the right audience, owner, and lifecycle;
- obtain confirmation when promotion changes future execution or policy.

Use an available persistence-tool Skill for record lookup, semantic links,
knowledge promotion, and evidence storage. Use project-native documents for
facts that must govern people or tools that do not share that persistence
system. Link the two when each serves a different audience; do not create two
mutable authorities for the same contract.

## Keep Categories Distinct

- Goal, Plan, and Task records describe intended or active work.
- Decisions describe choices and tradeoffs.
- Findings describe what evidence established.
- Assumptions and Questions preserve uncertainty.
- Attempts preserve tried paths and outcomes.
- Knowledge is a reusable conclusion with provenance and scope.
- Project authority is the source future contributors are expected to obey.

Report the selected authority, why it fits the claim, conflicts or uncertainty,
what was promoted or deliberately left provisional, and how future work can
verify it.
