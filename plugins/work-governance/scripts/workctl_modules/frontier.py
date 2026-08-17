"""Decision-frontier drafting for lightweight requirement clarification."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from workctl_modules.filesystem import sha256_bytes

FRONTIER_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
DEFAULT_FRONTIER_TARGETS = ("route",)


class FrontierError(ValueError):
    """Raised when a decision-frontier manifest is invalid."""


def canonical_frontier_bytes(payload: Mapping[str, object]) -> bytes:
    """Return stable bytes for one frontier payload digest."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def optional_string(value: object, *, field: str) -> str | None:
    """Normalize an optional non-empty string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise FrontierError(f"FRONTIER_{field}_INVALID")
    stripped = value.strip()
    if not stripped:
        raise FrontierError(f"FRONTIER_{field}_EMPTY")
    return stripped


def required_string(value: object, *, field: str) -> str:
    """Normalize a required non-empty string."""
    result = optional_string(value, field=field)
    if result is None:
        raise FrontierError(f"FRONTIER_{field}_REQUIRED")
    return result


def string_list(value: object, *, field: str, default: tuple[str, ...] = ()) -> list[str]:
    """Normalize a list of non-empty strings."""
    if value is None:
        return list(default)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise FrontierError(f"FRONTIER_{field}_EMPTY")
        return [stripped]
    if not isinstance(value, list):
        raise FrontierError(f"FRONTIER_{field}_INVALID")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise FrontierError(f"FRONTIER_{field}_{index}_INVALID")
        result.append(item.strip())
    return result


def mapping_list(value: object, *, field: str) -> list[Mapping[str, object]]:
    """Normalize a list of mapping entries."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise FrontierError(f"FRONTIER_{field}_INVALID")
    result: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise FrontierError(f"FRONTIER_{field}_{index}_INVALID")
        result.append(item)
    return result


def frontier_entries(manifest: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return user-owned decision entries from supported manifest fields."""
    entries: list[Mapping[str, object]] = []
    for field in ("questions", "decisions", "choices"):
        entries.extend(mapping_list(manifest.get(field), field=field.upper()))
    return entries


def normalize_frontier_id(value: object, *, fallback: str) -> str:
    """Return a stable decision ID."""
    candidate = optional_string(value, field="QUESTION_ID") or fallback
    if FRONTIER_ID_RE.fullmatch(candidate) is None:
        raise FrontierError(f"FRONTIER_QUESTION_ID_INVALID: {candidate}")
    return candidate


def normalize_question(
    entry: Mapping[str, object],
    *,
    index: int,
    default_targets: list[str],
) -> dict[str, object]:
    """Normalize one user-owned frontier decision."""
    owner = optional_string(entry.get("owner"), field="QUESTION_OWNER") or "user"
    if owner != "user":
        raise FrontierError("FRONTIER_QUESTION_OWNER_MUST_BE_USER")
    blocks = string_list(
        entry.get("blocks"),
        field="QUESTION_BLOCKS",
        default=tuple(default_targets),
    )
    if not blocks:
        raise FrontierError("FRONTIER_QUESTION_BLOCKS_REQUIRED")
    payload: dict[str, object] = {
        "id": normalize_frontier_id(entry.get("id"), fallback=f"D-{index:03d}"),
        "owner": "user",
        "question": required_string(entry.get("question"), field="QUESTION"),
        "recommended_answer": required_string(
            entry.get("recommended_answer"),
            field="RECOMMENDED_ANSWER",
        ),
        "reason": required_string(entry.get("reason"), field="QUESTION_REASON"),
        "blocks": blocks,
    }
    source_ref = optional_string(entry.get("source_ref"), field="QUESTION_SOURCE_REF")
    if source_ref is not None:
        payload["source_ref"] = source_ref
    return payload


def normalize_fact(entry: Mapping[str, object], *, field: str) -> dict[str, object]:
    """Normalize one agent-owned finding or unresolved probe."""
    payload: dict[str, object] = {
        "summary": required_string(entry.get("summary"), field=f"{field}_SUMMARY")
    }
    for key in ("source_ref", "sha256", "next_probe"):
        value = optional_string(entry.get(key), field=f"{field}_{key.upper()}")
        if value is not None:
            payload[key] = value
    return payload


def normalize_facts(manifest: Mapping[str, object]) -> list[dict[str, object]]:
    """Return already-discovered agent-owned facts."""
    entries = [
        *mapping_list(manifest.get("facts"), field="FACTS"),
        *mapping_list(manifest.get("findings"), field="FINDINGS"),
    ]
    return [normalize_fact(entry, field="FACT") for entry in entries]


def normalize_agent_unknowns(manifest: Mapping[str, object]) -> list[dict[str, object]]:
    """Return agent-owned unknowns that should be explored before asking users."""
    entries = [
        *mapping_list(manifest.get("agent_owned"), field="AGENT_OWNED"),
        *mapping_list(manifest.get("agent_unknowns"), field="AGENT_UNKNOWNS"),
    ]
    return [normalize_fact(entry, field="AGENT_UNKNOWN") for entry in entries]


def build_frontier_draft(
    manifest: Mapping[str, object],
    *,
    manifest_sha256: str,
) -> dict[str, object]:
    """Build a deterministic read-only decision-frontier draft."""
    goal_anchor = required_string(manifest.get("goal_anchor"), field="GOAL_ANCHOR")
    target_refs = string_list(
        manifest.get("blocked_targets", manifest.get("target_ref")),
        field="BLOCKED_TARGETS",
        default=DEFAULT_FRONTIER_TARGETS,
    )
    questions = [
        normalize_question(entry, index=index, default_targets=target_refs)
        for index, entry in enumerate(frontier_entries(manifest), start=1)
    ]
    facts = normalize_facts(manifest)
    agent_owned = normalize_agent_unknowns(manifest)
    if not questions and not agent_owned:
        raise FrontierError("FRONTIER_EMPTY")
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-decision-frontier",
        "status": "FRONTIER_DRAFTED",
        "goal_anchor": goal_anchor,
        "blocked_targets": target_refs,
        "manifest_sha256": manifest_sha256,
        "facts": facts,
        "agent_owned_unknowns": agent_owned,
        "questions": questions,
        "user_intervention": "required" if questions else "not_required",
        "next_action": (
            "Ask the first listed user-owned question with its recommended answer."
            if questions
            else "Explore the listed agent-owned unknowns before asking the user."
        ),
    }
    summary = optional_string(manifest.get("summary"), field="SUMMARY")
    if summary is not None:
        payload["summary"] = summary
    payload["frontier_sha256"] = sha256_bytes(canonical_frontier_bytes(payload))
    return payload
