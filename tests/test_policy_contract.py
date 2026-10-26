"""Structural and interface contracts for the Work Governance plugin."""

from __future__ import annotations

import json
import re
import shlex
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
    "resource-observation",
    "continuation-governance",
    "frontend-governance",
}


def read(path: Path) -> str:
    """Read one repository text file as UTF-8."""
    return path.read_text(encoding="utf-8")


def skill_frontmatter(path: Path) -> dict[str, object]:
    """Parse and validate one Skill frontmatter object."""
    parts = read(path).split("---", 2)
    assert len(parts) == 3, f"{path} has no YAML frontmatter"
    parsed: object = yaml.safe_load(parts[1])
    assert isinstance(parsed, dict), f"{path} frontmatter is not an object"
    assert all(isinstance(key, str) for key in parsed)
    return parsed


def markdown_links(path: Path) -> list[str]:
    """Extract local Markdown link targets from one file."""
    return re.findall(r"\]\(([^)#]+)(?:#[^)]+)?\)", read(path))


def test_skill_package_metadata_is_complete_and_consistent() -> None:
    """Every shipped Skill must have matching UI metadata and a unique description."""
    skill_files = sorted(SKILLS.glob("*/SKILL.md"))
    assert {path.parent.name for path in skill_files} == SKILL_NAMES
    descriptions: set[str] = set()

    for skill_file in skill_files:
        name = skill_file.parent.name
        frontmatter = skill_frontmatter(skill_file)
        assert frontmatter.get("name") == name
        description = frontmatter.get("description")
        assert isinstance(description, str) and description.strip()
        assert description not in descriptions
        descriptions.add(description)

        metadata_path = skill_file.parent / "agents" / "openai.yaml"
        metadata: object = yaml.safe_load(read(metadata_path))
        assert isinstance(metadata, dict)
        interface = metadata.get("interface")
        assert isinstance(interface, dict)
        assert isinstance(interface.get("display_name"), str)
        assert isinstance(interface.get("short_description"), str)
        default_prompt = interface.get("default_prompt")
        assert isinstance(default_prompt, str) and name in default_prompt


def test_all_local_markdown_links_resolve() -> None:
    """Local links in published Markdown must resolve to repository files."""
    markdown_files = [ROOT / "README.md", ROOT / "README.zh-CN.md"]
    markdown_files.extend(PLUGIN.rglob("*.md"))
    markdown_files.extend((ROOT / "docs").rglob("*.md"))

    for markdown_file in markdown_files:
        for target in markdown_links(markdown_file):
            if "://" in target or target.startswith("mailto:"):
                continue
            assert (markdown_file.parent / target).resolve().exists(), (
                f"{markdown_file} contains unresolved link {target}"
            )


def test_skill_references_are_discoverable_from_their_entrypoint() -> None:
    """Conditional reference detail must remain reachable through progressive disclosure."""
    for reference in SKILLS.glob("*/references/*"):
        if not reference.is_file():
            continue
        entrypoint = reference.parents[1] / "SKILL.md"
        relative = reference.relative_to(entrypoint.parent).as_posix()
        assert relative in read(entrypoint), f"{reference} is not linked from {entrypoint}"


def test_readmes_discover_every_shipped_skill() -> None:
    """Both public capability indexes must list every packaged Skill identifier."""
    for filename in ["README.md", "README.zh-CN.md"]:
        contents = read(ROOT / filename)
        missing = sorted(name for name in SKILL_NAMES if f"`{name}`" not in contents)
        assert not missing, f"{filename} omits {missing}"


def test_governance_core_has_no_provider_command_dependency() -> None:
    """Core instructions must stay portable and leave provider commands to provider Skills."""
    public_files = [ROOT / "README.md", ROOT / "README.zh-CN.md", ROOT / "AGENTS.md"]
    public_files.extend(SKILLS.rglob("*.md"))
    public_files.extend(SKILLS.rglob("*.yaml"))
    contents = "\n".join(read(path).lower() for path in public_files)
    for forbidden in ["workctl", "workvcs", "action lease"]:
        assert forbidden not in contents


def test_plugin_manifests_describe_one_portable_interface() -> None:
    """Compatibility and portable manifests must agree on identity and UI behavior."""
    compatibility = json.loads(read(PLUGIN / ".codex-plugin" / "plugin.json"))
    portable = json.loads(read(PLUGIN / "plugin.json"))
    project = tomllib.loads(read(ROOT / "pyproject.toml"))

    assert portable["name"] == compatibility["name"] == project["project"]["name"]
    assert portable["version"] == compatibility["version"]
    assert portable["description"] == compatibility["description"]
    assert portable["author"]["name"] == compatibility["author"]["name"]
    assert portable["license"] == compatibility["license"] == project["project"]["license"]
    assert portable["extensions"]["com.openai"]["interface"] == compatibility["interface"]
    assert compatibility["hooks"] == "./hooks/hooks.json"
    assert portable["extensions"]["com.openai"]["hooks"] == "./hooks/hooks.json"
    assert "hooks" not in portable
    assert "mcpServers" not in compatibility
    assert "mcp.json" not in portable


def test_hook_manifest_uses_only_the_stable_user_launcher() -> None:
    """Hook entries must use the installed stable launcher rather than cache paths."""
    manifest = json.loads(read(PLUGIN / "hooks" / "hooks.json"))
    hooks = manifest.get("hooks")
    assert isinstance(hooks, dict) and hooks
    commands: list[str] = []
    for groups in hooks.values():
        assert isinstance(groups, list)
        for group in groups:
            assert isinstance(group, dict)
            entries = group.get("hooks")
            assert isinstance(entries, list)
            for entry in entries:
                assert isinstance(entry, dict)
                command = entry.get("command")
                assert isinstance(command, str)
                commands.append(command)

    assert commands
    for command in commands:
        argv = shlex.split(command)
        assert argv[0] == "$HOME/.local/bin/work-governance-hook"
        assert not any(part.lower() in {"latest", "current"} for part in argv)


def test_external_workflow_actions_are_pinned_to_commit_shas() -> None:
    """Reusable CI dependencies must be immutable and reviewable."""
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


def test_release_metadata_is_machine_consistent() -> None:
    """Package, plugin, and lock metadata must describe the same release."""
    compatibility = json.loads(read(PLUGIN / ".codex-plugin" / "plugin.json"))
    project = tomllib.loads(read(ROOT / "pyproject.toml"))
    lock = tomllib.loads(read(ROOT / "uv.lock"))
    package = next(item for item in lock["package"] if item["name"] == project["project"]["name"])

    version = compatibility["version"]
    assert isinstance(version, str)
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
    assert package["version"] == project["project"]["version"]
    assert project["project"]["dependencies"] == []
    assert "/.work-governance/" in read(ROOT / ".gitignore").splitlines()


def test_behavior_scenarios_have_independent_non_vacuous_outcome_contracts() -> None:
    """Every forward scenario must require independent semantic outcomes."""
    behavior_root = ROOT / "tests" / "behavior"
    fixtures = sorted(path.parent for path in behavior_root.glob("*/evaluation-contract.json"))
    assert fixtures

    for fixture in fixtures:
        contract = json.loads(read(fixture / "evaluation-contract.json"))
        assert contract["schema_version"] == 2
        assert isinstance(contract["task_id"], str) and contract["task_id"].strip()
        assert isinstance(contract["trial_kind"], str) and contract["trial_kind"].strip()
        trace = contract["trace"]
        assert isinstance(trace, dict)
        assert trace["minimum_completed_commands"] > 0
        assert trace["minimum_final_messages"] > 0
        required_files = contract["required_files"]
        assert isinstance(required_files, list) and required_files
        assert all(
            isinstance(value, str)
            and value
            and not Path(value).is_absolute()
            and ".." not in Path(value).parts
            for value in required_files
        )
        outcome = contract["outcome_contract"]
        assert isinstance(outcome, dict)
        assert isinstance(outcome["oracle_id"], str) and outcome["oracle_id"].strip()
        required_checks = outcome["required_checks"]
        assert isinstance(required_checks, list) and required_checks
        assert len(required_checks) == len(set(required_checks))
        assert all(isinstance(value, str) and value.strip() for value in required_checks)
        assert "acceptance_commands" not in contract
        assert not list((fixture / "input").glob("acceptance.py"))
