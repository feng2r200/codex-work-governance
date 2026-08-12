"""Pure payload projections for compact Plan status views."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence, Set

from .scheduler import next_suggestion as default_next_suggestion

StatusDocument = Mapping[str, object]
BlockedDetail = Mapping[str, object]
ReadyTaskTargets = Callable[[StatusDocument, Mapping[str, int]], Sequence[str]]
TaskBlockingDetails = Callable[[StatusDocument], Sequence[BlockedDetail]]
PendingConfirmationIds = Callable[[StatusDocument], Sequence[str]]
LegacyRefreshProjection = Callable[[StatusDocument], Mapping[str, object] | None]
NextSuggestion = Callable[[str | None, Sequence[str], Sequence[str], Sequence[str]], str]
IncompleteEntryIds = Callable[[StatusDocument, str], Sequence[str]]
ConfirmationsById = Callable[[StatusDocument], Mapping[str, Mapping[str, object]]]

VERIFIED_TASK_STATES: Set[str] = frozenset({"verified", "skipped"})


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


def _mapping_field(frontmatter: StatusDocument, field: str) -> Mapping[str, object]:
    """Return a mapping field or an empty mapping for malformed state."""
    value = frontmatter.get(field, {})
    return value if isinstance(value, Mapping) else {}


def _confirmed(
    confirmations: Mapping[str, Mapping[str, object]],
    confirmation_id: str | None,
) -> bool:
    """Check whether a confirmation id has an accepted decision reference."""
    if confirmation_id is None:
        return False
    confirmation = confirmations.get(confirmation_id)
    return bool(
        confirmation
        and confirmation.get("status") == "accepted"
        and confirmation.get("ref")
    )


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


def queue_projection(compact_status: Mapping[str, object], action: str) -> object:
    """Project one public queue command from the compact status payload."""
    if action == "ready":
        return compact_status["ready"]
    if action == "blocked":
        return compact_status["blocked"]
    return {
        "current_task": compact_status["current_task"],
        "parallel_ready": compact_status["parallel_ready"],
        "blocked_details": compact_status["blocked_details"],
        "next_suggestion": compact_status["next_suggestion"],
    }


def completion_claims(
    frontmatter: StatusDocument,
    readiness: Mapping[str, object],
    *,
    incomplete_entry_ids: IncompleteEntryIds,
    confirmations_by_id: ConfirmationsById,
    verified_task_states: Set[str] = VERIFIED_TASK_STATES,
) -> dict[str, object]:
    """Describe which completion claims current evidence permits."""
    delivery = _mapping_field(frontmatter, "delivery")
    route = _mapping_field(frontmatter, "route")
    confirmation_lookup = confirmations_by_id(frontmatter)
    delivery_declared_complete = delivery.get("status") == "complete"
    obligations_complete = not incomplete_entry_ids(frontmatter, "obligations")
    validations_complete = not incomplete_entry_ids(frontmatter, "validations")
    tasks = frontmatter.get("tasks", [])
    local_tasks_complete = isinstance(tasks, list) and all(
        isinstance(task, Mapping)
        and (
            task.get("completion_scope", "local") == "route"
            or task.get("status") in verified_task_states
        )
        for task in tasks
    )
    artifacts = frontmatter.get("artifacts", [])
    artifacts_final = isinstance(artifacts, list) and all(
        isinstance(artifact, Mapping) and artifact.get("status") == "final"
        for artifact in artifacts
    )
    local_delivery_complete = (
        delivery_declared_complete
        and obligations_complete
        and validations_complete
        and local_tasks_complete
        and artifacts_final
    )
    route_complete = bool(readiness.get("ready"))
    confirmation_gate = route.get("confirmation_gate")
    slice_action_authorized = confirmation_gate in {None, "", "none"}
    if isinstance(confirmation_gate, str) and confirmation_gate.startswith("C-"):
        slice_action_authorized = _confirmed(confirmation_lookup, confirmation_gate)
    activation = _mapping_field(frontmatter, "activation")
    activation_confirmation = activation.get("confirmation_id")
    activation_authorized = _confirmed(
        confirmation_lookup,
        activation_confirmation if isinstance(activation_confirmation, str) else None,
    )
    if route_complete:
        level = "route_complete"
    elif local_delivery_complete:
        level = "local_delivery_complete"
    else:
        level = "in_progress"
    return {
        "level": level,
        "slice_status": route.get("slice_status"),
        "delivery_declared_complete": delivery_declared_complete,
        "local_delivery_complete": local_delivery_complete,
        "route_complete": route_complete,
        "no_required_next_step_allowed": route_complete,
        "slice_next_action_authorized": slice_action_authorized,
        "slice_confirmation_id": confirmation_gate,
        "activation_authorized": activation_authorized,
        "activation_confirmation_id": activation_confirmation,
    }
