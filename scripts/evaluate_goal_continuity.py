#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

"""Inspect a Codex JSONL trial without turning caller-supplied files into proof.

The command-line interface is deliberately observational. A real behavior
claim is produced only by ``run_behavior_trial.py``, which owns the subprocess,
the randomized trial instance, and the independent post-process oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class ContractError(ValueError):
    """Report an invalid evaluation contract or trajectory."""


@dataclass(frozen=True)
class CheckResult:
    """Represent one independently observable evaluation check."""

    name: str
    passed: bool
    detail: str

    def as_json(self) -> dict[str, JsonValue]:
        """Return stable check fields for a JSON report."""
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class TokenMetric:
    """Hold one trace-backed token total and its completeness evidence."""

    source_field: str
    value: int | None
    observed_lines: tuple[int, ...]
    missing_lines: tuple[int, ...]

    def as_json(self) -> dict[str, JsonValue]:
        """Return the measurement without converting missing usage into zero."""
        return {
            "status": "observed" if self.value is not None else "unknown",
            "value": self.value,
            "source_field": self.source_field,
            "observed_lines": list(self.observed_lines),
            "missing_lines": list(self.missing_lines),
        }


@dataclass(frozen=True)
class ResourceObservation:
    """Describe token usage and unavailable elapsed time from the raw trace."""

    trace_path: str
    completed_turn_lines: tuple[int, ...]
    input_tokens: TokenMetric
    cached_input_tokens: TokenMetric
    output_tokens: TokenMetric

    def as_json(self) -> dict[str, JsonValue]:
        """Return trace provenance, complete token totals, and explicit unknowns."""
        return {
            "source": {
                "trace_path": self.trace_path,
                "event_type": "turn.completed",
                "line_numbers": list(self.completed_turn_lines),
                "aggregation": (
                    "sum each usage field across completed turns only when that field is "
                    "present on every completed turn"
                ),
            },
            "token_usage": {
                "input_tokens": self.input_tokens.as_json(),
                "cached_input_tokens": self.cached_input_tokens.as_json(),
                "output_tokens": self.output_tokens.as_json(),
            },
            "elapsed_time_seconds": {
                "status": "unknown",
                "value": None,
                "reason": "raw trace has no reliable elapsed-time field",
            },
        }


@dataclass(frozen=True)
class TraceSummary:
    """Hold lifecycle-bound observations extracted from one Codex turn."""

    thread_id: str
    completed_turns: int
    final_messages: int
    completed_commands: int
    failed_commands: int
    transient_errors: int
    greatest_identical_failure_count: int
    commands: tuple[CompletedCommand, ...]
    changed_paths: tuple[ChangedPath, ...]
    resources: ResourceObservation

    def as_json(self) -> dict[str, JsonValue]:
        """Return observable trajectory facts for a JSON report."""
        return {
            "thread_id": self.thread_id,
            "completed_turns": self.completed_turns,
            "final_messages": self.final_messages,
            "completed_commands": self.completed_commands,
            "failed_commands": self.failed_commands,
            "transient_errors": self.transient_errors,
            "greatest_identical_failure_count": self.greatest_identical_failure_count,
            "commands": [command.as_json() for command in self.commands],
            "changed_paths": [change.as_json() for change in self.changed_paths],
        }


@dataclass(frozen=True)
class CompletedCommand:
    """Retain one completed command and its observable output from the raw trace."""

    line_number: int
    command: str
    exit_code: int
    output: str

    def as_json(self) -> dict[str, JsonValue]:
        """Return command provenance without duplicating potentially large output."""
        return {
            "line_number": self.line_number,
            "command": self.command,
            "exit_code": self.exit_code,
            "output_bytes": len(self.output.encode("utf-8")),
            "output_sha256": hashlib.sha256(self.output.encode("utf-8")).hexdigest(),
        }


@dataclass(frozen=True)
class ChangedPath:
    """Retain one file-change path from the raw trace."""

    line_number: int
    path: str
    kind: str

    def as_json(self) -> dict[str, JsonValue]:
        """Return the path and source line used by the boundary oracle."""
        return {"line_number": self.line_number, "path": self.path, "kind": self.kind}


@dataclass(frozen=True)
class StartedItem:
    """Retain the fields that must agree across item lifecycle events."""

    item_type: str
    command: str | None
    changes: tuple[tuple[str, str], ...] | None


def parse_arguments() -> argparse.Namespace:
    """Parse the offline observation arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a Codex JSONL trial. This offline command never certifies "
            "that a behavior trial was actually executed."
        )
    )
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, JsonValue]:
    """Load one top-level JSON object or raise ``ContractError``."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON file {path}: {exc}") from exc
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise ContractError(f"JSON file must contain an object: {path}")
    return raw


def require_object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    """Return ``value`` as an object or reject the named field."""
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def require_list(value: JsonValue, label: str) -> list[JsonValue]:
    """Return ``value`` as a list or reject the named field."""
    if not isinstance(value, list):
        raise ContractError(f"{label} must be a list")
    return value


def require_nonempty_list(value: JsonValue, label: str) -> list[JsonValue]:
    """Return a non-empty list or reject a vacuous contract field."""
    items = require_list(value, label)
    if not items:
        raise ContractError(f"{label} must not be empty")
    return items


def require_string(value: JsonValue, label: str) -> str:
    """Return a non-empty string or reject the named field."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"{label} must be a non-empty trimmed string")
    return value


def require_positive_integer(value: JsonValue, label: str) -> int:
    """Return a positive integer while rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{label} must be a positive integer")
    return value


def resolve_workspace_path(workspace: Path, relative: str) -> Path:
    """Resolve a relative contract path without allowing workspace escape."""
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ContractError(f"contract path must be relative: {relative}")
    resolved = (workspace / candidate).resolve()
    if not resolved.is_relative_to(workspace):
        raise ContractError(f"contract path escapes workspace: {relative}")
    return resolved


def sha256_file(path: Path) -> str:
    """Compute and return the hexadecimal SHA-256 digest of a regular file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def token_metric(
    field: str,
    total: int,
    observed_lines: list[int],
    missing_lines: list[int],
    completed_turn_lines: list[int],
) -> TokenMetric:
    """Build a complete total or an explicit unknown for one usage field."""
    complete = bool(completed_turn_lines) and not missing_lines
    return TokenMetric(
        source_field=f"usage.{field}",
        value=total if complete else None,
        observed_lines=tuple(observed_lines),
        missing_lines=tuple(missing_lines),
    )


def parse_file_changes(value: object, line_number: int) -> tuple[tuple[str, str], ...]:
    """Validate and normalize one raw ``file_change`` item."""
    if not isinstance(value, list) or not value:
        raise ContractError(f"trace line {line_number} file changes must be a non-empty list")
    changes: list[tuple[str, str]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ContractError(f"trace line {line_number} file changes[{index}] must be an object")
        changed_path = raw.get("path")
        kind = raw.get("kind")
        if not isinstance(changed_path, str) or not changed_path:
            raise ContractError(
                f"trace line {line_number} file changes[{index}].path must be non-empty"
            )
        if not isinstance(kind, str) or not kind:
            raise ContractError(
                f"trace line {line_number} file changes[{index}].kind must be non-empty"
            )
        changes.append((changed_path, kind))
    return tuple(changes)


def parse_trace(path: Path) -> TraceSummary:
    """Validate one complete Codex JSONL lifecycle and summarize its effects."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"cannot read trace {path}: {exc}") from exc
    if not lines:
        raise ContractError("trace is empty")

    events: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            raw: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid JSONL at trace line {line_number}: {exc}") from exc
        if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
            raise ContractError(f"trace line {line_number} must contain an object")
        events.append(raw)

    if events[0].get("type") != "thread.started":
        raise ContractError("trace line 1 must be thread.started")
    thread_id = events[0].get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ContractError("trace line 1 thread_id must be non-empty")
    if len(events) < 3 or events[1].get("type") != "turn.started":
        raise ContractError("trace line 2 must be turn.started")
    if events[-1].get("type") != "turn.completed":
        raise ContractError("the final trace event must be turn.completed")

    started_items: dict[str, StartedItem] = {}
    completed_item_ids: set[str] = set()
    completed_commands = 0
    failed_commands = 0
    transient_errors = 0
    final_messages = 0
    failure_runs: dict[str, int] = {}
    commands: list[CompletedCommand] = []
    changed_paths: list[ChangedPath] = []
    last_item_type: str | None = None
    completed_turn_lines: list[int] = []
    usage_totals = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    usage_observed_lines: dict[str, list[int]] = {field: [] for field in usage_totals}
    usage_missing_lines: dict[str, list[int]] = {field: [] for field in usage_totals}

    for line_number, event in enumerate(events, start=1):
        event_type = event.get("type")
        if event_type not in {
            "thread.started",
            "turn.started",
            "item.started",
            "item.completed",
            "error",
            "turn.completed",
        }:
            raise ContractError(f"trace line {line_number} has unsupported event type")
        if line_number > 1 and event_type == "thread.started":
            raise ContractError(f"trace line {line_number} repeats thread.started")
        if line_number != 2 and event_type == "turn.started":
            raise ContractError(f"trace line {line_number} repeats or reorders turn.started")
        if event_type == "turn.completed":
            if line_number != len(events):
                raise ContractError(f"trace line {line_number} completes the turn before EOF")
            if started_items:
                pending = ", ".join(sorted(started_items))
                raise ContractError(f"turn completed with unfinished items: {pending}")
            completed_turn_lines.append(line_number)
            usage = event.get("usage")
            if usage is None:
                for field in usage_totals:
                    usage_missing_lines[field].append(line_number)
            elif not isinstance(usage, dict):
                raise ContractError(
                    f"trace line {line_number} field usage must be an object or null"
                )
            else:
                for field in usage_totals:
                    value = usage.get(field)
                    if value is None:
                        usage_missing_lines[field].append(line_number)
                    elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise ContractError(
                            f"trace line {line_number} field usage.{field} "
                            "must be a non-negative integer or null"
                        )
                    else:
                        usage_totals[field] += value
                        usage_observed_lines[field].append(line_number)
            if last_item_type != "agent_message":
                raise ContractError("turn.completed must follow a completed final agent message")
            continue
        if event_type in {"thread.started", "turn.started"}:
            continue
        if event_type == "error":
            message = event.get("message")
            if not isinstance(message, str) or not message.strip():
                raise ContractError(
                    f"trace line {line_number} transient error message must be non-empty"
                )
            transient_errors += 1
            continue

        item = event.get("item")
        if not isinstance(item, dict):
            raise ContractError(f"trace line {line_number} item must be an object")
        item_id = item.get("id")
        item_type = item.get("type")
        if not isinstance(item_id, str) or not item_id:
            raise ContractError(f"trace line {line_number} item.id must be non-empty")
        if not isinstance(item_type, str) or not item_type:
            raise ContractError(f"trace line {line_number} item.type must be non-empty")
        command_value = item.get("command")
        command = command_value if isinstance(command_value, str) and command_value else None
        changes = (
            parse_file_changes(item.get("changes"), line_number)
            if item_type == "file_change"
            else None
        )

        if event_type == "item.started":
            if item_id in started_items or item_id in completed_item_ids:
                raise ContractError(f"trace line {line_number} reuses item id {item_id}")
            if item_type == "command_execution" and command is None:
                raise ContractError(f"trace line {line_number} command must be non-empty")
            started_items[item_id] = StartedItem(
                item_type=item_type,
                command=command,
                changes=changes,
            )
            continue

        if item_id in completed_item_ids:
            raise ContractError(f"trace line {line_number} repeats completed item id {item_id}")
        started = started_items.pop(item_id, None)
        if item_type == "command_execution":
            if started is None:
                raise ContractError(
                    f"trace line {line_number} completes command {item_id} without item.started"
                )
            if started.item_type != item_type or started.command != command:
                raise ContractError(
                    f"trace line {line_number} command lifecycle fields do not match item.started"
                )
            exit_code = item.get("exit_code")
            if isinstance(exit_code, bool) or not isinstance(exit_code, int):
                raise ContractError(f"trace line {line_number} exit_code must be an integer")
            output_value = item.get("aggregated_output", "")
            if not isinstance(output_value, str):
                raise ContractError(f"trace line {line_number} aggregated_output must be a string")
            completed_commands += 1
            assert command is not None
            commands.append(
                CompletedCommand(
                    line_number=line_number,
                    command=command,
                    exit_code=exit_code,
                    output=output_value,
                )
            )
            if exit_code != 0:
                failed_commands += 1
                command_key = command if command is not None else "<unknown-command>"
                failure_runs[command_key] = failure_runs.get(command_key, 0) + 1
        elif item_type == "file_change":
            if started is None:
                raise ContractError(
                    f"trace line {line_number} completes file change {item_id} without item.started"
                )
            if started.item_type != item_type or started.changes != changes:
                raise ContractError(
                    f"trace line {line_number} file-change lifecycle fields "
                    "do not match item.started"
                )
            assert changes is not None
            changed_paths.extend(
                ChangedPath(line_number=line_number, path=changed_path, kind=kind)
                for changed_path, kind in changes
            )
        elif started is not None and started.item_type != item_type:
            raise ContractError(f"trace line {line_number} item type changed during lifecycle")
        elif item_type == "agent_message":
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ContractError(f"trace line {line_number} agent message must be non-empty")
            final_messages += 1
        completed_item_ids.add(item_id)
        last_item_type = item_type

    return TraceSummary(
        thread_id=thread_id,
        completed_turns=1,
        final_messages=final_messages,
        completed_commands=completed_commands,
        failed_commands=failed_commands,
        transient_errors=transient_errors,
        greatest_identical_failure_count=max(failure_runs.values(), default=0),
        commands=tuple(commands),
        changed_paths=tuple(changed_paths),
        resources=ResourceObservation(
            trace_path=str(path.resolve()),
            completed_turn_lines=tuple(completed_turn_lines),
            input_tokens=token_metric(
                "input_tokens",
                usage_totals["input_tokens"],
                usage_observed_lines["input_tokens"],
                usage_missing_lines["input_tokens"],
                completed_turn_lines,
            ),
            cached_input_tokens=token_metric(
                "cached_input_tokens",
                usage_totals["cached_input_tokens"],
                usage_observed_lines["cached_input_tokens"],
                usage_missing_lines["cached_input_tokens"],
                completed_turn_lines,
            ),
            output_tokens=token_metric(
                "output_tokens",
                usage_totals["output_tokens"],
                usage_observed_lines["output_tokens"],
                usage_missing_lines["output_tokens"],
                completed_turn_lines,
            ),
        ),
    )


def validate_contract(contract: dict[str, JsonValue]) -> tuple[str, dict[str, JsonValue]]:
    """Validate a non-vacuous observation and independent-outcome contract."""
    if contract.get("schema_version") != 2:
        raise ContractError("schema_version must equal 2")
    task_id = require_string(contract.get("task_id"), "task_id")
    require_string(contract.get("trial_kind"), "trial_kind")
    trace_contract = require_object(contract.get("trace"), "trace")
    require_positive_integer(
        trace_contract.get("minimum_completed_commands"),
        "trace.minimum_completed_commands",
    )
    require_positive_integer(
        trace_contract.get("minimum_final_messages"),
        "trace.minimum_final_messages",
    )
    boundary = require_object(trace_contract.get("boundary"), "trace.boundary")
    if boundary.get("workspace_only") is not True:
        raise ContractError("trace.boundary.workspace_only must equal true")
    forbidden_executables = require_nonempty_list(
        boundary.get("forbidden_executables"),
        "trace.boundary.forbidden_executables",
    )
    for index, value in enumerate(forbidden_executables):
        require_string(value, f"trace.boundary.forbidden_executables[{index}]")
    required_files = require_nonempty_list(contract.get("required_files"), "required_files")
    for index, value in enumerate(required_files):
        require_string(value, f"required_files[{index}]")
    outcome_contract = require_object(contract.get("outcome_contract"), "outcome_contract")
    require_string(outcome_contract.get("oracle_id"), "outcome_contract.oracle_id")
    required_checks = require_nonempty_list(
        outcome_contract.get("required_checks"), "outcome_contract.required_checks"
    )
    for index, value in enumerate(required_checks):
        require_string(value, f"outcome_contract.required_checks[{index}]")
    return task_id, trace_contract


def evaluate_trace(
    trace_contract: dict[str, JsonValue], summary: TraceSummary
) -> list[CheckResult]:
    """Evaluate declared trajectory minimums against a lifecycle-valid trace."""
    minimum_messages = require_positive_integer(
        trace_contract.get("minimum_final_messages"),
        "trace.minimum_final_messages",
    )
    minimum_commands = require_positive_integer(
        trace_contract.get("minimum_completed_commands"),
        "trace.minimum_completed_commands",
    )
    return [
        CheckResult(
            "trace.single_complete_turn",
            summary.completed_turns == 1,
            f"observed={summary.completed_turns}, required=1",
        ),
        CheckResult(
            "trace.final_messages",
            summary.final_messages >= minimum_messages,
            f"observed={summary.final_messages}, required>={minimum_messages}",
        ),
        CheckResult(
            "trace.completed_commands",
            summary.completed_commands >= minimum_commands,
            f"observed={summary.completed_commands}, required>={minimum_commands}",
        ),
    ]


def shell_payload(command: str, line_number: int) -> str:
    """Return the script executed by a traced shell wrapper."""
    try:
        outer = shlex.split(command)
    except ValueError as exc:
        raise ContractError(f"trace line {line_number} command is not valid shell syntax") from exc
    if (
        len(outer) == 3
        and outer[0] in {"/bin/bash", "/bin/sh", "/bin/zsh"}
        and outer[1] in {"-c", "-lc"}
    ):
        return outer[2]
    return command


def lexical_command_boundary_observations(
    command: CompletedCommand,
    workspace: Path,
    forbidden_executables: frozenset[str],
) -> tuple[list[str], list[str]]:
    """Return literal boundary hints without claiming runtime enforcement.

    Dynamic executable construction, interpreter behavior, command substitution,
    symlink resolution, and runtime-generated paths are deliberately outside this
    lexical observation. The runner reports enforced isolation separately.
    """
    payload = shell_payload(command.command, command.line_number)
    try:
        lexer = shlex.shlex(payload, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError as exc:
        raise ContractError(
            f"trace line {command.line_number} command payload is not valid shell syntax"
        ) from exc

    forbidden: list[str] = []
    for token in tokens:
        candidate = token.rstrip(";,|&")
        if Path(candidate).name in forbidden_executables:
            forbidden.append(candidate)

    escapes: list[str] = []
    if re.search(r"(?:^|[\s'\"=:(])\.\.(?:/|$)", payload):
        escapes.append("parent traversal")
    for marker in ("$HOME", "${HOME}", "$CODEX_HOME", "${CODEX_HOME}", "~/"):
        if marker in payload:
            escapes.append(marker)
    absolute_paths = re.findall(
        r"(?<![A-Za-z0-9_.:-])(/[A-Za-z0-9_][A-Za-z0-9_./@%+~=:-]*)",
        payload,
    )
    for raw_path in absolute_paths:
        normalized = raw_path.rstrip(".,;:)")
        resolved = Path(normalized).resolve(strict=False)
        if not resolved.is_relative_to(workspace):
            escapes.append(normalized)
    return forbidden, escapes


def evaluate_trace_boundary(
    trace_contract: dict[str, JsonValue], summary: TraceSummary, workspace: Path
) -> list[CheckResult]:
    """Report lexical command hints and trace-reported file-change locations."""
    boundary = require_object(trace_contract.get("boundary"), "trace.boundary")
    values = require_nonempty_list(
        boundary.get("forbidden_executables"),
        "trace.boundary.forbidden_executables",
    )
    forbidden_executables = frozenset(
        require_string(value, f"trace.boundary.forbidden_executables[{index}]")
        for index, value in enumerate(values)
    )
    forbidden_hits: list[str] = []
    escape_hits: list[str] = []
    for command in summary.commands:
        forbidden, escapes = lexical_command_boundary_observations(
            command,
            workspace,
            forbidden_executables,
        )
        forbidden_hits.extend(f"line {command.line_number}: {value}" for value in forbidden)
        escape_hits.extend(f"line {command.line_number}: {value}" for value in escapes)

    file_change_escapes: list[str] = []
    for change in summary.changed_paths:
        changed_path = Path(change.path)
        resolved = (
            changed_path.resolve(strict=False)
            if changed_path.is_absolute()
            else (workspace / changed_path).resolve(strict=False)
        )
        if not resolved.is_relative_to(workspace):
            file_change_escapes.append(f"line {change.line_number}: {change.path}")
    return [
        CheckResult(
            "trace.lexical_forbidden_executable_hits_absent",
            not forbidden_hits,
            (
                "lexical heuristic only; no literal hits"
                if not forbidden_hits
                else "lexical heuristic only; " + "; ".join(forbidden_hits)
            ),
        ),
        CheckResult(
            "trace.lexical_workspace_escape_hits_absent",
            not escape_hits,
            (
                "lexical heuristic only; no literal hits"
                if not escape_hits
                else "lexical heuristic only; " + "; ".join(escape_hits)
            ),
        ),
        CheckResult(
            "trace.reported_file_changes_within_workspace",
            not file_change_escapes,
            (
                "all trace-reported file changes resolve inside the workspace"
                if not file_change_escapes
                else "; ".join(file_change_escapes)
            ),
        ),
    ]


def evaluate_required_files(contract: dict[str, JsonValue], workspace: Path) -> list[CheckResult]:
    """Check that every declared deliverable exists as a regular file."""
    results: list[CheckResult] = []
    values = require_nonempty_list(contract.get("required_files"), "required_files")
    for index, value in enumerate(values):
        relative = require_string(value, f"required_files[{index}]")
        path = resolve_workspace_path(workspace, relative)
        exists = path.is_file()
        results.append(
            CheckResult(
                f"required_file:{relative}",
                exists,
                "regular file exists" if exists else "missing regular file",
            )
        )
    return results


def evaluate_protected_files(contract: dict[str, JsonValue], workspace: Path) -> list[CheckResult]:
    """Verify every protected input against its runner-recorded digest."""
    results: list[CheckResult] = []
    values = require_list(contract.get("protected_files", []), "protected_files")
    for index, value in enumerate(values):
        item = require_object(value, f"protected_files[{index}]")
        relative = require_string(item.get("path"), f"protected_files[{index}].path")
        expected = require_string(item.get("sha256"), f"protected_files[{index}].sha256")
        if len(expected) != 64 or any(
            character not in "0123456789abcdef" for character in expected
        ):
            raise ContractError(f"protected_files[{index}].sha256 must be a lowercase digest")
        path = resolve_workspace_path(workspace, relative)
        actual = sha256_file(path) if path.is_file() else "missing"
        results.append(
            CheckResult(
                f"protected_file:{relative}",
                actual == expected,
                f"expected={expected}, actual={actual}",
            )
        )
    return results


def evaluate_observation(
    contract: dict[str, JsonValue], trace_path: Path, workspace: Path
) -> dict[str, JsonValue]:
    """Return bounded observations without certifying process or outcome provenance."""
    task_id, trace_contract = validate_contract(contract)
    resolved_workspace = workspace.resolve()
    if not resolved_workspace.is_dir() or resolved_workspace == Path(resolved_workspace.anchor):
        raise ContractError("workspace must be an existing non-root directory")
    summary = parse_trace(trace_path)
    checks = evaluate_trace(trace_contract, summary)
    checks.extend(evaluate_trace_boundary(trace_contract, summary, resolved_workspace))
    checks.extend(evaluate_required_files(contract, resolved_workspace))
    checks.extend(evaluate_protected_files(contract, resolved_workspace))
    observation_checks_passed = all(check.passed for check in checks)
    return {
        "schema_version": 2,
        "task_id": task_id,
        "claim_scope": "untrusted_offline_observation",
        "behavior_passed": False,
        "passed": False,
        "observation_checks_passed": observation_checks_passed,
        "independent_outcome_status": "not_executed_by_offline_evaluator",
        "trace": summary.as_json(),
        "resource_observation": summary.resources.as_json(),
        "checks": [check.as_json() for check in checks],
    }


def main() -> int:
    """Run the offline observer and never return a behavior-success status."""
    arguments = parse_arguments()
    try:
        contract = load_json(arguments.contract)
        report = evaluate_observation(contract, arguments.trace, arguments.workspace)
    except ContractError as exc:
        print(json.dumps({"schema_version": 2, "passed": False, "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    sys.exit(main())
