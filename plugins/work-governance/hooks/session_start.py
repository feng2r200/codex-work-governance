#!/usr/bin/env python3
# ruff: noqa: UP006, UP017, UP035, UP045
"""Prepare Work Governance layout state for one Codex session.

This hook intentionally uses only the Python standard library. It verifies that
the bundled controller can start from the project-local UV cache, performs one
bounded prewarm only when script dependencies are unavailable, then runs every
state-changing or validating controller command offline.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

BOOTSTRAP_ACTION_REVISION = 5
SUPPORTED_BOOTSTRAP_ACTION_REVISIONS = {2, 3, 4, BOOTSTRAP_ACTION_REVISION}
LEGACY_MIGRATION_ACTION_REVISION = 4
SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS = {2, 3, LEGACY_MIGRATION_ACTION_REVISION}
BOOTSTRAP_CONTRACT_VERSION = 1
GOVERNANCE_DIR = ".work-governance"
LOCAL_DIRECTORIES = (
    "logs",
    "worktrees",
    "cache/uv",
    "proposals",
    "evidence/bootstrap",
    "runtime",
)
RECEIPT_NAME = "bootstrap-state.json"
CLAIM_NAME = "bootstrap-claim.json"
CAPABILITY_NAME = "bootstrap-capability.json"
SESSIONS_DIR_NAME = "sessions"
LEGACY_ADOPTION_NAME = "legacy-adoption.json"
FAILURE_JOURNAL_NAME = "bootstrap-failure-journal.json"
BOOTSTRAP_STAGING_NAME = ".work-governance.bootstrap"
CLAIM_KEYS = {
    "schema_version",
    "kind",
    "bootstrap_contract_version",
    "action_revision",
    "project_root",
    "created_at",
    "creator",
    "controller_sha256",
    "project_input_sha256",
}
BLOCKED_RECEIPT_KEYS = {
    "schema_version",
    "bootstrap_contract_version",
    "action_revision",
    "updated_at",
    "status",
    "reason",
    "plugin_build",
    "plugin_manifest_sha256",
    "project_input_sha256",
    "claim_sha256",
    "evidence_ref",
    "evidence_sha256",
}
BLOCKED_EVIDENCE_CONTEXT_KEYS = {"hook_source", "session_id"}
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
HOOK_SOURCES = {"startup", "resume", "clear", "compact"}
BOOTSTRAP_EVIDENCE_NAME_RE = re.compile(r"^\d{8}T\d{6}\.\d{6}Z-\d+\.json$")
LAYOUT_TRANSACTION_RE = re.compile(
    r"^LAY-\d{8}T\d{6}Z-[0-9a-f]{8}(?:-[0-9a-f]{8}(?:[0-9a-f]{8}){0,3})?$"
)
ACTIVE_LAYOUT_JOURNAL_KEYS = {
    "schema_version",
    "kind",
    "transaction_id",
    "status",
    "created_at",
    "updated_at",
    "active_plan_id",
    "active_plan_path",
    "legacy_manifest",
    "legacy_manifest_sha256",
    "legacy_proposals_manifest",
    "legacy_proposals_sha256",
    "legacy_adoption_sha256",
    "git_baseline",
    "paths",
    "completed_operations",
    "new_layout_manifest",
    "new_layout_baseline_sha256",
    "conversion_table",
    "conversion_table_sha256",
    "log_files",
    "proposal_trees",
    "new_proposals_baseline_sha256",
}
LEGACY_ADOPTION_KEYS = {
    "schema_version",
    "kind",
    "action_revision",
    "project_root",
    "worktree_identity",
    "active_plan_id",
    "active_plan_path",
    "legacy_manifest_sha256",
    "controller_sha256",
    "confirmation_ref",
    "created_at",
}
PLAN_ID_RE = re.compile(r"^PLAN-\d{8}-\d{3}$")
MIGRATION_ID_RE = re.compile(r"^MIG-\d{8}-\d{3}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REFERENCE_RE = re.compile(r"^(user|project|git|runtime|evidence|handoff|codex-plugin-list):\S+$")


class BootstrapError(RuntimeError):
    """A fail-closed bootstrap condition safe to expose as short context."""


def legacy_logs_path(project_root: Path) -> Path:
    """Return the legacy shared log root for bootstrap fingerprinting only."""
    return project_root / ".logs"


def legacy_plan_path(project_root: Path) -> Path:
    """Return the legacy authority root for bootstrap fingerprinting only."""
    return project_root / "_Plan"


def reject_symlink_components(project_root: Path, path: Path) -> None:
    """Reject every existing symlink in one lexical project-local path."""
    try:
        relative = path.relative_to(project_root)
    except ValueError as exc:
        raise BootstrapError("BOOTSTRAP_PATH_OUTSIDE_PROJECT") from exc
    current = project_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise BootstrapError(
                "GOVERNANCE_CONTROL_PATH_SYMLINK: " + current.relative_to(project_root).as_posix()
            )


def strict_bootstrap_evidence_relative(raw_path: str) -> Path:
    """Parse one direct bootstrap evidence child without traversal segments."""
    path = Path(raw_path)
    expected_parent = Path(GOVERNANCE_DIR) / "evidence" / "bootstrap"
    if (
        not raw_path
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parent != expected_parent
        or BOOTSTRAP_EVIDENCE_NAME_RE.fullmatch(path.name) is None
    ):
        raise BootstrapError("INVALID_BOOTSTRAP_EVIDENCE_PATH")
    return path


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp without fractional seconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA256 digest."""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one regular file without following a symlink."""
    if path.is_symlink() or not path.is_file():
        raise BootstrapError(f"BOOTSTRAP_INPUT_NOT_REGULAR: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(value: Any) -> str:
    """Hash one JSON-compatible value using a deterministic encoding."""
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def path_manifest(path: Path) -> List[Dict[str, Any]]:
    """Describe one path tree without following symlinks."""
    if not path.exists() and not path.is_symlink():
        return []
    if path.is_symlink():
        return [{"path": ".", "kind": "symlink", "target": os.readlink(str(path))}]
    if path.is_file():
        return [
            {
                "path": ".",
                "kind": "file",
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        ]
    if not path.is_dir():
        return [{"path": ".", "kind": "other"}]
    entries: List[Dict[str, Any]] = [{"path": ".", "kind": "directory"}]
    for base, directory_names, file_names in os.walk(str(path), followlinks=False):
        base_path = Path(base)
        directory_names.sort()
        file_names.sort()
        retained_directories: List[str] = []
        for name in directory_names:
            candidate = base_path / name
            relative = candidate.relative_to(path).as_posix()
            if candidate.is_symlink():
                entries.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "target": os.readlink(str(candidate)),
                    }
                )
            else:
                retained_directories.append(name)
                entries.append({"path": relative, "kind": "directory"})
        directory_names[:] = retained_directories
        for name in file_names:
            candidate = base_path / name
            relative = candidate.relative_to(path).as_posix()
            if candidate.is_symlink():
                entries.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "target": os.readlink(str(candidate)),
                    }
                )
            elif candidate.is_file():
                entries.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "size": candidate.stat().st_size,
                        "sha256": sha256_file(candidate),
                    }
                )
            else:
                entries.append({"path": relative, "kind": "other"})
    return sorted(entries, key=lambda item: (str(item["path"]), str(item["kind"])))


def regular_tree_manifest(
    path: Path,
    *,
    exclude_names: Iterable[str] = (),
) -> Optional[List[Dict[str, Any]]]:
    """Return a regular directory manifest without its root or excluded exact names."""
    manifest = path_manifest(path)
    if (
        not manifest
        or manifest[0] != {"path": ".", "kind": "directory"}
        or any(entry.get("kind") not in {"directory", "file"} for entry in manifest[1:])
    ):
        return None
    excluded = set(exclude_names)
    return [entry for entry in manifest[1:] if Path(str(entry.get("path"))).name not in excluded]


def worktree_identity(project_root: Path) -> Dict[str, Any]:
    """Return the same physical Git-worktree identity recorded by the controller."""
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return {"repository": False, "project_root": project_root.resolve().as_posix()}
    commands = {
        "project_root": ["git", "rev-parse", "--show-toplevel"],
        "git_dir": ["git", "rev-parse", "--absolute-git-dir"],
        "git_common_dir": [
            "git",
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
    }
    values: Dict[str, Any] = {}
    for field, command in commands.items():
        result = subprocess.run(
            command,
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise BootstrapError("LEGACY_ADOPTION_GIT_IDENTITY_UNAVAILABLE")
        values[field] = Path(result.stdout.strip()).resolve().as_posix()
    if values["project_root"] != project_root.resolve().as_posix():
        raise BootstrapError("LEGACY_ADOPTION_PROJECT_ROOT_MISMATCH")
    return {"repository": True, **values}


def validate_active_adoption(
    governance: Path,
    adoption: Path,
    journal: Mapping[str, Any],
) -> None:
    """Require the formal worktree-bound adoption contract, not only its self-reported hash."""
    try:
        payload = json.loads(adoption.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID") from exc
    project_root = governance.parent
    expected = {
        "schema_version": 1,
        "kind": "work-governance-legacy-adoption",
        "project_root": project_root.resolve().as_posix(),
        "worktree_identity": worktree_identity(project_root),
        "active_plan_id": journal.get("active_plan_id"),
        "active_plan_path": journal.get("active_plan_path"),
        "legacy_manifest_sha256": journal.get("legacy_manifest_sha256"),
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != LEGACY_ADOPTION_KEYS
        or any(payload.get(field) != value for field, value in expected.items())
        or payload.get("action_revision") not in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS
        or re.fullmatch(r"[0-9a-f]{64}", str(payload.get("controller_sha256"))) is None
        or not isinstance(payload.get("confirmation_ref"), str)
        or REFERENCE_RE.fullmatch(str(payload.get("confirmation_ref"))) is None
        or not isinstance(payload.get("created_at"), str)
        or not payload.get("created_at")
    ):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")


def validate_active_migration_proof(
    proof: Path,
    journal: Mapping[str, Any],
) -> None:
    """Validate the exact standard-library-readable proof and all journal cross-bindings."""
    expected_keys = [
        "schema_version",
        "kind",
        "transaction_id",
        "status",
        "legacy_manifest_sha256",
        "legacy_adoption_sha256",
        "conversion_table_sha256",
        "legacy_proposals_sha256",
        "new_proposals_baseline_sha256",
        "created_at",
    ]
    lines = proof.read_text(encoding="utf-8").splitlines()
    values: Dict[str, str] = {}
    if len(lines) != len(expected_keys):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    for index, key in enumerate(expected_keys):
        match = re.fullmatch(rf"{re.escape(key)}:(?: (.*))?", lines[index])
        if match is None or match.group(1) is None:
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        values[key] = str(match.group(1)).strip("'\"")
    expected = {
        "schema_version": "1",
        "kind": "layout-migration-proof",
        "transaction_id": str(journal.get("transaction_id")),
        "status": "prepared",
        "legacy_manifest_sha256": str(journal.get("legacy_manifest_sha256")),
        "legacy_adoption_sha256": str(journal.get("legacy_adoption_sha256")),
        "conversion_table_sha256": str(journal.get("conversion_table_sha256")),
        "legacy_proposals_sha256": str(journal.get("legacy_proposals_sha256")),
        "new_proposals_baseline_sha256": str(journal.get("new_proposals_baseline_sha256")),
    }
    if any(values.get(field) != value for field, value in expected.items()) or not values.get(
        "created_at"
    ):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")


def load_hook_input() -> Dict[str, Any]:
    """Parse the SessionStart JSON object from stdin."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("INVALID_SESSION_START_INPUT") from exc
    if not isinstance(payload, dict):
        raise BootstrapError("INVALID_SESSION_START_INPUT")
    if payload.get("hook_event_name") != "SessionStart":
        raise BootstrapError("UNEXPECTED_HOOK_EVENT")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise BootstrapError("SESSION_START_CWD_REQUIRED")
    return payload


def discover_project_root(cwd: Path) -> Path:
    """Use the nearest Git root when present, otherwise the session cwd."""
    resolved = cwd.resolve()
    if not resolved.is_dir():
        raise BootstrapError("SESSION_START_CWD_INVALID")
    for candidate in (resolved, *resolved.parents):
        git_marker = candidate / ".git"
        if git_marker.exists() or git_marker.is_symlink():
            return candidate
    return resolved


def plugin_root() -> Path:
    """Resolve the installed plugin root supplied by Codex."""
    raw = os.environ.get("PLUGIN_ROOT")
    root = Path(raw).resolve() if raw else Path(__file__).resolve().parents[1]
    manifest = root / ".codex-plugin" / "plugin.json"
    controller = root / "scripts" / "workctl.py"
    if not manifest.is_file() or not controller.is_file():
        raise BootstrapError("PLUGIN_ROOT_INVALID")
    return root


def plugin_build(root: Path) -> str:
    """Read the exact build only from plugin.json."""
    try:
        payload = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("PLUGIN_MANIFEST_INVALID") from exc
    version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not version:
        raise BootstrapError("PLUGIN_VERSION_MISSING")
    return version


def plugin_manifest_digest(root: Path) -> str:
    """Fingerprint the complete installed plugin payload."""
    return stable_digest(path_manifest(root))


def bootstrap_claim_input_digest(project_root: Path) -> str:
    """Fingerprint project inputs before claiming the canonical root."""
    paths = (
        ("legacy-plan", legacy_plan_path(project_root)),
        ("legacy-logs", legacy_logs_path(project_root)),
        ("agents", project_root / "AGENTS.md"),
        ("claude", project_root / "CLAUDE.md"),
    )
    return stable_digest([{"name": name, "manifest": path_manifest(path)} for name, path in paths])


def validate_bootstrap_claim(project_root: Path, claim: Path) -> None:
    """Require an exact first-owner claim before extending an uncommitted root."""
    reject_symlink_components(project_root, claim)
    if claim.is_symlink() or not claim.is_file():
        raise BootstrapError("GOVERNANCE_ROOT_OWNERSHIP_UNPROVEN")
    try:
        payload = json.loads(claim.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("GOVERNANCE_BOOTSTRAP_CLAIM_INVALID") from exc
    if not isinstance(payload, dict) or set(payload) != CLAIM_KEYS:
        raise BootstrapError("GOVERNANCE_BOOTSTRAP_CLAIM_INVALID")
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != "work-governance-bootstrap-claim"
        or payload.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
        or payload.get("action_revision") not in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS
        or payload.get("project_root") != project_root.resolve().as_posix()
        or payload.get("creator") not in {"workctl", "session-start"}
        or not isinstance(payload.get("created_at"), str)
        or re.fullmatch(r"[0-9a-f]{64}", str(payload.get("controller_sha256"))) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(payload.get("project_input_sha256"))) is None
    ):
        raise BootstrapError("GOVERNANCE_BOOTSTRAP_CLAIM_INVALID")


def rename_directory_noreplace(source: Path, target: Path) -> None:
    """Atomically activate a prepared root without replacing any target."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    if sys.platform == "darwin" and hasattr(library, "renamex_np"):
        result = library.renamex_np(
            ctypes.c_char_p(source_bytes),
            ctypes.c_char_p(target_bytes),
            ctypes.c_uint(0x00000004),
        )
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        result = library.renameat2(
            ctypes.c_int(-100),
            ctypes.c_char_p(source_bytes),
            ctypes.c_int(-100),
            ctypes.c_char_p(target_bytes),
            ctypes.c_uint(1),
        )
    else:
        raise BootstrapError("ATOMIC_NOREPLACE_RENAME_UNAVAILABLE")
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise BootstrapError("GOVERNANCE_ROOT_OWNERSHIP_CONFLICT")
        raise BootstrapError("GOVERNANCE_ROOT_ACTIVATION_FAILED: " + os.strerror(error_number))


def create_bootstrap_claim(
    project_root: Path,
    staging: Path,
    *,
    controller_sha256: str,
    input_digest: str,
) -> None:
    """Exclusively create or validate the local ownership claim."""
    runtime = staging / "runtime"
    runtime.mkdir(exist_ok=True)
    claim = runtime / CLAIM_NAME
    payload = {
        "schema_version": 1,
        "kind": "work-governance-bootstrap-claim",
        "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
        "action_revision": LEGACY_MIGRATION_ACTION_REVISION,
        "project_root": project_root.resolve().as_posix(),
        "created_at": utc_now(),
        "creator": "session-start",
        "controller_sha256": controller_sha256,
        "project_input_sha256": input_digest,
    }
    try:
        descriptor = os.open(
            str(claim),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        validate_bootstrap_claim(project_root, claim)
        return
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory_descriptor = os.open(str(runtime), os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        if claim.exists():
            claim.unlink()
        raise


def validate_layout_version(project_root: Path, governance: Path) -> None:
    """Validate the complete committed layout contract without third-party YAML."""
    version = governance / "version.yaml"
    ignore = governance / ".gitignore"
    if (
        version.is_symlink()
        or not version.is_file()
        or ignore.is_symlink()
        or not ignore.is_file()
        or ignore.read_text(encoding="utf-8")
        != "/logs/\n/worktrees/\n/cache/\n/proposals/\n/evidence/\n/runtime/\n"
        "/bootstrap-state.json\n/workctl.lock\n"
    ):
        raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
    expected = [
        (0, "schema_version"),
        (0, "layout_version"),
        (0, "bootstrap_contract_version"),
        (0, "plugin_compatibility"),
        (0, "legacy_migration_action_revision"),
        (0, "migration"),
        (2, "status"),
        (2, "transaction_id"),
        (2, "legacy_manifest_sha256"),
        (2, "new_layout_baseline_sha256"),
        (2, "completion_evidence"),
        (4, "kind"),
        (4, "path"),
        (4, "sha256"),
        (4, "completed_at"),
    ]
    parsed: Dict[str, str] = {}
    lines = version.read_text(encoding="utf-8").splitlines()
    if len(lines) != len(expected):
        raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
    for index, (indent, key) in enumerate(expected):
        line = lines[index]
        match = re.fullmatch(rf" {{{indent}}}{re.escape(key)}:(?: (.*))?", line)
        if match is None:
            raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
        value = match.group(1)
        if value is not None:
            parsed[key] = value.strip("'\"")
    if (
        parsed.get("schema_version") != "1"
        or parsed.get("layout_version") != "1"
        or parsed.get("bootstrap_contract_version") != "1"
        or parsed.get("plugin_compatibility") != ">=1.0.0,<2.0.0"
        or parsed.get("legacy_migration_action_revision")
        not in {str(value) for value in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS}
        or parsed.get("status") not in {"migrated", "not_applicable"}
        or re.fullmatch(r"[0-9a-f]{64}", parsed.get("legacy_manifest_sha256", "")) is None
        or re.fullmatch(r"[0-9a-f]{64}", parsed.get("new_layout_baseline_sha256", "")) is None
        or re.fullmatch(r"[0-9a-f]{64}", parsed.get("sha256", "")) is None
        or not parsed.get("completed_at")
    ):
        raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
    if parsed["status"] == "migrated":
        transaction_id = parsed.get("transaction_id", "")
        expected_path = f".work-governance/_Plan/.migrations/{transaction_id}.yaml"
        proof = project_root / parsed.get("path", "")
        if (
            LAYOUT_TRANSACTION_RE.fullmatch(transaction_id) is None
            or parsed.get("kind") != "migration-proof"
            or parsed.get("path") != expected_path
            or proof.is_symlink()
            or not proof.is_file()
            or sha256_file(proof) != parsed["sha256"]
        ):
            raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
        legacy_proof_expected = [
            (0, "schema_version"),
            (0, "kind"),
            (0, "transaction_id"),
            (0, "status"),
            (0, "legacy_manifest_sha256"),
            (0, "legacy_adoption_sha256"),
            (0, "conversion_table_sha256"),
            (0, "created_at"),
        ]
        proposal_proof_expected = [
            *legacy_proof_expected[:-1],
            (0, "legacy_proposals_sha256"),
            (0, "new_proposals_baseline_sha256"),
            legacy_proof_expected[-1],
        ]
        proof_lines = proof.read_text(encoding="utf-8").splitlines()
        if len(proof_lines) == len(legacy_proof_expected):
            proof_expected = legacy_proof_expected
        elif len(proof_lines) == len(proposal_proof_expected):
            proof_expected = proposal_proof_expected
        else:
            raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
        proof_values: Dict[str, str] = {}
        for index, (indent, key) in enumerate(proof_expected):
            line = proof_lines[index]
            match = re.fullmatch(rf" {{{indent}}}{re.escape(key)}:(?: (.*))?", line)
            if match is None or match.group(1) is None:
                raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
            proof_values[key] = str(match.group(1)).strip("'\"")
        if (
            proof_values.get("schema_version") != "1"
            or proof_values.get("kind") != "layout-migration-proof"
            or proof_values.get("transaction_id") != transaction_id
            or proof_values.get("status") != "prepared"
            or proof_values.get("legacy_manifest_sha256") != parsed.get("legacy_manifest_sha256")
            or re.fullmatch(r"[0-9a-f]{64}", proof_values.get("legacy_adoption_sha256", "")) is None
            or re.fullmatch(r"[0-9a-f]{64}", proof_values.get("conversion_table_sha256", ""))
            is None
            or (
                proof_expected == proposal_proof_expected
                and (
                    re.fullmatch(
                        r"[0-9a-f]{64}",
                        proof_values.get("legacy_proposals_sha256", ""),
                    )
                    is None
                    or re.fullmatch(
                        r"[0-9a-f]{64}",
                        proof_values.get("new_proposals_baseline_sha256", ""),
                    )
                    is None
                )
            )
            or not proof_values.get("created_at")
        ):
            raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
    else:
        receipt = {
            "action": "layout-not-applicable",
            "completed_at": parsed["completed_at"],
            "legacy_classification": "NOT_APPLICABLE",
        }
        if (
            parsed.get("transaction_id") != "not-applicable"
            or parsed.get("kind") != "not-applicable-receipt"
            or parsed.get("path") != "not-applicable"
            or stable_digest(receipt) != parsed["sha256"]
        ):
            raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")


def validate_blocked_record(governance: Path) -> set[Path]:
    """Validate one claim-bound blocked receipt and its exact evidence file."""
    receipt_path = governance / RECEIPT_NAME
    reject_symlink_components(governance.parent, receipt_path)
    if not receipt_path.exists() and not receipt_path.is_symlink():
        return set()
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_RECEIPT_INVALID")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_RECEIPT_INVALID") from exc
    claim = governance / "runtime" / CLAIM_NAME
    reject_symlink_components(governance.parent, claim)
    if (
        not isinstance(receipt, dict)
        or set(receipt) != BLOCKED_RECEIPT_KEYS
        or receipt.get("schema_version") != 1
        or receipt.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
        or receipt.get("action_revision") not in SUPPORTED_BOOTSTRAP_ACTION_REVISIONS
        or receipt.get("status") != "ENVIRONMENT_BLOCKED"
        or not isinstance(receipt.get("updated_at"), str)
        or not isinstance(receipt.get("reason"), str)
        or not isinstance(receipt.get("plugin_build"), str)
        or re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("plugin_manifest_sha256"))) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("project_input_sha256"))) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("claim_sha256"))) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("evidence_sha256"))) is None
        or not claim.is_file()
        or sha256_file(claim) != receipt.get("claim_sha256")
    ):
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_RECEIPT_INVALID")
    evidence_ref = receipt.get("evidence_ref")
    expected_prefix = f"evidence:{GOVERNANCE_DIR}/evidence/bootstrap/"
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith(expected_prefix):
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_INVALID")
    try:
        evidence_relative = strict_bootstrap_evidence_relative(
            evidence_ref.removeprefix("evidence:")
        )
    except BootstrapError as exc:
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_INVALID") from exc
    evidence_path = governance.parent / evidence_relative
    reject_symlink_components(governance.parent, evidence_path)
    if (
        evidence_path.is_symlink()
        or not evidence_path.is_file()
        or sha256_file(evidence_path) != receipt.get("evidence_sha256")
    ):
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_INVALID")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_INVALID") from exc
    legacy_evidence_keys = (BLOCKED_RECEIPT_KEYS - {"evidence_sha256"}) | {"commands"}
    current_evidence_keys = legacy_evidence_keys | BLOCKED_EVIDENCE_CONTEXT_KEYS
    evidence_keys = set(evidence) if isinstance(evidence, dict) else set()
    if (
        not isinstance(evidence, dict)
        or evidence_keys not in (legacy_evidence_keys, current_evidence_keys)
        or (
            receipt.get("action_revision") == BOOTSTRAP_ACTION_REVISION
            and evidence_keys != current_evidence_keys
        )
        or (
            evidence_keys == current_evidence_keys
            and (
                evidence.get("hook_source") not in {*HOOK_SOURCES, None}
                or (
                    evidence.get("session_id") is not None
                    and SESSION_ID_RE.fullmatch(str(evidence.get("session_id"))) is None
                )
            )
        )
        or not isinstance(evidence.get("commands"), list)
        or any(evidence.get(key) != receipt.get(key) for key in receipt if key != "evidence_sha256")
    ):
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_INVALID")
    return {evidence_path.resolve()}


def validate_blocked_evidence_history(
    governance: Path,
    current_evidence: set[Path],
) -> set[Path]:
    """Validate prior non-authoritative blocked evidence before layout commitment."""
    project_root = governance.parent
    bootstrap = governance / "evidence" / "bootstrap"
    if not bootstrap.exists() and not bootstrap.is_symlink():
        return current_evidence
    if bootstrap.is_symlink() or not bootstrap.is_dir():
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID")
    evidence_children = tuple(sorted(bootstrap.iterdir()))
    if evidence_children and len(current_evidence) != 1:
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID")

    claim = governance / "runtime" / CLAIM_NAME
    if claim.is_symlink() or not claim.is_file():
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID")
    claim_sha256 = sha256_file(claim)
    legacy_keys = (BLOCKED_RECEIPT_KEYS - {"evidence_sha256"}) | {"commands"}
    current_keys = legacy_keys | BLOCKED_EVIDENCE_CONTEXT_KEYS
    allowed = set(current_evidence)
    for evidence_path in evidence_children:
        relative = evidence_path.relative_to(project_root).as_posix()
        try:
            strict_bootstrap_evidence_relative(relative)
            reject_symlink_components(project_root, evidence_path)
        except BootstrapError as exc:
            raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID") from exc
        if evidence_path.is_symlink() or not evidence_path.is_file():
            raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID")
        resolved = evidence_path.resolve()
        if resolved in current_evidence:
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID") from exc
        commands = evidence.get("commands") if isinstance(evidence, dict) else None
        evidence_keys = set(evidence) if isinstance(evidence, dict) else set()
        if (
            not isinstance(evidence, dict)
            or evidence_keys not in (legacy_keys, current_keys)
            or (
                evidence.get("action_revision") == BOOTSTRAP_ACTION_REVISION
                and evidence_keys != current_keys
            )
            or (
                evidence_keys == current_keys
                and (
                    evidence.get("hook_source") not in {*HOOK_SOURCES, None}
                    or (
                        evidence.get("session_id") is not None
                        and SESSION_ID_RE.fullmatch(str(evidence.get("session_id"))) is None
                    )
                )
            )
            or evidence.get("schema_version") != 1
            or evidence.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
            or evidence.get("action_revision") not in SUPPORTED_BOOTSTRAP_ACTION_REVISIONS
            or evidence.get("status") != "ENVIRONMENT_BLOCKED"
            or evidence.get("claim_sha256") != claim_sha256
            or re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("project_input_sha256"))) is None
            or evidence.get("evidence_ref") != f"evidence:{relative}"
            or not isinstance(evidence.get("updated_at"), str)
            or not isinstance(evidence.get("reason"), str)
            or not isinstance(evidence.get("plugin_build"), str)
            or re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("plugin_manifest_sha256"))) is None
            or not isinstance(commands, list)
            or any(
                not isinstance(command, dict)
                or set(command) != {"command", "returncode", "stderr", "stdout"}
                or not isinstance(command.get("command"), list)
                or not all(isinstance(argument, str) for argument in command["command"])
                or type(command.get("returncode")) is not int
                or not isinstance(command.get("stderr"), str)
                or not isinstance(command.get("stdout"), str)
                for command in commands
            )
        ):
            raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID")
        allowed.add(resolved)
    return allowed


def validate_transaction_bound_proposals(
    governance: Path,
    transactions: Sequence[Path],
) -> None:
    """Accept non-empty proposals only when an active layout journal proves every byte."""
    proposals = governance / "proposals"
    if proposals.is_symlink() or (proposals.exists() and not proposals.is_dir()):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    expected: Dict[str, List[Dict[str, Any]]] = {}
    staged_locations: Dict[str, Path] = {}
    active_status: Optional[str] = None
    active_transaction: Optional[Path] = None
    for transaction in transactions:
        if transaction.is_symlink() or not transaction.is_dir():
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        journal_path = transaction / "journal.json"
        if journal_path.is_symlink() or not journal_path.is_file():
            continue
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID") from exc
        if not isinstance(journal, dict):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        status = journal.get("status")
        if status not in {"plan-activated", "version-pending"}:
            continue
        if active_transaction is not None:
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        active_status = str(status)
        active_transaction = transaction
        transaction_id = journal.get("transaction_id")
        expected_paths = {
            "staged_plan": (transaction / "staging" / "_Plan").as_posix(),
            "staged_proposals": (transaction / "staging" / "proposals").as_posix(),
            "target_proposals": (governance / "proposals").as_posix(),
            "backup_plan": (transaction / "backup" / "_Plan").as_posix(),
            "original_evidence": (
                governance / "evidence" / "layout-migrations" / transaction.name / "legacy-_Plan"
            ).as_posix(),
        }
        active_plan_id = journal.get("active_plan_id")
        active_plan_path = journal.get("active_plan_path")
        completed_operations = journal.get("completed_operations")
        expected_operations = [
            "snapshot",
            "staging",
            "conversion",
            "staged-validation",
            "legacy-backup",
            "plan-activation",
        ]
        if status == "version-pending":
            expected_operations.extend(["side-files", "final-validation"])
        manifests = (
            ("legacy_manifest", "legacy_manifest_sha256"),
            ("legacy_proposals_manifest", "legacy_proposals_sha256"),
            ("new_layout_manifest", "new_layout_baseline_sha256"),
            ("conversion_table", "conversion_table_sha256"),
        )
        if (
            set(journal) != ACTIVE_LAYOUT_JOURNAL_KEYS
            or journal.get("schema_version") != 1
            or journal.get("kind") != "layout-migration"
            or not isinstance(transaction_id, str)
            or transaction_id != transaction.name
            or LAYOUT_TRANSACTION_RE.fullmatch(transaction_id) is None
            or not isinstance(active_plan_id, str)
            or PLAN_ID_RE.fullmatch(active_plan_id) is None
            or active_plan_path != f"{active_plan_id}.md"
            or not isinstance(journal.get("created_at"), str)
            or not journal.get("created_at")
            or not isinstance(journal.get("updated_at"), str)
            or not journal.get("updated_at")
            or not isinstance(journal.get("git_baseline"), dict)
            or journal.get("paths") != expected_paths
            or completed_operations != expected_operations
            or not isinstance(journal.get("log_files"), list)
            or not isinstance(journal.get("proposal_trees"), list)
            or SHA256_RE.fullmatch(str(journal.get("legacy_adoption_sha256"))) is None
            or any(
                not isinstance(journal.get(manifest_key), list)
                or SHA256_RE.fullmatch(str(journal.get(digest_key))) is None
                or stable_digest(journal[manifest_key]) != journal[digest_key]
                for manifest_key, digest_key in manifests
            )
            or journal.get("new_proposals_baseline_sha256")
            != journal.get("legacy_proposals_sha256")
        ):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        legacy_manifest = cast(List[Dict[str, Any]], journal["legacy_manifest"])
        projected_proposals = [
            {
                **entry,
                "path": str(entry["path"]).removeprefix("proposals/"),
            }
            for entry in legacy_manifest
            if isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and str(entry["path"]).startswith("proposals/")
        ]
        canonical_plan = governance / "_Plan"
        backup_plan = transaction / "backup" / "_Plan"
        original_evidence = (
            governance / "evidence" / "layout-migrations" / transaction.name / "legacy-_Plan"
        )
        adoption = governance / "runtime" / LEGACY_ADOPTION_NAME
        proof_relative = f".migrations/{transaction.name}.yaml"
        proof = canonical_plan / proof_relative
        guard = governance.parent / "_Plan"
        if (
            projected_proposals != journal.get("legacy_proposals_manifest")
            or regular_tree_manifest(canonical_plan) != journal.get("new_layout_manifest")
            or regular_tree_manifest(backup_plan, exclude_names={".workctl.lock"})
            != legacy_manifest
            or regular_tree_manifest(original_evidence) != legacy_manifest
            or adoption.is_symlink()
            or not adoption.is_file()
            or sha256_file(adoption) != journal.get("legacy_adoption_sha256")
            or proof.is_symlink()
            or not proof.is_file()
            or not any(
                entry.get("path") == proof_relative and entry.get("kind") == "file"
                for entry in cast(List[Dict[str, Any]], journal["new_layout_manifest"])
            )
            or (transaction / "staging" / "_Plan").exists()
            or (transaction / "staging" / "_Plan").is_symlink()
            or (
                status == "plan-activated"
                and (
                    guard.is_symlink()
                    or not guard.is_file()
                    or guard.read_text(encoding="utf-8")
                    != "WORK_GOVERNANCE_LAYOUT_ACTIVATION_GUARD\n"
                )
            )
            or (status == "version-pending" and (guard.exists() or guard.is_symlink()))
        ):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        validate_active_adoption(governance, adoption, journal)
        validate_active_migration_proof(proof, journal)
        records = journal.get("proposal_trees")
        assert isinstance(records, list)
        combined_manifest: List[Dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {
                "migration_id",
                "manifest",
                "manifest_sha256",
                "staged_path",
                "target",
            }:
                raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
            migration_id = record.get("migration_id")
            manifest = record.get("manifest")
            manifest_sha256 = record.get("manifest_sha256")
            if (
                not isinstance(migration_id, str)
                or MIGRATION_ID_RE.fullmatch(migration_id) is None
                or migration_id in expected
                or not isinstance(manifest, list)
                or not isinstance(manifest_sha256, str)
                or SHA256_RE.fullmatch(manifest_sha256) is None
                or stable_digest(manifest) != manifest_sha256
                or record.get("staged_path")
                != (transaction / "staging" / "proposals" / migration_id).as_posix()
                or record.get("target") != f"{GOVERNANCE_DIR}/proposals/{migration_id}"
            ):
                raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
            expected[migration_id] = cast(List[Dict[str, Any]], manifest)
            staged_locations[migration_id] = transaction / "staging" / "proposals" / migration_id
            combined_manifest.append({"path": migration_id, "kind": "directory"})
            for entry in manifest:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
                combined_manifest.append(
                    {
                        **entry,
                        "path": f"{migration_id}/{entry['path']}",
                    }
                )
        combined_manifest.sort(key=lambda entry: str(entry["path"]))
        if combined_manifest != journal.get("legacy_proposals_manifest"):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    actual_names = {child.name for child in proposals.iterdir()} if proposals.is_dir() else set()
    if not actual_names.issubset(expected):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    if active_transaction is None:
        if actual_names:
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        return
    staged_root = active_transaction / "staging" / "proposals"
    if staged_root.is_symlink() or (staged_root.exists() and not staged_root.is_dir()):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    staged_names = (
        {child.name for child in staged_root.iterdir()} if staged_root.is_dir() else set()
    )
    if (
        not staged_names.issubset(expected)
        or staged_names & actual_names
        or staged_names | actual_names != set(expected)
        or (active_status == "version-pending" and staged_names)
    ):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    for name in sorted(expected):
        proposal = proposals / name if name in actual_names else staged_locations[name]
        manifest = path_manifest(proposal)
        if (
            proposal.is_symlink()
            or not proposal.is_dir()
            or not manifest
            or manifest[0] != {"path": ".", "kind": "directory"}
            or manifest[1:] != expected[name]
        ):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")


def audit_uncommitted_root(governance: Path) -> None:
    """Allow only the bounded footprint created before version commitment."""
    allowed = {
        "logs",
        "worktrees",
        "cache",
        "proposals",
        "evidence",
        "runtime",
        "_Plan",
        ".gitignore",
        RECEIPT_NAME,
        "workctl.lock",
    }
    if any(child.name not in allowed for child in governance.iterdir()):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    ignore = governance / ".gitignore"
    if ignore.exists() and (
        ignore.is_symlink()
        or not ignore.is_file()
        or ignore.read_text(encoding="utf-8")
        != "/logs/\n/worktrees/\n/cache/\n/proposals/\n/evidence/\n/runtime/\n"
        "/bootstrap-state.json\n/workctl.lock\n"
    ):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    bootstrap_evidence = validate_blocked_record(governance)
    bootstrap_evidence = validate_blocked_evidence_history(governance, bootstrap_evidence)
    for name in ("logs", "worktrees"):
        path = governance / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        if path.is_dir() and any(path.iterdir()):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    cache = governance / "cache"
    if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    if cache.is_dir() and any(child.name != "uv" for child in cache.iterdir()):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    runtime = governance / "runtime"
    if runtime.is_symlink() or not runtime.is_dir():
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    transactions = []
    for child in runtime.iterdir():
        if child.name in {CLAIM_NAME, LEGACY_ADOPTION_NAME}:
            continue
        if child.name == CAPABILITY_NAME:
            validate_bootstrap_capability(governance, child)
            continue
        if child.name == "plugin-builds":
            if child.is_symlink() or not child.is_dir():
                raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
            bundles = list(child.iterdir())
            if len(bundles) > 16:
                raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
            for bundle in bundles:
                if (
                    bundle.is_symlink()
                    or not bundle.is_dir()
                    or re.fullmatch(r"[0-9a-f]{64}", bundle.name) is None
                ):
                    raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
                manifest = bundle / "manifest.json"
                try:
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID") from exc
                if (
                    not isinstance(payload, dict)
                    or payload.get("plugin_manifest_sha256") != bundle.name
                ):
                    raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
                validate_runtime_bundle(governance.parent, bundle, payload)
            continue
        if LAYOUT_TRANSACTION_RE.fullmatch(child.name) is None:
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        transactions.append(child)
    validate_transaction_bound_proposals(governance, transactions)
    evidence = governance / "evidence"
    if evidence.is_symlink() or (evidence.exists() and not evidence.is_dir()):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    if evidence.is_dir() and any(evidence.iterdir()):
        migrations = evidence / "layout-migrations"
        bootstrap = evidence / "bootstrap"
        transaction_names = {path.name for path in transactions}
        migration_children = (
            list(migrations.iterdir())
            if migrations.is_dir() and not migrations.is_symlink()
            else []
        )
        migration_names = {child.name for child in migration_children}
        allowed_evidence_children = {
            name
            for name, condition in (
                (
                    "bootstrap",
                    bootstrap.is_dir()
                    and not bootstrap.is_symlink()
                    and {child.resolve() for child in bootstrap.iterdir()} == bootstrap_evidence,
                ),
                (
                    "layout-migrations",
                    migrations.is_dir() and not migrations.is_symlink() and bool(transaction_names),
                ),
            )
            if condition
        }
        if (
            {child.name for child in evidence.iterdir()} != allowed_evidence_children
            or not migration_names.issubset(transaction_names)
            or any(child.is_symlink() or not child.is_dir() for child in migration_children)
        ):
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    if (
        (governance / "_Plan").exists()
        and not transactions
        and not (governance.parent / "_Plan").exists()
    ):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")


def validate_bootstrap_capability(governance: Path, capability: Path) -> None:
    """Validate the exact ignored SessionStart capability used by layout writes."""
    project_root = governance.parent
    reject_symlink_components(project_root, capability)
    if capability.is_symlink() or not capability.is_file():
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    try:
        payload = json.loads(capability.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID") from exc
    required = {
        "schema_version",
        "bootstrap_contract_version",
        "action_revision",
        "updated_at",
        "status",
        "plugin_build",
        "plugin_manifest_sha256",
        "project_input_sha256",
        "project_output_sha256",
        "layout_state",
        "evidence_ref",
        "session_id",
        "runtime_bundle_ref",
        "runtime_manifest_sha256",
        "controller_ref",
        "controller_sha256",
        "lifecycle_ref",
        "lifecycle_sha256",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or payload.get("schema_version") != 2
        or payload.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
        or payload.get("action_revision") != BOOTSTRAP_ACTION_REVISION
        or payload.get("status") != "BOOTSTRAPPING"
        or payload.get("layout_state") != "BOOTSTRAPPING"
        or not isinstance(payload.get("updated_at"), str)
        or not isinstance(payload.get("plugin_build"), str)
        or not isinstance(payload.get("session_id"), str)
        or SESSION_ID_RE.fullmatch(str(payload.get("session_id"))) is None
    ):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    for field in (
        "plugin_manifest_sha256",
        "project_input_sha256",
        "project_output_sha256",
        "runtime_manifest_sha256",
        "controller_sha256",
        "lifecycle_sha256",
    ):
        if re.fullmatch(r"[0-9a-f]{64}", str(payload.get(field))) is None:
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    bundle = project_root / str(payload["runtime_bundle_ref"])
    reject_symlink_components(project_root, bundle)
    if bundle.parent != governance / "runtime" / "plugin-builds":
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
    manifest = bundle / "manifest.json"
    try:
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID") from exc
    runtime = validate_runtime_bundle(project_root, bundle, manifest_payload)
    if any(payload.get(key) != value for key, value in runtime.items()):
        raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")


def ensure_local_directories(
    project_root: Path,
    *,
    controller_sha256: str,
    input_digest: str,
) -> Path:
    """Prove first ownership, then create only declared local infrastructure."""
    governance = project_root / GOVERNANCE_DIR
    staging = project_root / BOOTSTRAP_STAGING_NAME
    committed_layout = False
    if governance.is_symlink():
        raise BootstrapError("GOVERNANCE_ROOT_SYMLINK")
    if not governance.exists():
        if staging.exists() or staging.is_symlink():
            staging_children = (
                sorted(child.name for child in staging.iterdir())
                if staging.is_dir() and not staging.is_symlink()
                else []
            )
            runtime_children = (
                sorted(child.name for child in (staging / "runtime").iterdir())
                if (staging / "runtime").is_dir() and not (staging / "runtime").is_symlink()
                else []
            )
            if (
                staging.is_symlink()
                or not staging.is_dir()
                or staging_children != ["runtime"]
                or runtime_children != [CLAIM_NAME]
            ):
                raise BootstrapError("GOVERNANCE_BOOTSTRAP_STAGING_INVALID")
            validate_bootstrap_claim(project_root, staging / "runtime" / CLAIM_NAME)
        else:
            staging.mkdir()
            create_bootstrap_claim(
                project_root,
                staging,
                controller_sha256=controller_sha256,
                input_digest=input_digest,
            )
        if os.environ.get("WORK_GOVERNANCE_TEST_INTERRUPT_AFTER_CLAIM") == "1":
            raise BootstrapError("BOOTSTRAP_TEST_INTERRUPTED_AFTER_CLAIM")
        rename_directory_noreplace(staging, governance)
    elif not governance.is_dir():
        raise BootstrapError("GOVERNANCE_ROOT_INVALID")
    elif staging.exists() or staging.is_symlink():
        raise BootstrapError("GOVERNANCE_BOOTSTRAP_STAGING_CONFLICT")
    if (governance / "version.yaml").exists() or (governance / "version.yaml").is_symlink():
        committed_layout = True
        validate_layout_version(project_root, governance)
    else:
        validate_bootstrap_claim(project_root, governance / "runtime" / CLAIM_NAME)
        recover_blocked_failure(governance)
        audit_uncommitted_root(governance)
    for relative in LOCAL_DIRECTORIES:
        current = governance
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                relative = current.relative_to(project_root).as_posix()
                raise BootstrapError(f"GOVERNANCE_CONTROL_PATH_SYMLINK: {relative}")
            current.mkdir(exist_ok=True)
    if committed_layout:
        create_bootstrap_claim(
            project_root,
            governance,
            controller_sha256=controller_sha256,
            input_digest=input_digest,
        )
        validate_bootstrap_claim(project_root, governance / "runtime" / CLAIM_NAME)
        failure_journal = governance / "runtime" / FAILURE_JOURNAL_NAME
        if failure_journal.exists() or failure_journal.is_symlink():
            recover_blocked_failure(governance)
    return governance


def project_input_digest(project_root: Path) -> str:
    """Fingerprint layout inputs while excluding normal canonical Plan revisions."""
    if os.environ.get("WORK_GOVERNANCE_TEST_FAIL_PROJECT_INPUT_DIGEST") == "1":
        raise OSError("BOOTSTRAP_TEST_PROJECT_INPUT_DIGEST_FAILED")
    governance = project_root / GOVERNANCE_DIR
    version = governance / "version.yaml"
    paths: List[Tuple[str, Path]] = [
        ("legacy-plan", legacy_plan_path(project_root)),
        ("version", version),
        ("ignore", governance / ".gitignore"),
    ]
    if not version.is_file():
        paths.extend(
            [
                ("legacy-logs", legacy_logs_path(project_root)),
                ("agents", project_root / "AGENTS.md"),
                ("claude", project_root / "CLAUDE.md"),
            ]
        )
    manifests = [{"name": name, "manifest": path_manifest(path)} for name, path in paths]
    runtime_manifest = [
        entry
        for entry in path_manifest(governance / "runtime")
        if entry.get("path") != SESSIONS_DIR_NAME
        and not str(entry.get("path", "")).startswith(f"{SESSIONS_DIR_NAME}/")
    ]
    manifests.append({"name": "runtime", "manifest": runtime_manifest})
    return stable_digest(manifests)


def project_output_digest(project_root: Path) -> str:
    """Fingerprint committed layout outputs, excluding runtime and Plan content."""
    governance = project_root / GOVERNANCE_DIR
    return stable_digest(
        [
            {
                "name": "version",
                "manifest": path_manifest(governance / "version.yaml"),
            },
            {
                "name": "ignore",
                "manifest": path_manifest(governance / ".gitignore"),
            },
        ]
    )


def load_receipt(path: Path) -> Optional[Dict[str, Any]]:
    """Load a prior receipt; invalid local state is treated as a cache miss."""
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically and durably replace a small local JSON record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + path.name + ".", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
        directory_descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def session_state_dir(governance: Path, session_id: str) -> Path:
    """Return one symlink-safe project-local session state directory."""
    session_dir = governance / "runtime" / SESSIONS_DIR_NAME / session_id
    reject_symlink_components(governance.parent, session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    if session_dir.is_symlink() or not session_dir.is_dir():
        raise BootstrapError("GOVERNANCE_SESSION_STATE_INVALID")
    return session_dir


def session_receipt_path(governance: Path, session_id: str) -> Path:
    """Return the canonical READY receipt for one Codex session."""
    return session_state_dir(governance, session_id) / RECEIPT_NAME


def session_capability_path(governance: Path, session_id: str) -> Path:
    """Return the bootstrap-only capability for one Codex session."""
    return session_state_dir(governance, session_id) / CAPABILITY_NAME


def ready_receipt_is_reusable(
    prior: Mapping[str, Any] | None,
    candidate: Mapping[str, Any],
) -> bool:
    """Keep a same-session receipt stable when its trusted runtime identity is stable."""
    if not isinstance(prior, Mapping):
        return False
    stable_fields = {
        "schema_version",
        "bootstrap_contract_version",
        "action_revision",
        "status",
        "plugin_build",
        "plugin_manifest_sha256",
        "layout_state",
        "session_id",
        "runtime_bundle_ref",
        "runtime_manifest_sha256",
        "controller_ref",
        "controller_sha256",
        "lifecycle_ref",
        "lifecycle_sha256",
    }
    return all(prior.get(field) == candidate.get(field) for field in stable_fields)


def install_legacy_ready_receipt_if_absent(
    governance: Path,
    payload: Mapping[str, Any],
) -> None:
    """Maintain the singleton compatibility receipt without superseding its session."""
    legacy = governance / RECEIPT_NAME
    reject_symlink_components(governance.parent, legacy)
    if legacy.exists() or legacy.is_symlink():
        if legacy.is_symlink() or not legacy.is_file():
            raise BootstrapError("GOVERNANCE_BOOTSTRAP_RECEIPT_INVALID")
        current = load_receipt(legacy)
        if (
            current is not None
            and current.get("status") == "READY"
            and current.get("session_id") != payload.get("session_id")
        ):
            return
    atomic_write_json(legacy, payload)


def runtime_bundle_payload(
    project_root: Path,
    bundle: Path,
    *,
    build: str,
    manifest_digest: str,
    controller_sha256: str,
    lifecycle_sha256: str,
    module_files: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build the exact hash-bound runtime bundle manifest."""
    payload: Dict[str, Any] = {
        "schema_version": 1,
        "kind": "work-governance-runtime-bundle",
        "plugin_build": build,
        "plugin_manifest_sha256": manifest_digest,
        "controller_ref": (bundle / "workctl.py").relative_to(project_root).as_posix(),
        "controller_sha256": controller_sha256,
        "lifecycle_ref": (bundle / "work-lifecycle.SKILL.md").relative_to(project_root).as_posix(),
        "lifecycle_sha256": lifecycle_sha256,
    }
    if module_files:
        payload["module_files"] = module_files
    return payload


def validate_runtime_bundle(
    project_root: Path,
    bundle: Path,
    expected: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate an existing bundle without consulting the Plugin cache."""
    reject_symlink_components(project_root, bundle)
    controller = bundle / "workctl.py"
    lifecycle = bundle / "work-lifecycle.SKILL.md"
    manifest = bundle / "manifest.json"
    if (
        bundle.is_symlink()
        or not bundle.is_dir()
        or controller.is_symlink()
        or lifecycle.is_symlink()
        or manifest.is_symlink()
        or not controller.is_file()
        or not lifecycle.is_file()
        or not manifest.is_file()
        or sha256_file(controller) != expected["controller_sha256"]
        or sha256_file(lifecycle) != expected["lifecycle_sha256"]
    ):
        raise BootstrapError("RUNTIME_BUNDLE_INVALID")
    module_files = expected.get("module_files")
    if module_files is not None:
        if not isinstance(module_files, list):
            raise BootstrapError("RUNTIME_BUNDLE_INVALID")
        for entry in module_files:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"path", "sha256"}
                or not isinstance(entry.get("path"), str)
                or not isinstance(entry.get("sha256"), str)
                or not SHA256_RE.fullmatch(entry["sha256"])
            ):
                raise BootstrapError("RUNTIME_BUNDLE_INVALID")
            candidate = bundle / entry["path"]
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or sha256_file(candidate) != entry["sha256"]
            ):
                raise BootstrapError("RUNTIME_BUNDLE_INVALID")
    try:
        actual = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("RUNTIME_BUNDLE_INVALID") from exc
    if actual != dict(expected):
        raise BootstrapError("RUNTIME_BUNDLE_INVALID")
    return {
        "runtime_bundle_ref": bundle.relative_to(project_root).as_posix(),
        "runtime_manifest_sha256": sha256_file(manifest),
        "controller_ref": expected["controller_ref"],
        "controller_sha256": expected["controller_sha256"],
        "lifecycle_ref": expected["lifecycle_ref"],
        "lifecycle_sha256": expected["lifecycle_sha256"],
    }


def install_runtime_bundle(
    project_root: Path,
    installed_plugin: Path,
    *,
    build: str,
    manifest_digest: str,
) -> Dict[str, Any]:
    """Durably snapshot the exact controller and lifecycle before issuing READY."""
    source_controller = installed_plugin / "scripts" / "workctl.py"
    source_lifecycle = installed_plugin / "skills" / "work-lifecycle" / "SKILL.md"
    if (
        source_controller.is_symlink()
        or source_lifecycle.is_symlink()
        or not source_controller.is_file()
        or not source_lifecycle.is_file()
    ):
        raise BootstrapError("RUNTIME_BUNDLE_SOURCE_INVALID")
    module_source = installed_plugin / "scripts" / "workctl_modules"
    module_files: List[Dict[str, str]] = []
    if module_source.is_dir() and not module_source.is_symlink():
        for source in sorted(module_source.rglob("*.py")):
            if source.is_symlink() or not source.is_file():
                raise BootstrapError("RUNTIME_BUNDLE_SOURCE_INVALID")
            module_files.append(
                {
                    "path": f"workctl_modules/{source.relative_to(module_source).as_posix()}",
                    "sha256": sha256_file(source),
                }
            )
    bundles = project_root / GOVERNANCE_DIR / "runtime" / "plugin-builds"
    reject_symlink_components(project_root, bundles)
    bundles.mkdir(parents=True, exist_ok=True)
    bundle = bundles / manifest_digest
    expected = runtime_bundle_payload(
        project_root,
        bundle,
        build=build,
        manifest_digest=manifest_digest,
        controller_sha256=sha256_file(source_controller),
        lifecycle_sha256=sha256_file(source_lifecycle),
        module_files=module_files or None,
    )
    if bundle.exists() or bundle.is_symlink():
        return validate_runtime_bundle(project_root, bundle, expected)
    staging = bundles / f".{manifest_digest}.{os.getpid()}.staging"
    if staging.exists() or staging.is_symlink():
        raise BootstrapError("RUNTIME_BUNDLE_STAGING_CONFLICT")
    staging.mkdir()
    try:
        files = (
            ("workctl.py", source_controller.read_bytes()),
            ("work-lifecycle.SKILL.md", source_lifecycle.read_bytes()),
            (
                "manifest.json",
                (json.dumps(expected, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode(),
            ),
        )
        for name, content in files:
            path = staging / name
            with path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        for entry in module_files:
            source = module_source / Path(entry["path"]).relative_to("workctl_modules")
            target = staging / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(source.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
        directory_descriptor = os.open(str(staging), os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        try:
            os.rename(staging, bundle)
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
        directory_descriptor = os.open(str(bundles), os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return validate_runtime_bundle(project_root, bundle, expected)


def invalidate_bootstrap_receipt(project_root: Path, path: Path) -> None:
    """Durably remove a stale receipt when exact failure provenance is unavailable."""
    reject_symlink_components(project_root, path)
    if path.is_symlink():
        raise BootstrapError("GOVERNANCE_BOOTSTRAP_RECEIPT_SYMLINK")
    if not path.exists():
        return
    if not path.is_file():
        raise BootstrapError("GOVERNANCE_BOOTSTRAP_RECEIPT_INVALID")
    path.unlink()
    directory_descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def invalidate_legacy_ready_for_session(
    governance: Path,
    session_id: Optional[str],
) -> None:
    """Invalidate legacy compatibility only when it belongs to the failing session."""
    if session_id is None:
        return
    legacy = governance / RECEIPT_NAME
    current = load_receipt(legacy)
    if (
        current is not None
        and current.get("status") == "READY"
        and current.get("session_id") == session_id
    ):
        invalidate_bootstrap_receipt(governance.parent, legacy)


def json_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the exact bytes used by atomic JSON records."""
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def recover_blocked_failure(
    governance: Path,
    *,
    receipt_path: Optional[Path] = None,
    journal_path: Optional[Path] = None,
) -> None:
    """Finish an interrupted blocked evidence/receipt installation."""
    project_root = governance.parent
    runtime = governance / "runtime"
    reject_symlink_components(project_root, runtime)
    if not runtime.is_dir():
        raise BootstrapError("BOOTSTRAP_FAILURE_RUNTIME_INVALID")
    target_receipt = receipt_path or governance / RECEIPT_NAME
    journal = journal_path or runtime / FAILURE_JOURNAL_NAME
    reject_symlink_components(project_root, journal)
    if not journal.exists() and not journal.is_symlink():
        return
    if journal.is_symlink() or not journal.is_file():
        raise BootstrapError("BOOTSTRAP_FAILURE_JOURNAL_INVALID")
    try:
        payload = json.loads(journal.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BootstrapError("BOOTSTRAP_FAILURE_JOURNAL_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "schema_version",
            "kind",
            "evidence_path",
            "evidence_payload",
            "receipt_payload",
        }
        or payload.get("schema_version") != 1
        or payload.get("kind") != "bootstrap-failure-install"
        or not isinstance(payload.get("evidence_path"), str)
        or not isinstance(payload.get("evidence_payload"), dict)
        or not isinstance(payload.get("receipt_payload"), dict)
    ):
        raise BootstrapError("BOOTSTRAP_FAILURE_JOURNAL_INVALID")
    try:
        evidence_relative = strict_bootstrap_evidence_relative(str(payload["evidence_path"]))
    except BootstrapError as exc:
        raise BootstrapError("BOOTSTRAP_FAILURE_JOURNAL_INVALID") from exc
    evidence_base = governance / "evidence" / "bootstrap"
    reject_symlink_components(project_root, evidence_base)
    if not evidence_base.is_dir():
        raise BootstrapError("BOOTSTRAP_FAILURE_EVIDENCE_ROOT_INVALID")
    evidence_path = project_root / evidence_relative
    reject_symlink_components(project_root, evidence_path)
    evidence_payload = cast(Dict[str, Any], payload["evidence_payload"])
    receipt_payload = cast(Dict[str, Any], payload["receipt_payload"])
    evidence_sha256 = sha256_bytes(json_payload_bytes(evidence_payload))
    if (
        receipt_payload.get("evidence_sha256") != evidence_sha256
        or receipt_payload.get("evidence_ref")
        != f"evidence:{evidence_path.relative_to(project_root).as_posix()}"
    ):
        raise BootstrapError("BOOTSTRAP_FAILURE_JOURNAL_INVALID")
    atomic_write_json(evidence_path, evidence_payload)
    atomic_write_json(target_receipt, receipt_payload)
    if target_receipt == governance / RECEIPT_NAME:
        validate_blocked_record(governance)
    elif load_receipt(target_receipt) != receipt_payload:
        raise BootstrapError("BOOTSTRAP_FAILURE_RECEIPT_INVALID")
    journal.unlink()
    directory_descriptor = os.open(str(journal.parent), os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def persist_blocked_failure(
    governance: Path,
    *,
    base_receipt: Mapping[str, Any],
    reason: str,
    build: str,
    manifest_digest: str,
    input_digest: str,
    records: Sequence[Mapping[str, Any]],
    hook_source: Optional[str],
    session_id: Optional[str],
    receipt_path: Optional[Path] = None,
    journal_path: Optional[Path] = None,
) -> str:
    """Journal, install, and validate one claim-bound uncommitted failure record."""
    project_root = governance.parent
    runtime = governance / "runtime"
    evidence_base = governance / "evidence" / "bootstrap"
    reject_symlink_components(project_root, runtime)
    reject_symlink_components(project_root, evidence_base)
    if not runtime.is_dir() or not evidence_base.is_dir():
        raise BootstrapError("GOVERNANCE_BLOCKED_RECORD_ROOT_INVALID")
    claim = governance / "runtime" / CLAIM_NAME
    reject_symlink_components(project_root, claim)
    if claim.is_symlink() or not claim.is_file():
        raise BootstrapError("GOVERNANCE_BOOTSTRAP_CLAIM_INVALID")
    evidence = evidence_path(governance)
    reject_symlink_components(project_root, evidence)
    evidence_ref = f"evidence:{evidence.relative_to(project_root).as_posix()}"
    common: Dict[str, Any] = {
        **dict(base_receipt),
        "status": "ENVIRONMENT_BLOCKED",
        "reason": reason,
        "plugin_build": build,
        "plugin_manifest_sha256": manifest_digest,
        "project_input_sha256": input_digest,
        "claim_sha256": sha256_file(claim),
        "evidence_ref": evidence_ref,
    }
    evidence_payload = {
        **common,
        "hook_source": hook_source,
        "session_id": session_id,
        "commands": [dict(record) for record in records],
    }
    receipt_payload = {
        **common,
        "evidence_sha256": sha256_bytes(json_payload_bytes(evidence_payload)),
    }
    journal_payload = {
        "schema_version": 1,
        "kind": "bootstrap-failure-install",
        "evidence_path": evidence.relative_to(governance.parent).as_posix(),
        "evidence_payload": evidence_payload,
        "receipt_payload": receipt_payload,
    }
    target_receipt = receipt_path or governance / RECEIPT_NAME
    target_journal = journal_path or governance / "runtime" / FAILURE_JOURNAL_NAME
    reject_symlink_components(project_root, target_receipt)
    reject_symlink_components(project_root, target_journal)
    atomic_write_json(target_journal, journal_payload)
    if os.environ.get("WORK_GOVERNANCE_TEST_INTERRUPT_FAILURE_AFTER_JOURNAL") == "1":
        raise BootstrapError("BOOTSTRAP_TEST_INTERRUPTED_FAILURE_INSTALL")
    recover_blocked_failure(
        governance,
        receipt_path=target_receipt,
        journal_path=target_journal,
    )
    return evidence_ref


def bounded_hook_source(value: object) -> Optional[str]:
    """Return only one documented SessionStart source value."""
    return str(value) if isinstance(value, str) and value in HOOK_SOURCES else None


def bounded_session_id(value: object) -> Optional[str]:
    """Return one bounded local session correlation value."""
    if not isinstance(value, str) or SESSION_ID_RE.fullmatch(value) is None:
        return None
    return value


def failed_command_detail(records: Sequence[Mapping[str, Any]]) -> str:
    """Return the last bounded non-zero command diagnostic for short hook context."""
    for record in reversed(records):
        if record.get("returncode") == 0:
            continue
        raw = record.get("stderr")
        if not isinstance(raw, str) or not raw.strip():
            raw = record.get("stdout")
        if isinstance(raw, str) and raw.strip():
            return re.sub(r"\s+", " ", raw).strip()[:500]
    return "unavailable"


def blocked_recovery_action(reason: str, detail: str) -> str:
    """Map an observed bootstrap failure to the next allowed recovery action."""
    primary_reason = reason.split(";", 1)[0].strip()
    if primary_reason == "CONTROLLER_PREWARM_FAILED":
        return (
            "restore the exact project-local controller cache or permitted dependency "
            "access, then start a fresh session"
        )
    if primary_reason == "LAYOUT_MIGRATION_NOT_READY":
        if "LAYOUT_RECOVERY_REQUIRED" in detail:
            return "run workctl layout recover, verify layout status, then start a fresh session"
        if "RECONCILIATION_REQUIRED" in detail:
            return (
                "run workctl layout status and reconcile the competing authorities; "
                "do not migrate by guess"
            )
        if "LEGACY_CLASSIFICATION_REQUIRED" in detail:
            return (
                "run workctl layout status; review the exact blockers; when only adoption "
                "remains, run workctl layout adopt with the current manifest, active Plan "
                "and user reference, then start a fresh session"
            )
        return "run workctl layout status, resolve its exact blockers, then start a fresh session"
    if primary_reason == "LAYOUT_VALIDATION_FAILED":
        return "run workctl layout validate and recover the reported transaction before retrying"
    return "inspect the local bootstrap evidence and correct the reported control-path failure"


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run one bounded bootstrap command and retain output for local evidence."""
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        env=dict(environment),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def uv_controller_command(
    uv_path: str,
    cache: Path,
    controller: Path,
    arguments: Iterable[str],
    *,
    offline: bool,
) -> List[str]:
    """Build the isolated UV invocation without business-environment mutation."""
    command = [
        uv_path,
        "run",
        "--no-project",
        "--cache-dir",
        str(cache),
        "--no-python-downloads",
    ]
    if offline:
        command.append("--offline")
    command.extend(["--script", str(controller), *arguments])
    return command


def command_record(
    command: Sequence[str], result: subprocess.CompletedProcess[str]
) -> Dict[str, Any]:
    """Store concise command evidence without exposing it to hook stdout."""
    return {
        "command": list(command),
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def run_bootstrap(
    project_root: Path,
    controller: Path,
    receipt: Optional[Dict[str, Any]],
    manifest_digest: str,
    build: str,
    input_digest: str,
    runtime_bundle: Mapping[str, Any],
    bootstrap_receipt_sha256: str,
    records: List[Dict[str, Any]],
) -> str:
    """Prewarm when needed, then execute all controller work offline."""
    governance = project_root / GOVERNANCE_DIR
    cache = governance / "cache" / "uv"
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise BootstrapError("UV_NOT_AVAILABLE")
    environment = dict(os.environ)
    environment["UV_CACHE_DIR"] = str(cache)
    environment["UV_PYTHON_DOWNLOADS"] = "never"
    matching_ready = bool(
        receipt
        and receipt.get("schema_version") == 2
        and receipt.get("status") == "READY"
        and receipt.get("action_revision") == BOOTSTRAP_ACTION_REVISION
        and receipt.get("bootstrap_contract_version") == BOOTSTRAP_CONTRACT_VERSION
        and receipt.get("plugin_build") == build
        and receipt.get("plugin_manifest_sha256") == manifest_digest
        and receipt.get("project_input_sha256") == input_digest
        and receipt.get("project_output_sha256") == project_output_digest(project_root)
        and all(receipt.get(key) == value for key, value in runtime_bundle.items())
    )
    if not matching_ready:
        cached_prewarm = uv_controller_command(
            uv_path,
            cache,
            controller,
            ["--help"],
            offline=True,
        )
        cached_prewarm_result = run_command(
            cached_prewarm,
            cwd=project_root,
            environment=environment,
        )
        records.append(command_record(cached_prewarm, cached_prewarm_result))
        if cached_prewarm_result.returncode != 0:
            network_prewarm = uv_controller_command(
                uv_path,
                cache,
                controller,
                ["--help"],
                offline=False,
            )
            network_prewarm_result = run_command(
                network_prewarm,
                cwd=project_root,
                environment=environment,
            )
            records.append(command_record(network_prewarm, network_prewarm_result))
            if network_prewarm_result.returncode != 0:
                raise BootstrapError("CONTROLLER_PREWARM_FAILED")
        migrate = uv_controller_command(
            uv_path,
            cache,
            controller,
            [
                "--receipt-sha256",
                bootstrap_receipt_sha256,
                "layout",
                "migrate",
            ],
            offline=True,
        )
        migrate_result = run_command(migrate, cwd=project_root, environment=environment)
        records.append(command_record(migrate, migrate_result))
        if migrate_result.returncode != 0:
            raise BootstrapError("LAYOUT_MIGRATION_NOT_READY")
    validate = uv_controller_command(
        uv_path, cache, controller, ["layout", "validate"], offline=True
    )
    validate_result = run_command(validate, cwd=project_root, environment=environment)
    records.append(command_record(validate, validate_result))
    if validate_result.returncode != 0:
        raise BootstrapError("LAYOUT_VALIDATION_FAILED")
    status = uv_controller_command(uv_path, cache, controller, ["layout", "status"], offline=True)
    status_result = run_command(status, cwd=project_root, environment=environment)
    records.append(command_record(status, status_result))
    if status_result.returncode != 0:
        raise BootstrapError("LAYOUT_STATUS_FAILED")
    try:
        status_payload = json.loads(status_result.stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapError("LAYOUT_STATUS_INVALID") from exc
    layout_state = status_payload.get("layout_state") if isinstance(status_payload, dict) else None
    if layout_state != "LAYOUT_READY":
        raise BootstrapError(f"LAYOUT_NOT_READY: {layout_state}")
    return str(layout_state)


def evidence_path(governance: Path) -> Path:
    """Return a unique local bootstrap evidence path."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return governance / "evidence" / "bootstrap" / f"{stamp}-{os.getpid()}.json"


def emit_context(message: str) -> None:
    """Emit only the short model-visible SessionStart result."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": message,
                }
            },
            separators=(",", ":"),
        )
    )


def main() -> int:
    """Execute one incremental bootstrap and always return short hook context."""
    governance: Optional[Path] = None
    receipt_path: Optional[Path] = None
    failure_journal_path: Optional[Path] = None
    evidence: Optional[Path] = None
    build: Optional[str] = None
    manifest_digest: Optional[str] = None
    input_digest: Optional[str] = None
    hook_source: Optional[str] = None
    session_id: Optional[str] = None
    controller: Optional[Path] = None
    bootstrap_receipt_sha256: Optional[str] = None
    records: List[Dict[str, Any]] = []
    base_receipt: Dict[str, Any] = {
        "schema_version": 1,
        "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
        "action_revision": BOOTSTRAP_ACTION_REVISION,
        "updated_at": utc_now(),
    }
    try:
        hook_input = load_hook_input()
        hook_source = bounded_hook_source(hook_input.get("source"))
        session_id = bounded_session_id(hook_input.get("session_id"))
        project_root = discover_project_root(Path(str(hook_input["cwd"])))
        installed_plugin = plugin_root()
        build = plugin_build(installed_plugin)
        manifest_digest = plugin_manifest_digest(installed_plugin)
        controller_sha256 = sha256_file(installed_plugin / "scripts" / "workctl.py")
        claim_input_digest = bootstrap_claim_input_digest(project_root)
        governance = ensure_local_directories(
            project_root,
            controller_sha256=controller_sha256,
            input_digest=claim_input_digest,
        )
        runtime_bundle = install_runtime_bundle(
            project_root,
            installed_plugin,
            build=build,
            manifest_digest=manifest_digest,
        )
        controller = project_root / str(runtime_bundle["controller_ref"])
        safe_session_id = session_id or "session-unavailable"
        committed_layout = (governance / "version.yaml").is_file()
        receipt_path = (
            session_receipt_path(governance, safe_session_id)
            if committed_layout
            else governance / RECEIPT_NAME
        )
        failure_journal_path = (
            receipt_path.parent / FAILURE_JOURNAL_NAME
            if committed_layout
            else governance / "runtime" / FAILURE_JOURNAL_NAME
        )
        if committed_layout:
            recover_blocked_failure(
                governance,
                receipt_path=receipt_path,
                journal_path=failure_journal_path,
            )
        evidence = evidence_path(governance)
        input_digest = project_input_digest(project_root)
        receipt = load_receipt(receipt_path)
        if receipt is None:
            receipt = load_receipt(governance / RECEIPT_NAME)
        bootstrap_receipt = {
            **base_receipt,
            "schema_version": 2,
            "status": "BOOTSTRAPPING",
            "plugin_build": build,
            "plugin_manifest_sha256": manifest_digest,
            "project_input_sha256": input_digest,
            "project_output_sha256": project_output_digest(project_root),
            "layout_state": "BOOTSTRAPPING",
            "evidence_ref": f"evidence:{evidence.relative_to(project_root).as_posix()}",
            "session_id": safe_session_id,
            **runtime_bundle,
        }
        capability_path = (
            session_capability_path(governance, safe_session_id)
            if committed_layout
            else governance / "runtime" / CAPABILITY_NAME
        )
        atomic_write_json(capability_path, bootstrap_receipt)
        bootstrap_receipt_sha256 = sha256_file(capability_path)
        layout_state = run_bootstrap(
            project_root,
            controller,
            receipt,
            manifest_digest,
            build,
            input_digest,
            runtime_bundle,
            bootstrap_receipt_sha256,
            records,
        )
        ready_receipt = {
            **base_receipt,
            "schema_version": 2,
            "status": "READY",
            "plugin_build": build,
            "plugin_manifest_sha256": manifest_digest,
            "project_input_sha256": project_input_digest(project_root),
            "project_output_sha256": project_output_digest(project_root),
            "layout_state": layout_state,
            "evidence_ref": f"evidence:{evidence.relative_to(project_root).as_posix()}",
            "session_id": safe_session_id,
            **runtime_bundle,
        }
        canonical_receipt_path = session_receipt_path(governance, safe_session_id)
        prior_ready = load_receipt(canonical_receipt_path)
        if prior_ready is None and receipt is not None and receipt.get("status") == "READY":
            prior_ready = receipt
        if ready_receipt_is_reusable(prior_ready, ready_receipt):
            ready_receipt = cast(Dict[str, Any], prior_ready)
        else:
            atomic_write_json(
                evidence,
                {
                    **ready_receipt,
                    "hook_source": hook_input.get("source"),
                    "commands": records,
                },
            )
        atomic_write_json(canonical_receipt_path, ready_receipt)
        install_legacy_ready_receipt_if_absent(governance, ready_receipt)
        receipt_path = canonical_receipt_path
        receipt_relative = receipt_path.relative_to(project_root).as_posix()
        receipt_sha256 = sha256_file(receipt_path)
        uv_path = shutil.which("uv") or "uv"
        intake_command = [
            uv_path,
            "run",
            "--no-project",
            "--offline",
            "--cache-dir",
            str(governance / "cache" / "uv"),
            "--no-python-downloads",
            "--script",
            str(controller),
            "--receipt-sha256",
            receipt_sha256,
            "intake",
            "status",
        ]
        emit_context(
            "WORK_GOVERNANCE_BOOTSTRAP READY; layout=LAYOUT_READY; "
            f"build={build}; receipt={receipt_relative}; receipt_sha256={receipt_sha256}; "
            f"intake_command={shlex.join(intake_command)}. "
            "Plan-controlled work must load "
            "work-governance:work-lifecycle and confirm both layout and Plan "
            "authority before task action."
        )
        return 0
    except (BootstrapError, OSError, subprocess.SubprocessError) as exc:
        reason = str(exc).replace("\n", " ")[:500]
        detail = failed_command_detail(records)
        blocked_evidence_ref = "unavailable"
        try:
            if governance is not None:
                invalidate_legacy_ready_for_session(governance, session_id)
            if (
                governance is not None
                and isinstance(build, str)
                and isinstance(manifest_digest, str)
                and isinstance(input_digest, str)
            ):
                blocked_evidence_ref = persist_blocked_failure(
                    governance,
                    base_receipt=base_receipt,
                    reason=reason,
                    build=build,
                    manifest_digest=manifest_digest,
                    input_digest=input_digest,
                    records=records,
                    hook_source=hook_source,
                    session_id=session_id,
                    receipt_path=receipt_path,
                    journal_path=failure_journal_path,
                )
            elif governance is not None and receipt_path is not None:
                invalidate_bootstrap_receipt(governance.parent, receipt_path)
        except (BootstrapError, OSError) as record_error:
            reason = f"{reason}; BLOCKED_RECORD_FAILED: {record_error}"[:500]
        layout_command_prefix = ""
        if (
            governance is not None
            and controller is not None
            and bootstrap_receipt_sha256 is not None
        ):
            uv_path = shutil.which("uv") or "uv"
            prefix = [
                uv_path,
                "run",
                "--no-project",
                "--offline",
                "--cache-dir",
                str(governance / "cache" / "uv"),
                "--no-python-downloads",
                "--script",
                str(controller),
                "--receipt-sha256",
                bootstrap_receipt_sha256,
            ]
            layout_command_prefix = f" layout_command_prefix={shlex.join(prefix)}."
        emit_context(
            f"WORK_GOVERNANCE_BOOTSTRAP ENVIRONMENT_BLOCKED; hook=executed; "
            f"source={hook_source or 'unknown'}; reason={reason}; detail={detail}; "
            f"evidence={blocked_evidence_ref}.{layout_command_prefix} "
            "Do not perform Plan-controlled work. "
            f"Next allowed recovery: {blocked_recovery_action(reason, detail)}."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
