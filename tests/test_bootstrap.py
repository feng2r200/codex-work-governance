"""SessionStart bootstrap contract tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance"
HOOK = PLUGIN_ROOT / "hooks" / "session_start.py"
HOOKS_CONFIG = PLUGIN_ROOT / "hooks" / "hooks.json"
WORKCTL = PLUGIN_ROOT / "scripts" / "workctl.py"


def install_fake_uv(directory: Path, log_path: Path) -> Path:
    """Install a UV-shaped wrapper that executes the controller in the test venv."""
    wrapper = directory / "uv"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        + """
import json
import os
import subprocess
import sys

arguments = sys.argv[1:]
with open(os.environ["WORK_GOVERNANCE_TEST_UV_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(arguments) + "\\n")
script_index = arguments.index("--script")
controller = arguments[script_index + 1]
controller_arguments = arguments[script_index + 2:]
if (
    os.environ.get("WORK_GOVERNANCE_TEST_FAKE_UV_FAIL_PREWARM") == "1"
    and controller_arguments == ["--help"]
):
    raise SystemExit(17)
result = subprocess.run(
    [sys.executable, controller, *controller_arguments],
    env=os.environ,
    check=False,
)
raise SystemExit(result.returncode)
""",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    log_path.touch()
    return wrapper


def run_hook(
    project: Path,
    fake_bin: Path,
    log_path: Path,
    *,
    payload: dict[str, Any] | None = None,
    plugin_root: Path = PLUGIN_ROOT,
    environment_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the standard-library hook with one deterministic SessionStart input."""
    hook_input = payload or {
        "session_id": "test-session",
        "cwd": str(project),
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    environment = dict(os.environ)
    environment["PLUGIN_ROOT"] = str(plugin_root)
    environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
    environment["WORK_GOVERNANCE_TEST_UV_LOG"] = str(log_path)
    environment.update(environment_overrides or {})
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(hook_input),
        text=True,
        capture_output=True,
        env=environment,
        check=True,
    )
    output = json.loads(result.stdout)
    assert result.stderr == ""
    return cast(dict[str, Any], output)


def read_uv_commands(log_path: Path) -> list[list[str]]:
    """Read fake UV invocations."""
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]


def adopt_legacy(project: Path) -> dict[str, Any]:
    """Bind the reviewed bootstrap fixture to its physical project root."""
    status_result = subprocess.run(
        [sys.executable, str(WORKCTL), "layout", "status"],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )
    status = json.loads(status_result.stdout)
    legacy = status["legacy"]
    adopt_result = subprocess.run(
        [
            sys.executable,
            str(WORKCTL),
            "layout",
            "adopt",
            "--expected-manifest-sha256",
            legacy["manifest_sha256"],
            "--expected-active-plan-id",
            legacy["active_plan_id"],
            "--ref",
            "user:test-bootstrap-adoption",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(adopt_result.stdout)
    assert payload["status"] == "LEGACY_ADOPTED"
    return cast(dict[str, Any], payload)


def write_migratable_legacy(project: Path) -> None:
    """Create a minimal governed legacy Plan that still requires explicit adoption."""
    plan_id = "PLAN-20260723-001"
    plan_root = project / "_Plan"
    plan_root.mkdir()
    frontmatter = {
        "schema_version": 2,
        "plan_id": plan_id,
        "title": "Bootstrap migration fixture",
        "status": "active",
        "mode": "autonomous",
        "revision": 1,
        "created_at": "2026-07-23T00:00:00+00:00",
        "updated_at": "2026-07-23T00:00:00+00:00",
        "scope": {"include": ["Continue safely."], "exclude": []},
        "confirmations": {"required": []},
        "obligations": [{"id": "O-001", "description": "Migrate.", "status": "pending"}],
        "tasks": [{"id": "T-001", "description": "Resume.", "status": "pending"}],
        "validations": [{"id": "V-001", "description": "Validate.", "status": "pending"}],
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
            "next_phase": "Resume.",
            "validation_standard": "Fresh evidence.",
            "confirmation_gate": "none",
        },
        "handoff": {"route_status": "active", "next_step": "Resume."},
    }
    plan = plan_root / f"{plan_id}.md"
    plan.write_text(
        f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n# Body\n",
        encoding="utf-8",
    )
    index = {
        "schema_version": 1,
        "active_plan_id": plan_id,
        "plans": [
            {
                "id": plan_id,
                "path": plan.name,
                "title": "Bootstrap migration fixture",
                "created_at": "2026-07-23T00:00:00+00:00",
            }
        ],
    }
    (plan_root / "index.yaml").write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")
    (plan_root / "PLAN-20260720-999.md").write_text(
        "# Generated Work Governance pointer\n\n"
        "- Marker: `WORK_GOVERNANCE_NON_AUTHORITY_POINTER`\n"
        f"- Canonical Plan: [{plan_id}]({plan.name})\n",
        encoding="utf-8",
    )


def test_bootstrap_prewarms_then_runs_controller_offline(tmp_path: Path) -> None:
    """First load creates a No-Plan layout and a current exact-build receipt."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()

    output = run_hook(project, fake_bin, uv_log)

    governance = project / ".work-governance"
    receipt = json.loads((governance / "bootstrap-state.json").read_text(encoding="utf-8"))
    commands = read_uv_commands(uv_log)
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    context = output["hookSpecificOutput"]["additionalContext"]
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in context
    assert receipt["status"] == "READY"
    assert receipt["plugin_build"] == manifest["version"]
    assert receipt["layout_state"] == "LAYOUT_READY"
    assert (governance / "version.yaml").is_file()
    assert not (governance / "_Plan").exists()
    assert len(commands) == 4
    assert "--offline" not in commands[0]
    assert commands[0][-1] == "--help"
    for command in commands[1:]:
        assert "--offline" in command
        assert "--no-python-downloads" in command
        assert str(governance / "cache" / "uv") in command
    assert all("init" not in command for command in commands)
    assert not (project / "pyproject.toml").exists()


def test_prewarm_retry_keeps_prior_bootstrap_evidence_and_allows_adoption(
    tmp_path: Path,
) -> None:
    """A failed prewarm followed by classification cannot self-block adoption."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    write_migratable_legacy(project)

    prewarm_blocked = run_hook(
        project,
        fake_bin,
        uv_log,
        environment_overrides={"WORK_GOVERNANCE_TEST_FAKE_UV_FAIL_PREWARM": "1"},
    )
    classification_blocked = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "classification-retry",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )
    status = json.loads(
        subprocess.run(
            [sys.executable, str(WORKCTL), "layout", "status"],
            cwd=project,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
    )
    adoption = adopt_legacy(project)
    migrated = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "migration-after-history",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )
    evidence = list((project / ".work-governance" / "evidence" / "bootstrap").iterdir())

    assert (
        "CONTROLLER_PREWARM_FAILED" in (prewarm_blocked["hookSpecificOutput"]["additionalContext"])
    )
    assert (
        "LAYOUT_MIGRATION_NOT_READY"
        in (classification_blocked["hookSpecificOutput"]["additionalContext"])
    )
    assert status["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert status["legacy"]["classification"] == "AMBIGUOUS"
    assert adoption["status"] == "LEGACY_ADOPTED"
    assert (
        "WORK_GOVERNANCE_BOOTSTRAP READY" in (migrated["hookSpecificOutput"]["additionalContext"])
    )
    assert (project / ".work-governance" / "version.yaml").is_file()
    assert not (project / "_Plan").exists()
    assert len(evidence) == 3


@pytest.mark.parametrize("forgery", ["invalid-json", "symlink-current", "missing-receipt"])
def test_forged_prior_bootstrap_evidence_blocks_next_session(
    tmp_path: Path,
    forgery: str,
) -> None:
    """An unbound history-shaped file cannot be smuggled through bootstrap retry."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    write_migratable_legacy(project)
    run_hook(project, fake_bin, uv_log)
    governance = project / ".work-governance"
    receipt_path = governance / "bootstrap-state.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    current_evidence = project / receipt["evidence_ref"].removeprefix("evidence:")
    forged = governance / "evidence" / "bootstrap" / "20260727T000000.000000Z-999.json"
    if forgery == "invalid-json":
        forged.write_text("{}\n", encoding="utf-8")
    elif forgery == "symlink-current":
        forged.symlink_to(current_evidence.name)
    else:
        receipt_path.unlink()

    controller_status = json.loads(
        subprocess.run(
            [sys.executable, str(WORKCTL), "layout", "status"],
            cwd=project,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
    )

    blocked = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "forged-history",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )

    assert (
        "UNCOMMITTED_BOOTSTRAP_EVIDENCE_HISTORY_INVALID"
        in (blocked["hookSpecificOutput"]["additionalContext"])
    )
    assert controller_status["layout_state"] == "ENVIRONMENT_BLOCKED"
    assert not (project / ".work-governance" / "version.yaml").exists()
    assert (project / "_Plan").is_dir()


def test_session_start_bootstraps_only_the_nearest_linked_worktree(tmp_path: Path) -> None:
    """A nested SessionStart cwd creates governance only in its linked worktree."""
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Work Governance Test"],
        cwd=repository,
        check=True,
    )
    (repository / ".gitignore").write_text("/.worktree/\n", encoding="utf-8")
    (repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    linked = repository / ".worktree" / "feature"
    subprocess.run(
        [
            "git",
            "worktree",
            "add",
            "-q",
            "-b",
            "feature",
            str(linked),
            "HEAD",
        ],
        cwd=repository,
        check=True,
    )
    nested = linked / "nested"
    nested.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)

    output = run_hook(nested, fake_bin, uv_log)

    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in (output["hookSpecificOutput"]["additionalContext"])
    assert (linked / ".work-governance" / "version.yaml").is_file()
    assert not (repository / ".work-governance").exists()


def test_default_hook_config_is_stable_and_covers_every_session_source() -> None:
    """Use the default plugin hook path with one short stable command."""
    payload = json.loads(HOOKS_CONFIG.read_text(encoding="utf-8"))
    session = payload["hooks"]["SessionStart"]

    assert len(session) == 1
    assert session[0]["matcher"] == "startup|resume|clear|compact"
    assert session[0]["hooks"] == [
        {
            "type": "command",
            "command": "python3 ${PLUGIN_ROOT}/hooks/session_start.py",
            "statusMessage": "Checking Work Governance layout",
            "timeout": 120,
        }
    ]


def test_unchanged_bootstrap_is_incremental_and_offline(tmp_path: Path) -> None:
    """A matching READY receipt skips prewarm and remains network-independent."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(project, fake_bin, uv_log)
    first_commands = read_uv_commands(uv_log)

    output = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "test-session-2",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )

    repeated_commands = read_uv_commands(uv_log)[len(first_commands) :]
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in (output["hookSpecificOutput"]["additionalContext"])
    assert len(repeated_commands) == 2
    assert all("--offline" in command for command in repeated_commands)
    assert all("--help" not in command for command in repeated_commands)


def test_migrated_layout_remains_ready_on_second_session(tmp_path: Path) -> None:
    """Explicit adoption lets the next bootstrap migrate and later sessions remain READY."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    write_migratable_legacy(project)

    blocked = run_hook(project, fake_bin, uv_log)
    adopt_legacy(project)
    migrated = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "migration-resume",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )
    resumed = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "migration-ready-resume",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )
    governance = project / ".work-governance"
    transactions = [
        child.name for child in (governance / "runtime").iterdir() if child.name.startswith("LAY-")
    ]
    receipt = json.loads((governance / "bootstrap-state.json").read_text(encoding="utf-8"))

    assert "ENVIRONMENT_BLOCKED" in blocked["hookSpecificOutput"]["additionalContext"]
    assert "LAYOUT_MIGRATION_NOT_READY" in blocked["hookSpecificOutput"]["additionalContext"]
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in migrated["hookSpecificOutput"]["additionalContext"]
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in resumed["hookSpecificOutput"]["additionalContext"]
    assert len(transactions) == 1
    assert re.fullmatch(r"LAY-\d{8}T\d{6}Z-[0-9a-f]{8}-[0-9a-f]{32}", transactions[0])
    assert receipt["status"] == "READY"
    assert not (project / "_Plan").exists()


def test_changed_layout_input_reruns_and_fails_closed(tmp_path: Path) -> None:
    """A reappeared old-controller root invalidates READY instead of being ignored."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(project, fake_bin, uv_log)
    reappeared = project / "_Plan"
    reappeared.mkdir()
    (reappeared / ".workctl.lock").write_text("", encoding="utf-8")

    output = run_hook(project, fake_bin, uv_log)

    receipt = json.loads(
        (project / ".work-governance" / "bootstrap-state.json").read_text(encoding="utf-8")
    )
    context = output["hookSpecificOutput"]["additionalContext"]
    assert receipt["status"] == "ENVIRONMENT_BLOCKED"
    assert receipt["reason"] == "LAYOUT_MIGRATION_NOT_READY"
    assert "ENVIRONMENT_BLOCKED" in context
    assert "Do not perform Plan-controlled work" in context


def test_invalid_hook_input_has_short_fail_closed_output(tmp_path: Path) -> None:
    """Malformed hook input cannot select or mutate an arbitrary project."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)

    output = run_hook(
        tmp_path,
        fake_bin,
        uv_log,
        payload={"hook_event_name": "SessionStart"},
    )

    assert "ENVIRONMENT_BLOCKED" in (output["hookSpecificOutput"]["additionalContext"])
    assert not (tmp_path / ".work-governance").exists()
    assert read_uv_commands(uv_log) == []


def test_bootstrap_never_adopts_a_preexisting_unclaimed_root(tmp_path: Path) -> None:
    """SessionStart performs no writes inside a same-named unowned directory."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    governance = project / ".work-governance"
    governance.mkdir()
    business = governance / "business.txt"
    business.write_bytes(b"project-owned bytes\n")

    output = run_hook(project, fake_bin, uv_log)

    context = output["hookSpecificOutput"]["additionalContext"]
    assert "ENVIRONMENT_BLOCKED" in context
    assert "GOVERNANCE_ROOT_OWNERSHIP_UNPROVEN" in context
    assert business.read_bytes() == b"project-owned bytes\n"
    assert sorted(path.name for path in governance.iterdir()) == ["business.txt"]
    assert read_uv_commands(uv_log) == []


def test_bootstrap_does_not_trust_an_arbitrary_preexisting_version_file(
    tmp_path: Path,
) -> None:
    """A same-named version file is validated before SessionStart creates anything."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    governance = project / ".work-governance"
    governance.mkdir()
    version = governance / "version.yaml"
    version.write_text("schema_version: 1\n", encoding="utf-8")

    output = run_hook(project, fake_bin, uv_log)

    context = output["hookSpecificOutput"]["additionalContext"]
    assert "ENVIRONMENT_BLOCKED" in context
    assert "GOVERNANCE_VERSION_UNPROVEN" in context
    assert sorted(path.name for path in governance.iterdir()) == ["version.yaml"]
    assert version.read_text(encoding="utf-8") == "schema_version: 1\n"
    assert read_uv_commands(uv_log) == []


@pytest.mark.parametrize(
    "transaction_id",
    [
        "LAY-20260727T000000Z-12345678",
        f"LAY-20260727T000000Z-12345678-{'a' * 32}",
    ],
)
def test_uncommitted_audit_accepts_supported_transaction_ids(
    tmp_path: Path, transaction_id: str
) -> None:
    """Bootstrap permits old and nonce-suffixed controller recovery transactions."""
    governance = tmp_path / ".work-governance"
    (governance / "runtime" / transaction_id).mkdir(parents=True)
    namespace = runpy.run_path(str(HOOK), run_name="bootstrap_transaction_fixture")

    namespace["audit_uncommitted_root"](governance)


def test_bootstrap_validates_migration_proof_contract_beyond_its_hash(
    tmp_path: Path,
) -> None:
    """The stdlib preflight rejects rehashed arbitrary completion evidence."""
    project = tmp_path / "project"
    governance = project / ".work-governance"
    transaction_id = "LAY-20260727T000000Z-12345678"
    proof = governance / "_Plan" / ".migrations" / f"{transaction_id}.yaml"
    proof.parent.mkdir(parents=True)
    proof_text = (
        "schema_version: 1\n"
        "kind: layout-migration-proof\n"
        f"transaction_id: {transaction_id}\n"
        "status: prepared\n"
        f"legacy_manifest_sha256: {'1' * 64}\n"
        f"legacy_adoption_sha256: {'4' * 64}\n"
        f"conversion_table_sha256: {'2' * 64}\n"
        "created_at: '2026-07-27T00:00:00+00:00'\n"
    )
    proof.write_text(proof_text, encoding="utf-8")
    ignore = governance / ".gitignore"
    ignore.write_text(
        "/logs/\n/worktrees/\n/cache/\n/proposals/\n/evidence/\n/runtime/\n"
        "/bootstrap-state.json\n/workctl.lock\n",
        encoding="utf-8",
    )
    version = governance / "version.yaml"

    def write_version(proof_sha256: str) -> None:
        version.write_text(
            "schema_version: 1\n"
            "layout_version: 1\n"
            "bootstrap_contract_version: 1\n"
            "plugin_compatibility: '>=1.0.0,<2.0.0'\n"
            "legacy_migration_action_revision: 2\n"
            "migration:\n"
            "  status: migrated\n"
            f"  transaction_id: {transaction_id}\n"
            f"  legacy_manifest_sha256: {'1' * 64}\n"
            f"  new_layout_baseline_sha256: {'3' * 64}\n"
            "  completion_evidence:\n"
            "    kind: migration-proof\n"
            f"    path: .work-governance/_Plan/.migrations/{transaction_id}.yaml\n"
            f"    sha256: {proof_sha256}\n"
            "    completed_at: '2026-07-27T00:01:00+00:00'\n",
            encoding="utf-8",
        )

    write_version(hashlib.sha256(proof.read_bytes()).hexdigest())
    namespace = runpy.run_path(str(HOOK), run_name="bootstrap_proof_fixture")
    namespace["validate_layout_version"](project, governance)

    proof.write_text(
        proof_text.replace("layout-migration-proof", "arbitrary-bytes"), encoding="utf-8"
    )
    write_version(hashlib.sha256(proof.read_bytes()).hexdigest())

    with pytest.raises(namespace["BootstrapError"], match="GOVERNANCE_VERSION_UNPROVEN"):
        namespace["validate_layout_version"](project, governance)


def test_bootstrap_recovers_after_claim_fsync_before_root_activation(
    tmp_path: Path,
) -> None:
    """SessionStart resumes an exact sibling claim left before no-replace rename."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()

    interrupted = run_hook(
        project,
        fake_bin,
        uv_log,
        environment_overrides={"WORK_GOVERNANCE_TEST_INTERRUPT_AFTER_CLAIM": "1"},
    )

    assert (
        "BOOTSTRAP_TEST_INTERRUPTED_AFTER_CLAIM"
        in (interrupted["hookSpecificOutput"]["additionalContext"])
    )
    assert not (project / ".work-governance").exists()
    claim = project / ".work-governance.bootstrap" / "runtime" / "bootstrap-claim.json"
    assert claim.is_file()
    assert read_uv_commands(uv_log) == []

    resumed = run_hook(project, fake_bin, uv_log)
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in (resumed["hookSpecificOutput"]["additionalContext"])
    assert not (project / ".work-governance.bootstrap").exists()
    assert (project / ".work-governance" / "version.yaml").is_file()


def test_first_prewarm_failure_records_and_recovers_claim_bound_evidence(
    tmp_path: Path,
) -> None:
    """A journaled first-load failure is recovered before the next successful retry."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()

    failed = run_hook(
        project,
        fake_bin,
        uv_log,
        environment_overrides={
            "WORK_GOVERNANCE_TEST_FAKE_UV_FAIL_PREWARM": "1",
            "WORK_GOVERNANCE_TEST_INTERRUPT_FAILURE_AFTER_JOURNAL": "1",
        },
    )
    governance = project / ".work-governance"
    journal = governance / "runtime" / "bootstrap-failure-journal.json"

    assert "CONTROLLER_PREWARM_FAILED" in failed["hookSpecificOutput"]["additionalContext"]
    assert journal.is_file()
    assert not (governance / "bootstrap-state.json").exists()

    recovered = run_hook(project, fake_bin, uv_log)
    receipt = json.loads((governance / "bootstrap-state.json").read_text(encoding="utf-8"))
    evidence_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (governance / "evidence" / "bootstrap").glob("*.json")
    ]

    assert (
        "WORK_GOVERNANCE_BOOTSTRAP READY" in (recovered["hookSpecificOutput"]["additionalContext"])
    )
    assert receipt["status"] == "READY"
    assert not journal.exists()
    blocked = [
        payload for payload in evidence_payloads if payload.get("status") == "ENVIRONMENT_BLOCKED"
    ]
    assert len(blocked) == 1
    assert blocked[0]["reason"] == "CONTROLLER_PREWARM_FAILED"
    assert blocked[0]["commands"][0]["returncode"] == 17
    assert isinstance(blocked[0]["claim_sha256"], str)
    assert len(blocked[0]["claim_sha256"]) == 64


@pytest.mark.parametrize("redirect", ["runtime", "evidence-bootstrap"])
def test_failure_recovery_rejects_parent_symlink_redirection(tmp_path: Path, redirect: str) -> None:
    """Recovery never reads, writes, or deletes through a redirected parent."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(
        project,
        fake_bin,
        uv_log,
        environment_overrides={
            "WORK_GOVERNANCE_TEST_FAKE_UV_FAIL_PREWARM": "1",
            "WORK_GOVERNANCE_TEST_INTERRUPT_FAILURE_AFTER_JOURNAL": "1",
        },
    )
    governance = project / ".work-governance"
    if redirect == "runtime":
        redirected = tmp_path / "outside-runtime"
        (governance / "runtime").rename(redirected)
        (governance / "runtime").symlink_to(redirected, target_is_directory=True)
    else:
        redirected = tmp_path / "outside-evidence"
        (governance / "evidence" / "bootstrap").rename(redirected)
        (governance / "evidence" / "bootstrap").symlink_to(redirected, target_is_directory=True)
    before = {
        path.relative_to(redirected).as_posix(): path.read_bytes()
        for path in redirected.rglob("*")
        if path.is_file()
    }
    command_count = len(read_uv_commands(uv_log))

    blocked = run_hook(project, fake_bin, uv_log)

    context = blocked["hookSpecificOutput"]["additionalContext"]
    after = {
        path.relative_to(redirected).as_posix(): path.read_bytes()
        for path in redirected.rglob("*")
        if path.is_file()
    }
    assert "GOVERNANCE_CONTROL_PATH_SYMLINK" in context
    assert after == before
    assert len(read_uv_commands(uv_log)) == command_count


def test_failure_recovery_rejects_lexical_evidence_path_traversal(
    tmp_path: Path,
) -> None:
    """A fully rehashed journal cannot target a path containing parent traversal."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(
        project,
        fake_bin,
        uv_log,
        environment_overrides={
            "WORK_GOVERNANCE_TEST_FAKE_UV_FAIL_PREWARM": "1",
            "WORK_GOVERNANCE_TEST_INTERRUPT_FAILURE_AFTER_JOURNAL": "1",
        },
    )
    governance = project / ".work-governance"
    journal_path = governance / "runtime" / "bootstrap-failure-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    traversal = ".work-governance/evidence/bootstrap/../../../../outside/pwn.json"
    evidence_ref = f"evidence:{traversal}"
    journal["evidence_path"] = traversal
    journal["evidence_payload"]["evidence_ref"] = evidence_ref
    journal["receipt_payload"]["evidence_ref"] = evidence_ref
    evidence_bytes = (
        json.dumps(journal["evidence_payload"], indent=2, sort_keys=True) + "\n"
    ).encode()
    journal["receipt_payload"]["evidence_sha256"] = hashlib.sha256(evidence_bytes).hexdigest()
    journal_path.write_text(
        json.dumps(journal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_bytes(b"outside bytes\n")
    command_count = len(read_uv_commands(uv_log))

    blocked = run_hook(project, fake_bin, uv_log)

    context = blocked["hookSpecificOutput"]["additionalContext"]
    assert "BOOTSTRAP_FAILURE_JOURNAL_INVALID" in context
    assert sentinel.read_bytes() == b"outside bytes\n"
    assert sorted(path.name for path in outside.iterdir()) == ["sentinel.txt"]
    assert len(read_uv_commands(uv_log)) == command_count


def test_bootstrap_rejects_symlinked_control_path_without_outside_write(
    tmp_path: Path,
) -> None:
    """A local cache symlink cannot redirect bootstrap writes outside the project."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(project, fake_bin, uv_log)
    prior_commands = len(read_uv_commands(uv_log))
    governance = project / ".work-governance"
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.rmtree(governance / "cache")
    (governance / "cache").symlink_to(outside, target_is_directory=True)

    output = run_hook(project, fake_bin, uv_log)

    context = output["hookSpecificOutput"]["additionalContext"]
    assert "ENVIRONMENT_BLOCKED" in context
    assert "GOVERNANCE_CONTROL_PATH_SYMLINK" in context
    assert list(outside.iterdir()) == []
    assert len(read_uv_commands(uv_log)) == prior_commands


def test_isolated_plugin_copy_bootstraps_without_source_repository_paths(
    tmp_path: Path,
) -> None:
    """An installed payload uses PLUGIN_ROOT and stores build data only locally."""
    installed = tmp_path / "installed" / "work-governance"
    installed.parent.mkdir()
    shutil.copytree(PLUGIN_ROOT, installed)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()

    output = run_hook(project, fake_bin, uv_log, plugin_root=installed)

    governance = project / ".work-governance"
    receipt = json.loads((governance / "bootstrap-state.json").read_text(encoding="utf-8"))
    version_text = (governance / "version.yaml").read_text(encoding="utf-8")
    installed_manifest = json.loads(
        (installed / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in (output["hookSpecificOutput"]["additionalContext"])
    assert receipt["plugin_build"] == installed_manifest["version"]
    assert receipt["plugin_build"] not in version_text
    assert all(
        str(installed / "scripts" / "workctl.py") in command for command in read_uv_commands(uv_log)
    )


@pytest.mark.skipif(
    os.environ.get("WORK_GOVERNANCE_REAL_UV") != "1",
    reason="explicit real-UV bootstrap smoke",
)
def test_real_uv_bootstrap_then_network_denied_offline_resume(
    tmp_path: Path,
) -> None:
    """Prewarm a real isolated cache, then prove READY resume needs no network."""
    project = tmp_path / "project"
    project.mkdir()
    hook_input = {
        "session_id": "real-uv-session",
        "cwd": str(project),
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    environment = dict(os.environ)
    environment["PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    first = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(hook_input),
        text=True,
        capture_output=True,
        env=environment,
        timeout=120,
        check=True,
    )
    first_output = json.loads(first.stdout)
    assert (
        "WORK_GOVERNANCE_BOOTSTRAP READY"
        in (first_output["hookSpecificOutput"]["additionalContext"])
    )
    environment["HTTPS_PROXY"] = "http://127.0.0.1:1"
    environment["HTTP_PROXY"] = "http://127.0.0.1:1"
    hook_input["source"] = "resume"
    second = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(hook_input),
        text=True,
        capture_output=True,
        env=environment,
        timeout=120,
        check=True,
    )
    second_output = json.loads(second.stdout)
    receipt = json.loads(
        (project / ".work-governance" / "bootstrap-state.json").read_text(encoding="utf-8")
    )
    evidence = project / receipt["evidence_ref"].removeprefix("evidence:")
    evidence_payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert (
        "WORK_GOVERNANCE_BOOTSTRAP READY"
        in (second_output["hookSpecificOutput"]["additionalContext"])
    )
    assert receipt["status"] == "READY"
    assert len(evidence_payload["commands"]) == 2
    assert all("--offline" in command["command"] for command in evidence_payload["commands"])
