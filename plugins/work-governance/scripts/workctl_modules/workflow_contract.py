"""High-level workflow contract parsing helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import cast

import workctl_modules.yaml_compat as yaml


class WorkflowContractError(ValueError):
    """Raised when a high-level workflow contract is malformed."""


def parse_workflow_mapping(content: bytes, *, error_prefix: str) -> dict[object, object]:
    """Parse a bounded JSON/YAML workflow mapping."""
    try:
        payload: object = json.loads(content)
    except json.JSONDecodeError:
        try:
            payload = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise WorkflowContractError(f"{error_prefix}_INVALID") from exc
    if not isinstance(payload, dict):
        raise WorkflowContractError(f"{error_prefix}_MUST_BE_MAPPING")
    return payload


def non_empty_string(value: object, *, field: str) -> str:
    """Return a non-empty string field or raise a workflow contract error."""
    if not isinstance(value, str) or not value.strip():
        raise WorkflowContractError(f"{field}_REQUIRED")
    return value.strip()


def workflow_string_list(value: object, *, field: str) -> list[str]:
    """Validate one non-empty list of strings for high-level contracts."""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise WorkflowContractError(f"{field}_REQUIRES_NON_EMPTY_STRING_LIST")
    return [str(item).strip() for item in value]


def normalize_goal_tasks(
    raw_tasks: object,
    *,
    task_id_pattern: re.Pattern[str],
) -> list[dict[str, object]]:
    """Normalize a minimal task list into schema-v5 contract task mappings."""
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise WorkflowContractError("GOAL_TASKS_REQUIRED")
    tasks: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw_task in enumerate(raw_tasks, start=1):
        if isinstance(raw_task, str):
            task: dict[str, object] = {
                "id": f"T-{index:03d}",
                "description": raw_task.strip(),
            }
        elif isinstance(raw_task, dict):
            raw_mapping = cast(Mapping[object, object], raw_task)
            task_id = raw_mapping.get("id", f"T-{index:03d}")
            task = {
                "id": task_id,
                "description": raw_mapping.get("description"),
            }
            for optional_field in (
                "depends_on",
                "requires_confirmation",
                "completion_scope",
                "resolves_artifacts",
            ):
                if optional_field in raw_mapping:
                    task[optional_field] = deepcopy(raw_mapping[optional_field])
        else:
            raise WorkflowContractError("GOAL_TASKS_ENTRIES_INVALID")
        task_id_value = task.get("id")
        if not isinstance(task_id_value, str) or task_id_pattern.fullmatch(task_id_value) is None:
            raise WorkflowContractError("GOAL_TASK_ID_INVALID")
        if task_id_value in seen:
            raise WorkflowContractError(f"DUPLICATE_TASK_ID: {task_id_value}")
        seen.add(task_id_value)
        task["id"] = task_id_value
        task["description"] = non_empty_string(task.get("description"), field="TASK_DESCRIPTION")
        dependencies_value = task.get("depends_on", [])
        if not isinstance(dependencies_value, list) or not all(
            isinstance(item, str) for item in dependencies_value
        ):
            raise WorkflowContractError(f"{task_id_value}_DEPENDS_ON_INVALID")
        task["depends_on"] = [str(item) for item in dependencies_value]
        tasks.append(task)
    known = {str(task["id"]) for task in tasks}
    for task in tasks:
        task_id = str(task["id"])
        dependencies = cast(list[str], task.get("depends_on", []))
        for dependency in dependencies:
            if dependency not in known:
                raise WorkflowContractError(f"{task_id}_UNKNOWN_DEPENDENCY: {dependency}")
    return tasks


def normalize_goal_confirmations(
    raw_confirmations: object,
) -> dict[str, list[dict[str, object]]]:
    """Normalize the optional minimal schema-v5 confirmation mapping."""
    if raw_confirmations is None:
        return {"required": [], "accepted": []}
    if not isinstance(raw_confirmations, dict):
        raise WorkflowContractError("GOAL_CONFIRMATIONS_MUST_BE_MAPPING")
    raw_mapping = cast(Mapping[object, object], raw_confirmations)
    result: dict[str, list[dict[str, object]]] = {"required": [], "accepted": []}
    seen: set[str] = set()
    for group in ("required", "accepted"):
        values = raw_mapping.get(group, [])
        if not isinstance(values, list):
            raise WorkflowContractError(f"GOAL_CONFIRMATIONS_{group.upper()}_INVALID")
        for item in values:
            if not isinstance(item, dict):
                raise WorkflowContractError(f"GOAL_CONFIRMATIONS_{group.upper()}_ENTRIES_INVALID")
            confirmation = deepcopy(cast(dict[str, object], item))
            confirmation_id = confirmation.get("id")
            if not isinstance(confirmation_id, str) or not confirmation_id.startswith("C-"):
                raise WorkflowContractError("GOAL_CONFIRMATION_ID_INVALID")
            if confirmation_id in seen:
                raise WorkflowContractError(f"DUPLICATE_CONFIRMATION_ID: {confirmation_id}")
            seen.add(confirmation_id)
            confirmation["description"] = non_empty_string(
                confirmation.get("description"),
                field="CONFIRMATION_DESCRIPTION",
            )
            confirmation.setdefault("status", "pending" if group == "required" else "accepted")
            result[group].append(confirmation)
    return result
