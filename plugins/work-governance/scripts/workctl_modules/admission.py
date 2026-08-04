"""Admission projections kept separate from execution scheduling."""

from __future__ import annotations

from collections.abc import Mapping


def is_material_contract_change(before: Mapping[str, object], after: Mapping[str, object]) -> bool:
    """Return whether a change affects durable goal or execution contract fields."""
    return any(
        before.get(field) != after.get(field)
        for field in ("goal", "scope", "contract", "obligations", "tasks", "confirmations")
    )
