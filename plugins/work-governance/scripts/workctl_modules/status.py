"""Pure payload projections for compact Plan status views."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence, Set

from .migration import REFRESH_NEXT_MODEL_ACTION, REFRESH_NOT_MIGRATED
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
ArchiveStatusProjection = Callable[[str, object], Mapping[str, object]]
MigrationStatusProjection = Callable[[StatusDocument], Mapping[str, object]]
ContractStateProjection = Callable[[StatusDocument], str]
IndependentReviewBlockers = Callable[[str], Sequence[str]]

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


def confirmation_map(frontmatter: StatusDocument) -> dict[str, Mapping[str, object]]:
    """Return required and accepted confirmations keyed by stable ID."""
    result: dict[str, Mapping[str, object]] = {}
    raw = frontmatter.get("confirmations", {})
    for group in ("required", "accepted"):
        for item in raw.get(group, []) if isinstance(raw, Mapping) else []:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                result[str(item["id"])] = item
    return result


def blocking_artifacts(
    frontmatter: StatusDocument,
    blocking_artifact_states: Set[str],
) -> dict[str, str]:
    """Return blocking artifact IDs and states from a Plan-like status document."""
    result: dict[str, str] = {}
    raw_artifacts = frontmatter.get("artifacts", [])
    for artifact in raw_artifacts if isinstance(raw_artifacts, list) else []:
        if isinstance(artifact, Mapping) and artifact.get("status") in blocking_artifact_states:
            artifact_id = artifact.get("id")
            status = artifact.get("status")
            if isinstance(artifact_id, str) and isinstance(status, str):
                result[artifact_id] = status
    return result


def downstream_task_targets(
    task_id: str,
    task_map: Mapping[str, Mapping[str, object]],
    verified_task_states: Set[str] = VERIFIED_TASK_STATES,
) -> list[str]:
    """Return non-terminal tasks that transitively depend on one blocked task."""
    downstream: list[str] = []
    visited: set[str] = set()
    frontier = [task_id]
    while frontier:
        blocked_id = frontier.pop(0)
        for candidate_id, candidate in task_map.items():
            if candidate_id in visited:
                continue
            dependencies = candidate.get("depends_on", [])
            if not isinstance(dependencies, list) or blocked_id not in dependencies:
                continue
            visited.add(candidate_id)
            if candidate.get("status") not in verified_task_states:
                downstream.append(f"task:{candidate_id}")
            frontier.append(candidate_id)
    return downstream


def task_artifact_blockers(
    frontmatter: StatusDocument,
    task: Mapping[str, object],
    blocking_artifact_states: Set[str],
) -> list[dict[str, str]]:
    """Project artifact blockers with the same recovery exception as task advancement."""
    blocked = blocking_artifacts(frontmatter, blocking_artifact_states)
    if not blocked:
        return []
    non_suspect = {
        artifact_id: status for artifact_id, status in blocked.items() if status != "suspect"
    }
    if non_suspect:
        return [
            {
                "kind": "artifact",
                "artifact": artifact_id,
                "state": non_suspect[artifact_id],
            }
            for artifact_id in sorted(non_suspect)
        ]
    resolves = task.get("resolves_artifacts", [])
    if (
        isinstance(resolves, list)
        and resolves
        and all(isinstance(artifact_id, str) and artifact_id in blocked for artifact_id in resolves)
    ):
        return []
    return [
        {
            "kind": "artifact",
            "artifact": artifact_id,
            "state": blocked[artifact_id],
        }
        for artifact_id in sorted(blocked)
    ]


def task_confirmation_blocker(
    frontmatter: StatusDocument,
    task: Mapping[str, object],
) -> dict[str, str] | None:
    """Return the pending task gate that blocks a normal start/verify path."""
    confirmation_id = task.get("requires_confirmation")
    if not isinstance(confirmation_id, str):
        return None
    item = confirmation_map(frontmatter).get(confirmation_id)
    if item and item.get("status") == "accepted" and item.get("ref"):
        return None
    return {"kind": "confirmation", "confirmation_id": confirmation_id}


def task_blocking_details(
    frontmatter: StatusDocument,
    *,
    independent_review_blockers: IndependentReviewBlockers,
    blocking_artifact_states: Set[str],
    verified_task_states: Set[str] = VERIFIED_TASK_STATES,
) -> list[dict[str, object]]:
    """Explain every task that cannot currently advance and what it blocks downstream."""
    raw_tasks = frontmatter.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return []
    task_map: dict[str, Mapping[str, object]] = {
        str(task["id"]): task
        for task in raw_tasks
        if isinstance(task, Mapping) and isinstance(task.get("id"), str)
    }
    details: list[dict[str, object]] = []
    for task_id, task in task_map.items():
        status = str(task.get("status", "pending"))
        if status in verified_task_states:
            continue
        reasons: list[dict[str, object]] = []
        if status == "blocked":
            note = task.get("blocker", task.get("note", "task status is blocked"))
            reasons.append({"kind": "explicit-block", "detail": str(note)})
        dependencies = task.get("depends_on", [])
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if not isinstance(dependency, str):
                    reasons.append({"kind": "dependency-invalid"})
                    continue
                dependency_task = task_map.get(dependency)
                if dependency_task is None:
                    reasons.append({"kind": "dependency-missing", "dependency": dependency})
                elif dependency_task.get("status") not in verified_task_states:
                    reasons.append(
                        {
                            "kind": "dependency-not-verified",
                            "dependency": dependency,
                            "state": str(dependency_task.get("status", "pending")),
                        }
                    )
        elif "depends_on" in task:
            reasons.append({"kind": "dependency-invalid"})
        if status in {"pending", "in_progress"}:
            for reason in task_artifact_blockers(frontmatter, task, blocking_artifact_states):
                reasons.append(dict(reason))
            review_modes = independent_review_blockers(f"task:{task_id}")
            if review_modes:
                reasons.append(
                    {
                        "kind": "independent-review",
                        "modes": sorted(review_modes),
                    }
                )
            confirmation_blocker = task_confirmation_blocker(frontmatter, task)
            if confirmation_blocker is not None:
                reasons.append(dict(confirmation_blocker))
        if reasons:
            details.append(
                {
                    "task": f"task:{task_id}",
                    "status": status,
                    "reasons": reasons,
                    "blocks_downstream": downstream_task_targets(
                        task_id,
                        task_map,
                        verified_task_states,
                    ),
                }
            )
    return details


def pending_confirmation_ids(frontmatter: StatusDocument) -> list[str]:
    """Return pending confirmation IDs in stable Plan order."""
    raw = frontmatter.get("confirmations", {})
    required = raw.get("required", []) if isinstance(raw, Mapping) else []
    return [
        str(item["id"])
        for item in required
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and item.get("status") == "pending"
    ]


def legacy_refresh_projection(
    frontmatter: StatusDocument,
    *,
    archive_status_projection: ArchiveStatusProjection,
) -> dict[str, object] | None:
    """Project archive-backed refresh guidance for a rebuilt current-schema Plan."""
    archive = frontmatter.get("legacy_archive")
    if not isinstance(archive, Mapping):
        return None
    archive_path = archive.get("path")
    not_migrated = archive.get("not_migrated", REFRESH_NOT_MIGRATED)
    projection: dict[str, object] = {
        "from_schema_version": archive.get("from_schema_version"),
        "archive_path": archive_path,
        "archive_sha256": archive.get("sha256"),
        "migration_mode": archive.get("mode", "archive_legacy_and_rebuild_current_plan"),
        "runtime_state": archive.get("runtime_state", "fresh"),
        "state_reset": True,
        "legacy_state_migrated": False,
        "not_migrated": list(not_migrated)
        if isinstance(not_migrated, list)
        else list(REFRESH_NOT_MIGRATED),
        "next_model_action": archive.get("next_model_action", REFRESH_NEXT_MODEL_ACTION),
        "archive_status": "not_checked",
    }
    if not isinstance(archive_path, str) or not archive_path:
        projection["archive_status"] = "missing_path"
        return projection
    projection.update(archive_status_projection(archive_path, archive.get("sha256")))
    return projection


def current_schema_refresh_status(
    frontmatter: StatusDocument,
    *,
    authority_state: str,
    blocking_reasons: Sequence[str],
    current_schema_version: int,
    migration_projection: MigrationStatusProjection,
    contract_state: ContractStateProjection,
    full: bool,
    authority_candidates: Sequence[Mapping[str, object]] = (),
    allowed_commands: Sequence[str] = (),
) -> dict[str, object]:
    """Build a status view for an outdated active Plan without scheduling tasks."""
    projection = dict(migration_projection(frontmatter))
    contract = frontmatter.get("contract")
    expected_revision = (
        contract.get("revision")
        if isinstance(contract, Mapping)
        else frontmatter.get("revision")
    )
    payload: dict[str, object] = {
        "authority_state": authority_state,
        "blocking_reasons": list(blocking_reasons),
        "contract_state": contract_state(frontmatter),
        "current_schema_version": current_schema_version,
        "expected_contract_revision": expected_revision,
        "plan_id": frontmatter.get("plan_id"),
        "schema_version": frontmatter.get("schema_version"),
        "status": frontmatter.get("status"),
        "next_suggestion": (
            "Run migrate inspect and migrate apply --expected-contract-revision "
            f"{expected_revision}."
            if isinstance(expected_revision, int)
            else "Run migrate inspect before rebuilding the active Plan."
        ),
    }
    payload.update(projection)
    if full:
        payload["authority_candidates"] = list(authority_candidates)
        payload["allowed_commands"] = list(allowed_commands)
        payload["goal"] = frontmatter.get("goal", {})
        payload["tasks"] = frontmatter.get("tasks", [])
        payload["confirmations"] = frontmatter.get("confirmations", {})
    return payload


def user_intervention_projection(
    frontmatter: StatusDocument,
    *,
    current_targets: Sequence[str],
) -> dict[str, object]:
    """Describe only user-owned input that blocks the current advancement target."""
    target_list = list(current_targets)
    target_set = set(target_list)
    raw_unknowns = frontmatter.get("unknowns", [])
    if isinstance(raw_unknowns, list):
        for unknown in raw_unknowns:
            if not isinstance(unknown, Mapping):
                continue
            blocks = unknown.get("blocks")
            if (
                unknown.get("status") == "open"
                and unknown.get("owner") == "user"
                and unknown.get("impact") == "blocking"
                and isinstance(blocks, list)
                and target_set.intersection(blocks)
            ):
                return {
                    "state": "REQUIREMENT_INPUT_REQUIRED",
                    "current_targets": target_list,
                    "blocks": blocks,
                    "unknown_id": unknown.get("id"),
                    "confirmation_id": None,
                    "basis_ref": None,
                }
    raw_confirmations = frontmatter.get("confirmations", {})
    required = (
        raw_confirmations.get("required", [])
        if isinstance(raw_confirmations, Mapping)
        else []
    )
    for item in required if isinstance(required, list) else []:
        if not isinstance(item, Mapping) or item.get("status") != "pending":
            continue
        intervention = item.get("intervention")
        if intervention is None:
            return {
                "state": "PLAN_DECISION_REQUIRED",
                "current_targets": target_list,
                "blocks": target_list,
                "unknown_id": None,
                "confirmation_id": item.get("id"),
                "basis_ref": None,
            }
        blocks = intervention.get("blocks", []) if isinstance(intervention, Mapping) else []
        if not isinstance(blocks, list) or not target_set.intersection(blocks):
            continue
        kind = intervention.get("kind") if isinstance(intervention, Mapping) else "plan_contract"
        state = {
            "plan_contract": "PLAN_DECISION_REQUIRED",
            "external_authority": "AUTHORITY_REQUIRED",
            "deviation_recovery": "DEVIATION_DECISION_REQUIRED",
        }.get(str(kind), "PLAN_DECISION_REQUIRED")
        return {
            "state": state,
            "current_targets": target_list,
            "blocks": blocks,
            "unknown_id": None,
            "confirmation_id": item.get("id"),
            "basis_ref": intervention.get("basis_ref")
            if isinstance(intervention, Mapping)
            else None,
        }
    return {
        "state": "NOT_REQUIRED",
        "current_targets": target_list,
        "blocks": [],
        "unknown_id": None,
        "confirmation_id": None,
        "basis_ref": None,
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
