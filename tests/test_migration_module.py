from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

migration_module = importlib.import_module("workctl_modules.migration")
archive_path_for_source = migration_module.archive_path_for_source
pointer_text = migration_module.pointer_text


def test_archive_path_for_source_separates_canonical_and_legacy_sources() -> None:
    """Migration archives canonical and legacy sources under separate roots."""
    migration_id = "MIG-20260724-001"

    assert (
        archive_path_for_source(
            migration_id,
            ".work-governance/_Plan/PLAN-20260723-001.md",
        )
        == ".work-governance/_Plan/archive/MIG-20260724-001/unmerged/PLAN-20260723-001.md"
    )
    assert (
        archive_path_for_source(
            migration_id,
            "docs/Plan.md",
        )
        == ".work-governance/_Plan/archive/MIG-20260724-001/legacy/docs/Plan.md"
    )


def test_archive_path_for_source_accepts_controller_directory_names() -> None:
    """The module keeps directory names parameterized by the controller."""
    assert (
        archive_path_for_source(
            "MIG-20260724-001",
            "governance/plans/PLAN.md",
            governance_dir_name="governance",
            plan_dir_name="plans",
        )
        == "governance/plans/archive/MIG-20260724-001/unmerged/PLAN.md"
    )


def test_pointer_text_uses_relative_links_and_supplied_marker() -> None:
    """Pointer text keeps existing relative-link semantics and marker binding."""
    text = pointer_text(
        source_path="docs/Plan.md",
        canonical_path=".work-governance/_Plan/PLAN-20260724-002.md",
        migration_id="MIG-20260724-001",
        archive_path=".work-governance/_Plan/archive/MIG-20260724-001/legacy/docs/Plan.md",
        pointer_marker="WORK_GOVERNANCE_NON_AUTHORITY_POINTER",
    )

    assert "# Non-authoritative migration pointer" in text
    assert (
        "- Canonical Plan: [.work-governance/_Plan/PLAN-20260724-002.md]"
        "(../.work-governance/_Plan/PLAN-20260724-002.md)"
    ) in text
    assert (
        "- Archived source: "
        "[.work-governance/_Plan/archive/MIG-20260724-001/legacy/docs/Plan.md]"
        "(../.work-governance/_Plan/archive/MIG-20260724-001/legacy/docs/Plan.md)"
    ) in text
    assert "- Marker: `WORK_GOVERNANCE_NON_AUTHORITY_POINTER`" in text
