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

## Check And Create Project Readiness

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

When the result says `initialized: false`, initialize only if all parent-Skill
gates pass:

```sh
codegraph init --yes "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

The second command is mandatory readback. Success means the exact checkout now
has a readable index; it does not prove every language or file is covered.

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
depends on current graph state, inspect status. If status or a query identifies
pending changes or stale coverage, run:

```sh
codegraph sync "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

Use a full rebuild only when evidence shows incremental synchronization cannot
repair the index:

```sh
codegraph index "$PROJECT_ROOT"
codegraph status --json "$PROJECT_ROOT"
```

Do not run `codegraph uninit`, `codegraph unlock`, force flags, or repeated
rebuilds automatically. Preserve the failure evidence, continue independent
work with native tools where safe, and obtain the authority needed for the
specific repair.
