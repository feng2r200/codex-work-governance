"""Schema migration boundary helpers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .model import V5ContractProjection


def migration_projection(frontmatter: Mapping[str, object]) -> dict[str, object]:
    """Describe one Plan's read-only migration source and target versions."""
    version = frontmatter.get("schema_version")
    tasks_value = frontmatter.get("tasks", [])
    tasks = tasks_value if isinstance(tasks_value, list) else []
    unknowns_value = frontmatter.get("unknowns", [])
    unknowns = unknowns_value if isinstance(unknowns_value, list) else []
    confirmations = frontmatter.get("confirmations", {})
    confirmation_items: list[object] = []
    if isinstance(confirmations, dict):
        required = confirmations.get("required", [])
        if isinstance(required, list):
            confirmation_items = required
    truth_refs_value = frontmatter.get("truth_refs", [])
    truth_refs = truth_refs_value if isinstance(truth_refs_value, list) else []
    return {
        "from_schema_version": version,
        "to_schema_version": 5,
        "requires_migration": version != 5,
        "write": False,
        "contract_fields": [
            "goal",
            "success_criteria",
            "scope",
            "truth_refs",
            "tasks",
            "milestones",
            "confirmations",
        ],
        "state_fields": ["state_sequence", "current_task", "tasks", "priorities"],
        "event_fields": ["event_sequence", "event", "subject", "payload"],
        "task_mapping": [
            item.get("id")
            for item in tasks
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ],
        "unknown_mapping": [
            item.get("id")
            for item in unknowns
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ],
        "confirmation_mapping": [
            item.get("id")
            for item in confirmation_items
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ],
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


def build_v5_contract(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Create a v5 contract mapping while preserving v4 source semantics."""
    contract = deepcopy(dict(frontmatter))
    contract["schema_version"] = 5
    nested = contract.get("contract")
    nested_revision = nested.get("revision") if isinstance(nested, dict) else None
    revision_value = contract.get(
        "contract_revision",
        nested_revision or contract.get("revision", 1),
    )
    revision = revision_value if isinstance(revision_value, int) else 1
    contract["contract_revision"] = revision
    contract["revision"] = revision
    if isinstance(nested, dict):
        nested["revision"] = revision
    contract.pop("revision_history", None)
    contract.setdefault("truth_refs", [])
    plan_id = str(contract["plan_id"])
    base = f".work-governance/runtime/plans/{plan_id}"
    contract["state_ref"] = f"runtime:{base}/state.json"
    contract["event_ref"] = f"runtime:{base}/events.jsonl"
    contract["evidence_store_ref"] = f"evidence:.work-governance/_Plan/.evidence/{plan_id}"
    goal = contract.get("goal")
    if "success_criteria" not in contract:
        contract["success_criteria"] = deepcopy(
            goal.get("success_conditions", []) if isinstance(goal, dict) else []
        )
    contract.setdefault("milestones", [])
    raw_tasks = contract.get("tasks", [])
    for task in raw_tasks if isinstance(raw_tasks, list) else []:
        if isinstance(task, dict):
            task["status"] = "pending"
            task.pop("note", None)
            task.pop("evidence_ref", None)
            task.pop("evidence_sha256", None)
            task.pop("verified_at", None)
            task.setdefault("depends_on", [])
    return contract


def build_v5_state(frontmatter: Mapping[str, Any], *, updated_at: str) -> dict[str, Any]:
    """Create the independent runtime state snapshot for one v4 source."""
    plan_id = str(frontmatter["plan_id"])
    tasks: dict[str, dict[str, Any]] = {}
    raw_tasks = frontmatter.get("tasks", [])
    for task in raw_tasks if isinstance(raw_tasks, list) else []:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        entry: dict[str, Any] = {"status": task.get("status", "pending")}
        for key in ("note", "evidence_ref", "evidence_sha256", "verified_at"):
            if key in task:
                entry[key] = task[key]
        tasks[task["id"]] = entry
    return {
        "schema_version": 1,
        "kind": "work-governance-plan-state",
        "plan_id": plan_id,
        "state_sequence": 0,
        "event_sequence": 0,
        "current_task": next(
            (
                f"task:{task_id}"
                for task_id, value in tasks.items()
                if value.get("status") == "in_progress"
            ),
            None,
        ),
        "tasks": tasks,
        "priorities": {},
        "updated_at": updated_at,
    }
