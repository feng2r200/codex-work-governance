# CodeGraph Operations

Use these operations only after the parent Skill establishes that a structural
source-code question makes CodeGraph useful.

## Resolve The Exact Checkout

From inside the checkout:

```sh
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
test -n "$PROJECT_ROOT"
test "$PROJECT_ROOT" != "/"
test "$PROJECT_ROOT" != "$HOME"
```

Use the returned checkout root. Do not substitute
`git rev-parse --git-common-dir`: linked worktrees share a common Git
directory while their source trees can differ.

If the directory is not Git-managed, use a user- or project-authorized source
root only when it is unambiguous. Never infer a broad parent directory.

## Check Global Capability

```sh
command -v codegraph
codegraph version
```

For MCP use, also require a currently available CodeGraph tool. If MCP is
absent but the CLI query commands are available, the CLI remains a valid local
route. If the CLI is missing or incompatible, use native inspection and report
the degraded route. Global installation, upgrade, and MCP configuration are
separate actions:

```sh
codegraph install --target codex --location global --yes
```

The installation command is reference material, not standing authority to run
it.

## Check And Prepare Project Readiness

```sh
codegraph status --json "$PROJECT_ROOT"
```

For a healthy route, verify at least:

- `initialized` is true and `index.state` is complete;
- `worktreeMismatch` is null;
- `index.reindexRecommended` is false;
- extraction-version fields do not report a mismatch; and
- pending changes are empty for a claim that depends on current graph state.

Treat a missing field as unknown for the obligation it would prove. A readable
JSON response alone is not proof that the index is current.

For a structural source question, any of the following means the index is not
current: it is uninitialized or incomplete, reports pending changes, has a
worktree mismatch, has an extraction-version mismatch, recommends reindexing,
or leaves a required freshness field unknown. Do not issue a CodeGraph query
against that index. A source-read-only task does not exempt local `.codegraph`
derived state from this freshness check or from the refresh below.

When the result says `initialized: false`, initialize only if all parent-Skill
gates pass:

```sh
codegraph init --yes "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

The second command is mandatory readback. Success means the exact checkout now
has a readable index; it does not prove every language or file is covered.

When an initialized index is not current, refresh it before any graph query.
Use incremental synchronization first, regardless of whether the source task is
read-only:

```sh
codegraph sync "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

If the status readback still reports stale state, an extraction-version
mismatch, `index.reindexRecommended: true`, an incomplete index, or another
freshness failure, or if incremental synchronization fails for that ordinary
staleness condition, perform the full index refresh and read status back again:

```sh
codegraph index "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

Only use CodeGraph after the final readback proves the index is current. If a
full refresh fails, the failure indicates a lock or integrity problem, or the
status remains stale, preserve the failure evidence, do not rely on the stale
graph, and continue with native inspection where it can answer the question.
These commands update only local `.codegraph` derived state; they do not
authorize source edits, commits, or external operations.

CodeGraph creates `.codegraph/` as local derived state. Keep it out of
project truth and commits. For a Git repository, prefer an exact local exclude
for `/.codegraph/` after checking the repository's existing ignore policy.
Do not edit the tracked `.gitignore` merely to hide one local index, and do
not overwrite unrelated entries in the Git local exclude file.

## Query

Prefer the CodeGraph MCP exploration tool when it is available and pass the
exact checkout path. Follow the live tool schema because MCP tool names and
parameters can evolve.

Direct CLI equivalents include:

```sh
codegraph explore --path "$PROJECT_ROOT" "trace the request from route to storage"
codegraph query --path "$PROJECT_ROOT" --json "symbol_name"
codegraph node --path "$PROJECT_ROOT" "symbol_name"
codegraph callers --path "$PROJECT_ROOT" --json "symbol_name"
codegraph callees --path "$PROJECT_ROOT" --json "symbol_name"
codegraph impact --path "$PROJECT_ROOT" --json "symbol_name"
codegraph affected --path "$PROJECT_ROOT"
```

Start with `explore` for an area or flow. Use the narrower commands to answer
a specific unresolved question, not to recreate the same context repeatedly.

## Refresh And Repair

The normal initialized project uses incremental updates. Before a claim that
depends on current graph state, inspect status. If status identifies pending
changes, stale coverage, a worktree mismatch, or another non-current state, run
the incremental refresh and mandatory readback above. Do not defer this because
the source task is read-only.

```sh
codegraph sync "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

Use a full rebuild only when the readback shows incremental synchronization did
not repair the index or the status explicitly recommends reindexing:

```sh
codegraph index "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

Do not run `codegraph uninit`, `codegraph unlock`, force flags, or repeated
rebuilds automatically. Preserve the failure evidence, continue independent
work with native tools where safe, and obtain the authority needed for a
destructive or control-plane repair.
