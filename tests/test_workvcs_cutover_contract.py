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
    "git-change-governance",
    "independent-validation",
    "project-truth-governance",
}


def live_text_files() -> list[Path]:
    """Return text files that define the live plugin contract."""
    candidates: list[Path] = [
        ROOT / "README.md",
        ROOT / "PRIVACY.md",
        ROOT / "TERMS.md",
        ROOT / "AGENTS.md",
        ROOT / "pyproject.toml",
        PLUGIN / ".codex-plugin" / "plugin.json",
    ]
    candidates.extend(SKILLS.rglob("*.md"))
    candidates.extend(SKILLS.rglob("*.yaml"))
    return sorted(path for path in candidates if path.exists())


def read(path: Path) -> str:
    """Read a UTF-8 text file."""
    return path.read_text(encoding="utf-8")


def test_no_live_legacy_control_plane_terms() -> None:
    """The live plugin contract must not keep old local control-plane surfaces."""
    combined = "\n".join(read(path) for path in live_text_files())
    forbidden = [
        "work" + "ctl",
        "control" + "ler",
        "SessionStart",
        "UserPromptSubmit",
        "action lease",
        "review acquisition",
        "cooldown",
        "schema-v",
        "schema v",
    ]
    for term in forbidden:
        assert term not in combined


def test_four_core_skills_exist_with_valid_metadata() -> None:
    """The cutover keeps the four core skills with parseable YAML metadata."""
    for name in SKILL_NAMES:
        path = SKILLS / name / "SKILL.md"
        text = read(path)
        assert text.startswith("---\n")
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        assert frontmatter["name"] == name
        assert isinstance(frontmatter["description"], str)
        assert frontmatter["description"]


def test_skill_agent_metadata_is_parseable() -> None:
    """Every core skill keeps valid OpenAI-facing metadata."""
    for name in SKILL_NAMES:
        metadata_path = SKILLS / name / "agents" / "openai.yaml"
        metadata = yaml.safe_load(read(metadata_path))
        interface = metadata["interface"]
        assert isinstance(interface["display_name"], str)
        assert isinstance(interface["short_description"], str)
        assert isinstance(interface["default_prompt"], str)
        assert name in interface["default_prompt"]


def test_skill_markdown_links_are_not_dangling() -> None:
    """Relative skill links should point at files that still exist."""
    for skill_file in SKILLS.rglob("SKILL.md"):
        text = read(skill_file)
        for target in re.findall(r"\]\(([^)#][^)]+)\)", text):
            if "://" in target:
                continue
            assert (skill_file.parent / target).exists(), f"{skill_file}: {target}"


def test_no_plan_and_promotion_rules_are_explicit() -> None:
    """No-Plan is zero-persistence and promotion carries useful prior context."""
    lifecycle = read(SKILLS / "work-lifecycle" / "SKILL.md")
    assert "No-Plan" in lifecycle
    assert "zero WorkVCS calls and zero durable writes" in lifecycle
    assert "evolves into Plan-controlled work" in lifecycle
    for required in [
        "original request text or digest",
        "confirmed facts and decisions",
        "explored evidence and freshness",
        "unresolved agent-owned and user-owned unknowns",
        "why escalation is needed now",
        "acceptance anchors",
        "stop or revision triggers",
        "the next action",
    ]:
        assert required in lifecycle
    assert "do not block" in lifecycle
    assert "Plan, frontier" in lifecycle


def test_worktree_priority_uses_codex_configuration() -> None:
    """New worktrees follow Codex settings instead of project-local defaults."""
    git_skill = read(SKILLS / "git-change-governance" / "SKILL.md")
    ordered = [
        "current attached or already managed worktree",
        "explicit user or project path",
        "Codex configured `git-worktree-root`",
        "Codex official default `$CODEX_HOME/worktrees`",
    ]
    positions = [git_skill.index(item) for item in ordered]
    assert positions == sorted(positions)
    assert "Do not default to a project-local" in git_skill


def test_validation_and_truth_boundaries_are_conditional() -> None:
    """Validation and truth governance should stay useful without becoming taxes."""
    validation = read(SKILLS / "independent-validation" / "SKILL.md")
    truth = read(SKILLS / "project-truth-governance" / "SKILL.md")
    assert "Do not run validation as a default tax" in validation
    assert "WorkVCS is the activity state layer" in truth
    assert "Do not scan, migrate, or rewrite tracked `.work-governance` history by default" in truth


def test_manifest_readme_and_project_config_match_cutover() -> None:
    """Plugin metadata, README, and project config all describe the new boundary."""
    manifest = json.loads(read(PLUGIN / ".codex-plugin" / "plugin.json"))
    readme = read(ROOT / "README.md")
    project = tomllib.loads(read(ROOT / "pyproject.toml"))
    assert "hooks" not in manifest
    assert "mcpServers" not in manifest
    assert "scripts" not in manifest
    assert not (PLUGIN / "hooks").exists()
    assert not (PLUGIN / "scripts").exists()
    assert not (ROOT / "docs").exists()
    assert "minimum governance level" in manifest["interface"]["defaultPrompt"][0]
    assert "Durable Goals, Plans" in readme
    assert "Tasks" in readme
    assert "No-Plan means zero WorkVCS calls" in readme
    assert "uv run --with pyyaml python \"$SKILL_VALIDATOR\"" in readme
    assert "uv run --with pyyaml python \"$PLUGIN_VALIDATOR\"" in readme
    assert "old Plan-version" in readme
    assert "compatibility matrices" in readme
    assert project["project"]["dependencies"] == []
    assert "pyyaml>=6.0.3" in project.get("dependency-groups", {}).get("dev", [])
    assert "mypy" not in "\n".join(project.get("dependency-groups", {}).get("dev", []))
