"""Pure storage encodings used by the controller and runtime snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TypeVar

JsonMapping = TypeVar("JsonMapping", bound=Mapping[str, object])


def canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    """Encode one mapping deterministically for hashing and atomic storage."""
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def canonical_event_bytes(payload: Mapping[str, object]) -> bytes:
    """Encode one append-only event with a single trailing newline."""
    return canonical_json_bytes(payload)


def redacted_copy(value: Any) -> Any:
    """Redact common credential-bearing mapping keys without changing structure."""
    sensitive = ("api_key", "apikey", "authorization", "password", "secret", "token")
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(part in key.lower() for part in sensitive)
            else redacted_copy(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redacted_copy(item) for item in value]
    if isinstance(value, str):
        redacted = value
        if "Bearer " in redacted:
            redacted = redacted.split("Bearer ", 1)[0] + "Bearer [REDACTED]"
        for prefix in ("sk-", "AKIA"):
            if prefix in redacted:
                start = redacted.index(prefix)
                redacted = redacted[:start] + prefix + "[REDACTED]"
        return redacted
    return value
