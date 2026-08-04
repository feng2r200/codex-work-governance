"""Stable public workflow command descriptions."""

from __future__ import annotations

from typing import Final

WORKFLOW_HELP: Final[dict[str, dict[str, object]]] = {
    "plan": {
        "commands": [
            "goal show",
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
    "gate": {
        "commands": [
            "gate list",
            "gate check --gate-id C-001",
            "gate open",
            "gate satisfy",
            "gate waive",
        ],
        "note": "Gate writes are aliases over strict Plan confirmation transactions.",
    },
    "truth": {
        "commands": ["truth list", "truth conflicts", "truth add --manifest PATH"],
        "note": "Truth writes are aliases over the confirmed contract revision path.",
    },
    "review": {
        "commands": [
            "review status",
            "review request",
            "review attach --manifest PATH",
        ],
        "note": "Review attachment uses the independent-review recorder and its trust rules.",
    },
    "evidence": {
        "commands": [
            "evidence capture --task T-001 --kind command-output --summary TEXT",
            "evidence record --stdin",
            "plan evidence record --manifest PATH|--stdin",
        ],
        "note": (
            "Direct capture writes redacted blobs and an append-only ledger; "
            "Plan evidence records remain the bounded canonical compatibility path."
        ),
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
