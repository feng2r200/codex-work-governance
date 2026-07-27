from __future__ import annotations

import hashlib
import json
import os
import runpy
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "plugins" / "work-governance" / "scripts" / "workctl.py"


def run_workctl(
    cwd: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"workctl failed: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    return result


def init_plan(cwd: Path) -> None:
    run_workctl(cwd, "plan", "init", "--plan-id", "PLAN-20260723-001", "--title", "Test")


def plan_path(cwd: Path) -> Path:
    return cwd / "_Plan" / "PLAN-20260723-001.md"


def read_plan(cwd: Path) -> tuple[dict[str, Any], str]:
    text = plan_path(cwd).read_text(encoding="utf-8")
    _, raw, body = text.split("---\n", 2)
    payload = yaml.safe_load(raw)
    assert isinstance(payload, dict)
    return payload, body


def write_plan(cwd: Path, frontmatter: dict[str, Any], body: str = "# Body\n") -> None:
    text = yaml.safe_dump(frontmatter, sort_keys=False)
    plan_path(cwd).write_text(f"---\n{text}---\n{body}", encoding="utf-8")


def sha256_path(path: Path) -> str:
    """Return a test fixture file's SHA256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def legacy_frontmatter(plan_id: str, *, status: str = "active") -> dict[str, Any]:
    """Build a schema-v1 Plan fixture without authority metadata."""
    return {
        "schema_version": 1,
        "plan_id": plan_id,
        "title": "Legacy execution Plan",
        "status": status,
        "mode": "autonomous",
        "revision": 17,
        "created_at": "2026-07-23T00:00:00+00:00",
        "updated_at": "2026-07-23T00:00:00+00:00",
        "scope": {"include": ["Execute the current route."], "exclude": []},
        "confirmations": {"required": []},
        "obligations": [],
        "tasks": [{"id": "T-001", "description": "Continue execution.", "status": "pending"}],
        "validations": [],
        "artifacts": [],
    }


def canonical_frontmatter(plan_id: str) -> dict[str, Any]:
    """Build a schema-v2 canonical Plan fixture for reconciliation."""
    return {
        "schema_version": 2,
        "plan_id": plan_id,
        "title": "Merged canonical Plan",
        "status": "active",
        "mode": "autonomous",
        "revision": 1,
        "created_at": "2026-07-24T00:00:00+00:00",
        "updated_at": "2026-07-24T00:00:00+00:00",
        "scope": {"include": ["Continue from reconciled evidence."], "exclude": []},
        "confirmations": {"required": []},
        "obligations": [
            {"id": "O-001", "description": "Use one active Plan.", "status": "pending"}
        ],
        "tasks": [{"id": "T-001", "description": "Resume safely.", "status": "pending"}],
        "validations": [{"id": "V-001", "description": "Validate lineage.", "status": "pending"}],
        "artifacts": [{"id": "A-001", "path": "out.txt", "status": "pending"}],
        "authority": {
            "model": "single-active",
            "state": "governed",
            "canonical_plan_id": plan_id,
            "sources": [],
            "confirmations": {},
        },
        "route": {
            "route_status": "active",
            "slice_status": "reconciled",
            "next_phase": "Resume the first dependency-ready task.",
            "validation_standard": "Fresh evidence covers every obligation.",
            "confirmation_gate": "none",
        },
        "handoff": {
            "route_status": "active",
            "next_step": "Resume the first dependency-ready task.",
        },
    }


def write_markdown_plan(path: Path, frontmatter: dict[str, Any], body: str = "# Body\n") -> None:
    """Write a Plan fixture with YAML frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_dump(frontmatter, sort_keys=False)
    path.write_text(f"---\n{raw}---\n{body}", encoding="utf-8")


def write_legacy_active(cwd: Path, plan_id: str = "PLAN-20260723-001") -> Path:
    """Create an indexed schema-v1 active Plan fixture."""
    path = cwd / "_Plan" / f"{plan_id}.md"
    write_markdown_plan(path, legacy_frontmatter(plan_id))
    index = {
        "schema_version": 1,
        "active_plan_id": plan_id,
        "plans": [
            {
                "id": plan_id,
                "path": path.name,
                "title": "Legacy execution Plan",
                "created_at": "2026-07-23T00:00:00+00:00",
            }
        ],
    }
    (cwd / "_Plan" / "index.yaml").write_text(
        yaml.safe_dump(index, sort_keys=False),
        encoding="utf-8",
    )
    return path


def write_reconciliation_fixture(
    cwd: Path,
    *,
    include_agents_rewrite: bool = False,
) -> Path:
    """Create a two-authority reconciliation manifest and prepared target."""
    old_plan = write_legacy_active(cwd)
    docs_plan = cwd / "docs" / "Plan.md"
    write_markdown_plan(
        docs_plan,
        legacy_frontmatter("PLAN-20260722-001"),
        "# Current execution plan\n\n"
        "Target, phase, task queue, confirmation gate, and next step.\n",
    )
    prepared = cwd / "prepared.md"
    write_markdown_plan(prepared, canonical_frontmatter("PLAN-20260724-002"))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "migration_id": "MIG-20260724-001",
        "target_plan": {"prepared_file": "prepared.md"},
        "sources": [
            {
                "path": "docs/Plan.md",
                "role": "merged-source",
                "classification": "CONFIRMED_AUTHORITY",
                "sha256": sha256_path(docs_plan),
                "revision": 17,
            },
            {
                "path": "_Plan/PLAN-20260723-001.md",
                "role": "unmerged-source",
                "classification": "CONFIRMED_AUTHORITY",
                "sha256": sha256_path(old_plan),
                "revision": 17,
            },
        ],
        "confirmations": {},
    }
    if include_agents_rewrite:
        agents = cwd / "AGENTS.md"
        agents.write_text(
            "`docs/Plan.md` is the authoritative execution Plan and must be updated.\n",
            encoding="utf-8",
        )
        replacement = cwd / "AGENTS.proposed.md"
        replacement.write_text(
            "`_Plan/PLAN-20260724-002.md` is the authoritative execution Plan "
            "and must be updated.\n",
            encoding="utf-8",
        )
        manifest["agents_rewrite"] = {
            "path": "AGENTS.md",
            "sha256": sha256_path(agents),
            "replacement_file": "AGENTS.proposed.md",
        }
    manifest_path = cwd / "reconcile.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def bind_reconciliation_confirmations(
    cwd: Path,
    manifest_path: Path,
    *,
    include_agents_confirmation: bool,
) -> dict[str, Any]:
    """Bind confirmations to the exact dry-run proposal and optional AGENTS diff."""
    dry_run = cast(
        dict[str, Any],
        json.loads(
            run_workctl(
                cwd,
                "plan",
                "reconcile",
                "apply",
                "--manifest",
                str(manifest_path),
                "--dry-run",
            ).stdout
        ),
    )
    manifest = cast(
        dict[str, Any],
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")),
    )
    manifest["confirmations"]["baseline"] = {
        "id": "C-MIGRATION-BASELINE",
        "ref": "user:approved-plan",
        "accepted_at": "2026-07-24T00:01:00+00:00",
        "evidence_sha256": dry_run["proposal_sha256"],
    }
    if include_agents_confirmation:
        manifest["confirmations"]["agents_rewrite"] = {
            "id": "C-AGENTS-REWRITE",
            "ref": "user:approved-agents-diff",
            "accepted_at": "2026-07-24T00:02:00+00:00",
            "evidence_sha256": dry_run["agents_diff_sha256"],
        }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return dry_run


def make_terminal_rollover_source(cwd: Path) -> Path:
    """Create a governed, complete, terminal, closeout-ready Plan."""
    init_plan(cwd)
    frontmatter, body = read_plan(cwd)
    frontmatter["status"] = "complete"
    frontmatter["delivery"] = {
        "status": "complete",
        "boundary": "local-source-only",
        "evidence_ref": "git:terminal-source",
    }
    frontmatter["activation"] = {
        "status": "not_required",
        "current_ref": "not-applicable",
        "target_ref": "not-applicable",
        "decision_ref": "user:source-only",
    }
    frontmatter["route"] = {
        "route_status": "terminal",
        "slice_status": "complete",
        "next_phase": "none",
        "validation_standard": "Every obligation has fresh evidence.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {"route_status": "terminal", "next_step": "none"}
    write_plan(cwd, frontmatter, body)
    return plan_path(cwd)


def rollover_target_frontmatter(plan_id: str) -> dict[str, Any]:
    """Build an active schema-v3 successor contract."""
    return {
        "schema_version": 3,
        "plan_id": plan_id,
        "title": "Successor Plan",
        "status": "active",
        "mode": "autonomous",
        "revision": 1,
        "created_at": "2026-07-27T00:00:00+00:00",
        "updated_at": "2026-07-27T00:00:00+00:00",
        "scope": {"include": ["Execute the successor route."], "exclude": []},
        "confirmations": {"required": []},
        "obligations": [
            {"id": "O-001", "description": "Deliver the successor.", "status": "pending"}
        ],
        "tasks": [{"id": "T-001", "description": "Execute safely.", "status": "pending"}],
        "validations": [
            {"id": "V-001", "description": "Validate the successor.", "status": "pending"}
        ],
        "artifacts": [{"id": "A-001", "path": "successor.txt", "status": "pending"}],
        "authority": {
            "model": "single-active",
            "state": "governed",
            "canonical_plan_id": plan_id,
            "sources": [],
            "confirmations": {},
        },
        "delivery": {
            "status": "pending",
            "boundary": "successor-delivery",
            "evidence_ref": "project:successor-not-yet-delivered",
        },
        "activation": {
            "status": "not_required",
            "current_ref": "not-applicable",
            "target_ref": "not-applicable",
            "decision_ref": "user:source-only",
        },
        "route": {
            "route_status": "active",
            "slice_status": "initialized",
            "next_phase": "Execute T-001.",
            "validation_standard": "Fresh evidence covers O-001 and V-001.",
            "confirmation_gate": "none",
        },
        "handoff": {"route_status": "active", "next_step": "Execute T-001."},
    }


def write_rollover_fixture(cwd: Path) -> Path:
    """Create a terminal source, prepared successor, and rollover manifest."""
    source = make_terminal_rollover_source(cwd)
    source_frontmatter, _ = read_plan(cwd)
    prepared = cwd / "successor.md"
    write_markdown_plan(
        prepared,
        rollover_target_frontmatter("PLAN-20260727-001"),
        "# Successor authority\n",
    )
    index = cwd / "_Plan" / "index.yaml"
    manifest = {
        "schema_version": 1,
        "rollover_id": "ROL-20260727-001",
        "source_plan": {
            "path": "_Plan/PLAN-20260723-001.md",
            "plan_id": source_frontmatter["plan_id"],
            "revision": source_frontmatter["revision"],
            "sha256": sha256_path(source),
        },
        "index_baseline": {
            "active_plan_id": source_frontmatter["plan_id"],
            "sha256": sha256_path(index),
        },
        "target_plan": {
            "prepared_file": "successor.md",
            "plan_id": "PLAN-20260727-001",
            "revision": 1,
            "sha256": sha256_path(prepared),
        },
        "confirmations": {},
    }
    manifest_path = cwd / "rollover.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def bind_rollover_confirmation(cwd: Path, manifest_path: Path) -> dict[str, Any]:
    """Bind C-PLAN-ROLLOVER to the exact dry-run proposal digest."""
    dry_run = cast(
        dict[str, Any],
        json.loads(
            run_workctl(
                cwd,
                "plan",
                "rollover",
                "apply",
                "--manifest",
                str(manifest_path),
                "--dry-run",
            ).stdout
        ),
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["confirmations"]["rollover"] = {
        "id": "C-PLAN-ROLLOVER",
        "ref": "user:approved-rollover",
        "accepted_at": "2026-07-27T00:01:00+00:00",
        "evidence_sha256": dry_run["proposal_sha256"],
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return dry_run


def test_plan_init_status_and_active_conflict(tmp_path: Path) -> None:
    init_plan(tmp_path)

    status = run_workctl(tmp_path, "plan", "status")
    payload = json.loads(status.stdout)
    assert payload["plan_id"] == "PLAN-20260723-001"
    assert payload["revision"] == 1

    duplicate = run_workctl(
        tmp_path,
        "plan",
        "init",
        "--plan-id",
        "PLAN-20260723-002",
        "--title",
        "Other",
        check=False,
    )
    assert duplicate.returncode == 2
    assert "ACTIVE_PLAN_EXISTS" in duplicate.stderr


def test_expected_revision_gate(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [{"id": "T-001", "description": "Task", "status": "pending"}]
    write_plan(tmp_path, frontmatter, body)

    missing = run_workctl(tmp_path, "plan", "revise", "--status", "active", check=False)
    assert missing.returncode == 2

    mismatch = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "99",
        check=False,
    )
    assert mismatch.returncode == 2
    assert "REVISION_MISMATCH" in mismatch.stderr


def test_plan_revise_cannot_bypass_closeout_with_complete_status(tmp_path: Path) -> None:
    """Only the closeout command may set the Plan's complete status."""
    init_plan(tmp_path)

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--status",
        "complete",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "PLAN_COMPLETE_REQUIRES_CLOSEOUT_COMMAND" in result.stderr


def test_non_terminal_plan_status_transition_requires_confirmation(tmp_path: Path) -> None:
    """Operational Plan status changes remain structural authority changes."""
    init_plan(tmp_path)

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--status",
        "validating",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "CONFIRMATION_REQUIRED: structural plan revision" in result.stderr


def test_dependency_gate_blocks_start_until_verified(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [
        {"id": "T-001", "description": "First", "status": "pending"},
        {"id": "T-002", "description": "Second", "status": "pending", "depends_on": ["T-001"]},
    ]
    write_plan(tmp_path, frontmatter, body)

    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-002",
        "--expected-revision",
        "1",
        check=False,
    )
    assert blocked.returncode == 2
    assert "DEPENDENCY_NOT_VERIFIED" in blocked.stderr

    run_workctl(tmp_path, "task", "start", "--task-id", "T-001", "--expected-revision", "1")
    run_workctl(tmp_path, "task", "verify", "--task-id", "T-001", "--expected-revision", "2")
    run_workctl(tmp_path, "task", "start", "--task-id", "T-002", "--expected-revision", "3")
    frontmatter, _ = read_plan(tmp_path)
    assert frontmatter["tasks"][1]["status"] == "in_progress"
    assert frontmatter["revision"] == 4


def test_pending_task_cannot_be_verified_directly(tmp_path: Path) -> None:
    """Task evidence cannot skip the execution-state transition."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [{"id": "T-001", "description": "Task", "status": "pending"}]
    write_plan(tmp_path, frontmatter, body)

    result = run_workctl(
        tmp_path,
        "task",
        "verify",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "INVALID_TASK_TRANSITION: T-001 pending -> verified" in result.stderr


def test_confirmation_gate_blocks_high_impact_task(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [{"id": "C-LIVE", "description": "Live switch", "status": "pending"}]
    }
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Live switch",
            "status": "pending",
            "requires_confirmation": "C-LIVE",
        }
    ]
    write_plan(tmp_path, frontmatter, body)

    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
        check=False,
    )
    assert blocked.returncode == 2
    assert "CONFIRMATION_REQUIRED" in blocked.stderr

    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-LIVE",
        "--ref",
        "user:confirmed",
        "--expected-revision",
        "1",
    )
    run_workctl(tmp_path, "task", "start", "--task-id", "T-001", "--expected-revision", "2")


def test_plan_revise_updates_scope_after_confirmation(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [{"id": "C-PUBLISH", "description": "Publish", "status": "pending"}]
    }
    frontmatter["scope"]["exclude"] = [
        {
            "description": "Push to a remote repository.",
            "disposition": "pending_confirmation",
            "confirmation_id": "C-PUBLISH",
        }
    ]
    write_plan(tmp_path, frontmatter, body)

    missing_confirmation = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--include",
        "Publish the repository.",
        "--expected-revision",
        "1",
        check=False,
    )
    assert missing_confirmation.returncode == 2
    assert "CONFIRMATION_REQUIRED: structural plan revision" in missing_confirmation.stderr

    blocked = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--confirmation",
        "C-PUBLISH",
        "--include",
        "Publish the repository.",
        "--remove-exclude",
        "Push to a remote repository.",
        "--expected-revision",
        "1",
        check=False,
    )
    assert blocked.returncode == 2
    assert "CONFIRMATION_REQUIRED" in blocked.stderr

    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-PUBLISH",
        "--ref",
        "user:confirmed",
        "--expected-revision",
        "1",
    )
    resolution_patch = tmp_path / "publish-resolution.yaml"
    resolution_patch.write_text(
        """\
scope:
  include:
    - Publish the repository.
  exclude:
    - description: Push to a remote repository.
      disposition: completed
      confirmation_id: C-PUBLISH
      resolution_ref: user:confirmed
""",
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--confirmation",
        "C-PUBLISH",
        "--patch-file",
        str(resolution_patch),
        "--status",
        "switching",
        "--expected-revision",
        "2",
    )

    frontmatter, _ = read_plan(tmp_path)
    assert frontmatter["scope"]["include"][-1] == "Publish the repository."
    assert frontmatter["scope"]["exclude"][0]["disposition"] == "completed"
    assert frontmatter["status"] == "switching"
    assert frontmatter["revision"] == 3
    index = yaml.safe_load((tmp_path / "_Plan" / "index.yaml").read_text(encoding="utf-8"))
    assert "status" not in index["plans"][0]
    assert "updated_at" not in index["plans"][0]


def test_plan_revise_applies_authorized_patch_and_body(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [{"id": "C-STRUCTURE", "description": "Structure", "status": "pending"}]
    }
    write_plan(tmp_path, frontmatter, body)
    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-STRUCTURE",
        "--ref",
        "user:confirmed",
        "--expected-revision",
        "1",
    )
    patch_path = tmp_path / "patch.yaml"
    patch_path.write_text(
        yaml.safe_dump(
            {
                "obligations": [
                    {"id": "O-001", "description": "Publish safely", "status": "pending"}
                ],
                "validations": [
                    {"id": "V-001", "description": "Privacy scan", "status": "pending"}
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    body_path = tmp_path / "body.md"
    body_path.write_text("# Decision Summary\n\nAuthorized structure.\n", encoding="utf-8")

    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--body-file",
        str(body_path),
        "--confirmation",
        "C-STRUCTURE",
        "--expected-revision",
        "2",
    )

    revised, revised_body = read_plan(tmp_path)
    assert revised["obligations"][0]["id"] == "O-001"
    assert revised["validations"][0]["id"] == "V-001"
    assert revised_body == "# Decision Summary\n\nAuthorized structure.\n"
    assert revised["revision"] == 3


@pytest.mark.parametrize(
    ("patch_text", "error"),
    [
        ("artifacts: null\n", "artifacts must be a list"),
        (
            "artifacts:\n  - id: A-001\n    status: pending\n",
            "A-001 requires a non-empty path",
        ),
        (
            "artifacts:\n  - id: A-001\n    path: ''\n    status: pending\n",
            "A-001 requires a non-empty path",
        ),
        (
            "artifacts:\n  - id: A-001\n    path: 7\n    status: pending\n",
            "A-001 requires a non-empty path",
        ),
    ],
)
def test_failed_plan_patch_preserves_original_file(
    tmp_path: Path,
    patch_text: str,
    error: str,
) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-STRUCTURE",
                "description": "Structure",
                "status": "accepted",
                "ref": "user:confirmed",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    write_plan(tmp_path, frontmatter, body)
    original = plan_path(tmp_path).read_bytes()
    patch_path = tmp_path / "invalid-patch.yaml"
    patch_path.write_text(patch_text, encoding="utf-8")

    failed = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-STRUCTURE",
        "--expected-revision",
        "1",
        check=False,
    )

    assert failed.returncode == 2
    assert f"INVALID_PLAN: {error}" in failed.stderr
    assert plan_path(tmp_path).read_bytes() == original


def test_atomic_write_failure_preserves_original_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = runpy.run_path(str(SCRIPT))
    write_atomic = cast(Callable[[Path, str], None], namespace["write_atomic"])
    target = tmp_path / "state.yaml"
    target.write_text("original\n", encoding="utf-8")

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        write_atomic(target, "replacement\n")

    assert target.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.glob(".state.yaml.*")) == []


def test_atomic_write_fsyncs_file_new_directories_and_replaced_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Atomic writes synchronize both file content and directory entries."""
    namespace = runpy.run_path(str(SCRIPT))
    write_atomic = cast(Callable[[Path, str], None], namespace["write_atomic"])
    real_fsync = os.fsync
    synchronized_modes: list[int] = []

    def record_fsync(fd: int) -> None:
        synchronized_modes.append(os.fstat(fd).st_mode)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", record_fsync)
    target = tmp_path / "new-parent" / "nested" / "state.yaml"

    write_atomic(target, "durable\n")

    assert target.read_text(encoding="utf-8") == "durable\n"
    assert any(stat.S_ISREG(mode) for mode in synchronized_modes)
    assert sum(stat.S_ISDIR(mode) for mode in synchronized_modes) >= 3


def test_exclusive_lock_blocks_writer_until_release(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-STATUS",
                "description": "Status transition",
                "status": "accepted",
                "ref": "user:status",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    write_plan(tmp_path, frontmatter, body)
    lock_path = tmp_path / "_Plan" / ".workctl.lock"
    holder_ready_path = tmp_path / "holder-ready"
    writer_attempt_path = tmp_path / "writer-attempt"
    release_path = tmp_path / "release-holder"
    holder_script = """
import fcntl
import pathlib
import sys
import time

lock_path = pathlib.Path(sys.argv[1])
ready_path = pathlib.Path(sys.argv[2])
release_path = pathlib.Path(sys.argv[3])
with lock_path.open("w", encoding="utf-8") as handle:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    ready_path.write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 3
    while not release_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not release_path.exists():
        raise SystemExit(2)
"""
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            holder_script,
            str(lock_path),
            str(holder_ready_path),
            str(release_path),
        ],
        cwd=tmp_path,
    )
    deadline = time.monotonic() + 2
    while not holder_ready_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert holder_ready_path.exists()

    command = [
        sys.executable,
        str(SCRIPT),
        "plan",
        "revise",
        "--status",
        "validating",
        "--confirmation",
        "C-STATUS",
        "--expected-revision",
        "1",
    ]
    writer = subprocess.Popen(
        command,
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "WORKCTL_TEST_LOCK_ATTEMPT_FILE": str(writer_attempt_path)},
    )
    deadline = time.monotonic() + 2
    while not writer_attempt_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert writer_attempt_path.exists()
    assert writer.poll() is None
    release_path.write_text("release\n", encoding="utf-8")
    assert holder.wait(timeout=2) == 0
    stdout, stderr = writer.communicate(timeout=2)

    assert writer.returncode == 0, (stdout, stderr)
    frontmatter, _ = read_plan(tmp_path)
    assert frontmatter["revision"] == 2
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_suspect_artifact_blocks_validation_and_task_progress(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [{"id": "T-001", "description": "Task", "status": "pending"}]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "suspect"}]
    write_plan(tmp_path, frontmatter, body)

    validation = run_workctl(tmp_path, "plan", "validate", check=False)
    assert validation.returncode == 1
    assert "A-001 is suspect" in validation.stderr

    start = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
        check=False,
    )
    assert start.returncode == 2
    assert "BLOCKED_BY_ARTIFACT" in start.stderr


def test_declared_recovery_task_can_progress_with_suspect_artifact(tmp_path: Path) -> None:
    """Only an explicit recovery task may progress while its artifact is suspect."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Repair suspect output",
            "status": "pending",
            "resolves_artifacts": ["A-001"],
        }
    ]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "suspect"}]
    write_plan(tmp_path, frontmatter, body)

    started = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
    )
    revised, _ = read_plan(tmp_path)

    assert "TASK_UPDATED T-001 in_progress revision=2" in started.stdout
    assert revised["tasks"][0]["status"] == "in_progress"
    assert revised["artifacts"][0]["status"] == "suspect"


@pytest.mark.parametrize("blocking_status", ["quarantined", "rollback-pending"])
def test_recovery_task_cannot_bypass_non_suspect_artifact_blockers(
    tmp_path: Path,
    blocking_status: str,
) -> None:
    """Recovery exceptions apply only to suspect evidence, never stronger blockers."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Repair artifacts",
            "status": "pending",
            "resolves_artifacts": ["A-001", "A-002"],
        }
    ]
    frontmatter["artifacts"] = [
        {"id": "A-001", "path": "suspect.txt", "status": "suspect"},
        {"id": "A-002", "path": "blocked.txt", "status": blocking_status},
    ]
    write_plan(tmp_path, frontmatter, body)

    result = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert f"BLOCKED_BY_ARTIFACT: A-002 is {blocking_status}" in result.stderr


def test_final_artifact_can_fail_safe_to_suspect_and_block_task(tmp_path: Path) -> None:
    """Deviation marking remains available even after an artifact was finalized."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [
        {"id": "T-001", "description": "Downstream task", "status": "in_progress"}
    ]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "final"}]
    write_plan(tmp_path, frontmatter, body)

    changed = run_workctl(
        tmp_path,
        "plan",
        "artifact-state",
        "--artifact-id",
        "A-001",
        "--state",
        "suspect",
        "--evidence-ref",
        "evidence:deviation",
        "--evidence-sha256",
        "a" * 64,
        "--expected-revision",
        "1",
    )
    blocked = run_workctl(
        tmp_path,
        "task",
        "block",
        "--task-id",
        "T-001",
        "--expected-revision",
        "2",
    )
    revised, _ = read_plan(tmp_path)

    assert "ARTIFACT_STATE_UPDATED A-001 suspect" in changed.stdout
    assert "TASK_UPDATED T-001 blocked" in blocked.stdout
    assert revised["artifacts"][0]["status"] == "suspect"
    assert revised["tasks"][0]["status"] == "blocked"


@pytest.mark.parametrize("stronger_state", ["quarantined", "rollback-pending"])
def test_stronger_artifact_state_requires_recovery_gate_before_finalize(
    tmp_path: Path,
    stronger_state: str,
) -> None:
    """Quarantine and rollback-pending cannot jump directly back to final."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-RECOVERY",
                "description": "Artifact recovery",
                "status": "accepted",
                "ref": "user:recovery",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Recover artifact",
            "status": "in_progress",
            "resolves_artifacts": ["A-001"],
        }
    ]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "suspect"}]
    frontmatter["route"]["confirmation_gate"] = "C-RECOVERY"
    write_plan(tmp_path, frontmatter, body)

    missing_gate = run_workctl(
        tmp_path,
        "plan",
        "artifact-state",
        "--artifact-id",
        "A-001",
        "--state",
        stronger_state,
        "--evidence-ref",
        "evidence:isolation",
        "--evidence-sha256",
        "b" * 64,
        "--expected-revision",
        "1",
        check=False,
    )
    assert missing_gate.returncode == 2
    assert "CONFIRMATION_BINDING_MISMATCH" in missing_gate.stderr

    run_workctl(
        tmp_path,
        "plan",
        "artifact-state",
        "--artifact-id",
        "A-001",
        "--state",
        stronger_state,
        "--confirmation",
        "C-RECOVERY",
        "--evidence-ref",
        "evidence:isolation",
        "--evidence-sha256",
        "b" * 64,
        "--expected-revision",
        "1",
    )
    direct_finalize = run_workctl(
        tmp_path,
        "plan",
        "finalize-artifact",
        "--artifact-id",
        "A-001",
        "--task-id",
        "T-001",
        "--confirmation",
        "C-RECOVERY",
        "--evidence-ref",
        "evidence:final",
        "--evidence-sha256",
        "c" * 64,
        "--expected-revision",
        "2",
        check=False,
    )
    assert direct_finalize.returncode == 2
    assert f"A-001 {stronger_state} -> final" in direct_finalize.stderr

    run_workctl(
        tmp_path,
        "plan",
        "artifact-state",
        "--artifact-id",
        "A-001",
        "--state",
        "suspect",
        "--confirmation",
        "C-RECOVERY",
        "--evidence-ref",
        "evidence:released",
        "--evidence-sha256",
        "d" * 64,
        "--expected-revision",
        "2",
    )
    finalized = run_workctl(
        tmp_path,
        "plan",
        "finalize-artifact",
        "--artifact-id",
        "A-001",
        "--task-id",
        "T-001",
        "--confirmation",
        "C-RECOVERY",
        "--evidence-ref",
        "evidence:final",
        "--evidence-sha256",
        "e" * 64,
        "--expected-revision",
        "3",
    )

    assert "ARTIFACT_FINALIZED A-001 revision=4" in finalized.stdout


def test_suspect_finalize_requires_declared_recovery_owner(tmp_path: Path) -> None:
    """An in-progress unrelated task cannot clear another task's suspect output."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-RECOVERY",
                "description": "Artifact recovery",
                "status": "accepted",
                "ref": "user:recovery",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    frontmatter["tasks"] = [
        {"id": "T-001", "description": "Unrelated task", "status": "in_progress"}
    ]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "suspect"}]
    frontmatter["route"]["confirmation_gate"] = "C-RECOVERY"
    write_plan(tmp_path, frontmatter, body)

    result = run_workctl(
        tmp_path,
        "plan",
        "finalize-artifact",
        "--artifact-id",
        "A-001",
        "--task-id",
        "T-001",
        "--confirmation",
        "C-RECOVERY",
        "--evidence-ref",
        "evidence:final",
        "--evidence-sha256",
        "f" * 64,
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "ARTIFACT_RECOVERY_OWNERSHIP_REQUIRED" in result.stderr


def test_generic_patch_cannot_rebind_strong_artifact_state_gate(tmp_path: Path) -> None:
    """Artifact state evidence and recovery binding change only via dedicated commands."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-RECOVERY",
                "description": "Recovery",
                "status": "accepted",
                "ref": "user:recovery",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
            {
                "id": "C-OTHER",
                "description": "Other",
                "status": "accepted",
                "ref": "user:other",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["artifacts"] = [
        {
            "id": "A-001",
            "path": "out.txt",
            "status": "quarantined",
            "state_confirmation_id": "C-RECOVERY",
            "state_evidence_ref": "evidence:isolation",
            "state_evidence_sha256": "a" * 64,
        }
    ]
    frontmatter["route"]["confirmation_gate"] = "C-OTHER"
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "artifact-rebind.yaml"
    patch_path.write_text(
        f"""\
artifacts:
  - id: A-001
    path: out.txt
    status: quarantined
    state_confirmation_id: C-OTHER
    state_evidence_ref: evidence:rewritten
    state_evidence_sha256: {"b" * 64}
""",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-OTHER",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "ARTIFACT_ENTRY_REQUIRES_DEDICATED_COMMAND: A-001" in result.stderr


def test_log_append_is_append_only(tmp_path: Path) -> None:
    init_plan(tmp_path)

    run_workctl(
        tmp_path,
        "log",
        "append",
        "--kind",
        "note",
        "--message",
        "first",
        "--expected-revision",
        "1",
    )
    run_workctl(
        tmp_path,
        "log",
        "append",
        "--kind",
        "note",
        "--message",
        "second",
        "--expected-revision",
        "1",
    )

    log_path = tmp_path / ".logs" / "PLAN-20260723-001.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["message"] == "first"
    assert json.loads(lines[1])["message"] == "second"


def test_authority_state_unmanaged_empty_allows_governed_init(tmp_path: Path) -> None:
    """No Plan is unmanaged until init creates schema-v3 governed metadata."""
    before = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    assert before["authority_state"] == "UNMANAGED_EMPTY"

    init_plan(tmp_path)

    after = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)
    assert after["authority_state"] == "GOVERNED_ACTIVE"
    assert after["candidates"][0]["classification"] == "CONFIRMED_AUTHORITY"
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_docs_plan_designated_by_agents_requires_migration(tmp_path: Path) -> None:
    """A rule-designated legacy Plan is confirmed authority, not a filename guess."""
    docs_plan = tmp_path / "docs" / "Plan.md"
    write_markdown_plan(docs_plan, legacy_frontmatter("PLAN-20260722-001"))
    (tmp_path / "AGENTS.md").write_text(
        "`docs/Plan.md` is the authoritative execution Plan and must be updated.\n",
        encoding="utf-8",
    )

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)

    assert report["authority_state"] == "MIGRATION_REQUIRED"
    assert report["candidates"][0]["classification"] == "CONFIRMED_AUTHORITY"
    assert "project-rule-explicit" in report["candidates"][0]["signals"]


def test_phase_plan_and_next_step_text_do_not_trigger_authority(tmp_path: Path) -> None:
    """Plan-like words alone do not create execution authority."""
    (tmp_path / "Plan.md").write_text(
        "# Phase design\n\nTechnical design evidence and archive notes.\n\n下一步：讨论接口。\n",
        encoding="utf-8",
    )
    for number in range(20):
        path = tmp_path / "docs" / f"phase-plan-{number}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Batch plan\n\n下一步：保留证据。\n", encoding="utf-8")

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)

    assert report["authority_state"] == "UNMANAGED_EMPTY"
    assert report["candidates"][0]["classification"] == "NON_AUTHORITY"


def test_likely_authority_requires_human_review(tmp_path: Path) -> None:
    """A self-claim plus control signals is reviewable but not auto-confirmed."""
    (tmp_path / "Plan.md").write_text(
        "# Current execution plan\n\n"
        "Target, phase, task queue, confirmation gate, and next step.\n",
        encoding="utf-8",
    )

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)

    assert report["authority_state"] == "AUTHORITY_REVIEW_REQUIRED"
    assert report["candidates"][0]["classification"] == "LIKELY_AUTHORITY"


def test_agent_candidate_classification_normalizes_relative_path(tmp_path: Path) -> None:
    """Explicit semantic input remains effective with a dotted relative path."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "Plan.md").write_text("# Candidate\n", encoding="utf-8")

    report = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "authority",
            "inspect",
            "--candidate",
            "./docs/Plan.md=CONFIRMED_AUTHORITY",
        ).stdout
    )

    assert report["authority_state"] == "MIGRATION_REQUIRED"
    assert report["candidates"][0]["classification"] == "CONFIRMED_AUTHORITY"
    assert "agent-classification" in report["candidates"][0]["signals"]


def test_legacy_active_plan_requires_registration(tmp_path: Path) -> None:
    """A schema-v1 indexed Plan cannot execute before authority registration."""
    write_legacy_active(tmp_path)

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "17",
        check=False,
    )

    assert report["authority_state"] == "AUTHORITY_REGISTRATION_REQUIRED"
    assert blocked.returncode == 2
    assert "AUTHORITY_BLOCKED: AUTHORITY_REGISTRATION_REQUIRED" in blocked.stderr


def test_schema_validate_rejects_malformed_authority_source(tmp_path: Path) -> None:
    """Candidate schema validation deeply checks lineage entry shape."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["authority"]["sources"] = [{"path": "../outside.md"}]
    write_plan(tmp_path, frontmatter, body)

    result = run_workctl(tmp_path, "plan", "schema-validate", check=False)

    assert result.returncode == 1
    assert "authority.sources[0].path must be a project-relative path" in result.stderr
    assert "authority.sources[0].role must be a supported source role" in result.stderr
    assert "authority.sources[0].sha256 must be a SHA256 digest" in result.stderr
    assert "authority.sources[0].archive_path must be a project-relative path" in result.stderr


def test_schema_validate_is_distinct_from_full_lineage_validation(tmp_path: Path) -> None:
    """A structurally valid candidate still fails full validation without lineage files."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-MIGRATION-BASELINE",
                "description": "Migration baseline",
                "status": "accepted",
                "ref": "user:approved",
                "accepted_at": "2026-07-25T00:00:00+00:00",
                "evidence_sha256": "1" * 64,
            }
        ]
    }
    frontmatter["authority"] = {
        "model": "single-active",
        "state": "governed",
        "canonical_plan_id": "PLAN-20260723-001",
        "migration_id": "MIG-20260724-001",
        "sources": [
            {
                "path": "docs/Plan.md",
                "role": "merged-source",
                "classification": "CONFIRMED_AUTHORITY",
                "sha256": "0" * 64,
                "revision": 1,
                "archive_path": ("_Plan/archive/MIG-20260724-001/legacy/docs/Plan.md"),
            }
        ],
        "confirmations": {"baseline": "C-MIGRATION-BASELINE"},
    }
    write_plan(tmp_path, frontmatter, body)

    schema = run_workctl(tmp_path, "plan", "schema-validate")
    full = run_workctl(tmp_path, "plan", "validate", check=False)

    assert "PLAN_SCHEMA_VALID" in schema.stdout
    assert full.returncode == 1
    assert "authority archive missing" in full.stderr
    assert "authority source pointer missing" in full.stderr


def test_active_legacy_and_agents_docs_plan_require_reconciliation(tmp_path: Path) -> None:
    """The PharmaceuticalGroup-shaped fixture freezes work for reconciliation."""
    write_legacy_active(tmp_path)
    docs_plan = tmp_path / "docs" / "Plan.md"
    write_markdown_plan(docs_plan, legacy_frontmatter("PLAN-20260722-001"))
    (tmp_path / "AGENTS.md").write_text(
        "`docs/Plan.md` is the authoritative execution Plan and must be read and updated.\n",
        encoding="utf-8",
    )

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)
    blocked = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--status",
        "active",
        "--expected-revision",
        "17",
        check=False,
    )

    assert report["authority_state"] == "RECONCILIATION_REQUIRED"
    assert blocked.returncode == 2
    assert "AUTHORITY_BLOCKED: RECONCILIATION_REQUIRED" in blocked.stderr


def test_reconcile_requires_separate_agents_confirmation_and_shows_diff(
    tmp_path: Path,
) -> None:
    """AGENTS routing has a reviewable diff and an independent confirmation gate."""
    manifest_path = write_reconciliation_fixture(tmp_path, include_agents_rewrite=True)

    dry_run = bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )
    blocked = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert "AGENTS.md.proposed" in dry_run["agents_diff"]
    assert dry_run["confirmations_required"] == [
        "C-MIGRATION-BASELINE",
        "C-AGENTS-REWRITE",
    ]
    assert blocked.returncode == 2
    assert "MANIFEST_CONFIRMATION_REQUIRED: agents_rewrite" in blocked.stderr


def test_reconcile_confirmation_digest_rejects_changed_prepared_plan(tmp_path: Path) -> None:
    """An accepted proposal digest cannot authorize later target edits."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )
    prepared = tmp_path / "prepared.md"
    prepared.write_text(
        prepared.read_text(encoding="utf-8") + "\nChanged after confirmation.\n",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert result.returncode == 2
    assert "CONFIRMATION_EVIDENCE_MISMATCH: baseline" in result.stderr
    assert not (tmp_path / "_Plan" / ".migrations").exists()


def test_reconcile_requires_all_confirmed_and_likely_sources(tmp_path: Path) -> None:
    """A manifest cannot silently omit the indexed or reviewable authority."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"] = [
        source for source in manifest["sources"] if source["path"] != "docs/Plan.md"
    ]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    assert result.returncode == 2
    assert "UNRESOLVED_AUTHORITY_CANDIDATES: docs/Plan.md" in result.stderr


def test_reconcile_cannot_omit_indexed_active_plan(tmp_path: Path) -> None:
    """The currently indexed Plan is always a required migration source."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"] = [
        source for source in manifest["sources"] if source["path"] != "_Plan/PLAN-20260723-001.md"
    ]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    assert result.returncode == 2
    assert "MISSING_MIGRATION_SOURCES: _Plan/PLAN-20260723-001.md" in result.stderr


def test_reconcile_archives_both_sources_and_activates_index_last(tmp_path: Path) -> None:
    """A confirmed merge produces archives, pointers, lineage, and one active Plan."""
    manifest_path = write_reconciliation_fixture(tmp_path, include_agents_rewrite=True)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=True,
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
    )
    report = json.loads(run_workctl(tmp_path, "plan", "status").stdout)
    canonical = tmp_path / "_Plan" / "PLAN-20260724-002.md"
    _, raw_frontmatter, _ = canonical.read_text(encoding="utf-8").split("---\n", 2)
    frontmatter = yaml.safe_load(raw_frontmatter)

    assert "MIGRATION_COMMITTED MIG-20260724-001" in result.stdout
    assert report["authority_state"] == "GOVERNED_ACTIVE"
    assert report["plan_id"] == "PLAN-20260724-002"
    assert "WORK_GOVERNANCE_NON_AUTHORITY_POINTER" in (tmp_path / "docs" / "Plan.md").read_text(
        encoding="utf-8"
    )
    assert "(_Plan/PLAN-20260724-002.md)" not in (tmp_path / "docs" / "Plan.md").read_text(
        encoding="utf-8"
    )
    assert "(../_Plan/PLAN-20260724-002.md)" in (tmp_path / "docs" / "Plan.md").read_text(
        encoding="utf-8"
    )
    assert "WORK_GOVERNANCE_NON_AUTHORITY_POINTER" in (
        tmp_path / "_Plan" / "PLAN-20260723-001.md"
    ).read_text(encoding="utf-8")
    assert (
        tmp_path / "_Plan" / "archive" / "MIG-20260724-001" / "legacy" / "docs" / "Plan.md"
    ).is_file()
    assert (
        tmp_path / "_Plan" / "archive" / "MIG-20260724-001" / "unmerged" / "PLAN-20260723-001.md"
    ).is_file()
    assert frontmatter["authority"]["canonical_plan_id"] == "PLAN-20260724-002"
    assert frontmatter["schema_version"] == 3
    assert frontmatter["delivery"]["status"] == "pending"
    assert frontmatter["activation"]["status"] == "deferred"
    assert len(frontmatter["authority"]["sources"]) == 2
    assert "`_Plan/PLAN-20260724-002.md`" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_source_drift_prevents_migration_activation(tmp_path: Path) -> None:
    """Any post-review source change aborts before a journal or index activation."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )
    (tmp_path / "docs" / "Plan.md").write_text("changed after review\n", encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )
    index = yaml.safe_load((tmp_path / "_Plan" / "index.yaml").read_text(encoding="utf-8"))

    assert result.returncode == 2
    assert "SOURCE_DRIFT: docs/Plan.md" in result.stderr
    assert index["active_plan_id"] == "PLAN-20260723-001"
    assert not (tmp_path / "_Plan" / ".migrations").exists()


def test_interrupted_migration_requires_recovery_then_converges(tmp_path: Path) -> None:
    """A journaled interruption is recoverable without leaving dual authority."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )

    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "pointer:docs/Plan.md"},
    )
    during = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    recovered = run_workctl(tmp_path, "plan", "reconcile", "recover")
    after = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)

    assert interrupted.returncode == 2
    assert "SIMULATED_MIGRATION_INTERRUPT" in interrupted.stderr
    assert during["authority_state"] == "MIGRATION_RECOVERY_REQUIRED"
    assert "MIGRATION_COMMITTED" in recovered.stdout
    assert after["authority_state"] == "GOVERNED_ACTIVE"


def test_recovery_rechecks_recorded_git_baseline(tmp_path: Path) -> None:
    """Recovery freezes when the journal's reviewed Git baseline no longer matches."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "archive:docs/Plan.md"},
    )
    assert interrupted.returncode == 2
    journal_path = tmp_path / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    journal = yaml.safe_load(journal_path.read_text(encoding="utf-8"))
    journal["git_baseline"] = "0" * 40
    journal_path.write_text(yaml.safe_dump(journal, sort_keys=False), encoding="utf-8")

    recovered = run_workctl(tmp_path, "plan", "reconcile", "recover", check=False)

    assert recovered.returncode == 2
    assert "GIT_BASELINE_MISMATCH" in recovered.stderr


def test_recovery_rechecks_staged_agents_replacement_hash(tmp_path: Path) -> None:
    """Recovery cannot write an AGENTS replacement whose staged bytes drifted."""
    manifest_path = write_reconciliation_fixture(tmp_path, include_agents_rewrite=True)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=True,
    )
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "pointer:_Plan/PLAN-20260723-001.md"},
    )
    assert interrupted.returncode == 2
    staged_agents = (
        tmp_path
        / "_Plan"
        / ".migrations"
        / "MIG-20260724-001"
        / "staging"
        / "agents-replacement.md"
    )
    staged_agents.write_text("tampered\n", encoding="utf-8")

    recovered = run_workctl(tmp_path, "plan", "reconcile", "recover", check=False)

    assert recovered.returncode == 2
    assert "STAGED_AGENTS_REWRITE_HASH_MISMATCH" in recovered.stderr


def test_post_activation_interrupt_keeps_journal_recoverable(tmp_path: Path) -> None:
    """The journal stays non-committed until post-activation validation succeeds."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )

    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "index-activation"},
    )
    journal_path = tmp_path / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    journal = yaml.safe_load(journal_path.read_text(encoding="utf-8"))
    report = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)

    assert interrupted.returncode == 2
    assert journal["status"] == "applying"
    assert report["authority_state"] == "MIGRATION_RECOVERY_REQUIRED"
    assert run_workctl(tmp_path, "plan", "reconcile", "recover").returncode == 0


def test_lineage_pointer_reverted_and_agents_redirected_reopens_reconciliation(
    tmp_path: Path,
) -> None:
    """A historical path cannot silently reclaim execution authority."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )
    run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
    )
    archive = tmp_path / "_Plan" / "archive" / "MIG-20260724-001" / "legacy" / "docs" / "Plan.md"
    (tmp_path / "docs" / "Plan.md").write_bytes(archive.read_bytes())
    (tmp_path / "AGENTS.md").write_text(
        "`docs/Plan.md` is the authoritative current execution Plan and must be updated.\n",
        encoding="utf-8",
    )

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)

    assert report["authority_state"] == "RECONCILIATION_REQUIRED"


def test_committed_source_reversion_requires_authority_review(tmp_path: Path) -> None:
    """A restored execution Plan is reviewed instead of auto-overwritten."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )
    run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(manifest_path),
    )
    archive = tmp_path / "_Plan" / "archive" / "MIG-20260724-001" / "legacy" / "docs" / "Plan.md"
    source = tmp_path / "docs" / "Plan.md"
    source.write_bytes(archive.read_bytes())

    before = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    recovered = run_workctl(tmp_path, "plan", "reconcile", "recover", check=False)

    assert before["authority_state"] == "AUTHORITY_REVIEW_REQUIRED"
    assert recovered.returncode == 2
    assert "NO_INCOMPLETE_MIGRATION" in recovered.stderr


def test_rollover_dry_run_is_stable_and_requires_fixed_confirmation(
    tmp_path: Path,
) -> None:
    """A terminal rollover exposes one stable digest and its fixed gate."""
    manifest_path = write_rollover_fixture(tmp_path)

    first = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "rollover",
            "apply",
            "--manifest",
            str(manifest_path),
            "--dry-run",
        ).stdout
    )
    second = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "rollover",
            "apply",
            "--manifest",
            str(manifest_path),
            "--dry-run",
        ).stdout
    )

    assert first == second
    assert first["confirmations_required"] == ["C-PLAN-ROLLOVER"]
    assert first["source_plan"]["plan_id"] == "PLAN-20260723-001"
    assert first["target_plan"]["plan_id"] == "PLAN-20260727-001"


def test_rollover_requires_complete_terminal_closeout_ready_source(
    tmp_path: Path,
) -> None:
    """Non-complete and closeout-blocked predecessors cannot roll over."""
    init_plan(tmp_path)
    source = plan_path(tmp_path)
    prepared = tmp_path / "successor.md"
    write_markdown_plan(prepared, rollover_target_frontmatter("PLAN-20260727-001"))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "rollover_id": "ROL-20260727-001",
        "source_plan": {
            "path": "_Plan/PLAN-20260723-001.md",
            "plan_id": "PLAN-20260723-001",
            "revision": 1,
            "sha256": sha256_path(source),
        },
        "index_baseline": {
            "active_plan_id": "PLAN-20260723-001",
            "sha256": sha256_path(tmp_path / "_Plan" / "index.yaml"),
        },
        "target_plan": {
            "prepared_file": "successor.md",
            "plan_id": "PLAN-20260727-001",
            "revision": 1,
            "sha256": sha256_path(prepared),
        },
    }
    manifest_path = tmp_path / "rollover.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    non_complete = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )
    frontmatter, body = read_plan(tmp_path)
    frontmatter["status"] = "complete"
    frontmatter["route"] = {
        "route_status": "terminal",
        "slice_status": "complete",
        "next_phase": "none",
        "validation_standard": "Fresh evidence.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {"route_status": "terminal", "next_step": "none"}
    write_plan(tmp_path, frontmatter, body)
    manifest["source_plan"]["sha256"] = sha256_path(source)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    closeout_blocked = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    assert non_complete.returncode == 2
    assert "ROLLOVER_SOURCE_NOT_COMPLETE" in non_complete.stderr
    assert closeout_blocked.returncode == 2
    assert "ROLLOVER_SOURCE_NOT_CLOSEOUT_READY" in closeout_blocked.stderr


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("revision", 99, "ROLLOVER_SOURCE_REVISION_MISMATCH"),
        ("sha256", "0" * 64, "ROLLOVER_SOURCE_HASH_MISMATCH"),
    ],
)
def test_rollover_rejects_source_contract_drift(
    tmp_path: Path,
    field: str,
    value: object,
    expected_error: str,
) -> None:
    """Source revision and hash are immutable proposal inputs."""
    manifest_path = write_rollover_fixture(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["source_plan"][field] = value
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    assert result.returncode == 2
    assert expected_error in result.stderr


def test_rollover_rejects_index_drift_and_target_conflict(tmp_path: Path) -> None:
    """Index drift and an existing successor abort before journal creation."""
    index_case = tmp_path / "index-case"
    index_case.mkdir()
    manifest_path = write_rollover_fixture(index_case)
    bind_rollover_confirmation(index_case, manifest_path)
    index_path = index_case / "_Plan" / "index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    index["review_marker"] = "drift"
    index_path.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")

    index_drift = run_workctl(
        index_case,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert index_drift.returncode == 2
    assert "INDEX_BASELINE_DRIFT" in index_drift.stderr
    assert not (index_case / "_Plan" / ".rollovers").exists()

    target_case = tmp_path / "target-case"
    target_case.mkdir()
    manifest_path = write_rollover_fixture(target_case)
    bind_rollover_confirmation(target_case, manifest_path)
    target = target_case / "_Plan" / "PLAN-20260727-001.md"
    target.write_text("conflict\n", encoding="utf-8")
    target_conflict = run_workctl(
        target_case,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert target_conflict.returncode == 2
    assert "TARGET_PLAN_CONFLICT" in target_conflict.stderr
    assert not (target_case / "_Plan" / ".rollovers").exists()


def test_rollover_rejects_stale_project_rule_routing(tmp_path: Path) -> None:
    """An explicit predecessor path cannot become competing authority after activation."""
    manifest_path = write_rollover_fixture(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        "`_Plan/PLAN-20260723-001.md` is the authoritative current execution Plan.\n",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    assert result.returncode == 2
    assert "ROLLOVER_PROJECT_RULE_REWRITE_REQUIRED" in result.stderr
    assert not (tmp_path / "_Plan" / ".rollovers").exists()


def test_rollover_requires_digest_bound_confirmation(tmp_path: Path) -> None:
    """Apply rejects a missing or mismatched C-PLAN-ROLLOVER record."""
    manifest_path = write_rollover_fixture(tmp_path)
    missing = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )
    bind_rollover_confirmation(tmp_path, manifest_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["confirmations"]["rollover"]["evidence_sha256"] = "0" * 64
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    mismatch = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert missing.returncode == 2
    assert "MANIFEST_CONFIRMATION_REQUIRED: rollover" in missing.stderr
    assert mismatch.returncode == 2
    assert "CONFIRMATION_EVIDENCE_MISMATCH: rollover" in mismatch.stderr
    assert not (tmp_path / "_Plan" / ".rollovers").exists()


def test_rollover_preserves_predecessor_and_activates_successor_last(
    tmp_path: Path,
) -> None:
    """A confirmed rollover preserves bytes, lineage, history, and one authority."""
    manifest_path = write_rollover_fixture(tmp_path)
    bind_rollover_confirmation(tmp_path, manifest_path)
    predecessor = plan_path(tmp_path)
    predecessor_sha256 = sha256_path(predecessor)

    result = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
    )
    status = json.loads(run_workctl(tmp_path, "plan", "status").stdout)
    index = yaml.safe_load((tmp_path / "_Plan" / "index.yaml").read_text(encoding="utf-8"))
    successor = tmp_path / "_Plan" / "PLAN-20260727-001.md"
    _, raw_frontmatter, _ = successor.read_text(encoding="utf-8").split("---\n", 2)
    successor_frontmatter = yaml.safe_load(raw_frontmatter)
    predecessor_candidate = next(
        candidate
        for candidate in status["authority_candidates"]
        if candidate["path"] == "_Plan/PLAN-20260723-001.md"
    )

    assert "ROLLOVER_COMMITTED ROL-20260727-001" in result.stdout
    assert sha256_path(predecessor) == predecessor_sha256
    assert index["active_plan_id"] == "PLAN-20260727-001"
    assert {item["id"] for item in index["plans"]} == {
        "PLAN-20260723-001",
        "PLAN-20260727-001",
    }
    assert successor_frontmatter["authority"]["predecessor"] == {
        "path": "_Plan/PLAN-20260723-001.md",
        "plan_id": "PLAN-20260723-001",
        "revision": 1,
        "sha256": predecessor_sha256,
    }
    assert predecessor_candidate["classification"] == "NON_AUTHORITY"
    assert "completed-plan" in predecessor_candidate["signals"]
    assert status["authority_state"] == "GOVERNED_ACTIVE"
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_interrupted_rollover_freezes_work_then_recovers_idempotently(
    tmp_path: Path,
) -> None:
    """Target-written/index-not-activated interruption requires named recovery."""
    manifest_path = write_rollover_fixture(tmp_path)
    bind_rollover_confirmation(tmp_path, manifest_path)

    interrupted = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    during = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    blocked = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--expected-revision",
        "1",
        "--status",
        "active",
        check=False,
    )
    recovered = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260727-001",
    )
    repeated = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260727-001",
    )
    after = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)

    assert interrupted.returncode == 2
    assert "SIMULATED_MIGRATION_INTERRUPT: rollover-target-plan" in interrupted.stderr
    assert during["authority_state"] == "MIGRATION_RECOVERY_REQUIRED"
    assert blocked.returncode == 2
    assert "AUTHORITY_BLOCKED: MIGRATION_RECOVERY_REQUIRED" in blocked.stderr
    assert "ROLLOVER_COMMITTED" in recovered.stdout
    assert "ROLLOVER_ALREADY_COMMITTED" in repeated.stdout
    assert after["authority_state"] == "GOVERNED_ACTIVE"


def test_rollover_recovery_rechecks_source_and_target_hashes(tmp_path: Path) -> None:
    """Recovery refuses predecessor drift and conflicting target bytes."""
    source_case = tmp_path / "source-case"
    source_case.mkdir()
    manifest_path = write_rollover_fixture(source_case)
    bind_rollover_confirmation(source_case, manifest_path)
    interrupted = run_workctl(
        source_case,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    assert interrupted.returncode == 2
    plan_path(source_case).write_text("source drift\n", encoding="utf-8")
    source_drift = run_workctl(
        source_case,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260727-001",
        check=False,
    )
    assert source_drift.returncode == 2
    assert "ROLLOVER_SOURCE_DRIFT" in source_drift.stderr

    target_case = tmp_path / "target-case"
    target_case.mkdir()
    manifest_path = write_rollover_fixture(target_case)
    bind_rollover_confirmation(target_case, manifest_path)
    interrupted = run_workctl(
        target_case,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    assert interrupted.returncode == 2
    target = target_case / "_Plan" / "PLAN-20260727-001.md"
    target.write_text("target drift\n", encoding="utf-8")
    target_drift = run_workctl(
        target_case,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260727-001",
        check=False,
    )

    assert target_drift.returncode == 2
    assert "TARGET_PLAN_CONFLICT" in target_drift.stderr


def test_rollover_recovery_rejects_internally_inconsistent_journal(
    tmp_path: Path,
) -> None:
    """Recovery cross-binds the journal, staged Plan, index, and proposal."""
    manifest_path = write_rollover_fixture(tmp_path)
    bind_rollover_confirmation(tmp_path, manifest_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    assert interrupted.returncode == 2
    journal_path = tmp_path / "_Plan" / ".rollovers" / "ROL-20260727-001.yaml"
    journal = yaml.safe_load(journal_path.read_text(encoding="utf-8"))
    journal["proposal_sha256"] = "0" * 64
    journal_path.write_text(yaml.safe_dump(journal, sort_keys=False), encoding="utf-8")

    recovered = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260727-001",
        check=False,
    )

    assert recovered.returncode == 2
    assert "ROLLOVER_PROPOSAL_HASH_MISMATCH" in recovered.stderr


def test_rollover_recovery_rederives_target_from_prepared_contract(
    tmp_path: Path,
) -> None:
    """Updating self-reported target hashes cannot authorize changed target bytes."""
    manifest_path = write_rollover_fixture(tmp_path)
    bind_rollover_confirmation(tmp_path, manifest_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    assert interrupted.returncode == 2
    journal_path = tmp_path / "_Plan" / ".rollovers" / "ROL-20260727-001.yaml"
    journal = yaml.safe_load(journal_path.read_text(encoding="utf-8"))
    staged_target = tmp_path / journal["staged_plan"]
    materialized_target = tmp_path / journal["target_path"]
    changed_bytes = staged_target.read_bytes() + b"\nChanged outside the prepared contract.\n"
    staged_target.write_bytes(changed_bytes)
    materialized_target.write_bytes(changed_bytes)
    journal["target_sha256"] = sha256_path(staged_target)
    journal_path.write_text(yaml.safe_dump(journal, sort_keys=False), encoding="utf-8")

    recovered = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260727-001",
        check=False,
    )

    assert recovered.returncode == 2
    assert "STAGED_ROLLOVER_TARGET_CONTRACT_MISMATCH" in recovered.stderr


def test_incomplete_rollover_blocks_reconciliation_before_any_write(
    tmp_path: Path,
) -> None:
    """A second structural transaction cannot start during rollover recovery."""
    rollover_manifest = write_rollover_fixture(tmp_path)
    bind_rollover_confirmation(tmp_path, rollover_manifest)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(rollover_manifest),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    assert interrupted.returncode == 2

    source = plan_path(tmp_path)
    source_bytes = source.read_bytes()
    prepared = tmp_path / "reconciled-successor.md"
    write_markdown_plan(prepared, canonical_frontmatter("PLAN-20260727-002"))
    reconcile_manifest: dict[str, Any] = {
        "schema_version": 1,
        "migration_id": "MIG-20260727-001",
        "target_plan": {"prepared_file": prepared.name},
        "sources": [
            {
                "path": "_Plan/PLAN-20260723-001.md",
                "role": "unmerged-source",
                "classification": "CONFIRMED_AUTHORITY",
                "sha256": sha256_path(source),
                "revision": 1,
            }
        ],
        "confirmations": {},
    }
    reconcile_manifest_path = tmp_path / "reconcile-during-rollover.yaml"
    reconcile_manifest_path.write_text(
        yaml.safe_dump(reconcile_manifest, sort_keys=False),
        encoding="utf-8",
    )
    dry_run = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "reconcile",
            "apply",
            "--manifest",
            str(reconcile_manifest_path),
            "--dry-run",
        ).stdout
    )
    reconcile_manifest["confirmations"]["baseline"] = {
        "id": "C-MIGRATION-BASELINE",
        "ref": "user:reconcile",
        "accepted_at": "2026-07-27T00:02:00+00:00",
        "evidence_sha256": dry_run["proposal_sha256"],
    }
    reconcile_manifest_path.write_text(
        yaml.safe_dump(reconcile_manifest, sort_keys=False),
        encoding="utf-8",
    )

    blocked = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(reconcile_manifest_path),
        check=False,
    )

    assert blocked.returncode == 2
    assert "MIGRATION_RECOVERY_REQUIRED" in blocked.stderr
    assert source.read_bytes() == source_bytes
    assert not (tmp_path / "_Plan" / ".migrations").exists()
    assert (
        run_workctl(
            tmp_path,
            "plan",
            "rollover",
            "recover",
            "--rollover-id",
            "ROL-20260727-001",
        ).returncode
        == 0
    )


def test_rollover_rejects_symlinked_staging_root_before_outside_write(
    tmp_path: Path,
) -> None:
    """A symlinked transaction root fails before creating project-external files."""
    manifest_path = write_rollover_fixture(tmp_path)
    bind_rollover_confirmation(tmp_path, manifest_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    rollovers = tmp_path / "_Plan" / ".rollovers"
    rollovers.symlink_to(outside, target_is_directory=True)

    result = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert result.returncode == 2
    assert "ROLLOVER_PATH_SYMLINK: _Plan/.rollovers" in result.stderr
    assert list(outside.iterdir()) == []


def test_closeout_requires_terminal_route_and_complete_work(tmp_path: Path) -> None:
    """Complete is available only after route, work, artifacts, and handoff close."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["obligations"] = [
        {"id": "O-001", "description": "Obligation", "status": "verified"}
    ]
    frontmatter["tasks"] = [{"id": "T-001", "description": "Task", "status": "verified"}]
    frontmatter["validations"] = [
        {"id": "V-001", "description": "Validation", "status": "verified"}
    ]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "final"}]
    frontmatter["delivery"] = {
        "status": "complete",
        "boundary": "local-source-only",
        "evidence_ref": "git:verified-commit",
    }
    frontmatter["activation"] = {
        "status": "not_required",
        "current_ref": "not-applicable",
        "target_ref": "not-applicable",
        "decision_ref": "user:source-only-delivery",
    }
    frontmatter["route"] = {
        "route_status": "terminal",
        "slice_status": "complete",
        "next_phase": "none",
        "validation_standard": "All obligations have fresh evidence.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {"route_status": "terminal", "next_step": "none"}
    write_plan(tmp_path, frontmatter, body)

    assert run_workctl(tmp_path, "plan", "closeout-check").returncode == 0
    complete = run_workctl(
        tmp_path,
        "plan",
        "complete",
        "--expected-revision",
        "1",
    )
    frontmatter, _ = read_plan(tmp_path)

    assert "PLAN_COMPLETED revision=2" in complete.stdout
    assert frontmatter["status"] == "complete"


def test_pending_activation_blocks_terminal_and_no_next_claims(tmp_path: Path) -> None:
    """Local delivery completion cannot erase a pending live-activation decision."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-LIVE-SWITCH",
                "description": "Activate the candidate",
                "status": "pending",
            }
        ]
    }
    frontmatter["scope"]["exclude"] = [
        {
            "description": "Switch the live plugin.",
            "disposition": "pending_confirmation",
            "confirmation_id": "C-LIVE-SWITCH",
        }
    ]
    frontmatter["delivery"] = {
        "status": "complete",
        "boundary": "local-feature-commit",
        "evidence_ref": "git:local-commit",
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    frontmatter["route"] = {
        "route_status": "awaiting_confirmation",
        "slice_status": "validated",
        "next_phase": "Decide whether to activate the candidate.",
        "validation_standard": "Fresh-session discovery matches the candidate.",
        "confirmation_gate": "C-LIVE-SWITCH",
    }
    frontmatter["handoff"] = {
        "route_status": "awaiting_confirmation",
        "next_step": "Wait for C-LIVE-SWITCH.",
    }
    write_plan(tmp_path, frontmatter, body)

    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"
    closeout = run_workctl(tmp_path, "plan", "closeout-check", check=False)
    status = json.loads(run_workctl(tmp_path, "plan", "status").stdout)
    blockers = json.loads(closeout.stdout)["blockers"]

    assert closeout.returncode == 1
    assert "activation is pending_confirmation" in blockers
    assert any("scope exclusion is unresolved" in blocker for blocker in blockers)
    assert status["completion_claims"] == {
        "activation_authorized": False,
        "activation_confirmation_id": "C-LIVE-SWITCH",
        "delivery_declared_complete": True,
        "level": "local_delivery_complete",
        "local_delivery_complete": True,
        "no_required_next_step_allowed": False,
        "route_complete": False,
        "slice_confirmation_id": "C-LIVE-SWITCH",
        "slice_next_action_authorized": False,
        "slice_status": "validated",
    }
    assert status["activation"]["current_ref"] == "work-governance@old"
    assert status["activation"]["target_ref"] == "work-governance@candidate"


def test_schema_rejects_terminal_route_with_unresolved_activation(tmp_path: Path) -> None:
    """Schema-v3 terminal claims fail when activation or exclusions remain open."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-LIVE-SWITCH",
                "description": "Activate the candidate",
                "status": "pending",
            }
        ]
    }
    frontmatter["scope"]["exclude"] = [
        {
            "description": "Switch the live plugin.",
            "disposition": "pending_confirmation",
            "confirmation_id": "C-LIVE-SWITCH",
        }
    ]
    frontmatter["delivery"] = {
        "status": "complete",
        "boundary": "local-feature-commit",
        "evidence_ref": "git:local-commit",
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    frontmatter["route"] = {
        "route_status": "terminal",
        "slice_status": "validated",
        "next_phase": "none",
        "validation_standard": "Candidate tests pass.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {"route_status": "terminal", "next_step": "none"}
    write_plan(tmp_path, frontmatter, body)

    validation = run_workctl(tmp_path, "plan", "schema-validate", check=False)

    assert validation.returncode == 1
    assert "terminal route cannot retain unresolved activation" in validation.stderr
    assert "terminal route cannot retain unresolved scope exclusions" in validation.stderr


def test_schema_requires_structured_v3_exclusion_disposition(tmp_path: Path) -> None:
    """Schema-v3 exclusions cannot silently discard their future disposition."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["scope"]["exclude"] = ["Switch the live plugin."]
    write_plan(tmp_path, frontmatter, body)

    validation = run_workctl(tmp_path, "plan", "schema-validate", check=False)

    assert validation.returncode == 1
    assert "scope.exclude[0] must be a mapping for schema_version 3" in validation.stderr


def test_active_activation_requires_matching_refs_and_evidence(tmp_path: Path) -> None:
    """Activation cannot be declared active from an unverified target mismatch."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["activation"] = {
        "status": "active",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
    }
    write_plan(tmp_path, frontmatter, body)

    validation = run_workctl(tmp_path, "plan", "schema-validate", check=False)

    assert validation.returncode == 1
    assert "activation active requires current_ref to match target_ref" in validation.stderr
    assert "activation active requires runtime evidence" in validation.stderr


def test_schema_rejects_unverifiable_activation_evidence(tmp_path: Path) -> None:
    """A self-asserted target is not sufficient runtime activation evidence."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["activation"] = {
        "status": "active",
        "current_ref": "work-governance@candidate",
        "target_ref": "work-governance@candidate",
        "evidence": {
            "observed_ref": "work-governance@different",
            "source_ref": "claimed-by-controller",
            "checked_at": "",
            "sha256": "not-a-digest",
        },
    }
    write_plan(tmp_path, frontmatter, body)

    validation = run_workctl(tmp_path, "plan", "schema-validate", check=False)

    assert validation.returncode == 1
    assert "activation evidence observed_ref must match current_ref" in validation.stderr
    assert "activation evidence source_ref must be a typed reference" in validation.stderr
    assert "activation evidence requires checked_at" in validation.stderr
    assert "activation evidence requires a SHA256 digest" in validation.stderr


def test_activation_transition_rejects_wrong_confirmation(tmp_path: Path) -> None:
    """An unrelated accepted gate cannot authorize activation."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-LIVE-SWITCH",
                "description": "Activate candidate",
                "status": "accepted",
                "ref": "user:live",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
            {
                "id": "C-OTHER",
                "description": "Unrelated decision",
                "status": "accepted",
                "ref": "user:other",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "activation.yaml"
    patch_path.write_text(
        """\
activation:
  status: in_progress
  current_ref: work-governance@old
  target_ref: work-governance@candidate
  confirmation_id: C-LIVE-SWITCH
""",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-OTHER",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "CONFIRMATION_BINDING_MISMATCH" in result.stderr


def test_activation_transition_cannot_rebind_its_confirmation(tmp_path: Path) -> None:
    """A patch cannot replace an activation gate with an easier accepted gate."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {"id": "C-LIVE-SWITCH", "description": "Live", "status": "pending"},
            {
                "id": "C-OTHER",
                "description": "Other",
                "status": "accepted",
                "ref": "user:other",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "activation-rebind.yaml"
    patch_path.write_text(
        """\
activation:
  status: in_progress
  current_ref: work-governance@old
  target_ref: work-governance@candidate
  confirmation_id: C-OTHER
""",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-OTHER",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "ACTIVATION_CONFIRMATION_ID_IMMUTABLE" in result.stderr


@pytest.mark.parametrize(
    ("tasks_yaml", "error"),
    [
        (
            """\
tasks:
  - id: T-001
    description: Task
    status: verified
""",
            "TASK_STATUS_REQUIRES_DEDICATED_COMMAND: T-001",
        ),
        ("tasks: []\n", "TASK_REMOVAL_FORBIDDEN: T-001"),
    ],
)
def test_generic_plan_patch_cannot_bypass_task_commands(
    tmp_path: Path,
    tasks_yaml: str,
    error: str,
) -> None:
    """Task completion and removal cannot be smuggled through Plan revision."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-STRUCTURE",
                "description": "Structure",
                "status": "accepted",
                "ref": "user:structure",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    frontmatter["tasks"] = [{"id": "T-001", "description": "Task", "status": "pending"}]
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "tasks.yaml"
    patch_path.write_text(tasks_yaml, encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-STRUCTURE",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert error in result.stderr


def test_generic_plan_patch_cannot_rebind_task_gate_or_dependencies(tmp_path: Path) -> None:
    """A structural gate cannot make a live task authorize itself."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {"id": "C-LIVE-SWITCH", "description": "Live", "status": "pending"},
            {
                "id": "C-CORRECTION",
                "description": "Correction",
                "status": "accepted",
                "ref": "user:correction",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["tasks"] = [
        {"id": "T-001", "description": "Prerequisite", "status": "verified"},
        {
            "id": "T-002",
            "description": "Switch live",
            "status": "pending",
            "depends_on": ["T-001"],
            "requires_confirmation": "C-LIVE-SWITCH",
        },
    ]
    frontmatter["route"]["confirmation_gate"] = "C-CORRECTION"
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "task-rebind.yaml"
    patch_path.write_text(
        """\
tasks:
  - id: T-001
    description: Prerequisite
    status: verified
  - id: T-002
    description: Switch live
    status: pending
    depends_on: []
    requires_confirmation: C-CORRECTION
""",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-CORRECTION",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "TASK_CONFIRMATION_ID_IMMUTABLE: T-002" in result.stderr


@pytest.mark.parametrize(
    ("patch_text", "expected_error"),
    [
        (
            """\
route:
  route_status: active
  slice_status: initialized
  next_phase: Define the demand contract.
  validation_standard: Every obligation has direct fresh evidence.
  confirmation_gate: C-OTHER
""",
            "CONFIRMATION_BINDING_MISMATCH",
        ),
        (
            """\
delivery:
  status: complete
  boundary: local-feature-commit
  evidence_ref: git:local-commit
""",
            "DELIVERY_COMPLETE_REQUIRES_DEDICATED_COMMAND",
        ),
        (
            """\
obligations:
  - id: O-001
    description: Obligation
    status: verified
""",
            "OBLIGATIONS_STATUS_REQUIRES_DEDICATED_COMMAND: O-001",
        ),
    ],
)
def test_closeout_affecting_patch_uses_current_slice_gate(
    tmp_path: Path,
    patch_text: str,
    expected_error: str,
) -> None:
    """An unrelated accepted gate cannot alter slice authority or self-certify closeout."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-SLICE",
                "description": "Current slice",
                "status": "accepted",
                "ref": "user:slice",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
            {
                "id": "C-OTHER",
                "description": "Other",
                "status": "accepted",
                "ref": "user:other",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["obligations"] = [{"id": "O-001", "description": "Obligation", "status": "pending"}]
    frontmatter["route"]["confirmation_gate"] = "C-SLICE"
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "unrelated-gate.yaml"
    patch_path.write_text(patch_text, encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-OTHER",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert expected_error in result.stderr


def test_activation_metadata_update_uses_current_slice_gate(tmp_path: Path) -> None:
    """A target/reference rewrite cannot use an unrelated accepted gate."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {"id": "C-LIVE-SWITCH", "description": "Live", "status": "pending"},
            {
                "id": "C-SLICE",
                "description": "Current slice",
                "status": "accepted",
                "ref": "user:slice",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
            {
                "id": "C-OTHER",
                "description": "Other",
                "status": "accepted",
                "ref": "user:other",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate-1",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    frontmatter["route"]["confirmation_gate"] = "C-SLICE"
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "activation-metadata.yaml"
    patch_path.write_text(
        """\
activation:
  status: pending_confirmation
  current_ref: work-governance@old
  target_ref: work-governance@candidate-2
  confirmation_id: C-LIVE-SWITCH
""",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-OTHER",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "CONFIRMATION_BINDING_MISMATCH" in result.stderr


def test_accepted_activation_target_cannot_drift_under_slice_gate(tmp_path: Path) -> None:
    """Once accepted, the activation object may change only under its own gate."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-LIVE-SWITCH",
                "description": "Live",
                "status": "accepted",
                "ref": "user:live",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
            {
                "id": "C-SLICE",
                "description": "Current slice",
                "status": "accepted",
                "ref": "user:slice",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@accepted-target",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    frontmatter["route"]["confirmation_gate"] = "C-SLICE"
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "accepted-target-drift.yaml"
    patch_path.write_text(
        """\
activation:
  status: pending_confirmation
  current_ref: work-governance@old
  target_ref: work-governance@different-target
  confirmation_id: C-LIVE-SWITCH
""",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-SLICE",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "CONFIRMATION_BINDING_MISMATCH" in result.stderr


def test_resolved_exclusion_cannot_be_removed_or_rewritten(tmp_path: Path) -> None:
    """Resolved no-go scope remains stable under unrelated structural revision."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-STRUCTURE",
                "description": "Structure",
                "status": "accepted",
                "ref": "user:structure",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    frontmatter["scope"]["exclude"] = [
        {
            "description": "Never push.",
            "disposition": "forbidden",
            "resolution_ref": "user:original-no-go",
        }
    ]
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "scope-remove.yaml"
    patch_path.write_text("scope:\n  include: []\n  exclude: []\n", encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-STRUCTURE",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "SCOPE_EXCLUSION_REMOVAL_FORBIDDEN: Never push." in result.stderr


def test_new_resolved_exclusion_requires_its_own_confirmation_reference(
    tmp_path: Path,
) -> None:
    """A typed string alone cannot fabricate a newly resolved scope decision."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-STRUCTURE",
                "description": "Structure",
                "status": "accepted",
                "ref": "user:structure",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "scope-add.yaml"
    patch_path.write_text(
        """\
scope:
  include: []
  exclude:
    - description: Never publish.
      disposition: forbidden
      confirmation_id: C-STRUCTURE
      resolution_ref: user:someone-else
""",
        encoding="utf-8",
    )

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-STRUCTURE",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "EXCLUSION_RESOLUTION_REF_MISMATCH: Never publish." in result.stderr


def test_generic_plan_patch_cannot_modify_confirmations(tmp_path: Path) -> None:
    """Confirmation decisions are accepted only through the dedicated command."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-STRUCTURE",
                "description": "Structure",
                "status": "accepted",
                "ref": "user:structure",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "confirmations.yaml"
    patch_path.write_text("confirmations:\n  required: []\n", encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-STRUCTURE",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "UNSUPPORTED_PLAN_PATCH_FIELDS: confirmations" in result.stderr


def test_generic_plan_patch_cannot_downgrade_schema(tmp_path: Path) -> None:
    """Legacy compatibility cannot be used to disable schema-v3 closeout gates."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-STRUCTURE",
                "description": "Structure",
                "status": "accepted",
                "ref": "user:structure",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    write_plan(tmp_path, frontmatter, body)
    patch_path = tmp_path / "schema-downgrade.yaml"
    patch_path.write_text("schema_version: 2\n", encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-STRUCTURE",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "UNSUPPORTED_PLAN_PATCH_FIELDS: schema_version" in result.stderr


def test_dedicated_evidence_commands_record_digest_bound_transitions(
    tmp_path: Path,
) -> None:
    """Verified/final states retain the evidence reference and reviewed digest."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-SLICE",
                "description": "Current slice",
                "status": "accepted",
                "ref": "user:slice",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    frontmatter["obligations"] = [{"id": "O-001", "description": "Obligation", "status": "pending"}]
    frontmatter["validations"] = [{"id": "V-001", "description": "Validation", "status": "pending"}]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "suspect"}]
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Recover artifact",
            "status": "in_progress",
            "resolves_artifacts": ["A-001"],
        }
    ]
    frontmatter["route"]["confirmation_gate"] = "C-SLICE"
    write_plan(tmp_path, frontmatter, body)

    run_workctl(
        tmp_path,
        "plan",
        "verify-entry",
        "--field",
        "obligations",
        "--entry-id",
        "O-001",
        "--confirmation",
        "C-SLICE",
        "--evidence-ref",
        "evidence:obligation-check",
        "--evidence-sha256",
        "a" * 64,
        "--expected-revision",
        "1",
    )
    run_workctl(
        tmp_path,
        "plan",
        "verify-entry",
        "--field",
        "validations",
        "--entry-id",
        "V-001",
        "--confirmation",
        "C-SLICE",
        "--evidence-ref",
        "evidence:validation-check",
        "--evidence-sha256",
        "b" * 64,
        "--expected-revision",
        "2",
    )
    run_workctl(
        tmp_path,
        "plan",
        "finalize-artifact",
        "--artifact-id",
        "A-001",
        "--task-id",
        "T-001",
        "--confirmation",
        "C-SLICE",
        "--evidence-ref",
        "evidence:artifact-check",
        "--evidence-sha256",
        "c" * 64,
        "--expected-revision",
        "3",
    )

    revised, _ = read_plan(tmp_path)

    assert revised["obligations"][0]["evidence_sha256"] == "a" * 64
    assert revised["validations"][0]["evidence_ref"] == "evidence:validation-check"
    assert revised["artifacts"][0]["status"] == "final"
    assert revised["revision"] == 4


def test_declined_activation_path_can_reach_terminal_closeout(tmp_path: Path) -> None:
    """A declined live switch remains a first-class, internally consistent route."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {"id": "C-LIVE-SWITCH", "description": "Activate candidate", "status": "pending"},
            {
                "id": "C-DELIVERY",
                "description": "Accept local delivery evidence",
                "status": "accepted",
                "ref": "user:delivery",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
        ]
    }
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Activate candidate",
            "status": "pending",
            "requires_confirmation": "C-LIVE-SWITCH",
            "completion_scope": "route",
        }
    ]
    frontmatter["scope"]["exclude"] = [
        {
            "description": "Switch the live plugin.",
            "disposition": "pending_confirmation",
            "confirmation_id": "C-LIVE-SWITCH",
        }
    ]
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    frontmatter["route"]["confirmation_gate"] = "C-DELIVERY"
    write_plan(tmp_path, frontmatter, body)

    delivery_patch = tmp_path / "delivery-complete.yaml"
    delivery_patch.write_text(
        """\
delivery:
  status: in_progress
  boundary: local-feature-commit
  evidence_ref: project:delivery-in-progress
""",
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(delivery_patch),
        "--confirmation",
        "C-DELIVERY",
        "--expected-revision",
        "1",
    )
    run_workctl(
        tmp_path,
        "plan",
        "delivery-complete",
        "--confirmation",
        "C-DELIVERY",
        "--evidence-ref",
        "git:local-commit",
        "--evidence-sha256",
        "a" * 64,
        "--expected-revision",
        "2",
    )
    route_patch = tmp_path / "route-to-live-decision.yaml"
    route_patch.write_text(
        """\
route:
  route_status: active
  slice_status: initialized
  next_phase: Decide whether to activate the candidate.
  validation_standard: Every obligation has direct fresh evidence.
  confirmation_gate: C-LIVE-SWITCH
""",
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(route_patch),
        "--confirmation",
        "C-DELIVERY",
        "--expected-revision",
        "3",
    )
    decision = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-LIVE-SWITCH",
        "--decision",
        "declined",
        "--ref",
        "user:declined-live-switch",
        "--expected-revision",
        "4",
    )
    run_workctl(
        tmp_path,
        "task",
        "skip",
        "--task-id",
        "T-001",
        "--expected-revision",
        "5",
    )
    patch_path = tmp_path / "declined-closeout.yaml"
    patch_path.write_text(
        """\
scope:
  include: []
  exclude:
    - description: Switch the live plugin.
      disposition: not_required
      confirmation_id: C-LIVE-SWITCH
      resolution_ref: user:declined-live-switch
activation:
  status: declined
  current_ref: work-governance@old
  target_ref: work-governance@candidate
  confirmation_id: C-LIVE-SWITCH
  decision_ref: user:declined-live-switch
route:
  route_status: terminal
  slice_status: complete
  next_phase: none
  validation_standard: Declined route is internally consistent.
  confirmation_gate: none
handoff:
  route_status: terminal
  next_step: none
""",
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(patch_path),
        "--confirmation",
        "C-LIVE-SWITCH",
        "--expected-revision",
        "6",
    )

    closeout = json.loads(run_workctl(tmp_path, "plan", "closeout-check").stdout)
    status = json.loads(run_workctl(tmp_path, "plan", "status").stdout)

    assert "CONFIRMATION_DECIDED C-LIVE-SWITCH declined" in decision.stdout
    assert closeout == {"blockers": [], "ready": True}
    assert status["completion_claims"]["route_complete"] is True
    assert status["completion_claims"]["no_required_next_step_allowed"] is True


def test_accepted_activation_with_runtime_evidence_reaches_terminal_closeout(
    tmp_path: Path,
) -> None:
    """The accepted active route is reachable only after delivery and runtime evidence."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-DELIVERY",
                "description": "Accept local delivery evidence",
                "status": "accepted",
                "ref": "user:delivery",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            },
            {
                "id": "C-LIVE-SWITCH",
                "description": "Activate candidate",
                "status": "accepted",
                "ref": "user:live",
                "accepted_at": "2026-07-25T00:01:00+00:00",
            },
        ]
    }
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Activate candidate",
            "status": "pending",
            "requires_confirmation": "C-LIVE-SWITCH",
            "completion_scope": "route",
        }
    ]
    frontmatter["scope"]["exclude"] = [
        {
            "description": "Switch the live plugin.",
            "disposition": "pending_confirmation",
            "confirmation_id": "C-LIVE-SWITCH",
        }
    ]
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    frontmatter["route"]["confirmation_gate"] = "C-DELIVERY"
    write_plan(tmp_path, frontmatter, body)
    delivery_patch = tmp_path / "accepted-delivery-in-progress.yaml"
    delivery_patch.write_text(
        """\
delivery:
  status: in_progress
  boundary: local-feature-commit
  evidence_ref: project:delivery-in-progress
""",
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(delivery_patch),
        "--confirmation",
        "C-DELIVERY",
        "--expected-revision",
        "1",
    )
    run_workctl(
        tmp_path,
        "plan",
        "delivery-complete",
        "--confirmation",
        "C-DELIVERY",
        "--evidence-ref",
        "git:local-commit",
        "--evidence-sha256",
        "d" * 64,
        "--expected-revision",
        "2",
    )
    route_patch = tmp_path / "accepted-route-to-live.yaml"
    route_patch.write_text(
        """\
route:
  route_status: active
  slice_status: delivery-complete
  next_phase: Activate the accepted candidate.
  validation_standard: Fresh runtime evidence matches the target.
  confirmation_gate: C-LIVE-SWITCH
""",
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(route_patch),
        "--confirmation",
        "C-DELIVERY",
        "--expected-revision",
        "3",
    )
    run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "4",
    )
    run_workctl(
        tmp_path,
        "task",
        "verify",
        "--task-id",
        "T-001",
        "--expected-revision",
        "5",
    )
    activation_patch = tmp_path / "accepted-activation-closeout.yaml"
    activation_patch.write_text(
        """\
scope:
  include: []
  exclude:
    - description: Switch the live plugin.
      disposition: completed
      confirmation_id: C-LIVE-SWITCH
      resolution_ref: user:live
activation:
  status: active
  current_ref: work-governance@candidate
  target_ref: work-governance@candidate
  confirmation_id: C-LIVE-SWITCH
  evidence:
    observed_ref: work-governance@candidate
    source_ref: codex-plugin-list:work-governance
    checked_at: '2026-07-25T00:02:00+00:00'
    sha256: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
route:
  route_status: terminal
  slice_status: complete
  next_phase: none
  validation_standard: Runtime evidence matches the accepted target.
  confirmation_gate: none
handoff:
  route_status: terminal
  next_step: none
""",
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--patch-file",
        str(activation_patch),
        "--confirmation",
        "C-LIVE-SWITCH",
        "--expected-revision",
        "6",
    )

    closeout = json.loads(run_workctl(tmp_path, "plan", "closeout-check").stdout)
    status = json.loads(run_workctl(tmp_path, "plan", "status").stdout)

    assert closeout == {"blockers": [], "ready": True}
    assert status["activation"]["status"] == "active"
    assert status["completion_claims"]["activation_authorized"] is True
    assert status["completion_claims"]["route_complete"] is True


def test_accepted_gate_authorizes_action_but_does_not_complete_activation(tmp_path: Path) -> None:
    """Accepted authority permits the next action without closing the route."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["confirmations"] = {
        "required": [
            {
                "id": "C-LIVE-SWITCH",
                "description": "Activate the candidate",
                "status": "accepted",
                "ref": "user:confirmed",
                "accepted_at": "2026-07-25T00:00:00+00:00",
            }
        ]
    }
    frontmatter["scope"]["exclude"] = [
        {
            "description": "Switch the live plugin.",
            "disposition": "pending_confirmation",
            "confirmation_id": "C-LIVE-SWITCH",
        }
    ]
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    frontmatter["route"] = {
        "route_status": "awaiting_confirmation",
        "slice_status": "validated",
        "next_phase": "Activate the approved candidate.",
        "validation_standard": "Fresh-session discovery matches the candidate.",
        "confirmation_gate": "C-LIVE-SWITCH",
    }
    frontmatter["handoff"] = {
        "route_status": "awaiting_confirmation",
        "next_step": "Activate the approved candidate.",
    }
    write_plan(tmp_path, frontmatter, body)

    validation = run_workctl(tmp_path, "plan", "schema-validate")
    status = json.loads(run_workctl(tmp_path, "plan", "status").stdout)

    assert "PLAN_SCHEMA_VALID" in validation.stdout
    assert status["completion_claims"]["slice_next_action_authorized"] is True
    assert status["completion_claims"]["route_complete"] is False
    assert status["activation"]["status"] == "pending_confirmation"


def test_closeout_includes_full_plan_validation(tmp_path: Path) -> None:
    """Terminal-looking work cannot close with an invalid index contract."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["route"] = {
        "route_status": "terminal",
        "slice_status": "complete",
        "next_phase": "none",
        "validation_standard": "Schema and authority are valid.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {"route_status": "terminal", "next_step": "none"}
    write_plan(tmp_path, frontmatter, body)
    index_path = tmp_path / "_Plan" / "index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    index["plans"][0]["status"] = "active"
    index_path.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")

    closeout = run_workctl(tmp_path, "plan", "closeout-check", check=False)

    assert closeout.returncode == 1
    payload = json.loads(closeout.stdout)
    assert any(
        "index must not duplicate mutable Plan fields" in item for item in payload["blockers"]
    )
