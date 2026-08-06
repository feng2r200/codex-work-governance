"""Schema migration boundary helpers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .model import V5ContractProjection
from .plan_schema import CURRENT_PLAN_SCHEMA_VERSION


def migration_projection(frontmatter: Mapping[str, object]) -> dict[str, object]:
    """Describe one Plan's read-only current-schema refresh boundary."""
    version = frontmatter.get("schema_version")
    tasks_value = frontmatter.get("tasks", [])
    tasks = tasks_value if isinstance(tasks_value, list) else []
    truth_refs_value = frontmatter.get("truth_refs", [])
    truth_refs = truth_refs_value if isinstance(truth_refs_value, list) else []
    return {
        "from_schema_version": version,
        "to_schema_version": CURRENT_PLAN_SCHEMA_VERSION,
        "requires_migration": version != CURRENT_PLAN_SCHEMA_VERSION,
        "migration_mode": "archive_legacy_and_rebuild_current_plan",
        "write": False,
        "contract_fields": [
            "goal",
            "success_conditions",
            "truth_refs",
            "tasks",
        ],
        "state_fields": [
            "state_sequence",
            "current_task",
            "tasks",
            "priorities",
        ],
        "event_fields": ["event_sequence", "event", "subject", "payload"],
        "legacy_task_ids": [
            item.get("id")
            for item in tasks
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ],
        "state_mapping": "not performed; legacy state remains only in the archived Plan",
        "evidence_mapping": "canonical Plan evidence remains addressable by content hash",
        "truth_refs": list(truth_refs),
    }


def v5_contract_projection(frontmatter: Mapping[str, Any]) -> V5ContractProjection:
    """Project v5 contract references without reading runtime state."""
    plan_id = str(frontmatter.get("plan_id", ""))
    contract = frontmatter.get("contract")
    nested_revision = contract.get("revision") if isinstance(contract, dict) else None
    revision = frontmatter.get("contract_revision", nested_revision)
    truth_refs = frontmatter.get("truth_refs", [])
    return V5ContractProjection(
        plan_id=plan_id,
        contract_revision=int(revision) if isinstance(revision, int) else 0,
        state_ref=str(frontmatter.get("state_ref", "")),
        event_ref=str(frontmatter.get("event_ref", "")),
        evidence_ref=str(frontmatter.get("evidence_store_ref", "")),
        truth_refs=tuple(item for item in truth_refs if isinstance(item, str))
        if isinstance(truth_refs, list)
        else (),
    )


def _goal_statement(frontmatter: Mapping[str, Any]) -> str:
    """Extract a readable goal statement from a legacy Plan."""
    goal = frontmatter.get("goal")
    if isinstance(goal, dict) and isinstance(goal.get("statement"), str) and goal["statement"]:
        return str(goal["statement"])
    if isinstance(goal, str) and goal:
        return goal
    title = frontmatter.get("title")
    if isinstance(title, str) and title:
        return title
    return "Review the archived legacy Plan and establish the current execution contract."


def _success_conditions(frontmatter: Mapping[str, Any]) -> list[str]:
    """Extract current-schema success conditions from a legacy Plan."""
    goal = frontmatter.get("goal")
    candidates: object = None
    if isinstance(goal, dict):
        candidates = goal.get("success_conditions")
    if candidates is None:
        candidates = frontmatter.get("success_conditions", frontmatter.get("success_criteria"))
    if isinstance(candidates, list):
        values = [item for item in candidates if isinstance(item, str) and item]
        if values:
            return values
    return ["A current-schema Plan is established from the archived legacy Plan."]


def _contract_tasks(frontmatter: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract task definitions without carrying legacy runtime state."""
    raw_tasks = frontmatter.get("tasks", [])
    tasks: list[dict[str, Any]] = []
    if isinstance(raw_tasks, list):
        for raw_task in raw_tasks:
            if not isinstance(raw_task, dict):
                continue
            task_id = raw_task.get("id")
            description = raw_task.get("description")
            if not isinstance(task_id, str) or not isinstance(description, str) or not description:
                continue
            task: dict[str, Any] = {
                "id": task_id,
                "description": description,
            }
            depends_on = raw_task.get("depends_on", [])
            if isinstance(depends_on, list) and all(
                isinstance(item, str) for item in depends_on
            ):
                task["depends_on"] = list(depends_on)
            tasks.append(task)
    if tasks:
        return tasks
    return [
        {
            "id": "T-001",
            "description": (
                "Review the archived legacy Plan and define the next "
                "current-schema execution slice."
            ),
        }
    ]


def build_v5_contract(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Create a fresh v5 contract from a legacy Plan summary."""
    plan_id = str(frontmatter["plan_id"])
    title = frontmatter.get("title")
    base = f".work-governance/runtime/plans/{plan_id}"
    truth_refs = frontmatter.get("truth_refs", [])
    return {
        "schema_version": CURRENT_PLAN_SCHEMA_VERSION,
        "plan_id": plan_id,
        "title": title if isinstance(title, str) and title else plan_id,
        "status": "active",
        "contract_revision": 1,
        "revision": 1,
        "goal": _goal_statement(frontmatter),
        "success_conditions": _success_conditions(frontmatter),
        "tasks": _contract_tasks(frontmatter),
        "confirmations": {"required": []},
        "truth_refs": deepcopy(truth_refs) if isinstance(truth_refs, list) else [],
        "state_ref": f"runtime:{base}/state.json",
        "event_ref": f"runtime:{base}/events.jsonl",
        "evidence_store_ref": "evidence:.work-governance/evidence",
    }


def build_v5_state(frontmatter: Mapping[str, Any], *, updated_at: str) -> dict[str, Any]:
    """Create a fresh runtime state snapshot without adapting legacy state."""
    plan_id = str(frontmatter["plan_id"])
    tasks: dict[str, dict[str, Any]] = {}
    for task in _contract_tasks(frontmatter):
        task_id = task["id"]
        tasks[task_id] = {"status": "pending"}
    return {
        "schema_version": 1,
        "kind": "work-governance-plan-state",
        "plan_id": plan_id,
        "state_sequence": 0,
        "event_sequence": 0,
        "current_task": None,
        "tasks": tasks,
        "priorities": {},
        "updated_at": updated_at,
    }
