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
        "cache_dir",
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


def test_legacy_root_literals_are_confined_to_controller_compatibility() -> None:
    """Prevent new normal writers to root .logs or .worktree."""
    controller = KERNEL_CONTROLLER.read_text(encoding="utf-8")
    path_helpers = PATH_HELPERS.read_text(encoding="utf-8")

    assert controller.count('root / ".logs"') == 0
    assert path_helpers.count('root / ".logs"') == 1
    assert controller.count('Path(".logs")') == 1
    assert 'root / ".worktree"' not in controller
    assert 'Path(".worktree")' not in controller


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


def test_controller_runtime_bootstrap_has_no_uv_script_dependency() -> None:
    """Runtime entrypoints must not require UV script execution."""
    wrapper = CONTROLLER.read_text(encoding="utf-8")
    controller = KERNEL_CONTROLLER.read_text(encoding="utf-8")

    assert "uv run" not in wrapper
    assert "# /// script" not in wrapper
    assert "sys.dont_write_bytecode = True" in wrapper
    assert 'VENDOR_DIR = SCRIPT_DIR / "vendor"' in wrapper
    assert "yaml_compat" in controller


def test_public_contract_explains_proposal_and_direct_tool_boundaries() -> None:
    """Keep recovery and local-evidence claims aligned with the hookless runtime."""
    readme = README.read_text(encoding="utf-8")
    privacy = PRIVACY.read_text(encoding="utf-8")
    readme_flat = " ".join(readme.split())
    privacy_flat = " ".join(privacy.split())

    assert "registered `workctl` executable" in readme
    assert "does not require Codex lifecycle hooks" in readme_flat
    assert "The directory name `proposals/` alone is not ownership evidence" in readme_flat
    assert "it never places proposals under the canonical Plan root" in readme_flat
    assert "bounded local command context" in privacy_flat
    assert "migration does not apply it or accept its confirmations" in privacy_flat
    assert "raw prompt content is not copied into those records" in privacy_flat
