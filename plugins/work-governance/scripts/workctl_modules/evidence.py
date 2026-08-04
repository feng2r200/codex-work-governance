"""Bounded evidence parsing and canonical encoding."""

from __future__ import annotations

import json
from collections.abc import Mapping

import yaml

from .storage import canonical_json_bytes


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
