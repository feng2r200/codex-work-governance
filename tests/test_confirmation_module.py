from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

confirmation_module = importlib.import_module("workctl_modules.confirmation")
accepted_confirmation = confirmation_module.accepted_confirmation
confirmation_from_manifest = confirmation_module.confirmation_from_manifest
manifest_input_path = confirmation_module.manifest_input_path


def test_manifest_input_path_resolves_relative_to_manifest(tmp_path: Path) -> None:
    """Manifest input paths resolve relative to the manifest directory."""
    manifest = tmp_path / "inputs" / "manifest.json"
    expected = tmp_path / "inputs" / "prepared.md"

    assert manifest_input_path(manifest, "prepared.md") == expected.resolve()


def test_confirmation_from_manifest_accepts_required_and_optional_entries() -> None:
    """Confirmation manifest parsing returns the canonical tuple and optional None."""
    confirmations = {
        "baseline": {
            "id": "C-MIGRATION-BASELINE",
            "ref": "user:session/turn",
            "accepted_at": "2026-08-07T00:00:00Z",
            "evidence_sha256": "a" * 64,
        }
    }

    assert confirmation_from_manifest(confirmations, "optional", required=False) is None
    assert confirmation_from_manifest(confirmations, "baseline", required=True) == (
        "C-MIGRATION-BASELINE",
        "user:session/turn",
        "2026-08-07T00:00:00Z",
        "a" * 64,
    )


def test_confirmation_from_manifest_preserves_error_codes() -> None:
    """Confirmation manifest parsing raises controller-facing error codes."""
    try:
        confirmation_from_manifest(
            {"baseline": {"id": "not-confirmation"}},
            "baseline",
            required=True,
        )
    except ValueError as exc:
        assert str(exc) == "INVALID_MANIFEST_CONFIRMATION_ID: baseline"
    else:
        raise AssertionError("invalid confirmation id was accepted")


def test_accepted_confirmation_builds_accepted_and_pending_entries() -> None:
    """Accepted confirmation entries keep the intervention basis shape."""
    accepted = accepted_confirmation(
        "C-MIGRATION-BASELINE",
        "user:session/turn",
        "2026-08-07T00:00:00Z",
        "b" * 64,
        "Confirm migration baseline.",
    )
    pending = accepted_confirmation(
        "C-MIGRATION-BASELINE",
        "PENDING",
        "2026-08-07T00:00:00Z",
        "b" * 64,
        "Confirm migration baseline.",
        intervention_kind="retirement",
    )

    assert accepted["status"] == "accepted"
    assert accepted["ref"] == "user:session/turn"
    assert accepted["intervention"]["basis_sha256"] == "b" * 64
    assert pending["status"] == "pending"
    assert "ref" not in pending
    assert pending["intervention"]["kind"] == "retirement"
