---
name: code-intelligence
description: Use when software work needs structural source-code understanding, such as symbol discovery, callers or callees, call paths, change impact, affected tests, or cross-layer tracing, and CodeGraph readiness may need to be established or refreshed for the active checkout. Do not use for literal text search, prose, logs, configuration-only inspection, or non-code work. A source-read-only task does not suppress local derived-index refresh when current graph state is needed.
---

# Code Intelligence

Use this Skill as an optional source-intelligence adapter. It chooses between
CodeGraph and native inspection, establishes and maintains safe per-checkout
readiness when the structural route is useful, and leaves project truth and
durable work state to their own authorities.

## Route By Question

- Use CodeGraph for indexed source-code structure: definitions, symbols,
  callers, callees, call paths, change impact, affected tests, and
  cross-layer relationships.
- Use native `rg`, file listing, and direct file reading for literal text,
  documentation, policy prose, logs, configuration, generated output, and
  unsupported file types.
- Do not initialize or refresh CodeGraph merely because a repository exists. The
  current task must have a concrete structural question that the graph can
  answer.
- A task may keep the source tree read-only while still updating the local
  `.codegraph` derived state. Source-read-only is not derived-state-read-only.
- Treat graph relationships and impact as best-effort evidence. Compiler,
  tests, runtime probes, and direct source remain the authorities for claims
  those mechanisms own.

## Establish Readiness

Evaluate three independent conditions:

1. **Task applicability:** the work needs structural source intelligence.
2. **Global tool availability:** a compatible CodeGraph CLI is available, and
   either its MCP tool or its direct query commands can be used.
3. **Active-checkout index health:** `codegraph status --json` reports a
   healthy, current index for the exact checkout being inspected, after any
   required refresh.

Resolve the project path from the active checkout, not from the Git common
directory. Different worktrees can contain different source and therefore need
checkout-specific indexes.

If the task is applicable, global capability is present, current authority
permits local derived-state creation, and the exact active checkout is writable
but uninitialized, run the non-interactive initialization flow in
[CodeGraph operations](references/codegraph.md), then read status back before
relying on the graph. If an existing index reports pending changes, stale
coverage, a worktree mismatch, an extraction-version mismatch, a reindex
recommendation, or any other non-current state, run the prescribed incremental
refresh and status readback before querying. If that readback remains stale,
or an incremental refresh reports an ordinary staleness failure, perform the
prescribed full index refresh and read status back again. This local derived
index is neither project truth nor durable work state, and its refresh is
allowed even when the source task itself is read-only.

Do not initialize or mutate an index when any of these apply:

- the path is a synced project mirror, reference-only `sources/` tree, home
  directory, filesystem root, or another protected location;
- the active checkout root is ambiguous or cannot be verified;
- the task is prose-, configuration-, log-, or data-only and has no structural
  source question;
- CodeGraph is unavailable or incompatible.

If the exact active checkout is authorized and writable but a source-read-only
task cannot update its local derived index, do not use the stale graph. Continue
with native inspection or report the degraded route instead.

Missing global capability is a degraded route: use native inspection and report
the missing capability. Do not install CodeGraph, change global MCP
configuration, upgrade it, or alter shell configuration implicitly.

## Use The Graph Deliberately

- Prefer one focused CodeGraph exploration that returns relevant source and
  relationships over repeated symbol-by-symbol calls.
- Pass the exact active-checkout path on every CLI or MCP request.
- Treat verbatim source returned by CodeGraph as already read. Do not repeat
  the same lookup with `rg` or direct file reading.
- Before any CodeGraph query, use the exact-checkout status and do not query an
  index that reports pending changes, stale coverage, a worktree mismatch, an
  extraction-version mismatch, a reindex recommendation, or another unknown
  freshness condition. Refresh it even when the source task is read-only.
- Refresh only what the evidence requires: use incremental synchronization
  first, and use a full index refresh when the status still reports stale state
  or explicitly recommends reindexing. Do not rebuild a healthy current index.
- Stop using the graph for a route it does not cover; continue with native
  inspection instead of retrying equivalent graph queries.
- Never run destructive `uninit`, force initialization, `unlock`, or
  equivalent repair automatically. A lock or integrity problem is a distinct
  diagnosis and authorization boundary.

Read [CodeGraph operations](references/codegraph.md) for exact readiness,
initialization, refresh, query, and repository-hygiene commands.
