from __future__ import annotations

import importlib
import os
import stat
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

filesystem_module = importlib.import_module("workctl_modules.filesystem")
FilesystemError = filesystem_module.FilesystemError


def test_hash_and_project_path_helpers_reject_unsafe_paths(tmp_path: Path) -> None:
    """Filesystem helpers preserve digest behavior and project containment."""
    target = tmp_path / "src" / "state.txt"
    target.parent.mkdir()
    target.write_bytes(b"state\n")

    assert filesystem_module.sha256_bytes(b"state\n") == (
        "927489cb2fcdb32e302713f6a720397868b71dd2128c734181983f367d622c24"
    )
    assert filesystem_module.sha256_file(target) == (
        "927489cb2fcdb32e302713f6a720397868b71dd2128c734181983f367d622c24"
    )
    assert filesystem_module.relative_project_path(tmp_path, target) == "src/state.txt"
    assert filesystem_module.checked_project_path(tmp_path, "src/state.txt") == target

    with pytest.raises(FilesystemError, match="INVALID_PROJECT_PATH"):
        filesystem_module.checked_project_path(tmp_path, "/tmp/outside")
    with pytest.raises(FilesystemError, match="PATH_OUTSIDE_PROJECT"):
        filesystem_module.checked_project_path(tmp_path, "../outside")


def test_reject_symlink_components_rejects_existing_symlink(tmp_path: Path) -> None:
    """Control paths fail closed when any existing component is a symlink."""
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "target")

    with pytest.raises(FilesystemError, match="LAYOUT_PATH_SYMLINK: link"):
        filesystem_module.reject_symlink_components(tmp_path, link / "child")


def test_durable_write_and_move_helpers_sync_expected_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Durable writes sync file data before directory entry transitions."""
    real_fsync = os.fsync
    synchronized_modes: list[int] = []

    def record_fsync(fd: int) -> None:
        synchronized_modes.append(os.fstat(fd).st_mode)
        real_fsync(fd)

    monkeypatch.setattr(filesystem_module.os, "fsync", record_fsync)

    target = tmp_path / "new" / "nested" / "state.txt"
    filesystem_module.write_atomic(target, "durable\n")

    assert target.read_text(encoding="utf-8") == "durable\n"
    assert any(stat.S_ISREG(mode) for mode in synchronized_modes)
    assert sum(stat.S_ISDIR(mode) for mode in synchronized_modes) >= 3

    events: list[tuple[str, Path, Path | None]] = []
    monkeypatch.setattr(
        filesystem_module.os,
        "replace",
        lambda source, destination: events.append(("replace", source, destination)),
    )
    monkeypatch.setattr(
        filesystem_module,
        "fsync_directory",
        lambda path: events.append(("fsync", path, None)),
    )

    source = tmp_path / "source" / "tree"
    destination = tmp_path / "destination" / "tree"
    filesystem_module.durable_replace(source, destination)

    assert events == [
        ("replace", source, destination),
        ("fsync", source.parent, None),
        ("fsync", destination.parent, None),
    ]


def test_tree_copy_and_unlink_durability_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tree, copy, and unlink helpers expose durable ordering for controller calls."""
    tree = tmp_path / "tree"
    child = tree / "child"
    child.mkdir(parents=True)
    (tree / "root.txt").write_text("root\n", encoding="utf-8")
    (child / "child.txt").write_text("child\n", encoding="utf-8")
    target_parent = tmp_path / "target"
    target_parent.mkdir()
    target = target_parent / "copied.txt"
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(
        filesystem_module.os,
        "fsync",
        lambda descriptor: events.append(("file-fsync", descriptor)),
    )
    monkeypatch.setattr(
        filesystem_module,
        "fsync_directory",
        lambda path: events.append(("dir-fsync", path)),
    )

    filesystem_module.fsync_tree(tree)
    tree_events = list(events)
    assert [event[0] for event in tree_events] == [
        "file-fsync",
        "file-fsync",
        "dir-fsync",
        "dir-fsync",
    ]
    assert tree_events[-2:] == [("dir-fsync", child), ("dir-fsync", tree)]

    events.clear()
    filesystem_module.durable_copy_file(tree / "root.txt", target)
    assert target.read_bytes() == b"root\n"
    assert [event[0] for event in events] == ["file-fsync", "dir-fsync"]
    assert events[-1] == ("dir-fsync", target_parent)

    events.clear()
    filesystem_module.durable_unlink(target)
    assert not target.exists()
    assert events == [("dir-fsync", target_parent)]
