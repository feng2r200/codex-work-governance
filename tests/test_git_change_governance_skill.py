"""Contract tests for Git change governance instructions."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = (
    REPOSITORY_ROOT
    / "plugins"
    / "work-governance"
    / "skills"
    / "git-change-governance"
    / "SKILL.md"
)


def test_worktree_default_is_project_local_and_external_paths_are_exceptional() -> None:
    """Keep worktree isolation inside the project unless an exception is justified."""
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "<project-root>/.worktree/<task-or-branch-slug>" in skill
    assert "[A-Za-z0-9._-]" in skill
    assert "trim leading and trailing `.`, `-`, and\n  `_`" in skill
    assert "reject an empty slug, `.` or `..`" in skill
    assert "A slug must be one path component" in skill
    assert 'repo_root=$(cd "$(git rev-parse --show-toplevel)" && pwd -P)' in skill
    assert 'test ! -L "$worktree_root"' in skill
    assert 'worktree_root=$(cd "$worktree_root" && pwd -P)' in skill
    assert 'test "$(dirname "$worktree_root")" = "$repo_root"' in skill
    assert 'test ! -e "$target" && test ! -L "$target"' in skill
    assert "nor appears in\n  `git worktree list --porcelain`" in skill
    assert "Use a worktree path outside the project root only" in skill
    assert "sandbox/permission impact" in skill


def test_worktree_commands_preserve_explicit_branch_semantics() -> None:
    """Do not let the default path silently choose a branch or its start point."""
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert 'git worktree add "$target" <existing-branch>' in skill
    assert 'git worktree add -b <new-branch> "$target" <verified-start-point>' in skill
    assert "never silently default the start point to the current `HEAD`" in skill
    assert "Use detached mode only when the task explicitly calls for it" in skill
    assert 'git worktree add "$repo_root/.worktree/<task-or-branch-slug>" -b' not in skill


def test_worktree_permission_and_cleanup_boundaries_are_explicit() -> None:
    """Cover shared Git metadata and safe removal of registered worktrees."""
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "git rev-parse --path-format=absolute --git-common-dir" in skill
    assert "both that common Git directory and the target" in skill
    assert "git worktree remove" in skill
    assert "checking its dirty, locked, and associated-branch state" in skill
    assert "Never recursively" in skill
    assert "Deleting the associated branch is a separate" in skill


def test_repository_ignores_the_project_local_worktree_root() -> None:
    """Prevent nested worktrees from appearing as ordinary repository changes."""
    ignore_entries = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "/.worktree/" in ignore_entries
