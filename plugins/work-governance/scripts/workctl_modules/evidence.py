"""Bounded evidence parsing and canonical encoding."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping

from . import yaml_compat as yaml
from .storage import canonical_json_bytes

EVIDENCE_SUBJECT_RE = re.compile(
    r"(?:[a-z][a-z0-9-]*:[A-Za-z0-9._-]+|closeout|delivery|"
    r"activation|plan-validation|contract-upgrade)"
)


def parse_evidence_bytes(content: bytes, max_bytes: int) -> dict[str, object]:
    """Parse one bounded JSON or YAML evidence mapping."""
    if len(content) > max_bytes:
        raise ValueError("EVIDENCE_MANIFEST_TOO_LARGE")
    try:
        payload: object = json.loads(content)
    except json.JSONDecodeError:
        payload = yaml.safe_load(content)
    if not isinstance(payload, dict):
        raise ValueError("EVIDENCE_MANIFEST_INVALID")
    return payload


def canonical_evidence_bytes(payload: Mapping[str, object]) -> bytes:
    """Return deterministic content-addressed evidence bytes."""
    return canonical_json_bytes(payload)


def validate_evidence_payload(
    payload: Mapping[str, object],
    *,
    expected_plan_id: str,
    expected_subject: str | None,
    valid_reference: Callable[[object], bool],
    sha256_pattern: re.Pattern[str],
    max_items: int,
) -> None:
    """Validate bounded evidence metadata without accepting process output blobs."""
    subject = payload.get("subject")
    required_fields = {
        "schema_version",
        "kind",
        "plan_id",
        "subject",
        "created_at",
        "producer_ref",
        "items",
    }
    if subject == "activation":
        required_fields.add("observed_ref")
    if set(payload) != required_fields:
        raise ValueError("INVALID_EVIDENCE_MANIFEST_FIELDS")
    if payload.get("schema_version") != 1 or payload.get("kind") != "work-governance-evidence":
        raise ValueError("INVALID_EVIDENCE_MANIFEST_SCHEMA")
    if payload.get("plan_id") != expected_plan_id:
        raise ValueError("EVIDENCE_MANIFEST_PLAN_MISMATCH")
    if not isinstance(subject, str) or EVIDENCE_SUBJECT_RE.fullmatch(subject) is None:
        raise ValueError("INVALID_EVIDENCE_MANIFEST_SUBJECT")
    if expected_subject is not None and subject != expected_subject:
        raise ValueError(
            f"EVIDENCE_MANIFEST_SUBJECT_MISMATCH: expected {expected_subject}, found {subject}"
        )
    if not isinstance(payload.get("created_at"), str) or not payload.get("created_at"):
        raise ValueError("INVALID_EVIDENCE_MANIFEST_CREATED_AT")
    if not valid_reference(payload.get("producer_ref")):
        raise ValueError("INVALID_EVIDENCE_MANIFEST_PRODUCER")
    if subject == "activation":
        observed_ref = payload.get("observed_ref")
        if (
            not isinstance(observed_ref, str)
            or not observed_ref
            or observed_ref != observed_ref.strip()
            or any(character.isspace() for character in observed_ref)
        ):
            raise ValueError("INVALID_ACTIVATION_EVIDENCE_OBSERVED_REF")
    items = payload.get("items")
    if not isinstance(items, list) or not items or len(items) > max_items:
        raise ValueError("INVALID_EVIDENCE_MANIFEST_ITEMS")
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"ref", "sha256"}
            or not valid_reference(item.get("ref"))
            or not isinstance(item.get("sha256"), str)
            or sha256_pattern.fullmatch(item["sha256"]) is None
        ):
            raise ValueError("INVALID_EVIDENCE_MANIFEST_ITEM")
