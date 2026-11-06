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

Select the user's installed CLI through an explicit stable absolute entry, not
ambient PATH. The placeholder below must be replaced by that verified entry;
all later direct CLI examples reuse it.

```sh
CODEGRAPH_BIN="/absolute/user-owned/codegraph"
case "$CODEGRAPH_BIN" in /*) ;; *) exit 1 ;; esac
test -x "$CODEGRAPH_BIN"
"$CODEGRAPH_BIN" --version
"$CODEGRAPH_BIN" explore --help
```

Read the help content: it must describe the `explore` command itself. A zero
exit with only top-level help does not prove command support. For a host tool,
inspect the CLI identity and capability at its actual subprocess boundary;
a shell probe may resolve a different installation. An explicitly installed
host adapter may own this check, but must not silently fall back to another
CLI, install/upgrade it, or treat command failure as an empty graph. Recheck
after a CLI/host change; keep the entry and observed version with the evidence.

For MCP use, also require a currently available CodeGraph tool. If MCP is
absent but the CLI query commands are available, the CLI remains a valid local
route. If the CLI is missing or incompatible, use native inspection and report
the degraded route. Global installation, upgrade, and MCP configuration are
separate actions, and the registration route depends on the host.

When the installer recognizes the host, it writes that host's MCP
configuration:

```sh
"$CODEGRAPH_BIN" install --target <host> --location global --yes
```

When it does not, register the same stdio server through the host's own MCP
configuration instead:

```sh
<agent> mcp add codegraph -- "$CODEGRAPH_BIN" serve --mcp
```

Verify the resulting route by its reported connection and tool list rather than
by assuming either command applies. Both are reference material, not standing
authority to run them.

## Check And Prepare Project Readiness

```sh
"$CODEGRAPH_BIN" status --json "$PROJECT_ROOT"
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
"$CODEGRAPH_BIN" init --yes "$PROJECT_ROOT"
"$CODEGRAPH_BIN" status --json "$PROJECT_ROOT"
```

The second command is mandatory readback. Success means the exact checkout now
has a readable index; it does not prove every language or file is covered.

When an initialized index is not current, refresh it before any graph query.
Use incremental synchronization first, regardless of whether the source task is
read-only:

```sh
"$CODEGRAPH_BIN" sync "$PROJECT_ROOT"
"$CODEGRAPH_BIN" status --json "$PROJECT_ROOT"
```

If the status readback still reports stale state, an extraction-version
mismatch, `index.reindexRecommended: true`, an incomplete index, or another
freshness failure, or if incremental synchronization fails for that ordinary
staleness condition, perform the full index refresh and read status back again:

```sh
"$CODEGRAPH_BIN" index "$PROJECT_ROOT"
"$CODEGRAPH_BIN" status --json "$PROJECT_ROOT"
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
"$CODEGRAPH_BIN" explore --path "$PROJECT_ROOT" "trace the request from route to storage"
"$CODEGRAPH_BIN" query --path "$PROJECT_ROOT" --json "symbol_name"
"$CODEGRAPH_BIN" node --path "$PROJECT_ROOT" "symbol_name"
"$CODEGRAPH_BIN" callers --path "$PROJECT_ROOT" --json "symbol_name"
"$CODEGRAPH_BIN" callees --path "$PROJECT_ROOT" --json "symbol_name"
"$CODEGRAPH_BIN" impact --path "$PROJECT_ROOT" --json "symbol_name"
"$CODEGRAPH_BIN" affected --path "$PROJECT_ROOT"
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
"$CODEGRAPH_BIN" sync "$PROJECT_ROOT"
"$CODEGRAPH_BIN" status --json "$PROJECT_ROOT"
```

Use a full rebuild only when the readback shows incremental synchronization did
not repair the index or the status explicitly recommends reindexing:

```sh
"$CODEGRAPH_BIN" index "$PROJECT_ROOT"
"$CODEGRAPH_BIN" status --json "$PROJECT_ROOT"
```

Do not run `codegraph uninit`, `codegraph unlock`, force flags, or repeated
rebuilds automatically. Preserve the failure evidence, continue independent
work with native tools where safe, and obtain the authority needed for a
destructive or control-plane repair.
