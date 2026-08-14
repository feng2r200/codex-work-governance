"""Project-local Work Governance path helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from re import Pattern


class PathError(ValueError):
    """Raised when a path helper rejects malformed runtime path state."""


def project_root() -> Path:
    """Resolve the physical root of the current Git worktree or local directory."""
    current = Path.cwd().resolve()
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=current,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0 and probe.stdout.strip():
        root = Path(probe.stdout.strip()).resolve()
        if root == current or root in current.parents:
            return root
    for candidate in (current, *current.parents):
        marker = candidate / ".git"
        if marker.exists() or marker.is_symlink():
            return candidate
    return current


def governance_root(root: Path, governance_dir_name: str) -> Path:
    """Return the only project-level root owned by Work Governance."""
    return root / governance_dir_name


def plan_dir(root: Path, governance_dir_name: str, plan_dir_name: str) -> Path:
    """Return the only normal Plan authority directory."""
    return governance_root(root, governance_dir_name) / plan_dir_name


def legacy_plan_dir(root: Path, plan_dir_name: str) -> Path:
    """Return the project-root legacy Plan directory used only by layout migration."""
    return root / plan_dir_name


def legacy_logs_dir(root: Path) -> Path:
    """Return the old shared log root used only by migration compatibility."""
    return root / ".logs"


def logs_dir(root: Path, governance_dir_name: str) -> Path:
    """Return the local append-only process evidence directory."""
    return governance_root(root, governance_dir_name) / "logs"


def worktrees_dir(root: Path, governance_dir_name: str) -> Path:
    """Return the default directory for post-layout worktrees."""
    return governance_root(root, governance_dir_name) / "worktrees"


def cache_dir(root: Path, governance_dir_name: str) -> Path:
    """Return the Plugin-owned project cache directory."""
    return governance_root(root, governance_dir_name) / "cache"


def proposals_dir(root: Path, governance_dir_name: str) -> Path:
    """Return the local non-authoritative proposal directory."""
    return governance_root(root, governance_dir_name) / "proposals"


def evidence_dir(root: Path, governance_dir_name: str) -> Path:
    """Return the local validation evidence directory."""
    return governance_root(root, governance_dir_name) / "evidence"


def runtime_dir(root: Path, governance_dir_name: str) -> Path:
    """Return the local recoverable transaction and staging directory."""
    return governance_root(root, governance_dir_name) / "runtime"


def bootstrap_claim_path(
    root: Path,
    governance_dir_name: str,
    bootstrap_claim_name: str,
) -> Path:
    """Return the durable marker proving who first created the governance root."""
    return runtime_dir(root, governance_dir_name) / bootstrap_claim_name


def legacy_adoption_path(
    root: Path,
    governance_dir_name: str,
    legacy_adoption_name: str,
) -> Path:
    """Return the worktree-local explicit legacy adoption receipt."""
    return runtime_dir(root, governance_dir_name) / legacy_adoption_name


def bootstrap_staging_path(root: Path, bootstrap_staging_name: str) -> Path:
    """Return the sibling used to durably prepare a first-owner claim."""
    return root / bootstrap_staging_name


def version_path(root: Path, governance_dir_name: str) -> Path:
    """Return the versioned layout contract."""
    return governance_root(root, governance_dir_name) / "version.yaml"


def governance_ignore_path(root: Path, governance_dir_name: str) -> Path:
    """Return the versioned local-content ignore contract."""
    return governance_root(root, governance_dir_name) / ".gitignore"


def bootstrap_state_path(root: Path, governance_dir_name: str) -> Path:
    """Return the local exact-build and incremental bootstrap receipt."""
    return governance_root(root, governance_dir_name) / "bootstrap-state.json"


def session_state_dir(
    root: Path,
    session_id: str,
    *,
    governance_dir_name: str,
    sessions_dir_name: str,
    session_id_pattern: Pattern[str],
) -> Path:
    """Return a bounded project-local directory for one Codex session."""
    if session_id_pattern.fullmatch(session_id) is None:
        raise PathError("SESSION_ID_INVALID")
    return runtime_dir(root, governance_dir_name) / sessions_dir_name / session_id


def session_receipt_path(
    root: Path,
    session_id: str,
    *,
    governance_dir_name: str,
    sessions_dir_name: str,
    session_id_pattern: Pattern[str],
) -> Path:
    """Return the canonical READY receipt path for one Codex session."""
    return session_state_dir(
        root,
        session_id,
        governance_dir_name=governance_dir_name,
        sessions_dir_name=sessions_dir_name,
        session_id_pattern=session_id_pattern,
    ) / "bootstrap-state.json"


def session_capability_path(
    root: Path,
    session_id: str,
    *,
    governance_dir_name: str,
    sessions_dir_name: str,
    session_id_pattern: Pattern[str],
    bootstrap_capability_name: str,
) -> Path:
    """Return the bootstrap-only capability path for one Codex session."""
    return session_state_dir(
        root,
        session_id,
        governance_dir_name=governance_dir_name,
        sessions_dir_name=sessions_dir_name,
        session_id_pattern=session_id_pattern,
    ) / bootstrap_capability_name


def scoped_session_paths(
    root: Path,
    name: str,
    *,
    governance_dir_name: str,
    sessions_dir_name: str,
    session_id_pattern: Pattern[str],
) -> list[Path]:
    """List regular session control paths without following session-root symlinks."""
    sessions = runtime_dir(root, governance_dir_name) / sessions_dir_name
    if not sessions.exists() and not sessions.is_symlink():
        return []
    if sessions.is_symlink() or not sessions.is_dir():
        raise PathError("SESSION_STATE_ROOT_INVALID")
    paths: list[Path] = []
    for child in sorted(sessions.iterdir(), key=lambda item: item.name):
        if (
            child.is_symlink()
            or not child.is_dir()
            or session_id_pattern.fullmatch(child.name) is None
        ):
            raise PathError("SESSION_STATE_ENTRY_INVALID")
        candidate = child / name
        if candidate.exists() or candidate.is_symlink():
            paths.append(candidate)
    return paths


def bootstrap_capability_path(
    root: Path,
    governance_dir_name: str,
    bootstrap_capability_name: str,
) -> Path:
    """Return the current SessionStart-only capability used for layout writes."""
    return runtime_dir(root, governance_dir_name) / bootstrap_capability_name


def ready_receipt_paths(
    root: Path,
    *,
    allow_bootstrapping: bool,
    governance_dir_name: str,
    sessions_dir_name: str,
    session_id_pattern: Pattern[str],
    bootstrap_capability_name: str,
) -> list[Path]:
    """Return legacy plus session-scoped receipt candidates."""
    paths = [bootstrap_state_path(root, governance_dir_name)]
    paths.extend(
        scoped_session_paths(
            root,
            "bootstrap-state.json",
            governance_dir_name=governance_dir_name,
            sessions_dir_name=sessions_dir_name,
            session_id_pattern=session_id_pattern,
        )
    )
    if allow_bootstrapping:
        paths.append(
            bootstrap_capability_path(
                root,
                governance_dir_name,
                bootstrap_capability_name,
            )
        )
        paths.extend(
            scoped_session_paths(
                root,
                bootstrap_capability_name,
                governance_dir_name=governance_dir_name,
                sessions_dir_name=sessions_dir_name,
                session_id_pattern=session_id_pattern,
            )
        )
    return paths


def workctl_lock_path(root: Path, governance_dir_name: str) -> Path:
    """Return the stable lock shared by every controller."""
    return governance_root(root, governance_dir_name) / "workctl.lock"


def index_path(root: Path, governance_dir_name: str, plan_dir_name: str) -> Path:
    """Return the active Plan index path."""
    return plan_dir(root, governance_dir_name, plan_dir_name) / "index.yaml"


def plan_relative_path(*parts: str, governance_dir_name: str, plan_dir_name: str) -> str:
    """Build a project-relative path below the canonical Plan directory."""
    return Path(governance_dir_name, plan_dir_name, *parts).as_posix()
