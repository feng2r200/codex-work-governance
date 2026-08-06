"""Read-only historical Plan inspection helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import workctl_modules.yaml_compat as yaml


class PlanHistoryError(ValueError):
    """Raised when a history request cannot select a target Plan."""


def _status_counts(values: object, *, default_status: str) -> dict[str, int]:
    """Count status values in a loose legacy list."""
    counts: dict[str, int] = {}
    for item in values if isinstance(values, list) else []:
        status = item.get("status", default_status) if isinstance(item, dict) else "invalid"
        status_name = str(status)
        counts[status_name] = counts.get(status_name, 0) + 1
    return counts


def _confirmation_counts(raw_confirmations: object) -> dict[str, int]:
    """Count confirmation statuses in loose legacy confirmation groups."""
    counts: dict[str, int] = {}
    if not isinstance(raw_confirmations, dict):
        return counts
    for group in ("required", "accepted"):
        values = raw_confirmations.get(group, [])
        for item in values if isinstance(values, list) else []:
            status = item.get("status", group) if isinstance(item, dict) else "invalid"
            status_name = str(status)
            counts[status_name] = counts.get(status_name, 0) + 1
    return counts


def tolerant_plan_history_summary(
    *,
    path: Path,
    relative_path: str,
    file_sha256: str,
    body_sha256: Callable[[bytes], str],
) -> dict[str, object]:
    """Read historical Plan metadata without enforcing the active schema."""
    summary: dict[str, object] = {
        "path": relative_path,
        "sha256": file_sha256,
        "parse_state": "ok",
        "plan_id": None,
        "title": None,
        "status": None,
        "schema_version": None,
        "task_counts": {},
        "confirmation_counts": {},
    }
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise PlanHistoryError("frontmatter missing")
        _, raw_frontmatter, body = text.split("---\n", 2)
        frontmatter = yaml.safe_load(raw_frontmatter)
        if not isinstance(frontmatter, dict):
            raise PlanHistoryError("frontmatter must be a mapping")
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError, PlanHistoryError) as exc:
        summary["parse_state"] = "error"
        summary["error"] = str(exc)
        return summary
    frontmatter_map: Mapping[object, object] = frontmatter
    summary.update(
        {
            "plan_id": frontmatter_map.get("plan_id"),
            "title": frontmatter_map.get("title"),
            "status": frontmatter_map.get("status"),
            "schema_version": frontmatter_map.get("schema_version"),
            "body_sha256": body_sha256(body.encode("utf-8")),
        }
    )
    summary["task_counts"] = _status_counts(
        frontmatter_map.get("tasks", []),
        default_status="contract-only",
    )
    summary["confirmation_counts"] = _confirmation_counts(frontmatter_map.get("confirmations", {}))
    return summary


def find_plan_history_target(
    summaries: Sequence[Mapping[str, object]],
    plan_id: str,
) -> Mapping[str, object] | None:
    """Return the first history summary matching a Plan ID or filename stem."""
    for item in summaries:
        path_plan_id = Path(str(item.get("path"))).stem
        if item.get("plan_id") == plan_id or path_plan_id == plan_id:
            return item
    return None
