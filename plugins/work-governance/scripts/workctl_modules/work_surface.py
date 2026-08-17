"""Project work-surface aggregation for compact model-facing status."""

from __future__ import annotations

from collections.abc import Mapping


def _string(value: object, default: str) -> str:
    """Return a string field or a fallback."""
    return value if isinstance(value, str) else default


def _string_or_none(value: object) -> str | None:
    """Return a nullable string field."""
    return value if isinstance(value, str) else None


def _sequence(value: object) -> list[object]:
    """Return a shallow list copy for JSON-facing payloads."""
    return list(value) if isinstance(value, list) else []


def activation_state(
    *,
    registered_workctl: Mapping[str, object],
    source_workctl_path: str | None,
    plugin_version: str | None,
    release_target_version: str | None,
) -> tuple[str, bool]:
    """Return whether the inspected source is the registered live workctl target."""
    registered_target = _string_or_none(registered_workctl.get("target_path"))
    if registered_target is None:
        registered_target = _string_or_none(registered_workctl.get("path"))
    if registered_target is not None and source_workctl_path == registered_target:
        return "active", False
    if release_target_version is None:
        return "unknown", False
    if plugin_version is not None and plugin_version.startswith(f"{release_target_version}+"):
        return "not_activated", True
    return "target_version_mismatch", True


def classify_work_state(
    *,
    layout_state: str,
    authority_state: str,
    contract_state: str,
) -> str:
    """Classify the current project work surface into one model-facing state."""
    if layout_state != "LAYOUT_READY":
        return "ENVIRONMENT_BLOCKED"
    if authority_state == "UNMANAGED_EMPTY":
        return "NO_ACTIVE_PLAN"
    if authority_state == "GOVERNED_ACTIVE":
        return "PLAN_ACTIVE"
    if (
        authority_state == "PLAN_SCHEMA_REFRESH_REQUIRED"
        or contract_state == "PLAN_SCHEMA_REFRESH_REQUIRED"
    ):
        return "PLAN_SCHEMA_REFRESH_REQUIRED"
    if authority_state == "MIGRATION_RECOVERY_REQUIRED":
        return "MIGRATION_RECOVERY_REQUIRED"
    return "AUTHORITY_BLOCKED"


def build_work_status(
    *,
    layout: Mapping[str, object],
    intake: Mapping[str, object],
    plan: Mapping[str, object] | None,
    registered_workctl: Mapping[str, object],
    plugin_version: str | None,
    source_workctl_path: str | None,
    release_target_version: str | None,
    full: bool,
) -> dict[str, object]:
    """Build a compact, read-only work status from existing controller projections."""
    layout_state = _string(layout.get("layout_state"), "UNKNOWN")
    authority_state = _string(intake.get("authority_state"), "UNKNOWN")
    contract_state = _string(intake.get("contract_state"), "UNKNOWN")
    work_state = classify_work_state(
        layout_state=layout_state,
        authority_state=authority_state,
        contract_state=contract_state,
    )
    plan_id = _string_or_none(intake.get("plan_id"))
    current_task = plan.get("current_task") if plan is not None else None
    next_suggestion = (
        plan.get("next_suggestion")
        if plan is not None
        else "Admit a Plan only when durable execution state is needed."
    )
    live_activation_state, activation_requires_confirmation = activation_state(
        registered_workctl=registered_workctl,
        source_workctl_path=source_workctl_path,
        plugin_version=plugin_version,
        release_target_version=release_target_version,
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-work-status",
        "status": "WORK_STATUS_READY",
        "work_state": work_state,
        "layout_state": layout_state,
        "authority_state": authority_state,
        "contract_state": contract_state,
        "intake_state": _string(intake.get("intake_state"), "UNKNOWN"),
        "plan_id": plan_id,
        "current_task": current_task,
        "ready": _sequence(plan.get("ready") if plan is not None else []),
        "blocked": _sequence(plan.get("blocked") if plan is not None else []),
        "confirmation_gates": _sequence(
            plan.get("confirmation_gates") if plan is not None else []
        ),
        "next_suggestion": next_suggestion,
        "registered_workctl": dict(registered_workctl),
        "live_plugin_boundary": {
            "current_source_version": plugin_version,
            "source_workctl_path": source_workctl_path,
            "release_target_version": release_target_version,
            "activation_state": live_activation_state,
            "activation_requires_user_confirmation": activation_requires_confirmation,
        },
    }
    if full:
        payload["layout"] = dict(layout)
        payload["intake"] = dict(intake)
        payload["plan"] = dict(plan) if plan is not None else None
    return payload
