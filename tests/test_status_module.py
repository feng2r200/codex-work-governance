from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

status_module = importlib.import_module("workctl_modules.status")
compact_plan_status = status_module.compact_plan_status


def no_blockers(_frontmatter: Mapping[str, object]) -> Sequence[Mapping[str, object]]:
    """Return an empty blocking-detail projection."""
    return []


def no_confirmations(_frontmatter: Mapping[str, object]) -> Sequence[str]:
    """Return an empty pending-confirmation projection."""
    return []


def no_legacy_refresh(_frontmatter: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return no legacy-refresh projection."""
    return None


def test_compact_plan_status_preserves_default_payload_shape() -> None:
    """Compact status keeps the bounded public JSON shape and scheduler ordering."""

    def ready_targets(
        _frontmatter: Mapping[str, object],
        priorities: Mapping[str, int],
    ) -> Sequence[str]:
        assert priorities == {"T-002": 5}
        return ["task:T-002", "task:T-001"]

    payload = compact_plan_status(
        {
            "plan_id": "PLAN-20260806-001",
            "goal": {"statement": "Reduce status friction."},
            "tasks": [
                {"id": "T-001", "status": "pending"},
                {"id": "T-002", "status": "pending"},
            ],
        },
        scheduler={"priorities": {"T-002": 5}},
        ready_task_targets=ready_targets,
        task_blocking_details=no_blockers,
        pending_confirmation_ids=no_confirmations,
        legacy_refresh_projection=no_legacy_refresh,
    )

    assert payload == {
        "plan_id": "PLAN-20260806-001",
        "goal": {"statement": "Reduce status friction."},
        "current_task": "task:T-002",
        "ready": ["task:T-002", "task:T-001"],
        "blocked": [],
        "blocked_details": [],
        "parallel_ready": ["task:T-002", "task:T-001"],
        "confirmation_gates": [],
        "next_suggestion": "Start task:T-002",
    }


def test_compact_plan_status_resolves_current_task_blocker() -> None:
    """An in-progress task with a blocking detail produces the blocker suggestion."""

    def ready_targets(
        _frontmatter: Mapping[str, object],
        _priorities: Mapping[str, int],
    ) -> Sequence[str]:
        return ["task:T-001"]

    def blockers(_frontmatter: Mapping[str, object]) -> Sequence[Mapping[str, object]]:
        return [
            {
                "task": "task:T-001",
                "status": "in_progress",
                "reasons": [{"kind": "artifact", "artifact": "A-001"}],
            }
        ]

    payload = compact_plan_status(
        {
            "plan_id": "PLAN-20260806-001",
            "tasks": [{"id": "T-001", "status": "in_progress"}],
        },
        ready_task_targets=ready_targets,
        task_blocking_details=blockers,
        pending_confirmation_ids=no_confirmations,
        legacy_refresh_projection=no_legacy_refresh,
    )

    assert payload["current_task"] == "task:T-001"
    assert payload["ready"] == []
    assert payload["blocked"] == ["task:T-001"]
    assert payload["next_suggestion"] == "Resolve blockers for task:T-001 before advancing."


def test_compact_plan_status_adds_legacy_refresh_when_present() -> None:
    """Legacy refresh remains an optional compact-status projection."""

    def ready_targets(
        _frontmatter: Mapping[str, object],
        _priorities: Mapping[str, int],
    ) -> Sequence[str]:
        return []

    def pending(_frontmatter: Mapping[str, object]) -> Sequence[str]:
        return ["C-PLAN-DECISION"]

    def legacy(_frontmatter: Mapping[str, object]) -> Mapping[str, object] | None:
        return {"requires_migration": True, "from_schema_version": 4}

    payload = compact_plan_status(
        {"plan_id": "PLAN-20260806-001", "tasks": []},
        ready_task_targets=ready_targets,
        task_blocking_details=no_blockers,
        pending_confirmation_ids=pending,
        legacy_refresh_projection=legacy,
    )

    assert payload["next_suggestion"] == "Resolve the pending confirmation gate."
    assert payload["confirmation_gates"] == ["C-PLAN-DECISION"]
    assert payload["legacy_refresh"] == {
        "requires_migration": True,
        "from_schema_version": 4,
    }
