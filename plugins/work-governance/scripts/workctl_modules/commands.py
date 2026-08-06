"""Stable public workflow command descriptions."""

from __future__ import annotations

from typing import Final

WORKFLOW_HELP: Final[dict[str, dict[str, object]]] = {
    "goal": {
        "commands": [
            "goal show",
            "goal init --stdin|--from-file",
        ],
        "note": (
            "Use goal init to admit the minimal model-facing schema-v5 contract; "
            "runtime task state, evidence, and event history are stored separately."
        ),
    },
    "plan": {
        "commands": [
            "goal show",
            "goal init --stdin|--from-file",
            "plan create",
            "plan show [--full]",
            "plan history list|show",
            "plan edit",
            "plan reorder",
            "plan status",
            "plan ready",
            "plan next",
            "plan blocked",
            "plan activation-repair",
            "plan adapt --intent-stdin|--intent-from-file",
        ],
        "note": (
            "Start from the high-level goal/adapt/history commands when possible; "
            "schema-v4 adapt intent still requires revision/current-intake guards; "
            "strict manifest commands remain compatible for advanced controller work."
        ),
    },
    "task": {
        "commands": [
            "task start",
            "task block",
            "task unblock",
            "task verify [--evidence-stdin]",
            "task done --task-id T-001 --evidence-stdin|--from-file",
            "task reprioritize",
        ],
        "note": (
            "Use task done when raw evidence capture and verification are the same "
            "workflow; low-level transitions remain available when exact state control "
            "is needed."
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
            "review acquisition check",
            "review acquisition record-failure",
            "review acquisition status",
        ],
        "note": (
            "Review attachment uses the independent-review recorder and its trust rules; "
            "reviewer acquisition caches exact and environment-level same-mechanism "
            "validator-unavailable failures in runtime."
        ),
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
        "commands": [
            "action authorize",
            "action consume",
            "action status",
            "action lease prepare",
            "action lease issue",
            "action lease authorize",
            "action lease status",
            "action lease revoke",
        ],
        "note": (
            "Single-use capabilities and leases remain compatibility/advanced tools; "
            "confirmation judgment belongs to the model using current user authority, "
            "project rules, reversibility, risk, and evidence."
        ),
    },
    "risk": {
        "commands": [
            "risk inspect --action-kind KIND --target-ref REF",
            "risk inspect --action-kind KIND --target-ref REF --action-stdin",
        ],
        "note": (
            "Read-only facts only: the controller reports action kind, target, "
            "reversibility, evidence digest, and risk factors without deciding "
            "whether the model must ask the user."
        ),
    },
    "worktree": {
        "commands": [
            "worktree begin --worktree-id WT-ID --path PATH --branch BRANCH",
            "worktree record --worktree-id WT-ID --event EVENT --summary TEXT",
            "worktree close --worktree-id WT-ID --summary TEXT",
        ],
        "note": (
            "Worktree ledgers are runtime-only NON_AUTHORITY execution logs; only "
            "their close summary should be absorbed into the parent Plan evidence."
        ),
    },
    "migration": {
        "commands": [
            "migrate inspect",
            "migrate apply [--dry-run]",
            "migrate recover",
            "migrate rollback-info",
            "doctor",
        ],
        "note": (
            "Outdated active Plans are read-only inputs: migrate apply archives the "
            "legacy Plan, rebuilds the current schema contract, and starts fresh "
            "runtime state without adapting legacy task status."
        ),
    },
    "doctor": {
        "commands": ["doctor", "doctor --clean-stale-transactions"],
        "note": (
            "Doctor is read-only by default; cleanup only removes stale generic "
            "runtime transaction directories with no journal."
        ),
    },
}

WORKFLOW_HELP_ALIASES: Final[dict[str, str]] = {
    "migrate": "migration",
}
