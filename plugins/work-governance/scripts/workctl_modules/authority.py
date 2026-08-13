"""Pure helpers for Plan-authority candidate inputs and output projections."""

from __future__ import annotations

from collections.abc import Container, Iterable
from typing import Protocol


class AuthorityCandidateView(Protocol):
    """Minimal read-only shape required for authority candidate projection."""

    @property
    def path(self) -> str:
        """Project-local candidate path."""
        ...

    @property
    def classification(self) -> str:
        """Candidate semantic class."""
        ...

    @property
    def origin(self) -> str:
        """Discovery origin."""
        ...

    @property
    def signals(self) -> list[str]:
        """Authority signals that led to classification."""
        ...

    @property
    def sha256(self) -> str:
        """Candidate content digest."""
        ...

    @property
    def plan_id(self) -> str | None:
        """Plan ID parsed from the candidate, if any."""
        ...

    @property
    def revision(self) -> int | None:
        """Plan revision parsed from the candidate, if any."""
        ...

    @property
    def status(self) -> str | None:
        """Plan status parsed from the candidate, if any."""
        ...


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
