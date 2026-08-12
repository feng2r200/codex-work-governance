"""Pure helpers for Plan-authority candidate inputs and output projections."""

from __future__ import annotations

from collections.abc import Container, Iterable
from typing import Protocol


class AuthorityCandidateView(Protocol):
    """Minimal read-only shape required for authority candidate projection."""

    path: str
    classification: str
    origin: str
    signals: list[str]
    sha256: str
    plan_id: str | None
    revision: int | None
    status: str | None


def candidate_to_dict(candidate: AuthorityCandidateView) -> dict[str, object]:
    """Convert a candidate into stable JSON output."""
    return {
        "path": candidate.path,
        "classification": candidate.classification,
        "origin": candidate.origin,
        "signals": candidate.signals,
        "sha256": candidate.sha256,
        "plan_id": candidate.plan_id,
        "revision": candidate.revision,
        "status": candidate.status,
    }


def parse_candidate_specs(
    values: Iterable[str],
    classifications: Container[str],
) -> dict[str, str]:
    """Parse repeatable ``PATH=CLASSIFICATION`` semantic inputs."""
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("INVALID_CANDIDATE: expected PATH=CLASSIFICATION")
        path, classification = value.rsplit("=", 1)
        if classification not in classifications:
            raise ValueError(f"INVALID_AUTHORITY_CLASSIFICATION: {classification}")
        if path in result and result[path] != classification:
            raise ValueError(f"CONFLICTING_CANDIDATE_CLASSIFICATION: {path}")
        result[path] = classification
    return result
