"""Pure confirmation manifest helpers used by controller transactions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def manifest_input_path(manifest_path: Path, raw_path: str) -> Path:
    """Resolve a read-only manifest input relative to the manifest directory."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def confirmation_from_manifest(
    confirmations_value: Mapping[str, object],
    key: str,
    *,
    required: bool,
) -> tuple[str, str, str, str] | None:
    """Read one accepted confirmation reference from a transaction manifest."""
    raw = confirmations_value.get(key)
    if raw is None and not required:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"MANIFEST_CONFIRMATION_REQUIRED: {key}")
    confirmation_id = raw.get("id")
    ref = raw.get("ref")
    accepted_at = raw.get("accepted_at")
    evidence_sha256 = raw.get("evidence_sha256")
    if not isinstance(confirmation_id, str) or not confirmation_id.startswith("C-"):
        raise ValueError(f"INVALID_MANIFEST_CONFIRMATION_ID: {key}")
    if not isinstance(ref, str) or not ref:
        raise ValueError(f"MANIFEST_CONFIRMATION_REF_REQUIRED: {key}")
    if not isinstance(accepted_at, str) or not accepted_at:
        raise ValueError(f"MANIFEST_CONFIRMATION_ACCEPTED_AT_REQUIRED: {key}")
    if not isinstance(evidence_sha256, str) or SHA256_RE.fullmatch(evidence_sha256) is None:
        raise ValueError(f"MANIFEST_CONFIRMATION_EVIDENCE_REQUIRED: {key}")
    return confirmation_id, ref, accepted_at, evidence_sha256


def accepted_confirmation(
    confirmation_id: str,
    ref: str,
    accepted_at: str,
    evidence_sha256: str,
    description: str,
    *,
    intervention_kind: str = "plan_contract",
) -> dict[str, object]:
    """Build a confirmed or dry-run-pending entry for the canonical Plan."""
    intervention = {
        "kind": intervention_kind,
        "blocks": ["route"],
        "basis_ref": f"project:confirmation-basis/{evidence_sha256}",
        "basis_sha256": evidence_sha256,
    }
    if ref == "PENDING":
        return {
            "id": confirmation_id,
            "description": description,
            "status": "pending",
            "evidence_sha256": evidence_sha256,
            "intervention": intervention,
        }
    return {
        "id": confirmation_id,
        "description": description,
        "status": "accepted",
        "ref": ref,
        "accepted_at": accepted_at,
        "evidence_sha256": evidence_sha256,
        "intervention": intervention,
    }
