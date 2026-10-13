#!/usr/bin/python3 -I
"""Install and inspect the stable Work Governance hook runtime."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

CONTRACT = "wg-hook-v1"
ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "plugins" / "work-governance" / "runtime"
LAUNCHER_SOURCE = ROOT / "scripts" / "work-governance-hook"
HOOKS_SOURCE = ROOT / "plugins" / "work-governance" / "hooks" / "hooks.json"
USER_HOOKS_RELATIVE_PATH = Path(".codex") / "hooks.json"
USER_HOOK_ROLLBACK_RELATIVE_PATH = Path(".codex") / ".work-governance-hooks.rollback.json"
MANAGED_LAUNCHER = "$HOME/.local/bin/work-governance-hook"
MANAGED_EVENT_HANDLERS = {
    "SessionStart": "session-start",
    "PreCompact": "pre-compact",
    "PostToolUse": "post-tool-use",
}
MANAGED_HANDLERS = frozenset(MANAGED_EVENT_HANDLERS.values())
POST_TOOL_USE_MATCHER = "Bash|Write|Edit|functions\\.exec|functions\\.apply_patch|mcp__.*"
ROLLBACK_RECEIPT_SCHEMA_VERSION = 1


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _empty_user_hook_config() -> dict[str, object]:
    return {
        "description": "User-level Codex hooks installed by Work Governance.",
        "hooks": {},
    }


def _source_manifest() -> tuple[dict[str, Any], str]:
    manifest = json.loads((RUNTIME_ROOT / "package.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(_canonical(manifest)).hexdigest()
    if manifest.get("contract") != CONTRACT or manifest.get("schema_version") != 1:
        raise RuntimeError("source package manifest is incompatible")
    for entry in manifest.get("files", []):
        path = RUNTIME_ROOT / entry["path"]
        if path.name != entry["path"] or path.is_symlink() or not path.is_file():
            raise RuntimeError(f"source package file is unsafe: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"source package file digest mismatch: {path}")
    return manifest, digest


def _private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError(f"installation directory is unsafe: {path}")


def _safe_parent_dir(path: Path) -> None:
    """Create a parent directory without tightening unrelated existing modes."""
    path.mkdir(mode=0o755, parents=True, exist_ok=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"installation parent is not a real directory: {path}")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise RuntimeError(f"installation parent is not safely owner-controlled: {path}")


def _atomic_replace(target: Path, content: bytes, mode: int, prefix: str) -> None:
    temporary = target.parent / (f"{prefix}.{os.getpid()}.{time.time_ns()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        try:
            remaining = memoryview(content)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("atomic write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _read_regular_bytes(
    path: Path, description: str, *, require_private: bool, missing_is_none: bool
) -> bytes | None:
    try:
        initial = path.lstat()
    except FileNotFoundError:
        if missing_is_none:
            return None
        raise RuntimeError(f"{description} is missing") from None
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise RuntimeError(f"{description} is not a real regular file: {path}")
    if initial.st_uid != os.getuid() or (require_private and stat.S_IMODE(initial.st_mode) & 0o077):
        raise RuntimeError(f"{description} is not owner-private: {path}")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        if missing_is_none:
            return None
        raise RuntimeError(f"{description} is missing") from None
    except OSError as error:
        raise RuntimeError(f"{description} could not be opened safely: {path}") from error
    try:
        opened = os.fstat(descriptor)
        if stat.S_ISLNK(opened.st_mode) or not stat.S_ISREG(opened.st_mode):
            raise RuntimeError(f"{description} is not a real regular file: {path}")
        if opened.st_uid != os.getuid() or (
            require_private and stat.S_IMODE(opened.st_mode) & 0o077
        ):
            raise RuntimeError(f"{description} is not owner-private: {path}")
        if (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino):
            raise RuntimeError(f"{description} changed while opening: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 64 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_private_regular(path: Path, description: str) -> bytes | None:
    return _read_regular_bytes(path, description, require_private=True, missing_is_none=True)


def _read_source_regular(path: Path, description: str) -> bytes:
    result = _read_regular_bytes(path, description, require_private=False, missing_is_none=False)
    assert result is not None
    return result


def _open_private_lock(path: Path, description: str) -> int:
    try:
        initial = path.lstat()
    except FileNotFoundError:
        initial = None
    if initial is not None and (
        stat.S_ISLNK(initial.st_mode)
        or not stat.S_ISREG(initial.st_mode)
        or initial.st_uid != os.getuid()
        or stat.S_IMODE(initial.st_mode) & 0o077
    ):
        raise RuntimeError(f"{description} is not owner-private")
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as error:
        raise RuntimeError(f"{description} could not be opened safely") from error
    opened = os.fstat(descriptor)
    try:
        current = path.lstat()
        if (
            stat.S_ISLNK(opened.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            or (
                initial is not None
                and (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino)
            )
        ):
            raise RuntimeError(f"{description} is not owner-private")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _parse_hook_config(data: bytes, description: str) -> dict[str, object]:
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{description} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{description} must be a JSON object")
    hooks = parsed.get("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError(f"{description} hooks must be a JSON object")
    for event, groups in hooks.items():
        if not isinstance(event, str) or not isinstance(groups, list):
            raise RuntimeError(f"{description} has an invalid hook event")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise RuntimeError(f"{description} has an invalid hook group")
            if not all(isinstance(hook, dict) for hook in group["hooks"]):
                raise RuntimeError(f"{description} has an invalid hook handler")
    return parsed


def _managed_hook_digest(command: object) -> str | None:
    if not isinstance(command, str):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if len(tokens) != 8:
        return None
    if tokens[:5] != [MANAGED_LAUNCHER, "dispatch", "--contract", CONTRACT, "--package-digest"]:
        return None
    digest = tokens[5]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        return None
    if tokens[6] != "--handler" or tokens[7] not in MANAGED_HANDLERS:
        return None
    return digest


def _managed_hook_handler(command: object) -> str | None:
    if _managed_hook_digest(command) is None:
        return None
    assert isinstance(command, str)
    return shlex.split(command)[7]


def _is_managed_hook(hook: object) -> bool:
    return (
        isinstance(hook, dict)
        and hook.get("type") == "command"
        and _managed_hook_digest(hook.get("command")) is not None
    )


def _managed_definition(config: dict[str, object]) -> list[dict[str, object]]:
    hooks = config.get("hooks", {})
    assert isinstance(hooks, dict)
    definitions: list[dict[str, object]] = []
    for event, groups in hooks.items():
        assert isinstance(event, str)
        assert isinstance(groups, list)
        for group in groups:
            assert isinstance(group, dict)
            handlers = group["hooks"]
            assert isinstance(handlers, list)
            managed_handlers = [hook for hook in handlers if _is_managed_hook(hook)]
            if not managed_handlers:
                continue
            managed_group = json.loads(_canonical(group))
            assert isinstance(managed_group, dict)
            managed_group["hooks"] = managed_handlers
            definitions.append({"event": event, "group": managed_group})
    return sorted(
        definitions,
        key=lambda definition: (
            str(definition["event"]),
            _canonical(definition["group"]),
        ),
    )


def _definition_digest(definition: list[dict[str, object]]) -> str:
    return hashlib.sha256(_canonical(definition)).hexdigest()


def _definition_as_config(definition: list[dict[str, object]]) -> dict[str, object]:
    hooks: dict[str, list[object]] = {}
    for item in definition:
        event = item.get("event")
        group = item.get("group")
        assert isinstance(event, str)
        assert isinstance(group, dict)
        hooks.setdefault(event, []).append(json.loads(_canonical(group)))
    return {"hooks": hooks}


def _validate_managed_definition(definition: object, description: str) -> list[dict[str, object]]:
    if not isinstance(definition, list):
        raise RuntimeError(f"{description} is not a managed Hook definition list")
    normalized: list[dict[str, object]] = []
    for item in definition:
        if not isinstance(item, dict):
            raise RuntimeError(f"{description} has an invalid managed Hook definition")
        event = item.get("event")
        group = item.get("group")
        if not isinstance(event, str) or not isinstance(group, dict):
            raise RuntimeError(f"{description} has an invalid managed Hook definition")
        handlers = group.get("hooks")
        if (
            not isinstance(handlers, list)
            or not handlers
            or not all(_is_managed_hook(handler) for handler in handlers)
        ):
            raise RuntimeError(f"{description} has an incompatible managed Hook definition")
        copied_group = json.loads(_canonical(group))
        assert isinstance(copied_group, dict)
        normalized.append({"event": event, "group": copied_group})
    normalized.sort(
        key=lambda item: (
            str(item["event"]),
            _canonical(item["group"]),
        )
    )
    if len({_canonical(item) for item in normalized}) != len(normalized):
        raise RuntimeError(f"{description} has duplicate managed Hook definitions")
    return normalized


def _expected_hook_config(expected_package_digest: str) -> dict[str, object]:
    hooks: dict[str, list[object]] = {}
    for event, handler in MANAGED_EVENT_HANDLERS.items():
        group: dict[str, object] = {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        f"{MANAGED_LAUNCHER} dispatch --contract {CONTRACT} "
                        f"--package-digest {expected_package_digest} --handler {handler}"
                    ),
                }
            ]
        }
        if event == "PostToolUse":
            group["matcher"] = POST_TOOL_USE_MATCHER
        hooks[event] = [group]
    return {"hooks": hooks}


def _source_hooks(expected_package_digest: str) -> tuple[dict[str, object], str]:
    data = _read_source_regular(HOOKS_SOURCE, "source Hook definition")
    parsed = _parse_hook_config(data, "source Hook definition")
    expected = _expected_hook_config(expected_package_digest)
    if parsed.get("hooks") != expected["hooks"]:
        raise RuntimeError("source Hook definition differs from the exact managed contract")
    definition = _managed_definition(expected)
    if len(definition) != len(MANAGED_EVENT_HANDLERS):
        raise RuntimeError("source Hook definition does not provide every managed handler")
    return expected, _definition_digest(definition)


def _merge_user_hooks(
    existing: dict[str, object] | None, candidate: dict[str, object]
) -> dict[str, object]:
    if existing is None:
        merged = _empty_user_hook_config()
    else:
        merged = json.loads(_canonical(existing))
        assert isinstance(merged, dict)
    existing_hooks = merged.get("hooks", {})
    candidate_hooks = candidate["hooks"]
    assert isinstance(existing_hooks, dict)
    assert isinstance(candidate_hooks, dict)
    retained_hooks: dict[str, object] = {}
    for event, groups in existing_hooks.items():
        assert isinstance(event, str)
        assert isinstance(groups, list)
        retained_groups: list[object] = []
        for group in groups:
            assert isinstance(group, dict)
            handlers = group["hooks"]
            assert isinstance(handlers, list)
            retained_handlers = [handler for handler in handlers if not _is_managed_hook(handler)]
            if retained_handlers:
                retained_group = json.loads(_canonical(group))
                assert isinstance(retained_group, dict)
                retained_group["hooks"] = retained_handlers
                retained_groups.append(retained_group)
        if retained_groups:
            retained_hooks[event] = retained_groups
    for event, groups in candidate_hooks.items():
        assert isinstance(event, str)
        assert isinstance(groups, list)
        copied_groups = json.loads(_canonical(groups))
        assert isinstance(copied_groups, list)
        retained_hooks.setdefault(event, [])
        current_groups = retained_hooks[event]
        assert isinstance(current_groups, list)
        current_groups.extend(copied_groups)
    merged["hooks"] = retained_hooks
    return merged


def _managed_hook_commands(config: dict[str, object]) -> list[str]:
    commands: list[str] = []
    for item in _managed_definition(config):
        group = item["group"]
        assert isinstance(group, dict)
        handlers = group["hooks"]
        assert isinstance(handlers, list)
        for handler in handlers:
            assert isinstance(handler, dict)
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)
    return sorted(commands)


def _install_package(home: Path, expected: str | None) -> str:
    manifest, digest = _source_manifest()
    if expected is not None and expected != digest:
        raise RuntimeError(f"expected package digest {expected}, computed {digest}")
    root = home / ".local" / "libexec" / "work-governance"
    for path in (home / ".local", home / ".local" / "libexec"):
        _safe_parent_dir(path)
    _private_dir(root)
    destination = root / digest
    if destination.exists():
        _validate_installed_package(destination, manifest, digest)
        return digest
    temporary = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=root))
    try:
        temporary.chmod(0o700)
        for entry in manifest["files"]:
            target = temporary / entry["path"]
            target.write_bytes((RUNTIME_ROOT / entry["path"]).read_bytes())
            target.chmod(0o600)
        manifest_path = temporary / "package.json"
        manifest_path.write_bytes(_canonical(manifest) + b"\n")
        manifest_path.chmod(0o600)
        os.rename(temporary, destination)
    except OSError:
        if not destination.exists():
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        shutil.rmtree(temporary)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _validate_installed_package(destination, manifest, digest)
    return digest


def _validate_installed_package(
    destination: Path, manifest: dict[str, Any], expected_digest: str
) -> None:
    info = destination.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("installed package is not a real directory")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("installed package is not owner-private")
    installed_manifest = json.loads((destination / "package.json").read_text(encoding="utf-8"))
    if hashlib.sha256(_canonical(installed_manifest)).hexdigest() != expected_digest:
        raise RuntimeError("installed package manifest digest mismatch")
    if installed_manifest != manifest:
        raise RuntimeError("installed package manifest differs from the source manifest")
    expected_names = {"package.json"}
    for entry in manifest["files"]:
        expected_names.add(entry["path"])
        path = destination / entry["path"]
        file_info = path.lstat()
        if stat.S_ISLNK(file_info.st_mode) or not stat.S_ISREG(file_info.st_mode):
            raise RuntimeError(f"installed package file is unsafe: {path}")
        if file_info.st_uid != os.getuid() or stat.S_IMODE(file_info.st_mode) & 0o077:
            raise RuntimeError(f"installed package file is not owner-private: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"installed package file digest mismatch: {path}")
    if {path.name for path in destination.iterdir()} != expected_names:
        raise RuntimeError("installed package tree contains unexpected members")


def _installed_package(home: Path, expected_digest: str) -> None:
    manifest, digest = _source_manifest()
    if digest != expected_digest:
        raise RuntimeError(
            f"expected package digest {expected_digest}, computed source digest {digest}"
        )
    _validate_installed_package(
        home / ".local" / "libexec" / "work-governance" / expected_digest,
        manifest,
        expected_digest,
    )


def _write_private_file(path: Path, expected: bytes, description: str, prefix: str) -> None:
    _atomic_replace(path, expected, 0o600, prefix)
    readback = _read_private_regular(path, description)
    if readback != expected:
        raise RuntimeError(f"{description} readback differs from written bytes")


def _remove_private_file(path: Path, expected: bytes, description: str) -> None:
    current = _read_private_regular(path, description)
    if current != expected:
        raise RuntimeError(f"{description} changed before removal")
    path.unlink()
    if _read_private_regular(path, description) is not None:
        raise RuntimeError(f"{description} was not removed")


def _restore_private_file(
    path: Path, previous: bytes | None, expected: bytes | None, description: str, prefix: str
) -> bool:
    current = _read_private_regular(path, description)
    if current == previous:
        return False
    if current != expected:
        raise RuntimeError(f"{description} changed before rollback")
    if previous is None:
        path.unlink()
        if _read_private_regular(path, description) is not None:
            raise RuntimeError(f"{description} was not removed during rollback")
        return True
    _write_private_file(path, previous, description, prefix)
    return True


def _managed_package_digests(definition: list[dict[str, object]]) -> list[str]:
    digests: set[str] = set()
    for item in definition:
        group = item["group"]
        assert isinstance(group, dict)
        handlers = group["hooks"]
        assert isinstance(handlers, list)
        for handler in handlers:
            assert isinstance(handler, dict)
            digest = _managed_hook_digest(handler.get("command"))
            assert digest is not None
            digests.add(digest)
    return sorted(digests)


def _rollback_receipt(
    previous_definition: list[dict[str, object]],
    candidate_definition: list[dict[str, object]],
    candidate_package_digest: str,
    previous_config_absent: bool,
) -> dict[str, object]:
    return {
        "candidate_definition": candidate_definition,
        "candidate_definition_sha256": _definition_digest(candidate_definition),
        "candidate_package_digest": candidate_package_digest,
        "previous_definition": previous_definition,
        "previous_definition_sha256": _definition_digest(previous_definition),
        "previous_config_absent": previous_config_absent,
        "previous_package_digests": _managed_package_digests(previous_definition),
        "schema_version": ROLLBACK_RECEIPT_SCHEMA_VERSION,
    }


def _parse_rollback_receipt(data: bytes, description: str) -> dict[str, object]:
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{description} is not valid JSON") from error
    if (
        not isinstance(parsed, dict)
        or parsed.get("schema_version") != ROLLBACK_RECEIPT_SCHEMA_VERSION
    ):
        raise RuntimeError(f"{description} has an incompatible schema")
    candidate_package_digest = parsed.get("candidate_package_digest")
    if not isinstance(candidate_package_digest, str) or len(candidate_package_digest) != 64:
        raise RuntimeError(f"{description} has an invalid candidate package digest")
    candidate_definition = _validate_managed_definition(
        parsed.get("candidate_definition"), f"{description} candidate definition"
    )
    previous_definition = _validate_managed_definition(
        parsed.get("previous_definition"), f"{description} previous definition"
    )
    previous_config_absent = parsed.get("previous_config_absent")
    if not isinstance(previous_config_absent, bool):
        raise RuntimeError(f"{description} does not record prior configuration presence")
    if parsed.get("candidate_definition_sha256") != _definition_digest(candidate_definition):
        raise RuntimeError(f"{description} candidate definition digest does not match")
    if parsed.get("previous_definition_sha256") != _definition_digest(previous_definition):
        raise RuntimeError(f"{description} previous definition digest does not match")
    previous_package_digests = parsed.get("previous_package_digests")
    if previous_package_digests != _managed_package_digests(previous_definition):
        raise RuntimeError(f"{description} previous package digests do not match")
    return {
        "candidate_definition": candidate_definition,
        "candidate_package_digest": candidate_package_digest,
        "previous_definition": previous_definition,
        "previous_config_absent": previous_config_absent,
        "previous_package_digests": previous_package_digests,
    }


def _read_rollback_receipt(path: Path) -> tuple[bytes, dict[str, object]] | None:
    data = _read_private_regular(path, "user Hook rollback receipt")
    if data is None:
        return None
    return data, _parse_rollback_receipt(data, "user Hook rollback receipt")


def _rollback_state(
    receipt: dict[str, object],
    expected_package_digest: str,
    candidate_definition: list[dict[str, object]],
) -> str:
    if (
        receipt["candidate_package_digest"] != expected_package_digest
        or receipt["candidate_definition"] != candidate_definition
    ):
        return "stale"
    previous_definition = receipt["previous_definition"]
    assert isinstance(previous_definition, list)
    return "unavailable" if previous_definition == candidate_definition else "available"


def _restore_install_state(
    config_path: Path,
    previous_config: bytes | None,
    expected_config: bytes,
    receipt_path: Path,
    previous_receipt: bytes | None,
    expected_receipt: bytes,
) -> None:
    errors: list[str] = []
    for path, previous, expected, description, prefix in (
        (
            receipt_path,
            previous_receipt,
            expected_receipt,
            "user Hook rollback receipt",
            ".work-governance-hooks.rollback",
        ),
        (
            config_path,
            previous_config,
            expected_config,
            "user Hook configuration",
            ".work-governance-hooks",
        ),
    ):
        try:
            _restore_private_file(path, previous, expected, description, prefix)
        except Exception as error:  # noqa: BLE001 - preserve both failure boundaries.
            errors.append(f"{description}={error}")
    if errors:
        raise RuntimeError("; ".join(errors))


def _install_user_hooks(home: Path, expected_package_digest: str) -> dict[str, object]:
    _installed_package(home, expected_package_digest)
    _probe(home, expected_package_digest)
    candidate, definition_digest = _source_hooks(expected_package_digest)
    config_path = home / USER_HOOKS_RELATIVE_PATH
    receipt_path = home / USER_HOOK_ROLLBACK_RELATIVE_PATH
    _safe_parent_dir(config_path.parent)
    lock_path = config_path.parent / ".work-governance-hooks.install.lock"
    lock_descriptor = _open_private_lock(lock_path, "user Hook installation lock")
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        previous = _read_private_regular(config_path, "user Hook configuration")
        previous_receipt = _read_private_regular(receipt_path, "user Hook rollback receipt")
        if previous_receipt is not None:
            _parse_rollback_receipt(previous_receipt, "user Hook rollback receipt")
        existing = (
            None if previous is None else _parse_hook_config(previous, "user Hook configuration")
        )
        previous_definition = [] if existing is None else _managed_definition(existing)
        candidate_definition = _managed_definition(candidate)
        if previous_definition == candidate_definition:
            rollback_state = "missing"
            if previous_receipt is not None:
                parsed_receipt = _parse_rollback_receipt(
                    previous_receipt,
                    "user Hook rollback receipt",
                )
                rollback_state = _rollback_state(
                    parsed_receipt,
                    expected_package_digest,
                    candidate_definition,
                )
            return {
                "hook_config_installed": True,
                "hook_config_path": str(config_path),
                "hook_definition_sha256": definition_digest,
                "package_digest": expected_package_digest,
                "rollback_receipt_path": str(receipt_path),
                "rollback_state": rollback_state,
                "trust_state": "requires_codex_review",
            }
        merged = _merge_user_hooks(existing, candidate)
        expected = _canonical(merged) + b"\n"
        receipt = _rollback_receipt(
            previous_definition,
            candidate_definition,
            expected_package_digest,
            previous is None,
        )
        expected_receipt = _canonical(receipt) + b"\n"
        try:
            _write_private_file(
                config_path,
                expected,
                "user Hook configuration",
                ".work-governance-hooks",
            )
            readback = _read_private_regular(config_path, "user Hook configuration")
            assert readback is not None
            parsed = _parse_hook_config(readback, "user Hook configuration")
            if parsed != merged:
                raise RuntimeError(
                    "user Hook configuration readback differs from installed definition"
                )
            _write_private_file(
                receipt_path,
                expected_receipt,
                "user Hook rollback receipt",
                ".work-governance-hooks.rollback",
            )
        except Exception as install_error:
            try:
                _restore_install_state(
                    config_path,
                    previous,
                    expected,
                    receipt_path,
                    previous_receipt,
                    expected_receipt,
                )
            except Exception as rollback_error:
                raise RuntimeError(
                    "user Hook installation failed and rollback failed: "
                    f"install={install_error}; rollback={rollback_error}"
                ) from rollback_error
            raise RuntimeError(
                f"user Hook installation failed; previous configuration restored: {install_error}"
            ) from install_error
    finally:
        os.close(lock_descriptor)
    return {
        "hook_config_installed": True,
        "hook_config_path": str(config_path),
        "hook_definition_sha256": definition_digest,
        "package_digest": expected_package_digest,
        "rollback_receipt_path": str(receipt_path),
        "rollback_state": "available",
        "trust_state": "requires_codex_review",
    }


def _user_hook_status(home: Path, expected_package_digest: str) -> dict[str, object]:
    _installed_package(home, expected_package_digest)
    _probe(home, expected_package_digest)
    candidate, definition_digest = _source_hooks(expected_package_digest)
    config_path = home / USER_HOOKS_RELATIVE_PATH
    receipt_path = home / USER_HOOK_ROLLBACK_RELATIVE_PATH
    data = _read_private_regular(config_path, "user Hook configuration")
    if data is None:
        return {
            "hook_config_installed": False,
            "hook_config_path": str(config_path),
            "hook_definition_sha256": definition_digest,
            "hook_definitions_match": False,
            "package_digest": expected_package_digest,
            "rollback_state": "not_configured",
            "trust_state": "not_configured",
        }
    installed = _parse_hook_config(data, "user Hook configuration")
    candidate_definition = _managed_definition(candidate)
    installed_definition = _managed_definition(installed)
    matches = installed_definition == candidate_definition
    receipt = _read_rollback_receipt(receipt_path)
    if receipt is None:
        rollback_state = "missing"
    else:
        _, parsed_receipt = receipt
        rollback_state = _rollback_state(
            parsed_receipt,
            expected_package_digest,
            candidate_definition,
        )
        if rollback_state == "available" and not matches:
            rollback_state = "blocked_by_definition_mismatch"
    return {
        "hook_config_installed": True,
        "hook_config_path": str(config_path),
        "hook_definition_sha256": definition_digest,
        "hook_definitions_match": matches,
        "managed_hook_commands": len(_managed_hook_commands(installed)),
        "package_digest": expected_package_digest,
        "rollback_receipt_path": str(receipt_path),
        "rollback_state": rollback_state,
        "trust_state": "requires_codex_review" if matches else "definition_mismatch",
    }


def _rollback_user_hooks(home: Path, expected_package_digest: str) -> dict[str, object]:
    _installed_package(home, expected_package_digest)
    _probe(home, expected_package_digest)
    candidate, definition_digest = _source_hooks(expected_package_digest)
    candidate_definition = _managed_definition(candidate)
    config_path = home / USER_HOOKS_RELATIVE_PATH
    receipt_path = home / USER_HOOK_ROLLBACK_RELATIVE_PATH
    _safe_parent_dir(config_path.parent)
    lock_path = config_path.parent / ".work-governance-hooks.install.lock"
    lock_descriptor = _open_private_lock(lock_path, "user Hook installation lock")
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        previous = _read_private_regular(config_path, "user Hook configuration")
        if previous is None:
            raise RuntimeError("user Hook configuration is not installed")
        receipt = _read_rollback_receipt(receipt_path)
        if receipt is None:
            raise RuntimeError("user Hook rollback receipt is missing")
        receipt_bytes, parsed_receipt = receipt
        receipt_state = _rollback_state(
            parsed_receipt,
            expected_package_digest,
            candidate_definition,
        )
        if receipt_state != "available":
            raise RuntimeError(f"user Hook rollback receipt is {receipt_state}")
        current = _parse_hook_config(previous, "user Hook configuration")
        if _managed_definition(current) != candidate_definition:
            raise RuntimeError(
                "user Hook configuration changed since rollback receipt; refusing rollback"
            )
        previous_definition = parsed_receipt["previous_definition"]
        assert isinstance(previous_definition, list)
        previous_config_absent = parsed_receipt["previous_config_absent"]
        assert isinstance(previous_config_absent, bool)
        previous_package_digests = parsed_receipt["previous_package_digests"]
        assert isinstance(previous_package_digests, list)
        for digest in previous_package_digests:
            assert isinstance(digest, str)
            _probe(home, digest)
        restored = _merge_user_hooks(current, _definition_as_config(previous_definition))
        expected = _canonical(restored) + b"\n"
        restore_to_absent = previous_config_absent and restored == _empty_user_hook_config()
        try:
            if restore_to_absent:
                _remove_private_file(config_path, previous, "user Hook configuration")
            else:
                _write_private_file(
                    config_path,
                    expected,
                    "user Hook configuration",
                    ".work-governance-hooks",
                )
                readback = _read_private_regular(config_path, "user Hook configuration")
                assert readback is not None
                if _parse_hook_config(readback, "user Hook configuration") != restored:
                    raise RuntimeError(
                        "user Hook configuration readback differs from restored definition"
                    )
        except Exception as rollback_error:
            try:
                _restore_private_file(
                    config_path,
                    previous,
                    None if restore_to_absent else expected,
                    "user Hook configuration",
                    ".work-governance-hooks",
                )
            except Exception as restore_error:
                raise RuntimeError(
                    "user Hook rollback failed and configuration restore failed: "
                    f"rollback={rollback_error}; restore={restore_error}"
                ) from restore_error
            raise RuntimeError(
                f"user Hook rollback failed; candidate configuration restored: {rollback_error}"
            ) from rollback_error
        receipt_after = _read_private_regular(receipt_path, "user Hook rollback receipt")
        if receipt_after == receipt_bytes:
            receipt_path.unlink()
            receipt_state = "consumed"
        else:
            receipt_state = "changed_after_rollback"
    finally:
        os.close(lock_descriptor)
    return {
        "hook_config_installed": not restore_to_absent,
        "hook_config_path": str(config_path),
        "hook_definition_sha256": definition_digest,
        "package_digest": expected_package_digest,
        "restored_package_digests": previous_package_digests,
        "rollback_receipt_path": str(receipt_path),
        "rollback_state": receipt_state,
        "trust_state": "requires_codex_review",
    }


def _install_launcher(home: Path, probe_digests: list[str], rollback_digest: str | None) -> None:
    bin_dir = home / ".local" / "bin"
    _safe_parent_dir(home / ".local")
    _safe_parent_dir(bin_dir)
    target = bin_dir / "work-governance-hook"
    lock_path = bin_dir / ".work-governance-hook.install.lock"
    lock_descriptor = _open_private_lock(lock_path, "launcher installation lock")
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        previous: bytes | None = None
        if target.exists() or target.is_symlink():
            previous = _read_private_regular(target, "existing launcher")
            if previous is None:
                raise RuntimeError("existing launcher disappeared during inspection")
        if previous is not None and rollback_digest is None:
            raise RuntimeError(
                "launcher upgrade requires --rollback-digest for the current package"
            )
        if previous is None and rollback_digest is not None:
            raise RuntimeError("fresh launcher installation cannot name a rollback digest")
        if rollback_digest is not None:
            if rollback_digest not in probe_digests:
                raise RuntimeError("rollback digest must also be included in --probe-digest")
            _probe(home, rollback_digest)
        _replace_launcher(target, LAUNCHER_SOURCE.read_bytes())
        try:
            for digest in probe_digests:
                _probe(home, digest)
        except Exception as candidate_error:
            if previous is None:
                target.unlink(missing_ok=True)
                raise RuntimeError(
                    f"candidate launcher probe failed; fresh launcher removed: {candidate_error}"
                ) from candidate_error
            try:
                _replace_launcher(target, previous)
            except Exception as restore_error:
                raise RuntimeError(
                    "candidate launcher probe failed and rollback launcher restore failed: "
                    f"candidate={candidate_error}; rollback={restore_error}"
                ) from restore_error
            try:
                _probe(home, rollback_digest)
            except Exception as rollback_error:
                raise RuntimeError(
                    "candidate launcher probe failed and rollback launcher probe failed: "
                    f"candidate={candidate_error}; rollback={rollback_error}"
                ) from rollback_error
            raise RuntimeError(
                "candidate launcher probe failed; rollback launcher restored and verified: "
                f"{candidate_error}"
            ) from candidate_error
    finally:
        os.close(lock_descriptor)


def _replace_launcher(target: Path, content: bytes) -> None:
    _atomic_replace(target, content, 0o700, ".work-governance-hook")


def _probe(home: Path, digest: str) -> dict[str, Any]:
    launcher = home / ".local" / "bin" / "work-governance-hook"
    process = subprocess.run(
        [
            str(launcher),
            "probe",
            "--contract",
            CONTRACT,
            "--package-digest",
            digest,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        timeout=10,
    )
    result = json.loads(process.stdout)
    if result != {"contract": CONTRACT, "package_digest": digest, "ok": True}:
        raise RuntimeError("launcher probe returned an unexpected result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path.home())
    subparsers = parser.add_subparsers(dest="command", required=True)
    package = subparsers.add_parser("package")
    package.add_argument("--expected-digest")
    launcher = subparsers.add_parser("launcher")
    launcher.add_argument("--probe-digest", action="append", required=True)
    launcher.add_argument("--rollback-digest")
    status = subparsers.add_parser("status")
    status.add_argument("--package-digest", required=True)
    user_hook = subparsers.add_parser("user-hook")
    user_hook_subparsers = user_hook.add_subparsers(dest="user_hook_command", required=True)
    user_hook_install = user_hook_subparsers.add_parser("install")
    user_hook_install.add_argument("--expected-package-digest", required=True)
    user_hook_status = user_hook_subparsers.add_parser("status")
    user_hook_status.add_argument("--expected-package-digest", required=True)
    user_hook_rollback = user_hook_subparsers.add_parser("rollback")
    user_hook_rollback.add_argument("--expected-package-digest", required=True)
    args = parser.parse_args()
    home = args.home.resolve()
    if args.command == "package":
        digest = _install_package(home, args.expected_digest)
        print(json.dumps({"package_digest": digest, "package_installed": True}, sort_keys=True))
    elif args.command == "launcher":
        _install_launcher(home, args.probe_digest, args.rollback_digest)
        print(
            json.dumps(
                {
                    "launcher_installed": True,
                    "probed": args.probe_digest,
                    "rollback_digest": args.rollback_digest,
                },
                sort_keys=True,
            )
        )
    elif args.command == "user-hook":
        if args.user_hook_command == "install":
            result = _install_user_hooks(home, args.expected_package_digest)
        elif args.user_hook_command == "rollback":
            result = _rollback_user_hooks(home, args.expected_package_digest)
        else:
            result = _user_hook_status(home, args.expected_package_digest)
        print(json.dumps(result, sort_keys=True))
    else:
        result = _probe(home, args.package_digest)
        print(json.dumps({"launcher": str(home / ".local/bin/work-governance-hook"), **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
