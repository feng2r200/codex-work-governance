"""Bounded high-level workflow input readers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


class WorkflowInputError(ValueError):
    """Raised when a workflow input source is missing, ambiguous, or too large."""


def read_workflow_input_bytes(
    *,
    use_stdin: bool,
    raw_path: object,
    required: bool,
    max_bytes: int,
    stdin_reader: Callable[[int], bytes],
) -> bytes | None:
    """Read one bounded high-level workflow input from stdin or a file."""
    if use_stdin and isinstance(raw_path, str):
        raise WorkflowInputError("WORKFLOW_INPUT_SOURCE_CONFLICT")
    if use_stdin:
        content = stdin_reader(max_bytes + 1)
    elif isinstance(raw_path, str):
        source = Path(raw_path)
        if source.is_symlink() or not source.is_file():
            raise WorkflowInputError("WORKFLOW_INPUT_MISSING")
        content = source.read_bytes()
    elif required:
        raise WorkflowInputError("WORKFLOW_INPUT_REQUIRED")
    else:
        return None
    if len(content) > max_bytes:
        raise WorkflowInputError("WORKFLOW_INPUT_TOO_LARGE")
    return content
