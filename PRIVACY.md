# Privacy

Work Governance is a local Codex plugin. The plugin itself does not collect,
store, sell, or transmit personal data, and it does not include telemetry or a
hosted service.

The plugin can instruct Codex to read or write project files and to run local
commands when a user authorizes that work. Data processed by Codex, the operating
system, marketplaces, source-control hosts, or other external tools remains
subject to those products' policies and the user's configuration.

The registered `workctl` executable reads relevant local layout inputs and
writes only inside the invoked project's `.work-governance/` root. It runs
directly through Python >= 3.12 and does not require Codex lifecycle hooks, a
project-local UV cache, global UV configuration, or Python package installation
during normal runtime use.

Plan state and bounded canonical evidence metadata are versionable under
`.work-governance/_Plan/`. Evidence records contain explicit producer and
subject references plus caller-selected metadata items; they must not contain
secrets, arbitrary payloads, or full process transcripts.

Process logs, bootstrap and legacy-adoption compatibility receipts, generic
local cache, migration runtime, runtime Plugin bundles, and detailed operational evidence
remain locally ignored under `.work-governance/` by default. READY receipt
schema v2 includes the Codex session identifier, absolute local paths to the
snapshotted controller and lifecycle skill, and hashes binding those files to
the installed Plugin payload. The runtime bundle is retained so the session
uses the same controller even if the Plugin cache entry is replaced or
removed. Canonical bootstrap and current-turn receipts are isolated below
`runtime/sessions/<session_id>/`; one session cannot supersede another. The
root and old runtime receipt paths remain compatibility surfaces for older
installed sessions and do not override a current session-scoped receipt.

Legacy `runtime/sessions/<session_id>/bootstrap-capability.json` files use the
same bounded session, runtime-path, and hash fields for older hook-based
bootstrap flows. They are compatibility artifacts and never serve as normal
Plan-write readiness.

Full trusted-turn intake records are locally ignored and content-addressed
under `runtime/intake-history/<plan-id>/`. They retain only the same minimal
decision fields represented by the bounded current Plan anchor; raw prompt
content is not copied into those records.

Blocked bootstrap evidence may include bounded local command context so a
failure can be correlated without copying arbitrary user input into the
receipt. A legacy-adoption receipt contains local physical worktree and Git
identity paths so that it cannot authorize another worktree; only its digest is
retained in the versionable migration proof. A strictly validated legacy
reconciliation proposal may be
copied byte-for-byte from `_Plan/proposals/` to the locally ignored
`.work-governance/proposals/`; migration does not apply it or accept its
confirmations. Legacy `.logs/` entries move only when Plan ID, log schema, or
an active evidence reference proves Work Governance ownership; unrelated
business logs remain in place. Users should not place credentials, secrets,
or unnecessary personal data in Plans, logs, receipts, or evidence.
