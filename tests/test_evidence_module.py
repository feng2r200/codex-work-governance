from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

evidence_module = importlib.import_module("workctl_modules.evidence")
validate_evidence_payload = evidence_module.validate_evidence_payload


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
