"""High-level workflow contract parsing helpers."""

from __future__ import annotations

import json

import workctl_modules.yaml_compat as yaml


class WorkflowContractError(ValueError):
    """Raised when a high-level workflow contract is malformed."""


def parse_workflow_mapping(content: bytes, *, error_prefix: str) -> dict[object, object]:
    """Parse a bounded JSON/YAML workflow mapping."""
    try:
        payload: object = json.loads(content)
    except json.JSONDecodeError:
        try:
            payload = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise WorkflowContractError(f"{error_prefix}_INVALID") from exc
    if not isinstance(payload, dict):
        raise WorkflowContractError(f"{error_prefix}_MUST_BE_MAPPING")
    return payload


def non_empty_string(value: object, *, field: str) -> str:
    """Return a non-empty string field or raise a workflow contract error."""
    if not isinstance(value, str) or not value.strip():
        raise WorkflowContractError(f"{field}_REQUIRED")
    return value.strip()


def workflow_string_list(value: object, *, field: str) -> list[str]:
    """Validate one non-empty list of strings for high-level contracts."""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise WorkflowContractError(f"{field}_REQUIRES_NON_EMPTY_STRING_LIST")
    return [str(item).strip() for item in value]
