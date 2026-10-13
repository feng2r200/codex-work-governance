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

The current semantic plugin version is `2.5.0`. Release-impacting changes to
Skills, plugin metadata, packaging, installation, or release workflow must bump
the version according to compatibility impact. Build timestamps and Git commits
are provenance only; they do not replace a semantic version bump. The CI gate
enforces this contract.

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
- **Authority-aware:** authorization to change repository content includes
  coherent, validated, non-rewriting local commits by default, while pushes,
  releases, deployments, production actions, history rewriting, and destructive
  cleanup remain separate boundaries.
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
          +-- problem discovery
          +-- frontend delivery
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
| `code-intelligence` | Structural source routing and current per-checkout CodeGraph readiness |
| `problem-discovery` | Early, stage-appropriate falsification and validation design |
| `frontend-governance` | Reference fidelity, required behavior, product copy, and scoped frontend acceptance |
| `independent-validation` | Proportional independent challenge |
| `project-development-governance` | Long-running project entry, recovery, and state reconciliation |
| `project-truth-governance` | Truth-source selection and deliberate promotion |
| `project-archive-curation` | Retention placement and archive readiness |
| `work-reporting` | Progress, handoff, and completion communication |
| `resource-observation` | Consumption assessment, binding limits, and later efficiency candidates |

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

The optional hooks use a separately installed stable launcher, never a Plugin
cache path. Install and read back the immutable runtime package before updating
the Plugin:

```sh
scripts/install-hook-runtime.py package \
  --expected-digest b3c566cab26450cb6f5b05b51501c6303dbad7d9ce5f2c3085b90874db10580a
scripts/install-hook-runtime.py launcher \
  --probe-digest b3c566cab26450cb6f5b05b51501c6303dbad7d9ce5f2c3085b90874db10580a
```

During an upgrade, name the current digest with `--rollback-digest` and pass
both the current and candidate digests with `--probe-digest` before installing
the new Plugin. The installer verifies the current launcher first and, if the
candidate fails, restores the previous launcher and internally re-probes the
rollback digest. A rollback-probe failure is reported separately. Trust the
new exact Hook hash through Codex only after the old Hook still runs and the
candidate package probe succeeds. Hook trust is not inferred from installation.
The runtime is passive until a Hook invokes it, emits nothing when no explicit
context packet changed, and does not install a background service.

```sh
scripts/install-hook-runtime.py launcher \
  --rollback-digest <CURRENT_DIGEST> \
  --probe-digest <CURRENT_DIGEST> \
  --probe-digest <CANDIDATE_DIGEST>
```

After installation, use `/hooks` in a fresh local Codex session and require the
three events to appear before reviewing and trusting their exact definitions.
If the events remain `Installed 0`, adoption is blocked: do not use trust bypass
as the installed configuration and do not report the Hook as active. Current
Agent Plugins manifests can encounter
[openai/codex#47925](https://github.com/openai/codex/issues/47925), where the
portable manifest is parsed but its bundled Hooks are not loaded. Retain the
verified launcher and immutable package, keep the failure visible, and retry
adoption only after the host runtime is fixed or a separately approved delivery
route is selected.

After local adoption, verify the enabled version with `codex plugin list` and
remove older direct cache entries with:

```sh
scripts/prune-local-plugin-cache.sh \
  --cache-root "$HOME/.codex/plugins/cache/work-governance-local/work-governance" \
  --keep-version 2.5.0
```

## Example Behavior

For an actionable bug fix, Work Governance should let the Agent inspect,
implement, and run focused tests without first creating a Plan. If the same
task later grows into dependent stages that must survive a handoff, the Agent
can admit a Plan once and carry forward the useful findings, constraints, and
evidence already discovered.

When an active Plan is replaced or abandoned, Work Governance treats its
primary-containment graph of nested Plans and Tasks as one bounded assessment
scope. Each Task may be retained unchanged, replaced with an explicit successor,
cancelled with a reason, continued, or deferred. Current Goal, Plan, and external
dependency references are protected; status is assessed separately from
executable currentness; and exact changed or retained state is read back before
the Plan exit is considered closed.

If the repository is dirty, the Git module protects unrelated work. Once an
authorized stage is coherent and its claimed validation passes, the Agent can
create semantically grouped local commits without asking for a separate commit
confirmation. A read-only or confirmation-only request still forbids the
commit. If push was not authorized, the reporting module describes the verified
local result and leaves the remote untouched.

When a development task needs symbol, call-path, impact, affected-test, or
cross-layer understanding, the optional code-intelligence module checks the
exact active checkout. If CodeGraph is available but that checkout has no
current index, it can create, synchronize, or fully refresh the local derived
index and verify it before querying it, including when the source task is
read-only. Literal text, documentation, logs, configuration, unsupported
content, and protected or ambiguous locations stay on native inspection routes.
The adapter never treats an index as project truth or silently installs global
tooling.

When tests or evidence must reveal problems rather than merely confirm an
expected path, the problem-discovery module first maps the relevant actors,
states, assets, effects, dependencies, and trust boundaries, then derives
explicit and latent claims from changed seams and high-consequence boundaries.
It chooses the earliest observation environment with trustworthy evidence,
combines representative workloads with targeted state and boundary challenges,
checks effects that may occur before an error, and tests the acceptance oracle
itself. Observation environments remain separate from risk dimensions such as
concurrency or recovery. Later integration or real-service checks are added
only for bindings, composed behavior, or environmental and operational
semantics that earlier deterministic evidence cannot represent.

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

The task that starts a durable provider operation also owns its ordinary
same-target completion and exact readback when existing authority already
covers them; the user is not expected to monitor routine pending receipts.
Historical open inventories are classified against current project truth and
the effect of acting now before any recovery. They are never treated as batch
queues, because replaying a superseded or terminal operation can make durable
state less accurate rather than more complete.

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
The source learning, architecture boundary, independent challenge, and
forward-scenario evidence for early problem discovery are recorded in
[Problem Discovery Skill Adoption Evidence](docs/validation/problem-discovery-adoption-v1.md).
The combined source, current local activation, and remote delivery are recorded
in [Integrated Code Intelligence And Adaptive Governance Delivery Evidence](docs/validation/integrated-code-intelligence-adaptive-delivery-v1.md).

During development, implement and verify the agreed capability while assessing
Token, monetary, time, and memory use from available evidence. Record useful
assessments at existing semantic checkpoints. Unknown billing, corrected
estimates, and agent-created savings targets do not pause work or justify losing
evidence. Explicit binding limits, actual resource failures, and new spending
commitments retain their existing boundaries. Protection, compression, caching,
throttling, and similar mechanisms are separately scoped enhancements after
capability acceptance. See
[the resource-observation contract and validation boundary](docs/validation/resource-observation-v1.md).

Frontend work can use `frontend-governance` to connect the selected reference
and delivery level with required interactions, product-facing copy, and
observable effects. Screenshots do not establish hidden behavior; a Demo's
sample state does not change a business API contract. Required controls keep
their promised actions, and removing development narration does not repair a
missing function. Acceptance covers the required flows affected by the change,
distinguishing builds, visual evidence, interactions, mocks, and real integration.
A small label or style repair remains a small task; project and tool Skills
retain implementation and browser routing. The conditional delivery-checks
reference supplies examples without imposing a fixed form or new state ledger.
For an explicit first use, ask `Use $work-governance:frontend-governance for this
frontend change, preserving the specified reference and current business contracts.`
Source, scenario, correction, and local-adoption boundaries are recorded in
[Frontend Governance First-Version Adoption](docs/validation/frontend-governance-v1.md).

## Package Layout

The distributable plugin lives in `plugins/work-governance` and uses:

- `plugin.json` as the portable Agent Plugins manifest;
- `.codex-plugin/plugin.json` as the Codex compatibility fallback;
- `hooks/hooks.json` as the Hook definition declared by both the portable
  OpenAI extension and the Codex compatibility manifest;
- `skills/` for thirteen independent policy modules plus one optional
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
git diff --check
```

When the bundled Codex Skill validator is available locally, also run:

```sh
SKILL_VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"

for skill in plugins/work-governance/skills/*; do
  test -f "$skill/SKILL.md" || continue
  uv run --with pyyaml python "$SKILL_VALIDATOR" "$skill"
done
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
