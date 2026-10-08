# Code Intelligence Adapter Adoption Evidence

Status: Plan B source, combined integration, and current local activation verified
Date: 2026-10-08

## Why the ownership changed

CodeGraph guidance previously lived in the global `cli-command-reference`
Skill alongside filesystem, literal-text, JSON, spreadsheet, and document
inspection guidance. That combined two different responsibilities and made a
structural source-intelligence capability look like a general CLI prerequisite.

Plan B gives the responsibilities explicit owners:

| Concern | Owner |
| --- | --- |
| Decide whether the task needs structural source intelligence | `work-governance:code-intelligence` |
| Route structural questions from the governance lifecycle | `work-governance:work-lifecycle` |
| Establish and verify checkout-specific CodeGraph readiness | `work-governance:code-intelligence` and its `codegraph.md` reference |
| Choose native filesystem, literal-text, JSON, spreadsheet, and document commands | Independent `cli-command-reference` Skill |
| Prove compilation, tests, runtime behavior, project truth, or durable work state | The authority that owns that claim, not CodeGraph |

This keeps the Work Governance core tool-neutral while allowing one optional,
scenario-triggered adapter to ship with the plugin. The adapter is not a
fallback state engine, project authority, or universal development prerequisite.

## Readiness contract

The adapter checks three independent conditions before relying on CodeGraph:

1. The current task has a concrete structural question, such as symbol
   discovery, callers or callees, call paths, change impact, affected tests, or
   cross-layer tracing.
2. A compatible CodeGraph CLI is available, with either MCP or direct query
   commands available for the chosen route.
3. `codegraph status --json` reports a healthy index for the exact active
   checkout rather than only for its shared Git common directory.

When those conditions apply and the checkout is writable, uninitialized, and
authorized for local derived-state creation, the adapter may run the
non-interactive initialization flow and must read status back before querying.
The resulting `.codegraph/` directory is local derived state. It is excluded
locally rather than promoted to project truth or committed merely to hide the
index.

The adapter does not initialize an index for prose, logs, configuration,
unsupported content, an explicitly read-only task, a synced project mirror,
or another protected or ambiguous path. Missing global capability degrades to
native inspection without silently installing or upgrading CodeGraph. Locks,
integrity failures, forced initialization, `uninit`, and `unlock` remain
separate diagnosis and authorization boundaries.

## Controlled cases

| Case | Expected route | Boundary retained |
| --- | --- | --- |
| Structural question and healthy current index | Use one focused CodeGraph exploration or narrow structural query | Direct source, compiler, tests, and runtime remain authoritative for their claims |
| Structural question and safe uninitialized checkout | Initialize non-interactively, read status back, then query | Initialization is checkout-specific local derived state |
| Structural question but CodeGraph is unavailable or incompatible | Use native inspection and report the degraded route | No implicit global install, upgrade, or MCP reconfiguration |
| Literal text, documentation, policy prose, logs, or configuration | Use `rg`, file listing, and direct reads | No unnecessary graph query or index creation |
| Pending or stale indexed files | Refresh only when the affected claim needs current graph state | No default full rebuild |
| Lock, integrity problem, or failed incremental repair | Preserve evidence and continue safe native work | No destructive repair without separate authority |

## Verification snapshot

The validated source boundary is commit
`4191e2d5c40cf660fc410f48841d2aa6a5dbcbda`. At its local-adoption checkpoint:

- all 23 policy-contract tests passed;
- Ruff lint and formatting checks passed;
- all 11 packaged Skills passed the bundled Skill structural validator;
- a fresh pre-merge check of the independent `cli-command-reference` Skill
  exposed one unsupported legacy `compatibility` frontmatter field; removing
  only that field preserved the native-command routing and made the official
  Skill validator pass;
- the source and formally installed plugin each contained 26 files and shared
  aggregate tree SHA-256
  `60827995b6b1f97e5a0e4a4b1488ea12099007a813fa4bef255174ef8e0abe8c`;
- CodeGraph 1.6.2 reported a complete index for the exact source checkout with
  17 files, 36 nodes, 118 edges, no pending changes, no worktree mismatch, no
  extraction-version mismatch, and no reindex recommendation; and
- a focused structural MCP query completed successfully against that checkout.

The package manifests, lifecycle route, README files, contributor and privacy
guidance, operations reference, and policy contracts were reviewed as one
coherent source boundary.

## Combined integration and current activation

The original verified local-adoption checkpoint used plugin version
`2.0.0+codex.20261008141523`. It proves that the Plan B source could be
formally installed and loaded from an identical package tree at that point in
time. It is not a timeless claim about whichever local candidate is installed
later.

A separately owned concurrent worktree subsequently installed its own
adaptive-loop candidate. Both histories were independently revalidated before
integration, then combined without rewriting either line at merge commit
`af937f82d2e3801b181816e82836e4e2f55b6d1a`.

The final `work-governance-local` marketplace now points to the integrated
`main` worktree. Plugin version `2.0.0+codex.20261008145343` is installed and
enabled from that source. Source and installed plugin inventories each contain
26 files, recursive comparison reports no difference, and both relative-path
aggregates equal SHA-256
`ad5b931da0189bba51f84030be49717825ee9ab9947ce7f33c223cfe0447ff35`.
All 11 installed Skills validate, and installed `work-lifecycle` contains both
the adaptive decision/review contract and the `code-intelligence` route.

The combined source passes 26 policy-contract tests and Ruff checks. After an
incremental refresh, CodeGraph 1.6.2 reports a complete exact-checkout index
with 17 files, 39 nodes, 135 edges, no pending changes, no worktree mismatch,
no extraction-version mismatch, and no reindex recommendation. A focused
structural MCP exploration returned the current CodeGraph, adaptive-loop, and
manifest-contract test symbols from the combined tree.

The isolated adaptive-loop worktree and branch remain preserved; the combined
installation changed the active marketplace and Plugin, not that historical
candidate.

## Delivery boundary

Git source delivery, the remote branch readback, and exact-commit CI are
verified independently of this source evidence. A local commit, a healthy
CodeGraph index, and a successful installation do not by themselves prove a
Push or CI result. This adoption does not create a tag or release, deploy, or
modify an external production environment.

The pre-change source revision
`42ca9c6e525d63f1f1ea2a81ec4b61b876646ee2` remains the historical comparison
point. Any source rollback or installed-plugin replacement is a separately
authorized operation and must preserve unrelated work.
