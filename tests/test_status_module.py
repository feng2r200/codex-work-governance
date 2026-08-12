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
current_schema_refresh_status = status_module.current_schema_refresh_status
legacy_refresh_projection = status_module.legacy_refresh_projection
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


def refresh_projection(frontmatter: Mapping[str, object]) -> Mapping[str, object]:
    """Return a representative read-only migration projection."""
    return {
        "from_schema_version": frontmatter.get("schema_version"),
        "to_schema_version": 5,
        "requires_migration": True,
        "migration_mode": "archive_legacy_and_rebuild_current_plan",
        "state_reset": True,
        "legacy_state_migrated": False,
        "legacy_summary": {"authority": "NON_AUTHORITY"},
        "not_migrated": ["task.status"],
    }


def refresh_contract_state(_frontmatter: Mapping[str, object]) -> str:
    """Return the current-schema refresh contract state."""
    return "PLAN_SCHEMA_REFRESH_REQUIRED"


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


def test_legacy_refresh_projection_reads_archive_status() -> None:
    """Archive-backed refresh guidance merges controller archive probe evidence."""

    def archive_status(archive_path: str, expected_sha256: object) -> Mapping[str, object]:
        assert archive_path == ".work-governance/_Plan/.archive/PLAN-OLD.md"
        assert expected_sha256 == "a" * 64
        return {
            "archive_status": "readable",
            "legacy_summary": {"plan_status": "active"},
        }

    payload = legacy_refresh_projection(
        {
            "legacy_archive": {
                "path": ".work-governance/_Plan/.archive/PLAN-OLD.md",
                "sha256": "a" * 64,
                "from_schema_version": 4,
            }
        },
        archive_status_projection=archive_status,
    )

    assert payload == {
        "archive_path": ".work-governance/_Plan/.archive/PLAN-OLD.md",
        "archive_sha256": "a" * 64,
        "archive_status": "readable",
        "from_schema_version": 4,
        "legacy_state_migrated": False,
        "legacy_summary": {"plan_status": "active"},
        "migration_mode": "archive_legacy_and_rebuild_current_plan",
        "next_model_action": (
            "Review legacy_summary and the archived legacy Plan before selecting the "
            "next current-schema task."
        ),
        "not_migrated": [
            "task.status",
            "task.note",
            "task.evidence",
            "confirmations",
            "runtime_state",
            "current_task",
            "revision_history",
        ],
        "runtime_state": "fresh",
        "state_reset": True,
    }


def test_legacy_refresh_projection_handles_missing_archive_path_without_probe() -> None:
    """Missing archive path is reported without invoking archive file probes."""

    def archive_status(_archive_path: str, _expected_sha256: object) -> Mapping[str, object]:
        raise AssertionError("archive probe should not run without a path")

    payload = legacy_refresh_projection(
        {"legacy_archive": {"from_schema_version": 4}},
        archive_status_projection=archive_status,
    )

    assert payload is not None
    assert payload["archive_status"] == "missing_path"
    assert payload["archive_path"] is None


def test_legacy_refresh_projection_propagates_archive_problem_statuses() -> None:
    """Archive probe results are preserved in the legacy refresh projection."""
    cases = [
        {"archive_status": "missing"},
        {"archive_status": "sha256_mismatch", "actual_archive_sha256": "b" * 64},
        {"archive_status": "unreadable", "archive_error": "PATH_ESCAPES_PROJECT"},
    ]

    for archive_result in cases:

        def archive_status(
            _archive_path: str,
            _expected_sha256: object,
            result: Mapping[str, object] = archive_result,
        ) -> Mapping[str, object]:
            return result

        payload = legacy_refresh_projection(
            {
                "legacy_archive": {
                    "path": ".work-governance/_Plan/.archive/PLAN-OLD.md",
                    "sha256": "a" * 64,
                }
            },
            archive_status_projection=archive_status,
        )

        assert payload is not None
        for key, value in archive_result.items():
            assert payload[key] == value


def test_current_schema_refresh_status_keeps_queue_fields_out_of_default_view() -> None:
    """Outdated active Plan status is read-only refresh guidance, not a runnable queue."""
    payload = current_schema_refresh_status(
        {
            "plan_id": "PLAN-20260806-001",
            "schema_version": 4,
            "status": "active",
            "contract": {"revision": 3},
            "tasks": [{"id": "T-001", "status": "verified"}],
        },
        authority_state="PLAN_SCHEMA_REFRESH_REQUIRED",
        blocking_reasons=["active Plan requires current-schema refresh"],
        current_schema_version=5,
        migration_projection=refresh_projection,
        contract_state=refresh_contract_state,
        full=False,
    )

    assert payload["authority_state"] == "PLAN_SCHEMA_REFRESH_REQUIRED"
    assert payload["blocking_reasons"] == ["active Plan requires current-schema refresh"]
    assert payload["contract_state"] == "PLAN_SCHEMA_REFRESH_REQUIRED"
    assert payload["current_schema_version"] == 5
    assert payload["expected_contract_revision"] == 3
    assert payload["legacy_summary"] == {"authority": "NON_AUTHORITY"}
    assert payload["requires_migration"] is True
    assert "migrate apply --expected-contract-revision 3" in str(payload["next_suggestion"])
    assert "ready" not in payload
    assert "current_task" not in payload


def test_current_schema_refresh_status_full_view_adds_authority_details() -> None:
    """Full refresh status adds authority details without scheduling tasks."""
    payload = current_schema_refresh_status(
        {
            "plan_id": "PLAN-20260806-001",
            "schema_version": 4,
            "status": "active",
            "revision": 7,
            "goal": {"statement": "Reduce friction."},
            "tasks": [{"id": "T-001"}],
            "confirmations": {"required": []},
        },
        authority_state="PLAN_SCHEMA_REFRESH_REQUIRED",
        blocking_reasons=[],
        current_schema_version=5,
        migration_projection=refresh_projection,
        contract_state=refresh_contract_state,
        full=True,
        authority_candidates=[{"plan_id": "PLAN-20260806-001"}],
        allowed_commands=["migrate inspect|apply|recover"],
    )

    assert payload["authority_candidates"] == [{"plan_id": "PLAN-20260806-001"}]
    assert payload["allowed_commands"] == ["migrate inspect|apply|recover"]
    assert payload["expected_contract_revision"] == 7
    assert payload["goal"] == {"statement": "Reduce friction."}
    assert payload["tasks"] == [{"id": "T-001"}]
    assert payload["confirmations"] == {"required": []}
