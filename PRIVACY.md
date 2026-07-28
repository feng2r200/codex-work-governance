# Privacy

Work Governance is a local Codex plugin. The plugin itself does not collect,
store, sell, or transmit personal data, and it does not include telemetry or a
hosted service.

The plugin can instruct Codex to read or write project files and to run local
commands when a user authorizes that work. Data processed by Codex, the operating
system, marketplaces, source-control hosts, or other external tools remains
subject to those products' policies and the user's configuration.

The bundled SessionStart hook reads the installed Plugin payload and relevant
local layout inputs, may prewarm pinned Python dependencies through UV on the
first or changed bootstrap, and writes only inside the invoked project's
`.work-governance/` root. It does not alter business dependency groups, global
UV configuration, or Python installations. After readiness, controller checks
run offline.

Plan state and bounded canonical evidence metadata are versionable under
`.work-governance/_Plan/`. Evidence records contain explicit producer and
subject references plus caller-selected metadata items; they must not contain
secrets, arbitrary payloads, or full process transcripts.

Process logs, bootstrap and legacy-adoption receipts, dependency cache,
migration runtime, runtime Plugin bundles, and detailed operational evidence
remain locally ignored under `.work-governance/` by default. READY receipt
schema v2 includes the Codex session identifier, absolute local paths to the
snapshotted controller and lifecycle skill, and hashes binding those files to
the installed Plugin payload. The runtime bundle is retained so the session
uses the same controller even if the Plugin cache entry is replaced or
removed. A newer receipt supersedes older sessions for writes.

The ignored `runtime/bootstrap-capability.json` uses the same bounded session,
runtime-path, and hash fields while SessionStart is bootstrapping. It is
restricted to layout mutation, replaced by a newer SessionStart, and never
serves as Plan-write readiness.

Blocked bootstrap evidence may include the bounded SessionStart source and
session identifier supplied by Codex so a failure can be correlated without
copying arbitrary hook input into the receipt. A legacy-adoption receipt
contains local physical worktree and Git identity paths so that it cannot
authorize another worktree; only its digest is retained in the versionable
migration proof. A strictly validated legacy reconciliation proposal may be
copied byte-for-byte from `_Plan/proposals/` to the locally ignored
`.work-governance/proposals/`; migration does not apply it or accept its
confirmations. Legacy `.logs/` entries move only when Plan ID, log schema, or
an active evidence reference proves Work Governance ownership; unrelated
business logs remain in place. Users should not place credentials, secrets,
or unnecessary personal data in Plans, logs, receipts, or evidence.
