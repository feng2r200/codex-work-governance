# Privacy

Work Governance is a local Codex plugin. The plugin itself does not collect,
store, sell, or transmit personal data, and it does not include telemetry or a
hosted service.

The plugin can instruct Codex to read or write project files and to run local
commands when a user authorizes that work. Data processed by Codex, the operating
system, marketplaces, source-control hosts, or other external tools remains
subject to those products' policies and the user's configuration.

Durable Goals, Plans, Tasks, sessions, evidence references, authorization
receipts, history, and closeout inspection data are handled by the installed
WorkVCS CLI and its configured local store. Work Governance tells Codex when
durable state is useful, but it does not bundle a state engine, register
lifecycle hooks, or transmit data to a hosted service.

No-Plan work should not call WorkVCS and should not create durable governance
state. When work is promoted into a WorkVCS-backed Plan, the admission payload
may include bounded prior context such as request digests, confirmed facts,
decisions, evidence references, constraints, unknowns, acceptance anchors, and
next actions. Users should not place credentials, secrets, or unnecessary
personal data in Plans, WorkVCS records, logs, receipts, or evidence.

Tracked `.work-governance` files in this repository are historical audit data
from older plugin versions. They are not scanned, migrated, or rewritten by
default.
