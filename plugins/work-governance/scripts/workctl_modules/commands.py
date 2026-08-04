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
            "plan activation-repair",
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
        "note": (
            "Schema-v5 runtime transitions use state_sequence and task gates without "
            "current-turn intake; mutable v4 transitions retain their turn binding."
        ),
    },
    "evidence": {
        "commands": [
            "evidence record --stdin",
            "plan evidence record --manifest PATH|--stdin",
        ],
        "note": "Evidence is bounded, canonical, content-addressed, and redaction-safe.",
    },
    "action": {
        "commands": ["action authorize", "action consume", "action status"],
        "note": (
            "High-impact authority is current-turn, target, digest, expiry, and "
            "single-consumption bound."
        ),
    },
    "migration": {
        "commands": ["migrate inspect", "migrate apply", "migrate recover"],
        "note": "Migration is explicit, backed up, and recovery-bound.",
    },
}
