# Work Governance Plugin

Work Governance is a Codex plugin that governs a task from intake through
planning, execution, evidence review, independent validation, and handoff.

The repository-local marketplace is `.agents/plugins/marketplace.json` and the
plugin source is `plugins/work-governance`.

## Skills

- `work-governance:work-lifecycle` is the mandatory lifecycle entry.
- `work-governance:git-change-governance` controls Git isolation and delivery
  boundaries.
- `work-governance:project-truth-governance` selects durable project authority
  locations.
- `work-governance:independent-validation` challenges plans, artifacts, and
  completion evidence.

## Install

Add the repository root as a local marketplace, then install the plugin:

```sh
codex plugin marketplace add /path/to/codex-work-governance
codex plugin add work-governance@work-governance-local
```

Start a new Codex thread after installation so the plugin skills are loaded.

## Controller

`plugins/work-governance/scripts/workctl.py` is a PEP 723 script. Run it from a
governed project with:

```sh
uv run --script /path/to/workctl.py plan status
```

The controller uses `_Plan/index.yaml` only to locate the active Plan.
`_Plan/<plan-id>.md` frontmatter is the sole mutable execution authority. The
controller enforces expected revisions, dependency and confirmation gates,
artifact quarantine states, atomic Plan writes, and append-only logs.

## Validate

```sh
uv run --group dev ruff check .
uv run --group dev mypy --strict plugins/work-governance/scripts/workctl.py tests
uv run --group dev pytest -q
```

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.

The plugin itself does not provide a hosted service or telemetry. See
`PRIVACY.md` and `TERMS.md` for the public policy boundary.
