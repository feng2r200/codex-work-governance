from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

manifest_module = importlib.import_module("workctl_modules.manifest")
filesystem_module = importlib.import_module("workctl_modules.filesystem")
ManifestError = manifest_module.ManifestError


def test_tree_manifest_hash_and_exclusions_are_stable(tmp_path: Path) -> None:
    """Tree manifests are sorted, content-addressed, and exact-name filtered."""
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "state.txt").write_text("state\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / ".workctl.lock").write_text("lock\n", encoding="utf-8")

    entries = manifest_module.tree_manifest(tmp_path, exclude_names={".workctl.lock"})

    assert entries == [
        {
            "path": "a.txt",
            "kind": "file",
            "size": 6,
            "sha256": filesystem_module.sha256_bytes(b"alpha\n"),
        },
        {"path": "b", "kind": "directory"},
        {
            "path": "b/state.txt",
            "kind": "file",
            "size": 6,
            "sha256": filesystem_module.sha256_bytes(b"state\n"),
        },
    ]
    expected_digest = filesystem_module.sha256_bytes(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    )
    assert manifest_module.manifest_sha256(entries) == expected_digest


def test_tree_manifest_rejects_unclosed_or_non_regular_trees(tmp_path: Path) -> None:
    """Tree manifesting fails closed for symlinked roots and symlink children."""
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "link").symlink_to(tmp_path / "outside")

    with pytest.raises(ManifestError, match="LAYOUT_PATH_SYMLINK"):
        manifest_module.tree_manifest(tmp_path / "root")
    with pytest.raises(ManifestError, match="MANIFEST_ROOT_INVALID"):
        manifest_module.tree_manifest(tmp_path / "missing")


def test_proposal_manifest_projection_removes_only_proposals_prefix() -> None:
    """Legacy Plan manifests project proposal subtree entries without broad rewrites."""
    legacy_manifest = [
        {"path": "active.md", "kind": "file"},
        {"path": "proposals", "kind": "directory"},
        {"path": "proposals/T-001.md", "kind": "file", "sha256": "a" * 64},
        {"path": "proposals/nested/item.md", "kind": "file", "sha256": "b" * 64},
    ]

    assert manifest_module.proposal_manifest_from_plan_manifest(legacy_manifest) == [
        {"path": "T-001.md", "kind": "file", "sha256": "a" * 64},
        {"path": "nested/item.md", "kind": "file", "sha256": "b" * 64},
    ]


def test_manifest_matches_allowed_subset_checks_paths_and_hashes(tmp_path: Path) -> None:
    """Subset matching rejects unknown paths and journal-drifted file hashes."""
    (tmp_path / "state.txt").write_text("state\n", encoding="utf-8")
    digest = filesystem_module.sha256_bytes(b"state\n")

    assert manifest_module.manifest_matches_allowed_subset(
        tmp_path,
        {"state.txt"},
        {"state.txt": digest},
    )
    assert not manifest_module.manifest_matches_allowed_subset(
        tmp_path,
        {"state.txt"},
        {"state.txt": "0" * 64},
    )
    (tmp_path / "extra.txt").write_text("extra\n", encoding="utf-8")
    assert not manifest_module.manifest_matches_allowed_subset(
        tmp_path,
        {"state.txt"},
        {"state.txt": digest},
    )
