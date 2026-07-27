"""Contract tests for work-lifecycle slice completion reporting."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "skills" / "work-lifecycle"
SKILL_PATH = LIFECYCLE_ROOT / "SKILL.md"
L3_PATH = LIFECYCLE_ROOT / "references" / "l3-execution.md"
L6_PATH = LIFECYCLE_ROOT / "references" / "l6-closeout-handoff.md"

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
