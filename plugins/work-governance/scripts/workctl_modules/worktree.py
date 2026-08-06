"""Non-authoritative worktree ledger helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast


class WorktreeLedgerError(ValueError):
    """Raised when a worktree ledger payload or reference is invalid."""


def worktree_ledger_path(
    runtime_root: Path,
    worktree_id: str,
    id_pattern: re.Pattern[str],
) -> Path:
    """Return the runtime ledger path for one non-authoritative worktree run."""
    if id_pattern.fullmatch(worktree_id) is None:
        raise WorktreeLedgerError("WORKTREE_ID_INVALID")
    return runtime_root / "worktrees" / f"{worktree_id}.json"


def load_worktree_ledger(path: Path, worktree_id: str) -> dict[str, Any]:
    """Load and validate one non-authoritative worktree ledger."""
    if path.is_symlink() or not path.is_file():
        raise WorktreeLedgerError("WORKTREE_LEDGER_MISSING")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorktreeLedgerError("WORKTREE_LEDGER_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("kind") != "work-governance-worktree-ledger"
        or payload.get("authority") != "NON_AUTHORITY"
        or payload.get("worktree_id") != worktree_id
        or not isinstance(payload.get("events"), list)
    ):
        raise WorktreeLedgerError("WORKTREE_LEDGER_INVALID")
    return cast(dict[str, Any], payload)


def encode_worktree_ledger(payload: Mapping[str, Any]) -> str:
    """Encode one worktree ledger for deterministic atomic writes."""
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_worktree_event(
    *,
    event: str,
    summary: str,
    recorded_at: str,
    evidence_ref: str | None,
    evidence_sha256: str | None,
    valid_reference: Callable[[str], bool],
    sha256_pattern: re.Pattern[str],
) -> dict[str, Any]:
    """Build one bounded ledger event and validate optional evidence pointers."""
    payload: dict[str, Any] = {
        "event": event,
        "summary": summary,
        "recorded_at": recorded_at,
    }
    if evidence_ref is not None:
        if not valid_reference(evidence_ref):
            raise WorktreeLedgerError("WORKTREE_EVIDENCE_REF_INVALID")
        payload["evidence_ref"] = evidence_ref
    if evidence_sha256 is not None:
        if sha256_pattern.fullmatch(evidence_sha256) is None:
            raise WorktreeLedgerError("WORKTREE_EVIDENCE_SHA256_INVALID")
        payload["evidence_sha256"] = evidence_sha256
    return payload


def open_worktree_ledger(
    *,
    worktree_id: str,
    path: str,
    branch: str,
    summary: str,
    opened_at: str,
) -> dict[str, Any]:
    """Create the initial non-authoritative ledger payload."""
    return {
        "schema_version": 1,
        "kind": "work-governance-worktree-ledger",
        "authority": "NON_AUTHORITY",
        "worktree_id": worktree_id,
        "status": "open",
        "path": path,
        "branch": branch,
        "summary": summary,
        "opened_at": opened_at,
        "updated_at": opened_at,
        "events": [
            {
                "sequence": 1,
                "event": "begin",
                "summary": summary,
                "recorded_at": opened_at,
            }
        ],
    }


def append_worktree_event(
    ledger: dict[str, Any],
    event: Mapping[str, Any],
) -> int:
    """Append one event to an open worktree ledger and return the event count."""
    if ledger.get("status") == "closed":
        raise WorktreeLedgerError("WORKTREE_LEDGER_CLOSED")
    events = cast(list[Any], ledger["events"])
    payload = dict(event)
    payload["sequence"] = len(events) + 1
    events.append(payload)
    return len(events)


def close_worktree_ledger(
    ledger: dict[str, Any],
    event: Mapping[str, Any],
    *,
    summary: str,
    closed_at: str,
) -> dict[str, Any]:
    """Close one worktree ledger and return its non-authoritative summary."""
    if ledger.get("status") == "closed":
        raise WorktreeLedgerError("WORKTREE_LEDGER_ALREADY_CLOSED")
    event_count = append_worktree_event(ledger, event)
    ledger["status"] = "closed"
    ledger["updated_at"] = closed_at
    ledger["closed_at"] = closed_at
    close_summary = {
        "summary": summary,
        "authority": "NON_AUTHORITY",
        "event_count": event_count,
    }
    ledger["close_summary"] = close_summary
    return close_summary
