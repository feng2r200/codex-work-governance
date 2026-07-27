#!/usr/bin/env python3
# ruff: noqa: UP006, UP017, UP035, UP045
"""Prepare Work Governance layout state for one Codex session.

This hook intentionally uses only the Python standard library. It prewarms the
controller's locked PEP 723 dependency environment in the project-local UV
cache, then runs every state-changing or validating controller command offline.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

ACTION_REVISION = 2
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
BOOTSTRAP_EVIDENCE_NAME_RE = re.compile(r"^\d{8}T\d{6}\.\d{6}Z-\d+\.json$")
LAYOUT_TRANSACTION_RE = re.compile(
    r"^LAY-\d{8}T\d{6}Z-[0-9a-f]{8}(?:-[0-9a-f]{8}(?:[0-9a-f]{8}){0,3})?$"
)


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
        or payload.get("action_revision") != ACTION_REVISION
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
    """Exclusively claim a newly created root before creating local infrastructure."""
    runtime = staging / "runtime"
    runtime.mkdir()
    claim = runtime / CLAIM_NAME
    payload = {
        "schema_version": 1,
        "kind": "work-governance-bootstrap-claim",
        "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
        "action_revision": ACTION_REVISION,
        "project_root": project_root.resolve().as_posix(),
        "created_at": utc_now(),
        "creator": "session-start",
        "controller_sha256": controller_sha256,
        "project_input_sha256": input_digest,
    }
    descriptor = os.open(
        str(claim),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
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
        or parsed.get("legacy_migration_action_revision") != "2"
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
        proof_expected = [
            (0, "schema_version"),
            (0, "kind"),
            (0, "transaction_id"),
            (0, "status"),
            (0, "legacy_manifest_sha256"),
            (0, "legacy_adoption_sha256"),
            (0, "conversion_table_sha256"),
            (0, "created_at"),
        ]
        proof_lines = proof.read_text(encoding="utf-8").splitlines()
        proof_values: Dict[str, str] = {}
        if len(proof_lines) != len(proof_expected):
            raise BootstrapError("GOVERNANCE_VERSION_UNPROVEN")
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
        or receipt.get("action_revision") != ACTION_REVISION
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
    expected_evidence_keys = (BLOCKED_RECEIPT_KEYS - {"evidence_sha256"}) | {"commands"}
    if (
        not isinstance(evidence, dict)
        or set(evidence) != expected_evidence_keys
        or not isinstance(evidence.get("commands"), list)
        or any(evidence.get(key) != receipt.get(key) for key in receipt if key != "evidence_sha256")
    ):
        raise BootstrapError("UNCOMMITTED_BOOTSTRAP_EVIDENCE_INVALID")
    return {evidence_path.resolve()}


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
    for name in ("logs", "worktrees", "proposals"):
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
        if LAYOUT_TRANSACTION_RE.fullmatch(child.name) is None:
            raise BootstrapError("UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID")
        transactions.append(child)
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
                ("layout-migrations", bool(migration_names)),
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


def ensure_local_directories(
    project_root: Path,
    *,
    controller_sha256: str,
    input_digest: str,
) -> Path:
    """Prove first ownership, then create only declared local infrastructure."""
    governance = project_root / GOVERNANCE_DIR
    staging = project_root / BOOTSTRAP_STAGING_NAME
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
    return governance


def project_input_digest(project_root: Path) -> str:
    """Fingerprint layout inputs while excluding normal canonical Plan revisions."""
    governance = project_root / GOVERNANCE_DIR
    version = governance / "version.yaml"
    paths: List[Tuple[str, Path]] = [
        ("legacy-plan", legacy_plan_path(project_root)),
        ("version", version),
        ("ignore", governance / ".gitignore"),
        ("runtime", governance / "runtime"),
    ]
    if not version.is_file():
        paths.extend(
            [
                ("legacy-logs", legacy_logs_path(project_root)),
                ("agents", project_root / "AGENTS.md"),
                ("claude", project_root / "CLAUDE.md"),
            ]
        )
    return stable_digest([{"name": name, "manifest": path_manifest(path)} for name, path in paths])


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


def json_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the exact bytes used by atomic JSON records."""
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def recover_blocked_failure(governance: Path) -> None:
    """Finish an interrupted blocked evidence/receipt installation."""
    project_root = governance.parent
    runtime = governance / "runtime"
    reject_symlink_components(project_root, runtime)
    if not runtime.is_dir():
        raise BootstrapError("BOOTSTRAP_FAILURE_RUNTIME_INVALID")
    journal = runtime / FAILURE_JOURNAL_NAME
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
    atomic_write_json(governance / RECEIPT_NAME, receipt_payload)
    validate_blocked_record(governance)
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
) -> None:
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
    evidence_payload = {**common, "commands": [dict(record) for record in records]}
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
    atomic_write_json(governance / "runtime" / FAILURE_JOURNAL_NAME, journal_payload)
    if os.environ.get("WORK_GOVERNANCE_TEST_INTERRUPT_FAILURE_AFTER_JOURNAL") == "1":
        raise BootstrapError("BOOTSTRAP_TEST_INTERRUPTED_FAILURE_INSTALL")
    recover_blocked_failure(governance)


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
    installed_plugin: Path,
    receipt: Optional[Dict[str, Any]],
    manifest_digest: str,
    build: str,
    input_digest: str,
    records: List[Dict[str, Any]],
) -> str:
    """Prewarm when needed, then execute all controller work offline."""
    governance = project_root / GOVERNANCE_DIR
    cache = governance / "cache" / "uv"
    controller = installed_plugin / "scripts" / "workctl.py"
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise BootstrapError("UV_NOT_AVAILABLE")
    environment = dict(os.environ)
    environment["UV_CACHE_DIR"] = str(cache)
    environment["UV_PYTHON_DOWNLOADS"] = "never"
    matching_ready = bool(
        receipt
        and receipt.get("status") == "READY"
        and receipt.get("action_revision") == ACTION_REVISION
        and receipt.get("bootstrap_contract_version") == BOOTSTRAP_CONTRACT_VERSION
        and receipt.get("plugin_build") == build
        and receipt.get("plugin_manifest_sha256") == manifest_digest
        and receipt.get("project_input_sha256") == input_digest
        and receipt.get("project_output_sha256") == project_output_digest(project_root)
    )
    if not matching_ready:
        prewarm = uv_controller_command(uv_path, cache, controller, ["--help"], offline=False)
        prewarm_result = run_command(prewarm, cwd=project_root, environment=environment)
        records.append(command_record(prewarm, prewarm_result))
        if prewarm_result.returncode != 0:
            raise BootstrapError("CONTROLLER_PREWARM_FAILED")
        migrate = uv_controller_command(
            uv_path,
            cache,
            controller,
            ["layout", "migrate"],
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
    evidence: Optional[Path] = None
    build: Optional[str] = None
    manifest_digest: Optional[str] = None
    input_digest: Optional[str] = None
    records: List[Dict[str, Any]] = []
    base_receipt: Dict[str, Any] = {
        "schema_version": 1,
        "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
        "action_revision": ACTION_REVISION,
        "updated_at": utc_now(),
    }
    try:
        hook_input = load_hook_input()
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
        receipt_path = governance / RECEIPT_NAME
        evidence = evidence_path(governance)
        input_digest = project_input_digest(project_root)
        receipt = load_receipt(receipt_path)
        layout_state = run_bootstrap(
            project_root,
            installed_plugin,
            receipt,
            manifest_digest,
            build,
            input_digest,
            records,
        )
        ready_receipt = {
            **base_receipt,
            "status": "READY",
            "plugin_build": build,
            "plugin_manifest_sha256": manifest_digest,
            "project_input_sha256": project_input_digest(project_root),
            "project_output_sha256": project_output_digest(project_root),
            "layout_state": layout_state,
            "evidence_ref": f"evidence:{evidence.relative_to(project_root).as_posix()}",
        }
        atomic_write_json(
            evidence,
            {
                **ready_receipt,
                "hook_source": hook_input.get("source"),
                "commands": records,
            },
        )
        atomic_write_json(receipt_path, ready_receipt)
        receipt_relative = receipt_path.relative_to(project_root).as_posix()
        emit_context(
            "WORK_GOVERNANCE_BOOTSTRAP READY; layout=LAYOUT_READY; "
            f"build={build}; receipt={receipt_relative}. "
            "Plan-controlled work must load "
            "work-governance:work-lifecycle and confirm both layout and Plan "
            "authority before task action."
        )
        return 0
    except (BootstrapError, OSError, subprocess.SubprocessError) as exc:
        reason = str(exc).replace("\n", " ")[:500]
        blocked_receipt = {
            **base_receipt,
            "status": "ENVIRONMENT_BLOCKED",
            "reason": reason,
        }
        try:
            if (
                governance is not None
                and not (governance / "version.yaml").exists()
                and isinstance(build, str)
                and isinstance(manifest_digest, str)
                and isinstance(input_digest, str)
            ):
                persist_blocked_failure(
                    governance,
                    base_receipt=base_receipt,
                    reason=reason,
                    build=build,
                    manifest_digest=manifest_digest,
                    input_digest=input_digest,
                    records=records,
                )
            elif governance is not None and (governance / "version.yaml").is_file():
                if evidence is None:
                    evidence = evidence_path(governance)
                evidence_relative = evidence.relative_to(governance.parent).as_posix()
                blocked_receipt["evidence_ref"] = f"evidence:{evidence_relative}"
                atomic_write_json(
                    evidence,
                    {**blocked_receipt, "commands": records},
                )
                if receipt_path is not None:
                    atomic_write_json(receipt_path, blocked_receipt)
        except (BootstrapError, OSError) as record_error:
            reason = f"{reason}; BLOCKED_RECORD_FAILED: {record_error}"[:500]
        emit_context(
            f"WORK_GOVERNANCE_BOOTSTRAP ENVIRONMENT_BLOCKED; reason={reason}. "
            "Do not perform Plan-controlled work. Restore a trusted/enabled "
            "SessionStart hook and a valid READY receipt, then start a fresh "
            "session."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
