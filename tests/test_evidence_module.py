from __future__ import annotations

import importlib
import json
import re
import sys
from argparse import Namespace
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

evidence_module = importlib.import_module("workctl_modules.evidence")
append_capture_record = evidence_module.append_capture_record
find_capture_record_by_idempotency_key = evidence_module.find_capture_record_by_idempotency_key
persist_capture_blob = evidence_module.persist_capture_blob
persist_capture_metadata = evidence_module.persist_capture_metadata
persist_direct_evidence_bytes = evidence_module.persist_direct_evidence_bytes
redact_capture_bytes = evidence_module.redact_capture_bytes
validate_capture_args = evidence_module.validate_capture_args
validate_evidence_payload = evidence_module.validate_evidence_payload
verify_capture_record_file = evidence_module.verify_capture_record_file
workflow_evidence_payload = evidence_module.workflow_evidence_payload


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def valid_reference(value: object) -> bool:
    """Return the bounded reference shape accepted by evidence fixtures."""
    return (
        isinstance(value, str)
        and re.fullmatch(r"^(project|runtime|git):\S+$", value) is not None
    )


def test_validate_evidence_payload_accepts_bounded_manifest() -> None:
    """The evidence module accepts the same bounded manifest shape as workctl."""
    validate_evidence_payload(
        {
            "schema_version": 1,
            "kind": "work-governance-evidence",
            "plan_id": "PLAN-20260806-001",
            "subject": "task:T-001",
            "created_at": "2026-08-06T00:00:00Z",
            "producer_ref": "runtime:pytest",
            "items": [{"ref": "project:result", "sha256": "a" * 64}],
        },
        expected_plan_id="PLAN-20260806-001",
        expected_subject="task:T-001",
        valid_reference=valid_reference,
        sha256_pattern=SHA256_RE,
        max_items=10,
    )


def test_validate_evidence_payload_preserves_error_codes() -> None:
    """The extracted validator raises the controller-facing error code unchanged."""
    try:
        validate_evidence_payload(
            {
                "schema_version": 1,
                "kind": "work-governance-evidence",
                "plan_id": "PLAN-20260806-001",
                "subject": "task:T-001",
                "created_at": "2026-08-06T00:00:00Z",
                "producer_ref": "runtime:pytest",
                "items": [{"ref": "project:result", "sha256": "not-a-sha"}],
            },
            expected_plan_id="PLAN-20260806-001",
            expected_subject="task:T-001",
            valid_reference=valid_reference,
            sha256_pattern=SHA256_RE,
            max_items=10,
        )
    except ValueError as exc:
        assert str(exc) == "INVALID_EVIDENCE_MANIFEST_ITEM"
    else:
        raise AssertionError("invalid evidence item was accepted")


def test_direct_capture_store_persists_blob_metadata_and_ledger(tmp_path: Path) -> None:
    """The evidence module owns direct capture blob, metadata, and ledger storage."""
    blob_ref, blob_sha256, blob_size = persist_capture_blob(tmp_path, b"secret-free evidence\n")
    assert blob_ref == f"evidence:.work-governance/evidence/blobs/{blob_sha256}"
    assert blob_size == len(b"secret-free evidence\n")

    record = {
        "schema_version": 1,
        "kind": "work-governance-evidence-record",
        "id": "E-20260806T000000Z-abcdefabcdef",
        "plan_id": "PLAN-20260806-001",
        "idempotency_key": "capture:test",
        "blob_ref": blob_ref,
        "blob_sha256": blob_sha256,
        "summary": "captured",
    }
    record_ref, record_sha256 = persist_capture_metadata(tmp_path, record)
    ledger_record = {**record, "evidence_ref": record_ref, "evidence_sha256": record_sha256}
    append_capture_record(tmp_path, ledger_record)

    assert verify_capture_record_file(tmp_path, ledger_record) == (record_ref, record_sha256)
    assert find_capture_record_by_idempotency_key(
        tmp_path,
        plan_id="PLAN-20260806-001",
        key="capture:test",
    ) == ledger_record


def test_direct_capture_helpers_preserve_error_codes(tmp_path: Path) -> None:
    """The extracted capture helpers keep controller-facing validation codes."""
    try:
        validate_capture_args(
            Namespace(
                stdin=True,
                from_file="result.txt",
                kind="command-output",
                summary="summary",
                idempotency_key=None,
                task=None,
            )
        )
    except ValueError as exc:
        assert str(exc) == "EVIDENCE_CAPTURE_SOURCE_CONFLICT"
    else:
        raise AssertionError("conflicting capture sources were accepted")

    too_large = b"x" * (1024 * 1024 + 1)
    try:
        redact_capture_bytes(too_large)
    except ValueError as exc:
        assert str(exc) == "EVIDENCE_CAPTURE_TOO_LARGE"
    else:
        raise AssertionError("oversized capture bytes were accepted")

    invalid_record = {
        "evidence_ref": "evidence:.work-governance/evidence/records/not-a-sha.json",
        "evidence_sha256": "not-a-sha",
    }
    try:
        verify_capture_record_file(tmp_path, invalid_record)
    except ValueError as exc:
        assert str(exc) == "EVIDENCE_CAPTURE_RECORD_INVALID"
    else:
        raise AssertionError("invalid capture record was accepted")


def test_direct_capture_redacts_binary_and_text_sources() -> None:
    """Direct evidence capture redacts obvious secrets and avoids raw binary persistence."""
    text, text_source = redact_capture_bytes(b"Authorization: Bearer abc.def\nsecret=value\n")
    assert text_source is True
    assert b"[REDACTED]" in text
    assert b"abc.def" not in text
    assert b"secret=[REDACTED]" in text

    binary, binary_source = redact_capture_bytes(b"\xff\x00")
    assert binary_source is False
    payload = json.loads(binary)
    assert payload["kind"] == "work-governance-binary-evidence-placeholder"
    assert payload["source_size"] == 2


def test_persist_direct_evidence_bytes_replays_idempotently(tmp_path: Path) -> None:
    """Workflow direct evidence persistence replays matching idempotency keys."""
    first = persist_direct_evidence_bytes(
        tmp_path,
        plan_id="PLAN-20260806-001",
        task_id="T-001",
        kind="command-output",
        summary="pytest token=summary-secret",
        raw_content=b"ok\nAuthorization: Bearer output-secret\n",
        source_type="stdin",
        source_ref=None,
        idempotency_key="workflow:test",
    )
    replayed = persist_direct_evidence_bytes(
        tmp_path,
        plan_id="PLAN-20260806-001",
        task_id="T-001",
        kind="command-output",
        summary="pytest token=summary-secret",
        raw_content=b"ok\nAuthorization: Bearer output-secret\n",
        source_type="stdin",
        source_ref=None,
        idempotency_key="workflow:test",
    )

    assert first["idempotent"] is False
    assert replayed["idempotent"] is True
    assert replayed["id"] == first["id"]
    assert first["summary"] == "pytest token=[REDACTED]"
    assert first["task_ref"] == "task:T-001"
    assert first["validator"] == "workctl:workflow"
    ledger = tmp_path / ".work-governance" / "evidence" / "ledger.ndjson"
    assert "summary-secret" not in ledger.read_text(encoding="utf-8")
    assert "output-secret" not in ledger.read_text(encoding="utf-8")


def test_persist_direct_evidence_bytes_preserves_conflict_code(tmp_path: Path) -> None:
    """Workflow direct evidence persistence keeps the idempotency conflict code."""
    persist_direct_evidence_bytes(
        tmp_path,
        plan_id="PLAN-20260806-001",
        task_id="T-001",
        kind="command-output",
        summary="same",
        raw_content=b"first\n",
        source_type="stdin",
        source_ref=None,
        idempotency_key="workflow:test",
    )
    try:
        persist_direct_evidence_bytes(
            tmp_path,
            plan_id="PLAN-20260806-001",
            task_id="T-001",
            kind="command-output",
            summary="same",
            raw_content=b"changed\n",
            source_type="stdin",
            source_ref=None,
            idempotency_key="workflow:test",
        )
    except ValueError as exc:
        assert str(exc) == "EVIDENCE_CAPTURE_IDEMPOTENCY_CONFLICT"
    else:
        raise AssertionError("conflicting idempotent evidence was accepted")


def test_workflow_evidence_payload_builds_plan_evidence_record() -> None:
    """Workflow evidence payload construction is testable without Plan writes."""
    payload = workflow_evidence_payload(
        plan_id="PLAN-20260806-001",
        subject="task:T-001",
        producer_ref="runtime:workflow",
        direct_record={
            "evidence_ref": "evidence:.work-governance/evidence/records/" + "a" * 64 + ".json",
            "evidence_sha256": "a" * 64,
        },
    )

    assert payload["schema_version"] == 1
    assert payload["kind"] == "work-governance-evidence"
    assert payload["plan_id"] == "PLAN-20260806-001"
    assert payload["subject"] == "task:T-001"
    assert payload["producer_ref"] == "runtime:workflow"
    assert payload["items"] == [
        {
            "ref": "evidence:.work-governance/evidence/records/" + "a" * 64 + ".json",
            "sha256": "a" * 64,
        }
    ]
    assert isinstance(payload["created_at"], str)


def test_workflow_evidence_payload_preserves_invalid_record_code() -> None:
    """Workflow evidence payload construction keeps the invalid direct-record code."""
    try:
        workflow_evidence_payload(
            plan_id="PLAN-20260806-001",
            subject="task:T-001",
            producer_ref="runtime:workflow",
            direct_record={"evidence_ref": "evidence:missing-sha"},
        )
    except ValueError as exc:
        assert str(exc) == "DIRECT_EVIDENCE_RECORD_INVALID"
    else:
        raise AssertionError("invalid direct evidence record was accepted")
