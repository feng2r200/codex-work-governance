from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

paths_module = importlib.import_module("workctl_modules.paths")
PathError = paths_module.PathError


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")


def test_path_helpers_derive_from_configured_governance_root(tmp_path: Path) -> None:
    """Path helpers keep project-local layout names caller-owned."""
    assert paths_module.governance_root(tmp_path, ".wg") == tmp_path / ".wg"
    assert paths_module.plan_dir(tmp_path, ".wg", "_Plan") == tmp_path / ".wg" / "_Plan"
    assert paths_module.legacy_plan_dir(tmp_path, "_Plan") == tmp_path / "_Plan"
    assert paths_module.cache_dir(tmp_path, ".wg") == tmp_path / ".wg" / "cache"
    assert paths_module.bootstrap_claim_path(tmp_path, ".wg", "claim.json") == (
        tmp_path / ".wg" / "runtime" / "claim.json"
    )
    assert paths_module.plan_relative_path(
        ".evidence",
        "record.json",
        governance_dir_name=".wg",
        plan_dir_name="_Plan",
    ) == ".wg/_Plan/.evidence/record.json"


def test_session_paths_validate_session_ids_and_entries(tmp_path: Path) -> None:
    """Session path helpers reject malformed session roots and entries."""
    assert paths_module.session_state_dir(
        tmp_path,
        "session-alpha",
        governance_dir_name=".wg",
        sessions_dir_name="sessions",
        session_id_pattern=SESSION_ID_RE,
    ) == tmp_path / ".wg" / "runtime" / "sessions" / "session-alpha"

    try:
        paths_module.session_state_dir(
            tmp_path,
            "bad/session",
            governance_dir_name=".wg",
            sessions_dir_name="sessions",
            session_id_pattern=SESSION_ID_RE,
        )
    except PathError as exc:
        assert str(exc) == "SESSION_ID_INVALID"
    else:
        raise AssertionError("malformed session id was accepted")

    sessions = tmp_path / ".wg" / "runtime" / "sessions"
    (sessions / "session-alpha").mkdir(parents=True)
    (sessions / "session-alpha" / "bootstrap-state.json").write_text("{}", encoding="utf-8")
    (sessions / "bad name").mkdir()
    try:
        paths_module.scoped_session_paths(
            tmp_path,
            "bootstrap-state.json",
            governance_dir_name=".wg",
            sessions_dir_name="sessions",
            session_id_pattern=SESSION_ID_RE,
        )
    except PathError as exc:
        assert str(exc) == "SESSION_STATE_ENTRY_INVALID"
    else:
        raise AssertionError("malformed session entry was accepted")


def test_ready_receipt_paths_include_bootstrap_capabilities_when_allowed(
    tmp_path: Path,
) -> None:
    """READY receipt lookup preserves legacy and session-scoped candidate order."""
    sessions = tmp_path / ".wg" / "runtime" / "sessions" / "session-alpha"
    sessions.mkdir(parents=True)
    (sessions / "bootstrap-state.json").write_text("{}", encoding="utf-8")
    (sessions / "bootstrap-capability.json").write_text("{}", encoding="utf-8")

    assert paths_module.ready_receipt_paths(
        tmp_path,
        allow_bootstrapping=True,
        governance_dir_name=".wg",
        sessions_dir_name="sessions",
        session_id_pattern=SESSION_ID_RE,
        bootstrap_capability_name="bootstrap-capability.json",
    ) == [
        tmp_path / ".wg" / "bootstrap-state.json",
        sessions / "bootstrap-state.json",
        tmp_path / ".wg" / "runtime" / "bootstrap-capability.json",
        sessions / "bootstrap-capability.json",
    ]
