from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from test_workctl import (
    init_plan,
    read_plan,
    run_workctl,
    schema_v4_admission_plan,
    sha256_path,
    write_plan,
)


def prepare_v4_plan(tmp_path: Path) -> None:
    """Create a valid v4 Plan with an explicit migration gate."""
    init_plan(tmp_path)
    frontmatter = schema_v4_admission_plan("PLAN-20260723-001")
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-MIGRATION-SCHEMA-V5",
            "description": "Migrate the Plan to schema v5.",
            "status": "accepted",
            "ref": "user:test-schema-v5-migration",
            "accepted_at": "2026-08-04T00:00:00+00:00",
        }
    )
    write_plan(tmp_path, frontmatter, "# Schema v5 fixture\n")


def read_active_plan_bytes(tmp_path: Path) -> bytes:
    return (tmp_path / ".work-governance" / "_Plan" / "PLAN-20260723-001.md").read_bytes()


def test_v4_inspect_and_dry_run_are_read_only_and_repeatable(tmp_path: Path) -> None:
    """Migration inspection does not rewrite the v4 source and dry-run is stable."""
    prepare_v4_plan(tmp_path)
    before = read_active_plan_bytes(tmp_path)
    inspect = json.loads(run_workctl(tmp_path, "migrate", "inspect").stdout)
    first = json.loads(
        run_workctl(
            tmp_path,
            "migrate",
            "apply",
            "--confirmation",
            "C-MIGRATION-SCHEMA-V5",
            "--expected-contract-revision",
            "1",
            "--dry-run",
        ).stdout
    )
    second = json.loads(
        run_workctl(
            tmp_path,
            "migrate",
            "apply",
            "--confirmation",
            "C-MIGRATION-SCHEMA-V5",
            "--expected-contract-revision",
            "1",
            "--dry-run",
        ).stdout
    )

    assert inspect["from_schema_version"] == 4
    assert inspect["to_schema_version"] == 5
    assert inspect["requires_migration"] is True
    assert first == second
    assert first["writes"] == []
    assert read_active_plan_bytes(tmp_path) == before
    assert not (tmp_path / ".work-governance" / "runtime" / "migrations-v5").exists()


def test_v5_apply_creates_backup_bundle_and_recovers_after_replace_interrupt(
    tmp_path: Path,
) -> None:
    """A replaced Plan is recoverable from its exact source backup and journal."""
    prepare_v4_plan(tmp_path)
    source_before = read_active_plan_bytes(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "migrate",
        "apply",
        "--confirmation",
        "C-MIGRATION-SCHEMA-V5",
        "--expected-contract-revision",
        "1",
        env={"WORKCTL_TEST_V5_MIGRATION_INTERRUPT": "1"},
        check=False,
    )
    assert interrupted.returncode == 2
    transactions = sorted(
        (tmp_path / ".work-governance" / "runtime" / "migrations-v5").glob("MIG-*/journal.json")
    )
    assert len(transactions) == 1
    journal_path = transactions[0]
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "plan-replaced"
    assert journal["source_sha256"] == sha256_path(
        next(journal_path.parent.glob("backup/plan.md"))
    )
    active = yaml.safe_load(read_active_plan_bytes(tmp_path).decode().split("---\n", 2)[1])
    assert active["schema_version"] == 5

    recovered = run_workctl(
        tmp_path,
        "migrate",
        "recover",
        "--migration-id",
        journal_path.parent.name,
    )
    assert "SCHEMA_V5_MIGRATION_RECOVERED" in recovered.stdout
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "committed"
    assert (journal_path.parent / "backup" / "plan.md").read_bytes() == source_before
    runtime_plan = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "plans"
        / "PLAN-20260723-001"
    )
    assert (runtime_plan / "state.json").is_file()
    assert (runtime_plan / "events.jsonl").is_file()


def test_v5_runtime_transitions_keep_contract_bytes_and_redact_secrets(
    tmp_path: Path,
) -> None:
    """Runtime state, events, and evidence evolve without rewriting the contract."""
    prepare_v4_plan(tmp_path)
    run_workctl(
        tmp_path,
        "migrate",
        "apply",
        "--confirmation",
        "C-MIGRATION-SCHEMA-V5",
        "--expected-contract-revision",
        "1",
    )
    contract_before = read_active_plan_bytes(tmp_path)

    started = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
    )
    assert "state_sequence=1" in started.stdout
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": "PLAN-20260723-001",
        "subject": "task:T-001",
        "created_at": "2026-08-04T00:00:00Z",
        "producer_ref": "runtime:test-schema-v5",
        "api_key": "sk-live-secret-fixture",
        "items": [{"ref": "runtime:test-result", "sha256": "a" * 64}],
    }
    verified = run_workctl(
        tmp_path,
        "task",
        "verify",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "1",
        "--evidence-stdin",
        input_text=json.dumps(evidence),
    )
    assert "state_sequence=2" in verified.stdout
    assert read_active_plan_bytes(tmp_path) == contract_before
    state_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "plans"
        / "PLAN-20260723-001"
        / "state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["state_sequence"] == 2
    assert state["tasks"]["T-001"]["status"] == "verified"
    event_text = (
        state_path.parent / "events.jsonl"
    ).read_text(encoding="utf-8")
    assert "sk-live-secret-fixture" not in event_text
    evidence_files = list(
        (tmp_path / ".work-governance" / "_Plan" / ".evidence" / "PLAN-20260723-001").glob("*.json")
    )
    assert evidence_files
    assert all(
        "sk-live-secret-fixture" not in path.read_text(encoding="utf-8")
        for path in evidence_files
    )


def test_v5_status_and_scheduler_keep_blocked_work_visible_and_bounded(
    tmp_path: Path,
) -> None:
    """A blocked task does not hide another ready task or expand compact status."""
    prepare_v4_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"].append(
        {
            "id": "T-002",
            "description": "A task intentionally blocked for the scheduler probe.",
            "status": "blocked",
            "unknowns": [],
            "expected_evidence_delta": "The blocked state remains visible.",
        }
    )
    write_plan(tmp_path, frontmatter, body)
    run_workctl(
        tmp_path,
        "migrate",
        "apply",
        "--confirmation",
        "C-MIGRATION-SCHEMA-V5",
        "--expected-contract-revision",
        "1",
    )

    status = json.loads(run_workctl(tmp_path, "plan", "status").stdout)
    assert len(json.dumps(status, ensure_ascii=False).encode("utf-8")) < 8 * 1024
    assert status["ready"] == ["task:T-001"]
    assert status["blocked"] == ["task:T-002"]
    assert "revision_history" not in status

    next_view = json.loads(run_workctl(tmp_path, "plan", "next").stdout)
    assert next_view["current_task"] == "task:T-001"


def test_v5_state_sequence_rejects_stale_transition_without_contract_change(
    tmp_path: Path,
) -> None:
    """A stale runtime sequence fails closed while preserving the v5 contract bytes."""
    prepare_v4_plan(tmp_path)
    run_workctl(
        tmp_path,
        "migrate",
        "apply",
        "--confirmation",
        "C-MIGRATION-SCHEMA-V5",
        "--expected-contract-revision",
        "1",
    )
    contract_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260723-001.md"
    contract_before = contract_path.read_bytes()
    run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
    )
    stale = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
        check=False,
    )
    assert stale.returncode == 2
    assert "STATE_SEQUENCE_MISMATCH" in stale.stderr
    assert contract_path.read_bytes() == contract_before
