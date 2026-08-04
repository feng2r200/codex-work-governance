from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from test_workctl import (
    SCRIPT,
    independent_validation_fixture,
    init_plan,
    read_plan,
    run_workctl,
    schema_v4_admission_plan,
    sha256_path,
    write_plan,
)

STRICT_CONTROLLER_ENV = {"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"}


def run_without_receipt(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the real controller without the required SessionStart receipt argument."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def issue_test_turn(
    tmp_path: Path,
    *,
    turn_id: str,
    prompt: str,
) -> tuple[str, str]:
    """Issue a valid current-turn receipt against the strict test controller."""
    run_workctl(tmp_path, "plan", "status", env=STRICT_CONTROLLER_ENV)
    session_path = tmp_path / ".work-governance" / "bootstrap-state.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    request_ref = f"user:session/{session['session_id']}/turn/{turn_id}/sha256/{prompt_sha256}"
    turn: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-current-turn-receipt",
        "plugin_build": session["plugin_build"],
        "session_start_receipt_sha256": hashlib.sha256(session_path.read_bytes()).hexdigest(),
        "session_id": session["session_id"],
        "turn_id": turn_id,
        "prompt_sha256": prompt_sha256,
        "request_ref": request_ref,
        "project_root": tmp_path.resolve().as_posix(),
        "issued_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    turn_sha256 = hashlib.sha256(
        json.dumps(
            turn,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    turn["receipt_sha256"] = turn_sha256
    path = tmp_path / ".work-governance" / "runtime" / "current-turn-receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(turn, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return request_ref, turn_sha256


def add_pending_v5_confirmation(tmp_path: Path, *, basis_sha256: str) -> None:
    """Add a strict pending gate that survives the v4-to-v5 fixture migration."""
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-V5-HIGH-IMPACT",
            "description": "Authorize the exact v5 high-impact task gate.",
            "status": "pending",
            "intervention": {
                "kind": "plan_contract",
                "blocks": ["task:T-001"],
                "basis_ref": "project:v5-high-impact-basis",
                "basis_sha256": basis_sha256,
            },
        }
    )
    write_plan(tmp_path, frontmatter, body)


def add_pending_action_confirmation(
    tmp_path: Path,
    *,
    target_ref: str,
    action_sha256: str,
) -> None:
    """Add an external-authority gate bound to one exact action target and digest."""
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-EXACT-PRODUCTION-ACTION",
            "description": "Authorize one exact production action.",
            "status": "pending",
            "intervention": {
                "kind": "external_authority",
                "action_kind": "production_change",
                "blocks": ["task:T-001"],
                "basis_ref": target_ref,
                "basis_sha256": action_sha256,
            },
        }
    )
    write_plan(tmp_path, frontmatter, body)


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


def test_goal_gate_truth_and_review_public_views(tmp_path: Path) -> None:
    """Top-level public views expose current governance state without mutation."""
    prepare_v4_plan(tmp_path)
    before = read_active_plan_bytes(tmp_path)

    goal = json.loads(run_workctl(tmp_path, "goal", "show").stdout)
    gates = json.loads(run_workctl(tmp_path, "gate", "list").stdout)
    gate = json.loads(
        run_workctl(
            tmp_path,
            "gate",
            "check",
            "--gate-id",
            "C-MIGRATION-SCHEMA-V5",
        ).stdout
    )
    truth = json.loads(run_workctl(tmp_path, "truth", "list").stdout)
    truth_conflicts = json.loads(run_workctl(tmp_path, "truth", "conflicts").stdout)
    review = json.loads(run_workctl(tmp_path, "review", "status").stdout)
    review_request = json.loads(run_workctl(tmp_path, "review", "request").stdout)

    assert goal["plan_id"] == "PLAN-20260723-001"
    assert {item["id"] for item in gates["gates"]} >= {
        "C-ADMISSION",
        "C-MIGRATION-SCHEMA-V5",
    }
    assert gate["id"] == "C-MIGRATION-SCHEMA-V5"
    assert truth["truth_refs"] == []
    assert truth_conflicts["conflicts"] == []
    assert review["independent_validation"] == {}
    assert review_request["record_command"] == "review attach --manifest PATH"
    assert read_active_plan_bytes(tmp_path) == before


def test_top_level_write_aliases_require_ready_receipt(tmp_path: Path) -> None:
    """Public write aliases must not bypass the SessionStart READY receipt gate."""
    prepare_v4_plan(tmp_path)
    patch = tmp_path / "truth.yaml"
    patch.write_text("truth_refs:\n- project:truth-source\n", encoding="utf-8")
    review_manifest = tmp_path / "review.json"
    review_manifest.write_text("{}", encoding="utf-8")
    commands = [
        (
            "goal",
            "revise",
            "--manifest",
            str(patch),
        ),
        (
            "gate",
            "open",
            "--confirmation-id",
            "C-ALIAS",
            "--description",
            "Alias gate",
            "--intervention-kind",
            "plan_contract",
            "--blocks",
            "route",
            "--basis-ref",
            "project:alias-basis",
            "--basis-sha256",
            "a" * 64,
            "--expected-revision",
            "1",
        ),
        (
            "truth",
            "add",
            "--manifest",
            str(patch),
        ),
        (
            "review",
            "attach",
            "--manifest",
            str(review_manifest),
            "--expected-revision",
            "1",
        ),
    ]

    for command in commands:
        result = run_without_receipt(tmp_path, *command)
        assert result.returncode == 2, command
        assert "BOOTSTRAP_RECEIPT_REQUIRED" in result.stderr


def test_gate_aliases_are_directional_and_upgrade_gate_compatible(
    tmp_path: Path,
) -> None:
    """Gate aliases hard-code their decision and remain legal under upgrade gating."""
    init_plan(tmp_path)
    result = run_workctl(
        tmp_path,
        "gate",
        "open",
        "--confirmation-id",
        "C-SCHEMA-UPGRADE-ALIAS",
        "--description",
        "Authorize upgrade gate alias.",
        "--intervention-kind",
        "plan_contract",
        "--blocks",
        "route",
        "--basis-ref",
        "project:schema-upgrade-alias",
        "--basis-sha256",
        "b" * 64,
        "--expected-revision",
        "1",
        env=STRICT_CONTROLLER_ENV,
    )
    assert "CONFIRMATION_ADDED C-SCHEMA-UPGRADE-ALIAS pending" in result.stdout

    reversed_decision = run_workctl(
        tmp_path,
        "gate",
        "satisfy",
        "--confirmation-id",
        "C-SCHEMA-UPGRADE-ALIAS",
        "--decision",
        "declined",
        "--ref",
        "user:invalid-alias-decision",
        "--expected-revision",
        "2",
        check=False,
    )
    assert reversed_decision.returncode == 2
    assert "unrecognized arguments: --decision declined" in reversed_decision.stderr


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
    assert journal["source_sha256"] == sha256_path(next(journal_path.parent.glob("backup/plan.md")))
    active = yaml.safe_load(read_active_plan_bytes(tmp_path).decode().split("---\n", 2)[1])
    assert active["schema_version"] == 5

    bypass = run_without_receipt(
        tmp_path,
        "migrate",
        "recover",
        "--migration-id",
        journal_path.parent.name,
    )
    assert bypass.returncode == 2
    assert "BOOTSTRAP_RECEIPT_REQUIRED" in bypass.stderr
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "plan-replaced"

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
    runtime_plan = tmp_path / ".work-governance" / "runtime" / "plans" / "PLAN-20260723-001"
    assert (runtime_plan / "state.json").is_file()
    assert (runtime_plan / "events.jsonl").is_file()
    frontmatter, _body = read_plan(tmp_path)
    assert frontmatter["evidence_store_ref"] == "evidence:.work-governance/evidence"


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
    assert not (tmp_path / ".work-governance" / "runtime" / "current-turn-receipt.json").exists()

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
        tmp_path / ".work-governance" / "runtime" / "plans" / "PLAN-20260723-001" / "state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["state_sequence"] == 2
    assert state["tasks"]["T-001"]["status"] == "verified"
    event_text = (state_path.parent / "events.jsonl").read_text(encoding="utf-8")
    assert "sk-live-secret-fixture" not in event_text
    evidence_files = list(
        (tmp_path / ".work-governance" / "_Plan" / ".evidence" / "PLAN-20260723-001").glob("*.json")
    )
    assert evidence_files
    assert all(
        "sk-live-secret-fixture" not in path.read_text(encoding="utf-8") for path in evidence_files
    )


def test_v5_task_advancement_preserves_independent_review_blockers(
    tmp_path: Path,
) -> None:
    """A v5 blocked task cannot bypass review while unrelated ready work can proceed."""
    prepare_v4_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"].append(
        {
            "id": "T-002",
            "description": "Unblocked sibling task.",
            "status": "pending",
            "unknowns": [],
            "expected_evidence_delta": "The sibling task can still progress.",
        }
    )
    frontmatter["independent_validation"] = independent_validation_fixture()
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

    blocked_start = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
        check=False,
    )
    blocked_skip = run_workctl(
        tmp_path,
        "task",
        "skip",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
        check=False,
    )
    sibling = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-002",
        "--expected-state-sequence",
        "0",
    )

    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked_start.stderr
    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked_skip.stderr
    assert "TASK_UPDATED T-002 in_progress state_sequence=1" in sibling.stdout


def test_v5_task_advancement_preserves_artifact_blockers(tmp_path: Path) -> None:
    """A v5 task cannot progress through suspect artifacts unless it owns recovery."""
    prepare_v4_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"].append(
        {
            "id": "T-002",
            "description": "Repair the suspect artifact.",
            "status": "pending",
            "unknowns": [],
            "resolves_artifacts": ["A-001"],
            "expected_evidence_delta": "The suspect artifact is repaired.",
        }
    )
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "pending"}]
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
    frontmatter, body = read_plan(tmp_path)
    frontmatter["artifacts"][0]["status"] = "suspect"
    write_plan(tmp_path, frontmatter, body)

    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
        check=False,
    )
    recovery = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-002",
        "--expected-state-sequence",
        "0",
    )

    assert "BLOCKED_BY_ARTIFACT: A-001 is suspect" in blocked.stderr
    assert "TASK_UPDATED T-002 in_progress state_sequence=1" in recovery.stdout


def test_v5_task_verify_reads_evidence_manifest_path(tmp_path: Path) -> None:
    """The documented --evidence-manifest path works for v5 task verification."""
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
    run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
    )
    evidence = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": "PLAN-20260723-001",
        "subject": "task:T-001",
        "created_at": "2026-08-04T00:00:00Z",
        "producer_ref": "runtime:test-schema-v5-manifest",
        "items": [{"ref": "runtime:test-result", "sha256": "a" * 64}],
    }
    evidence_path = tmp_path / "task-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    wrong_subject = {**evidence, "subject": "validation:V-001"}
    wrong_subject_path = tmp_path / "wrong-subject-evidence.json"
    wrong_subject_path.write_text(json.dumps(wrong_subject), encoding="utf-8")

    subject_blocked = run_workctl(
        tmp_path,
        "task",
        "verify",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "1",
        "--evidence-manifest",
        str(wrong_subject_path),
        check=False,
    )

    assert "EVIDENCE_MANIFEST_SUBJECT_MISMATCH" in subject_blocked.stderr

    verified = run_workctl(
        tmp_path,
        "task",
        "verify",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "1",
        "--evidence-manifest",
        str(evidence_path),
    )

    assert "TASK_UPDATED T-001 verified state_sequence=2" in verified.stdout
    state_path = (
        tmp_path / ".work-governance" / "runtime" / "plans" / "PLAN-20260723-001" / "state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["tasks"]["T-001"]["status"] == "verified"
    assert state["tasks"]["T-001"]["evidence_ref"].startswith(
        "evidence:.work-governance/_Plan/.evidence/PLAN-20260723-001/"
    )


def test_direct_evidence_capture_writes_ledger_blob_and_keeps_contract_stable(
    tmp_path: Path,
) -> None:
    """Direct capture persists redacted evidence and only advances v5 runtime state."""
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

    captured = json.loads(
        run_workctl(
            tmp_path,
            "evidence",
            "capture",
            "--task",
            "T-001",
            "--kind",
            "command-output",
            "--summary",
            "pytest token=summary-secret",
            "--idempotency-key",
            "pytest:capture:stdin",
            "--expected-state-sequence",
            "0",
            input_text="ok\nAuthorization: Bearer output-secret\n",
        ).stdout
    )
    replayed = json.loads(
        run_workctl(
            tmp_path,
            "evidence",
            "capture",
            "--task",
            "T-001",
            "--kind",
            "command-output",
            "--summary",
            "pytest token=summary-secret",
            "--idempotency-key",
            "pytest:capture:stdin",
            input_text="ok\nAuthorization: Bearer output-secret\n",
        ).stdout
    )

    assert captured["idempotent"] is False
    assert captured["state_sequence"] == 1
    assert replayed["idempotent"] is True
    assert replayed["id"] == captured["id"]
    assert replayed["state_sequence"] == 1
    assert read_active_plan_bytes(tmp_path) == contract_before

    ledger_path = tmp_path / ".work-governance" / "evidence" / "ledger.ndjson"
    ledger_records = [
        json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(ledger_records) == 1
    assert ledger_records[0]["summary"] == "pytest token=[REDACTED]"
    assert ledger_records[0]["task_ref"] == "task:T-001"
    assert "summary-secret" not in ledger_path.read_text(encoding="utf-8")

    blob_path = tmp_path / captured["blob_ref"].removeprefix("evidence:")
    blob_text = blob_path.read_text(encoding="utf-8")
    assert "output-secret" not in blob_text
    assert "Bearer [REDACTED]" in blob_text or "Authorization=[REDACTED]" in blob_text

    state_path = (
        tmp_path / ".work-governance" / "runtime" / "plans" / "PLAN-20260723-001" / "state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["state_sequence"] == 1
    assert state["tasks"]["T-001"]["evidence_refs"] == [captured["evidence_ref"]]
    assert state["tasks"]["T-001"]["evidence_sha256s"] == [captured["evidence_sha256"]]
    record_path = tmp_path / captured["evidence_ref"].removeprefix("evidence:")
    assert sha256_path(record_path) == captured["evidence_sha256"]

    artifact = tmp_path / "artifact.txt"
    artifact.write_text("file token=file-secret\n", encoding="utf-8")
    file_capture = json.loads(
        run_workctl(
            tmp_path,
            "evidence",
            "capture",
            "--task",
            "T-001",
            "--kind",
            "artifact",
            "--summary",
            "artifact capture",
            "--from-file",
            "artifact.txt",
            "--expected-state-sequence",
            "1",
        ).stdout
    )
    assert file_capture["state_sequence"] == 2
    file_blob = tmp_path / file_capture["blob_ref"].removeprefix("evidence:")
    assert "file-secret" not in file_blob.read_text(encoding="utf-8")
    file_record = tmp_path / file_capture["evidence_ref"].removeprefix("evidence:")
    assert sha256_path(file_record) == file_capture["evidence_sha256"]
    assert read_active_plan_bytes(tmp_path) == contract_before


def test_direct_capture_stale_state_writes_no_durable_evidence(
    tmp_path: Path,
) -> None:
    """A failed state guard leaves no direct evidence ledger, record, or blob."""
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
    run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-state-sequence",
        "0",
    )
    contract_before = read_active_plan_bytes(tmp_path)
    failed = run_workctl(
        tmp_path,
        "evidence",
        "capture",
        "--task",
        "T-001",
        "--kind",
        "command-output",
        "--summary",
        "stale capture",
        "--expected-state-sequence",
        "0",
        input_text="this output must not persist\n",
        check=False,
    )

    assert failed.returncode == 2
    assert "STATE_SEQUENCE_MISMATCH" in failed.stderr
    evidence_root = tmp_path / ".work-governance" / "evidence"
    assert not (evidence_root / "ledger.ndjson").exists()
    assert not (evidence_root / "records").exists()
    assert not (evidence_root / "blobs").exists()
    assert read_active_plan_bytes(tmp_path) == contract_before


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


def test_v5_confirmation_requires_exact_current_turn_without_plan_intake(
    tmp_path: Path,
) -> None:
    """A v5 high-impact gate is turn-bound but does not recreate v4 intake."""
    basis_sha256 = "b" * 64
    prepare_v4_plan(tmp_path)
    add_pending_v5_confirmation(tmp_path, basis_sha256=basis_sha256)
    run_workctl(
        tmp_path,
        "migrate",
        "apply",
        "--confirmation",
        "C-MIGRATION-SCHEMA-V5",
        "--expected-contract-revision",
        "1",
        env=STRICT_CONTROLLER_ENV,
    )

    missing = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-V5-HIGH-IMPACT",
        "--ref",
        "user:missing-turn",
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "1",
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert missing.returncode == 2
    assert "TURN_RECEIPT_REQUIRED" in missing.stderr

    request_ref, turn_sha256 = issue_test_turn(
        tmp_path,
        turn_id="turn-v5-confirm",
        prompt="authorize the exact v5 confirmation",
    )
    mismatched = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-V5-HIGH-IMPACT",
        "--ref",
        "user:not-the-current-turn",
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "1",
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert mismatched.returncode == 2
    assert "CONFIRMATION_REF_CURRENT_TURN_REQUIRED" in mismatched.stderr

    decided = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-V5-HIGH-IMPACT",
        "--ref",
        request_ref,
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "1",
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
    )
    assert "CONFIRMATION_DECIDED C-V5-HIGH-IMPACT accepted revision=2" in decided.stdout
    frontmatter, _body = read_plan(tmp_path)
    assert frontmatter["revision"] == 2
    assert frontmatter["contract_revision"] == 2
    assert "intake" not in frontmatter
    event_lines = (
        tmp_path / ".work-governance" / "runtime" / "plans" / "PLAN-20260723-001" / "events.jsonl"
    ).read_text(encoding="utf-8")
    assert "confirmation.decided" in event_lines
    assert "C-V5-HIGH-IMPACT" in event_lines

    replay = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-V5-HIGH-IMPACT",
        "--ref",
        request_ref,
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert replay.returncode == 2
    assert "INVALID_CONFIRMATION_TRANSITION" in replay.stderr


def test_v5_confirmation_add_cannot_pre_accept_gate(tmp_path: Path) -> None:
    """Schema-v5 accepted gates must be decided by plan confirm with the current turn."""
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

    fabricated = run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "add",
        "--confirmation-id",
        "C-V5-FABRICATED",
        "--description",
        "Fabricate an accepted v5 gate.",
        "--intervention-kind",
        "external_authority",
        "--action-kind",
        "production_change",
        "--blocks",
        "task:T-001",
        "--basis-ref",
        "project:fabricated-action",
        "--basis-sha256",
        "f" * 64,
        "--status",
        "accepted",
        "--ref",
        "user:not-current-turn",
        "--expected-revision",
        "1",
        check=False,
    )

    assert fabricated.returncode == 2
    assert "CONFIRMATION_ACCEPTED_REQUIRES_PLAN_CONFIRM" in fabricated.stderr


def test_high_impact_action_authorization_is_target_bound_and_single_use(
    tmp_path: Path,
) -> None:
    """External high-impact authority expires with its turn and cannot replay."""
    target_ref = "project:service/stocklens-production"
    action_sha256 = "c" * 64
    prepare_v4_plan(tmp_path)
    add_pending_action_confirmation(
        tmp_path,
        target_ref=target_ref,
        action_sha256=action_sha256,
    )
    run_workctl(
        tmp_path,
        "migrate",
        "apply",
        "--confirmation",
        "C-MIGRATION-SCHEMA-V5",
        "--expected-contract-revision",
        "1",
        env=STRICT_CONTROLLER_ENV,
    )
    request_ref, turn_sha256 = issue_test_turn(
        tmp_path,
        turn_id="turn-action-authorize",
        prompt="authorize one exact production action",
    )
    unconfirmed = run_workctl(
        tmp_path,
        "action",
        "authorize",
        "--action-kind",
        "production_change",
        "--target-ref",
        target_ref,
        "--action-sha256",
        action_sha256,
        "--confirmation-id",
        "C-EXACT-PRODUCTION-ACTION",
        "--ref",
        request_ref,
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert unconfirmed.returncode == 2
    assert "ACTION_CONFIRMATION_NOT_ACCEPTED" in unconfirmed.stderr

    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-EXACT-PRODUCTION-ACTION",
        "--ref",
        request_ref,
        "--evidence-sha256",
        action_sha256,
        "--expected-revision",
        "1",
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
    )
    wrong_kind = run_workctl(
        tmp_path,
        "action",
        "authorize",
        "--action-kind",
        "remote_write",
        "--target-ref",
        target_ref,
        "--action-sha256",
        action_sha256,
        "--confirmation-id",
        "C-EXACT-PRODUCTION-ACTION",
        "--ref",
        request_ref,
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert wrong_kind.returncode == 2
    assert "ACTION_CONFIRMATION_BINDING_MISMATCH" in wrong_kind.stderr

    authorized = json.loads(
        run_workctl(
            tmp_path,
            "action",
            "authorize",
            "--action-kind",
            "production_change",
            "--target-ref",
            target_ref,
            "--action-sha256",
            action_sha256,
            "--confirmation-id",
            "C-EXACT-PRODUCTION-ACTION",
            "--ref",
            request_ref,
            "--turn-receipt-sha256",
            turn_sha256,
            env=STRICT_CONTROLLER_ENV,
        ).stdout
    )
    authorization_id = authorized["authorization_id"]
    assert authorized["state"] == "authorized"
    assert authorized["contract_sha256"] == sha256_path(
        tmp_path / ".work-governance" / "_Plan" / "PLAN-20260723-001.md"
    )
    assert "production action" not in json.dumps(authorized)

    plan_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260723-001.md"
    unchanged_contract = plan_path.read_bytes()
    plan_path.write_bytes(unchanged_contract + b"\nOut-of-band contract drift.\n")
    contract_drift = run_workctl(
        tmp_path,
        "action",
        "consume",
        "--authorization-id",
        authorization_id,
        "--action-kind",
        "production_change",
        "--target-ref",
        target_ref,
        "--action-sha256",
        action_sha256,
        "--turn-receipt-sha256",
        turn_sha256,
        "--consumer-ref",
        "runtime:executor",
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert contract_drift.returncode == 2
    assert "ACTION_AUTHORIZATION_CONTRACT_DRIFT" in contract_drift.stderr
    plan_path.write_bytes(unchanged_contract)

    mismatch = run_workctl(
        tmp_path,
        "action",
        "consume",
        "--authorization-id",
        authorization_id,
        "--action-kind",
        "production_change",
        "--target-ref",
        "project:service/other-production",
        "--action-sha256",
        action_sha256,
        "--turn-receipt-sha256",
        turn_sha256,
        "--consumer-ref",
        "runtime:executor",
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert mismatch.returncode == 2
    assert "ACTION_AUTHORIZATION_TARGET_MISMATCH" in mismatch.stderr

    consumed = json.loads(
        run_workctl(
            tmp_path,
            "action",
            "consume",
            "--authorization-id",
            authorization_id,
            "--action-kind",
            "production_change",
            "--target-ref",
            target_ref,
            "--action-sha256",
            action_sha256,
            "--turn-receipt-sha256",
            turn_sha256,
            "--consumer-ref",
            "runtime:executor",
            env=STRICT_CONTROLLER_ENV,
        ).stdout
    )
    assert consumed["state"] == "consumed"

    replay = run_workctl(
        tmp_path,
        "action",
        "consume",
        "--authorization-id",
        authorization_id,
        "--action-kind",
        "production_change",
        "--target-ref",
        target_ref,
        "--action-sha256",
        action_sha256,
        "--turn-receipt-sha256",
        turn_sha256,
        "--consumer-ref",
        "runtime:executor",
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert replay.returncode == 2
    assert "ACTION_AUTHORIZATION_REPLAYED" in replay.stderr

    remint = run_workctl(
        tmp_path,
        "action",
        "authorize",
        "--action-kind",
        "production_change",
        "--target-ref",
        target_ref,
        "--action-sha256",
        action_sha256,
        "--confirmation-id",
        "C-EXACT-PRODUCTION-ACTION",
        "--ref",
        request_ref,
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert remint.returncode == 2
    assert "ACTION_AUTHORIZATION_REPLAYED" in remint.stderr


def test_v5_confirmation_recovers_event_after_contract_replace_interrupt(
    tmp_path: Path,
) -> None:
    """A killed v5 confirmation repairs its ledger without replaying authority."""
    basis_sha256 = "d" * 64
    prepare_v4_plan(tmp_path)
    add_pending_v5_confirmation(tmp_path, basis_sha256=basis_sha256)
    run_workctl(
        tmp_path,
        "migrate",
        "apply",
        "--confirmation",
        "C-MIGRATION-SCHEMA-V5",
        "--expected-contract-revision",
        "1",
        env=STRICT_CONTROLLER_ENV,
    )
    request_ref, turn_sha256 = issue_test_turn(
        tmp_path,
        turn_id="turn-v5-interrupt",
        prompt="authorize the recoverable v5 confirmation",
    )
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-V5-HIGH-IMPACT",
        "--ref",
        request_ref,
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "1",
        "--turn-receipt-sha256",
        turn_sha256,
        env={
            **STRICT_CONTROLLER_ENV,
            "WORKCTL_TEST_V5_CONTRACT_INTERRUPT": "after-plan",
        },
        check=False,
    )
    assert interrupted.returncode == 2
    assert "SCHEMA_V5_TEST_INTERRUPTED_AFTER_CONTRACT" in interrupted.stderr

    runtime = tmp_path / ".work-governance" / "runtime" / "plans" / "PLAN-20260723-001"
    state_before = json.loads((runtime / "state.json").read_text(encoding="utf-8"))
    assert state_before["pending_event"]["event"] == "confirmation.decided"
    assert "confirmation.decided" not in (runtime / "events.jsonl").read_text(encoding="utf-8")

    recovered_replay = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-V5-HIGH-IMPACT",
        "--ref",
        request_ref,
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        env=STRICT_CONTROLLER_ENV,
        check=False,
    )
    assert recovered_replay.returncode == 2
    assert "INVALID_CONFIRMATION_TRANSITION" in recovered_replay.stderr
    state_after = json.loads((runtime / "state.json").read_text(encoding="utf-8"))
    assert "pending_event" not in state_after
    assert "confirmation.decided" in (runtime / "events.jsonl").read_text(encoding="utf-8")
