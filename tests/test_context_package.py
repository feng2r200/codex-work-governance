from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from test_schema_v5 import STRICT_CONTROLLER_ENV, init_minimal_v5_goal, run_without_receipt
from test_workctl import REPO_ROOT, SCRIPT, file_tree_snapshot, run_workctl

SCRIPT_ROOT = REPO_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

context_pack_module: Any = importlib.import_module("workctl_modules.context_pack")
build_context_package = context_pack_module.build_context_package


def load_json_output(value: str) -> dict[str, Any]:
    """Parse one JSON command response as a mutable mapping."""
    return cast(dict[str, Any], json.loads(value))


def write_context_sources(tmp_path: Path) -> Path:
    """Create a small mixed-role context manifest for command tests."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "README.md").write_text(
        "Implementation notes for the current slice.\n",
        encoding="utf-8",
    )
    (docs / "review.md").write_text("Review-only context.\n", encoding="utf-8")
    (docs / "implementation.md").write_text(
        "Implementation detail with enough text to exercise truncation.\n",
        encoding="utf-8",
    )
    manifest = {
        "summary": "Prepare a role-scoped implementation package.",
        "files": [
            {
                "path": "README.md",
                "roles": ["implement", "check"],
                "reason": "Shared task intent.",
            },
            {
                "path": "docs/review.md",
                "role": "review",
                "reason": "Reviewer-only prompt.",
            },
            {
                "path": "docs/implementation.md",
                "role": "implement",
                "label": "implementation detail",
            },
        ],
        "notes": ["Keep the package explicit and bounded."],
    }
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_context_build_is_read_only_and_does_not_create_plan_authority(
    tmp_path: Path,
) -> None:
    """Context packages support No-Plan exploration without creating authority."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    manifest_path = write_context_sources(tmp_path)
    before = file_tree_snapshot(tmp_path / ".work-governance")

    package = load_json_output(
        run_without_receipt(
            tmp_path,
            "context",
            "build",
            "--role",
            "implement",
            "--manifest",
            manifest_path.as_posix(),
            "--task",
            "T-001",
            "--max-file-bytes",
            "24",
        ).stdout
    )

    files = cast(list[dict[str, object]], package["files"])
    assert package["status"] == "CONTEXT_PACKAGE_BUILT"
    assert package["role"] == "implement"
    assert package["task_id"] == "T-001"
    assert "active_plan_id" not in package
    assert [item["path"] for item in files] == ["README.md", "docs/implementation.md"]
    assert files[0]["reason"] == "Shared task intent."
    assert files[0]["included"] is True
    assert files[0]["truncated"] is True
    assert files[0]["sha256"] == hashlib.sha256(
        (tmp_path / "README.md").read_bytes()
    ).hexdigest()
    assert package["skipped_entries"] == 1
    assert len(cast(str, package["package_sha256"])) == 64
    package_again = load_json_output(
        run_without_receipt(
            tmp_path,
            "context",
            "build",
            "--role",
            "implement",
            "--manifest",
            manifest_path.as_posix(),
            "--task",
            "T-001",
            "--max-file-bytes",
            "24",
        ).stdout
    )
    assert package_again["package_sha256"] == package["package_sha256"]
    assert not (tmp_path / ".work-governance" / "_Plan").exists()
    assert file_tree_snapshot(tmp_path / ".work-governance") == before


def test_context_build_uses_total_budget_and_omits_binary_files(tmp_path: Path) -> None:
    """Packages report total-budget truncation and binary omission explicitly."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / "first.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "second.txt").write_text("xyz", encoding="utf-8")
    (tmp_path / "binary.dat").write_bytes(b"\x00abcdef")
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": [
                    {"path": "binary.dat"},
                    {"path": "first.txt"},
                    {"path": "second.txt"},
                ]
            }
        ),
        encoding="utf-8",
    )

    package = load_json_output(
        run_without_receipt(
            tmp_path,
            "context",
            "build",
            "--role",
            "implement",
            "--manifest",
            manifest_path.as_posix(),
            "--max-file-bytes",
            "10",
            "--max-total-bytes",
            "5",
        ).stdout
    )

    files = cast(list[dict[str, object]], package["files"])
    assert files[0]["included"] is False
    assert files[0]["omitted_reason"] == "binary_or_non_utf8"
    assert files[1]["content"] == "abcd"
    assert files[1]["content_bytes"] == 4
    assert files[2]["content"] == "x"
    assert files[2]["content_bytes"] == 1
    assert files[2]["truncation_reason"] == "total_limit"
    warnings = cast(list[str], package["warnings"])
    assert "CONTEXT_FILE_OMITTED_BINARY_OR_NON_UTF8: binary.dat" in warnings
    assert "CONTEXT_FILE_TRUNCATED: second.txt" in warnings
    assert package["content_budget"] == {
        "max_file_bytes": 10,
        "max_total_bytes": 5,
        "total_content_bytes": 5,
    }


def test_context_build_truncates_to_a_valid_utf8_boundary(tmp_path: Path) -> None:
    """Byte budgets must not make misleading UTF-8 content byte metadata."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / "utf8.txt").write_text("a雪b", encoding="utf-8")
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(json.dumps({"files": ["utf8.txt"]}), encoding="utf-8")

    package = load_json_output(
        run_without_receipt(
            tmp_path,
            "context",
            "build",
            "--role",
            "implement",
            "--manifest",
            manifest_path.as_posix(),
            "--max-file-bytes",
            "3",
        ).stdout
    )

    files = cast(list[dict[str, object]], package["files"])
    assert files[0]["content"] == "a"
    assert files[0]["content_bytes"] == 1
    assert files[0]["truncated"] is True
    assert files[0]["truncation_reason"] == "file_limit"


def test_context_build_rejects_symlink_sources(tmp_path: Path) -> None:
    """Context packages do not follow project-local symlink sources."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / "target.txt").write_text("target\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "target.txt")
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(json.dumps({"files": ["link.txt"]}), encoding="utf-8")

    result = run_without_receipt(
        tmp_path,
        "context",
        "build",
        "--role",
        "implement",
        "--manifest",
        manifest_path.as_posix(),
    )

    assert result.returncode == 2
    assert "CONTEXT_PATH_SYMLINK" in result.stderr


def test_context_build_rejects_known_secret_source_paths(tmp_path: Path) -> None:
    """Known credential files are rejected before any package content is emitted."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / ".env").write_text("API_TOKEN=super-secret-token\n", encoding="utf-8")
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(json.dumps({"files": [".env"]}), encoding="utf-8")

    result = run_without_receipt(
        tmp_path,
        "context",
        "build",
        "--role",
        "implement",
        "--manifest",
        manifest_path.as_posix(),
    )

    assert result.returncode == 2
    assert "CONTEXT_SECRET_PATH_REJECTED: .env" in result.stderr
    assert "super-secret-token" not in result.stdout
    assert "super-secret-token" not in result.stderr


def test_context_build_redacts_secret_patterns_before_emitting_content(
    tmp_path: Path,
) -> None:
    """Source files that are not secret paths still redact credential-like values."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / "settings.txt").write_text(
        "API_TOKEN=super-secret-token-12345\n"
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
        "safe_value=visible\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(json.dumps({"files": ["settings.txt"]}), encoding="utf-8")

    package = load_json_output(
        run_without_receipt(
            tmp_path,
            "context",
            "build",
            "--role",
            "implement",
            "--manifest",
            manifest_path.as_posix(),
            "--max-file-bytes",
            "256",
        ).stdout
    )

    files = cast(list[dict[str, object]], package["files"])
    content = cast(str, files[0]["content"])
    assert "super-secret-token-12345" not in content
    assert "abcdefghijklmnopqrstuvwxyz" not in content
    assert "safe_value=visible" in content
    assert content.count("[REDACTED]") >= 2
    assert files[0]["redacted"] is True
    warnings = cast(list[str], package["warnings"])
    assert "CONTEXT_CONTENT_REDACTED: settings.txt" in warnings


def test_context_build_redacts_truncated_token_prefixes(tmp_path: Path) -> None:
    """Budget-truncated standalone token prefixes are still redacted."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / "settings.txt").write_text("prefix sk-ab trailing\n", encoding="utf-8")
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(json.dumps({"files": ["settings.txt"]}), encoding="utf-8")

    package = load_json_output(
        run_without_receipt(
            tmp_path,
            "context",
            "build",
            "--role",
            "implement",
            "--manifest",
            manifest_path.as_posix(),
            "--max-file-bytes",
            "12",
        ).stdout
    )

    files = cast(list[dict[str, object]], package["files"])
    content = cast(str, files[0]["content"])
    assert "sk-" not in content
    assert "[RED" in content
    assert cast(int, files[0]["content_bytes"]) <= 12
    assert files[0]["redacted"] is True


def test_context_lint_validates_manifest_without_emitting_content(tmp_path: Path) -> None:
    """Lint checks paths and roles without reading package content into stdout."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / "settings.txt").write_text(
        "API_TOKEN=super-secret-token-12345\nsafe_value=visible\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "path": "settings.txt",
                        "role": "implement",
                        "reason": "Implementation input.",
                    }
                ],
                "notes": ["Only validate the manifest shape."],
            }
        ),
        encoding="utf-8",
    )
    before = file_tree_snapshot(tmp_path / ".work-governance")

    result = run_without_receipt(
        tmp_path,
        "context",
        "lint",
        "--role",
        "implement",
        "--manifest",
        manifest_path.as_posix(),
    )

    payload = load_json_output(result.stdout)
    files = cast(list[dict[str, object]], payload["files"])
    assert result.returncode == 0
    assert payload["status"] == "CONTEXT_MANIFEST_VALID"
    assert payload["roles"] == ["implement"]
    assert files == [
        {
            "path": "settings.txt",
            "roles": ["implement"],
            "reason": "Implementation input.",
        }
    ]
    assert "content" not in files[0]
    assert "super-secret-token-12345" not in result.stdout
    assert "safe_value=visible" not in result.stdout
    assert result.stderr == ""
    assert file_tree_snapshot(tmp_path / ".work-governance") == before


def test_context_lint_rejects_known_secret_paths_without_leaking_values(
    tmp_path: Path,
) -> None:
    """Lint rejects credential paths before emitting source content."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    (tmp_path / ".env").write_text("API_TOKEN=super-secret-token\n", encoding="utf-8")
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(json.dumps({"files": [".env"]}), encoding="utf-8")

    result = run_without_receipt(
        tmp_path,
        "context",
        "lint",
        "--manifest",
        manifest_path.as_posix(),
    )

    assert result.returncode == 2
    assert "CONTEXT_SECRET_PATH_REJECTED: .env" in result.stderr
    assert "super-secret-token" not in result.stdout
    assert "super-secret-token" not in result.stderr


def test_context_package_streams_source_files_before_content_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source files are not loaded through Path.read_bytes before budget slicing."""
    source = tmp_path / "large.txt"
    source.write_text("abcdef", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def reject_source_read_bytes(path: Path) -> bytes:
        if path == source:
            raise AssertionError("source files must not use Path.read_bytes")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_source_read_bytes)

    package = build_context_package(
        tmp_path,
        {"files": ["large.txt"]},
        role="implement",
        task_id=None,
        summary=None,
        max_file_bytes=3,
        max_total_bytes=3,
        manifest_sha256="0" * 64,
    )

    files = cast(list[dict[str, object]], package["files"])
    assert files[0]["content"] == "abc"
    assert files[0]["content_bytes"] == 3
    assert files[0]["truncated"] is True
    assert files[0]["sha256"] == hashlib.sha256(b"abcdef").hexdigest()


def test_context_build_annotates_current_plan_without_mutating_it(tmp_path: Path) -> None:
    """An active Plan is context metadata only; the command remains read-only."""
    init_minimal_v5_goal(tmp_path, "PLAN-20260817-201")
    manifest_path = write_context_sources(tmp_path)
    before = file_tree_snapshot(tmp_path / ".work-governance")

    package = load_json_output(
        run_without_receipt(
            tmp_path,
            "context",
            "build",
            "--role",
            "check",
            "--manifest",
            manifest_path.as_posix(),
        ).stdout
    )

    files = cast(list[dict[str, object]], package["files"])
    assert package["active_plan_id"] == "PLAN-20260817-201"
    assert [item["path"] for item in files] == ["README.md"]
    assert file_tree_snapshot(tmp_path / ".work-governance") == before


def test_context_build_rejects_project_escape_paths(tmp_path: Path) -> None:
    """Context manifests cannot make a package read outside the project root."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    manifest_path = tmp_path / "context.json"
    manifest_path.write_text(
        json.dumps({"files": [{"path": "../outside.txt", "reason": "escape"}]}),
        encoding="utf-8",
    )

    result = run_without_receipt(
        tmp_path,
        "context",
        "build",
        "--role",
        "implement",
        "--manifest",
        manifest_path.as_posix(),
    )

    assert result.returncode == 2
    assert "PATH_OUTSIDE_PROJECT" in result.stderr


def test_context_help_exposes_the_role_scoped_read_only_surface(tmp_path: Path) -> None:
    """Public help lists the implemented context package workflow."""
    context_help = load_json_output(run_workctl(tmp_path, "help", "context").stdout)
    parser_help = subprocess.run(
        [sys.executable, str(SCRIPT), "context", "build", "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert "context build --role implement|check|review|truth --manifest PATH|--stdin" in (
        context_help["commands"]
    )
    assert "context lint --manifest PATH|--stdin [--role ROLE]" in context_help["commands"]
    assert "read-only" in cast(str, context_help["note"])
    assert parser_help.returncode == 0
    assert "--role {check,implement,review,truth}" in parser_help.stdout
