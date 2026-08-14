from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

authority_module = importlib.import_module("workctl_modules.authority")
candidate_to_dict = authority_module.candidate_to_dict
parse_candidate_specs = authority_module.parse_candidate_specs
plan_sources_module = importlib.import_module("workctl_modules.plan_sources")
discover_plan_sources = plan_sources_module.discover_plan_sources
PlanSourceError = plan_sources_module.PlanSourceError


@dataclass(frozen=True)
class CandidateFixture:
    """Minimal authority candidate fixture for module-level projection tests."""

    path: str
    classification: str
    origin: str
    signals: list[str]
    sha256: str
    plan_id: str | None = None
    revision: int | None = None
    status: str | None = None


def test_candidate_to_dict_preserves_stable_json_projection() -> None:
    """Authority candidate projection keeps the controller's public JSON fields."""
    candidate = CandidateFixture(
        path=".work-governance/_Plan/PLAN-20260806-001.md",
        classification="CONFIRMED_AUTHORITY",
        origin="index",
        signals=["index-active", "schema-v5"],
        sha256="a" * 64,
        plan_id="PLAN-20260806-001",
        revision=7,
        status="active",
    )

    assert candidate_to_dict(candidate) == {
        "path": ".work-governance/_Plan/PLAN-20260806-001.md",
        "classification": "CONFIRMED_AUTHORITY",
        "origin": "index",
        "signals": ["index-active", "schema-v5"],
        "sha256": "a" * 64,
        "plan_id": "PLAN-20260806-001",
        "revision": 7,
        "status": "active",
    }


def test_parse_candidate_specs_accepts_repeatable_path_classifications() -> None:
    """Candidate parsing accepts idempotent repeats and keeps the last path map."""
    classifications = {"CONFIRMED_AUTHORITY", "LIKELY_AUTHORITY", "NON_AUTHORITY"}

    assert parse_candidate_specs(
        [
            "docs/Plan.md=NON_AUTHORITY",
            "docs/Plan.md=NON_AUTHORITY",
            ".work-governance/_Plan/current.md=CONFIRMED_AUTHORITY",
        ],
        classifications,
    ) == {
        "docs/Plan.md": "NON_AUTHORITY",
        ".work-governance/_Plan/current.md": "CONFIRMED_AUTHORITY",
    }


def test_parse_candidate_specs_preserves_controller_error_codes() -> None:
    """Candidate parsing keeps the controller-facing error code strings."""
    classifications = {"CONFIRMED_AUTHORITY", "LIKELY_AUTHORITY", "NON_AUTHORITY"}

    cases = [
        (
            ["docs/Plan.md"],
            "INVALID_CANDIDATE: expected PATH=CLASSIFICATION",
        ),
        (
            ["docs/Plan.md=bad"],
            "INVALID_AUTHORITY_CLASSIFICATION: bad",
        ),
        (
            ["docs/Plan.md=NON_AUTHORITY", "docs/Plan.md=LIKELY_AUTHORITY"],
            "CONFLICTING_CANDIDATE_CLASSIFICATION: docs/Plan.md",
        ),
    ]
    for values, expected in cases:
        try:
            parse_candidate_specs(values, classifications)
        except ValueError as exc:
            assert str(exc) == expected
        else:
            raise AssertionError(f"invalid candidate spec was accepted: {values}")


def test_plan_source_index_marks_conventional_plan_as_history_visible(
    tmp_path: Path,
) -> None:
    """Shared source discovery keeps conventional Plans visible but non-authoritative."""
    docs_plan = tmp_path / "docs" / "Plan.md"
    docs_plan.parent.mkdir()
    docs_plan.write_text(
        "# Historical Plan\n\n"
        "Goal: keep prior work visible without granting execution authority.\n",
        encoding="utf-8",
    )

    source = next(item for item in discover_plan_sources(tmp_path) if item.path == "docs/Plan.md")

    assert source.classification == "NON_AUTHORITY"
    assert source.origin == "conventional-path"
    assert source.reason == "historical_conventional_plan_ignored"
    assert source.history_visible is True


def test_plan_source_index_rejects_conflicting_samefile_explicit_candidates(
    tmp_path: Path,
) -> None:
    """Explicit candidate classification conflicts stay physical-file based."""
    docs_plan = tmp_path / "docs" / "Plan.md"
    docs_plan.parent.mkdir()
    docs_plan.write_text("# Candidate\n", encoding="utf-8")
    alias = tmp_path / "docs" / "alias.md"
    alias.symlink_to(docs_plan.name)

    try:
        discover_plan_sources(
            tmp_path,
            explicit_candidates=[
                ("docs/Plan.md", "NON_AUTHORITY"),
                ("docs/alias.md", "LIKELY_AUTHORITY"),
            ],
        )
    except PlanSourceError as exc:
        assert str(exc) == "CONFLICTING_CANDIDATE_CLASSIFICATION: docs/Plan.md"
    else:
        raise AssertionError("conflicting samefile candidate classifications were accepted")
