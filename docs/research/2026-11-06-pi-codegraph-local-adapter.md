# Optional local Pi CodeGraph adapter

As of: 2026-11-06. Owner: Work Governance optional integrations, not core policy.

## Goal and authority

The operator requested: propose, falsify, implement and validate a local adapter
using their installed CodeGraph, then uninstall `npm:@bopstack/pi-codegraph`.
Do not uninstall CodeGraph, alter global shell PATH, delete the old CLI, change
MCP configuration, restart another live session, or commit/push this work.

## Observations and sources

Collected 2026-11-06:

- Target transcript: `~/.pi/agent/sessions/--Users-ld-Projects-HeXun-Hernes-agent_buddy--/2026-11-06T07-58-37-284Z_01a1afdd-e4e4-71fb-ba55-b5d083cc9221.jsonl`, lines 32–33: valid `explore` request, CLI `unknown command 'explore'`, exit 1, but `isError: false`.
- Installed extension `~/.pi/agent/npm/node_modules/@bopstack/pi-codegraph/src/run.ts:84` spawns bare `codegraph`; descriptors implement `explore`. The extension wraps the CLI; it is not an index engine.
- `~/.volta/tools/image/node/24.11.0/bin/codegraph --version` => 0.9.5; `~/.volta/bin/codegraph --version` => 1.6.2. The target Pi process uses Node 24.11.0. Volta package metadata labels Pi 0.84.4, but fresh `~/.volta/bin/pi --version` and the actual installed SDK package both report **1.5.0**; the metadata label is not the executable version. Acceptance below binds to the actual 1.5.0 artifact, not that historical label.
- Same parent Node, cwd and `spawn('codegraph', ...)`, changing only PATH order: runtime-first `explore` => unknown command; shim-first => missing required query. Exact `explore --help` output, not exit code alone, distinguishes capability: the old CLI misleadingly exits 0 with top-level help.
- A clean-PATH `volta run --node 24.11.0 node` prepends the runtime bin and its bare CodeGraph child reports 0.9.5. This reproduces the shadowing mechanism without modifying the running Pi.
- Explicit 1.6.2 status on this checkout was initialized/current, extraction version 27; explicit `explore` returned actual source and call paths. No third-party extension is required by the CLI itself.
- `AGENTS.md` explicitly allows optional single-responsibility adapters but forbids runtime binding to plugin caches, cwd or environment PATH. Root `package.json` exposes skills only; `tests/test_policy_contract.py` protects portable policy. `code-intelligence` already owns applicability, checkout freshness and degraded routes.

## Proposed route and refutation gate

| Part | Premise | Executable refutation / positive control | Benefit denominator | Cost basis | Reversal |
| --- | --- | --- | --- | --- | --- |
| Ownership | A host adapter can be optional without making governance depend on Pi | Keep root manifest skills-only; run policy tests. Load optional extension through real Pi SDK and verify one tool. Reject if policy package must auto-load it | All existing portable policy contracts; exactly one optional registered `codegraph` | New `integrations/pi-codegraph/` source/tests/installer plus docs; no core policy runtime | Remove explicit installed adapter package; remove new optional files/docs |
| CLI identity | Explicit stable CLI avoids shadowing | Put 0.9.5 first in PATH, execute configured shim; negative configure 0.9.5 and require capability error; same action/help shape positive configure 1.6.2 | All invocations use configured absolute entry; no fallback or ambient CLI resolution | Runner/config plus CLI capability probe; no CLI installation/upgrade | Restore previous package declaration; never mutate CLI installation |
| Tool replacement | Thin bridge covers useful original behavior | Unit adversarial checks; real temporary CodeGraph project and Pi loader/tool execution, verify emitted index/source rather than result shapes only | Explore/node/search/files/callers/callees/impact/affected/status/init/sync/index; diagnostics/help added; admin/lock repair rejected | Standard Node APIs plus host-supplied schema; no extra runtime dependencies or index engine | Keep old package until replacement passes; retain migration receipt for reinstall |
| Local delivery | Stable explicit copy can load independently of checkout/cache | Install to user-owned absolute directory, read back copied bytes/config; real host smoke there. Reject any runtime import of repository/npm plugin | Runtime files all under install destination; configured CLI outside plugin cache | Explicit installer copies only declared runtime files; Pi package registration | `pi remove <destination>` then reinstall original if needed |
| Uninstall | New registration works without old package | Only after tests, remove with `pi remove npm:@bopstack/pi-codegraph`; re-read settings/install state, load actual configured packages and assert one CodeGraph tool | Zero old declarations/install; one new provider; no model/network request required for SDK tool probe | One host package removal, fresh SDK validation; existing sessions require reload | `pi install npm:@bopstack/pi-codegraph@0.1.1` after removing local adapter |

## Responsibilities and excluded routes

Keep policy in `code-intelligence`: structural-question applicability, index
freshness, when local derived refresh is permitted, and source verification.
Keep host registration, argument translation, stable executable identity,
cancellation, bounded output and error propagation in the optional adapter.
No automatic prompt-wide rule injection, CLI installation/upgrade, lock repair,
source edits, index refresh, daemon or MCP management. Explicit index mutations
remain tools requiring task authority. Reject protected home/root targets and
force-init. Uninstalling the npm bridge does not remove its already-loaded code
from existing sessions; reload only when those sessions are idle.

Rejected proposals: documentation-only cannot register a host tool; automatic
root-package extension loading makes a host-specific dependency implicit; a
shell-PATH-only change is undone by Volta runtime prefixing; replacing
`explore` with `context` hides CLI incompatibility instead of fixing identity.

## Validation results

Collected 2026-11-06 (host smoke 09:05:22 UTC), before old-package removal:

- `node --test integrations/pi-codegraph/core.test.mjs`: **33 passed, 0 failed, 0 skipped**. Includes all 12 CLI action mappings, missing/incompatible executable, invalid fields, protected roots/aliases, freshness refusal, nonzero exit, cancellation/timeout, SIGTERM-resistant attached descendant cleanup, installer isolation and UTF-8 output/stream readback.
- `node integrations/pi-codegraph/typecheck.mjs --sdk-root <actual-installed-Pi> --tsc <installed-tsc>`: passed against the installed Pi **1.5.0** SDK and typebox peer declarations. Default editor LSP cannot resolve host-supplied peers from this dependency-free source checkout; this explicit-host check is authoritative for the entrypoint. The .mjs files also received fresh LSP probes without findings.
- `uv run pytest -q`: **49 passed**; portable governance contracts remain intact.
- Real `host-smoke.mjs` on the stable installed adapter: **20 calls/events**, **17 successes + 3 expected failures** (missing root, unsupported lock repair, stale source). Real CLI init wrote an index; explore/node returned unique source bytes; callers/callees and affected-test paths matched the fixture; explicit sync exposed changed source; full index rebuild and final status succeeded. Fixture directories were removed.
- The smoke uses the real SDK loader and nested `ctx.executeTool` validation/error pipeline with an explicitly synthetic assistant parent. It sends no model prompt and does not prove model routing/compliance or behavior in an already-loaded tmux session. Initial host-fixture failures (an empty tool allowlist, then a missing assistant parent) were apparatus failures, corrected without changing product claims.
- Fresh executable control at 09:05:06 UTC: bare CodeGraph still 0.9.5; configured old entry rejected for missing `explore,node`; configured Volta shim accepted as 1.6.2. No PATH fallback occurred.
- The first output oracle wrongly assumed cross-stream ordering; the first root oracle compared `/var` with canonical `/private/var`. Corrected the apparatus. Stream testing also exposed a real UTF-8 interleaving risk: the runner now decodes pipes separately for combined display and preserves both raw streams independently. Added a descendant liveness/termination test to challenge cancellation, not just its return flag.
- Installer delivered to `~/.local/share/work-governance/pi-codegraph`, verified SHA-256 at the destination, with configured CLI `~/.volta/bin/codegraph`. Runtime imports stay inside that directory; no root-package extension registration was added.

Machine-readable acceptance: `docs/validation/pi-codegraph-local-adapter-2026-11-06.json`.
Raw invocation logs for this run: `/tmp/wg-codegraph-unit.log`,
`/tmp/wg-codegraph-types.log`, `/tmp/wg-codegraph-policy.log`,
`/tmp/wg-codegraph-executable-controls.json`, `/tmp/wg-codegraph-install.json`,
`/tmp/wg-codegraph-host-smoke.json`. Temporary logs are diagnostic evidence, not
long-term project authority.

## Delivered migration

Collected 2026-11-06, post-removal smoke **09:08:39 UTC**:

- `pi install /Users/ld/.local/share/work-governance/pi-codegraph` succeeded.
- `pi remove npm:@bopstack/pi-codegraph` removed exactly one npm package.
- Read back `~/.pi/agent/settings.json`: old declaration absent, new local package source `../../.local/share/work-governance/pi-codegraph` present. Read back npm installation: `~/.pi/agent/npm/node_modules/@bopstack/pi-codegraph` absent.
- Re-ran the full 20-call real-host smoke using **actual user settings**, not just `-e`: exactly one CodeGraph tool, `sourceInfo.scope=user`, package source is the stable directory, CLI identity remains 1.6.2 at the configured Volta shim. All expected successes/refusals passed again.
- Real-host negative control at **09:12:56 UTC**: isolated settings loading only the root Work Governance package registered **zero** CodeGraph tools with no extension errors. The separately installed adapter is genuinely opt-in; source presence alone does not activate it. Result: `/tmp/wg-codegraph-core-isolation.json`.
- Original settings snapshot: `/tmp/wg-pi-settings-before-codegraph-migration.json`. Registration/removal logs: `/tmp/wg-codegraph-register.log`, `/tmp/wg-codegraph-remove.log`; configured-load acceptance: `/tmp/wg-codegraph-post-uninstall-smoke.json`.
- No business checkout index, CLI installation, global PATH, MCP configuration or existing live session was modified by acceptance. Existing sessions retain loaded extension code until an **idle `/reload` or new session**. No tmux input/reload was sent on the operator's behalf.
- Source changes remain uncommitted; no push or release performed. This checkout's local derived graph was refreshed only for affected-test inspection, separately from the disposable acceptance indexes.

These are dated local observations, not assurances for other machines, future
CLI/host upgrades, independently detached daemons, or concurrent source writes
between status and query. Use the README commands to revalidate those boundaries.

## Follow-up: explicit old-CLI cleanup and Codex compatibility

The operator subsequently authorized removal of the old bare CLI and asked
whether the shared package changes affect Codex. This extends the earlier
no-CLI-mutation boundary only to that exact old installation; it does not
authorize changing Codex configuration or refreshing its plugin cache.

Collected **2026-11-06 09:20:23 UTC**:

- Confirmed npm ownership with `node <node-24.11.0>/lib/node_modules/npm/bin/npm-cli.js ls --global --prefix <node-24.11.0> --depth=0`; package version was 0.9.5. The matching npm dry-run removed only the old CodeGraph wrapper and its darwin-arm64 0.9.5 package.
- Ran that npm CLI's `uninstall --global --prefix /Users/ld/.volta/tools/image/node/24.11.0 --ignore-scripts --no-audit --no-fund @colbymchenry/codegraph`. It removed **2 packages**. Verified the old package directory and runtime `bin/codegraph` are absent.
- Both bare `codegraph --version` and explicit `~/.volta/bin/codegraph --version` now return **1.6.2**. The other top-level global packages are byte-for-byte equal as npm inventory JSON, and SHA-256 of Codex config, Pi settings and the local adapter config did not change. No CodeGraph project index or live session was removed/restarted.
- Reversal, if explicitly wanted, is an exact 0.9.5 npm install under the same runtime prefix; no old-version backup was retained. Earlier observations that bare resolution returned 0.9.5 are now **historical, pre-cleanup evidence**, not current environment facts.

Collected **2026-11-06 09:25:40–09:25:48 UTC**:

- Codex CLI is **0.167.0**. `work-governance@work-governance-local` is enabled at **3.1.3**. Its Codex manifests expose Skills/interface only, with no reference to `integrations/pi-codegraph`, JS hooks or new MCP registration. Root `package.json` retains its Pi skills-only declaration. Thus the optional Pi bridge is not loaded by Codex.
- The shared change is intentional host-neutral CLI guidance: select/verify an absolute stable entry and reuse `CODEGRAPH_BIN`. It does change future adopted Skill instructions, but does not require Pi or its adapter. The cached Codex 3.1.3 `skills/code-intelligence/references/codegraph.md` currently has different bytes from source and contains no `CODEGRAPH_BIN`; this cache has not adopted the new instructions. Plugin listing alone does not establish the bytes already loaded by a live conversation.
- Read back Codex's actual MCP config: stdio `codegraph serve --mcp`, no env/cwd override. Started a disposable server with that exact command/args and inherited environment. `initialize` reports CodeGraph **1.6.2** and `tools/list` reports **only `codegraph_explore`**.
- **Refuted test premise:** expecting default `codegraph_node` and `codegraph_status` in the list was wrong. Installed 1.6.2 `lib/dist/mcp/tools.js:1555–1574` intentionally defaults to an explore-only listing; other CLI/API handlers remain. Positive control changed only the test child environment to `CODEGRAPH_MCP_TOOLS=explore,node,status` and the same protocol then listed exactly those three tools. No persistent env or Codex config was changed. The old named approval entries in Codex config do not cause unlisted tools to be exposed.
- This default MCP surface is upstream behavior, not a dependency introduced by the optional Pi adapter. The existing Skill's CLI route remains available for status, node and other focused operations. Do not infer that all Pi CLI actions will appear as separate default Codex MCP tools.
- After cleanup, the actual-settings Pi smoke again passed **20 calls/events**, CLI 1.6.2, and **49 governance tests** passed. MCP compatibility here proves a fresh configured-command handshake/schema, not a Codex model turn or a hot upgrade of an existing server.

Evidence: `/tmp/wg-codegraph-old-cli-removal.json`,
`/tmp/wg-codegraph-codex-mcp-original-assumption.json`,
`/tmp/wg-codegraph-codex-mcp-check.json`,
`/tmp/wg-codegraph-codex-mcp-expanded-check.json`,
`/tmp/wg-codegraph-after-cli-removal-smoke.json`, and
`/tmp/wg-codegraph-after-cli-removal-policy.log`. The durable summarized result
is in the machine-readable validation record linked above.
