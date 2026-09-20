# Contributing

Thank you for helping improve Work Governance.

## Design Contract

Keep the plugin composable and tool-neutral:

- clear, actionable work must not be blocked by ceremony;
- Plans and SubAgents are introduced only when they add coordination value;
- one module owns each judgment;
- persistence providers remain optional, separate Skills;
- authority boundaries are never inferred from available credentials; and
- tests protect current behavior, not obsolete prose or historical versions.

A proposal that embeds a state engine, requires one CLI, creates a second
mutable authority, or makes governance mandatory for every task should explain
the demonstrated need and why a smaller policy change is insufficient.

## Development

Requirements: Python 3.12 or newer and `uv`.

```sh
uv sync --locked --all-groups
uv run pytest
uv run ruff check tests/test_policy_contract.py
```

Run the Codex Skill and plugin validators when they are available, using the
commands in the repository README.

## Pull Requests

- Keep one coherent policy boundary per pull request.
- Explain the user-visible failure mode and the intended behavior.
- Add or update a focused contract test.
- Update both plugin manifests when identity or interface metadata changes.
- Do not include credentials, personal paths, generated caches, or local
  `.work-governance` state.
- State what was validated and what remains unverified.

By contributing, you agree that your contribution is licensed under the
Apache License 2.0 used by this repository.
