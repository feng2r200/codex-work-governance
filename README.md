# Work Governance Plugin

Work Governance is a Codex policy plugin. It helps Codex decide the smallest
useful governance level for a request, keep the user goal stable, ask only real
path-changing questions, and validate completion claims. Durable Goals, Plans,
Tasks, evidence, sessions, claims, handoffs, and historical recovery belong to
WorkVCS.

The repository-local marketplace is `.agents/plugins/marketplace.json` and the
plugin source is `plugins/work-governance`.

## Architecture

Work Governance owns judgment:

- No-Plan versus Plan-controlled routing;
- goal discovery and decision frontiers;
- user authority and confirmation boundaries;
- Git, remote, production, destructive, and data-risk boundaries;
- validation strength and final completion wording.

WorkVCS owns durable state:

- project binding and store discovery;
- Goal, Plan, Task, acceptance, verification, and evidence records;
- Codex Sessions, Claims, Handoffs, and compact resume context;
- confirmation receipts as target-bound mechanical records;
- closeout inspection, history, diffs, and recovery packets.

This plugin does not ship a durable-state CLI. It expects an installed
`workvcs` command and uses only the high-level WorkVCS surfaces needed for
governed work.

## Operating Rules

- No-Plan means zero WorkVCS calls and zero durable writes.
- When a No-Plan task evolves into Plan-controlled work, the first WorkVCS
  admission must carry the useful prior context: original request or digest,
  confirmed facts, explored evidence, decisions, unresolved unknowns, why the
  task escalated, acceptance anchors, stop triggers, and the next action.
- WorkVCS records authorization receipts mechanically. The model still decides
  whether user authority is sufficient before issuing or consuming a receipt.
- `workvcs closeout inspect` supports completion claims; it does not make the
  claim for the model.
- Historical `.work-governance` data is read-only history unless the user asks
  for historical audit or cleanup. New mutable authority is WorkVCS only.

## Worktree Policy

New Git worktrees should follow Codex configuration. Use this priority:

1. the current attached or already managed worktree;
2. an explicit user or project path;
3. the Codex `git-worktree-root` setting;
4. Codex official default `$CODEX_HOME/worktrees`.

Do not create new project-local `.work-governance/worktrees` paths.

## Install

Install WorkVCS first and verify the direct CLI:

```sh
command -v workvcs
workvcs --help
```

Then install or update the plugin from the local marketplace:

```sh
codex plugin add work-governance@work-governance-local
```

Existing threads may keep the old loaded skill context. Start a new Codex thread
after reinstalling to verify the updated plugin behavior.

## Validation

Use the focused regression tests for plugin contract checks:

```sh
uv run pytest
uv run ruff check tests/test_workvcs_cutover_contract.py
```

For skill edits, also run the system validators. They import PyYAML, so run
them with a temporary `uv --with pyyaml` environment instead of adding a plugin
runtime dependency:

```sh
SKILL_VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
PLUGIN_VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py"

for skill in \
  plugins/work-governance/skills/work-lifecycle \
  plugins/work-governance/skills/git-change-governance \
  plugins/work-governance/skills/independent-validation \
  plugins/work-governance/skills/project-truth-governance
do
  uv run --with pyyaml python "$SKILL_VALIDATOR" "$skill"
done

uv run --with pyyaml python "$PLUGIN_VALIDATOR" plugins/work-governance
git diff --check
```

The tests protect current behavior only. They do not maintain old Plan-version
compatibility matrices.
