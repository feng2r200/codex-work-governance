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
    assert "work-reporting" in readme
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
