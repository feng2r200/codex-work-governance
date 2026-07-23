# Privacy

Work Governance is a local Codex plugin. The plugin itself does not collect,
store, sell, or transmit personal data, and it does not include telemetry or a
hosted service.

The plugin can instruct Codex to read or write project files and to run local
commands when a user authorizes that work. Data processed by Codex, the operating
system, marketplaces, source-control hosts, or other external tools remains
subject to those products' policies and the user's configuration.

The bundled controller writes Plan state only in the project where it is
invoked. Optional process logs remain local under `.logs/` by default. Users
should not place credentials, secrets, or unnecessary personal data in Plans or
logs.
