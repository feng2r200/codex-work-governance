import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "work-governance"
SKILLS = PLUGIN / "skills"
SKILL_NAMES = {
    "work-lifecycle",
    "goal-discovery",
    "plan-governance",
    "subagent-governance",
    "git-change-governance",
    "code-intelligence",
    "problem-discovery",
    "independent-validation",
    "project-development-governance",
    "project-truth-governance",
    "project-archive-curation",
    "work-reporting",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(path: Path) -> str:
    return " ".join(read(path).split())


def live_text() -> str:
    files = [ROOT / "README.md", ROOT / "PRIVACY.md", ROOT / "TERMS.md", ROOT / "AGENTS.md"]
    files.extend(SKILLS.rglob("*.md"))
    files.extend(SKILLS.rglob("*.yaml"))
    return "\n".join(read(path) for path in files)


def test_expected_skills_exist_with_matching_metadata() -> None:
    assert {path.parent.name for path in SKILLS.glob("*/SKILL.md")} == SKILL_NAMES
    for name in SKILL_NAMES:
        text = read(SKILLS / name / "SKILL.md")
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        assert frontmatter["name"] == name
        assert frontmatter["description"]

        agent = yaml.safe_load(read(SKILLS / name / "agents" / "openai.yaml"))["interface"]
        assert agent["display_name"]
        assert agent["short_description"]
        assert name in agent["default_prompt"]


def test_skill_links_resolve() -> None:
    for skill_file in SKILLS.rglob("SKILL.md"):
        for target in re.findall(r"\]\(([^)#][^)]+)\)", read(skill_file)):
            if "://" not in target:
                assert (skill_file.parent / target).exists(), f"{skill_file}: {target}"


def test_workflows_pin_external_actions_by_commit_sha() -> None:
    """Keep reusable workflow dependencies immutable and reviewable."""
    workflows = ROOT / ".github" / "workflows"
    for workflow in workflows.glob("*.y*ml"):
        uses_values = re.findall(r"^\s*uses:\s*([^\s#]+)", read(workflow), re.MULTILINE)
        for uses_value in uses_values:
            if uses_value.startswith("./"):
                continue
            action, separator, revision = uses_value.rpartition("@")
            assert action and separator, f"{workflow}: invalid uses value {uses_value}"
            assert re.fullmatch(r"[0-9a-f]{40}", revision), (
                f"{workflow}: {uses_value} must use a full commit SHA"
            )


def test_public_plugin_core_is_tool_neutral_and_has_no_state_engine() -> None:
    """Verify that optional adapters do not smuggle in a state engine."""
    text = live_text().lower()
    for forbidden in ["workctl", "workvcs", "sessionstart", "userpromptsubmit", "action lease"]:
        assert forbidden not in text

    manifest = json.loads(read(PLUGIN / ".codex-plugin" / "plugin.json"))
    portable = json.loads(read(PLUGIN / "plugin.json"))
    assert "hooks" not in manifest
    assert "mcpServers" not in manifest
    assert "scripts" not in manifest
    assert "mcp.json" not in portable
    assert not (PLUGIN / "hooks").exists()
    assert not (PLUGIN / "scripts").exists()


def test_code_intelligence_routes_and_refreshes_bounded_readiness() -> None:
    """Keep CodeGraph current without making it a universal prerequisite."""
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    skill = normalized(SKILLS / "code-intelligence" / "SKILL.md")
    operations = normalized(SKILLS / "code-intelligence" / "references" / "codegraph.md")

    assert "work-governance:code-intelligence" in lifecycle
    assert "structural symbol, call-path, impact, affected-test" in lifecycle
    assert "Global tool availability" in skill
    assert "Active-checkout index health" in skill
    assert "active checkout, not from the Git common directory" in skill
    assert "current authority permits local derived-state creation" in skill
    assert "Source-read-only is not derived-state-read-only" in skill
    assert "codegraph status --json" in skill
    assert "synced project mirror" in skill
    assert "reference-only `sources/` tree" in skill
    assert "Do not install CodeGraph" in skill
    assert "This local derived index is neither project truth nor durable work state" in skill
    assert "Before any CodeGraph query" in skill
    assert "Refresh only what the evidence requires" in skill
    assert "Never run destructive `uninit`" in skill

    assert 'PROJECT_ROOT="$(git rev-parse --show-toplevel)"' in operations
    assert 'codegraph status --json "$PROJECT_ROOT"' in operations
    assert 'codegraph init --yes "$PROJECT_ROOT"' in operations
    assert 'codegraph sync "$PROJECT_ROOT"' in operations
    assert 'codegraph index "$PROJECT_ROOT"' in operations
    assert "The second command is mandatory readback" in operations
    assert "Do not issue a CodeGraph query against that index" in operations
    assert "regardless of whether the source task is read-only" in operations
    assert "Only use CodeGraph after the final readback proves the index is current" in operations
    assert "`index.state` is complete" in operations
    assert "`worktreeMismatch` is null" in operations
    assert "`index.reindexRecommended` is false" in operations
    assert "installation command is reference material, not standing authority" in operations
    assert "Do not edit the tracked `.gitignore`" in operations


def test_clear_work_and_goal_discovery_do_not_force_ceremony() -> None:
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    discovery = normalized(SKILLS / "goal-discovery" / "SKILL.md")
    assert "already-actionable" in lifecycle
    assert "keep its participation independent from Plan admission" in lifecycle
    assert "If a proposed technical solution already determines" in discovery
    assert "Investigate cheap, in-scope facts before asking the user" in discovery
    assert "non-blocking" in discovery.lower()


def test_material_solution_strategy_is_confirmed_before_dependent_work() -> None:
    """Keep material solution choices ahead of dependent stage work."""
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    discovery = normalized(SKILLS / "goal-discovery" / "SKILL.md")
    plan = normalized(SKILLS / "plan-governance" / "SKILL.md")
    project = normalized(SKILLS / "project-development-governance" / "SKILL.md")
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )

    assert "material solution strategy" in lifecycle
    assert "requested outcome from the proposed means" in lifecycle
    assert "materially different approaches" in discovery
    assert "most visible artifact" in discovery
    assert "one assumed path fails" in discovery
    assert "before the first design, agent delegation, or mutation" in discovery
    assert "explicitly selected a material approach" in discovery
    assert "interchangeable, reversible implementation detail" in discovery
    assert "Do not hard-code one approach into a stage definition" in plan
    assert "Feasibility discovery supports a recommendation" in plan
    assert "do not turn an unconfirmed material solution assumption" in project
    assert "material solution choice that remains unresolved" in contract


def test_adaptive_loop_routes_decisions_through_current_authority() -> None:
    """Keep default confirmation and explicit delegation distinct and bounded."""
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    discovery = normalized(SKILLS / "goal-discovery" / "SKILL.md")
    plan = normalized(SKILLS / "plan-governance" / "SKILL.md")

    assert "investigate an in-scope fact" in lifecycle
    assert "interchangeable, reversible implementation detail" in lifecycle
    assert "material user-owned route or contract change" in lifecycle
    assert "explicit decision delegation covers that choice" in lifecycle
    assert "never infer it from silence, urgency" in lifecycle
    assert "available credentials" in lifecycle
    assert "another task or stage" in lifecycle
    assert "current task or named stage" in lifecycle
    assert "latest instruction can narrow or revoke" in lifecycle

    assert "Material choices are user-owned by default" in discovery
    assert "choose the evidence-backed route" in discovery
    assert "inside the active envelope" in discovery
    assert "Reassess and choose the correction" in discovery

    assert "current decision owner" in plan
    assert "decision-authority envelope" in plan
    assert "Decision delegation does not require a Plan" in plan
    assert "same authority envelope and semantic-review rules apply to No-Plan work" in plan
    assert "delegation that expires, is narrowed, or is revoked" in plan


def test_semantic_review_corrects_in_scope_and_reopens_only_at_boundaries() -> None:
    """Require bounded autonomous correction without weakening evidence or authority."""
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    project = normalized(SKILLS / "project-development-governance" / "SKILL.md")
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )
    reporting = normalized(SKILLS / "work-reporting" / "SKILL.md")

    for event in [
        "new evidence",
        "failed material assumption",
        "validation failure",
        "milestone completion",
        "scope or relevant external-state change",
        "mismatch between a receipt and observed state",
    ]:
        assert event in lifecycle

    for correction in [
        "continue",
        "repair",
        "roll back",
        "replace the approach",
        "reorder work",
        "revise a Plan",
        "expand validation",
    ]:
        assert correction in lifecycle

    assert "exceed the delegated scope or decision classes" in lifecycle
    assert "enter an unauthorized environment" in lifecycle
    assert "perform an unlisted guarded action" in lifecycle
    assert "never permits ignoring evidence" in lifecycle
    assert "never widens a claim beyond the validation performed" in lifecycle
    assert "Do not repeat broad reads" in lifecycle

    assert "active task or stage decision-authority envelope" in project
    assert "Do not create a parallel permissions ledger" in project
    assert "Record activation, revocation, scope changes" in project
    assert "omit routine choices and unchanged review outcomes" in project
    assert "single execution-state provider" in contract
    assert (
        "No semantic change means no repeated read, review, report, or provider write" in contract
    )

    assert "Do not narrate every ordinary judgment" in reporting
    assert "changed evidence, its effect, the bounded action taken" in reporting
    assert "does not expose hidden reasoning" in reporting
    assert "exceeds the decision-authority envelope" in reporting


def test_decision_delegation_does_not_expand_guarded_action_authority() -> None:
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    discovery = normalized(SKILLS / "goal-discovery" / "SKILL.md")
    validation_record = normalized(
        ROOT / "docs" / "validation" / "adaptive-decision-and-review-loop-v1.md"
    )

    assert "does not expand the goal, scope, target, environment" in lifecycle
    for guarded in [
        "Push",
        "release",
        "deployment",
        "production or data changes",
        "credential use",
        "destructive cleanup",
    ]:
        assert guarded in lifecycle
    assert "exact action and target in the same authorization contract" in lifecycle
    assert "resolve the exact target and obtain the fresh guard evidence" in lifecycle
    assert "Do not add another policy-only confirmation" in lifecycle
    assert "stop at the confirmation frontier" in lifecycle
    assert "Do not mutate files, create or update durable provider state or a Plan" in lifecycle
    assert "unlisted guarded action" in discovery
    assert "judgment delegation is not action authorization" in validation_record
    assert "guarded action is explicitly listed with an exact target" in validation_record
    assert "confirmation-only proposal" in validation_record


def test_plan_is_independent_and_no_plan_can_evolve() -> None:
    plan = normalized(SKILLS / "plan-governance" / "SKILL.md")
    assert "without any particular persistence tool" in plan
    assert "No-Plan means no Plan entity or Plan ceremony" in plan
    assert "does not forbid independent knowledge" in plan
    assert "why durable coordination became valuable now" in plan
    assert "Do this once" in plan
    assert "does not force a Plan" in plan
    assert "per-version test suites" in plan


def test_subagent_rules_preserve_net_value_and_single_ownership() -> None:
    subagent = normalized(SKILLS / "subagent-governance" / "SKILL.md")
    assert "provides net value" in subagent
    assert "Give each writable area one owner" in subagent
    assert "do not encode a permanent role-to-model matrix" in subagent
    assert "A timeout or quiet agent is not itself failure" in subagent
    assert "Blocking discovery" in subagent
    assert "Non-blocking discovery" in subagent


def test_worktree_policy_prefers_current_configuration_and_default_branch() -> None:
    git_skill = read(SKILLS / "git-change-governance" / "SKILL.md")
    ordered = [
        "current attached or already managed worktree",
        "explicit user or project path",
        "worktree root configured by the current Codex environment",
        "Codex's official default, `$CODEX_HOME/worktrees`",
    ]
    positions = [git_skill.index(item) for item in ordered]
    assert positions == sorted(positions)
    assert "current default branch" in git_skill
    assert "Do not assume it is named `main`" in git_skill


def test_authorized_local_commits_are_default_stage_checkpoints() -> None:
    """Allow recoverable local checkpoints without weakening explicit Git gates."""
    git_skill = normalized(SKILLS / "git-change-governance" / "SKILL.md")
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")

    assert "Authorization to modify repository content includes creating new" in git_skill
    assert "non-rewriting local commits" in git_skill
    assert "Do not ask for separate confirmation after each coherent stage" in git_skill
    assert "checkpoint for staged Git-tracked state" in git_skill
    assert "not as a complete workspace backup" in git_skill
    assert "independently meaningful delivery boundary" in git_skill
    assert "instead of splitting mechanically by file type" in git_skill

    for protected_boundary in [
        "makes the task read-only",
        "confirmation-only proposal",
        "review before commit",
        "excludes commits",
        "ownership unresolved",
        "remote state changes are separate actions",
        "does not authorize amend, rebase, reset, force updates",
    ]:
        assert protected_boundary in git_skill

    assert "stop at the confirmation frontier" in lifecycle
    assert "Do not mutate files, create or update durable provider state or a Plan" in lifecycle
    assert "change Git" in lifecycle


def test_validation_truth_and_reporting_boundaries() -> None:
    validation = read(SKILLS / "independent-validation" / "SKILL.md")
    truth = normalized(SKILLS / "project-truth-governance" / "SKILL.md")
    reporting = read(SKILLS / "work-reporting" / "SKILL.md")
    assert "Do not impose independent review" in validation
    assert "persistence-tool Skill" in truth
    assert "recorded decision is not project truth merely because it is durable" in truth
    for item in ["**added**", "**modified**", "**deleted**", "**operated**"]:
        assert item in reporting
    assert "never force a canned sentence" in reporting
    assert "Do not claim that nothing remains" in reporting


def test_problem_discovery_is_early_stage_appropriate_and_risk_bounded() -> None:
    """Keep proactive discovery broad enough to matter without becoming exhaustive."""
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    discovery = normalized(SKILLS / "problem-discovery" / "SKILL.md")
    validation = normalized(SKILLS / "independent-validation" / "SKILL.md")

    assert "work-governance:problem-discovery" in lifecycle
    assert "already-defined routine test suite" in lifecycle
    assert "Do not assume the important claims have already been written down" in discovery
    assert "work-governance:goal-discovery" in discovery
    assert "must not invent a material product rule" in discovery
    assert "orthogonal to risk dimensions" in discovery
    assert "Concurrency is not a later stage" in discovery
    assert "Do not multiply every dimension into an exhaustive Cartesian product" in discovery
    assert "exact target and uniquely unresolved claim" in discovery
    assert "maximum effect or cost per probe" in discovery
    assert "Do not force every task through every environment" in discovery
    assert "work-governance:independent-validation" in discovery
    assert "primary need is to design the coverage" in validation


def test_project_development_trigger_and_anti_trigger_are_explicit() -> None:
    skill_path = SKILLS / "project-development-governance" / "SKILL.md"
    text = read(skill_path)
    description = yaml.safe_load(text.split("---", 2)[1])["description"]
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")

    assert "explicitly enrolled project" in description
    assert "multiple tasks, sessions, or phases" in description
    assert "Do not use for isolated edits or one-off investigations" in description
    assert "project-development-governance" in lifecycle
    assert "bounded recovery, live-state reconciliation, or stage-baseline cadence" in lifecycle


def test_project_development_separates_authority_and_mutable_state() -> None:
    skill = normalized(SKILLS / "project-development-governance" / "SKILL.md")
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )

    assert "exactly one mutable execution-state provider" in skill
    assert "external durable-state provider or a project-local ledger, never both" in skill
    assert "The entry is a map, not a second status report" in skill
    assert "Architecture and module relationships" in contract
    assert "Accepted decisions and rationale" in contract
    assert "Constraints and prohibited actions" in contract
    assert "Acceptance methods and criteria" in contract
    assert "Durable risks and boundary conditions" in contract
    assert "Do not leave two independently mutable copies" in contract
    assert "stage baseline is a project-native accepted snapshot" in skill
    assert "provider is authoritative for live execution state" in contract


def test_project_development_startup_and_closeout_are_bounded() -> None:
    skill = read(SKILLS / "project-development-governance" / "SKILL.md")
    skill_normalized = normalized(SKILLS / "project-development-governance" / "SKILL.md")
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )
    startup = [
        "Read the project entry first",
        "Recover a bounded current-state packet",
        "Read only the task-relevant authority documents",
    ]
    positions = [skill.index(item) for item in startup]

    assert positions == sorted(positions)
    for delta in [
        "progress and status",
        "remaining work and priority",
        "material decisions and reasons",
        "open risks and boundary cases",
        "acceptance evidence",
    ]:
        assert delta in skill_normalized
    assert "No material delta means no state churn" in skill_normalized
    assert "durable handoff is incomplete" in skill_normalized
    assert "entry, selected provider, task-relevant authority, then live evidence" in contract
    assert "no relevant provider state exists" in skill_normalized
    assert "Task closeout and stage closeout are different" in contract


def test_project_development_handles_provider_modes_and_ambiguity() -> None:
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )

    assert "External durable-state provider" in contract
    assert "Project-local ledger" in contract
    assert "Never operate both as live authorities" in contract
    assert "A shared backend does not identify the logical project" in contract
    assert "stop before writing state" in contract
    assert "Do not initialize or bind an ambient mirror" in contract
    assert "authorized local ledger is selected" in contract


def test_provider_state_isolation_and_snapshot_invalidation_are_explicit() -> None:
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    project = normalized(SKILLS / "project-development-governance" / "SKILL.md")
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )
    validation = normalized(ROOT / "docs" / "validation" / "provider-state-efficiency-v1.md")

    assert "stable locator proves where to look" in project
    assert "state-isolation boundary" in project
    assert "shared provider state with no enforced partition" in project
    assert "treat reads as candidate context and fail closed on provider writes" in project
    assert "Provider isolation" in contract
    assert "Prove logical ownership and provider-state isolation separately" in contract
    assert "Do not copy ambiguous history" in contract
    for trigger in [
        "logical owner or route changes",
        "provider revision, head, or cursor advances",
        "task scope changes",
        "external writer is observed",
        "relevant evidence identity changes",
        "status becomes unknown",
        "mutation receipt and exact target readback disagree",
    ]:
        assert trigger in project
    assert "precise typed receipt plus direct readback" in project
    assert "do not immediately repeat a broad recovery read" in lifecycle
    assert "reopen the affected target or dependency first" in project
    assert "No material semantic delta still means no provider write" in validation
    assert "does not claim a fixed token, latency, or monetary saving" in validation


def test_provider_control_plane_health_and_issue_classes_are_bounded() -> None:
    """Keep aggregate health reuse and degraded/blocked handling tool-neutral."""
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    project = normalized(SKILLS / "project-development-governance" / "SKILL.md")
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )

    assert "read-only aggregate health or readiness snapshot" in lifecycle
    assert "equivalent focused status reads" in lifecycle
    assert "cleanly inactive or missing capability" in lifecycle
    assert "degraded authority boundary" in lifecycle
    assert "stale, malformed, ambiguous, or integrity-failed" in lifecycle
    assert "blocked for the affected path" in lifecycle
    assert "does not cover the claim" in lifecycle
    assert "authorized mutation requires an exact fresh guard" in lifecycle

    assert "route, binding, isolation, capability, and integrity obligations" in project
    assert "continue independent work when safe" in project
    assert "fail closed on dependent claims and mutations" in project
    assert "neither state expands authority" in project
    assert "If continuity is missing or stale" not in project

    assert "Provider Control-Plane Readiness" in contract
    assert "A healthy aggregate is bounded evidence, not universal proof" in contract
    assert "do not repeat equivalent focused status reads" in contract
    assert "do not activate implicitly" in contract
    assert "before any separately authorized repair" in contract


def test_provider_operations_remain_task_owned_and_history_is_classified() -> None:
    """Keep routine delivery with the responsible task and historical replay bounded."""
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")
    project = normalized(SKILLS / "project-development-governance" / "SKILL.md")
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )

    assert "the responsible task owns that operation" in lifecycle
    assert "user monitoring job" in lifecycle
    assert "current task's known operation identifiers" in lifecycle
    assert "historical open inventory as classification evidence" in lifecycle
    assert "counterfactual effect" in lifecycle
    assert "open-looking status alone does not justify replaying" in lifecycle

    assert "The responsible task, not the user, monitors" in project
    assert "classify each candidate's present semantic value" in project
    assert "effect of acting now" in project
    assert "already-delivered operations" in project
    assert "superseded undelivered intent" in project

    assert "Provider Operation Ownership" in contract
    assert "not work the user must notice and resume manually" in contract
    assert "provider-wide historical inventory is classification evidence" in contract
    assert "deterministic terminal failure" in contract
    assert "An effective status that merely looks open" in contract


def test_project_development_scenario_matrix_covers_activation_boundaries() -> None:
    contract = normalized(
        SKILLS / "project-development-governance" / "references" / "project-contract.md"
    )

    for scenario in [
        "Continue an explicitly enrolled project, even for a small slice",
        "Resume the next priority after a prior task or long pause",
        "Start a delivery that will span dependent phases or handoffs",
        "Fix an isolated typo in a project with no enrollment",
        "Perform a one-off investigation with no durable continuation",
        "External provider is unresolved but an authorized local ledger is selected",
        "Shared storage contains several possible logical projects",
        (
            "A stable project locator resolves, but several projects expose the same "
            "unpartitioned mutable state"
        ),
        (
            "One aggregate provider snapshot proves the required route, binding, isolation, "
            "capability, and integrity obligations"
        ),
        "A route is cleanly inactive or a required capability is absent",
        "Provider control state is stale, malformed, ambiguous, or integrity-failed",
        (
            "A current-task operation is awaiting ordinary same-target delivery or receipt "
            "work already covered by authority"
        ),
        "A historical provider inventory contains open-looking operations",
        ("An older operation is already delivered, terminal, replaced, or semantically superseded"),
        "A precise mutation receipt and exact target readback match the recovered snapshot",
        (
            "Provider owner, route, revision, head, scope, external-write state, or "
            "evidence identity changes"
        ),
    ]:
        assert scenario in contract


def test_project_development_does_not_force_a_plan() -> None:
    project = normalized(SKILLS / "project-development-governance" / "SKILL.md")

    assert "A project entry is not a Plan" in project
    assert "project enrollment never creates a mega-Plan" in project
    assert "may remain No-Plan" in project


def test_work_governance_archive_scenario_reuses_existing_coverage() -> None:
    curation = normalized(SKILLS / "project-archive-curation" / "SKILL.md")
    lifecycle = read(SKILLS / "work-lifecycle" / "SKILL.md")

    assert "Reuse existing durable records and authoritative documents" in curation
    assert "shared context as a thin projection" in curation
    assert "must not become competing mutable authorities" in curation
    assert "Exclude the current curation work" in curation
    assert "project-archive-curation" not in lifecycle


def test_dianjin_archive_scenario_preserves_unbound_and_mixed_history() -> None:
    curation = normalized(SKILLS / "project-archive-curation" / "SKILL.md")

    assert "its absence does not prove that the project or its history is empty" in curation
    assert "Do not infer archive readiness from a title or UI status alone" in curation
    assert "Keep different item kinds separate" in curation
    assert "must not initialize persistence" in curation
    assert "bind an ambient mirror" in curation
    assert (
        "Historical work that predates durable capture may need one bounded curation pass"
        in curation
    )


def test_archive_curation_keeps_mutation_gates_ordered_and_independent() -> None:
    curation = read(SKILLS / "project-archive-curation" / "SKILL.md")
    ordered = [
        "persist durable cognition or draft shared context",
        "publish or import the shared context",
        "read back and verify the published result",
        "archive the exact approved items",
    ]
    positions = [curation.index(item) for item in ordered]

    assert positions == sorted(positions)
    assert "Authority for one does not grant the next" in curation
    assert "Archive readiness is not a completion claim" in curation


def test_manifest_readme_and_project_metadata_match_architecture() -> None:
    """Keep portable, compatibility, project, and README metadata aligned."""
    manifest = json.loads(read(PLUGIN / ".codex-plugin" / "plugin.json"))
    portable = json.loads(read(PLUGIN / "plugin.json"))
    portable_interface = portable["extensions"]["com.openai"]["interface"]
    project = tomllib.loads(read(ROOT / "pyproject.toml"))
    readme = normalized(ROOT / "README.md")
    assert manifest["interface"]["defaultPrompt"] == [
        "Use $work-governance:work-lifecycle to align evidence and authority, then adapt "
        "execution at meaningful change."
    ]
    assert all(len(prompt) <= 128 for prompt in manifest["interface"]["defaultPrompt"])
    assert "Tool-neutral core" in read(ROOT / "README.md")
    assert "Optional tool adapters are isolated" in read(ROOT / "README.md")
    assert "code-intelligence" in readme
    assert "project-archive-curation" in readme
    assert "project-development-governance" in readme
    assert "work-reporting" in readme
    assert "Project development continuity" in manifest["interface"]["capabilities"]
    assert "Optional code intelligence" in manifest["interface"]["capabilities"]
    assert "Adaptive decision and review" in manifest["interface"]["capabilities"]
    assert "Problem discovery" in manifest["interface"]["capabilities"]
    assert "Project archive curation" in manifest["interface"]["capabilities"]
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert portable["name"] == manifest["name"] == project["project"]["name"]
    assert portable["version"] == manifest["version"]
    assert portable["description"] == manifest["description"]
    assert portable["author"]["name"] == manifest["author"]["name"] == "feng2r200"
    assert portable["license"] == manifest["license"] == project["project"]["license"]
    assert portable_interface == manifest["interface"]
    assert project["project"]["version"] == "2.0.0"
    assert project["project"]["dependencies"] == []
    assert "/.work-governance/" in read(ROOT / ".gitignore").splitlines()
