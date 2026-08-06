"""Read-only action risk inspection helpers."""

from __future__ import annotations

from collections.abc import Collection

MODEL_CONFIRMATION_CONSIDERATIONS = [
    "current user authorization",
    "project rules",
    "impact on remote, production, data, secrets, destructive state, or rollback",
    "reversibility and blast radius",
    "fresh evidence already available",
]


def risk_factors_for_action(
    action_kind: str,
    high_impact_action_kinds: Collection[str],
) -> list[str]:
    """Return factual risk categories for one proposed action kind."""
    factors: list[str] = []
    if action_kind in high_impact_action_kinds:
        factors.append("high_impact_action")
    if action_kind in {"remote_write", "remote_read"}:
        factors.append("remote_state")
    if action_kind == "production_change":
        factors.append("production_surface")
    if action_kind == "destructive_operation":
        factors.append("destructive_or_hard_to_reverse")
    if action_kind == "secret_handling":
        factors.append("secret_or_credential_exposure")
    if action_kind in {"data_read", "data_write"}:
        factors.append("data_boundary")
    if action_kind in {"local_edit", "local_commit"}:
        factors.append("local_repository_state")
    return factors


def action_reversibility(action_kind: str) -> str:
    """Classify reversibility facts without making a confirmation decision."""
    if action_kind in {"local_edit", "data_read", "remote_read"}:
        return "usually_reversible_or_read_only"
    if action_kind == "local_commit":
        return "locally_reversible_with_git_history"
    if action_kind in {"remote_write", "production_change", "destructive_operation"}:
        return "may_be_irreversible_or_externally_visible"
    if action_kind in {"secret_handling", "data_write", "substantive_rollback"}:
        return "context_dependent_high_impact"
    return "unknown"


def risk_inspection_payload(
    *,
    action_kind: str,
    target_ref: str,
    high_impact_action_kinds: Collection[str],
    action_sha256: str | None = None,
    action_size: int | None = None,
) -> dict[str, object]:
    """Build the read-only risk inspection response payload."""
    payload: dict[str, object] = {
        "decision_owner": "model",
        "controller_decision": "facts_only",
        "requires_confirmation_by_controller": False,
        "action_kind": action_kind,
        "target_ref": target_ref,
        "risk_factors": risk_factors_for_action(action_kind, high_impact_action_kinds),
        "reversibility": action_reversibility(action_kind),
        "model_confirmation_considerations": MODEL_CONFIRMATION_CONSIDERATIONS,
    }
    if action_sha256 is not None:
        payload["action_sha256"] = action_sha256
    if action_size is not None:
        payload["action_size"] = action_size
    return payload
