"""Static layout-1 path contract tests."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts" / "workctl.py"
BOOTSTRAP = REPOSITORY_ROOT / "plugins" / "work-governance" / "hooks" / "session_start.py"


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
    controller = CONTROLLER.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    assert controller.count('root / ".logs"') == 1
    assert controller.count('Path(".logs")') == 1
    assert ".worktree" not in controller
    assert bootstrap.count('project_root / ".logs"') == 1
    assert bootstrap.count('project_root / "_Plan"') == 1
    assert ".worktree" not in bootstrap


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


def test_controller_dependency_and_project_lock_are_exactly_pinned() -> None:
    """Bootstrap prewarm and repository validation resolve the same PyYAML."""
    controller = CONTROLLER.read_text(encoding="utf-8")
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8")

    assert '# dependencies = ["pyyaml==6.0.3"]' in controller
    assert '"pyyaml==6.0.3"' in pyproject
    assert 'specifier = "==6.0.3"' in lock
