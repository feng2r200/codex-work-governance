"""Regression checks for the temporary Codex effect evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "work_governance_1_1_0_codex_effect_eval.json"
REPORT = REPO_ROOT / "docs" / "WORK_GOVERNANCE_1_1_0_CODEX_EFFECT_EVAL.md"

REQUIRED_SCENARIOS = {
    "CE-001",
    "CE-002",
    "CE-003",
    "CE-004",
    "CE-005",
    "CE-006",
    "CE-007",
    "CE-008",
    "CE-009",
    "CE-010",
    "CE-011",
    "CE-012",
}
REQUIRED_METRICS = {
    "plan_contract_churn",
    "temporary_evidence_dependency",
    "ready_task_progress",
    "repeated_user_confirmation_prompts",
    "reviewer_retry_loop",
    "help_first_usability",
    "overclaim_prevention",
    "activation_boundary",
}
ALLOWED_RESULTS = {"passed", "degraded", "blocked_as_designed"}
ALLOWED_EVIDENCE_GRADES = {
    "real_codex_live",
    "real_codex_candidate_degraded",
    "real_hook_candidate",
    "controller_replay",
    "static_contract",
}
PRIVATE_TMP = "/private" + "/tmp"
FORBIDDEN_RECOMMENDATIONS = (
    f"write `{PRIVATE_TMP}/*.json` before calling `workctl`",
    f"write {PRIVATE_TMP}/*.json before calling workctl",
    "private " + "tmp manifest handoff is required",
    "fully implemented " + "target architecture",
    "complete target architecture " + "is implemented",
)
OVERCLAIM_PHRASE_FRAGMENTS = (
    ("1.1.0", " is activated"),
    ("1.1.0", " activated"),
    ("live plugin switched to ", "1.1.0"),
    ("live ", "1.1.0", " is verified"),
    ("target architecture ", "is complete"),
    ("target architecture ", "complete"),
    ("target architecture ", "fully implemented"),
    ("full bash-first crud surface ", "is implemented"),
    ("full bash-first crud surface ", "complete"),
    ("task add ", "is implemented"),
)


def as_mapping(value: object) -> Mapping[str, object]:
    """Return a JSON object as a string-keyed mapping."""
    assert isinstance(value, dict)
    return cast(Mapping[str, object], value)


def as_sequence(value: object) -> Sequence[object]:
    """Return a JSON array as a sequence of objects."""
    assert isinstance(value, list)
    return cast(Sequence[object], value)


def as_string(value: object) -> str:
    """Return a JSON scalar as a string."""
    assert isinstance(value, str)
    return value


def as_int(value: object) -> int:
    """Return a JSON scalar as an integer."""
    assert isinstance(value, int)
    return value


def sha256_text(value: str) -> str:
    """Return the SHA256 digest for one UTF-8 text value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_fixture() -> Mapping[str, object]:
    """Load the temporary Codex effect evaluation fixture."""
    payload: object = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return as_mapping(payload)


def test_codex_effect_fixture_covers_historical_friction() -> None:
    """The evaluation matrix covers every historically important friction class."""
    fixture = load_fixture()
    assert as_string(fixture["evaluation_id"]) == "WG-CODEX-EFFECT-EVAL-20260805"

    metrics = {as_string(metric) for metric in as_sequence(fixture["metrics"])}
    assert metrics >= REQUIRED_METRICS

    scenarios = [as_mapping(item) for item in as_sequence(fixture["scenarios"])]
    scenario_ids = {as_string(scenario["id"]) for scenario in scenarios}
    assert scenario_ids >= REQUIRED_SCENARIOS
    evidence_ids = {
        as_string(record["id"])
        for record in as_sequence(fixture["evidence_records"])
        if isinstance(record, dict)
    }

    covered_metrics: set[str] = set()
    for scenario in scenarios:
        assert as_string(scenario["result"]) in ALLOWED_RESULTS
        assert as_string(scenario["evidence_grade"]) in ALLOWED_EVIDENCE_GRADES
        assert as_string(scenario["command_or_evidence"])
        assert as_string(scenario["claim_boundary"])
        evidence_refs = {as_string(ref) for ref in as_sequence(scenario["evidence_refs"])}
        assert evidence_refs
        assert evidence_ids >= evidence_refs
        covered_metrics.update(as_mapping(scenario["metrics"]).keys())

    assert covered_metrics >= REQUIRED_METRICS


def test_codex_effect_fixture_binds_results_to_durable_evidence() -> None:
    """Each scenario result is backed by hashed redacted evidence records."""
    fixture = load_fixture()
    evidence_records = [
        as_mapping(record) for record in as_sequence(fixture["evidence_records"])
    ]
    evidence_by_id = {as_string(record["id"]): record for record in evidence_records}

    for record in evidence_records:
        assert as_string(record["evidence_grade"]) in ALLOWED_EVIDENCE_GRADES
        assert as_string(record["source_type"])
        assert as_string(record["command_summary"])
        assert as_int(record["exit_code"]) in {0, 1, 2}
        excerpt = as_string(record["output_excerpt"])
        assert excerpt
        assert as_string(record["output_excerpt_sha256"]) == sha256_text(excerpt)
        assert as_string(record["supports_result"]) in ALLOWED_RESULTS
        assert as_string(record["redaction_policy"])

    for scenario in [as_mapping(item) for item in as_sequence(fixture["scenarios"])]:
        scenario_result = as_string(scenario["result"])
        refs = [as_string(ref) for ref in as_sequence(scenario["evidence_refs"])]
        assert any(
            as_string(evidence_by_id[ref]["supports_result"]) == scenario_result
            for ref in refs
        )


def test_codex_effect_fixture_keeps_activation_boundary_explicit() -> None:
    """The fixture distinguishes candidate testing from live activation."""
    fixture = load_fixture()
    candidate = as_mapping(fixture["candidate"])
    boundaries = as_mapping(fixture["boundaries"])

    assert candidate["activation_status"] == "not_activated"
    assert candidate["live_plugin_observed"] == "1.0.7+codex.20260804122047"
    assert boundaries["activation_gate"] == "CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0"
    assert boundaries["live_plugin_unchanged"] is True
    assert boundaries["marketplace_or_cache_switch"] is False
    assert boundaries["push"] is False
    assert boundaries["auth_secret_copy"] is False

    scenarios = [as_mapping(item) for item in as_sequence(fixture["scenarios"])]
    degraded = {
        as_string(scenario["id"])
        for scenario in scenarios
        if as_string(scenario["result"]) == "degraded"
    }
    assert degraded == {"CE-003"}


def test_codex_effect_report_matches_fixture_and_avoids_overclaim() -> None:
    """The report cites every scenario without recommending temp evidence handoffs."""
    report = REPORT.read_text(encoding="utf-8")
    normalized = " ".join(report.split())

    assert "CONFIRM_ACTIVATE_WORK_GOVERNANCE_1_1_0" in report
    assert "does not prove live 1.1.0 behavior" in report
    assert "task add" in report
    assert "not an activation report" in normalized

    for scenario_id in REQUIRED_SCENARIOS:
        assert scenario_id in report

    lowered = report.lower()
    for forbidden in FORBIDDEN_RECOMMENDATIONS:
        assert forbidden not in lowered


def test_codex_effect_overclaim_scan_covers_release_surfaces() -> None:
    """Configured release surfaces contain no activation or draft-done overclaim."""
    fixture = load_fixture()
    scan = as_mapping(fixture["overclaim_scan"])
    forbidden_phrases = {"".join(parts) for parts in OVERCLAIM_PHRASE_FRAGMENTS}
    assert forbidden_phrases == {
        as_string(phrase) for phrase in as_sequence(scan["forbidden_phrases"])
    }

    scan_files: list[Path] = []
    for raw_target in as_sequence(scan["target_paths"]):
        target = REPO_ROOT / as_string(raw_target)
        if target.is_dir():
            scan_files.extend(sorted(path for path in target.rglob("*.md") if path.is_file()))
        else:
            assert target.is_file()
            scan_files.append(target)

    assert REPORT in scan_files
    assert FIXTURE in scan_files

    violations: list[str] = []
    for path in scan_files:
        if path == FIXTURE:
            fixture_without_scan = dict(load_fixture())
            fixture_without_scan.pop("overclaim_scan", None)
            text = json.dumps(fixture_without_scan, sort_keys=True).lower()
        else:
            text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden_phrases:
            if phrase in text:
                relative = path.relative_to(REPO_ROOT).as_posix()
                violations.append(f"{relative}: {phrase}")

    assert violations == []
