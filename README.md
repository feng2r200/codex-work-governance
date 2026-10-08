# Work Governance

**English** | [简体中文](README.zh-CN.md)

**A composable governance layer for Codex that adds judgment without adding ceremony.**

Work Governance helps an Agent discover the real goal, choose only the
coordination a task benefits from, protect authority boundaries, and make
completion claims that the evidence supports. It also keeps enrolled,
long-running project development recoverable without imposing that machinery on
one-off work. Clear work keeps moving; Plans, SubAgents, independent review,
and durable state enter only when they add value.

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
- **Tool-neutral core:** the lifecycle and policy modules do not contain a
  state engine or require one specific CLI. Optional tool adapters are isolated,
  scenario-triggered, and able to degrade without blocking unrelated work.
- **Authority-aware:** local changes, commits, pushes, releases, deployments,
  production actions, and destructive cleanup remain distinct boundaries.
- **Evidence-calibrated:** validation expands with the claim and risk instead of
  becoming a fixed test ritual.
- **Adaptive:** material choices are aligned before dependent work, while new
  evidence triggers only the review and correction its impact warrants.
- **Composable:** each Skill owns one judgment and remains useful on its own.

## Adaptive Work Loop

Work Governance distinguishes discoverable facts, ordinary implementation
details, and material user-owned choices before execution commits to a route.
The default mode puts material choices at a compact user confirmation frontier.
When the user explicitly delegates judgment for a task or stage, Codex chooses
inside that decision-authority envelope and continues without unnecessary
stops.

```text
align goal, evidence, constraints, and authority
                         |
          +--------------+---------------+
          |              |               |
  discoverable fact  reversible detail  material choice
    investigate         decide          default: confirm
                                      delegated: decide
                         |
              smallest verifiable slice
                         |
                   semantic event
                         |
       bounded review, correction, and revalidation
```

Semantic events include new evidence, failed material assumptions, validation
failures, milestones, scope or relevant external-state changes, and receipt
mismatches. With explicit decision delegation, Codex may repair, roll back,
replace or reorder the route, revise a Plan, or expand validation while it
remains inside the envelope. It returns to the user only when the correction
must change the goal, exceed the delegated scope, enter an unauthorized
environment, or use an unlisted guarded action. Delegation transfers judgment;
it never removes the evidence obligation or silently grants push, release,
deployment, production, data, credential, or destructive authority.

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
          +-- code intelligence (optional adapter)
          +-- independent validation
          +-- project development continuity
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
| `code-intelligence` | Structural source routing and safe per-checkout CodeGraph readiness |
| `independent-validation` | Proportional independent challenge |
| `project-development-governance` | Long-running project entry, recovery, and state reconciliation |
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

When a development task needs symbol, call-path, impact, affected-test, or
cross-layer understanding, the optional code-intelligence module checks the
exact active checkout. If CodeGraph is available but that checkout has no
index, it can create and verify the local derived index before querying it.
Literal text, documentation, logs, configuration, unsupported content, and
explicitly read-only locations stay on native inspection routes. The adapter
never treats an index as project truth or silently installs global tooling.

If the same outcome can be delivered through materially different approaches,
goal discovery exposes that direction choice before a stage Plan hard-codes one
path. It may inspect prerequisites and constraints to recommend a route, but it
does not wait for an assumed approach to fail before asking the question. An
explicit choice proceeds with only the bounded feasibility checks the next
slice needs.

If the user explicitly delegates the choice for the current task or stage,
goal discovery compares the same material effects and selects the
evidence-backed route directly. A later semantic event can trigger an
autonomous correction inside that envelope; revocation, expiry, or an
out-of-envelope action restores the corresponding confirmation gate. Unchanged
state does not trigger repeated reading, review, reporting, or durable writes.

For an enrolled long-running project, the project development module reads a
small routing entry and only the bounded state and authority relevant to the
task. At closeout it reconciles material progress, priority, decision, risk,
and evidence changes into exactly one mutable execution-state provider. Goals,
architecture, constraints, and acceptance remain in project-native authority,
and the project contract does not force a task Plan.

A stable provider locator is not treated as proof that state is isolated to
one logical project. Shared unpartitioned state remains candidate context and
blocks provider writes until isolation is verified. Once one bounded snapshot
is recovered, unchanged work reuses it; precise mutation receipts and exact
target readback replace an immediate broad reread, while owner, route, head,
scope, evidence, external-write, or mismatch changes reopen only the affected
path first.

When the provider exposes an aggregate read-only health or readiness view, the
governance layer prefers that single bounded snapshot over repeating equivalent
focused status checks. A cleanly inactive route or missing capability is
degraded only for the named operation; stale, malformed, ambiguous, or
integrity-failed control state blocks the affected provider path. Neither state
silently authorizes activation or repair.

The provider-state evidence is recorded in
[Provider Control-Plane Efficiency Synchronization Evidence](docs/validation/provider-control-plane-efficiency-v1.md).
The CodeGraph ownership decision, readiness contract, validation scope, and
adoption boundary are recorded in
[Code Intelligence Adapter Adoption Evidence](docs/validation/code-intelligence-adoption-v1.md).
The adaptive decision-delegation and semantic-review contract is recorded in
[Adaptive Decision and Review Loop Evidence](docs/validation/adaptive-decision-and-review-loop-v1.md).
The combined source, current local activation, and remote delivery are recorded
in [Integrated Code Intelligence And Adaptive Governance Delivery Evidence](docs/validation/integrated-code-intelligence-adaptive-delivery-v1.md).

## Package Layout

The distributable plugin lives in `plugins/work-governance` and uses:

- `plugin.json` as the portable Agent Plugins manifest;
- `.codex-plugin/plugin.json` as the Codex compatibility fallback;
- `skills/` for ten independent policy modules plus one optional
  code-intelligence adapter; and
- `.agents/plugins/marketplace.json` as the repository marketplace.

The portable manifest is the forward-looking package authority. Tests keep its
identity and OpenAI interface metadata aligned with the compatibility manifest.

## Validation

Install development dependencies and run the policy contracts:

```sh
uv sync --locked --all-groups
uv run pytest
uv run ruff check tests/test_policy_contract.py
uv run ruff format --check tests/test_policy_contract.py
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
