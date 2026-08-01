#!/usr/bin/env python3
"""Issue one trusted, project-local receipt for the current Codex user turn."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

GOVERNANCE_DIR = ".work-governance"
SESSION_RECEIPT_NAME = "bootstrap-state.json"
TURN_RECEIPT_NAME = "current-turn-receipt.json"
SESSIONS_DIR_NAME = "sessions"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class TurnReceiptError(RuntimeError):
    """Describe a fail-closed current-turn receipt condition."""


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA256 digest of *payload*."""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one regular file without following a symlink."""
    if path.is_symlink() or not path.is_file():
        raise TurnReceiptError(f"TURN_RECEIPT_INPUT_NOT_REGULAR: {path}")
    return sha256_bytes(path.read_bytes())


def utc_now() -> str:
    """Return a second-resolution RFC 3339 UTC timestamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json_object(path: Path, error: str) -> dict[str, object]:
    """Load one regular UTF-8 JSON object or raise *error*."""
    if path.is_symlink() or not path.is_file():
        raise TurnReceiptError(error)
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise TurnReceiptError(error) from exc
    if not isinstance(payload, dict):
        raise TurnReceiptError(error)
    return cast(dict[str, object], payload)


def required_string(payload: Mapping[str, object], field: str, error: str) -> str:
    """Return one required non-empty string field."""
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise TurnReceiptError(error)
    return value


def load_hook_input() -> dict[str, object]:
    """Parse the official UserPromptSubmit JSON object."""
    try:
        payload: object = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        raise TurnReceiptError("INVALID_USER_PROMPT_SUBMIT_INPUT") from exc
    if not isinstance(payload, dict):
        raise TurnReceiptError("INVALID_USER_PROMPT_SUBMIT_INPUT")
    return cast(dict[str, object], payload)


def validate_hook_input(payload: Mapping[str, object]) -> None:
    """Validate the official fields after invalidating any prior receipt."""
    if payload.get("hook_event_name") != "UserPromptSubmit":
        raise TurnReceiptError("UNEXPECTED_HOOK_EVENT")
    session_id = required_string(payload, "session_id", "TURN_SESSION_ID_REQUIRED")
    turn_id = required_string(payload, "turn_id", "TURN_ID_REQUIRED")
    required_string(payload, "cwd", "TURN_CWD_REQUIRED")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        raise TurnReceiptError("TURN_PROMPT_REQUIRED")
    if IDENTIFIER_RE.fullmatch(session_id) is None or IDENTIFIER_RE.fullmatch(turn_id) is None:
        raise TurnReceiptError("TURN_IDENTITY_INVALID")


def discover_project_root(cwd: Path) -> Path:
    """Return the nearest physical Git worktree root or the physical cwd."""
    resolved = cwd.resolve()
    if not resolved.is_dir():
        raise TurnReceiptError("TURN_CWD_INVALID")
    for candidate in (resolved, *resolved.parents):
        marker = candidate / ".git"
        if marker.exists() or marker.is_symlink():
            return candidate
    return resolved


def installed_plugin_root() -> Path:
    """Return the installed plugin root supplied by Codex."""
    raw_root = os.environ.get("PLUGIN_ROOT")
    root = Path(raw_root).resolve() if raw_root else Path(__file__).resolve().parents[1]
    if not (root / ".codex-plugin" / "plugin.json").is_file():
        raise TurnReceiptError("PLUGIN_ROOT_INVALID")
    return root


def installed_plugin_build(root: Path) -> str:
    """Read the installed plugin build from its manifest."""
    manifest = load_json_object(
        root / ".codex-plugin" / "plugin.json",
        "PLUGIN_MANIFEST_INVALID",
    )
    return required_string(manifest, "version", "PLUGIN_VERSION_MISSING")


def checked_project_path(project_root: Path, raw_path: str) -> Path:
    """Resolve a project-relative receipt path without allowing escape."""
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or ".." in candidate.parts:
        raise TurnReceiptError("SESSION_RECEIPT_RUNTIME_INVALID")
    resolved = (project_root / candidate).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise TurnReceiptError("SESSION_RECEIPT_RUNTIME_INVALID") from exc
    return resolved


def reject_symlink_components(project_root: Path, path: Path) -> None:
    """Reject existing symlinks in a project-local control path."""
    try:
        relative = path.relative_to(project_root)
    except ValueError as exc:
        raise TurnReceiptError("TURN_RECEIPT_PATH_OUTSIDE_PROJECT") from exc
    current = project_root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise TurnReceiptError("TURN_RECEIPT_CONTROL_PATH_SYMLINK")


def validate_session_receipt(
    project_root: Path,
    *,
    expected_session_id: str,
    expected_plugin_build: str,
) -> tuple[dict[str, object], str]:
    """Validate this session's READY receipt and exact runtime bundle."""
    scoped = session_state_dir(project_root, expected_session_id) / SESSION_RECEIPT_NAME
    legacy = project_root / GOVERNANCE_DIR / SESSION_RECEIPT_NAME
    receipt_path = scoped if scoped.is_file() and not scoped.is_symlink() else legacy
    receipt = load_json_object(receipt_path, "SESSION_RECEIPT_REQUIRED")
    if (
        receipt.get("schema_version") != 2
        or receipt.get("status") != "READY"
        or receipt.get("layout_state") != "LAYOUT_READY"
        or receipt.get("session_id") != expected_session_id
        or receipt.get("plugin_build") != expected_plugin_build
    ):
        raise TurnReceiptError("SESSION_RECEIPT_MISMATCH")
    controller_ref = required_string(
        receipt,
        "controller_ref",
        "SESSION_RECEIPT_RUNTIME_INVALID",
    )
    lifecycle_ref = required_string(
        receipt,
        "lifecycle_ref",
        "SESSION_RECEIPT_RUNTIME_INVALID",
    )
    bundle_ref = required_string(
        receipt,
        "runtime_bundle_ref",
        "SESSION_RECEIPT_RUNTIME_INVALID",
    )
    controller_sha256 = required_string(
        receipt,
        "controller_sha256",
        "SESSION_RECEIPT_RUNTIME_INVALID",
    )
    lifecycle_sha256 = required_string(
        receipt,
        "lifecycle_sha256",
        "SESSION_RECEIPT_RUNTIME_INVALID",
    )
    if (
        SHA256_RE.fullmatch(controller_sha256) is None
        or SHA256_RE.fullmatch(lifecycle_sha256) is None
    ):
        raise TurnReceiptError("SESSION_RECEIPT_RUNTIME_INVALID")
    controller = checked_project_path(project_root, controller_ref)
    lifecycle = checked_project_path(project_root, lifecycle_ref)
    bundle = checked_project_path(project_root, bundle_ref)
    reject_symlink_components(project_root, bundle)
    if (
        not bundle.is_dir()
        or controller.parent != bundle
        or lifecycle.parent != bundle
        or sha256_file(controller) != controller_sha256
        or sha256_file(lifecycle) != lifecycle_sha256
    ):
        raise TurnReceiptError("SESSION_RECEIPT_RUNTIME_INVALID")
    return receipt, sha256_file(receipt_path)


def session_state_dir(project_root: Path, session_id: str) -> Path:
    """Return one bounded session directory without permitting control-path escape."""
    path = project_root / GOVERNANCE_DIR / "runtime" / SESSIONS_DIR_NAME / session_id
    reject_symlink_components(project_root, path)
    return path


def canonical_receipt_sha256(payload: Mapping[str, object]) -> str:
    """Hash the canonical receipt projection that excludes its self digest."""
    projected = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    encoded = json.dumps(
        projected,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically and durably replace one small local JSON object."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise TurnReceiptError("TURN_RECEIPT_TARGET_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def invalidate_prior_turn_receipt(project_root: Path, session_id: str) -> Path:
    """Atomically replace only this session's prior receipt with a tombstone."""
    turn_receipt_path = session_state_dir(project_root, session_id) / TURN_RECEIPT_NAME
    reject_symlink_components(project_root, turn_receipt_path.parent)
    atomic_write_json(
        turn_receipt_path,
        {
            "schema_version": 1,
            "kind": "work-governance-current-turn-invalid",
            "issued_at": utc_now(),
        },
    )
    return turn_receipt_path


def install_legacy_turn_receipt_if_safe(
    project_root: Path,
    receipt: Mapping[str, object],
) -> None:
    """Maintain a single-session compatibility file without crossing sessions."""
    legacy = project_root / GOVERNANCE_DIR / "runtime" / TURN_RECEIPT_NAME
    reject_symlink_components(project_root, legacy)
    if legacy.exists() or legacy.is_symlink():
        current = load_json_object(legacy, "TURN_RECEIPT_TARGET_INVALID")
        if current.get("session_id") != receipt.get("session_id"):
            return
    atomic_write_json(legacy, receipt)


def emit_context(message: str) -> None:
    """Emit bounded UserPromptSubmit additional developer context."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    """Issue the current-turn receipt or inject a fail-closed diagnostic."""
    project_root: Path | None = None
    prior_invalidated = False
    try:
        hook_input = load_hook_input()
        raw_cwd = hook_input.get("cwd")
        project_root = discover_project_root(
            Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
        )
        session_id = required_string(
            hook_input,
            "session_id",
            "TURN_SESSION_ID_REQUIRED",
        )
        if IDENTIFIER_RE.fullmatch(session_id) is None:
            raise TurnReceiptError("TURN_IDENTITY_INVALID")
        turn_receipt_path = invalidate_prior_turn_receipt(project_root, session_id)
        prior_invalidated = True
        validate_hook_input(hook_input)
        turn_id = required_string(hook_input, "turn_id", "TURN_ID_REQUIRED")
        prompt = cast(str, hook_input["prompt"])
        plugin_root = installed_plugin_root()
        build = installed_plugin_build(plugin_root)
        _session_receipt, session_receipt_sha256 = validate_session_receipt(
            project_root,
            expected_session_id=session_id,
            expected_plugin_build=build,
        )
        prompt_sha256 = sha256_bytes(prompt.encode("utf-8"))
        request_ref = f"user:session/{session_id}/turn/{turn_id}/sha256/{prompt_sha256}"
        receipt: dict[str, object] = {
            "schema_version": 1,
            "kind": "work-governance-current-turn-receipt",
            "plugin_build": build,
            "session_start_receipt_sha256": session_receipt_sha256,
            "session_id": session_id,
            "turn_id": turn_id,
            "prompt_sha256": prompt_sha256,
            "request_ref": request_ref,
            "project_root": project_root.as_posix(),
            "issued_at": utc_now(),
        }
        receipt["receipt_sha256"] = canonical_receipt_sha256(receipt)
        atomic_write_json(turn_receipt_path, receipt)
        install_legacy_turn_receipt_if_safe(project_root, receipt)
        emit_context(
            "WORK_GOVERNANCE_TURN_RECEIPT READY; "
            f"request_ref={request_ref}; "
            f"turn_receipt_sha256={receipt['receipt_sha256']}. "
            "For a simple No-Plan answer, answer directly and create no Plan, index, "
            "or project log. For every other request, explicitly decide proceed, "
            "explore, or ask after stating target, knowns, locally explorable unknowns, "
            "user-owned unknowns, and rationale. Choose explore when a fact must be "
            "discovered before the requested outcome; do not choose proceed merely "
            "because that exploration is safe or local. Summarize rationale without "
            "copying secrets or raw prompt content. Show one INTAKE_RECEIPT on first "
            "classification; show INTAKE_REVISION only when the demand contract materially "
            "changes."
        )
        return 0
    except (OSError, TurnReceiptError) as exc:
        if not prior_invalidated:
            try:
                fallback_root = project_root or discover_project_root(Path.cwd())
                fallback_session = (
                    hook_input.get("session_id") if "hook_input" in locals() else None
                )
                if isinstance(fallback_session, str) and IDENTIFIER_RE.fullmatch(fallback_session):
                    invalidate_prior_turn_receipt(fallback_root, fallback_session)
            except (OSError, TurnReceiptError):
                pass
        reason = str(exc).replace("\n", " ")[:400]
        emit_context(
            "WORK_GOVERNANCE_TURN_RECEIPT ENVIRONMENT_BLOCKED; "
            f"reason={reason}. Simple No-Plan answers may continue without project "
            "writes. Do not advance Plan-controlled work until a trusted "
            "UserPromptSubmit receipt is available."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
