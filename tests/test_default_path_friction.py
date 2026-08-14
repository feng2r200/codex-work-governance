from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from test_schema_v5 import (
    STRICT_CONTROLLER_ENV,
    init_minimal_v5_goal,
    prepare_v4_plan,
    read_active_plan_bytes,
    run_without_receipt,
)
from test_workctl import file_tree_snapshot, read_plan_by_id, run_workctl, sha256_path


def load_json_output(value: str) -> dict[str, Any]:
    """Parse one JSON command response as a mutable mapping."""
    return cast(dict[str, Any], json.loads(value))


def runtime_plan_root(tmp_path: Path, plan_id: str) -> Path:
    """Return the schema-v5 runtime directory for one Plan."""
    return tmp_path / ".work-governance" / "runtime" / "plans" / plan_id


def test_default_path_read_only_surfaces_do_not_create_an_implicit_plan(
    tmp_path: Path,
) -> None:
    """No-Plan bootstrap and read-only views must not create active Plan authority."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)

    status = load_json_output(
        run_workctl(tmp_path, "plan", "status", env=STRICT_CONTROLLER_ENV).stdout
    )
    before = file_tree_snapshot(tmp_path / ".work-governance")
    risk = load_json_output(
        run_without_receipt(
            tmp_path,
            "risk",
            "inspect",
            "--action-kind",
            "local_edit",
            "--target-ref",
            "project:src/example.py",
        ).stdout
    )
    history = load_json_output(
        run_without_receipt(tmp_path, "plan", "history", "list").stdout
    )
    plan_help = load_json_output(run_without_receipt(tmp_path, "help", "plan").stdout)

    assert status["plan_id"] is None
    assert status["ready"] == []
    assert status["next_suggestion"] == "Admit a Plan only when durable execution state is needed."
    assert risk["controller_decision"] == "facts_only"
    assert risk["decision_owner"] == "model"
    assert history["plans"] == []
    assert "goal init --stdin|--from-file" in plan_help["commands"]
    assert not (tmp_path / ".work-governance" / "_Plan").exists()
    assert file_tree_snapshot(tmp_path / ".work-governance") == before


def test_default_path_v5_adapt_and_task_done_skip_v4_intake_manifest_churn(
    tmp_path: Path,
) -> None:
    """Schema-v5 high-level adapt and task done run without v4 intake arguments."""
    init_minimal_v5_goal(tmp_path, "PLAN-20260812-101")
    plan_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260812-101.md"
    contract_before = plan_path.read_bytes()

    adapted = load_json_output(
        run_workctl(
            tmp_path,
            "plan",
            "adapt",
            "--intent-stdin",
            "--summary",
            "Record default-path adjustment.",
            "--idempotency-key",
            "default-path-adapt",
            input_text="continue with the next ready task\n",
            env=STRICT_CONTROLLER_ENV,
        ).stdout
    )
    done = load_json_output(
        run_workctl(
            tmp_path,
            "task",
            "done",
            "--task-id",
            "T-001",
            "--expected-state-sequence",
            "1",
            "--evidence-stdin",
            "--summary",
            "default path task evidence",
            "--idempotency-key",
            "default-path-task-done",
            input_text="task evidence\n",
            env=STRICT_CONTROLLER_ENV,
        ).stdout
    )
    frontmatter, _body = read_plan_by_id(tmp_path, "PLAN-20260812-101")
    state = json.loads(
        (runtime_plan_root(tmp_path, "PLAN-20260812-101") / "state.json").read_text(
            encoding="utf-8"
        )
    )
    events = [
        json.loads(line)
        for line in (runtime_plan_root(tmp_path, "PLAN-20260812-101") / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert adapted["status"] == "PLAN_ADAPT_INTENT_RECORDED"
    assert adapted["state_sequence"] == 1
    assert adapted["evidence_ref"] == adapted["direct_evidence_ref"]
    assert done["status"] == "TASK_DONE"
    assert done["state_sequence"] == 2
    assert done["evidence_ref"] == done["direct_evidence_ref"]
    assert frontmatter["contract_revision"] == 1
    assert plan_path.read_bytes() == contract_before
    assert state["state_sequence"] == 2
    assert state["tasks"]["T-001"]["status"] == "verified"
    assert not (tmp_path / ".work-governance" / "_Plan" / ".evidence").exists()
    assert [event["event"] for event in events] == [
        "plan.initialized",
        "plan.adapted",
        "task.verified",
    ]


def test_default_path_legacy_plan_is_read_only_until_current_schema_refresh(
    tmp_path: Path,
) -> None:
    """Outdated active Plans expose guidance without runnable task or state adaptation."""
    prepare_v4_plan(tmp_path)
    source_before = read_active_plan_bytes(tmp_path)

    status = load_json_output(
        run_workctl(tmp_path, "plan", "status", env=STRICT_CONTROLLER_ENV).stdout
    )
    inspect = load_json_output(
        run_workctl(tmp_path, "migrate", "inspect", env=STRICT_CONTROLLER_ENV).stdout
    )
    dry_run = load_json_output(
        run_without_receipt(tmp_path, "migrate", "apply", "--dry-run").stdout
    )
    blocked_task = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )

    assert status["authority_state"] == "PLAN_SCHEMA_REFRESH_REQUIRED"
    assert status["legacy_summary"]["authority"] == "NON_AUTHORITY"
    assert "ready" not in status
    assert "migrate apply --expected-contract-revision 1" in status["next_suggestion"]
    assert inspect["legacy_state_migrated"] is False
    assert dry_run["writes"] == []
    assert dry_run["legacy_summary"] == inspect["legacy_summary"]
    assert blocked_task.returncode == 2
    assert "PLAN_SCHEMA_REFRESH_REQUIRED" in blocked_task.stderr
    assert read_active_plan_bytes(tmp_path) == source_before
    assert not (tmp_path / ".work-governance" / "runtime" / "migrations-v5").exists()


def test_default_path_risk_and_worktree_merge_inspection_remain_facts_only(
    tmp_path: Path,
) -> None:
    """Risk and worktree merge inspection report facts without taking authority."""
    init_minimal_v5_goal(tmp_path, "PLAN-20260812-102")
    plan_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260812-102.md"
    contract_before = plan_path.read_bytes()
    before_risk = file_tree_snapshot(tmp_path / ".work-governance")
    action_text = "deploy candidate\n"

    risk = load_json_output(
        run_without_receipt(
            tmp_path,
            "risk",
            "inspect",
            "--action-kind",
            "production_change",
            "--target-ref",
            "project:service/prod",
            "--action-stdin",
            input_text=action_text,
        ).stdout
    )
    assert risk["controller_decision"] == "facts_only"
    assert risk["requires_confirmation_by_controller"] is False
    assert risk["decision_owner"] == "model"
    assert risk["action_sha256"] == hashlib.sha256(action_text.encode("utf-8")).hexdigest()
    assert file_tree_snapshot(tmp_path / ".work-governance") == before_risk

    opened = load_json_output(
        run_workctl(
            tmp_path,
            "worktree",
            "begin",
            "--worktree-id",
            "WT-default-path",
            "--path",
            ".work-governance/worktrees/default-path",
            "--branch",
            "feature/default-path",
            "--summary",
            "Run default-path implementation slice.",
            env=STRICT_CONTROLLER_ENV,
        ).stdout
    )
    closed = load_json_output(
        run_workctl(
            tmp_path,
            "worktree",
            "close",
            "--worktree-id",
            "WT-default-path",
            "--summary",
            "Closed default-path implementation slice.",
            env=STRICT_CONTROLLER_ENV,
        ).stdout
    )
    merge = load_json_output(
        run_without_receipt(
            tmp_path,
            "worktree",
            "merge",
            "inspect",
            "--worktree-id",
            "WT-default-path",
        ).stdout
    )
    authority = load_json_output(
        run_workctl(tmp_path, "plan", "authority", "check", env=STRICT_CONTROLLER_ENV).stdout
    )

    assert opened["authority"] == "NON_AUTHORITY"
    assert opened["fork_base"]["plan_sha256"] == sha256_path(plan_path)
    assert closed["close_summary"]["authority"] == "NON_AUTHORITY"
    assert merge["authority"] == "NON_AUTHORITY"
    assert merge["controller_decision"] == "inspect_only"
    assert merge["parent_mutated"] is False
    assert merge["merge_state"] == "READY_FOR_PARENT_REVIEW"
    assert authority["authority_state"] == "GOVERNED_ACTIVE"
    assert plan_path.read_bytes() == contract_before
