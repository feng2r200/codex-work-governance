"""Static layout-1 path contract tests."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts" / "workctl.py"
KERNEL_CONTROLLER = (
    REPOSITORY_ROOT
    / "plugins"
    / "work-governance"
    / "scripts"
    / "workctl_modules"
    / "kernel"
    / "controller.py"
)
PATH_HELPERS = (
    REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts" / "workctl_modules" / "paths.py"
)
BOOTSTRAP = REPOSITORY_ROOT / "plugins" / "work-governance" / "hooks" / "session_start.py"
README = REPOSITORY_ROOT / "README.md"
PRIVACY = REPOSITORY_ROOT / "PRIVACY.md"


def test_all_normal_controller_paths_derive_from_governance_root(
    tmp_path: Path,
) -> None:
    """Plan and local runtime helpers share the sole project-level root."""
    namespace = runpy.run_path(str(CONTROLLER))
    governance_root = cast(Callable[[Path], Path], namespace["governance_root"])
    helpers = (
        "plan_dir",
        "logs_dir",
        "worktrees_dir",
        "uv_cache_dir",
        "proposals_dir",
        "evidence_dir",
        "runtime_dir",
        "version_path",
        "governance_ignore_path",
        "bootstrap_state_path",
        "workctl_lock_path",
    )
    governance = governance_root(tmp_path)

    assert governance == tmp_path / ".work-governance"
    for name in helpers:
        helper = cast(Callable[[Path], Path], namespace[name])
        assert helper(tmp_path).is_relative_to(governance)


def test_legacy_root_literals_are_confined_to_bootstrap_compatibility() -> None:
    """Prevent new normal writers to root .logs or .worktree."""
    controller = KERNEL_CONTROLLER.read_text(encoding="utf-8")
    path_helpers = PATH_HELPERS.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    assert controller.count('root / ".logs"') == 0
    assert path_helpers.count('root / ".logs"') == 1
    assert controller.count('Path(".logs")') == 1
    assert 'root / ".worktree"' not in controller
    assert 'Path(".worktree")' not in controller
    assert bootstrap.count('project_root / ".logs"') == 1
    assert bootstrap.count('project_root / "_Plan"') == 1
    assert 'project_root / ".worktree"' not in bootstrap
    assert 'Path(".worktree")' not in bootstrap


def test_public_contracts_name_only_canonical_normal_paths() -> None:
    """Old names may appear only in explicit legacy compatibility statements."""
    lifecycle = (
        REPOSITORY_ROOT / "plugins" / "work-governance" / "skills" / "work-lifecycle" / "SKILL.md"
    ).read_text(encoding="utf-8")
    git_skill = (
        REPOSITORY_ROOT
        / "plugins"
        / "work-governance"
        / "skills"
        / "git-change-governance"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert ".work-governance/_Plan/index.yaml" in lifecycle
    assert ".logs/" not in lifecycle
    assert "<project-root>/.work-governance/worktrees/<task-or-branch-slug>" in git_skill
    assert 'worktree_root="$repo_root/.worktree"' not in git_skill


def test_controller_runtime_bootstrap_has_no_external_script_dependency() -> None:
    """Cold hook bootstrap must not require fetching PyYAML into a new cache."""
    wrapper = CONTROLLER.read_text(encoding="utf-8")
    controller = KERNEL_CONTROLLER.read_text(encoding="utf-8")

    assert "# dependencies = []" in wrapper
    assert "yaml_compat" in controller


def test_public_contract_explains_proposal_and_executed_hook_boundaries() -> None:
    """Keep the public recovery and local-evidence claims aligned with 1.0.2."""
    readme = README.read_text(encoding="utf-8")
    privacy = PRIVACY.read_text(encoding="utf-8")
    readme_flat = " ".join(readme.split())
    privacy_flat = " ".join(privacy.split())

    assert "`hook=executed`" in readme
    assert "Do not reinterpret such output as a hook-trust failure" in readme_flat
    assert "The directory name `proposals/` alone is not ownership evidence" in readme_flat
    assert "it never places proposals under the canonical Plan root" in readme_flat
    assert "bounded SessionStart source and session identifier" in privacy_flat
    assert "migration does not apply it or accept its confirmations" in privacy_flat
    assert "one session cannot supersede another" in privacy_flat
    assert "raw prompt content is not copied into those records" in privacy_flat
