from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

scheduler_module = importlib.import_module("workctl_modules.scheduler")
current_advancement_targets = scheduler_module.current_advancement_targets


def test_current_advancement_targets_prefers_in_progress_tasks() -> None:
    """In-progress tasks are the current target set before pending work."""
    payload = current_advancement_targets(
        {
            "tasks": [
                {"id": "T-001", "status": "in_progress"},
                {"id": "T-002", "status": "pending"},
            ],
            "delivery": {"status": "pending"},
        }
    )

    assert payload == ["task:T-001"]


def test_current_advancement_targets_selects_first_dependency_ready_task() -> None:
    """The first pending task with verified dependencies becomes the advancement target."""
    payload = current_advancement_targets(
        {
            "tasks": [
                {"id": "T-001", "status": "verified"},
                {"id": "T-002", "status": "pending", "depends_on": ["T-001"]},
                {"id": "T-003", "status": "pending", "depends_on": ["T-404"]},
            ],
        },
        {"verified"},
    )

    assert payload == ["task:T-002"]


def test_current_advancement_targets_falls_back_to_delivery_activation_route() -> None:
    """Delivery, activation, then route are fallback targets after task selection."""
    assert current_advancement_targets({"delivery": {"status": "pending"}}) == ["delivery"]
    assert current_advancement_targets(
        {
            "delivery": {"status": "complete"},
            "activation": {"status": "pending_confirmation"},
        }
    ) == ["activation"]
    assert current_advancement_targets(
        {
            "delivery": {"status": "complete"},
            "activation": {"status": "active"},
        }
    ) == ["route"]


def test_current_advancement_targets_ignores_malformed_pending_dependencies() -> None:
    """Malformed dependency declarations do not make a pending task ready."""
    payload = current_advancement_targets(
        {
            "tasks": [{"id": "T-001", "status": "pending", "depends_on": "T-000"}],
            "delivery": {"status": "in_progress"},
        }
    )

    assert payload == ["delivery"]
