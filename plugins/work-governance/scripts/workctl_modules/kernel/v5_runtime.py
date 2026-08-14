"""Schema-v5 runtime state and event helpers for the Work Governance kernel."""

from __future__ import annotations

# Controller infrastructure is bound by name for each runtime operation.
# ruff: noqa: F821
import copy
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from workctl_modules.kernel.bindings import call_with_bound_globals


def call(bindings: Mapping[str, Any], function: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a schema-v5 runtime helper with controller infrastructure bound."""
    return call_with_bound_globals(globals(), bindings, function, *args, **kwargs)


def v5_runtime_dir(root: Path, plan_id: str) -> Path:
    """Return the durable runtime bundle directory for one schema-v5 Plan."""
    path = governance_root(root) / "runtime" / "plans" / plan_id
    reject_symlink_components(root, path)
    return path


def v5_state_path(root: Path, plan_id: str) -> Path:
    return v5_runtime_dir(root, plan_id) / "state.json"


def v5_event_path(root: Path, plan_id: str) -> Path:
    return v5_runtime_dir(root, plan_id) / "events.jsonl"


def v5_state_defaults(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Build a valid empty runtime state for a newly created v5 contract."""
    if build_v5_state is None:
        raise WorkctlError("SCHEMA_V5_RUNTIME_MODULE_UNAVAILABLE")
    return build_v5_state(frontmatter, updated_at=str(frontmatter.get("updated_at", utc_now())))


def v5_redact_evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove credential-bearing fields before strict evidence canonicalization."""
    sensitive = ("api_key", "apikey", "authorization", "password", "secret", "token")

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if not any(part in key.lower() for part in sensitive)
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str) and "Bearer " in value:
            return value.split("Bearer ", 1)[0] + "Bearer [REDACTED]"
        return value

    return cast(dict[str, Any], clean(dict(payload)))


def load_v5_state(root: Path, frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Load and validate the independent v5 state snapshot."""
    plan_id = str(frontmatter.get("plan_id"))
    path = v5_state_path(root, plan_id)
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("SCHEMA_V5_STATE_MISSING")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkctlError("SCHEMA_V5_STATE_INVALID") from exc
    if not isinstance(payload, dict):
        raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    tasks = payload.get("tasks")
    priorities = payload.get("priorities")
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != "work-governance-plan-state"
        or payload.get("plan_id") != plan_id
        or type(payload.get("state_sequence")) is not int
        or payload["state_sequence"] < 0
        or type(payload.get("event_sequence")) is not int
        or payload["event_sequence"] < 0
        or not isinstance(tasks, dict)
        or not isinstance(priorities, dict)
        or any(type(value) is not int for value in priorities.values())
    ):
        raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    for task_id, task in tasks.items():
        if (
            not isinstance(task_id, str)
            or not isinstance(task, dict)
            or task.get("status") not in WORK_ITEM_STATES
        ):
            raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    event_path = v5_event_path(root, plan_id)
    if event_path.is_symlink() or not event_path.is_file():
        raise WorkctlError("SCHEMA_V5_EVENT_MISSING")
    event_lines = event_path.read_text(encoding="utf-8").splitlines()
    expected_events = payload["event_sequence"]
    if isinstance(payload.get("pending_event"), dict):
        expected_events -= 1
    if len(event_lines) != expected_events:
        raise WorkctlError("SCHEMA_V5_EVENT_SEQUENCE_MISMATCH")
    return cast(dict[str, Any], payload)


def v5_runtime_frontmatter(
    root: Path,
    frontmatter: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Overlay runtime task state for scheduling without mutating the contract."""
    runtime = copy.deepcopy(dict(frontmatter))
    if state is None:
        state = load_v5_state(root, frontmatter)
    state_tasks = state.get("tasks", {})
    for task in runtime.get("tasks", []) if isinstance(runtime.get("tasks"), list) else []:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        current = state_tasks.get(task["id"]) if isinstance(state_tasks, dict) else None
        if isinstance(current, dict):
            for key, value in current.items():
                if key != "status" or isinstance(value, str):
                    task[key] = copy.deepcopy(value)
    return runtime


def v5_terminal_runtime_view(
    root: Path,
    frontmatter: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the schema-v5 runtime authority view used for terminal closeout."""
    view = v5_runtime_frontmatter(root, frontmatter, state)
    view["route"] = {
        "route_status": "terminal",
        "slice_status": "complete",
        "next_phase": "none",
        "validation_standard": "schema-v5 runtime state is terminal-ready",
        "confirmation_gate": "none",
    }
    view["handoff"] = {"route_status": "terminal", "next_step": "none"}
    return view


def require_v5_expected_state_sequence(
    state: Mapping[str, Any],
    expected: int | None,
) -> None:
    """Fail unless a v5 runtime write is guarded by the current state sequence."""
    if expected is None:
        raise WorkctlError("EXPECTED_STATE_SEQUENCE_REQUIRED")
    if state["state_sequence"] != expected:
        raise WorkctlError(
            f"STATE_SEQUENCE_MISMATCH: expected {expected}, found {state['state_sequence']}"
        )


def v5_runtime_closeout_readiness(
    root: Path,
    frontmatter: Mapping[str, Any],
    report: AuthorityReport,
    validation_errors: list[str] | None = None,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute schema-v5 closeout readiness from runtime state, not contract task text."""
    if state is None:
        state = load_v5_state(root, frontmatter)
    runtime = v5_terminal_runtime_view(root, frontmatter, state)
    return closeout_readiness(cast(dict[str, Any], runtime), report, validation_errors)


def completion_claim_readiness(
    frontmatter: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    """Separate readiness-to-complete from already-complete route claims."""
    if frontmatter.get("schema_version") != 5 or frontmatter.get("status") == "complete":
        return copy.deepcopy(dict(readiness))
    raw_blockers = readiness.get("blockers", [])
    blockers = list(raw_blockers) if isinstance(raw_blockers, list) else []
    blockers.append("plan completion event not recorded")
    return {"ready": False, "blockers": blockers}


def release_v5_active_index(root: Path, plan_id: str) -> None:
    """Remove the active pointer after a v5 Plan becomes terminal history."""
    path = index_path(root)
    if not path.exists():
        return
    if path.is_symlink():
        raise WorkctlError("INDEX_PATH_SYMLINK")
    index = load_yaml_file(path)
    if index.get("active_plan_id") != plan_id:
        raise WorkctlError("INDEX_ACTIVE_PLAN_DRIFT")
    path.unlink()
    fsync_directory(path.parent)


def v5_read_events(root: Path, plan_id: str) -> list[dict[str, Any]]:
    """Read the append-only v5 event ledger with canonical JSON validation."""
    path = v5_event_path(root, plan_id)
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("SCHEMA_V5_EVENT_MISSING")
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkctlError("SCHEMA_V5_EVENT_INVALID") from exc
        if not isinstance(item, dict) or item.get("plan_id") != plan_id:
            raise WorkctlError("SCHEMA_V5_EVENT_INVALID")
        events.append(cast(dict[str, Any], item))
    return events


def canonical_event_payload_bytes(event: Mapping[str, Any]) -> bytes:
    """Return canonical bytes for one runtime event."""
    if canonical_event_bytes is None:
        raise WorkctlError("STORAGE_MODULE_UNAVAILABLE: canonical_event_bytes")
    return canonical_event_bytes(event)


def redacted_runtime_copy(value: Any) -> Any:
    """Return the storage-module redacted projection used in runtime payloads."""
    if redacted_copy is None:
        raise WorkctlError("STORAGE_MODULE_UNAVAILABLE: redacted_copy")
    return redacted_copy(value)


def v5_append_event(root: Path, plan_id: str, event: Mapping[str, Any]) -> None:
    """Append one canonical event and fsync the event ledger."""
    path = v5_event_path(root, plan_id)
    ensure_directory_durable(path.parent)
    encoded = canonical_event_payload_bytes(event)
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(path.parent)


def v5_persist_state_transition(
    root: Path,
    frontmatter: Mapping[str, Any],
    state: dict[str, Any],
    *,
    event: str,
    subject: str,
    payload: Mapping[str, Any],
) -> None:
    """Persist state before event, then complete the event with recoverable intent."""
    plan_id = str(frontmatter["plan_id"])
    next_event_sequence = int(state["event_sequence"]) + 1
    next_state_sequence = int(state["state_sequence"]) + 1
    event_payload = {
        "schema_version": 1,
        "kind": "work-governance-plan-event",
        "plan_id": plan_id,
        "event_sequence": next_event_sequence,
        "state_sequence": next_state_sequence,
        "event": event,
        "subject": subject,
        "payload": redacted_runtime_copy(dict(payload)),
        "recorded_at": utc_now(),
    }
    state["state_sequence"] = next_state_sequence
    state["event_sequence"] = next_event_sequence
    state["updated_at"] = utc_now()
    state["pending_event"] = event_payload
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")
    if os.environ.get("WORKCTL_TEST_V5_INTERRUPT_AFTER_STATE") == "1":
        raise WorkctlError("SCHEMA_V5_TEST_INTERRUPTED_AFTER_STATE")
    v5_append_event(root, plan_id, event_payload)
    state.pop("pending_event", None)
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")


def v5_recover_pending_event(root: Path, frontmatter: Mapping[str, Any]) -> None:
    """Finish a state-first transition left by a process interruption."""
    plan_id = str(frontmatter["plan_id"])
    state = load_v5_state(root, frontmatter)
    pending = state.get("pending_event")
    if not isinstance(pending, dict):
        return
    payload = pending.get("payload")
    contract_sha256 = payload.get("contract_sha256") if isinstance(payload, dict) else None
    if isinstance(contract_sha256, str):
        plan_path = active_plan_path(root)
        if plan_path.is_symlink() or not plan_path.is_file():
            raise WorkctlError("SCHEMA_V5_PENDING_CONTRACT_INVALID")
        if sha256_file(plan_path) != contract_sha256:
            state["event_sequence"] = int(state["event_sequence"]) - 1
            state.pop("pending_event", None)
            write_atomic(
                v5_state_path(root, plan_id),
                json.dumps(state, indent=2, sort_keys=True) + "\n",
            )
            return
    events = v5_read_events(root, plan_id)
    if not events or events[-1] != pending:
        v5_append_event(root, plan_id, pending)
    state.pop("pending_event", None)
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")


def v5_persist_contract_transition(
    root: Path,
    doc: PlanDocument,
    *,
    event: str,
    subject: str,
    payload: Mapping[str, Any],
) -> None:
    """Atomically replace a v5 contract with a recoverable ledger event intent."""
    plan_id = str(doc.frontmatter["plan_id"])
    state = load_v5_state(root, doc.frontmatter)
    target_bytes = dump_plan(doc).encode("utf-8")
    contract_sha256 = sha256_bytes(target_bytes)
    next_event_sequence = int(state["event_sequence"]) + 1
    event_payload = {
        "schema_version": 1,
        "kind": "work-governance-plan-event",
        "plan_id": plan_id,
        "event_sequence": next_event_sequence,
        "state_sequence": int(state["state_sequence"]),
        "event": event,
        "subject": subject,
        "payload": {
            **cast(dict[str, Any], redacted_runtime_copy(dict(payload))),
            "contract_revision": doc.frontmatter["contract_revision"],
            "contract_sha256": contract_sha256,
        },
        "recorded_at": utc_now(),
    }
    state["event_sequence"] = next_event_sequence
    state["updated_at"] = utc_now()
    state["pending_event"] = event_payload
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")
    if os.environ.get("WORKCTL_TEST_V5_CONTRACT_INTERRUPT") == "before-plan":
        raise WorkctlError("SCHEMA_V5_TEST_INTERRUPTED_BEFORE_CONTRACT")
    write_atomic_bytes(doc.path, target_bytes)
    if os.environ.get("WORKCTL_TEST_V5_CONTRACT_INTERRUPT") == "after-plan":
        raise WorkctlError("SCHEMA_V5_TEST_INTERRUPTED_AFTER_CONTRACT")
    v5_append_event(root, plan_id, event_payload)
    state.pop("pending_event", None)
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")
