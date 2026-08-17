from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

from test_schema_v5 import STRICT_CONTROLLER_ENV, init_minimal_v5_goal, run_without_receipt
from test_workctl import file_tree_snapshot, run_workctl

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

work_surface_module: Any = importlib.import_module("workctl_modules.work_surface")
classify_work_state = work_surface_module.classify_work_state
build_work_status = work_surface_module.build_work_status


def test_work_surface_classifies_model_facing_states() -> None:
    """The compact work surface keeps authority and environment states distinct."""
    assert (
        classify_work_state(
            layout_state="LAYOUT_BLOCKED",
            authority_state="UNMANAGED_EMPTY",
            contract_state="NO_ACTIVE_PLAN",
        )
        == "ENVIRONMENT_BLOCKED"
    )
    assert (
        classify_work_state(
            layout_state="LAYOUT_READY",
            authority_state="UNMANAGED_EMPTY",
            contract_state="NO_ACTIVE_PLAN",
        )
        == "NO_ACTIVE_PLAN"
    )
    assert (
        classify_work_state(
            layout_state="LAYOUT_READY",
            authority_state="GOVERNED_ACTIVE",
            contract_state="PLAN_CONTRACT_READY",
        )
        == "PLAN_ACTIVE"
    )
    assert (
        classify_work_state(
            layout_state="LAYOUT_READY",
            authority_state="PLAN_SCHEMA_REFRESH_REQUIRED",
            contract_state="PLAN_SCHEMA_REFRESH_REQUIRED",
        )
        == "PLAN_SCHEMA_REFRESH_REQUIRED"
    )


def test_build_work_status_exposes_non_activation_boundary() -> None:
    """The aggregate payload states that a candidate version has not been activated."""
    payload = build_work_status(
        layout={"layout_state": "LAYOUT_READY"},
        intake={
            "intake_state": "INTAKE_READY",
            "authority_state": "UNMANAGED_EMPTY",
            "contract_state": "NO_ACTIVE_PLAN",
            "plan_id": None,
        },
        plan=None,
        registered_workctl={"state": "ok", "path": "/tmp/workctl"},
        plugin_version="1.4.0+codex.20260817000000",
        source_workctl_path="/tmp/candidate/workctl",
        release_target_version="1.4.0",
        full=False,
    )

    boundary = cast(dict[str, object], payload["live_plugin_boundary"])
    assert payload["work_state"] == "NO_ACTIVE_PLAN"
    assert payload["next_suggestion"] == "Admit a Plan only when durable execution state is needed."
    assert boundary == {
        "current_source_version": "1.4.0+codex.20260817000000",
        "source_workctl_path": "/tmp/candidate/workctl",
        "release_target_version": "1.4.0",
        "activation_state": "not_activated",
        "activation_requires_user_confirmation": True,
    }


def test_build_work_status_marks_registered_source_active() -> None:
    """The status boundary stops claiming non-activation after the source is registered."""
    payload = build_work_status(
        layout={"layout_state": "LAYOUT_READY"},
        intake={
            "intake_state": "INTAKE_READY",
            "authority_state": "UNMANAGED_EMPTY",
            "contract_state": "NO_ACTIVE_PLAN",
            "plan_id": None,
        },
        plan=None,
        registered_workctl={
            "state": "ok",
            "path": "/Users/ld/.local/bin/workctl",
            "target_path": "/tmp/candidate/workctl",
        },
        plugin_version="1.4.0+codex.20260817000000",
        source_workctl_path="/tmp/candidate/workctl",
        release_target_version="1.4.0",
        full=False,
    )

    boundary = cast(dict[str, object], payload["live_plugin_boundary"])
    assert boundary["activation_state"] == "active"
    assert boundary["activation_requires_user_confirmation"] is False


def test_work_status_command_is_read_only_without_active_plan(tmp_path: Path) -> None:
    """A clean governed layout can be inspected without creating a Plan."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    before = file_tree_snapshot(tmp_path / ".work-governance")

    result = run_without_receipt(
        tmp_path,
        "work",
        "status",
        "--release-target-version",
        "1.4.0",
    )

    payload = cast(dict[str, object], json.loads(result.stdout))
    boundary = cast(dict[str, object], payload["live_plugin_boundary"])
    assert result.returncode == 0
    assert payload["status"] == "WORK_STATUS_READY"
    assert payload["work_state"] == "NO_ACTIVE_PLAN"
    assert payload["authority_state"] == "UNMANAGED_EMPTY"
    assert boundary["release_target_version"] == "1.4.0"
    assert boundary["activation_state"] == "not_activated"
    assert "registered_workctl" in payload
    assert not (tmp_path / ".work-governance" / "_Plan").exists()
    assert file_tree_snapshot(tmp_path / ".work-governance") == before


def test_work_status_command_projects_active_v5_plan(tmp_path: Path) -> None:
    """An active v5 Plan appears as a compact queue surface."""
    init_minimal_v5_goal(tmp_path, "PLAN-20260817-401")
    before = file_tree_snapshot(tmp_path / ".work-governance")

    result = run_without_receipt(
        tmp_path,
        "work",
        "status",
        "--release-target-version",
        "1.4.0",
    )

    payload = cast(dict[str, object], json.loads(result.stdout))
    assert result.returncode == 0
    assert payload["work_state"] == "PLAN_ACTIVE"
    assert payload["plan_id"] == "PLAN-20260817-401"
    assert payload["ready"] == ["task:T-001"]
    assert payload["blocked"] == []
    assert file_tree_snapshot(tmp_path / ".work-governance") == before
