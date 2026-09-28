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


def test_public_plugin_is_tool_neutral_and_has_no_state_engine() -> None:
    """Verify that packaging does not smuggle in a state or execution engine."""
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


def test_clear_work_and_goal_discovery_do_not_force_ceremony() -> None:
    lifecycle = read(SKILLS / "work-lifecycle" / "SKILL.md")
    discovery = normalized(SKILLS / "goal-discovery" / "SKILL.md")
    assert "already-actionable" in lifecycle
    assert "If a proposed technical solution already determines" in discovery
    assert "Investigate cheap, in-scope facts before asking the user" in discovery
    assert "non-blocking" in discovery.lower()


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


def test_project_development_trigger_and_anti_trigger_are_explicit() -> None:
    skill_path = SKILLS / "project-development-governance" / "SKILL.md"
    text = read(skill_path)
    description = yaml.safe_load(text.split("---", 2)[1])["description"]
    lifecycle = normalized(SKILLS / "work-lifecycle" / "SKILL.md")

    assert "explicitly enrolled project" in description
    assert "multiple tasks, sessions, or phases" in description
    assert "Do not use for isolated edits or one-off investigations" in description
    assert "project-development-governance" in lifecycle
    assert "bounded recovery, or closeout reconciliation" in lifecycle


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
        "Use $work-governance:work-lifecycle to preserve goal, authority, momentum, "
        "and evidence with only the needed modules."
    ]
    assert all(len(prompt) <= 128 for prompt in manifest["interface"]["defaultPrompt"])
    assert "does not require one specific CLI" in readme
    assert "project-archive-curation" in readme
    assert "project-development-governance" in readme
    assert "work-reporting" in readme
    assert "Project development continuity" in manifest["interface"]["capabilities"]
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
