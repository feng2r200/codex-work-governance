# Work Governance Plugin

Work Governance is a tool-neutral Codex policy plugin. It helps Codex understand
the real goal, choose only the coordination a task benefits from, maintain
useful momentum, protect authority boundaries, and make completion claims that
the evidence supports.

The repository-local marketplace is `.agents/plugins/marketplace.json`; the
plugin source is `plugins/work-governance`.

## Design

Each module owns one kind of judgment and remains useful by itself:

- `work-lifecycle`: small router and safety kernel;
- `goal-discovery`: goal clarification and minimal decision frontiers;
- `plan-governance`: Plan admission, No-Plan evolution, and material revision;
- `subagent-governance`: useful delegation, ownership, and integration;
- `git-change-governance`: branches, worktrees, commits, and remote boundaries;
- `independent-validation`: proportional independent challenge;
- `project-truth-governance`: truth-source selection and promotion;
- `project-archive-curation`: retention placement and archive readiness;
- `work-reporting`: progress, handoff, and completion communication.

The plugin does not implement a state engine and does not require one specific
CLI. Plan governance, retrospective learning, project truth, and persistence are
separate concerns. When a compatible state or knowledge tool exists, its own
Skill supplies the storage, recall, evidence, and recovery mechanics.

## Core Behavior

- Clear, actionable work proceeds without a forced Plan or discovery ceremony.
- A Plan is introduced only when durable coordination, recovery, staged
  dependencies, or a persistent contract adds value.
- If No-Plan work grows into a Plan, the first recorded Plan carries forward
  useful findings, decisions, unknowns, constraints, evidence, and the reason
  for the evolution.
- High-impact work needs exact authority and proportional evidence, but impact
  alone does not require a Plan.
- Knowledge, decisions, evidence, and retrospectives may exist independently of
  a Plan when another capability records them.
- Completed project work is archived only after valuable knowledge, current
  authority, open obligations, and provenance have a durable destination.
- Non-blocking discoveries do not interrupt ongoing work. Directional,
  outcome-changing, authority-changing, or irreversible issues do.
- Compatibility is introduced only after its necessity is established and the
  user can see the decision and cost.
- Completion reports explain the result, additions, modifications, deletions,
  operations, validation boundary, unfinished work, risks, and useful next
  action without a fixed response template.

## Worktree Policy

For a new Git worktree, use the current attached workspace first, then an
explicit user or project path, then the root configured in the current Codex
environment, and finally Codex's official default `$CODEX_HOME/worktrees`.
Never create a project-local governance directory merely to hold worktrees.

## Install Or Update

Install or update the plugin from the local marketplace:

```sh
codex plugin add work-governance@work-governance-local
```

An existing task can retain already-loaded Skill content. Validate an update in
a fresh Codex process or task as well as checking registration and cached files.

## Validation

Run the focused policy contract tests:

```sh
uv run pytest
uv run ruff check tests/test_policy_contract.py
```

For Skill and manifest edits, run the system validators without adding runtime
dependencies to this plugin:

```sh
SKILL_VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
PLUGIN_VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py"

for skill in plugins/work-governance/skills/*; do
  test -f "$skill/SKILL.md" || continue
  uv run --with pyyaml python "$SKILL_VALIDATOR" "$skill"
done

uv run --with pyyaml python "$PLUGIN_VALIDATOR" plugins/work-governance
git diff --check
```

Tests protect representative behavior and module boundaries. They do not
preserve obsolete workflow versions or reproduce the Skill prose mechanically.
