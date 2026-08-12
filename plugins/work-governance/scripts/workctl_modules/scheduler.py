"""Dependency-aware runtime scheduling projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set

from .model import TaskProjection


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
