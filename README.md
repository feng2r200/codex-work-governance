# Work Governance

**English** | [简体中文](README.zh-CN.md)

**A composable governance layer for Codex that adds judgment without adding ceremony.**

Work Governance helps an Agent discover the real goal, choose only the
coordination a task benefits from, protect authority boundaries, and make
completion claims that the evidence supports. Clear work keeps moving; Plans,
SubAgents, independent review, and durable state enter only when they add value.

Created and maintained by [feng2r200](https://github.com/feng2r200).

## Why It Exists

Capable Agents usually do not fail because they lack another mandatory
workflow. They fail when they:

- solve the proposed implementation instead of the underlying goal;
- turn every task into a Plan or delegation tree;
- confuse available credentials with authority to push, release, or deploy;
- interrupt useful execution for non-blocking discoveries;
- promote historical notes into project truth without checking current evidence;
- or report completion more broadly than validation supports.

Work Governance addresses those failures as independent policy modules rather
than a monolithic process engine.

## What Makes It Different

- **Value-driven:** no Plan, SubAgent, tool call, or review is mandatory merely
  because a task is large or important.
- **Tool-neutral:** the plugin does not contain a state engine, does not require
  one specific CLI, and leaves persistence providers as separate capabilities.
- **Authority-aware:** local changes, commits, pushes, releases, deployments,
  production actions, and destructive cleanup remain distinct boundaries.
- **Evidence-calibrated:** validation expands with the claim and risk instead of
  becoming a fixed test ritual.
- **Composable:** each Skill owns one judgment and remains useful on its own.

```text
User goal and authority
          |
          v
  work-lifecycle router
          |
          +-- goal discovery
          +-- Plan governance
          +-- SubAgent governance
          +-- Git boundaries
          +-- independent validation
          +-- project truth
          +-- archive curation
          +-- work reporting
          |
          v
Existing tools and project-specific Skills
```

## Modules

| Skill | Owns |
| --- | --- |
| `work-lifecycle` | Small router and safety kernel |
| `goal-discovery` | Goal clarification and minimal decision frontiers |
| `plan-governance` | Plan admission, No-Plan evolution, and material revision |
| `subagent-governance` | Delegation value, ownership, and integration |
| `git-change-governance` | Branches, worktrees, commits, and remote boundaries |
| `independent-validation` | Proportional independent challenge |
| `project-truth-governance` | Truth-source selection and deliberate promotion |
| `project-archive-curation` | Retention placement and archive readiness |
| `work-reporting` | Progress, handoff, and completion communication |

## Install

Add the GitHub repository as a Codex plugin marketplace, then install the
plugin:

```sh
codex plugin marketplace add feng2r200/codex-work-governance
codex plugin add work-governance@work-governance-local
```

For local development from this checkout:

```sh
codex plugin marketplace add .
codex plugin add work-governance@work-governance-local
```

Open a new Codex task after installing or updating. Existing tasks can retain
the Skill content that was loaded when they started.

## Example Behavior

For an actionable bug fix, Work Governance should let the Agent inspect,
implement, and run focused tests without first creating a Plan. If the same
task later grows into dependent stages that must survive a handoff, the Agent
can admit a Plan once and carry forward the useful findings, constraints, and
evidence already discovered.

If the repository is dirty, the Git module protects unrelated work. If local
validation passes but push was not authorized, the reporting module describes
the verified local result and leaves the remote untouched.

## Package Layout

The distributable plugin lives in `plugins/work-governance` and uses:

- `plugin.json` as the portable Agent Plugins manifest;
- `.codex-plugin/plugin.json` as the Codex compatibility fallback;
- `skills/` for the nine independent policy modules; and
- `.agents/plugins/marketplace.json` as the repository marketplace.

The portable manifest is the forward-looking package authority. Tests keep its
identity and OpenAI interface metadata aligned with the compatibility manifest.

## Validation

Install development dependencies and run the policy contracts:

```sh
uv sync --locked --all-groups
uv run pytest
uv run ruff check tests/test_policy_contract.py
```

When the bundled Codex validators are available locally, also run:

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

The current suite protects representative policy boundaries and packaging
consistency. It is not yet a published behavioral benchmark of Agent outcomes;
that distinction is intentional and documented rather than hidden.

## Contributing And Security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a policy change. Report
security concerns through [SECURITY.md](SECURITY.md), and use
[SUPPORT.md](SUPPORT.md) to choose the right support channel.

## License

Apache License 2.0. See [LICENSE](LICENSE).
