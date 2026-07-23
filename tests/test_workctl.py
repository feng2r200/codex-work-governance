from __future__ import annotations

import json
import os
import runpy
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


def run_workctl(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
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

    run_workctl(tmp_path, "task", "verify", "--task-id", "T-001", "--expected-revision", "1")
    run_workctl(tmp_path, "task", "start", "--task-id", "T-002", "--expected-revision", "2")
    frontmatter, _ = read_plan(tmp_path)
    assert frontmatter["tasks"][1]["status"] == "in_progress"
    assert frontmatter["revision"] == 3


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
    frontmatter["scope"]["exclude"] = ["Push to a remote repository."]
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
    run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--confirmation",
        "C-PUBLISH",
        "--include",
        "Publish the repository.",
        "--remove-exclude",
        "Push to a remote repository.",
        "--status",
        "switching",
        "--expected-revision",
        "2",
    )

    frontmatter, _ = read_plan(tmp_path)
    assert frontmatter["scope"]["include"][-1] == "Publish the repository."
    assert "Push to a remote repository." not in frontmatter["scope"]["exclude"]
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
                "ref": "user",
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


def test_exclusive_lock_blocks_writer_until_release(tmp_path: Path) -> None:
    init_plan(tmp_path)
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
