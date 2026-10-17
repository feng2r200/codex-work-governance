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
MAX_CONTINUATION_PACKET_BYTES = 8_192
MAX_CONTINUATION_PACKET_ITEMS = 64
MAX_CONTINUATION_PACKET_TOKEN_BUDGET = 4_096
MAX_CONTINUATION_EVIDENCE_REFERENCES = 32
STATE_TTL_SECONDS = 7 * 24 * 60 * 60
CONTINUATION_EVALUATOR_VERSION = "wg-continuation-v1"
CONTINUATION_PRESSURE_SIGNALS = (
    "context_pressure",
    "repeated_compaction",
    "unchanged_context_replay",
    "coordination_drag",
)


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


def _required_bool(value: dict[str, object], field: str, label: str) -> bool:
    """Return one required boolean field or fail closed on malformed input."""
    candidate = value.get(field)
    if not isinstance(candidate, bool):
        raise RuntimeError(f"{label}.{field} must be boolean")
    return candidate


def _required_enum(value: dict[str, object], field: str, allowed: set[str], label: str) -> str:
    """Return one required closed-vocabulary string field."""
    candidate = value.get(field)
    if not isinstance(candidate, str) or candidate not in allowed:
        expected = ", ".join(sorted(allowed))
        raise RuntimeError(f"{label}.{field} must be one of: {expected}")
    return candidate


def _required_identifier(value: dict[str, object], field: str, label: str) -> str:
    """Return one bounded, line-safe identity string or fail closed."""
    candidate = value.get(field)
    if (
        not isinstance(candidate, str)
        or not candidate.strip()
        or candidate != candidate.strip()
        or len(candidate.encode("utf-8")) > 2_048
        or any(
            ord(character) < 32
            or ord(character) == 127
            or (character.isspace() and character != " ")
            for character in candidate
        )
    ):
        raise RuntimeError(f"{label}.{field} must be a non-empty, bounded, line-safe string")
    return candidate


def _required_digest(value: dict[str, object], field: str, label: str) -> str:
    """Return one canonical lowercase hexadecimal digest or fail closed."""
    candidate = _required_identifier(value, field, label)
    if len(candidate) != 64 or any(character not in "0123456789abcdef" for character in candidate):
        raise RuntimeError(f"{label}.{field} must be a 64-character lowercase hex digest")
    return candidate


def _required_positive_int(value: dict[str, object], field: str, label: str) -> int:
    """Return one positive integer while rejecting booleans and malformed values."""
    candidate = value.get(field)
    if isinstance(candidate, bool) or not isinstance(candidate, int) or candidate <= 0:
        raise RuntimeError(f"{label}.{field} must be a positive integer")
    return candidate


def _required_bounded_positive_int(
    value: dict[str, object], field: str, maximum: int, label: str
) -> int:
    """Return one positive integer no greater than the protocol bound."""
    candidate = _required_positive_int(value, field, label)
    if candidate > maximum:
        raise RuntimeError(f"{label}.{field} must be at most {maximum}")
    return candidate


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_evidence_references(event: dict[str, object]) -> list[dict[str, str]]:
    candidate = event.get("evidence_references")
    if not isinstance(candidate, list) or not candidate:
        raise RuntimeError("event.evidence_references must be a non-empty array")
    if len(candidate) > MAX_CONTINUATION_EVIDENCE_REFERENCES:
        raise RuntimeError(
            "event.evidence_references must contain at most "
            f"{MAX_CONTINUATION_EVIDENCE_REFERENCES} entries"
        )
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, entry in enumerate(candidate):
        label = f"event.evidence_references[{index}]"
        if not isinstance(entry, dict):
            raise RuntimeError(f"{label} must be an object")
        normalized_entry = {
            "kind": _required_identifier(entry, "kind", label),
            "reference": _required_identifier(entry, "reference", label),
            "digest": _required_digest(entry, "digest", label),
        }
        identity = (
            normalized_entry["kind"],
            normalized_entry["reference"],
            normalized_entry["digest"],
        )
        if identity in seen:
            raise RuntimeError("event.evidence_references must not contain duplicates")
        seen.add(identity)
        normalized.append(normalized_entry)
    return normalized


def evaluate_continuation_policy(event: dict[str, object]) -> dict[str, object]:
    """Evaluate a bounded continuation recommendation without causing product effects."""
    if event.get("schema_version") != 1:
        raise RuntimeError("continuation policy schema_version must be 1")
    actor_role = _required_enum(
        event, "actor_role", {"listener", "work", "subagent", "side_chat"}, "event"
    )
    source_role = _required_enum(
        event,
        "source_role",
        {"listener", "work", "work_candidate", "subagent", "side_chat"},
        "event",
    )
    target_role = _required_enum(
        event,
        "target_role",
        {"listener", "work", "work_candidate", "subagent", "side_chat"},
        "event",
    )
    expected_benefit = _required_enum(event, "expected_benefit", {"low", "medium", "high"}, "event")
    continuation_risk = _required_enum(
        event, "continuation_risk", {"low", "medium", "high"}, "event"
    )
    continuation_enabled = _required_bool(event, "continuation_enabled", "event")
    durable_provider_available = _required_bool(event, "durable_provider_available", "event")
    decision_identity = {
        "project_opt_in_receipt_kind": _required_enum(
            event,
            "project_opt_in_receipt_kind",
            {"workvcs_project_policy"},
            "event",
        ),
        "project_opt_in_receipt_digest": _required_digest(
            event, "project_opt_in_receipt_digest", "event"
        ),
        "project_opt_in_revision": _required_positive_int(
            event, "project_opt_in_revision", "event"
        ),
        "project_opt_in_verified_at_us": _required_positive_int(
            event, "project_opt_in_verified_at_us", "event"
        ),
        "project_id": _required_identifier(event, "project_id", "event"),
        "scope_id": _required_identifier(event, "scope_id", "event"),
        "workspace_id": _required_identifier(event, "workspace_id", "event"),
        "branch_id": _required_identifier(event, "branch_id", "event"),
        "task_entity_id": _required_identifier(event, "task_entity_id", "event"),
        "listener_session_id": _required_identifier(event, "listener_session_id", "event"),
        "source_session_id": _required_identifier(event, "source_session_id", "event"),
        "source_claim_id": _required_identifier(event, "source_claim_id", "event"),
        "handoff_digest": _required_digest(event, "handoff_digest", "event"),
        "scope_currentness_digest": _required_digest(event, "scope_currentness_digest", "event"),
        "continuation_packet_digest": _required_digest(
            event, "continuation_packet_digest", "event"
        ),
        "continuation_packet_bytes": _required_bounded_positive_int(
            event,
            "continuation_packet_bytes",
            MAX_CONTINUATION_PACKET_BYTES,
            "event",
        ),
        "continuation_packet_items": _required_bounded_positive_int(
            event,
            "continuation_packet_items",
            MAX_CONTINUATION_PACKET_ITEMS,
            "event",
        ),
        "continuation_packet_token_budget": _required_bounded_positive_int(
            event,
            "continuation_packet_token_budget",
            MAX_CONTINUATION_PACKET_TOKEN_BUDGET,
            "event",
        ),
        "initial_message_digest": _required_digest(event, "initial_message_digest", "event"),
        "adapter_kind": _required_identifier(event, "adapter_kind", "event"),
        "adapter_version": _required_identifier(event, "adapter_version", "event"),
    }
    listener_revision = _required_positive_int(event, "listener_revision", "event")
    owner_epoch = _required_positive_int(event, "owner_epoch", "event")
    evaluated_at_us = _required_positive_int(event, "evaluated_at_us", "event")
    signals = event.get("signals")
    if not isinstance(signals, dict):
        raise RuntimeError("event.signals must be an object")
    pressure_count = sum(
        _required_bool(signals, signal, "event.signals") for signal in CONTINUATION_PRESSURE_SIGNALS
    )
    evidence_references = _required_evidence_references(event)

    reasons: list[str] = []
    if not continuation_enabled:
        reasons.append("project_not_opted_in")
    if not durable_provider_available:
        reasons.append("durable_provider_unavailable")
    if actor_role != "listener":
        reasons.append("actor_must_be_bound_listener")
    source_committed = _required_bool(event, "source_committed", "event")
    source_is_current_carrier = _required_bool(event, "source_is_current_carrier", "event")
    source_has_exclusive_claim = _required_bool(event, "source_has_exclusive_claim", "event")
    if source_role not in {"work", "work_candidate"}:
        reasons.append("source_role_not_rotatable")
    elif source_role == "work_candidate" and not source_committed:
        reasons.append("work_candidate_not_committed")
    if not source_is_current_carrier:
        reasons.append("source_not_current_carrier")
    if not source_has_exclusive_claim:
        reasons.append("source_missing_exclusive_claim")
    if target_role != "work_candidate":
        reasons.append("target_must_be_work_candidate")
    gate_expectations = (
        ("listener_matches", True, "listener_binding_mismatch"),
        ("listener_revision_matches", True, "listener_revision_mismatch"),
        ("scope_currentness_matches", True, "scope_currentness_mismatch"),
        ("project_binding_matches", True, "project_binding_mismatch"),
        ("active_rotation", False, "rotation_already_active_or_unknown"),
        ("prior_rotation_terminal", True, "prior_rotation_not_terminal"),
        ("cooldown_satisfied", True, "cooldown_not_satisfied"),
        ("safe_semantic_point", True, "unsafe_semantic_point"),
        ("handoff_fresh", True, "handoff_not_fresh"),
        ("progress_since_last_rotation", True, "no_fresh_progress"),
    )
    for field, expected, reason in gate_expectations:
        if _required_bool(event, field, "event") is not expected:
            reasons.append(reason)
    if expected_benefit != "high":
        reasons.append("expected_benefit_not_high")
    if continuation_risk == "high":
        reasons.append("continuation_risk_high")
    if pressure_count < 2:
        reasons.append("insufficient_pressure_diversity")

    action = "prepare_rotation" if not reasons else "stay"
    gate_summary: dict[str, object] = {
        "continuation_enabled": continuation_enabled,
        "durable_provider_available": durable_provider_available,
        "actor_role": actor_role,
        "source_role": source_role,
        "target_role": target_role,
        "source_committed": source_committed,
        "source_is_current_carrier": source_is_current_carrier,
        "source_has_exclusive_claim": source_has_exclusive_claim,
        **{field: _required_bool(event, field, "event") for field, _, _ in gate_expectations},
        "expected_benefit": expected_benefit,
        "continuation_risk": continuation_risk,
        "signals": {
            signal: _required_bool(signals, signal, "event.signals")
            for signal in CONTINUATION_PRESSURE_SIGNALS
        },
    }
    evaluator_result = {
        "schema_version": 1,
        "evaluator_version": CONTINUATION_EVALUATOR_VERSION,
        "action": action,
        "reasons": reasons if reasons else ["all_gates_satisfied"],
        "pressure_signal_count": pressure_count,
        "decision_identity": decision_identity,
        "listener_revision": listener_revision,
        "owner_epoch": owner_epoch,
        "evaluated_at_us": evaluated_at_us,
        "gate_summary": gate_summary,
        "evidence_references": evidence_references,
    }
    evaluator_result_digest = _canonical_digest(evaluator_result)
    evaluator_receipt: dict[str, object] = {
        "schema_version": 1,
        "evaluator_version": CONTINUATION_EVALUATOR_VERSION,
        "result_digest": evaluator_result_digest,
        "result": evaluator_result,
        "action": action,
        "gate_summary": gate_summary,
        "evidence_references": evidence_references,
    }
    evaluator_receipt_digest = _canonical_digest(evaluator_receipt)
    policy_decision: dict[str, object] = {
        "schema_version": 1,
        "action": action,
        "continuation_enabled": continuation_enabled,
        "durable_provider_available": durable_provider_available,
        **decision_identity,
        "listener_revision": listener_revision,
        "owner_epoch": owner_epoch,
        "evaluated_at_us": evaluated_at_us,
        "evaluator_version": CONTINUATION_EVALUATOR_VERSION,
        "evaluator_result_digest": evaluator_result_digest,
        "evaluator_receipt": evaluator_receipt,
        "evaluator_receipt_digest": evaluator_receipt_digest,
    }
    return {
        "decision_version": 1,
        "action": action,
        "reasons": reasons if reasons else ["all_gates_satisfied"],
        "pressure_signal_count": pressure_count,
        "causes_product_effects": False,
        "evaluator_receipt": evaluator_receipt,
        "evaluator_receipt_digest": evaluator_receipt_digest,
        "policy_decision": policy_decision,
        "target_contract": {
            "conversation_kind": "work",
            "creation_method": "create_thread",
            "forked": False,
            "exact_project_required": True,
            "project_binding_provenance_required": True,
            "creation_operation_correlation_required": True,
            "creation_request_digest_required": True,
            "bounded_continuation_packet_required": True,
            "continuation_packet_max_bytes": MAX_CONTINUATION_PACKET_BYTES,
            "continuation_packet_max_items": MAX_CONTINUATION_PACKET_ITEMS,
            "continuation_packet_token_budget_max": MAX_CONTINUATION_PACKET_TOKEN_BUDGET,
            "initial_message_digest_required": True,
            "source_transcript_included": False,
            "durable_dispatch_before_product_call_required": True,
            "dispatch_currentness_revalidation_required": True,
            "product_receipt_required": True,
            "product_receipt_actor_binding_required": True,
            "current_listener_revision_required": True,
            "stable_thread_id_required": True,
            "resolved_thread_id_required": True,
            "user_visible": True,
            "auditable": True,
            "interactive": True,
            "target_authored_acceptance_required": True,
            "created_target_global_role_reservation_required": True,
            "created_target_source_exception": "exact_committed_candidate_claim_scope",
            "lost_listener_drift_recovery_mode": "abort_only",
            "abort_only_recovery_may_create_target": False,
            "abort_only_recovery_may_commit": False,
            "abort_only_recovery_requires_original_operation_reconciliation": True,
            "abort_only_recovery_requires_state_specific_terminal_evidence": True,
            "prohibited_targets": ["listener", "subagent", "side_chat", "hidden_task"],
        },
    }


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
    if args.handler == "evaluate-continuation":
        result = evaluate_continuation_policy(_read_event())
        sys.stdout.buffer.write(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        )
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
