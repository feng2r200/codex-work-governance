"""Filesystem hashing, containment, and durability helpers."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tempfile
from pathlib import Path


class FilesystemError(ValueError):
    """Raised when a filesystem helper rejects unsafe local state."""


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA256 digest for *content*."""
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest for a regular file."""
    if not path.is_file():
        raise FilesystemError(f"MISSING_FILE: {path}")
    return sha256_bytes(path.read_bytes())


def relative_project_path(root: Path, path: Path) -> str:
    """Return a stable project-relative POSIX path."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise FilesystemError(f"PATH_OUTSIDE_PROJECT: {path}") from exc


def reject_symlink_components(root: Path, path: Path) -> None:
    """Reject an existing symlink in a project-local control path chain."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise FilesystemError(f"PATH_OUTSIDE_PROJECT: {path}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise FilesystemError(f"LAYOUT_PATH_SYMLINK: {current.relative_to(root).as_posix()}")


def checked_project_path(root: Path, raw_path: str) -> Path:
    """Resolve a manifest path while preventing project-root escape."""
    if not raw_path or Path(raw_path).is_absolute():
        raise FilesystemError(f"INVALID_PROJECT_PATH: {raw_path}")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FilesystemError(f"PATH_OUTSIDE_PROJECT: {raw_path}") from exc
    return resolved


def fsync_directory(path: Path) -> None:
    """Synchronize one directory entry set to durable storage."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_tree(path: Path) -> None:
    """Synchronize every regular file, then every directory from leaves upward."""
    if path.is_symlink() or not path.is_dir():
        raise FilesystemError(f"DURABILITY_TREE_INVALID: {path}")
    directories = [path]
    for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            raise FilesystemError(f"LAYOUT_PATH_SYMLINK: {candidate}")
        if candidate.is_dir():
            directories.append(candidate)
        elif candidate.is_file():
            with candidate.open("rb") as handle:
                os.fsync(handle.fileno())
        else:
            raise FilesystemError(f"LAYOUT_PATH_NOT_REGULAR: {candidate}")
    for directory in sorted(
        directories,
        key=lambda item: len(item.relative_to(path).parts),
        reverse=True,
    ):
        fsync_directory(directory)


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
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()


def write_atomic(path: Path, text: str) -> None:
    """Atomically replace a UTF-8 text file."""
    write_atomic_bytes(path, text.encode())


def durable_replace(source: Path, target: Path) -> None:
    """Rename one path and durably synchronize both affected parent entries."""
    source_parent = source.parent
    target_parent = target.parent
    os.replace(source, target)
    fsync_directory(source_parent)
    if target_parent != source_parent:
        fsync_directory(target_parent)


def durable_copy_file(source: Path, target: Path) -> None:
    """Copy one regular file through a synced temp file and durable rename."""
    if source.is_symlink() or not source.is_file():
        raise FilesystemError(f"DURABLE_COPY_SOURCE_INVALID: {source}")
    ensure_directory_durable(target.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with source.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, target)
        fsync_directory(target.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def durable_unlink(path: Path) -> None:
    """Remove one file and synchronize the parent directory entry."""
    path.unlink()
    fsync_directory(path.parent)
