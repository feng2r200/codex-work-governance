"""Contract tests for work-lifecycle slice completion reporting."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "skills" / "work-lifecycle"
SKILL_PATH = LIFECYCLE_ROOT / "SKILL.md"
L0_PATH = LIFECYCLE_ROOT / "references" / "l0-intake.md"
L0_DECISION_FRONTIER_PATH = LIFECYCLE_ROOT / "references" / "l0-decision-frontier.md"
L1_PATH = LIFECYCLE_ROOT / "references" / "l1-demand-contract.md"
L2_PATH = LIFECYCLE_ROOT / "references" / "l2-plan-control.md"
L3_PATH = LIFECYCLE_ROOT / "references" / "l3-execution.md"
L4_PATH = LIFECYCLE_ROOT / "references" / "l4-validation.md"
L5_PATH = LIFECYCLE_ROOT / "references" / "l5-deviation-rollback.md"
L6_PATH = LIFECYCLE_ROOT / "references" / "l6-closeout-handoff.md"
L7_PATH = LIFECYCLE_ROOT / "references" / "l7-context-governance.md"
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
CANDIDATE_NOTES_PATH = REPOSITORY_ROOT / "docs" / "WORK_GOVERNANCE_1_1_0_CANDIDATE.md"

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
    assert "<T-ID、ADMISSION、GOVERNANCE 或 NO_PLAN>" in skill
    assert "<T-ID、ADMISSION、GOVERNANCE 或 NO_PLAN>" in execution
    assert "<T-ID、ADMISSION、GOVERNANCE 或 NO_PLAN>" in closeout


def test_trigger_and_task_mapping_cover_plan_and_no_plan_work() -> None:
    """Tie each independently accepted slice to its correct public identifier."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")

    assert "After every independently verifiable execution slice" in skill
    assert "before describing or starting the next\n  step" in skill
    assert "For Plan-controlled work, `当前子任务` is the corresponding `T-ID`." in execution
    assert "`ADMISSION`" in execution
    assert "`GOVERNANCE`" in execution
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


def test_lifecycle_requires_direct_workctl_and_canonical_layout() -> None:
    """Plan-controlled work starts from direct workctl layout readiness."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())

    assert "registered direct `workctl` executable" in skill
    assert "without `uv run`" in skill
    assert "without Codex\n  lifecycle hooks" in skill
    assert ".work-governance/bootstrap-state.json" in skill
    assert ".work-governance/_Plan/index.yaml" in skill
    assert ".work-governance/workctl.lock" in skill
    assert "All non-layout commands require `LAYOUT_READY`" in normalized_skill
    assert "stale local installation shim" in normalized_skill
    assert "codex plugin list --json" in skill
    assert "Do not use a derived cache/source path for Plan mutations" in normalized_skill


def test_lifecycle_uses_hookless_direct_workctl() -> None:
    """The direct executable, not a SessionStart command, drives intake."""
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "--script plugins/work-governance/scripts/workctl.py" not in skill
    assert ".work-governance/cache/uv" not in skill
    assert "Run the registered direct `workctl` executable" in skill
    assert "intake status" in skill
    assert "--no-project" not in skill


def test_decision_frontier_and_context_governance_are_routed_from_lifecycle() -> None:
    """Keep lightweight questions and context packages in the mandatory entry."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    frontier = L0_DECISION_FRONTIER_PATH.read_text(encoding="utf-8")
    context = L7_PATH.read_text(encoding="utf-8")

    assert "references/l0-decision-frontier.md" in skill
    assert "references/l7-context-governance.md" in skill
    assert "recommended answer" in frontier
    assert "ask one blocking question at a time" in frontier
    assert "workctl frontier draft --manifest PATH|--stdin" in frontier
    assert "workctl context lint --manifest PATH|--stdin [--role ROLE]" in context
    assert "workctl context build --role implement|check|review|truth" in skill
    assert "workctl work status [--full]" in skill
    assert "does not mutate the contract or runtime state" in context
    assert "Do not install automatic context-injection hooks by default" in context


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


def test_pre_implementation_contract_is_required_before_mutation() -> None:
    """Non-trivial work must plan evidence, uncertainty, actions, and checks first."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    intake = L0_PATH.read_text(encoding="utf-8")
    demand = L1_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    validation = L4_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    model_first = (REPOSITORY_ROOT / "docs" / "MODEL_FIRST.md").read_text(
        encoding="utf-8"
    )
    public_contract = "\n".join(
        (skill, intake, demand, execution, validation, closeout, readme, model_first)
    )

    assert "`Pre-Implementation Contract`" in skill
    assert "Before implementation, make the intake output usable" in intake
    for requirement in (
        "goal anchor",
        "evidence basis",
        "unresolved user-owned uncertainty",
        "exact files, data, commands, external surfaces, or documentation locations",
        "validation anchors",
        "stop or revision triggers",
    ):
        assert requirement in demand
    assert "present the `Pre-Implementation Contract` for non-trivial work" in execution
    assert "intended action versus actual change" in public_contract
    assert "expected evidence versus observed evidence" in public_contract
    assert "Pre-implementation audit" in validation
    assert "有 blocker 时，\n  先用 frontier 问最小问题" in model_first
    assert "This keeps the lightweight path\nSocratic and plan-first" in readme


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


def test_bulk_authorization_preserves_pilot_and_quality_drift_stop_loss() -> None:
    """Blanket approval never certifies a pilot or permits drift amplification."""
    demand = L1_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    deviation = L5_PATH.read_text(encoding="utf-8")
    normalized_demand = " ".join(demand.split())
    normalized_execution = " ".join(execution.split())
    normalized_deviation = " ".join(deviation.split())

    assert "Bulk or blanket authorization can reduce repeated prompts only when the model" in (
        normalized_demand
    )
    assert "judges it still covers the concrete repeated work" in normalized_demand
    assert "pilot task and validation remain explicit dependencies" in normalized_demand
    assert "cannot satisfy or bypass the pilot gate" in normalized_demand
    assert "QUALITY_DRIFT_DETECTED" in normalized_execution
    assert "freeze all dependent downstream batch work" in normalized_execution
    assert "do not continue amplifying the deviation" in normalized_deviation


def test_user_decision_refs_prefer_session_turn_and_evidence_hash() -> None:
    """New decision authority is strongly attributable without breaking history."""
    intake = L0_PATH.read_text(encoding="utf-8")
    control = L2_PATH.read_text(encoding="utf-8")
    normalized_control = " ".join(control.split())
    reference = "user:session/<SessionId>/turn/<TurnId>/sha256/<digest>"

    assert reference in intake
    assert reference in control
    assert "Prefer this exact form for new user decisions" in normalized_control
    assert "Existing typed references remain valid" in normalized_control


def test_inserted_requests_route_by_goal_alignment_and_resume_automatically() -> None:
    """Keep the Plan useful as a map without turning insertion into route churn."""
    intake = L0_PATH.read_text(encoding="utf-8")
    execution = L3_PATH.read_text(encoding="utf-8")
    deviation = L5_PATH.read_text(encoding="utf-8")

    assert "`NO_PLAN_INTERRUPTION`" in intake
    assert "next-action resume anchor" in intake
    assert "resume automatically" in intake
    assert "changes only execution order or priority" in intake
    assert "materially changes obligations, scope, behavior, cost" in intake
    assert "same dependency-ready Plan target automatically" in execution
    assert "is not automatically a deviation" in deviation


def test_reviewer_unavailability_and_atomic_closeout_are_bounded() -> None:
    """Unavailable review must not invent confidence or force an extra turn."""
    independent = INDEPENDENT_PATH.read_text(encoding="utf-8")
    control = L2_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")

    assert "one initial attempt and at most one retry" in independent
    assert "`VALIDATOR_UNAVAILABLE`" in independent
    assert "ordinary reversible local tasks" in independent
    assert "pending `plan_challenge`" in control
    assert "`activation.resolves_exclusions`" in control
    assert "Gate acceptance alone\n  never resolves an exclusion" in control
    assert "`plan complete --finalize-route --confirmation C-..." in closeout
    assert "decision-free extra user turn" in closeout

    skill = SKILL_PATH.read_text(encoding="utf-8")
    assert "`NO_PLAN_INTERRUPTION`" in skill
    assert "resume it automatically" in skill
    assert "`VALIDATOR_UNAVAILABLE`" in skill
    assert "controller-caused\nPlan revision" in skill
    assert "accepted external gate records authority" in skill


def test_retirement_is_distinct_from_completion_and_excluded_routes_stay_out() -> None:
    """Document the general retirement path without task-specific main-flow scope."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    control = L2_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    public_contract = "\n".join((skill, control, closeout, readme))

    assert "plan retire apply" in control
    assert "C-PLAN-RETIREMENT" in control
    assert "status: retired" in control
    assert "Do not call an obsolete or user-withdrawn route complete" in closeout
    assert "The result is `UNMANAGED_EMPTY`" in readme
    assert "modality-specific" not in public_contract
    assert "large-session rollover" not in public_contract


def test_devbooks_patterns_are_codex_native_and_lightweight() -> None:
    """Borrow useful DevBooks checks without importing its heavy platform model."""
    intake = L0_PATH.read_text(encoding="utf-8")
    demand = L1_PATH.read_text(encoding="utf-8")
    validation = L4_PATH.read_text(encoding="utf-8")
    deviation = L5_PATH.read_text(encoding="utf-8")
    closeout = L6_PATH.read_text(encoding="utf-8")
    independent = INDEPENDENT_PATH.read_text(encoding="utf-8")
    truth = TRUTH_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    candidate_notes = CANDIDATE_NOTES_PATH.read_text(encoding="utf-8")
    normalized_demand = " ".join(demand.split())
    normalized_deviation = " ".join(deviation.split())
    normalized_closeout = " ".join(closeout.split())
    public_contract = "\n".join(
        (
            intake,
            demand,
            validation,
            deviation,
            closeout,
            independent,
            truth,
            readme,
            candidate_notes,
        )
    )

    for gate in ("Value", "Impact", "Cognition", "Verification"):
        assert gate in intake
    assert "These gates are an intake thinking aid, not a required Plan artifact" in intake
    assert "Bind every must-have obligation to at least one acceptance anchor" in demand
    assert "weak-link" in demand
    assert "Do not create a second parallel checklist system" in normalized_demand
    assert "runtime-scoped until it proves a material contract change" in normalized_deviation
    assert "Do not create a separate deviation log, Plan revision, or contract churn" in (
        normalized_deviation
    )
    assert "Claim-boundary audit" in validation
    assert "claim-boundary check" in closeout
    assert "workctl help <workflow>" in normalized_closeout
    assert "generated `docs/CLI_REFERENCE.md`" in independent
    assert "External playbooks, framework drafts" in truth
    assert "DevBooks-Derived Skill Hardening" in candidate_notes
    assert "They are modeled as ordinary obligations/checks" in readme
    assert "does not adopt DevBooks change packages" in candidate_notes

    for forbidden in ("~/.claude", "git push  #", "Task 工具", "主 Agent 只编排"):
        assert forbidden not in public_contract
