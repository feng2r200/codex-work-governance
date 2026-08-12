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
completion_claims = status_module.completion_claims
queue_projection = status_module.queue_projection


def no_blockers(_frontmatter: Mapping[str, object]) -> Sequence[Mapping[str, object]]:
    """Return an empty blocking-detail projection."""
    return []


def no_confirmations(_frontmatter: Mapping[str, object]) -> Sequence[str]:
    """Return an empty pending-confirmation projection."""
    return []


def no_legacy_refresh(_frontmatter: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return no legacy-refresh projection."""
    return None


def incomplete_ids(frontmatter: Mapping[str, object], field: str) -> Sequence[str]:
    """Return incomplete item IDs with the controller's verified-state rule."""
    values = frontmatter.get(field, [])
    if not isinstance(values, list):
        return [f"{field}:invalid"]
    result: list[str] = []
    for item in values:
        if not isinstance(item, Mapping):
            result.append(f"{field}:invalid")
            continue
        if item.get("status") not in {"verified", "skipped"}:
            result.append(str(item.get("id", f"{field}:unknown")))
    return result


def confirmations_by_id(
    frontmatter: Mapping[str, object],
) -> Mapping[str, Mapping[str, object]]:
    """Return required and accepted confirmations keyed by id."""
    result: dict[str, Mapping[str, object]] = {}
    raw = frontmatter.get("confirmations", {})
    for group in ("required", "accepted"):
        for item in raw.get(group, []) if isinstance(raw, Mapping) else []:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                result[str(item["id"])] = item
    return result


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


def test_queue_projection_preserves_public_queue_views() -> None:
    """Queue projections keep ready, blocked, and next command JSON shapes."""
    compact = {
        "ready": ["task:T-002", "task:T-001"],
        "blocked": ["task:T-003"],
        "current_task": "task:T-002",
        "parallel_ready": ["task:T-002", "task:T-001"],
        "blocked_details": [
            {
                "task": "task:T-003",
                "status": "blocked",
                "reasons": [{"kind": "explicit-block"}],
            }
        ],
        "next_suggestion": "Start task:T-002",
    }

    assert queue_projection(compact, "ready") == ["task:T-002", "task:T-001"]
    assert queue_projection(compact, "blocked") == ["task:T-003"]
    assert queue_projection(compact, "next") == {
        "current_task": "task:T-002",
        "parallel_ready": ["task:T-002", "task:T-001"],
        "blocked_details": [
            {
                "task": "task:T-003",
                "status": "blocked",
                "reasons": [{"kind": "explicit-block"}],
            }
        ],
        "next_suggestion": "Start task:T-002",
    }


def test_completion_claims_marks_local_delivery_without_route_completion() -> None:
    """Local delivery completion cannot claim route completion or authorized action."""
    frontmatter = {
        "confirmations": {
            "required": [
                {
                    "id": "C-LIVE-SWITCH",
                    "description": "Activate the candidate",
                    "status": "pending",
                }
            ]
        },
        "delivery": {"status": "complete"},
        "activation": {"status": "pending_confirmation", "confirmation_id": "C-LIVE-SWITCH"},
        "route": {"slice_status": "validated", "confirmation_gate": "C-LIVE-SWITCH"},
        "obligations": [{"id": "O-001", "status": "verified"}],
        "validations": [{"id": "V-001", "status": "skipped"}],
        "tasks": [
            {"id": "T-LOCAL", "status": "verified"},
            {"id": "T-ROUTE", "status": "pending", "completion_scope": "route"},
        ],
        "artifacts": [{"id": "A-001", "status": "final"}],
    }

    payload = completion_claims(
        frontmatter,
        {"ready": False},
        incomplete_entry_ids=incomplete_ids,
        confirmations_by_id=confirmations_by_id,
    )

    assert payload == {
        "activation_authorized": False,
        "activation_confirmation_id": "C-LIVE-SWITCH",
        "delivery_declared_complete": True,
        "level": "local_delivery_complete",
        "local_delivery_complete": True,
        "no_required_next_step_allowed": False,
        "route_complete": False,
        "slice_confirmation_id": "C-LIVE-SWITCH",
        "slice_next_action_authorized": False,
        "slice_status": "validated",
    }


def test_completion_claims_accepts_gate_without_route_completion() -> None:
    """Accepted gate evidence authorizes the next action without closing the route."""
    frontmatter = {
        "confirmations": {
            "required": [
                {
                    "id": "C-LIVE-SWITCH",
                    "description": "Activate the candidate",
                    "status": "accepted",
                    "ref": "user:accepted",
                }
            ]
        },
        "delivery": {"status": "in_progress"},
        "activation": {"status": "pending_confirmation", "confirmation_id": "C-LIVE-SWITCH"},
        "route": {"slice_status": "validated", "confirmation_gate": "C-LIVE-SWITCH"},
        "obligations": [{"id": "O-001", "status": "verified"}],
        "validations": [{"id": "V-001", "status": "verified"}],
        "tasks": [{"id": "T-001", "status": "verified"}],
        "artifacts": [{"id": "A-001", "status": "final"}],
    }

    payload = completion_claims(
        frontmatter,
        {"ready": False},
        incomplete_entry_ids=incomplete_ids,
        confirmations_by_id=confirmations_by_id,
    )

    assert payload["activation_authorized"] is True
    assert payload["level"] == "in_progress"
    assert payload["route_complete"] is False
    assert payload["slice_next_action_authorized"] is True


def test_completion_claims_route_readiness_allows_no_required_next_step() -> None:
    """Route readiness is the only source of the no-required-next-step claim."""
    payload = completion_claims(
        {
            "route": {"slice_status": "complete", "confirmation_gate": "none"},
            "delivery": {"status": "in_progress"},
            "tasks": [{"id": "T-001", "status": "pending"}],
        },
        {"ready": True},
        incomplete_entry_ids=incomplete_ids,
        confirmations_by_id=confirmations_by_id,
    )

    assert payload["level"] == "route_complete"
    assert payload["no_required_next_step_allowed"] is True
    assert payload["route_complete"] is True
    assert payload["slice_next_action_authorized"] is True


def test_completion_claims_preserves_malformed_activation_confirmation_id() -> None:
    """Projection preserves legacy output shape even when activation id is malformed."""
    payload = completion_claims(
        {"activation": {"confirmation_id": 123}, "route": {"confirmation_gate": "none"}},
        {"ready": False},
        incomplete_entry_ids=incomplete_ids,
        confirmations_by_id=confirmations_by_id,
    )

    assert payload["activation_authorized"] is False
    assert payload["activation_confirmation_id"] == 123
