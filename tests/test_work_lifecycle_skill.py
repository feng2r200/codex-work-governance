"""Contract tests for work-lifecycle slice completion reporting."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "skills" / "work-lifecycle"
SKILL_PATH = LIFECYCLE_ROOT / "SKILL.md"
L0_PATH = LIFECYCLE_ROOT / "references" / "l0-intake.md"
L1_PATH = LIFECYCLE_ROOT / "references" / "l1-demand-contract.md"
L3_PATH = LIFECYCLE_ROOT / "references" / "l3-execution.md"
L4_PATH = LIFECYCLE_ROOT / "references" / "l4-validation.md"
L5_PATH = LIFECYCLE_ROOT / "references" / "l5-deviation-rollback.md"
L6_PATH = LIFECYCLE_ROOT / "references" / "l6-closeout-handoff.md"
INDEPENDENT_PATH = (
    REPOSITORY_ROOT
    / "plugins"
    / "work-governance"
    / "skills"
    / "independent-validation"
    / "SKILL.md"
)
TRUTH_PATH = (
    REPOSITORY_ROOT
    / "plugins"
    / "work-governance"
    / "skills"
    / "project-truth-governance"
    / "SKILL.md"
)
README_PATH = REPOSITORY_ROOT / "README.md"

SUMMARY_FIELDS = (
    "当前子任务：",
    "完成与作用：",
    "验证：",
    "决定与依据：",
    "修改：",
    "下一步：",
)


def assert_fields_in_order(document: str) -> None:
    """Require every summary field once and in the public contract order."""
    for field in SUMMARY_FIELDS:
        assert document.count(field) == 1

    positions = [document.index(field) for field in SUMMARY_FIELDS]

    assert positions == sorted(positions)


def test_summary_fields_and_order_are_stable() -> None:
    """Keep the complete ordered template in core, execution, and closeout guidance."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")

    assert_fields_in_order(skill)
    assert_fields_in_order(execution)
    assert_fields_in_order(closeout)
    assert "<T-ID 或 NO_PLAN>" in skill
    assert "<T-ID 或 NO_PLAN>" in execution
    assert "<T-ID 或 NO_PLAN>" in closeout


def test_trigger_and_task_mapping_cover_plan_and_no_plan_work() -> None:
    """Tie each independently accepted slice to its correct public identifier."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")

    assert "After every independently verifiable execution slice" in skill
    assert "before describing or starting the next\n  step" in skill
    assert "For Plan-controlled work, `当前子任务` is the corresponding `T-ID`." in execution
    assert "the whole request is one slice" in execution
    assert "`NO_PLAN`" in execution


def test_multiple_completed_slices_are_not_merged() -> None:
    """Preserve per-slice decisions and validation gaps in execution order."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")

    assert "report each slice separately and in execution order" in skill
    assert "emit one summary per slice in\n  execution order" in execution
    assert "Do not merge them in a way that hides a decision or\n  validation gap." in execution
    assert "Multiple\ncompleted slices require separate summaries in execution order." in closeout


def test_incomplete_or_unverified_results_cannot_look_complete() -> None:
    """Reject false completion from partial states or unverified delegation."""
    execution = L3_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")

    for state in ("`in_progress`", "`blocked`", "unverified"):
        assert state in execution
        assert state in closeout
    assert "A SubAgent's report alone cannot complete a slice." in execution
    assert "SubAgent-only results" in closeout
    assert "must not be formatted as one" in execution
    assert "Do not use the\ncompletion-summary shape" in closeout


def test_explicit_no_change_and_no_decision_wording_is_required() -> None:
    """Make empty decision and modification sections unambiguous."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")

    assert "没有则写“无新增决策”" in skill
    assert "没有则写“无”" in skill
    assert "`无新增决策`" in execution
    assert "Use `无` when no file, configuration, data, or external state changed." in closeout


def test_decision_basis_is_material_and_traceable() -> None:
    """Exclude mechanical steps while retaining high-impact decision provenance."""
    execution = L3_PATH.read_text(encoding="utf-8")

    assert "goal, scope,\nbehavior, cost, safety, or delivery form" in execution
    for basis in (
        "user confirmation",
        "project rule",
        "current evidence",
        "technical constraint",
        "agent tradeoff",
    ):
        assert basis in execution
    assert "Mechanical steps are not decisions" in execution


def test_summary_is_reply_protocol_not_plan_schema() -> None:
    """Keep execution authority in the Plan instead of turning it into a diary."""
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "This is a reply protocol, not a Plan task-schema extension" in skill
    assert "turn the Plan into a process log" in skill


def test_lifecycle_requires_current_bootstrap_and_canonical_layout() -> None:
    """Plan-controlled work fails closed when SessionStart readiness is absent."""
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert ".work-governance/bootstrap-state.json" in skill
    assert "untrusted, disabled, skipped by managed policy, absent, or stale" in skill
    assert "`ENVIRONMENT_BLOCKED`" in skill
    assert ".work-governance/_Plan/index.yaml" in skill
    assert ".work-governance/workctl.lock" in skill
    assert "controller commands require `LAYOUT_READY`" in skill


def test_goal_anchor_reality_probe_and_test_provenance_are_required() -> None:
    """Keep validation effort tied to the user result and observed boundaries."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    intake = L0_PATH.read_text(encoding="utf-8")
    demand = L1_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    validation = L4_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")

    assert "Keep a goal anchor" in skill
    assert "user-visible target, not the planned method, test suite" in intake
    assert "cheapest safe\nreality-bound probe" in execution
    for provenance in (
        "a confirmed obligation",
        "an observed failure",
        "a code invariant",
        "a supported integration boundary",
    ):
        assert provenance in demand
        assert provenance.removeprefix("a ").removeprefix("an ") in validation
    assert "Do not invent hypothetical use cases" in demand
    assert "exhaustive\ncoverage and invented scenarios are not delivery goals" in readme


def test_ineffective_loop_has_a_deterministic_stop_loss() -> None:
    """Forbid evidence-free retries while preserving explicit monitoring."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    deviation = L5_PATH.read_text(encoding="utf-8")
    independent = INDEPENDENT_PATH.read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    normalized_execution = " ".join(execution.split())
    normalized_deviation = " ".join(deviation.split())

    assert "materially identical inputs and state" in skill
    assert "Two consecutive attempts without a material evidence delta" in normalized_skill
    assert "`INEFFECTIVE_LOOP_DETECTED`" in skill
    assert "record an attempt tuple" in execution
    assert "Do not respond by creating more synthetic cases" in normalized_execution
    assert "Explicit monitoring or wait requests are not loops" in normalized_deviation
    assert "`stop-loss-audit`" in independent


def test_root_cause_and_solution_challenge_precede_fix_claims() -> None:
    """Separate symptoms and workarounds from discriminated causal evidence."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    deviation = L5_PATH.read_text(encoding="utf-8")
    independent = INDEPENDENT_PATH.read_text(encoding="utf-8")
    truth = TRUTH_PATH.read_text(encoding="utf-8")

    for requirement in (
        "falsifiable cause hypothesis and causal chain",
        "evidence supporting and contradicting the hypothesis",
        "cheapest safe discriminating probe",
        "minimal containment, causal correction, and alternate\n  route",
    ):
        assert requirement in deviation
    assert "removes the cause or only hides it" in skill
    assert "`causal-challenge`" in independent
    assert "Keep symptoms, hypotheses, probes, and confirmed causes distinct" in truth
    assert "successful workaround does not promote a root-cause hypothesis" in truth
