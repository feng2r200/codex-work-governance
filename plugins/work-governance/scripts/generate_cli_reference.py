#!/usr/bin/env python3
"""Generate the documented CLI surface from the controller's argparse tree."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTROLLER_PATH = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts" / "workctl.py"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "CLI_REFERENCE.md"


def load_controller() -> ModuleType:
    """Load the controller module without running its command entry point."""
    sys.path.insert(0, str(CONTROLLER_PATH.parent))
    try:
        spec = importlib.util.spec_from_file_location("workctl_cli_reference", CONTROLLER_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load controller: {CONTROLLER_PATH}")
        module = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(spec.name)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            return module
        finally:
            if previous is None:
                sys.modules.pop(spec.name, None)
            else:
                sys.modules[spec.name] = previous
    finally:
        sys.path.pop(0)


def subcommand_choices(
    parser: argparse.ArgumentParser,
) -> Mapping[str, argparse.ArgumentParser]:
    """Return the nested subcommand parsers attached to an argparse parser."""
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if not isinstance(choices, dict):
            continue
        typed = {
            name: child
            for name, child in choices.items()
            if isinstance(name, str) and isinstance(child, argparse.ArgumentParser)
        }
        if len(typed) == len(choices):
            return typed
    return {}


def leaf_parsers(
    parser: argparse.ArgumentParser,
    path: Sequence[str],
) -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    """Yield every executable command parser in deterministic path order."""
    choices = subcommand_choices(parser)
    if not choices:
        yield tuple(path), parser
        return
    for name in sorted(choices):
        yield from leaf_parsers(choices[name], (*path, name))


def workflow_section(workflows: Mapping[str, Mapping[str, object]]) -> str:
    """Render the short stable workflow aliases maintained by the command module."""
    sections: list[str] = ["## Stable workflow aliases", ""]
    for name in sorted(workflows):
        workflow = workflows[name]
        sections.extend((f"### `{name}`", ""))
        commands = workflow.get("commands", [])
        if isinstance(commands, list) and all(isinstance(item, str) for item in commands):
            sections.extend(f"- `{item}`" for item in cast(list[str], commands))
        note = workflow.get("note")
        if isinstance(note, str):
            sections.extend(("", note))
        sections.append("")
    return "\n".join(sections).rstrip()


def render_reference(parser: argparse.ArgumentParser) -> str:
    """Render the complete nested argparse command surface as Markdown."""
    from workctl_modules.commands import WORKFLOW_HELP

    sections = [
        "# Work Governance CLI reference",
        "",
        "> Generated from the public `plugins/work-governance/scripts/workctl.py` "
        "entrypoint and current kernel parser by `generate_cli_reference.py`; "
        "edit the kernel parser, not this file.",
        "",
        "## Invocation contract",
        "",
        "Use the registered direct `workctl` executable. It runs without `uv run` "
        "and without Codex lifecycle hooks; the controller's authority and "
        "contract states decide writable Plan work.",
        "",
        "```sh",
        "workctl <domain> <command> [options]",
        "```",
        "",
        "Legacy schema-v4 compatibility commands may require an explicitly "
        "supplied current turn receipt. Ordinary schema-v5 runtime commands use "
        "the expected state guard without turn intake. "
        "Outdated active Plans report `PLAN_SCHEMA_REFRESH_REQUIRED` and allow "
        "only read-only inspection plus explicit current-schema refresh. "
        "`plan status`, `plan show`, queue views, `help`, `migrate inspect`, "
        "`migrate apply --dry-run`, `migrate rollback-info`, "
        "`frontier draft`, `context build`, `context lint`, `work status`, and "
        "default `doctor` are read-only views.",
        "",
        workflow_section(cast(Mapping[str, Mapping[str, object]], WORKFLOW_HELP)),
        "",
        "## Parser command reference",
        "",
    ]
    for path, command_parser in leaf_parsers(parser, ("workctl",)):
        sections.extend(
            (
                f"### `{' '.join(path[1:])}`",
                "",
                "```text",
                command_parser.format_help().rstrip(),
                "```",
                "",
            )
        )
    return "\n".join(sections).rstrip() + "\n"


def write_or_check(output: Path, content: str, check: bool) -> int:
    """Write the generated reference or report whether it is stale."""
    if check:
        if not output.is_file() or output.read_text(encoding="utf-8") != content:
            print(f"CLI_REFERENCE_OUT_OF_DATE: {output}", file=sys.stderr)
            return 1
        print(f"CLI_REFERENCE_VALID: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"CLI_REFERENCE_WRITTEN: {output}")
    return 0


def build_script_parser() -> argparse.ArgumentParser:
    """Build the generator's own small command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate or validate the checked-in CLI reference."""
    args = build_script_parser().parse_args(argv)
    controller = load_controller()
    build_parser = cast(Callable[[], argparse.ArgumentParser], controller.__dict__["build_parser"])
    return write_or_check(args.output, render_reference(build_parser()), args.check)


if __name__ == "__main__":
    raise SystemExit(main())
