"""Dependency-aware runtime scheduling projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

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
