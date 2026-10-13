"""Bounded Work Governance hook runtime.

The stable launcher verifies this file before executing it.  This runtime keeps
only small, owner-private observations and emits context solely from an
explicitly staged packet whose digest has not already been emitted for the
current session.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any

CONTRACT = "wg-hook-v1"
MAX_INPUT_BYTES = 262_144
MAX_PACKET_BYTES = 8_192
MAX_CONTEXT_CHARS = 6_000
STATE_TTL_SECONDS = 7 * 24 * 60 * 60


def _private_dir(path: Path) -> Path:
    """Create or validate an owner-only, non-symlink directory."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"state path is not a real directory: {path}")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError(f"state directory is not owner-private: {path}")
    return path


def _safe_parent_dir(path: Path) -> Path:
    """Create or validate an owner-controlled, non-symlink parent directory."""
    path.mkdir(mode=0o755, parents=True, exist_ok=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"state parent is not a real directory: {path}")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise RuntimeError(f"state parent is not safely owner-controlled: {path}")
    return path


def _state_root() -> Path:
    """Return the private hook state root without consulting plugin paths."""
    configured = os.environ.get("WORK_GOVERNANCE_HOOK_STATE")
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            raise RuntimeError("WORK_GOVERNANCE_HOOK_STATE must be absolute")
    else:
        local = _safe_parent_dir(Path.home() / ".local")
        state = _safe_parent_dir(local / "state")
        application = _private_dir(state / "work-governance-hook")
        root = application / "v1"
    return _private_dir(root)


def _read_event() -> dict[str, Any]:
    """Read one bounded JSON event without retaining opaque payload fields."""
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise RuntimeError("hook input exceeds the bounded input limit")
    if not data.strip():
        return {}
    decoded = json.loads(data)
    if not isinstance(decoded, dict):
        raise RuntimeError("hook input must be a JSON object")
    return decoded


def _text_field(event: dict[str, Any], *names: str, limit: int = 512) -> str | None:
    for name in names:
        value = event.get(name)
        if isinstance(value, str) and value:
            return value[:limit]
    return None


def _session_key(event: dict[str, Any]) -> str:
    value = _text_field(event, "session_id", "sessionId", "thread_id", "threadId")
    if value is None:
        value = "unknown"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    """Publish a small owner-only JSON file atomically."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _read_private_json(path: Path, limit: int) -> object:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError(f"state file is not an owner file: {path}")
        if stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > limit:
            raise RuntimeError(f"state file permissions or size are invalid: {path}")
        data = os.read(descriptor, limit + 1)
        if len(data) > limit:
            raise RuntimeError(f"state file exceeds its bound: {path}")
        return json.loads(data)
    finally:
        os.close(descriptor)


def _append_observation(root: Path, event: dict[str, Any], handler: str, elapsed_us: int) -> None:
    """Append only bounded metadata; never copy transcript or tool payloads."""
    record = {
        "schema_version": 1,
        "observed_at_us": time.time_ns() // 1_000,
        "handler": handler,
        "session_key": _session_key(event),
        "tool_name": _text_field(event, "tool_name", "toolName", "tool", limit=128),
        "event_name": _text_field(event, "hook_event_name", "hookEventName", "event", limit=64),
        "elapsed_us": elapsed_us,
    }
    path = root / "observations.jsonl"
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None and existing.st_size > 1_048_576:
        if not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.getuid():
            raise RuntimeError("observation file is not an owner file")
        replacement = root / f".observations.{os.getpid()}.{time.time_ns()}.tmp"
        descriptor = os.open(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        os.replace(replacement, path)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise RuntimeError("observation file is not owner-private")
        os.write(
            descriptor,
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
        )
    finally:
        os.close(descriptor)


def _prune_expired(root: Path) -> None:
    cutoff = time.time() - STATE_TTL_SECONDS
    for directory_name in ("emitted", "packets"):
        directory = _private_dir(root / directory_name)
        for candidate in directory.iterdir():
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError(f"state directory contains a symbolic link: {candidate}")
            if stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff:
                candidate.unlink(missing_ok=True)


def _load_packet(root: Path, session_key: str) -> tuple[str, str] | None:
    packet_path = root / "packets" / f"{session_key}.json"
    try:
        descriptor = os.open(packet_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("context packet is not an owner file")
        if stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_PACKET_BYTES:
            raise RuntimeError("context packet permissions or size are invalid")
        data = os.read(descriptor, MAX_PACKET_BYTES + 1)
    finally:
        os.close(descriptor)
    packet = json.loads(data)
    if not isinstance(packet, dict) or packet.get("schema_version") != 1:
        raise RuntimeError("context packet has an unsupported schema")
    context = packet.get("context")
    if not isinstance(context, str) or not context.strip() or len(context) > MAX_CONTEXT_CHARS:
        raise RuntimeError("context packet text is empty or exceeds the bound")
    digest = hashlib.sha256(context.encode("utf-8")).hexdigest()
    return digest, context


def _context_output(root: Path, event: dict[str, Any], handler: str) -> bytes:
    session_key = _session_key(event)
    packet = _load_packet(root, session_key)
    if packet is None:
        return b""
    digest, context = packet
    emitted = root / "emitted" / f"{session_key}.{handler}.json"
    lock_path = root / "emitted" / f".{session_key}.{handler}.lock"
    lock_descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        lock_info = os.fstat(lock_descriptor)
        if lock_info.st_uid != os.getuid() or stat.S_IMODE(lock_info.st_mode) & 0o077:
            raise RuntimeError("context emission lock is not owner-private")
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        try:
            prior = _read_private_json(emitted, MAX_PACKET_BYTES)
        except FileNotFoundError:
            prior = None
        if isinstance(prior, dict) and prior.get("packet_sha256") == digest:
            return b""
        _atomic_json(
            emitted,
            {"packet_sha256": digest, "emitted_at_us": time.time_ns() // 1_000},
        )
    finally:
        os.close(lock_descriptor)
    event_name = "SessionStart" if handler == "session-start" else "PreCompact"
    value = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _stage_context(root: Path, session_id: str, context: str) -> None:
    if not context.strip() or len(context) > MAX_CONTEXT_CHARS:
        raise RuntimeError("context must be non-empty and within the configured bound")
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    _atomic_json(
        root / "packets" / f"{session_key}.json",
        {"schema_version": 1, "context": context, "staged_at_us": time.time_ns() // 1_000},
    )


def main() -> int:
    """Dispatch one verified runtime operation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--package-digest", required=True)
    parser.add_argument("--handler", required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--context")
    args = parser.parse_args()
    if args.contract != CONTRACT:
        raise RuntimeError(f"unsupported contract: {args.contract}")
    if args.handler == "probe":
        print(json.dumps({"contract": CONTRACT, "package_digest": args.package_digest, "ok": True}))
        return 0
    root = _state_root()
    _private_dir(root / "packets")
    _private_dir(root / "emitted")
    _prune_expired(root)
    if args.handler == "stage-context":
        if args.session_id is None or args.context is None:
            raise RuntimeError("stage-context requires --session-id and --context")
        _stage_context(root, args.session_id, args.context)
        return 0
    if args.handler not in {"session-start", "pre-compact", "post-tool-use"}:
        raise RuntimeError(f"unknown handler: {args.handler}")
    started_ns = time.monotonic_ns()
    event = _read_event()
    output = b""
    if args.handler in {"session-start", "pre-compact"}:
        output = _context_output(root, event, args.handler)
    elapsed_us = (time.monotonic_ns() - started_ns) // 1_000
    _append_observation(root, event, args.handler, elapsed_us)
    if output:
        sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - hook failure must remain explicit to Codex.
        print(f"work-governance-hook: {error}", file=sys.stderr)
        raise SystemExit(70) from error
