# Optional local CodeGraph adapter for Pi

This adapter registers **one** `codegraph` tool around an existing local CLI.
It does not implement an indexer, install CodeGraph, register an MCP server, or
make CodeGraph a prerequisite for governance. The root Work Governance package
continues to expose **skills only**. This directory is an optional, separately
installed host adapter, not a runtime import from the Skills package/cache.

## Responsibility boundary

- `code-intelligence` owns when structural exploration is useful, selecting the
  exact checkout, authority to create/refresh derived state, freshness policy,
  native degradation and limits on graph evidence.
- This adapter owns Pi registration, argument translation, explicit executable
  identity, CLI/status contract checks, cancellation, output capture and errors.
- No global rule injection: three tool-specific guidelines are present only
  while the tool is active. No automatic init, refresh, repair, model request,
  package installation, daemon management or telemetry configuration.

## Install explicitly

Select an **absolute, stable, user-owned CodeGraph entry**. Do not resolve it
from runtime PATH or replace a dispatch shim with its `realpath`: Volta selects
its tool by the invoked filename. On a Volta installation, the configured
`$HOME/.volta/bin/codegraph` shim avoids an old npm-global CLI inside a Node
runtime image. Other installation methods can supply their own absolute entry.
The adapter checks actual version/help capabilities on every invocation and
never falls back to a different executable.

```sh
node integrations/pi-codegraph/install.mjs \
  --cli "$HOME/.volta/bin/codegraph" \
  --dest "$HOME/.local/share/work-governance/pi-codegraph"
```

The installer copies only declared runtime files into that stable directory,
writes `config.json` with the selected CLI, and reads back SHA-256 hashes.
`installation.json` records source location, collection time and CLI identity
for provenance; these are not runtime imports. Updates preserve the previous
installed directory as a reported `.backup-*` sibling. It refuses an unrelated
existing destination, a symlink destination, home/root, and an incompatible CLI.
It does **not** modify Pi settings or uninstall anything.

Validate the installed bytes with the real host before migrating registration:

```sh
node integrations/pi-codegraph/host-smoke.mjs \
  --sdk /absolute/installed/pi-package/dist/index.js \
  --adapter "$HOME/.local/share/work-governance/pi-codegraph"

pi install "$HOME/.local/share/work-governance/pi-codegraph"
# Only after replacement validation passes:
pi remove npm:@bopstack/pi-codegraph
```

Do not run two providers of the same tool in one newly loaded session. The
short install/remove sequence changes future resource loading, not already
loaded sessions. Once the registration change is complete, use `/reload` in an
**idle** existing Pi session, or start a new one. Do not interrupt another
agent's running task merely to reload. After migration, the same smoke command
with `--agent-dir "$HOME/.pi/agent"` checks actual configured resource discovery
and requires exactly one CodeGraph tool from the installed directory.

## Tool contract

```ts
codegraph({ action: 'diagnose' })
codegraph({ action: 'help' })
codegraph({ action: 'status', project_path: '/absolute/checkout' })
codegraph({ action: 'explore', project_path: '/absolute/checkout', query: 'request to storage', max_files: 5 })
codegraph({ action: 'node', project_path: '/absolute/checkout', file: 'src/main.ts', offset: 1, limit: 80 })
```

| Action | Required fields beyond `action` | Optional fields |
| --- | --- | --- |
| `diagnose`, `help` | none | none |
| `explore` | `project_path`, `query` | `max_files` |
| `node` | `project_path`, at least one of `file`/`symbol` | `offset`, `limit`, `symbols_only`; both file+symbol disambiguate |
| `search` (CLI `query`) | `project_path`, `query` | `kind`, `limit` |
| `files` | `project_path` | `filter`, `pattern`, `format`, `max_depth`, `no_metadata` |
| `callers`, `callees` | `project_path`, `symbol` | none |
| `impact` | `project_path`, `symbol` | `depth` |
| `affected` | `project_path`, non-empty `files` | `depth`, `filter`, `quiet` |
| `status` | `project_path` | none |
| `init` | `project_path` | none; always non-interactive `--yes` |
| `sync` | `project_path` | none |
| `index` | `project_path` | `force`, `quiet`, `verbose` |

Project paths must be absolute existing directories; symlink aliases are
canonicalized. Home/root index mutations are rejected even through aliases.
No force-init. Admin/destructive commands and `unlock` are intentionally not
exposed: lock repair requires separate explicit diagnosis and authority.
CLI input is an argv array without a shell; positional data follows `--`.
Unknown action-specific fields and invalid numeric/boolean values are errors.

Before graph queries, the adapter reads exact-root status and rejects absent,
unknown or stale readiness. It does not infer freshness from parseable JSON,
refresh automatically, or treat failure as an empty graph. A caller must use
the Skill's explicitly authorized init/sync/index flow and retry. Readiness is
a point-in-time check, not an atomic snapshot against concurrent source writes.

Every result reports `isError`; actual CLI results include path, version,
arguments, canonical project, exit code and output artifact paths. A nonzero
exit, signal, capture failure, timeout or cancellation is never reported as
success. Output is bounded to 50 KiB/2,000 lines in memory; full private temporary
artifacts remain outside the source tree. `output.txt` is a readable combined
stream in **observed chunk order**, not a cross-stream ordering guarantee;
`stdout.txt` and `stderr.txt` preserve each stream's original bytes. ANSI is
removed only from the model-facing excerpt. Temporary output files may contain
source and should be handled as local sensitive diagnostic data.

On POSIX, cancellation signals the child process group and escalates to SIGKILL
after five seconds. This covers attached descendants in that group, not a
CodeGraph daemon that independently detaches. Windows uses the direct child
kill API and has not been validated by the macOS acceptance run.

## Tests

```sh
node --test integrations/pi-codegraph/core.test.mjs
node integrations/pi-codegraph/typecheck.mjs \
  --sdk-root /absolute/installed/pi-package \
  --tsc /absolute/installed/typescript/bin/tsc
```

The typecheck uses host-supplied peer declarations via a temporary tsconfig;
it does not install duplicate SDK/typebox packages or write machine-specific
paths into this repository. The live smoke uses real Pi extension loading,
`ctx.executeTool` validation/error events and a disposable real CodeGraph
project. It verifies index artifacts, source sentinels, callers/callees,
affected tests, freshness refusal and explicit refresh/readback. It sends no
model prompt. Run it under a PATH with an incompatible bare CodeGraph first
to challenge executable selection. Core tests also supply missing/incompatible
CLIs, bad arguments, protected paths, nonzero exits, cancellation and large
UTF-8 output with stderr interleaving.

## Rollback

```sh
pi remove "$HOME/.local/share/work-governance/pi-codegraph"
pi install npm:@bopstack/pi-codegraph@0.1.1
```

Reload idle sessions afterwards. Reinstalling the old bridge restores its
behavior, **including** PATH shadowing; rollback is not a fix for that defect.
For a local-adapter update, stop resource reloads, move the current directory
aside, restore the installer's reported backup to the original destination,
and read back its `config.json`/`installation.json` before reloading.
No CodeGraph binary or project index is removed by adapter uninstallation.

The dated diagnosis, rejected alternatives, refutation contract and measured
acceptance are in `docs/research/2026-11-06-pi-codegraph-local-adapter.md` at the
repository root. Re-probe the current CLI and host after upgrades; historical
measurements are not guarantees about a later installation.
