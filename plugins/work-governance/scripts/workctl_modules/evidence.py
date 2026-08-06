"""Bounded evidence parsing, canonical encoding, and direct capture storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from . import yaml_compat as yaml
from .storage import canonical_json_bytes

EVIDENCE_SUBJECT_RE = re.compile(
    r"(?:[a-z][a-z0-9-]*:[A-Za-z0-9._-]+|closeout|delivery|"
    r"activation|plan-validation|contract-upgrade)"
)
EVIDENCE_CAPTURE_MAX_BYTES = 1024 * 1024
EVIDENCE_CAPTURE_KIND_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
EVIDENCE_CAPTURE_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
EVIDENCE_CAPTURE_ID_RE = re.compile(r"^E-\d{8}T\d{6}Z-[0-9a-f]{12}$")
EVIDENCE_CAPTURE_TASK_RE = re.compile(r"^T-\d{3}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_evidence_bytes(content: bytes, max_bytes: int) -> dict[str, object]:
    """Parse one bounded JSON or YAML evidence mapping."""
    if len(content) > max_bytes:
        raise ValueError("EVIDENCE_MANIFEST_TOO_LARGE")
    try:
        payload: object = json.loads(content)
    except json.JSONDecodeError:
        payload = yaml.safe_load(content)
    if not isinstance(payload, dict):
        raise ValueError("EVIDENCE_MANIFEST_INVALID")
    return payload


def canonical_evidence_bytes(payload: Mapping[str, object]) -> bytes:
    """Return deterministic content-addressed evidence bytes."""
    return canonical_json_bytes(payload)


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA256 digest for *content*."""
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest for a regular file."""
    if not path.is_file():
        raise ValueError(f"MISSING_FILE: {path}")
    return sha256_bytes(path.read_bytes())


def fsync_directory(path: Path) -> None:
    """Synchronize one directory entry set to durable storage."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_directory_durable(path: Path) -> None:
    """Create a directory chain and synchronize each new parent entry."""
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    path.mkdir(parents=True, exist_ok=True)
    for directory in reversed(missing):
        fsync_directory(directory.parent)
        fsync_directory(directory)


def write_atomic_bytes(path: Path, content: bytes) -> None:
    """Atomically and durably replace a file with exact bytes."""
    ensure_directory_durable(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        fsync_directory(path.parent)
    finally:
        with suppress(FileNotFoundError):
            tmp_path.unlink()


def relative_project_path(root: Path, path: Path) -> str:
    """Return a stable project-relative POSIX path."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"PATH_OUTSIDE_PROJECT: {path}") from exc


def reject_symlink_components(root: Path, path: Path) -> None:
    """Reject an existing symlink in a project-local control path chain."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"PATH_OUTSIDE_PROJECT: {path}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"LAYOUT_PATH_SYMLINK: {current.relative_to(root).as_posix()}")


def evidence_capture_root(root: Path, *, governance_dir_name: str = ".work-governance") -> Path:
    """Return the project-local direct evidence store root."""
    path = root / governance_dir_name / "evidence"
    reject_symlink_components(root, path)
    return path


def evidence_capture_blob_path(
    root: Path,
    digest: str,
    *,
    governance_dir_name: str = ".work-governance",
) -> Path:
    """Return the content-addressed blob path for direct evidence capture."""
    if SHA256_RE.fullmatch(digest) is None:
        raise ValueError("EVIDENCE_CAPTURE_BLOB_DIGEST_INVALID")
    return evidence_capture_root(root, governance_dir_name=governance_dir_name) / "blobs" / digest


def evidence_capture_record_path(
    root: Path,
    digest: str,
    *,
    governance_dir_name: str = ".work-governance",
) -> Path:
    """Return the content-addressed metadata record path for direct evidence capture."""
    if SHA256_RE.fullmatch(digest) is None:
        raise ValueError("EVIDENCE_CAPTURE_RECORD_DIGEST_INVALID")
    return (
        evidence_capture_root(root, governance_dir_name=governance_dir_name)
        / "records"
        / f"{digest}.json"
    )


def evidence_capture_ledger_path(
    root: Path,
    *,
    governance_dir_name: str = ".work-governance",
) -> Path:
    """Return the append-only direct evidence ledger path."""
    return evidence_capture_root(root, governance_dir_name=governance_dir_name) / "ledger.ndjson"


def normalize_capture_task(task_value: str | None) -> str | None:
    """Normalize an optional task reference to a task ID."""
    if task_value is None:
        return None
    normalized = task_value.removeprefix("task:")
    if EVIDENCE_CAPTURE_TASK_RE.fullmatch(normalized) is None:
        raise ValueError("EVIDENCE_CAPTURE_TASK_INVALID")
    return normalized


def redact_capture_text(value: str) -> str:
    """Apply conservative text redaction before evidence bytes are persisted."""
    redacted = value
    redacted = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [REDACTED]",
        redacted,
    )
    redacted = re.sub(r"\bsk-[A-Za-z0-9._-]+", "sk-[REDACTED]", redacted)
    redacted = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "AKIA[REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)\b(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )
    return redacted


def redact_capture_bytes(content: bytes) -> tuple[bytes, bool]:
    """Return persistable evidence bytes and whether the source was textual."""
    if len(content) > EVIDENCE_CAPTURE_MAX_BYTES:
        raise ValueError("EVIDENCE_CAPTURE_TOO_LARGE")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        placeholder = {
            "schema_version": 1,
            "kind": "work-governance-binary-evidence-placeholder",
            "source_sha256": sha256_bytes(content),
            "source_size": len(content),
            "redaction_note": "binary source was not persisted verbatim",
        }
        return (
            json.dumps(placeholder, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
            False,
        )
    return redact_capture_text(text).encode("utf-8"), True


def read_capture_source(root: Path, args: argparse.Namespace) -> tuple[bytes, str, str | None]:
    """Read direct evidence bytes from stdin or a project-local explicit file."""
    raw_from_file = getattr(args, "from_file", None)
    if isinstance(raw_from_file, str):
        input_path = Path(raw_from_file)
        candidate = input_path if input_path.is_absolute() else root / input_path
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"PATH_OUTSIDE_PROJECT: {raw_from_file}") from exc
        reject_symlink_components(root, candidate)
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("EVIDENCE_CAPTURE_SOURCE_MISSING")
        return candidate.read_bytes(), "file", relative_project_path(root, candidate)
    return sys.stdin.buffer.read(), "stdin", None


def capture_record_id(created_at: str) -> str:
    """Create a collision-resistant evidence ID from time and a random suffix."""
    compact_time = (
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        .astimezone(UTC)
        .strftime("%Y%m%dT%H%M%SZ")
    )
    return f"E-{compact_time}-{secrets.token_hex(6)}"


def load_capture_records(
    root: Path,
    *,
    governance_dir_name: str = ".work-governance",
) -> list[dict[str, object]]:
    """Load the direct evidence ledger for idempotency checks."""
    path = evidence_capture_ledger_path(root, governance_dir_name=governance_dir_name)
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise ValueError("EVIDENCE_CAPTURE_LEDGER_INVALID")
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("EVIDENCE_CAPTURE_LEDGER_INVALID") from exc
        if not isinstance(value, dict):
            raise ValueError("EVIDENCE_CAPTURE_LEDGER_INVALID")
        records.append(value)
    return records


def append_capture_record(
    root: Path,
    record: Mapping[str, object],
    *,
    governance_dir_name: str = ".work-governance",
) -> None:
    """Append one canonical direct evidence record to the ledger."""
    ledger = evidence_capture_ledger_path(root, governance_dir_name=governance_dir_name)
    ensure_directory_durable(ledger.parent)
    encoded = canonical_json_bytes(record)
    with ledger.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(ledger.parent)


def verify_capture_record_file(
    root: Path,
    record: Mapping[str, object],
    *,
    governance_dir_name: str = ".work-governance",
) -> tuple[str, str]:
    """Verify the content-addressed metadata file named by a ledger record."""
    ref = record.get("evidence_ref")
    digest = record.get("evidence_sha256")
    if not isinstance(ref, str) or not ref.startswith("evidence:"):
        raise ValueError("EVIDENCE_CAPTURE_RECORD_INVALID")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise ValueError("EVIDENCE_CAPTURE_RECORD_INVALID")
    expected_ref = f"evidence:{governance_dir_name}/evidence/records/{digest}.json"
    if ref != expected_ref:
        raise ValueError("EVIDENCE_CAPTURE_RECORD_INVALID")
    record_path = evidence_capture_record_path(
        root,
        digest,
        governance_dir_name=governance_dir_name,
    )
    if record_path.is_symlink() or not record_path.is_file():
        raise ValueError("EVIDENCE_CAPTURE_RECORD_MISSING")
    if sha256_file(record_path) != digest:
        raise ValueError("EVIDENCE_CAPTURE_RECORD_HASH_MISMATCH")
    return ref, digest


def find_capture_record_by_idempotency_key(
    root: Path,
    *,
    plan_id: str,
    key: str,
    governance_dir_name: str = ".work-governance",
) -> dict[str, object] | None:
    """Return the existing record for one idempotency key, if any."""
    for record in load_capture_records(root, governance_dir_name=governance_dir_name):
        if record.get("plan_id") == plan_id and record.get("idempotency_key") == key:
            return record
    return None


def validate_capture_args(args: argparse.Namespace) -> str | None:
    """Validate direct evidence capture arguments and return the normalized task."""
    if getattr(args, "stdin", False) and getattr(args, "from_file", None) is not None:
        raise ValueError("EVIDENCE_CAPTURE_SOURCE_CONFLICT")
    kind = getattr(args, "kind", None)
    if not isinstance(kind, str) or EVIDENCE_CAPTURE_KIND_RE.fullmatch(kind) is None:
        raise ValueError("EVIDENCE_CAPTURE_KIND_INVALID")
    summary = getattr(args, "summary", None)
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("EVIDENCE_CAPTURE_SUMMARY_REQUIRED")
    if len(summary) > 512:
        raise ValueError("EVIDENCE_CAPTURE_SUMMARY_TOO_LONG")
    idempotency_key = getattr(args, "idempotency_key", None)
    if (
        idempotency_key is not None
        and (
            not isinstance(idempotency_key, str)
            or EVIDENCE_CAPTURE_IDEMPOTENCY_RE.fullmatch(idempotency_key) is None
        )
    ):
        raise ValueError("EVIDENCE_CAPTURE_IDEMPOTENCY_KEY_INVALID")
    task_value = getattr(args, "task", None)
    if task_value is not None and not isinstance(task_value, str):
        raise ValueError("EVIDENCE_CAPTURE_TASK_INVALID")
    return normalize_capture_task(task_value)


def persist_capture_blob(
    root: Path,
    content: bytes,
    *,
    governance_dir_name: str = ".work-governance",
) -> tuple[str, str, int]:
    """Persist redacted direct evidence bytes as a content-addressed blob."""
    digest = sha256_bytes(content)
    blob = evidence_capture_blob_path(root, digest, governance_dir_name=governance_dir_name)
    if blob.exists():
        if blob.is_symlink() or blob.read_bytes() != content:
            raise ValueError("EVIDENCE_CAPTURE_BLOB_CONFLICT")
    else:
        write_atomic_bytes(blob, content)
    return f"evidence:{governance_dir_name}/evidence/blobs/{digest}", digest, len(content)


def persist_capture_metadata(
    root: Path,
    record: Mapping[str, object],
    *,
    governance_dir_name: str = ".work-governance",
) -> tuple[str, str]:
    """Persist direct evidence metadata as a content-addressed record."""
    canonical = canonical_evidence_bytes(record)
    digest = sha256_bytes(canonical)
    target = evidence_capture_record_path(root, digest, governance_dir_name=governance_dir_name)
    if target.exists():
        if target.is_symlink() or target.read_bytes() != canonical:
            raise ValueError("EVIDENCE_CAPTURE_RECORD_CONFLICT")
    else:
        write_atomic_bytes(target, canonical)
    return f"evidence:{governance_dir_name}/evidence/records/{digest}.json", digest


def utc_now() -> str:
    """Return the current UTC timestamp used by direct evidence records."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def persist_direct_evidence_bytes(
    root: Path,
    *,
    plan_id: str,
    task_id: str | None,
    kind: str,
    summary: str,
    raw_content: bytes,
    source_type: str,
    source_ref: str | None,
    idempotency_key: str | None,
    governance_dir_name: str = ".work-governance",
) -> dict[str, object]:
    """Persist direct evidence bytes and return the ledger-compatible record."""
    if EVIDENCE_CAPTURE_KIND_RE.fullmatch(kind) is None:
        raise ValueError("EVIDENCE_CAPTURE_KIND_INVALID")
    summary = redact_capture_text(summary.strip())
    if not summary:
        raise ValueError("EVIDENCE_CAPTURE_SUMMARY_REQUIRED")
    if len(summary) > 512:
        raise ValueError("EVIDENCE_CAPTURE_SUMMARY_TOO_LONG")
    if (
        idempotency_key is not None
        and EVIDENCE_CAPTURE_IDEMPOTENCY_RE.fullmatch(idempotency_key) is None
    ):
        raise ValueError("EVIDENCE_CAPTURE_IDEMPOTENCY_KEY_INVALID")
    redacted_content, text_source = redact_capture_bytes(raw_content)
    source_digest = sha256_bytes(redacted_content)
    task_ref = f"task:{task_id}" if task_id is not None else None
    existing = (
        find_capture_record_by_idempotency_key(
            root,
            plan_id=plan_id,
            key=idempotency_key,
            governance_dir_name=governance_dir_name,
        )
        if idempotency_key is not None
        else None
    )
    if existing is not None:
        if (
            existing.get("source_digest") != source_digest
            or existing.get("evidence_kind") != kind
            or existing.get("summary") != summary
            or existing.get("task_ref") != task_ref
        ):
            raise ValueError("EVIDENCE_CAPTURE_IDEMPOTENCY_CONFLICT")
        record_ref, record_sha256 = verify_capture_record_file(
            root,
            existing,
            governance_dir_name=governance_dir_name,
        )
        return {
            **existing,
            "evidence_ref": record_ref,
            "evidence_sha256": record_sha256,
            "idempotent": True,
        }
    blob_ref, blob_sha256, blob_size = persist_capture_blob(
        root,
        redacted_content,
        governance_dir_name=governance_dir_name,
    )
    created_at = utc_now()
    record_id = capture_record_id(created_at)
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-evidence-record",
        "id": record_id,
        "plan_id": plan_id,
        "goal_ref": f"plan:{plan_id}",
        "task_ref": task_ref,
        "evidence_kind": kind,
        "summary": summary,
        "source_type": source_type,
        "source_ref": source_ref,
        "source_digest": source_digest,
        "source_size": len(redacted_content),
        "text_source": text_source,
        "redaction_policy": "default-secret-patterns-v1",
        "blob_ref": blob_ref,
        "blob_sha256": blob_sha256,
        "blob_size": blob_size,
        "validator": "workctl:workflow",
        "result": "captured",
        "created_at": created_at,
    }
    if idempotency_key is not None:
        record["idempotency_key"] = idempotency_key
    record_ref, record_sha256 = persist_capture_metadata(
        root,
        record,
        governance_dir_name=governance_dir_name,
    )
    ledger_record = {**record, "evidence_ref": record_ref, "evidence_sha256": record_sha256}
    append_capture_record(root, ledger_record, governance_dir_name=governance_dir_name)
    return {**ledger_record, "idempotent": False}


def workflow_evidence_payload(
    *,
    plan_id: str,
    subject: str,
    producer_ref: str,
    direct_record: Mapping[str, object],
) -> dict[str, object]:
    """Create a canonical Plan evidence payload from a direct capture record."""
    evidence_ref = direct_record.get("evidence_ref")
    evidence_sha256 = direct_record.get("evidence_sha256")
    if not isinstance(evidence_ref, str) or not isinstance(evidence_sha256, str):
        raise ValueError("DIRECT_EVIDENCE_RECORD_INVALID")
    return {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": subject,
        "created_at": utc_now(),
        "producer_ref": producer_ref,
        "items": [{"ref": evidence_ref, "sha256": evidence_sha256}],
    }


def validate_evidence_payload(
    payload: Mapping[str, object],
    *,
    expected_plan_id: str,
    expected_subject: str | None,
    valid_reference: Callable[[object], bool],
    sha256_pattern: re.Pattern[str],
    max_items: int,
) -> None:
    """Validate bounded evidence metadata without accepting process output blobs."""
    subject = payload.get("subject")
    required_fields = {
        "schema_version",
        "kind",
        "plan_id",
        "subject",
        "created_at",
        "producer_ref",
        "items",
    }
    if subject == "activation":
        required_fields.add("observed_ref")
    if set(payload) != required_fields:
        raise ValueError("INVALID_EVIDENCE_MANIFEST_FIELDS")
    if payload.get("schema_version") != 1 or payload.get("kind") != "work-governance-evidence":
        raise ValueError("INVALID_EVIDENCE_MANIFEST_SCHEMA")
    if payload.get("plan_id") != expected_plan_id:
        raise ValueError("EVIDENCE_MANIFEST_PLAN_MISMATCH")
    if not isinstance(subject, str) or EVIDENCE_SUBJECT_RE.fullmatch(subject) is None:
        raise ValueError("INVALID_EVIDENCE_MANIFEST_SUBJECT")
    if expected_subject is not None and subject != expected_subject:
        raise ValueError(
            f"EVIDENCE_MANIFEST_SUBJECT_MISMATCH: expected {expected_subject}, found {subject}"
        )
    if not isinstance(payload.get("created_at"), str) or not payload.get("created_at"):
        raise ValueError("INVALID_EVIDENCE_MANIFEST_CREATED_AT")
    if not valid_reference(payload.get("producer_ref")):
        raise ValueError("INVALID_EVIDENCE_MANIFEST_PRODUCER")
    if subject == "activation":
        observed_ref = payload.get("observed_ref")
        if (
            not isinstance(observed_ref, str)
            or not observed_ref
            or observed_ref != observed_ref.strip()
            or any(character.isspace() for character in observed_ref)
        ):
            raise ValueError("INVALID_ACTIVATION_EVIDENCE_OBSERVED_REF")
    items = payload.get("items")
    if not isinstance(items, list) or not items or len(items) > max_items:
        raise ValueError("INVALID_EVIDENCE_MANIFEST_ITEMS")
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"ref", "sha256"}
            or not valid_reference(item.get("ref"))
            or not isinstance(item.get("sha256"), str)
            or sha256_pattern.fullmatch(item["sha256"]) is None
        ):
            raise ValueError("INVALID_EVIDENCE_MANIFEST_ITEM")
