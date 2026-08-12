"""Pure payload projections for compact Plan status views."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from .scheduler import next_suggestion as default_next_suggestion

StatusDocument = Mapping[str, object]
BlockedDetail = Mapping[str, object]
ReadyTaskTargets = Callable[[StatusDocument, Mapping[str, int]], Sequence[str]]
TaskBlockingDetails = Callable[[StatusDocument], Sequence[BlockedDetail]]
PendingConfirmationIds = Callable[[StatusDocument], Sequence[str]]
LegacyRefreshProjection = Callable[[StatusDocument], Mapping[str, object] | None]
NextSuggestion = Callable[[str | None, Sequence[str], Sequence[str], Sequence[str]], str]


def _task_items(frontmatter: StatusDocument) -> list[Mapping[str, object]]:
    """Return task-like mappings from a status document."""
    raw_tasks = frontmatter.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return []
    return [task for task in raw_tasks if isinstance(task, Mapping)]


def _priority_map(scheduler: Mapping[str, object] | None) -> dict[str, int]:
    """Read integer scheduler priorities without admitting non-mapping state."""
    raw_priorities = scheduler.get("priorities", {}) if isinstance(scheduler, Mapping) else {}
    if not isinstance(raw_priorities, Mapping):
        return {}
    return {
        str(task_id): priority
        for task_id, priority in raw_priorities.items()
        if isinstance(priority, int)
    }


def compact_plan_status(
    frontmatter: StatusDocument,
    *,
    scheduler: Mapping[str, object] | None = None,
    ready_task_targets: ReadyTaskTargets,
    task_blocking_details: TaskBlockingDetails,
    pending_confirmation_ids: PendingConfirmationIds,
    legacy_refresh_projection: LegacyRefreshProjection,
    next_suggestion: NextSuggestion = default_next_suggestion,
) -> dict[str, object]:
    """Build the bounded default status view without revision history."""
    current = [
        f"task:{task['id']}"
        for task in _task_items(frontmatter)
        if isinstance(task.get("id"), str) and task.get("status") == "in_progress"
    ]
    blocked_details = list(task_blocking_details(frontmatter))
    blocked = [str(item["task"]) for item in blocked_details]
    blocked_set = set(blocked)
    ready = [
        target
        for target in ready_task_targets(frontmatter, _priority_map(scheduler))
        if target not in blocked_set
    ]
    current_task = current[0] if current else (ready[0] if ready else None)
    confirmation_gates = list(pending_confirmation_ids(frontmatter))
    payload: dict[str, object] = {
        "plan_id": frontmatter.get("plan_id"),
        "goal": frontmatter.get("goal", {}),
        "current_task": current_task,
        "ready": ready,
        "blocked": blocked,
        "blocked_details": blocked_details,
        "parallel_ready": ready,
        "confirmation_gates": confirmation_gates,
        "next_suggestion": next_suggestion(
            current[0] if current else None,
            ready,
            blocked,
            confirmation_gates,
        ),
    }
    legacy_refresh = legacy_refresh_projection(frontmatter)
    if legacy_refresh is not None:
        payload["legacy_refresh"] = legacy_refresh
    return payload
