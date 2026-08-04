"""Stable public workflow command descriptions."""

from __future__ import annotations

from typing import Final

WORKFLOW_HELP: Final[dict[str, dict[str, object]]] = {
    "plan": {
        "commands": [
            "plan create",
            "plan show [--full]",
            "plan edit",
            "plan reorder",
            "plan status",
            "plan ready",
            "plan next",
            "plan blocked",
        ],
        "note": "Contract edits require their existing confirmation and revision guards.",
    },
    "task": {
        "commands": [
            "task start",
            "task block",
            "task unblock",
            "task verify [--evidence-stdin]",
            "task reprioritize",
        ],
        "note": "Task transitions remain receipt-bound and dependency-checked.",
    },
    "evidence": {
        "commands": [
            "evidence record --stdin",
            "plan evidence record --manifest PATH|--stdin",
        ],
        "note": "Evidence is bounded, canonical, content-addressed, and redaction-safe.",
    },
    "migration": {
        "commands": ["migrate inspect", "migrate apply", "migrate recover"],
        "note": "Migration is explicit, backed up, and recovery-bound.",
    },
}
