"""Stable directory-tree manifest helpers for layout and migration checks."""

from __future__ import annotations

import json
from pathlib import Path

from workctl_modules.filesystem import FilesystemError, sha256_bytes, sha256_file


class ManifestError(ValueError):
    """Raised when a manifest helper rejects unsafe local state."""


def tree_manifest(path: Path, *, exclude_names: set[str] | None = None) -> list[dict[str, object]]:
    """Return a stable, content-addressed manifest for one regular directory tree."""
    if path.is_symlink() or not path.is_dir():
        raise ManifestError(f"MANIFEST_ROOT_INVALID: {path}")
    excluded = exclude_names or set()
    entries: list[dict[str, object]] = []
    for candidate in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        relative = candidate.relative_to(path).as_posix()
        if candidate.name in excluded:
            continue
        if candidate.is_symlink():
            raise ManifestError(f"LAYOUT_PATH_SYMLINK: {candidate}")
        if candidate.is_dir():
            entries.append({"path": relative, "kind": "directory"})
        elif candidate.is_file():
            try:
                digest = sha256_file(candidate)
            except FilesystemError as exc:
                raise ManifestError(str(exc)) from exc
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size": candidate.stat().st_size,
                    "sha256": digest,
                }
            )
        else:
            raise ManifestError(f"LAYOUT_PATH_NOT_REGULAR: {candidate}")
    return entries


def manifest_sha256(entries: list[dict[str, object]]) -> str:
    """Hash a stable tree manifest without depending on YAML presentation."""
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def proposal_manifest_from_plan_manifest(
    legacy_manifest: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Project the exact ``proposals/`` subtree from a complete legacy Plan manifest."""
    prefix = "proposals/"
    projected: list[dict[str, object]] = []
    for entry in legacy_manifest:
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.startswith(prefix):
            continue
        projected.append(
            {
                **entry,
                "path": raw_path.removeprefix(prefix),
            }
        )
    return projected


def manifest_matches_allowed_subset(
    path: Path,
    allowed_paths: set[str],
    expected_file_hashes: dict[str, str] | None = None,
) -> bool:
    """Return whether a regular tree contains only journal-bound paths and bytes."""
    expected_hashes = expected_file_hashes or {}
    for entry in tree_manifest(path):
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or raw_path not in allowed_paths:
            return False
        if (
            entry.get("kind") == "file"
            and raw_path in expected_hashes
            and entry.get("sha256") != expected_hashes[raw_path]
        ):
            return False
    return True
