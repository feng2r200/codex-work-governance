from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

scheduler_module = importlib.import_module("workctl_modules.scheduler")
current_advancement_targets = scheduler_module.current_advancement_targets
dump_scheduler_state = scheduler_module.dump_scheduler_state
load_scheduler_state = scheduler_module.load_scheduler_state
scheduler_state_path = scheduler_module.scheduler_state_path
SchedulerStateError = scheduler_module.SchedulerStateError


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


def test_scheduler_state_path_uses_runtime_scheduler_directory(tmp_path: Path) -> None:
    """The schema-v4 scheduler state path stays under ignored runtime storage."""
    calls: list[tuple[Path, Path]] = []

    def reject_symlink_components(root: Path, path: Path) -> None:
        calls.append((root, path))

    path = scheduler_state_path(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        reject_symlink_components,
    )

    assert path == (
        tmp_path / ".work-governance" / "runtime" / "scheduler" / "PLAN-20260806-001.json"
    )
    assert calls == [(tmp_path, tmp_path / ".work-governance" / "runtime" / "scheduler")]


def test_load_scheduler_state_returns_default_when_file_is_missing(tmp_path: Path) -> None:
    """A missing scheduler state file starts from sequence zero without Plan mutation."""
    payload = load_scheduler_state(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        lambda _root, _path: None,
    )

    assert payload == {
        "schema_version": 1,
        "plan_id": "PLAN-20260806-001",
        "state_sequence": 0,
        "priorities": {},
    }


def test_load_scheduler_state_accepts_valid_state(tmp_path: Path) -> None:
    """A valid runtime scheduler payload is loaded unchanged."""
    path = scheduler_state_path(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        lambda _root, _path: None,
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plan_id": "PLAN-20260806-001",
                "state_sequence": 2,
                "priorities": {"T-002": 5},
            }
        ),
        encoding="utf-8",
    )

    assert load_scheduler_state(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        lambda _root, _path: None,
    ) == {
        "schema_version": 1,
        "plan_id": "PLAN-20260806-001",
        "state_sequence": 2,
        "priorities": {"T-002": 5},
    }


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema_version": 2, "plan_id": "PLAN-20260806-001", "state_sequence": 0},
        {
            "schema_version": 1,
            "plan_id": "PLAN-OTHER",
            "state_sequence": 0,
            "priorities": {},
        },
        {
            "schema_version": 1,
            "plan_id": "PLAN-20260806-001",
            "state_sequence": True,
            "priorities": {},
        },
        {
            "schema_version": 1,
            "plan_id": "PLAN-20260806-001",
            "state_sequence": 0,
            "priorities": {"T-001": True},
        },
    ],
)
def test_load_scheduler_state_rejects_invalid_payloads(
    tmp_path: Path,
    payload: object,
) -> None:
    """Malformed scheduler state never becomes trusted runtime input."""
    path = scheduler_state_path(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        lambda _root, _path: None,
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SchedulerStateError, match="SCHEDULER_STATE_INVALID"):
        load_scheduler_state(
            tmp_path,
            "PLAN-20260806-001",
            ".work-governance",
            lambda _root, _path: None,
        )


def test_load_scheduler_state_rejects_symlink_state_file(tmp_path: Path) -> None:
    """The scheduler state file itself cannot be a symlink."""
    path = scheduler_state_path(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        lambda _root, _path: None,
    )
    path.parent.mkdir(parents=True)
    target = path.parent / "target.json"
    target.write_text("{}", encoding="utf-8")
    path.symlink_to(target)

    with pytest.raises(SchedulerStateError, match="SCHEDULER_STATE_INVALID"):
        load_scheduler_state(
            tmp_path,
            "PLAN-20260806-001",
            ".work-governance",
            lambda _root, _path: None,
        )


def test_load_scheduler_state_rejects_non_file_state_path(tmp_path: Path) -> None:
    """The scheduler state path must be a regular file when it exists."""
    path = scheduler_state_path(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        lambda _root, _path: None,
    )
    path.mkdir(parents=True)

    with pytest.raises(SchedulerStateError, match="SCHEDULER_STATE_INVALID"):
        load_scheduler_state(
            tmp_path,
            "PLAN-20260806-001",
            ".work-governance",
            lambda _root, _path: None,
        )


def test_load_scheduler_state_rejects_invalid_json(tmp_path: Path) -> None:
    """Invalid JSON never becomes trusted scheduler state."""
    path = scheduler_state_path(
        tmp_path,
        "PLAN-20260806-001",
        ".work-governance",
        lambda _root, _path: None,
    )
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")

    with pytest.raises(SchedulerStateError, match="SCHEDULER_STATE_INVALID"):
        load_scheduler_state(
            tmp_path,
            "PLAN-20260806-001",
            ".work-governance",
            lambda _root, _path: None,
        )


def test_dump_scheduler_state_uses_stable_format() -> None:
    """Persisted scheduler state keeps stable sorted JSON formatting."""
    payload = dump_scheduler_state(
        {
            "priorities": {"T-002": 5},
            "state_sequence": 1,
            "plan_id": "PLAN-20260806-001",
            "schema_version": 1,
        }
    )

    assert payload == (
        '{\n'
        '  "plan_id": "PLAN-20260806-001",\n'
        '  "priorities": {\n'
        '    "T-002": 5\n'
        "  },\n"
        '  "schema_version": 1,\n'
        '  "state_sequence": 1\n'
        "}\n"
    )
