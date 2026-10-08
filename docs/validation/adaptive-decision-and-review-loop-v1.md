# Adaptive Decision And Review Loop Evidence

## Purpose And Boundary

This record verifies the source, packaging, local installation, and fresh-task
adoption of the adaptive pre-alignment and execution-feedback policy. The
change adds no Skill, runtime state machine, persistence schema, or tool
coupling. WorkVCS or another configured provider may persist the resulting
semantic checkpoints, but the public plugin remains tool-neutral.

The authorized delivery boundary is source, documentation, policy tests, local
commits, formal local plugin installation, and fresh local task validation.
Push, tag, release, remote publication, deployment, production or data changes,
and destructive cleanup remain outside this delivery.

Candidate package version: `2.0.0+codex.20261008143309`.

## Policy Contract

Before dependent work commits to a route, the lifecycle separates:

1. discoverable facts, which Codex investigates in scope;
2. interchangeable reversible details, which Codex decides; and
3. material choices, which remain user-owned by default.

Explicit decision delegation is valid only when the user directly grants it.
It is limited to the current task or named stage unless the user states another
boundary, and the latest instruction may narrow or revoke it. Its envelope is
defined by the authorized goal, scope, targets, environments, decision classes,
and action permissions.

Inside that envelope, Codex may choose the solution strategy, architecture,
priority, implementation structure, risk tradeoff, validation method, and
semantic-event response. It may continue, repair, roll back, replace or reorder
the route, revise a Plan, or expand validation without an automatic user
interrupt. It must reopen confirmation when the response would change the
goal, exceed the delegated envelope, enter an unauthorized environment, or use
an unlisted guarded action.

Semantic events include new evidence, a failed material assumption, validation
failure, milestone completion, scope or relevant external-state change, and a
receipt mismatch. Delegation does not permit Codex to ignore evidence, weaken
correctness or safety, or widen completion claims. No semantic change means no
repeated broad read, review, delegation, report, Plan update, or durable write.

## State And Reporting Contract

For an enrolled project, the configured single execution-state provider owns
the active task or stage decision-authority envelope and its current execution
effects. Activation, revocation, scope changes, and material autonomous route
changes are semantic checkpoints. Long-lived action permissions and project
boundaries remain project-native authority; no second permissions ledger is
introduced.

Reports expose material delegated decisions, corrections, verification effects,
remaining risks, and any exact boundary that requires renewed confirmation.
They do not narrate every ordinary choice or hidden chain of thought.

## Scenario Matrix

| Scenario | Required behavior |
| --- | --- |
| Material choice without delegation | Investigate cheap facts, recommend a route, and confirm before dependent work commits |
| Explicit in-scope delegation | Compare material effects, choose an evidence-backed route, record material impact, and proceed |
| Delegation in a prior task or stage | Do not inherit it; restore the default confirmation owner |
| Delegation is narrowed or revoked | Restore the corresponding confirmation gate immediately |
| Semantic event remains inside the envelope | Review and correct autonomously without an automatic question |
| Semantic event exceeds the envelope | Stop the affected work and identify the exact confirmation needed |
| Evidence undermines the route or completion claim | Revalidate or correct; delegation cannot suppress the evidence |
| Push, deployment, or destructive action is not listed | Do not perform it; judgment delegation is not action authorization |
| A guarded action is explicitly listed with an exact target | Verify the target and current guard before performing it |
| Review finds no semantic change | Reuse current evidence; do not repeat review, reporting, or state writes |
| The user requests a confirmation-only proposal | Stop before files, provider writes, Git changes, or other execution |

## Source Validation

The candidate must pass:

```sh
uv sync --locked --all-groups
uv run pytest
uv run ruff check tests/test_policy_contract.py
uv run ruff format --check tests/test_policy_contract.py
uv run --with pyyaml python \
  /Users/ld/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  plugins/work-governance/skills/<skill>
git diff --check
```

Source status on 2026-10-08:

- dependency synchronization completed from the lockfile;
- `pytest` collected and passed all 25 policy tests;
- Ruff check and format check passed for the policy tests;
- the bundled Skill validator accepted all ten Skill packages; and
- `git diff --check` passed.

The optional bundled Plugin validator is not present in this Codex installation.
Manifest identity, interface parity, package shape, and the absence of an
embedded state or execution engine remain covered by the policy suite.

Candidate commit: pending creation after this validated source snapshot.

## Local Installation And Fresh-Task Adoption

Formal local installation must use the repository marketplace and plugin
commands, followed by an exact source-to-installed comparison. Adoption then
uses three newly created local tasks so they load the installed candidate:

1. default confirmation for an unresolved material data-boundary choice;
2. delegated semantic correction after later evidence invalidates the initial
   route; and
3. delegated local judgment that stops at an unlisted remote-action boundary.

Installation status: pending source validation and candidate commit.

Fresh-task adoption status: pending formal local installation.

## Delivery Status

The source candidate has passed its local source checks and is awaiting the
candidate commit. This record must still be updated with that commit, installed
package path and parity evidence, fresh task identifiers and observed outcomes,
and the final local adoption boundary before completion is claimed.
