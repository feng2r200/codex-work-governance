"""Dependency-aware runtime scheduling projections."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence, Set
from pathlib import Path
from typing import cast

from .model import TaskProjection

RejectSymlinkComponents = Callable[[Path, Path], None]


class SchedulerStateError(ValueError):
    """Raised when ignored runtime scheduler state is malformed."""


def _task_map(tasks: Sequence[TaskProjection]) -> dict[str, TaskProjection]:
    """Index scheduler task projections by stable task ID."""
    return {task.task_id: task for task in tasks}


def ready_task_targets(
    tasks: Sequence[TaskProjection],
    priorities: Mapping[str, int] | None = None,
    verified_states: frozenset[str] = frozenset({"verified", "skipped"}),
) -> list[str]:
    """Return pending tasks ordered by runtime priority and hard dependencies."""
    task_map = _task_map(tasks)
    ready = [
        f"task:{task.task_id}"
        for task in tasks
        if task.status == "pending"
        and all(
            dependency in task_map and task_map[dependency].status in verified_states
            for dependency in task.dependencies
        )
    ]
    priority_map = priorities or {}
    order = {target: index for index, target in enumerate(ready)}
    return sorted(
        ready,
        key=lambda target: (
            -priority_map.get(target.removeprefix("task:"), 0),
            order[target],
        ),
    )


def blocked_task_targets(tasks: Sequence[TaskProjection]) -> list[str]:
    """Return tasks explicitly blocked by execution state."""
    return [f"task:{task.task_id}" for task in tasks if task.status == "blocked"]


def scheduler_state_path(
    root: Path,
    plan_id: str,
    governance_dir_name: str,
    reject_symlink_components: RejectSymlinkComponents,
) -> Path:
    """Return the ignored runtime scheduler state path for one active Plan."""
    scheduler_dir = root / governance_dir_name / "runtime" / "scheduler"
    reject_symlink_components(root, scheduler_dir)
    return scheduler_dir / f"{plan_id}.json"


def default_scheduler_state(plan_id: str) -> dict[str, object]:
    """Return the empty schema-v4 runtime scheduler state for one Plan."""
    return {"schema_version": 1, "plan_id": plan_id, "state_sequence": 0, "priorities": {}}


def validate_scheduler_state_payload(payload: object, plan_id: str) -> dict[str, object]:
    """Validate a decoded scheduler state payload before the controller trusts it."""
    if not isinstance(payload, dict):
        raise SchedulerStateError("SCHEDULER_STATE_INVALID")
    priorities = payload.get("priorities", {})
    if (
        payload.get("schema_version") != 1
        or payload.get("plan_id") != plan_id
        or type(payload.get("state_sequence")) is not int
        or payload["state_sequence"] < 0
        or not isinstance(priorities, dict)
        or any(
            not isinstance(key, str) or type(value) is not int for key, value in priorities.items()
        )
    ):
        raise SchedulerStateError("SCHEDULER_STATE_INVALID")
    return cast(dict[str, object], payload)


def load_scheduler_state(
    root: Path,
    plan_id: str,
    governance_dir_name: str,
    reject_symlink_components: RejectSymlinkComponents,
) -> dict[str, object]:
    """Load a bounded scheduler snapshot without changing the Plan contract."""
    path = scheduler_state_path(root, plan_id, governance_dir_name, reject_symlink_components)
    if not path.exists():
        return default_scheduler_state(plan_id)
    if path.is_symlink() or not path.is_file():
        raise SchedulerStateError("SCHEDULER_STATE_INVALID")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchedulerStateError("SCHEDULER_STATE_INVALID") from exc
    return validate_scheduler_state_payload(payload, plan_id)


def dump_scheduler_state(state: Mapping[str, object]) -> str:
    """Serialize scheduler state with stable formatting for atomic persistence."""
    return json.dumps(state, indent=2, sort_keys=True) + "\n"


def current_advancement_targets(
    frontmatter: Mapping[str, object],
    verified_states: Set[str] = frozenset({"verified", "skipped"}),
) -> list[str]:
    """Return the smallest dependency-ready target set for intervention projection."""
    raw_tasks = frontmatter.get("tasks", [])
    if isinstance(raw_tasks, list):
        in_progress = [
            f"task:{task['id']}"
            for task in raw_tasks
            if isinstance(task, dict)
            and isinstance(task.get("id"), str)
            and task.get("status") == "in_progress"
        ]
        if in_progress:
            return in_progress
        all_tasks = {
            str(task["id"]): task
            for task in raw_tasks
            if isinstance(task, dict) and isinstance(task.get("id"), str)
        }
        for task in raw_tasks:
            if not isinstance(task, dict) or task.get("status") != "pending":
                continue
            dependencies = task.get("depends_on", [])
            if isinstance(dependencies, list) and all(
                dependency in all_tasks
                and all_tasks[dependency].get("status") in verified_states
                for dependency in dependencies
            ):
                return [f"task:{task['id']}"]
    delivery = frontmatter.get("delivery", {})
    if isinstance(delivery, dict) and delivery.get("status") != "complete":
        return ["delivery"]
    activation = frontmatter.get("activation", {})
    if isinstance(activation, dict) and activation.get("status") != "active":
        return ["activation"]
    return ["route"]


def next_suggestion(
    current: str | None,
    ready: Sequence[str],
    blocked: Sequence[str],
    confirmation_gates: Sequence[str],
) -> str:
    """Choose the next bounded scheduler suggestion without changing authority."""
    if current is not None:
        if current in set(blocked):
            return f"Resolve blockers for {current} before advancing."
        return f"Continue {current}"
    if ready:
        return f"Start {ready[0]}"
    if confirmation_gates:
        return "Resolve the pending confirmation gate."
    if blocked:
        return "Resolve a blocked task before advancing."
    return "Inspect the route handoff for the next governed action."
