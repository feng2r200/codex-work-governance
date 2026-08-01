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
cache = arguments[arguments.index("--cache-dir") + 1]
prewarmed = os.path.join(cache, ".work-governance-test-prewarmed")
if (
    controller_arguments == ["--help"]
    and "--offline" in arguments
    and not os.path.isfile(prewarmed)
):
    raise SystemExit(18)
if (
    os.environ.get("WORK_GOVERNANCE_TEST_FAKE_UV_FAIL_PREWARM") == "1"
    and controller_arguments == ["--help"]
):
    raise SystemExit(17)
if controller_arguments == ["--help"]:
    os.makedirs(cache, exist_ok=True)
    with open(prewarmed, "w", encoding="utf-8") as handle:
        handle.write("ready\\n")
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


def write_schema3_plan_fixture(project: Path, plan_id: str, title: str) -> Path:
    """Create historical schema-v3 authority without a production admission bypass."""
    timestamp = "2026-07-28T00:00:00+00:00"
    plan_root = project / ".work-governance" / "_Plan"
    plan_root.mkdir(parents=True, exist_ok=True)
    index = {
        "schema_version": 1,
        "active_plan_id": plan_id,
        "plans": [
            {
                "id": plan_id,
                "path": f"{plan_id}.md",
                "title": title,
                "created_at": timestamp,
            }
        ],
    }
    frontmatter = {
        "schema_version": 3,
        "plan_id": plan_id,
        "title": title,
        "status": "active",
        "mode": "autonomous",
        "revision": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
        "scope": {"include": [], "exclude": []},
        "confirmations": {"required": []},
        "obligations": [],
        "tasks": [],
        "validations": [],
        "artifacts": [],
        "authority": {
            "model": "single-active",
            "state": "governed",
            "canonical_plan_id": plan_id,
            "sources": [],
            "confirmations": {},
        },
        "delivery": {
            "status": "pending",
            "boundary": "undetermined",
            "evidence_ref": "project:not-yet-delivered",
        },
        "activation": {
            "status": "deferred",
            "current_ref": "undetermined",
            "target_ref": "undetermined",
        },
        "route": {
            "route_status": "active",
            "slice_status": "initialized",
            "next_phase": "Define the demand contract.",
            "validation_standard": "Every obligation has direct fresh evidence.",
            "confirmation_gate": "none",
        },
        "handoff": {
            "route_status": "active",
            "next_step": "Define the demand contract.",
        },
    }
    (plan_root / "index.yaml").write_text(
        yaml.safe_dump(index, sort_keys=False),
        encoding="utf-8",
    )
    plan = plan_root / f"{plan_id}.md"
    plan.write_text(
        f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n"
        "# Decision Summary\n\nInitialized test fixture.\n",
        encoding="utf-8",
    )
    return plan


def write_active_proposal_journal(
    namespace: dict[str, Any],
    governance: Path,
) -> tuple[Path, dict[str, Any]]:
    """Write the controller artifacts and journal around a partial proposal activation."""
    transaction = governance / "runtime" / "LAY-20260728T000000Z-12345678-abcdef12"
    transaction.mkdir(parents=True)
    backup_plan = transaction / "backup" / "_Plan"
    proposal_sources = [
        backup_plan / "proposals" / migration_id
        for migration_id in ("MIG-20260727-001", "MIG-20260727-002")
    ]
    for proposal in proposal_sources:
        proposal.mkdir(parents=True)
        (proposal / "reconciliation.yaml").write_text(
            f"migration_id: {proposal.name}\nconfirmations: {{}}\n",
            encoding="utf-8",
        )
    (backup_plan / "index.yaml").write_text(
        "schema_version: 1\nactive_plan_id: PLAN-20260728-001\n",
        encoding="utf-8",
    )
    (backup_plan / "PLAN-20260728-001.md").write_text(
        "---\nplan_id: PLAN-20260728-001\n---\n# Legacy\n",
        encoding="utf-8",
    )
    original_evidence = (
        governance / "evidence" / "layout-migrations" / transaction.name / "legacy-_Plan"
    )
    shutil.copytree(backup_plan, original_evidence)
    legacy_manifest = namespace["path_manifest"](backup_plan)[1:]
    legacy_proposals_manifest = namespace["path_manifest"](backup_plan / "proposals")[1:]
    empty_digest = namespace["stable_digest"]([])
    proposal_digest = namespace["stable_digest"](legacy_proposals_manifest)
    adoption = governance / "runtime" / "legacy-adoption.json"
    adoption_payload = {
        "schema_version": 1,
        "kind": "work-governance-legacy-adoption",
        "action_revision": 3,
        "project_root": governance.parent.resolve().as_posix(),
        "worktree_identity": {
            "repository": False,
            "project_root": governance.parent.resolve().as_posix(),
        },
        "active_plan_id": "PLAN-20260728-001",
        "active_plan_path": "PLAN-20260728-001.md",
        "legacy_manifest_sha256": namespace["stable_digest"](legacy_manifest),
        "controller_sha256": hashlib.sha256(WORKCTL.read_bytes()).hexdigest(),
        "confirmation_ref": "user:test-legacy-adoption",
        "created_at": "2026-07-28T00:00:00+00:00",
    }
    adoption.write_text(json.dumps(adoption_payload), encoding="utf-8")
    adoption_sha256 = hashlib.sha256(adoption.read_bytes()).hexdigest()
    canonical_plan = governance / "_Plan"
    proof = canonical_plan / ".migrations" / f"{transaction.name}.yaml"
    proof.parent.mkdir(parents=True)
    proof.write_text(
        "schema_version: 1\n"
        "kind: layout-migration-proof\n"
        f"transaction_id: {transaction.name}\n"
        "status: prepared\n"
        f"legacy_manifest_sha256: {namespace['stable_digest'](legacy_manifest)}\n"
        f"legacy_adoption_sha256: {adoption_sha256}\n"
        f"conversion_table_sha256: {empty_digest}\n"
        f"legacy_proposals_sha256: {proposal_digest}\n"
        f"new_proposals_baseline_sha256: {proposal_digest}\n"
        "created_at: '2026-07-28T00:00:00+00:00'\n",
        encoding="utf-8",
    )
    (canonical_plan / "index.yaml").write_text(
        "schema_version: 1\nactive_plan_id: PLAN-20260728-001\n",
        encoding="utf-8",
    )
    (canonical_plan / "PLAN-20260728-001.md").write_text(
        "---\nplan_id: PLAN-20260728-001\n---\n# Canonical\n",
        encoding="utf-8",
    )
    (governance.parent / "_Plan").write_text(
        "WORK_GOVERNANCE_LAYOUT_ACTIVATION_GUARD\n",
        encoding="utf-8",
    )
    proposals = governance / "proposals"
    first = proposals / proposal_sources[0].name
    second = transaction / "staging" / "proposals" / proposal_sources[1].name
    shutil.copytree(proposal_sources[0], first)
    shutil.copytree(proposal_sources[1], second)
    records = []
    for proposal in (first, second):
        migration_id = proposal.name
        manifest = namespace["path_manifest"](proposal)[1:]
        records.append(
            {
                "migration_id": migration_id,
                "manifest": manifest,
                "manifest_sha256": namespace["stable_digest"](manifest),
                "staged_path": (transaction / "staging" / "proposals" / migration_id).as_posix(),
                "target": f".work-governance/proposals/{migration_id}",
            }
        )
    new_layout_manifest = namespace["path_manifest"](canonical_plan)[1:]
    journal = {
        "schema_version": 1,
        "kind": "layout-migration",
        "transaction_id": transaction.name,
        "status": "plan-activated",
        "created_at": "2026-07-28T00:00:00+00:00",
        "updated_at": "2026-07-28T00:01:00+00:00",
        "active_plan_id": "PLAN-20260728-001",
        "active_plan_path": "PLAN-20260728-001.md",
        "legacy_manifest": legacy_manifest,
        "legacy_manifest_sha256": namespace["stable_digest"](legacy_manifest),
        "legacy_proposals_manifest": legacy_proposals_manifest,
        "legacy_proposals_sha256": proposal_digest,
        "legacy_adoption_sha256": adoption_sha256,
        "git_baseline": {"repository": False},
        "paths": {
            "staged_plan": (transaction / "staging" / "_Plan").as_posix(),
            "staged_proposals": (transaction / "staging" / "proposals").as_posix(),
            "target_proposals": proposals.as_posix(),
            "backup_plan": backup_plan.as_posix(),
            "original_evidence": original_evidence.as_posix(),
        },
        "completed_operations": [
            "snapshot",
            "staging",
            "conversion",
            "staged-validation",
            "legacy-backup",
            "plan-activation",
        ],
        "new_layout_manifest": new_layout_manifest,
        "new_layout_baseline_sha256": namespace["stable_digest"](new_layout_manifest),
        "conversion_table": [],
        "conversion_table_sha256": empty_digest,
        "log_files": [],
        "proposal_trees": records,
        "new_proposals_baseline_sha256": proposal_digest,
    }
    (transaction / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
    return transaction, journal


def test_uncommitted_audit_accepts_journal_bound_partial_proposal_activation(
    tmp_path: Path,
) -> None:
    """SessionStart permits only an exact controller-journal proposal partition."""
    namespace = runpy.run_path(str(HOOK), run_name="session_start_partial_proposal_test")
    controller = runpy.run_path(str(WORKCTL), run_name="workctl_partial_proposal_test")
    governance = tmp_path / ".work-governance"
    write_active_proposal_journal(namespace, governance)

    namespace["audit_uncommitted_root"](governance)
    assert controller["uncommitted_governance_footprint_errors"](tmp_path) == []


@pytest.mark.parametrize(
    "forgery",
    [
        "minimal-journal",
        "transaction-id",
        "record-hash",
        "missing-adoption",
        "invalid-proof",
        "missing-staged",
        "rehash-drift",
    ],
)
def test_uncommitted_audit_rejects_self_asserted_proposal_journal(
    tmp_path: Path,
    forgery: str,
) -> None:
    """A proposal cannot authorize itself through an incomplete or drifted journal."""
    namespace = runpy.run_path(str(HOOK), run_name="session_start_forged_proposal_test")
    governance = tmp_path / ".work-governance"
    transaction, journal = write_active_proposal_journal(namespace, governance)
    if forgery == "minimal-journal":
        first = governance / "proposals" / "MIG-20260727-001"
        manifest = namespace["path_manifest"](first)[1:]
        journal = {
            "status": "plan-activated",
            "proposal_trees": [
                {
                    "migration_id": first.name,
                    "manifest_sha256": namespace["stable_digest"](manifest),
                    "target": f".work-governance/proposals/{first.name}",
                }
            ],
        }
    elif forgery == "transaction-id":
        journal["transaction_id"] = "LAY-20260728T000000Z-87654321-abcdef12"
    elif forgery == "record-hash":
        journal["proposal_trees"][0]["manifest_sha256"] = "f" * 64
    elif forgery == "missing-adoption":
        (governance / "runtime" / "legacy-adoption.json").unlink()
    elif forgery == "invalid-proof":
        proof = governance / "_Plan" / ".migrations" / f"{transaction.name}.yaml"
        proof.write_text(
            f"kind: layout-migration-proof\ntransaction_id: {transaction.name}\n",
            encoding="utf-8",
        )
        journal["new_layout_manifest"] = namespace["path_manifest"](governance / "_Plan")[1:]
        journal["new_layout_baseline_sha256"] = namespace["stable_digest"](
            journal["new_layout_manifest"]
        )
    elif forgery == "missing-staged":
        shutil.rmtree(transaction / "staging" / "proposals" / "MIG-20260727-002")
    else:
        first = governance / "proposals" / "MIG-20260727-001" / "reconciliation.yaml"
        first.write_text(
            "migration_id: MIG-20260727-001\nconfirmations: {}\ndrift: true\n",
            encoding="utf-8",
        )
        first_manifest = namespace["path_manifest"](first.parent)[1:]
        journal["proposal_trees"][0]["manifest"] = first_manifest
        journal["proposal_trees"][0]["manifest_sha256"] = namespace["stable_digest"](first_manifest)
        combined = []
        for record in journal["proposal_trees"]:
            combined.append({"path": record["migration_id"], "kind": "directory"})
            combined.extend(
                {
                    **entry,
                    "path": f"{record['migration_id']}/{entry['path']}",
                }
                for entry in record["manifest"]
            )
        combined.sort(key=lambda entry: str(entry["path"]))
        journal["legacy_proposals_manifest"] = combined
        journal["legacy_proposals_sha256"] = namespace["stable_digest"](combined)
        journal["new_proposals_baseline_sha256"] = namespace["stable_digest"](combined)
        legacy_manifest = journal["legacy_manifest"]
        drift_path = "proposals/MIG-20260727-001/reconciliation.yaml"
        for entry in legacy_manifest:
            if entry["path"] == drift_path:
                entry["size"] = first.stat().st_size
                entry["sha256"] = hashlib.sha256(first.read_bytes()).hexdigest()
        journal["legacy_manifest_sha256"] = namespace["stable_digest"](legacy_manifest)
    (transaction / "journal.json").write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(
        namespace["BootstrapError"],
        match="UNCOMMITTED_GOVERNANCE_FOOTPRINT_INVALID",
    ):
        namespace["audit_uncommitted_root"](governance)
    controller = runpy.run_path(str(WORKCTL), run_name=f"workctl_forged_proposal_{forgery}")
    assert "uncommitted governance proposals are not transaction-bound" in controller[
        "uncommitted_governance_footprint_errors"
    ](tmp_path)


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
    capability_path = project / ".work-governance" / "runtime" / "bootstrap-capability.json"
    capability = json.loads(capability_path.read_text(encoding="utf-8"))
    controller = project / capability["controller_ref"]
    capability_sha256 = hashlib.sha256(capability_path.read_bytes()).hexdigest()
    adopt_result = subprocess.run(
        [
            sys.executable,
            str(controller),
            "--receipt-sha256",
            capability_sha256,
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
        check=False,
    )
    assert adopt_result.returncode == 0, adopt_result.stderr
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
    assert len(commands) == 5
    assert "--offline" in commands[0]
    assert commands[0][-1] == "--help"
    assert "--offline" not in commands[1]
    assert commands[1][-1] == "--help"
    for command in commands[2:]:
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


def test_resume_block_reports_executed_hook_and_exact_adoption_recovery(
    tmp_path: Path,
) -> None:
    """The observed classification failure never misreports an absent SessionStart hook."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    write_migratable_legacy(project)
    session_id = "019f8e2d-96e9-75b0-ab00-09512f6fbfa0"

    blocked = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": session_id,
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )

    context = blocked["hookSpecificOutput"]["additionalContext"]
    receipt = json.loads(
        (project / ".work-governance" / "bootstrap-state.json").read_text(encoding="utf-8")
    )
    evidence_path = project / receipt["evidence_ref"].removeprefix("evidence:")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert "hook=executed; source=resume" in context
    assert "LEGACY_CLASSIFICATION_REQUIRED" in context
    assert "workctl layout adopt" in context
    assert f"evidence={receipt['evidence_ref']}" in context
    assert "Restore a trusted/enabled" not in context
    assert evidence["hook_source"] == "resume"
    assert evidence["session_id"] == session_id
    assert receipt["status"] == "ENVIRONMENT_BLOCKED"


def test_action_revision_four_accepts_and_preserves_revision_two_blocked_history(
    tmp_path: Path,
) -> None:
    """A newer 1.0.2 action reads the exact 1.0.1 uncommitted evidence contract."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    write_migratable_legacy(project)
    run_hook(project, fake_bin, uv_log)
    governance = project / ".work-governance"
    claim_path = governance / "runtime" / "bootstrap-claim.json"
    receipt_path = governance / "bootstrap-state.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    evidence_path = project / receipt["evidence_ref"].removeprefix("evidence:")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["action_revision"] = 2
    claim_path.write_text(json.dumps(claim, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    claim_sha256 = hashlib.sha256(claim_path.read_bytes()).hexdigest()
    legacy_evidence = {
        key: value for key, value in evidence.items() if key not in {"hook_source", "session_id"}
    }
    legacy_evidence["action_revision"] = 2
    legacy_evidence["claim_sha256"] = claim_sha256
    evidence_path.write_text(
        json.dumps(legacy_evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt["action_revision"] = 2
    receipt["claim_sha256"] = claim_sha256
    receipt["evidence_sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    retried = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "revision-four-retry",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )
    current_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    evidence_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (governance / "evidence" / "bootstrap").glob("*.json")
    ]

    assert "LEGACY_CLASSIFICATION_REQUIRED" in (retried["hookSpecificOutput"]["additionalContext"])
    assert current_receipt["action_revision"] == 5
    assert {payload["action_revision"] for payload in evidence_payloads} == {2, 5}


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


def test_action_four_sessionstart_upgrades_action_three_scope_residual(
    tmp_path: Path,
) -> None:
    """A fresh 1.0.2 session runs the real offline correction before issuing READY."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(project, fake_bin, uv_log)
    governance = project / ".work-governance"
    prior_command_count = len(read_uv_commands(uv_log))
    plan = write_schema3_plan_fixture(
        project,
        "PLAN-20260728-001",
        "Action upgrade bootstrap fixture",
    )
    _, raw_frontmatter, body = plan.read_text(encoding="utf-8").split("---\n", 2)
    frontmatter = yaml.safe_load(raw_frontmatter)
    frontmatter["scope"]["include"].extend(["_Plan/", "_Plan/business-output"])
    revision_before = frontmatter["revision"]
    plan.write_text(
        f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n{body.lstrip()}",
        encoding="utf-8",
    )
    version_path = governance / "version.yaml"
    version = yaml.safe_load(version_path.read_text(encoding="utf-8"))
    version["legacy_migration_action_revision"] = 3
    version_path.write_text(yaml.safe_dump(version, sort_keys=False), encoding="utf-8")
    receipt_path = governance / "bootstrap-state.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["action_revision"] = 3
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    resumed = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "action-four-layout-upgrade",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "startup",
        },
    )
    resumed_commands = read_uv_commands(uv_log)[prior_command_count:]
    current_receipt_path = (
        governance / "runtime" / "sessions" / "action-four-layout-upgrade" / "bootstrap-state.json"
    )
    current_receipt = json.loads(current_receipt_path.read_text(encoding="utf-8"))
    current_version = yaml.safe_load(version_path.read_text(encoding="utf-8"))
    _, corrected_raw, _corrected_body = plan.read_text(encoding="utf-8").split("---\n", 2)
    corrected = yaml.safe_load(corrected_raw)
    proofs = list((governance / "_Plan" / ".migrations").glob("LAY-*.yaml"))

    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in (resumed["hookSpecificOutput"]["additionalContext"])
    assert len(resumed_commands) == 4
    assert resumed_commands[0][-1] == "--help"
    assert all("--offline" in command for command in resumed_commands)
    assert current_receipt["status"] == "READY"
    assert current_receipt["action_revision"] == 5
    assert current_version["legacy_migration_action_revision"] == 4
    assert corrected["revision"] == revision_before + 1
    assert ".work-governance/_Plan/" in corrected["scope"]["include"]
    assert "_Plan/business-output" in corrected["scope"]["include"]
    assert "_Plan/" not in corrected["scope"]["include"]
    assert len(proofs) == 1
    assert yaml.safe_load(proofs[0].read_text(encoding="utf-8"))["kind"] == (
        "layout-action-upgrade-proof"
    )


def test_migrated_layout_with_suspect_artifact_recovers_prior_minimal_receipt(
    tmp_path: Path,
) -> None:
    """The observed 1.0.0 blocked state upgrades without clearing the suspect artifact."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    write_migratable_legacy(project)
    run_hook(project, fake_bin, uv_log)
    adopt_legacy(project)
    run_hook(project, fake_bin, uv_log)
    prior_command_count = len(read_uv_commands(uv_log))

    plan_path = project / ".work-governance" / "_Plan" / "PLAN-20260723-001.md"
    _, frontmatter_text, body = plan_path.read_text(encoding="utf-8").split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_text)
    frontmatter["tasks"][0]["resolves_artifacts"] = ["A-001"]
    frontmatter["artifacts"][0]["status"] = "suspect"
    plan_path.write_text(
        f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---{body}",
        encoding="utf-8",
    )
    receipt_path = project / ".work-governance" / "bootstrap-state.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bootstrap_contract_version": 1,
                "action_revision": 2,
                "updated_at": "2026-07-27T00:00:00Z",
                "status": "ENVIRONMENT_BLOCKED",
                "reason": "LAYOUT_VALIDATION_FAILED",
                "evidence_ref": "evidence:.work-governance/evidence/bootstrap/legacy.json",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    resumed = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "suspect-recovery-resume",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )
    resumed_commands = read_uv_commands(uv_log)[prior_command_count:]
    layout_validation = subprocess.run(
        [sys.executable, str(WORKCTL), "layout", "validate"],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )
    plan_validation = subprocess.run(
        [sys.executable, str(WORKCTL), "plan", "validate"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in (resumed["hookSpecificOutput"]["additionalContext"])
    assert receipt["status"] == "READY"
    assert (
        receipt["plugin_build"]
        == json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))[
            "version"
        ]
    )
    assert layout_validation.stdout.strip() == "LAYOUT_VALID"
    assert plan_validation.returncode == 1
    assert "A-001 is suspect" in plan_validation.stderr
    assert len(resumed_commands) == 4
    assert all("--offline" in command for command in resumed_commands)


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
        (
            project
            / ".work-governance"
            / "runtime"
            / "sessions"
            / "test-session"
            / "bootstrap-state.json"
        ).read_text(encoding="utf-8")
    )
    context = output["hookSpecificOutput"]["additionalContext"]
    assert receipt["status"] == "ENVIRONMENT_BLOCKED"
    assert receipt["reason"] == "LAYOUT_MIGRATION_NOT_READY"
    assert set(receipt) == {
        "schema_version",
        "bootstrap_contract_version",
        "action_revision",
        "updated_at",
        "status",
        "reason",
        "plugin_build",
        "plugin_manifest_sha256",
        "project_input_sha256",
        "claim_sha256",
        "evidence_ref",
        "evidence_sha256",
    }
    evidence_path = project / receipt["evidence_ref"].removeprefix("evidence:")
    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == receipt["evidence_sha256"]
    assert "ENVIRONMENT_BLOCKED" in context
    assert "Do not perform Plan-controlled work" in context


def test_committed_layout_recovers_interrupted_failure_transaction(
    tmp_path: Path,
) -> None:
    """A committed layout installs its durable blocked record before a later retry."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(project, fake_bin, uv_log)
    governance = project / ".work-governance"
    reappeared = project / "_Plan"
    reappeared.mkdir()
    (reappeared / ".workctl.lock").write_text("", encoding="utf-8")

    interrupted = run_hook(
        project,
        fake_bin,
        uv_log,
        environment_overrides={"WORK_GOVERNANCE_TEST_INTERRUPT_FAILURE_AFTER_JOURNAL": "1"},
    )
    session_dir = governance / "runtime" / "sessions" / "test-session"
    journal = session_dir / "bootstrap-failure-journal.json"

    assert (
        "BOOTSTRAP_TEST_INTERRUPTED_FAILURE_INSTALL"
        in (interrupted["hookSpecificOutput"]["additionalContext"])
    )
    assert journal.is_file()
    assert not (governance / "bootstrap-state.json").exists()

    shutil.rmtree(reappeared)
    recovered = run_hook(project, fake_bin, uv_log)
    receipt = json.loads((session_dir / "bootstrap-state.json").read_text(encoding="utf-8"))
    blocked_evidence = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (governance / "evidence" / "bootstrap").glob("*.json")
        if json.loads(path.read_text(encoding="utf-8")).get("status") == "ENVIRONMENT_BLOCKED"
    ]

    assert (
        "WORK_GOVERNANCE_BOOTSTRAP READY" in (recovered["hookSpecificOutput"]["additionalContext"])
    )
    assert receipt["status"] == "READY"
    assert not journal.exists()
    assert len(blocked_evidence) == 1
    assert blocked_evidence[0]["reason"] == "LAYOUT_MIGRATION_NOT_READY"
    assert set(blocked_evidence[0]) == {
        "schema_version",
        "bootstrap_contract_version",
        "action_revision",
        "updated_at",
        "status",
        "reason",
        "plugin_build",
        "plugin_manifest_sha256",
        "project_input_sha256",
        "claim_sha256",
        "evidence_ref",
        "hook_source",
        "session_id",
        "commands",
    }
    assert blocked_evidence[0]["hook_source"] == "startup"
    assert blocked_evidence[0]["session_id"] == "test-session"


def test_committed_layout_bootstraps_missing_local_directories(tmp_path: Path) -> None:
    """A fresh checkout recreates claim-bound infrastructure for later failures."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(project, fake_bin, uv_log)
    governance = project / ".work-governance"
    receipt_path = governance / "bootstrap-state.json"
    local_directories = (
        "logs",
        "worktrees",
        "cache",
        "proposals",
        "evidence",
        "runtime",
    )
    for local_directory in local_directories:
        shutil.rmtree(governance / local_directory)
    receipt_path.unlink()

    resumed = run_hook(project, fake_bin, uv_log)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in (resumed["hookSpecificOutput"]["additionalContext"])
    assert receipt["status"] == "READY"
    for local_directory in local_directories:
        assert (governance / local_directory).is_dir()
    claim = governance / "runtime" / "bootstrap-claim.json"
    assert claim.is_file()

    reappeared = project / "_Plan"
    reappeared.mkdir()
    (reappeared / ".workctl.lock").write_text("", encoding="utf-8")
    blocked = run_hook(project, fake_bin, uv_log)
    blocked_receipt = json.loads(
        (governance / "runtime" / "sessions" / "test-session" / "bootstrap-state.json").read_text(
            encoding="utf-8"
        )
    )
    evidence_path = project / blocked_receipt["evidence_ref"].removeprefix("evidence:")

    assert "LAYOUT_MIGRATION_NOT_READY" in (blocked["hookSpecificOutput"]["additionalContext"])
    assert set(blocked_receipt) == {
        "schema_version",
        "bootstrap_contract_version",
        "action_revision",
        "updated_at",
        "status",
        "reason",
        "plugin_build",
        "plugin_manifest_sha256",
        "project_input_sha256",
        "claim_sha256",
        "evidence_ref",
        "evidence_sha256",
    }
    assert blocked_receipt["claim_sha256"] == hashlib.sha256(claim.read_bytes()).hexdigest()
    assert (
        blocked_receipt["evidence_sha256"] == hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    )


def test_committed_early_digest_failure_invalidates_stale_ready_receipt(
    tmp_path: Path,
) -> None:
    """An unprovable failure leaves no minimal receipt that can resemble READY state."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    run_hook(project, fake_bin, uv_log)
    governance = project / ".work-governance"
    receipt_path = governance / "bootstrap-state.json"
    evidence_before = sorted((governance / "evidence" / "bootstrap").iterdir())

    blocked = run_hook(
        project,
        fake_bin,
        uv_log,
        environment_overrides={"WORK_GOVERNANCE_TEST_FAIL_PROJECT_INPUT_DIGEST": "1"},
    )

    assert (
        "BOOTSTRAP_TEST_PROJECT_INPUT_DIGEST_FAILED"
        in (blocked["hookSpecificOutput"]["additionalContext"])
    )
    assert not receipt_path.exists()
    assert sorted((governance / "evidence" / "bootstrap").iterdir()) == evidence_before

    recovered = run_hook(project, fake_bin, uv_log)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert (
        "WORK_GOVERNANCE_BOOTSTRAP READY" in (recovered["hookSpecificOutput"]["additionalContext"])
    )
    assert receipt["status"] == "READY"


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


def test_failed_new_session_does_not_invalidate_another_session_ready_receipt(
    tmp_path: Path,
) -> None:
    """A beta bootstrap failure cannot revoke alpha's scoped or legacy READY state."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.jsonl"
    install_fake_uv(fake_bin, uv_log)
    project = tmp_path / "project"
    project.mkdir()
    alpha_payload = {
        "session_id": "session-alpha",
        "cwd": str(project),
        "hook_event_name": "SessionStart",
        "source": "startup",
    }

    run_hook(project, fake_bin, uv_log, payload=alpha_payload)
    governance = project / ".work-governance"
    alpha_receipt = governance / "runtime" / "sessions" / "session-alpha" / "bootstrap-state.json"
    legacy_receipt = governance / "bootstrap-state.json"
    alpha_bytes = alpha_receipt.read_bytes()
    legacy_bytes = legacy_receipt.read_bytes()

    blocked = run_hook(
        project,
        fake_bin,
        uv_log,
        payload={
            "session_id": "session-beta",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "startup",
        },
        environment_overrides={"WORK_GOVERNANCE_TEST_FAIL_PROJECT_INPUT_DIGEST": "1"},
    )

    assert (
        "BOOTSTRAP_TEST_PROJECT_INPUT_DIGEST_FAILED"
        in blocked["hookSpecificOutput"]["additionalContext"]
    )
    assert alpha_receipt.read_bytes() == alpha_bytes
    assert legacy_receipt.read_bytes() == legacy_bytes
    assert not (
        governance / "runtime" / "sessions" / "session-beta" / "bootstrap-state.json"
    ).exists()


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
    failed_context = failed["hookSpecificOutput"]["additionalContext"]

    assert "CONTROLLER_PREWARM_FAILED" in failed_context
    assert "hook=executed; source=startup" in failed_context
    assert "exact project-local controller cache or permitted dependency access" in failed_context
    assert "Restore a trusted/enabled" not in failed_context
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
    assert [command["returncode"] for command in blocked[0]["commands"]] == [18, 17]
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
    bundled_controller = str(project / receipt["controller_ref"])
    commands = read_uv_commands(uv_log)
    assert all(bundled_controller in command for command in commands)
    assert all(str(installed / "scripts" / "workctl.py") not in command for command in commands)


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


def test_runtime_bundle_survives_plugin_cache_loss_and_preserves_other_session(
    tmp_path: Path,
) -> None:
    """Each exact session bundle survives cache loss and remains independently usable."""
    installed = tmp_path / "plugin-cache" / "work-governance"
    installed.parent.mkdir()
    shutil.copytree(PLUGIN_ROOT, installed)
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
        plugin_root=installed,
        payload={
            "session_id": "observed-session-old",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "startup",
        },
    )
    old_receipt_path = (
        project
        / ".work-governance"
        / "runtime"
        / "sessions"
        / "observed-session-old"
        / "bootstrap-state.json"
    )
    old_receipt_sha256 = hashlib.sha256(old_receipt_path.read_bytes()).hexdigest()
    run_hook(
        project,
        fake_bin,
        uv_log,
        plugin_root=installed,
        payload={
            "session_id": "observed-session-current",
            "cwd": str(project),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
    )
    receipt_path = (
        project
        / ".work-governance"
        / "runtime"
        / "sessions"
        / "observed-session-current"
        / "bootstrap-state.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    current_receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    controller = project / receipt["controller_ref"]
    lifecycle = project / receipt["lifecycle_ref"]
    bundle_manifest = project / receipt["runtime_bundle_ref"] / "manifest.json"

    assert receipt["schema_version"] == 2
    assert receipt["session_id"] == "observed-session-current"
    assert hashlib.sha256(controller.read_bytes()).hexdigest() == receipt["controller_sha256"]
    assert hashlib.sha256(lifecycle.read_bytes()).hexdigest() == receipt["lifecycle_sha256"]
    assert (
        hashlib.sha256(bundle_manifest.read_bytes()).hexdigest()
        == receipt["runtime_manifest_sha256"]
    )
    preserved = subprocess.run(
        [
            sys.executable,
            str(controller),
            "--receipt-sha256",
            old_receipt_sha256,
            "layout",
            "migrate",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    shutil.rmtree(installed)
    intake = subprocess.run(
        [
            sys.executable,
            str(controller),
            "--receipt-sha256",
            current_receipt_sha256,
            "intake",
            "status",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert preserved.returncode == 0, preserved.stderr
    assert intake.returncode == 0
    assert json.loads(intake.stdout)["intake_state"] == "INTAKE_READY"
