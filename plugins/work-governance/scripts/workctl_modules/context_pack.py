"""Role-scoped context package construction for handoff and review."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from workctl_modules.filesystem import (
    FilesystemError,
    checked_project_path,
    reject_symlink_components,
    relative_project_path,
    sha256_bytes,
)

VALID_CONTEXT_ROLES: tuple[str, ...] = ("check", "implement", "review", "truth")
DEFAULT_MAX_FILE_BYTES = 32 * 1024
DEFAULT_MAX_TOTAL_BYTES = 128 * 1024
CONTEXT_MANIFEST_MAX_BYTES = 128 * 1024
CONTEXT_FILE_READ_CHUNK_BYTES = 1024 * 1024
SAFE_ENV_TEMPLATE_NAMES = frozenset({".env.example", ".env.sample", ".env.template"})
SECRET_FILE_NAMES = frozenset(
    {
        ".netrc",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "service-account.json",
        "service_account.json",
    }
)
SECRET_DIRECTORY_NAMES = frozenset({".aws", ".gcp", ".ssh", "secret", "secrets"})
SECRET_FILE_SUFFIXES = (".key", ".p12", ".pfx", ".pem")
SECRET_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?im)^(\s*[A-Za-z0-9_.-]*(?:api[_-]?key|auth|credential|passwd|password|"
            r"secret|token)[A-Za-z0-9_.-]*\s*=\s*).+$"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?im)^(\s*[A-Za-z0-9_.-]*(?:api[_-]?key|auth|credential|passwd|password|"
            r"secret|token)[A-Za-z0-9_.-]*\s*:\s*).+$"
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]{3,}"), r"\1[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{1,16}\b"), "AKIA[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{1,}\b"), "[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{1,}\b"), "[REDACTED]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{1,}\b"), "[REDACTED]"),
)


class ContextPackageError(ValueError):
    """Raised when a context manifest or source file is unsafe or invalid."""


def canonical_context_bytes(payload: Mapping[str, object]) -> bytes:
    """Return stable bytes for package digest calculation."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def normalize_context_role(value: object) -> str:
    """Return a supported context role."""
    if not isinstance(value, str) or not value.strip():
        raise ContextPackageError("CONTEXT_ROLE_REQUIRED")
    role = value.strip()
    if role not in VALID_CONTEXT_ROLES:
        raise ContextPackageError(f"CONTEXT_ROLE_INVALID: {role}")
    return role


def validate_limit(value: int, *, field: str) -> int:
    """Validate a byte budget argument."""
    if value < 0:
        raise ContextPackageError(f"{field}_INVALID")
    return value


def optional_string(value: object, *, field: str) -> str | None:
    """Normalize an optional non-empty string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContextPackageError(f"{field}_INVALID")
    stripped = value.strip()
    if not stripped:
        raise ContextPackageError(f"{field}_EMPTY")
    return stripped


def string_list(value: object, *, field: str) -> list[str]:
    """Normalize a list of non-empty strings."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ContextPackageError(f"{field}_INVALID")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ContextPackageError(f"{field}_{index}_INVALID")
        result.append(item.strip())
    return result


def manifest_entries(manifest: Mapping[str, object]) -> list[object]:
    """Return all explicit context entries from supported manifest fields."""
    entries: list[object] = []
    for field in ("files", "entries", "context"):
        value = manifest.get(field)
        if value is None:
            continue
        if not isinstance(value, list):
            raise ContextPackageError(f"CONTEXT_MANIFEST_{field.upper()}_INVALID")
        entries.extend(value)
    return entries


def entry_is_enabled(entry: Mapping[str, object]) -> bool:
    """Return whether a mapping entry should be considered."""
    include = entry.get("include")
    if include is None:
        return True
    if not isinstance(include, bool):
        raise ContextPackageError("CONTEXT_ENTRY_INCLUDE_INVALID")
    return include


def entry_matches_role(entry: object, role: str) -> bool:
    """Return whether a context entry is visible to the requested role."""
    if not isinstance(entry, Mapping):
        return True
    raw_role = entry.get("role")
    if raw_role is not None:
        entry_role = normalize_context_role(raw_role)
        if entry_role != role:
            return False
    raw_roles = entry.get("roles")
    if raw_roles is None:
        return True
    if isinstance(raw_roles, str):
        if raw_roles == "all":
            return True
        return normalize_context_role(raw_roles) == role
    if not isinstance(raw_roles, list):
        raise ContextPackageError("CONTEXT_ENTRY_ROLES_INVALID")
    normalized = [normalize_context_role(item) for item in raw_roles]
    return role in normalized


def entry_field(entry: Mapping[str, object], field: str) -> str | None:
    """Read a nullable string field from one context entry."""
    value = entry.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContextPackageError(f"CONTEXT_ENTRY_{field.upper()}_INVALID")
    stripped = value.strip()
    if not stripped:
        raise ContextPackageError(f"CONTEXT_ENTRY_{field.upper()}_EMPTY")
    return stripped


def normalize_entry(entry: object) -> tuple[str, str | None, str | None]:
    """Return path, reason, and label for one context entry."""
    if isinstance(entry, str):
        path = entry.strip()
        if not path:
            raise ContextPackageError("CONTEXT_ENTRY_PATH_EMPTY")
        return path, None, None
    if not isinstance(entry, Mapping):
        raise ContextPackageError("CONTEXT_ENTRY_INVALID")
    raw_path = entry.get("path", entry.get("file"))
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ContextPackageError("CONTEXT_ENTRY_PATH_REQUIRED")
    return (
        raw_path.strip(),
        entry_field(entry, "reason"),
        entry_field(entry, "label"),
    )


def project_file_for_context(root: Path, raw_path: str) -> Path:
    """Resolve and validate a project-local source file."""
    try:
        reject_symlink_components(root, root / raw_path)
        path = checked_project_path(root, raw_path)
    except FilesystemError as exc:
        if str(exc).startswith("LAYOUT_PATH_SYMLINK:"):
            raise ContextPackageError(f"CONTEXT_PATH_SYMLINK: {raw_path}") from exc
        raise ContextPackageError(str(exc)) from exc
    if path.is_dir():
        raise ContextPackageError(f"CONTEXT_PATH_IS_DIRECTORY: {raw_path}")
    if not path.is_file():
        raise ContextPackageError(f"CONTEXT_PATH_MISSING: {raw_path}")
    return path


def secret_path_reason(relative_path: str) -> str | None:
    """Return a rejection reason when a context source path is known-secret."""
    parts = [
        part.lower()
        for part in PurePosixPath(relative_path).parts
        if part not in {"", "."}
    ]
    if not parts:
        return None
    filename = parts[-1]
    if filename in SAFE_ENV_TEMPLATE_NAMES:
        return None
    if filename == ".env" or filename.startswith(".env."):
        return "env_file"
    if filename in SECRET_FILE_NAMES:
        return "secret_file"
    if filename.endswith(SECRET_FILE_SUFFIXES):
        return "secret_suffix"
    if any(part in SECRET_DIRECTORY_NAMES for part in parts[:-1]):
        return "secret_directory"
    return None


def stream_file_size_and_sha256(path: Path) -> tuple[int, str]:
    """Return file size and SHA256 without loading the whole file at once."""
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        while chunk := handle.read(CONTEXT_FILE_READ_CHUNK_BYTES):
            size_bytes += len(chunk)
            digest.update(chunk)
    return size_bytes, digest.hexdigest()


def read_file_prefix(path: Path, byte_limit: int) -> bytes:
    """Read at most ``byte_limit`` source bytes for package content."""
    if byte_limit <= 0:
        return b""
    with path.open("rb") as handle:
        return handle.read(byte_limit)


def decode_context_prefix(raw: bytes, *, may_end_mid_character: bool) -> tuple[str, int] | None:
    """Decode a bounded UTF-8 prefix, omitting binary or non-text input."""
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8"), len(raw)
    except UnicodeDecodeError as exc:
        if not may_end_mid_character or exc.reason != "unexpected end of data":
            return None
        prefix = raw[: exc.start]
        try:
            return prefix.decode("utf-8"), len(prefix)
        except UnicodeDecodeError:
            return None


def redact_context_content(text: str) -> tuple[str, bool]:
    """Redact common credential patterns from emitted context content."""
    redacted = text
    for pattern, replacement in SECRET_REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted, redacted != text


def normalize_lint_roles(manifest: Mapping[str, object], roles: list[str] | None) -> list[str]:
    """Return the role set to validate for a context manifest."""
    manifest_role = manifest.get("role")
    if roles:
        normalized = [normalize_context_role(role) for role in roles]
        if manifest_role is not None and normalize_context_role(manifest_role) not in normalized:
            raise ContextPackageError("CONTEXT_MANIFEST_ROLE_MISMATCH")
        return normalized
    if manifest_role is not None:
        return [normalize_context_role(manifest_role)]
    return list(VALID_CONTEXT_ROLES)


def lint_context_manifest(
    root: Path,
    manifest: Mapping[str, object],
    *,
    roles: list[str] | None,
    manifest_sha256: str,
) -> dict[str, object]:
    """Validate context manifest paths and role visibility without emitting content."""
    lint_roles = normalize_lint_roles(manifest, roles)
    notes = string_list(manifest.get("notes"), field="CONTEXT_NOTES")
    files: list[dict[str, object]] = []
    skipped_entries = 0
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for entry in manifest_entries(manifest):
        if isinstance(entry, Mapping) and not entry_is_enabled(entry):
            skipped_entries += 1
            continue
        matched_roles = [role for role in lint_roles if entry_matches_role(entry, role)]
        if not matched_roles:
            skipped_entries += 1
            continue
        raw_path, reason, label = normalize_entry(entry)
        path = project_file_for_context(root, raw_path)
        try:
            relative_path = relative_project_path(root, path)
        except FilesystemError as exc:
            raise ContextPackageError(str(exc)) from exc
        reason_name = secret_path_reason(relative_path)
        if reason_name is not None:
            raise ContextPackageError(
                f"CONTEXT_SECRET_PATH_REJECTED: {relative_path} ({reason_name})"
            )
        key = (relative_path, tuple(matched_roles))
        if key in seen:
            skipped_entries += 1
            continue
        seen.add(key)
        payload: dict[str, object] = {
            "path": relative_path,
            "roles": matched_roles,
        }
        if reason is not None:
            payload["reason"] = reason
        if label is not None:
            payload["label"] = label
        files.append(payload)
    if not files and not notes:
        raise ContextPackageError("CONTEXT_PACKAGE_EMPTY")
    return {
        "schema_version": 1,
        "kind": "work-governance-context-manifest-lint",
        "status": "CONTEXT_MANIFEST_VALID",
        "roles": lint_roles,
        "manifest_sha256": manifest_sha256,
        "files": files,
        "notes": notes,
        "skipped_entries": skipped_entries,
        "warnings": [],
    }


def trim_text_to_utf8_budget(text: str, byte_limit: int) -> tuple[str, int, bool]:
    """Return text trimmed to a UTF-8 byte budget and whether trimming happened."""
    raw = text.encode("utf-8")
    if len(raw) <= byte_limit:
        return text, len(raw), False
    trimmed_text, trimmed_bytes = utf8_prefix(raw[:byte_limit])
    return trimmed_text, trimmed_bytes, True


def content_text(raw: bytes) -> str | None:
    """Decode UTF-8 text content, returning None for binary or non-text input."""
    decoded = decode_context_prefix(raw, may_end_mid_character=False)
    if decoded is None:
        return None
    return decoded[0]


def utf8_prefix(raw: bytes) -> tuple[str, int]:
    """Return a valid UTF-8 prefix and its exact byte length."""
    decoded = decode_context_prefix(raw, may_end_mid_character=True)
    if decoded is None:
        return "", 0
    return decoded


def package_file_entry(
    root: Path,
    *,
    raw_path: str,
    reason: str | None,
    label: str | None,
    max_file_bytes: int,
    remaining_bytes: int,
) -> tuple[dict[str, object], int, list[str]]:
    """Read one project file into a bounded context package entry."""
    path = project_file_for_context(root, raw_path)
    try:
        relative_path = relative_project_path(root, path)
    except FilesystemError as exc:
        raise ContextPackageError(str(exc)) from exc
    reason_name = secret_path_reason(relative_path)
    if reason_name is not None:
        raise ContextPackageError(f"CONTEXT_SECRET_PATH_REJECTED: {relative_path} ({reason_name})")
    size_bytes, digest = stream_file_size_and_sha256(path)
    payload: dict[str, object] = {
        "path": relative_path,
        "sha256": digest,
        "size_bytes": size_bytes,
        "included": False,
    }
    if reason is not None:
        payload["reason"] = reason
    if label is not None:
        payload["label"] = label

    if max_file_bytes == 0 or remaining_bytes == 0:
        payload["omitted_reason"] = "content_budget_exhausted"
        return payload, 0, [f"CONTEXT_FILE_OMITTED_BUDGET_EXHAUSTED: {relative_path}"]

    keep_bytes = min(size_bytes, max_file_bytes, remaining_bytes)
    raw_prefix = read_file_prefix(path, keep_bytes)
    decoded = decode_context_prefix(raw_prefix, may_end_mid_character=keep_bytes < size_bytes)
    if decoded is None:
        payload["omitted_reason"] = "binary_or_non_utf8"
        return payload, 0, [f"CONTEXT_FILE_OMITTED_BINARY_OR_NON_UTF8: {relative_path}"]

    kept_text, kept_bytes = decoded
    redacted_text, content_redacted = redact_context_content(kept_text)
    emitted_text, emitted_bytes, emitted_truncated = trim_text_to_utf8_budget(
        redacted_text,
        keep_bytes,
    )
    payload["included"] = True
    payload["content"] = emitted_text
    payload["content_bytes"] = emitted_bytes
    payload["source_content_bytes"] = kept_bytes
    payload["truncated"] = kept_bytes < size_bytes or emitted_truncated
    warnings: list[str] = []
    if content_redacted:
        payload["redacted"] = True
        warnings.append(f"CONTEXT_CONTENT_REDACTED: {relative_path}")
    if kept_bytes < size_bytes or emitted_truncated:
        truncation_reason = "file_limit" if max_file_bytes <= remaining_bytes else "total_limit"
        payload["truncation_reason"] = truncation_reason
        warnings.append(f"CONTEXT_FILE_TRUNCATED: {relative_path}")
    return payload, emitted_bytes, warnings


def build_context_package(
    root: Path,
    manifest: Mapping[str, object],
    *,
    role: str,
    task_id: str | None,
    summary: str | None,
    max_file_bytes: int,
    max_total_bytes: int,
    manifest_sha256: str,
    active_plan_id: str | None = None,
) -> dict[str, object]:
    """Build a deterministic role-scoped package from a manifest."""
    normalized_role = normalize_context_role(role)
    manifest_role = manifest.get("role")
    if manifest_role is not None and normalize_context_role(manifest_role) != normalized_role:
        raise ContextPackageError("CONTEXT_MANIFEST_ROLE_MISMATCH")
    file_budget = validate_limit(max_file_bytes, field="CONTEXT_MAX_FILE_BYTES")
    total_budget = validate_limit(max_total_bytes, field="CONTEXT_MAX_TOTAL_BYTES")
    package_task_id = task_id or optional_string(manifest.get("task_id"), field="CONTEXT_TASK_ID")
    package_summary = (
        summary
        or optional_string(manifest.get("summary"), field="CONTEXT_SUMMARY")
        or "Role-scoped context package."
    )
    notes = string_list(manifest.get("notes"), field="CONTEXT_NOTES")

    files: list[dict[str, object]] = []
    warnings: list[str] = []
    skipped_entries = 0
    total_content_bytes = 0
    for entry in manifest_entries(manifest):
        if isinstance(entry, Mapping) and not entry_is_enabled(entry):
            skipped_entries += 1
            continue
        if not entry_matches_role(entry, normalized_role):
            skipped_entries += 1
            continue
        raw_path, reason, label = normalize_entry(entry)
        packaged, used_bytes, entry_warnings = package_file_entry(
            root,
            raw_path=raw_path,
            reason=reason,
            label=label,
            max_file_bytes=file_budget,
            remaining_bytes=max(0, total_budget - total_content_bytes),
        )
        files.append(packaged)
        total_content_bytes += used_bytes
        warnings.extend(entry_warnings)

    if not files and not notes:
        raise ContextPackageError("CONTEXT_PACKAGE_EMPTY")

    package: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-context-package",
        "status": "CONTEXT_PACKAGE_BUILT",
        "role": normalized_role,
        "summary": package_summary,
        "manifest_sha256": manifest_sha256,
        "content_budget": {
            "max_file_bytes": file_budget,
            "max_total_bytes": total_budget,
            "total_content_bytes": total_content_bytes,
        },
        "files": files,
        "notes": notes,
        "skipped_entries": skipped_entries,
        "warnings": warnings,
    }
    if package_task_id is not None:
        package["task_id"] = package_task_id
    if active_plan_id is not None:
        package["active_plan_id"] = active_plan_id
    package["package_sha256"] = sha256_bytes(canonical_context_bytes(package))
    return package
