"""Trusted per-turn intake contract tests."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance"
HOOKS_CONFIG = PLUGIN_ROOT / "hooks" / "hooks.json"
SESSION_HOOK = PLUGIN_ROOT / "hooks" / "session_start.py"
TURN_HOOK = PLUGIN_ROOT / "hooks" / "user_prompt_submit.py"
WORKCTL = PLUGIN_ROOT / "scripts" / "workctl.py"
STOCKLENS_REPLAY = REPOSITORY_ROOT / "tests" / "fixtures" / "stocklens_goal_driven_replay.json"


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA256 digest of *payload*."""
    return hashlib.sha256(payload).hexdigest()


def install_fake_uv(directory: Path) -> Path:
    """Install a UV-shaped wrapper that executes the bundled controller."""
    wrapper = directory / "uv"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        + """
import os
import subprocess
import sys

arguments = sys.argv[1:]
script_index = arguments.index("--script")
controller = arguments[script_index + 1]
controller_arguments = arguments[script_index + 2:]
cache = arguments[arguments.index("--cache-dir") + 1]
if controller_arguments == ["--help"]:
    os.makedirs(cache, exist_ok=True)
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
    return wrapper


def run_session_hook(
    project: Path,
    fake_bin: Path,
    session_id: str,
    *,
    source: str = "startup",
    plugin_root: Path = PLUGIN_ROOT,
    environment_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run the real SessionStart hook for one temporary project."""
    environment = dict(os.environ)
    environment["PLUGIN_ROOT"] = str(plugin_root)
    environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
    environment.update(environment_overrides or {})
    result = subprocess.run(
        [sys.executable, str(plugin_root / "hooks" / "session_start.py")],
        input=json.dumps(
            {
                "session_id": session_id,
                "cwd": str(project),
                "hook_event_name": "SessionStart",
                "source": source,
            }
        ),
        text=True,
        capture_output=True,
        env=environment,
        check=True,
    )
    output: object = json.loads(result.stdout)
    assert isinstance(output, dict)
    return output


def run_turn_hook(
    project: Path,
    *,
    session_id: str,
    turn_id: str,
    prompt: str,
    plugin_root: Path = PLUGIN_ROOT,
    environment_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run the real UserPromptSubmit hook against the current SessionStart receipt."""
    return run_raw_turn_hook(
        {
            "session_id": session_id,
            "turn_id": turn_id,
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        },
        plugin_root=plugin_root,
        environment_overrides=environment_overrides,
    )


def run_raw_turn_hook(
    payload: dict[str, object],
    *,
    plugin_root: Path = PLUGIN_ROOT,
    environment_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run the prompt hook with one exact JSON input object."""
    environment = dict(os.environ)
    environment["PLUGIN_ROOT"] = str(plugin_root)
    environment.update(environment_overrides or {})
    result = subprocess.run(
        [sys.executable, str(plugin_root / "hooks" / "user_prompt_submit.py")],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        env=environment,
        check=True,
    )
    assert result.stderr == ""
    output: object = json.loads(result.stdout)
    assert isinstance(output, dict)
    return output


def read_json_object(path: Path) -> dict[str, object]:
    """Read one test JSON object."""
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def evidence_tree_snapshot(project: Path) -> dict[str, str]:
    """Return a digest snapshot of governance evidence files."""
    snapshot: dict[str, str] = {}
    for root in (
        project / ".work-governance" / "evidence",
        project / ".work-governance" / "_Plan" / ".evidence",
    ):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                snapshot[path.relative_to(project).as_posix()] = sha256_bytes(path.read_bytes())
    return snapshot


def read_plan_frontmatter(project: Path, plan_id: str) -> dict[str, object]:
    """Read one admitted Markdown Plan frontmatter mapping."""
    plan = project / ".work-governance" / "_Plan" / f"{plan_id}.md"
    _, raw, _body = plan.read_text(encoding="utf-8").split("---\n", 2)
    payload: object = yaml.safe_load(raw)
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def intake_records_for_assertion(frontmatter: dict[str, object]) -> list[dict[str, object]]:
    """Read legacy intake records or the bounded protocol-v2 current anchor."""
    intake = cast(dict[str, object], frontmatter["intake"])
    if intake.get("protocol_version") == 2:
        return [cast(dict[str, object], intake["current"])]
    return cast(list[dict[str, object]], intake["records"])


def write_plan_frontmatter(
    project: Path,
    plan_id: str,
    frontmatter: dict[str, object],
) -> None:
    """Rewrite one test Plan while preserving its Markdown body."""
    plan = project / ".work-governance" / "_Plan" / f"{plan_id}.md"
    _, _raw, body = plan.read_text(encoding="utf-8").split("---\n", 2)
    plan.write_text(
        f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n{body}",
        encoding="utf-8",
    )


def rewrite_plan_with_pyyaml_escaped_continuation(project: Path, plan_id: str) -> None:
    """Inject the escaped quoted-scalar shape produced by PyYAML line wrapping."""
    plan = project / ".work-governance" / "_Plan" / f"{plan_id}.md"
    text = plan.read_text(encoding="utf-8")
    old = "  validation_standard: Current intake covers the exact target.\n"
    new = "\n".join(
        [
            '  validation_standard: "Risk feature hit \\u5DF2\\',
            "    \\u7531 fallback\\",
            '    \\ text tied."',
        ]
    )
    if old not in text:
        raise AssertionError("validation_standard fixture line drifted")
    plan.write_text(text.replace(old, new + "\n", 1), encoding="utf-8")


def runtime_controller(project: Path) -> tuple[Path, str]:
    """Return the current runtime controller and SessionStart receipt digest."""
    receipt_path = project / ".work-governance" / "bootstrap-state.json"
    receipt = read_json_object(receipt_path)
    return (
        project / cast(str, receipt["controller_ref"]),
        sha256_bytes(receipt_path.read_bytes()),
    )


def patch_runtime_controller_for_legacy_schema_tests(project: Path) -> None:
    """Patch the runtime controller copy so legacy v4 intake tests stay scoped."""
    receipt_path = project / ".work-governance" / "bootstrap-state.json"
    receipt = read_json_object(receipt_path)
    bundle = project / cast(str, receipt["runtime_bundle_ref"])
    controller = bundle / "workctl_modules" / "kernel" / "controller.py"
    if not controller.is_file():
        controller = project / cast(str, receipt["controller_ref"])
    manifest_path = bundle / "manifest.json"
    controller_source = controller.read_text(encoding="utf-8")
    contract_state_marker = (
        "def contract_state(frontmatter: dict[str, Any]) -> str:\n"
        '    """Return the current-schema state independently from Plan authority."""\n'
        '    schema_version = frontmatter.get("schema_version")\n'
        '    status = frontmatter.get("status")\n'
        "    if schema_version == CURRENT_PLAN_SCHEMA_VERSION:\n"
        '        return "PLAN_CONTRACT_READY"\n'
        '    if status not in {"complete", "retired"}:\n'
        '        return "PLAN_SCHEMA_REFRESH_REQUIRED"\n'
        '    return "PLAN_CONTRACT_LEGACY_READABLE"\n'
    )
    legacy_contract_state = (
        "def contract_state(frontmatter: dict[str, Any]) -> str:\n"
        '    """Return the schema-cutover state independently from Plan authority."""\n'
        '    schema_version = frontmatter.get("schema_version")\n'
        "    if schema_version == 5:\n"
        '        return "PLAN_CONTRACT_READY"\n'
        "    if schema_version == 4:\n"
        '        return "PLAN_CONTRACT_READY"\n'
        "    if (\n"
        "        schema_version == 3\n"
        '        and frontmatter.get("status") not in {"complete", "retired"}\n'
        "    ):\n"
        '        return "PLAN_CONTRACT_UPGRADE_REQUIRED"\n'
        '    return "PLAN_CONTRACT_LEGACY_READABLE"\n'
    )
    gate_marker = (
        "def enforce_active_contract_gate(args: argparse.Namespace, root: Path) -> None:\n"
        '    """Allow only current-schema refresh writes for an outdated active Plan."""\n'
    )
    ready_marker = (
        "def require_plan_contract_ready(frontmatter: dict[str, Any]) -> None:\n"
        '    """Block ordinary writes from silently trusting an outdated active contract."""\n'
    )
    if contract_state_marker not in controller_source:
        raise AssertionError("turn-intake contract-state patch marker drifted")
    if gate_marker not in controller_source:
        raise AssertionError("turn-intake gate patch marker drifted")
    if ready_marker not in controller_source:
        raise AssertionError("turn-intake contract-ready patch marker drifted")
    controller_source = controller_source.replace(contract_state_marker, legacy_contract_state, 1)
    controller_source = controller_source.replace(gate_marker, gate_marker + "    return\n", 1)
    controller_source = controller_source.replace(ready_marker, ready_marker + "    return\n", 1)
    controller.write_text(controller_source, encoding="utf-8")
    controller_sha256 = sha256_bytes(controller.read_bytes())
    manifest = read_json_object(manifest_path)
    receipt_controller_sha256 = cast(str, receipt["controller_sha256"])
    if controller.name == "workctl.py":
        manifest["controller_sha256"] = controller_sha256
        receipt_controller_sha256 = controller_sha256
    else:
        module_files = manifest.get("module_files", [])
        if isinstance(module_files, list):
            for entry in module_files:
                if (
                    isinstance(entry, dict)
                    and entry.get("path") == "workctl_modules/kernel/controller.py"
                ):
                    entry["sha256"] = controller_sha256
                    break
            else:
                raise AssertionError("runtime bundle kernel controller manifest entry missing")
        else:
            raise AssertionError("runtime bundle module_files drifted")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_sha256 = sha256_bytes(manifest_path.read_bytes())
    receipt_paths = [
        receipt_path,
        *(
            project / ".work-governance" / "runtime" / "sessions"
        ).glob("*/bootstrap-state.json"),
    ]
    for candidate in receipt_paths:
        payload = read_json_object(candidate)
        payload["controller_sha256"] = receipt_controller_sha256
        payload["runtime_manifest_sha256"] = manifest_sha256
        candidate.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def run_controller(
    project: Path,
    *arguments: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the receipt-bound runtime controller for one test project."""
    controller, receipt_sha256 = runtime_controller(project)
    result = subprocess.run(
        [
            sys.executable,
            str(controller),
            "--receipt-sha256",
            receipt_sha256,
            *arguments,
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"workctl failed: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def strict_admission_plan(
    plan_id: str,
    *,
    unknowns: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build a compact schema-v4 Plan for intake contract probes."""
    created_at = "2026-07-29T00:00:00Z"
    unknown_items = unknowns or []
    task_one_unknowns = [
        cast(str, item["id"])
        for item in unknown_items
        if isinstance(item.get("blocks"), list)
        and "task:T-001" in cast(list[object], item["blocks"])
    ]
    return {
        "schema_version": 4,
        "plan_id": plan_id,
        "title": "Turn intake test Plan",
        "status": "active",
        "mode": "autonomous",
        "revision": 1,
        "created_at": created_at,
        "updated_at": created_at,
        "goal": {
            "statement": "Prove trusted per-turn intake.",
            "success_conditions": ["Advancement uses the current turn decision."],
        },
        "contract": {
            "revision": 1,
            "confirmation_id": "C-ADMISSION",
            "confirmed_ref": "user:test-intake-admission",
        },
        "scope": {"include": ["Test intake."], "exclude": []},
        "confirmations": {
            "required": [
                {
                    "id": "C-ADMISSION",
                    "description": "Admit intake test Plan.",
                    "status": "accepted",
                    "ref": "user:test-intake-admission",
                    "accepted_at": created_at,
                }
            ]
        },
        "unknowns": unknown_items,
        "obligations": [{"id": "O-001", "description": "Use current intake.", "status": "pending"}],
        "tasks": [
            {
                "id": "T-001",
                "description": "Advance guarded work.",
                "status": "pending",
                "unknowns": task_one_unknowns,
                "expected_evidence_delta": "T-001 advances only under current intake.",
            },
            {
                "id": "T-002",
                "description": "Exercise an unrelated task.",
                "status": "pending",
                "unknowns": [],
                "expected_evidence_delta": "Unrelated exact targets remain available.",
            },
        ],
        "validations": [
            {
                "id": "V-001",
                "description": "Verify current-turn behavior.",
                "status": "pending",
                "provenance": {
                    "kind": "confirmed-obligation",
                    "source_ref": "user:test-intake-contract",
                },
            }
        ],
        "artifacts": [{"id": "A-001", "path": "result.txt", "status": "pending"}],
        "authority": {
            "model": "single-active",
            "state": "governed",
            "canonical_plan_id": plan_id,
            "sources": [],
            "confirmations": {},
        },
        "delivery": {
            "status": "pending",
            "boundary": "local-test",
            "evidence_ref": "project:not-yet-delivered",
        },
        "activation": {
            "status": "not_required",
            "current_ref": "not-applicable",
            "target_ref": "not-applicable",
            "decision_ref": "user:test-no-activation",
        },
        "route": {
            "route_status": "active",
            "slice_status": "admitted",
            "next_phase": "Exercise guarded advancement.",
            "validation_standard": "Current intake covers the exact target.",
            "confirmation_gate": "none",
        },
        "handoff": {
            "route_status": "active",
            "next_step": "Exercise guarded advancement.",
        },
        "revision_history": [
            {
                "revision": 1,
                "kind": "admission",
                "changed_at": created_at,
                "rationale": "Admit the exact test contract.",
                "confirmation_id": "C-ADMISSION",
            }
        ],
    }


def prepare_admitted_project(
    tmp_path: Path,
    *,
    unknowns: list[dict[str, object]] | None = None,
    prepared_plan: dict[str, object] | None = None,
    admission_env: dict[str, str] | None = None,
    expect_admission_success: bool = True,
    legacy_contract_compat: bool = True,
) -> tuple[Path, str]:
    """Bootstrap and transactionally admit one schema-v4 test Plan."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    session_id = "session-intake"
    run_session_hook(project, fake_bin, session_id)
    if legacy_contract_compat:
        patch_runtime_controller_for_legacy_schema_tests(project)
    plan = prepared_plan or strict_admission_plan("PLAN-20260729-001", unknowns=unknowns)
    plan_id = cast(str, plan["plan_id"])
    unknown_items = cast(list[dict[str, object]], plan.get("unknowns", []))
    candidate = project / "candidate.md"
    candidate.write_text(
        f"---\n{yaml.safe_dump(plan, sort_keys=False)}---\n# Intake test Plan\n",
        encoding="utf-8",
    )
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-admission",
        prompt="admit the strict test Plan",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])
    route_blocker = next(
        (
            item
            for item in unknown_items
            if item.get("status") == "open"
            and item.get("owner") == "user"
            and item.get("impact") == "blocking"
            and isinstance(item.get("blocks"), list)
            and "route" in cast(list[object], item["blocks"])
        ),
        None,
    )
    initial_decision = "ask" if route_blocker is not None else "proceed"
    intake_command = [
        "intake",
        "receipt",
        "--turn-receipt-sha256",
        turn_sha256,
        "--classification",
        "plan_controlled",
        "--decision",
        initial_decision,
        "--rationale",
        "The exact initial Plan contract has an explicit intake decision.",
        "--targets",
        "route",
        "--candidate-plan",
        str(candidate),
    ]
    if route_blocker is not None:
        intake_command.extend(["--current-unknown-id", cast(str, route_blocker["id"])])
    intake_result = run_controller(
        project,
        *intake_command,
    )
    intake: object = json.loads(intake_result.stdout)
    assert isinstance(intake, dict)
    manifest = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": plan_id.replace("PLAN-", "ADM-"),
        "prepared_plan": candidate.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_bytes(candidate.read_bytes()),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:test-intake-admission",
        "intake": intake,
    }
    manifest_path = project / "admission.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    run_controller(
        project,
        "plan",
        "admit",
        "apply",
        "--manifest",
        str(manifest_path),
        check=expect_admission_success,
        env=admission_env,
    )
    return project, session_id


def issue_intake(
    project: Path,
    *,
    session_id: str,
    turn_id: str,
    decision: str,
    targets: list[str],
    expected_revision: int | None = None,
    current_unknown_id: str | None = None,
) -> tuple[dict[str, object], Path, str]:
    """Issue a turn, generate an intake proposal, and optionally record it."""
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id=turn_id,
        prompt=f"request for {turn_id}",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])
    command = [
        "intake",
        "receipt",
        "--turn-receipt-sha256",
        turn_sha256,
        "--classification",
        "plan_controlled",
        "--decision",
        decision,
        "--rationale",
        f"Decision for {turn_id}.",
    ]
    for target in targets:
        command.extend(["--targets", target])
    if current_unknown_id is not None:
        command.extend(["--current-unknown-id", current_unknown_id])
    result = run_controller(project, *command)
    payload: object = json.loads(result.stdout)
    assert isinstance(payload, dict)
    proposal = cast(dict[str, object], payload)
    manifest = project / f"{turn_id}-intake.json"
    manifest.write_text(
        json.dumps(proposal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if expected_revision is not None:
        run_controller(
            project,
            "plan",
            "intake",
            "record",
            "--manifest",
            str(manifest),
            "--expected-revision",
            str(expected_revision),
        )
    return proposal, manifest, turn_sha256


def make_terminal_predecessor(project: Path) -> dict[str, object]:
    """Grandfather one admitted Plan as a complete rollover predecessor."""
    plan_id = "PLAN-20260729-001"
    frontmatter = read_plan_frontmatter(project, plan_id)
    frontmatter["status"] = "complete"
    for field in ("obligations", "tasks", "validations"):
        for item in cast(list[dict[str, object]], frontmatter[field]):
            item["status"] = "verified"
    for artifact in cast(list[dict[str, object]], frontmatter["artifacts"]):
        artifact["status"] = "final"
    frontmatter["delivery"] = {
        "status": "complete",
        "boundary": "local-test",
        "evidence_ref": "project:terminal-predecessor",
    }
    frontmatter["activation"] = {
        "status": "not_required",
        "current_ref": "not-applicable",
        "target_ref": "not-applicable",
        "decision_ref": "user:test-no-activation",
    }
    frontmatter["route"] = {
        "route_status": "terminal",
        "slice_status": "complete",
        "next_phase": "none",
        "validation_standard": "The predecessor contract is complete.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {
        "route_status": "terminal",
        "next_step": "none",
    }
    write_plan_frontmatter(project, plan_id, frontmatter)
    return frontmatter


def prepare_strict_rollover(
    project: Path,
    *,
    session_id: str,
) -> tuple[Path, dict[str, object]]:
    """Prepare and confirmation-bind one strict successor rollover manifest."""
    source = make_terminal_predecessor(project)
    target_id = "PLAN-20260730-001"
    target = strict_admission_plan(target_id)
    target["title"] = "Strict successor"
    prepared = project / "successor.md"
    prepared.write_text(
        f"---\n{yaml.safe_dump(target, sort_keys=False)}---\n# Strict successor\n",
        encoding="utf-8",
    )
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-rollover",
        prompt="activate the exact strict successor",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])
    intake = json.loads(
        run_controller(
            project,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            turn_sha256,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            "The successor contract is exact.",
            "--targets",
            "route",
            "--candidate-plan",
            str(prepared),
        ).stdout
    )
    source_path = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    index_path = project / ".work-governance" / "_Plan" / "index.yaml"
    manifest: dict[str, object] = {
        "schema_version": 1,
        "rollover_id": "ROL-20260730-001",
        "source_plan": {
            "path": ".work-governance/_Plan/PLAN-20260729-001.md",
            "plan_id": "PLAN-20260729-001",
            "revision": source["revision"],
            "sha256": sha256_bytes(source_path.read_bytes()),
        },
        "index_baseline": {
            "active_plan_id": "PLAN-20260729-001",
            "sha256": sha256_bytes(index_path.read_bytes()),
        },
        "target_plan": {
            "prepared_file": prepared.name,
            "plan_id": target_id,
            "revision": 1,
            "sha256": sha256_bytes(prepared.read_bytes()),
        },
        "intake": intake,
        "confirmations": {},
    }
    manifest_path = project / "rollover.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    dry_run = json.loads(
        run_controller(
            project,
            "plan",
            "rollover",
            "apply",
            "--manifest",
            str(manifest_path),
            "--dry-run",
        ).stdout
    )
    cast(dict[str, object], manifest["confirmations"])["rollover"] = {
        "id": "C-PLAN-ROLLOVER",
        "ref": "user:test-rollover",
        "accepted_at": "2026-07-30T00:00:00Z",
        "evidence_sha256": dry_run["proposal_sha256"],
    }
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return manifest_path, cast(dict[str, object], dry_run)


def prepare_strict_contract_upgrade(
    tmp_path: Path,
) -> tuple[Path, str, Path]:
    """Create a schema-v3 authority and a current-turn strict upgrade manifest."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    session_id = "session-upgrade"
    run_session_hook(project, fake_bin, session_id)
    patch_runtime_controller_for_legacy_schema_tests(project)
    plan_id = "PLAN-20260729-001"
    source = strict_admission_plan(plan_id)
    source["schema_version"] = 3
    source.pop("goal")
    source.pop("contract")
    source.pop("revision_history")
    confirmations = cast(
        dict[str, list[dict[str, object]]],
        source["confirmations"],
    )
    confirmations["required"].append(
        {
            "id": "C-UPGRADE",
            "description": "Upgrade the legacy contract.",
            "status": "accepted",
            "ref": "user:test-upgrade",
            "accepted_at": "2026-07-30T00:00:00Z",
        }
    )
    plan_root = project / ".work-governance" / "_Plan"
    plan_root.mkdir(parents=True, exist_ok=True)
    plan_path = plan_root / f"{plan_id}.md"
    plan_path.write_text(
        f"---\n{yaml.safe_dump(source, sort_keys=False)}---\n# Legacy contract\n",
        encoding="utf-8",
    )
    index = {
        "schema_version": 1,
        "active_plan_id": plan_id,
        "plans": [
            {
                "id": plan_id,
                "path": plan_path.name,
                "title": source["title"],
                "created_at": source["created_at"],
            }
        ],
    }
    (plan_root / "index.yaml").write_text(
        yaml.safe_dump(index, sort_keys=False),
        encoding="utf-8",
    )
    evidence_input = project / "upgrade-evidence.json"
    evidence_input.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "work-governance-evidence",
                "plan_id": plan_id,
                "subject": "contract-upgrade",
                "created_at": "2026-07-30T00:01:00Z",
                "producer_ref": "runtime:test-upgrade",
                "items": [{"ref": "project:legacy-plan", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    evidence_record = json.loads(
        run_controller(
            project,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(evidence_input),
        ).stdout
    )
    goal = {
        "statement": "Upgrade to a strict current-turn contract.",
        "success_conditions": ["The staged schema-v4 Plan contains initial intake."],
    }
    candidate = json.loads(json.dumps(source))
    candidate["schema_version"] = 4
    candidate["goal"] = goal
    candidate["contract"] = {
        "revision": 1,
        "confirmation_id": "C-UPGRADE",
        "confirmed_ref": "user:test-upgrade",
    }
    candidate["unknowns"] = []
    candidate["revision"] = 2
    candidate["revision_history"] = [
        {
            "revision": 2,
            "kind": "contract-upgrade",
            "changed_at": "2026-07-30T00:01:00Z",
            "rationale": "Upgrade the test contract.",
            "confirmation_id": "C-UPGRADE",
            "evidence_manifest": evidence_record["path"],
        }
    ]
    candidate_path = project / "upgrade-candidate.md"
    candidate_path.write_text(
        f"---\n{yaml.safe_dump(candidate, sort_keys=False)}---\n# Upgraded contract\n",
        encoding="utf-8",
    )
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-upgrade",
        prompt="upgrade the exact legacy contract",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])
    intake = json.loads(
        run_controller(
            project,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            turn_sha256,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            "The upgraded contract is exact.",
            "--targets",
            "route",
            "--candidate-plan",
            str(candidate_path),
        ).stdout
    )
    manifest = {
        "schema_version": 1,
        "kind": "plan-contract-upgrade",
        "transaction_id": "UPG-20260730-001",
        "plan_id": plan_id,
        "expected_revision": 1,
        "plan_sha256": sha256_bytes(plan_path.read_bytes()),
        "confirmation_id": "C-UPGRADE",
        "confirmation_ref": "user:test-upgrade",
        "evidence_manifest": evidence_record["path"],
        "goal": goal,
        "unknowns": [],
        "task_metadata": {
            "T-001": {
                "unknowns": [],
                "expected_evidence_delta": ("T-001 advances only under current intake."),
            },
            "T-002": {
                "unknowns": [],
                "expected_evidence_delta": ("Unrelated exact targets remain available."),
            },
        },
        "validation_provenance": {
            "V-001": {
                "kind": "confirmed-obligation",
                "source_ref": "user:test-intake-contract",
            }
        },
        "intake": intake,
    }
    manifest_path = project / "upgrade.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return project, session_id, manifest_path


def test_user_prompt_submit_hook_is_registered() -> None:
    """The plugin no longer registers a per-turn receipt hook."""
    payload: dict[str, object] = json.loads(HOOKS_CONFIG.read_text(encoding="utf-8"))
    hooks = payload["hooks"]

    assert isinstance(hooks, dict)
    assert hooks == {}


def test_controller_exposes_turn_bound_intake_receipt_command() -> None:
    """The controller must expose the read-only intake receipt API."""
    result = subprocess.run(
        [sys.executable, str(WORKCTL), "intake", "receipt", "--help"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--turn-receipt-sha256" in result.stdout
    assert "--classification" in result.stdout
    assert "--decision" in result.stdout
    assert "--targets" in result.stdout


def test_schema_v4_risk_acceptance_requires_the_current_receipt_bound_user_turn(
    tmp_path: Path,
) -> None:
    """A degraded review is released only by the exact current-turn risk decision."""
    project, session_id = prepare_admitted_project(tmp_path)
    plan_id = "PLAN-20260729-001"
    frontmatter = read_plan_frontmatter(project, plan_id)
    frontmatter["independent_validation"] = {
        "required": True,
        "state": "pending",
        "required_modes": ["plan_challenge", "artifact_review", "evidence_audit"],
        "implementation_context_ref": "context:implementation",
        "reviews": [
            {
                "mode": "plan_challenge",
                "state": "pending",
                "blocks": ["route"],
                "review_context_ref": "context:pending-plan-challenge",
                "reviewed_contract_sha256": None,
                "reviewed_artifacts": [],
                "findings": [],
                "evidence_ref": "project:pending-plan-challenge",
                "evidence_sha256": None,
            },
            {
                "mode": "artifact_review",
                "state": "pending",
                "blocks": ["task:T-001", "activation", "route"],
                "review_context_ref": "context:pending-artifact-review",
                "reviewed_contract_sha256": None,
                "reviewed_artifacts": [],
                "findings": [],
                "evidence_ref": "project:pending-artifact-review",
                "evidence_sha256": None,
            },
            {
                "mode": "evidence_audit",
                "state": "pending",
                "blocks": ["route"],
                "review_context_ref": "context:pending-evidence-audit",
                "reviewed_contract_sha256": None,
                "reviewed_artifacts": [],
                "findings": [],
                "evidence_ref": "project:pending-evidence-audit",
                "evidence_sha256": None,
            },
        ],
    }
    write_plan_frontmatter(project, plan_id, frontmatter)
    _review_intake, _review_manifest, review_turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-record-degraded-review",
        decision="proceed",
        targets=["task:T-001"],
        expected_revision=1,
    )
    review_frontmatter = read_plan_frontmatter(project, plan_id)
    review_records = intake_records_for_assertion(review_frontmatter)
    review_intake_sha256 = cast(str, review_records[-1]["record_sha256"])
    evidence_input = project / "degraded-review-evidence.json"
    evidence_input.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "work-governance-evidence",
                "plan_id": plan_id,
                "subject": "independent-review:artifact_review",
                "created_at": "2026-07-31T10:03:00+00:00",
                "producer_ref": "context:implementation",
                "items": [
                    {"ref": "project:reviewed-contract", "sha256": "a" * 64},
                    {"ref": "git:candidate", "sha256": "b" * 64},
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence = cast(
        dict[str, object],
        json.loads(
            run_controller(
                project,
                "plan",
                "evidence",
                "record",
                "--manifest",
                str(evidence_input),
            ).stdout
        ),
    )
    review_manifest = project / "degraded-review.yaml"
    review_manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "independent-review",
                "plan_id": plan_id,
                "mode": "artifact_review",
                "state": "degraded",
                "implementation_context_ref": "context:implementation",
                "review_context_ref": "context:implementation",
                "reviewed_contract": {
                    "ref": "project:reviewed-contract",
                    "sha256": "a" * 64,
                },
                "reviewed_artifacts": [{"ref": "git:candidate", "sha256": "b" * 64}],
                "findings": [],
                "evidence_manifest": evidence["path"],
                "isolation_attestation": None,
                "bootstrap_evidence": [],
                "risk_acceptance_confirmation_id": "C-REVIEW-RISK",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    run_controller(
        project,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(review_manifest),
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        review_turn_sha256,
        "--expected-intake-sha256",
        review_intake_sha256,
    )
    basis_sha256 = cast(str, evidence["sha256"])
    run_controller(
        project,
        "plan",
        "confirmation",
        "add",
        "--confirmation-id",
        "C-REVIEW-RISK",
        "--description",
        "Accept the exact degraded independent-review risk.",
        "--intervention-kind",
        "external_authority",
        "--blocks",
        "task:T-001",
        "--blocks",
        "activation",
        "--blocks",
        "route",
        "--basis-ref",
        f"evidence:{evidence['path']}",
        "--basis-sha256",
        basis_sha256,
        "--expected-revision",
        "3",
    )
    proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-review-risk-decision",
        decision="proceed",
        targets=["task:T-001", "activation", "route"],
        expected_revision=4,
    )
    frontmatter = read_plan_frontmatter(project, plan_id)
    records = intake_records_for_assertion(frontmatter)
    intake_sha256 = cast(str, records[-1]["record_sha256"])
    fabricated = run_controller(
        project,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-REVIEW-RISK",
        "--ref",
        "user:fabricated-review-risk-decision",
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "5",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )
    accepted = run_controller(
        project,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-REVIEW-RISK",
        "--ref",
        cast(str, proposal["request_ref"]),
        "--evidence-sha256",
        basis_sha256,
        "--expected-revision",
        "5",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
    )
    started = run_controller(
        project,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "6",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
    )
    revised = read_plan_frontmatter(project, plan_id)
    confirmations = cast(
        list[dict[str, object]],
        cast(dict[str, object], revised["confirmations"])["required"],
    )
    risk = next(item for item in confirmations if item["id"] == "C-REVIEW-RISK")

    assert "CONFIRMATION_REF_CURRENT_TURN_REQUIRED" in fabricated.stderr
    assert "CONFIRMATION_DECIDED C-REVIEW-RISK accepted" in accepted.stdout
    assert "TASK_UPDATED T-001 in_progress" in started.stdout
    assert risk["ref"] == proposal["request_ref"]


def test_turn_hook_hashes_exact_utf8_prompt_and_atomically_replaces(
    tmp_path: Path,
) -> None:
    """Each new turn replaces the prior receipt and binds exact prompt bytes."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    run_session_hook(project, fake_bin, "session-alpha")
    session_receipt = project / ".work-governance" / "bootstrap-state.json"
    turn_receipt = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    prompt = "药材\n🌿"

    first_output = run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-one",
        prompt=prompt,
    )
    first = read_json_object(turn_receipt)
    first_digest = cast(str, first["receipt_sha256"])

    assert first["prompt_sha256"] == sha256_bytes(prompt.encode("utf-8"))
    assert first["session_start_receipt_sha256"] == sha256_bytes(session_receipt.read_bytes())
    assert first["request_ref"] == (
        "user:session/session-alpha/turn/turn-one/sha256/" + sha256_bytes(prompt.encode("utf-8"))
    )
    hook_specific = first_output["hookSpecificOutput"]
    assert isinstance(hook_specific, dict)
    context = cast(dict[str, object], hook_specific)["additionalContext"]
    assert isinstance(context, str)
    assert first_digest in context

    run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-two",
        prompt="second request",
    )
    second = read_json_object(turn_receipt)

    assert second["turn_id"] == "turn-two"
    assert second["receipt_sha256"] != first_digest
    assert not list(turn_receipt.parent.glob(f".{turn_receipt.name}.*"))


def test_turn_hook_stays_trusted_after_pyyaml_continuation_plan_resume(
    tmp_path: Path,
) -> None:
    """A PyYAML-wrapped active Plan must not cause SESSION_RECEIPT_MISMATCH."""
    fake_bin = tmp_path / "resume-bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    session_id = "session-intake"
    run_session_hook(project, fake_bin, session_id)
    plan_id = "PLAN-20260729-001"
    plan = strict_admission_plan(plan_id)
    plan_dir = project / ".work-governance" / "_Plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "index.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "active_plan_id": plan_id,
                "plans": [{"id": plan_id, "path": f"{plan_id}.md"}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (plan_dir / f"{plan_id}.md").write_text(
        f"---\n{yaml.safe_dump(plan, sort_keys=False)}---\n# Intake test Plan\n",
        encoding="utf-8",
    )
    rewrite_plan_with_pyyaml_escaped_continuation(project, plan_id)

    session_output = run_session_hook(
        project,
        fake_bin,
        session_id,
        source="resume",
        environment_overrides={"WORK_GOVERNANCE_DISABLE_PYYAML": "1"},
    )
    turn_output = run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-after-pyyaml-continuation",
        prompt="continue after fallback YAML continuation",
        environment_overrides={"WORK_GOVERNANCE_DISABLE_PYYAML": "1"},
    )
    session_context = cast(dict[str, object], session_output["hookSpecificOutput"])[
        "additionalContext"
    ]
    turn_context = cast(dict[str, object], turn_output["hookSpecificOutput"])[
        "additionalContext"
    ]
    current_turn = read_json_object(
        project
        / ".work-governance"
        / "runtime"
        / "sessions"
        / session_id
        / "current-turn-receipt.json"
    )

    assert isinstance(session_context, str)
    assert isinstance(turn_context, str)
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in session_context
    assert "WORK_GOVERNANCE_TURN_RECEIPT READY" in turn_context
    assert "SESSION_RECEIPT_MISMATCH" not in turn_context
    assert current_turn["kind"] == "work-governance-current-turn-receipt"


def test_session_receipts_are_isolated_and_compaction_preserves_active_turn(
    tmp_path: Path,
) -> None:
    """Another session and same-session compact cannot supersede a valid turn."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()

    run_session_hook(project, fake_bin, "session-alpha")
    alpha_session = (
        project
        / ".work-governance"
        / "runtime"
        / "sessions"
        / "session-alpha"
        / "bootstrap-state.json"
    )
    run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-alpha",
        prompt="alpha request",
    )
    alpha_turn = alpha_session.parent / "current-turn-receipt.json"
    alpha_session_bytes = alpha_session.read_bytes()
    alpha_turn_bytes = alpha_turn.read_bytes()

    run_session_hook(project, fake_bin, "session-beta")
    run_turn_hook(
        project,
        session_id="session-beta",
        turn_id="turn-beta",
        prompt="beta request",
    )
    beta_session = (
        project
        / ".work-governance"
        / "runtime"
        / "sessions"
        / "session-beta"
        / "bootstrap-state.json"
    )
    beta_turn = beta_session.parent / "current-turn-receipt.json"

    assert alpha_session.read_bytes() == alpha_session_bytes
    assert alpha_turn.read_bytes() == alpha_turn_bytes
    assert beta_session.is_file()
    assert beta_turn.is_file()

    run_session_hook(project, fake_bin, "session-alpha", source="compact")

    assert alpha_session.read_bytes() == alpha_session_bytes
    assert alpha_turn.read_bytes() == alpha_turn_bytes
    alpha_receipt = read_json_object(alpha_session)
    alpha_turn_receipt = read_json_object(alpha_turn)
    controller = project / cast(str, alpha_receipt["controller_ref"])
    result = subprocess.run(
        [
            sys.executable,
            str(controller),
            "--receipt-sha256",
            sha256_bytes(alpha_session_bytes),
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            cast(str, alpha_turn_receipt["receipt_sha256"]),
            "--classification",
            "no_plan",
            "--decision",
            "proceed",
            "--rationale",
            "The isolated turn remains current after compaction.",
            "--targets",
            "route",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["request_ref"] == alpha_turn_receipt["request_ref"]


def test_same_session_resumes_on_candidate_after_older_build_receipt(
    tmp_path: Path,
) -> None:
    """A reopened session replaces its old build authority and accepts a fresh turn."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    old_plugin = tmp_path / "old-plugin"
    shutil.copytree(PLUGIN_ROOT, old_plugin)
    old_manifest_path = old_plugin / ".codex-plugin" / "plugin.json"
    old_manifest = read_json_object(old_manifest_path)
    old_manifest["version"] = "1.0.6+codex.old-session-probe"
    old_manifest_path.write_text(
        json.dumps(old_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    candidate_manifest = read_json_object(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    candidate_build = cast(str, candidate_manifest["version"])
    session_id = "reopened-older-build-session"

    run_session_hook(project, fake_bin, session_id, plugin_root=old_plugin)
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="old-turn",
        prompt="old build request",
        plugin_root=old_plugin,
    )
    session_path = (
        project / ".work-governance" / "runtime" / "sessions" / session_id / "bootstrap-state.json"
    )
    old_receipt_bytes = session_path.read_bytes()
    old_receipt = read_json_object(session_path)

    resumed = run_session_hook(project, fake_bin, session_id, source="resume")
    candidate_receipt = read_json_object(session_path)
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="candidate-turn",
        prompt="continue the existing goal on the candidate",
    )
    candidate_turn = read_json_object(session_path.parent / "current-turn-receipt.json")
    controller_status = json.loads(run_controller(project, "intake", "status").stdout)
    hook_specific = cast(dict[str, object], resumed["hookSpecificOutput"])
    context = cast(str, hook_specific["additionalContext"])

    assert candidate_build.startswith("1.1.0+codex.")
    assert old_receipt["plugin_build"] == "1.0.6+codex.old-session-probe"
    assert candidate_receipt["plugin_build"] == candidate_build
    assert session_path.read_bytes() != old_receipt_bytes
    assert candidate_receipt["controller_ref"] != old_receipt["controller_ref"]
    assert candidate_turn["plugin_build"] == candidate_build
    assert candidate_turn["session_start_receipt_sha256"] == sha256_bytes(session_path.read_bytes())
    assert controller_status["authority_state"] == "UNMANAGED_EMPTY"
    assert f"build={candidate_build}" in context
    assert "WORK_GOVERNANCE_BOOTSTRAP READY" in context


def test_turn_hook_invalidates_prior_receipt_before_field_validation(tmp_path: Path) -> None:
    """Even malformed later-turn input atomically invalidates the prior receipt."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    run_session_hook(project, fake_bin, "session-alpha")
    run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-valid",
        prompt="first governed request",
    )
    turn_path = (
        project
        / ".work-governance"
        / "runtime"
        / "sessions"
        / "session-alpha"
        / "current-turn-receipt.json"
    )
    prior = read_json_object(turn_path)
    prior_sha256 = cast(str, prior["receipt_sha256"])

    output = run_raw_turn_hook(
        {
            "session_id": "session-alpha",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "malformed later request",
        }
    )

    hook_specific = output["hookSpecificOutput"]
    assert isinstance(hook_specific, dict)
    context = cast(dict[str, object], hook_specific)["additionalContext"]
    assert isinstance(context, str)
    assert "ENVIRONMENT_BLOCKED" in context
    assert "TURN_ID_REQUIRED" in context
    assert read_json_object(turn_path)["kind"] == "work-governance-current-turn-invalid"

    replay = run_controller(
        project,
        "intake",
        "receipt",
        "--turn-receipt-sha256",
        prior_sha256,
        "--classification",
        "plan_controlled",
        "--decision",
        "proceed",
        "--rationale",
        "Attempt stale receipt replay.",
        "--targets",
        "route",
        check=False,
    )
    assert replay.returncode == 2
    assert "TURN_RECEIPT_INVALID" in replay.stderr


def test_turn_hook_fails_closed_without_managed_session_receipt(
    tmp_path: Path,
) -> None:
    """A missing SessionStart receipt cannot authorize Plan-controlled writes."""
    project = tmp_path / "project"
    project.mkdir()

    output = run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-one",
        prompt="do governed work",
    )

    hook_specific = cast(dict[str, object], output["hookSpecificOutput"])
    context = cast(str, hook_specific["additionalContext"])
    assert "ENVIRONMENT_BLOCKED" in context
    assert "SESSION_RECEIPT_REQUIRED" in context


def test_turn_hook_hashes_empty_prompt_bytes(tmp_path: Path) -> None:
    """The exact official prompt includes the valid empty UTF-8 byte sequence."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    run_session_hook(project, fake_bin, "session-empty")

    run_turn_hook(
        project,
        session_id="session-empty",
        turn_id="turn-empty",
        prompt="",
    )

    turn = read_json_object(project / ".work-governance" / "runtime" / "current-turn-receipt.json")
    assert turn["prompt_sha256"] == sha256_bytes(b"")


def test_no_plan_intake_remains_runtime_only(tmp_path: Path) -> None:
    """A No-Plan turn creates only its replaceable runtime receipt."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    run_session_hook(project, fake_bin, "session-alpha")
    before_files = {
        path.relative_to(project)
        for path in project.rglob("*")
        if path.is_file() or path.is_symlink()
    }

    run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-no-plan",
        prompt="What is two plus two?",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn = read_json_object(turn_path)
    result = run_controller(
        project,
        "intake",
        "receipt",
        "--turn-receipt-sha256",
        cast(str, turn["receipt_sha256"]),
        "--classification",
        "no_plan",
        "--decision",
        "proceed",
        "--rationale",
        "A direct low-risk answer needs no durable Plan.",
        "--targets",
        "route",
    )
    proposal = json.loads(result.stdout)
    after_files = {
        path.relative_to(project)
        for path in project.rglob("*")
        if path.is_file() or path.is_symlink()
    }

    assert proposal["classification"] == "no_plan"
    assert after_files - before_files == {
        Path(".work-governance/runtime/current-turn-receipt.json"),
        Path(".work-governance/runtime/sessions/session-alpha/current-turn-receipt.json"),
    }
    assert not (project / ".work-governance" / "_Plan").exists()
    assert not any((project / ".work-governance" / "logs").iterdir())


def test_redacted_stocklens_replay_keeps_runtime_signals_out_of_plan_revision(
    tmp_path: Path,
) -> None:
    """Explore, continue, and credential-ready signals do not revise the Plan."""
    replay = read_json_object(STOCKLENS_REPLAY)
    events = replay.get("events")
    assert isinstance(events, list)
    assert replay["secrets"] == "[REDACTED]"
    project, session_id = prepare_admitted_project(tmp_path)
    plan_path = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    initial_plan_bytes = plan_path.read_bytes()
    initial = read_plan_frontmatter(project, "PLAN-20260729-001")
    initial_revision = initial["revision"]
    initial_intake = initial["intake"]

    for index, event in enumerate(events, start=1):
        assert isinstance(event, dict)
        prompt = event.get("prompt")
        assert isinstance(prompt, str)
        run_turn_hook(
            project,
            session_id=session_id,
            turn_id=f"turn-replay-{index}",
            prompt=prompt,
        )
        turn = read_json_object(
            project / ".work-governance" / "runtime" / "current-turn-receipt.json"
        )
        proposal = json.loads(
            run_controller(
                project,
                "intake",
                "receipt",
                "--turn-receipt-sha256",
                cast(str, turn["receipt_sha256"]),
                "--classification",
                "no_plan",
                "--decision",
                "proceed",
                "--rationale",
                "The redacted replay signal is runtime-only.",
                "--targets",
                "route",
            ).stdout
        )
        assert proposal["classification"] == "no_plan"
        current = read_plan_frontmatter(project, "PLAN-20260729-001")
        assert current["revision"] == initial_revision
        assert current["intake"] == initial_intake
        assert plan_path.read_bytes() == initial_plan_bytes


def test_controller_rejects_superseded_turn_receipt(tmp_path: Path) -> None:
    """The newest turn invalidates the prior turn digest for intake generation."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_fake_uv(fake_bin)
    project = tmp_path / "project"
    project.mkdir()
    run_session_hook(project, fake_bin, "session-alpha")
    session_receipt = project / ".work-governance" / "bootstrap-state.json"
    session_digest = sha256_bytes(session_receipt.read_bytes())
    session_payload = read_json_object(session_receipt)
    controller = project / cast(str, session_payload["controller_ref"])
    turn_receipt = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-one",
        prompt="first request",
    )
    first_digest = cast(str, read_json_object(turn_receipt)["receipt_sha256"])
    run_turn_hook(
        project,
        session_id="session-alpha",
        turn_id="turn-two",
        prompt="second request",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(controller),
            "--receipt-sha256",
            session_digest,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            first_digest,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            "The request and local path are explicit.",
            "--targets",
            "route",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "TURN_RECEIPT_SUPERSEDED" in result.stderr


def test_strict_admission_injects_and_binds_initial_intake(
    tmp_path: Path,
) -> None:
    """Admission stages the first record and binds every trusted identity axis."""
    project, _session_id = prepare_admitted_project(tmp_path)
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    records = intake_records_for_assertion(frontmatter)
    journal = read_json_object(
        project
        / ".work-governance"
        / "runtime"
        / "plan-admissions"
        / "ADM-20260729-001"
        / "journal.json"
    )
    binding = cast(dict[str, object], journal["intake_binding"])

    assert journal["status"] == "committed"
    assert len(records) == 1
    assert binding["request_ref"] == records[0]["request_ref"]
    assert binding["intake_record_sha256"] == records[0]["record_sha256"]
    assert binding["decision_basis_sha256"] == records[0]["decision_basis_sha256"]
    assert journal["plan_sha256"] != journal["prepared_plan_sha256"]
    assert isinstance(journal["transaction_binding_sha256"], str)


def test_admission_recovery_uses_bound_journal_after_turn_changes(
    tmp_path: Path,
) -> None:
    """Recovery replays bound staging without impersonating the admission turn."""
    project, session_id = prepare_admitted_project(
        tmp_path,
        admission_env={"WORKCTL_TEST_ADMISSION_INTERRUPT_AFTER": "plan-installed"},
        expect_admission_success=False,
    )
    index = project / ".work-governance" / "_Plan" / "index.yaml"
    assert not index.exists()
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-recovery",
        prompt="recover the already bound admission",
    )

    recovered = run_controller(
        project,
        "plan",
        "admit",
        "recover",
        "--transaction-id",
        "ADM-20260729-001",
    )

    assert "PLAN_ADMISSION_COMMITTED" in recovered.stdout
    assert index.is_file()


def test_rollover_successor_is_strict_and_transaction_bound(tmp_path: Path) -> None:
    """A grandfathered predecessor may activate only a strict bound successor."""
    project, session_id = prepare_admitted_project(tmp_path)
    manifest, dry_run = prepare_strict_rollover(
        project,
        session_id=session_id,
    )

    applied = run_controller(
        project,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest),
    )

    assert "ROLLOVER_COMMITTED" in applied.stdout
    successor = read_plan_frontmatter(project, "PLAN-20260730-001")
    records = intake_records_for_assertion(successor)
    journal = yaml.safe_load(
        (project / ".work-governance" / "_Plan" / ".rollovers" / "ROL-20260730-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert records[0]["record_sha256"] == journal["intake_binding"]["intake_record_sha256"]
    assert journal["proposal_sha256"] == dry_run["proposal_sha256"]
    assert journal["status"] == "committed"
    assert journal["confirmation_payload_version"] == 2
    assert isinstance(journal["target_contract_sha256"], str)
    assert isinstance(journal["transaction_binding_sha256"], str)


def test_rollover_rejects_stale_intake_after_confirmation_turn(
    tmp_path: Path,
) -> None:
    """A confirmation turn cannot replay the superseded proposal intake."""
    project, session_id = prepare_admitted_project(tmp_path)
    manifest, _dry_run = prepare_strict_rollover(
        project,
        session_id=session_id,
    )
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-rollover-confirmation",
        prompt="confirm the exact rollover digest",
    )

    blocked = run_controller(
        project,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest),
        check=False,
    )

    assert blocked.returncode == 2
    assert "TURN_RECEIPT_SUPERSEDED" in blocked.stderr
    assert not (
        project / ".work-governance" / "_Plan" / ".rollovers" / "ROL-20260730-001.yaml"
    ).exists()


def test_rollover_confirmation_digest_survives_current_turn_intake_refresh(
    tmp_path: Path,
) -> None:
    """The stable contract confirmation permits a fresh execution intake."""
    project, session_id = prepare_admitted_project(tmp_path)
    manifest_path, initial_dry_run = prepare_strict_rollover(
        project,
        session_id=session_id,
    )
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-rollover-confirmation",
        prompt="confirm the exact rollover digest",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])
    refreshed_intake = json.loads(
        run_controller(
            project,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            turn_sha256,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            "The confirmed successor contract is ready to activate.",
            "--targets",
            "route",
            "--candidate-plan",
            str(project / "successor.md"),
        ).stdout
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["intake"] = refreshed_intake
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    refreshed_dry_run = json.loads(
        run_controller(
            project,
            "plan",
            "rollover",
            "apply",
            "--manifest",
            str(manifest_path),
            "--dry-run",
        ).stdout
    )
    applied = run_controller(
        project,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest_path),
    )
    successor = read_plan_frontmatter(project, "PLAN-20260730-001")
    records = intake_records_for_assertion(successor)

    assert refreshed_dry_run["proposal_sha256"] == initial_dry_run["proposal_sha256"]
    assert "ROLLOVER_COMMITTED" in applied.stdout
    assert "turn-rollover-confirmation" in cast(str, records[0]["request_ref"])


def test_rollover_recovery_replays_bound_successor_across_turns(
    tmp_path: Path,
) -> None:
    """An interrupted rollover recovers from its journal after turn replacement."""
    project, session_id = prepare_admitted_project(tmp_path)
    manifest, _dry_run = prepare_strict_rollover(
        project,
        session_id=session_id,
    )
    interrupted = run_controller(
        project,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    assert "SIMULATED_MIGRATION_INTERRUPT" in interrupted.stderr
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-rollover-recovery",
        prompt="recover the already bound successor",
    )

    recovered = run_controller(
        project,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260730-001",
    )

    assert "ROLLOVER_COMMITTED" in recovered.stdout
    index = yaml.safe_load(
        (project / ".work-governance" / "_Plan" / "index.yaml").read_text(encoding="utf-8")
    )
    assert index["active_plan_id"] == "PLAN-20260730-001"


def test_rollover_recovery_accepts_legacy_confirmation_payload_journal(
    tmp_path: Path,
) -> None:
    """A versionless pre-fix journal remains recoverable after controller upgrade."""
    project, session_id = prepare_admitted_project(tmp_path)
    manifest, _dry_run = prepare_strict_rollover(
        project,
        session_id=session_id,
    )
    interrupted = run_controller(
        project,
        "plan",
        "rollover",
        "apply",
        "--manifest",
        str(manifest),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "rollover-target-plan"},
    )
    assert "SIMULATED_MIGRATION_INTERRUPT" in interrupted.stderr
    journal_path = project / ".work-governance" / "_Plan" / ".rollovers" / "ROL-20260730-001.yaml"
    journal = yaml.safe_load(journal_path.read_text(encoding="utf-8"))
    journal.pop("confirmation_payload_version", None)
    staged_plan = project / cast(str, journal["staged_plan"])
    _, raw_frontmatter, body = staged_plan.read_text(encoding="utf-8").split(
        "---\n",
        2,
    )
    staged_frontmatter = yaml.safe_load(raw_frontmatter)
    unsigned_frontmatter = copy.deepcopy(staged_frontmatter)
    unsigned_confirmations = cast(
        dict[str, object],
        unsigned_frontmatter["confirmations"],
    )
    unsigned_confirmations["required"] = [
        item
        for item in cast(list[dict[str, object]], unsigned_confirmations["required"])
        if item.get("id") != "C-PLAN-ROLLOVER"
    ]
    legacy_target_contract_sha256 = sha256_bytes(
        (
            f"---\n{yaml.safe_dump(unsigned_frontmatter, sort_keys=False)}---\n{body}"
        ).encode()
    )
    assert legacy_target_contract_sha256 != journal["target_contract_sha256"]
    journal["target_contract_sha256"] = legacy_target_contract_sha256
    legacy_payload = {
        "rollover_id": journal["rollover_id"],
        "source_plan": journal["source_plan"],
        "index_baseline": journal["index_baseline"],
        "target_plan": {
            "path": journal["target_path"],
            "plan_id": journal["target_plan_id"],
            "revision": 1,
            "prepared_plan_sha256": journal["prepared_plan_sha256"],
            "target_contract_sha256": legacy_target_contract_sha256,
        },
        "intake_binding": journal["intake_binding"],
    }
    legacy_proposal_sha256 = sha256_bytes(
        json.dumps(
            legacy_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    confirmations = cast(
        list[dict[str, object]],
        cast(dict[str, object], staged_frontmatter["confirmations"])["required"],
    )
    rollover_confirmation = next(item for item in confirmations if item["id"] == "C-PLAN-ROLLOVER")
    rollover_confirmation["evidence_sha256"] = legacy_proposal_sha256
    staged_plan.write_text(
        f"---\n{yaml.safe_dump(staged_frontmatter, sort_keys=False)}---\n{body}",
        encoding="utf-8",
    )
    target_plan_sha256 = sha256_bytes(staged_plan.read_bytes())
    journal["proposal_sha256"] = legacy_proposal_sha256
    journal["target_sha256"] = target_plan_sha256
    cast(dict[str, object], journal["rollover_confirmation"])["evidence_sha256"] = (
        legacy_proposal_sha256
    )
    transaction_binding = {
        "transaction_kind": "plan-rollover",
        "transaction_id": journal["rollover_id"],
        "plan_id": journal["target_plan_id"],
        "prepared_plan_sha256": journal["prepared_plan_sha256"],
        "target_plan_sha256": target_plan_sha256,
        "intake_binding": journal["intake_binding"],
    }
    journal["transaction_binding_sha256"] = sha256_bytes(
        json.dumps(
            transaction_binding,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    target_plan = project / cast(str, journal["target_path"])
    target_plan.write_bytes(staged_plan.read_bytes())
    journal_path.write_text(
        yaml.safe_dump(journal, sort_keys=False),
        encoding="utf-8",
    )

    recovered = run_controller(
        project,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260730-001",
        check=False,
    )

    assert recovered.returncode == 0
    assert "ROLLOVER_COMMITTED" in recovered.stdout


def test_schema_v3_upgrade_injects_strict_initial_intake(tmp_path: Path) -> None:
    """The v3-to-v4 transaction binds and installs its first intake record."""
    project, _session_id, manifest = prepare_strict_contract_upgrade(tmp_path)

    upgraded = run_controller(
        project,
        "plan",
        "contract",
        "upgrade",
        "apply",
        "--manifest",
        str(manifest),
    )

    assert "PLAN_CONTRACT_UPGRADE_COMMITTED" in upgraded.stdout
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    records = intake_records_for_assertion(frontmatter)
    journal = read_json_object(
        project
        / ".work-governance"
        / "runtime"
        / "contract-upgrades"
        / "UPG-20260730-001"
        / "journal.json"
    )
    assert frontmatter["schema_version"] == 4
    assert journal["status"] == "committed"
    assert (
        records[0]["record_sha256"]
        == cast(dict[str, object], journal["intake_binding"])["intake_record_sha256"]
    )
    assert isinstance(journal["transaction_binding_sha256"], str)


def test_schema_upgrade_recovery_does_not_require_original_turn(
    tmp_path: Path,
) -> None:
    """A post-replacement upgrade journal recovers after the runtime turn changes."""
    project, session_id, manifest = prepare_strict_contract_upgrade(tmp_path)
    interrupted = run_controller(
        project,
        "plan",
        "contract",
        "upgrade",
        "apply",
        "--manifest",
        str(manifest),
        check=False,
        env={"WORKCTL_TEST_UPGRADE_INTERRUPT_AFTER": "plan-replaced"},
    )
    assert "PLAN_CONTRACT_UPGRADE_TEST_INTERRUPTED" in interrupted.stderr
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-upgrade-recovery",
        prompt="recover the already bound contract upgrade",
    )

    recovered = run_controller(
        project,
        "plan",
        "contract",
        "upgrade",
        "recover",
        "--transaction-id",
        "UPG-20260730-001",
    )

    assert "PLAN_CONTRACT_UPGRADE_COMMITTED" in recovered.stdout


def test_plan_intake_records_form_hash_chain_and_replay_idempotently(
    tmp_path: Path,
) -> None:
    """Exact replay is idempotent while conflicting same-request content fails."""
    project, session_id = prepare_admitted_project(tmp_path)
    first, first_manifest, _turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-one",
        decision="proceed",
        targets=["task:T-001"],
        expected_revision=1,
    )
    replay = run_controller(
        project,
        "plan",
        "intake",
        "record",
        "--manifest",
        str(first_manifest),
        "--expected-revision",
        "1",
    )
    assert "PLAN_INTAKE_REPLAY" in replay.stdout

    conflict = dict(first)
    conflict["rationale"] = "Conflicting rationale."
    conflict.pop("intake_sha256")
    conflict["intake_sha256"] = sha256_bytes(
        json.dumps(
            conflict,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    conflict_path = project / "conflict.json"
    conflict_path.write_text(json.dumps(conflict), encoding="utf-8")
    rejected = run_controller(
        project,
        "plan",
        "intake",
        "record",
        "--manifest",
        str(conflict_path),
        "--expected-revision",
        "2",
        check=False,
    )
    assert rejected.returncode == 2
    assert "INTAKE_REQUEST_CONFLICT" in rejected.stderr

    issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-two",
        decision="proceed",
        targets=["task:T-002"],
        expected_revision=2,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    intake = frontmatter["intake"]
    assert isinstance(intake, dict)
    assert cast(dict[str, object], intake)["protocol_version"] == 2
    second_record = cast(dict[str, object], cast(dict[str, object], intake)["current"])
    first_record_path = (
        project
        / ".work-governance"
        / "runtime"
        / "intake-history"
        / "PLAN-20260729-001"
        / f"{second_record['previous_record_sha256']}.json"
    )
    first_record = read_json_object(first_record_path)
    assert second_record["previous_record_sha256"] == first_record["record_sha256"]
    assert frontmatter["revision"] == 3


def test_same_request_material_transition_uses_bounded_immutable_history(
    tmp_path: Path,
) -> None:
    """Explore may become proceed after basis resolution without growing the Plan."""
    project, session_id = prepare_admitted_project(tmp_path)
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    frontmatter["unknowns"] = [
        {
            "id": "U-001",
            "question": "Which local invariant applies?",
            "status": "open",
            "owner": "agent",
            "impact": "blocking",
            "blocks": ["route"],
            "expected_evidence": "A local inspection resolves the invariant.",
        }
    ]
    write_plan_frontmatter(project, "PLAN-20260729-001", frontmatter)
    explore, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-transition",
        decision="explore",
        targets=["route"],
        current_unknown_id="U-001",
        expected_revision=1,
    )
    explored = read_plan_frontmatter(project, "PLAN-20260729-001")
    unknown = cast(list[dict[str, object]], explored["unknowns"])[0]
    unknown.update(
        {
            "status": "resolved",
            "resolution": "The local invariant is confirmed.",
            "evidence_manifest": "evidence:runtime/local-invariant.json",
            "resolved_at": "2026-08-01T00:00:00Z",
        }
    )
    write_plan_frontmatter(project, "PLAN-20260729-001", explored)

    turn_path = (
        project
        / ".work-governance"
        / "runtime"
        / "sessions"
        / session_id
        / "current-turn-receipt.json"
    )
    proceed = json.loads(
        run_controller(
            project,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            turn_sha256,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            "The locally owned blocker is resolved.",
            "--targets",
            "route",
        ).stdout
    )
    assert proceed["request_ref"] == explore["request_ref"]
    proceed_manifest = project / "transition-proceed.json"
    proceed_manifest.write_text(json.dumps(proceed), encoding="utf-8")
    recorded = run_controller(
        project,
        "plan",
        "intake",
        "record",
        "--manifest",
        str(proceed_manifest),
        "--expected-revision",
        "2",
    )

    final = read_plan_frontmatter(project, "PLAN-20260729-001")
    intake = cast(dict[str, object], final["intake"])
    current = cast(dict[str, object], intake["current"])
    history = cast(dict[str, object], intake["history"])
    history_root = project / ".work-governance" / "runtime" / "intake-history" / "PLAN-20260729-001"

    assert "PLAN_INTAKE_TRANSITIONED" in recorded.stdout
    assert intake["protocol_version"] == 2
    assert current["decision"] == "proceed"
    assert current["supersedes_record_sha256"]
    assert history["record_count"] == 3
    assert history["head_sha256"] == current["record_sha256"]
    assert len(list(history_root.glob("*.json"))) == 3
    assert read_json_object(turn_path)["receipt_sha256"] == turn_sha256

    conflict = dict(proceed)
    conflict["rationale"] = "Rationale-only mutation is not material."
    conflict.pop("intake_sha256")
    conflict["intake_sha256"] = sha256_bytes(
        json.dumps(
            conflict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    conflict_path = project / "transition-conflict.json"
    conflict_path.write_text(json.dumps(conflict), encoding="utf-8")
    rejected = run_controller(
        project,
        "plan",
        "intake",
        "record",
        "--manifest",
        str(conflict_path),
        "--expected-revision",
        "3",
        check=False,
    )
    assert rejected.returncode == 2
    assert "INTAKE_REQUEST_CONFLICT" in rejected.stderr


def test_same_request_proceed_refreshes_after_controller_basis_change(
    tmp_path: Path,
) -> None:
    """One trusted proceed can refresh after a controller-owned structural write."""
    project, session_id = prepare_admitted_project(tmp_path)
    first, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-proceed-refresh",
        decision="proceed",
        targets=["route"],
        expected_revision=1,
    )
    first_frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    first_record = intake_records_for_assertion(first_frontmatter)[-1]

    run_controller(
        project,
        "plan",
        "unknown",
        "add",
        "--unknown-id",
        "U-001",
        "--question",
        "Which optional local note should be retained?",
        "--owner",
        "agent",
        "--impact",
        "non_blocking",
        "--expected-evidence",
        "A local note inspection.",
        "--expected-revision",
        "2",
    )
    refreshed = json.loads(
        run_controller(
            project,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            turn_sha256,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            cast(str, first["rationale"]),
            "--targets",
            "route",
        ).stdout
    )
    refresh_manifest = project / "proceed-refresh.json"
    refresh_manifest.write_text(json.dumps(refreshed), encoding="utf-8")

    recorded = run_controller(
        project,
        "plan",
        "intake",
        "record",
        "--manifest",
        str(refresh_manifest),
        "--expected-revision",
        "3",
    )
    final = read_plan_frontmatter(project, "PLAN-20260729-001")
    current = intake_records_for_assertion(final)[-1]

    assert "PLAN_INTAKE_REFRESHED" in recorded.stdout
    assert current["request_ref"] == first_record["request_ref"]
    assert current["rationale"] == first_record["rationale"]
    assert current["decision_basis_sha256"] != first_record["decision_basis_sha256"]
    assert current["supersedes_record_sha256"] == first_record["record_sha256"]


def test_same_request_proceed_refresh_rejects_unbound_direct_basis_edit(
    tmp_path: Path,
) -> None:
    """A valid-looking direct Plan edit cannot masquerade as a controller refresh."""
    project, session_id = prepare_admitted_project(tmp_path)
    first, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-unbound-refresh",
        decision="proceed",
        targets=["route"],
        expected_revision=1,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    cast(dict[str, object], frontmatter["route"])["next_phase"] = "A direct unbound edit."
    write_plan_frontmatter(project, "PLAN-20260729-001", frontmatter)
    proposal = json.loads(
        run_controller(
            project,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            turn_sha256,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            cast(str, first["rationale"]),
            "--targets",
            "route",
        ).stdout
    )
    manifest = project / "unbound-refresh.json"
    manifest.write_text(json.dumps(proposal), encoding="utf-8")

    rejected = run_controller(
        project,
        "plan",
        "intake",
        "record",
        "--manifest",
        str(manifest),
        "--expected-revision",
        "2",
        check=False,
    )

    assert "INTAKE_REQUEST_CONFLICT" in rejected.stderr


def test_atomic_closeout_refreshes_current_intake_without_an_extra_turn(
    tmp_path: Path,
) -> None:
    """Terminal route mutation and intake refresh commit under one trusted request."""
    plan_id = "PLAN-20260801-301"
    plan = strict_admission_plan(plan_id)
    plan["obligations"] = []
    plan["tasks"] = []
    plan["validations"] = []
    plan["artifacts"] = []
    plan["delivery"] = {
        "status": "complete",
        "boundary": "immutable-local-candidate",
        "evidence_ref": "git:exact-candidate",
    }
    cast(dict[str, object], plan["route"])["confirmation_gate"] = "C-ADMISSION"
    project, _session_id = prepare_admitted_project(tmp_path, prepared_plan=plan)
    admitted = read_plan_frontmatter(project, plan_id)
    initial_record = intake_records_for_assertion(admitted)[-1]
    turn_receipt = read_json_object(
        project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    )
    evidence_input = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "closeout",
        "created_at": "2026-08-01T10:10:00+00:00",
        "producer_ref": "runtime:strict-atomic-closeout-test",
        "items": [{"ref": "git:exact-candidate", "sha256": "d" * 64}],
    }
    evidence_input_path = project / "closeout-evidence.json"
    evidence_input_path.write_text(json.dumps(evidence_input), encoding="utf-8")
    evidence = json.loads(
        run_controller(
            project,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(evidence_input_path),
        ).stdout
    )

    completed = run_controller(
        project,
        "plan",
        "complete",
        "--finalize-route",
        "--confirmation",
        "C-ADMISSION",
        "--evidence-manifest",
        str(evidence["path"]),
        "--expected-revision",
        "1",
        "--turn-receipt-sha256",
        cast(str, turn_receipt["receipt_sha256"]),
        "--expected-intake-sha256",
        cast(str, initial_record["record_sha256"]),
    )
    final = read_plan_frontmatter(project, plan_id)
    current = intake_records_for_assertion(final)[-1]
    history = cast(dict[str, object], cast(dict[str, object], final["intake"])["history"])

    assert "PLAN_COMPLETED revision=2" in completed.stdout
    assert final["status"] == "complete"
    assert cast(dict[str, object], final["route"])["route_status"] == "terminal"
    assert current["request_ref"] == initial_record["request_ref"]
    assert current["supersedes_record_sha256"] == initial_record["record_sha256"]
    assert current["decision_basis_sha256"] != initial_record["decision_basis_sha256"]
    assert history["record_count"] == 2


def test_basis_change_invalidates_prior_intake(tmp_path: Path) -> None:
    """A structural unknown change makes the prior intake unusable."""
    project, session_id = prepare_admitted_project(tmp_path)
    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-one",
        decision="proceed",
        targets=["task:T-001"],
        expected_revision=1,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    record = intake_records_for_assertion(frontmatter)[-1]
    intake_sha256 = cast(str, record["record_sha256"])
    run_controller(
        project,
        "plan",
        "unknown",
        "add",
        "--unknown-id",
        "U-001",
        "--question",
        "Which local fact should be checked?",
        "--owner",
        "agent",
        "--impact",
        "non_blocking",
        "--expected-evidence",
        "A local inspection result.",
        "--expected-revision",
        "2",
    )

    blocked = run_controller(
        project,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "3",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert blocked.returncode == 2
    assert "INTAKE_BASIS_STALE" in blocked.stderr


def test_route_proceed_crosses_ready_tasks_and_evidence_until_structure_changes(
    tmp_path: Path,
) -> None:
    """One route decision remains valid across volatile progress, but not contract structure."""
    project, session_id = prepare_admitted_project(tmp_path)
    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-route-proceed",
        decision="proceed",
        targets=["route"],
        expected_revision=1,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    record = intake_records_for_assertion(frontmatter)[-1]
    intake_sha256 = cast(str, record["record_sha256"])

    def task_transition(action: str, task_id: str, revision: int) -> None:
        run_controller(
            project,
            "task",
            action,
            "--task-id",
            task_id,
            "--expected-revision",
            str(revision),
            "--turn-receipt-sha256",
            turn_sha256,
            "--expected-intake-sha256",
            intake_sha256,
        )

    task_transition("start", "T-001", 2)
    task_transition("verify", "T-001", 3)
    task_transition("start", "T-002", 4)
    evidence_input = project / "route-validation-evidence.json"
    evidence_input.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "work-governance-evidence",
                "plan_id": "PLAN-20260729-001",
                "subject": "validation:V-001",
                "created_at": "2026-07-31T10:00:00Z",
                "producer_ref": "runtime:route-proceed-test",
                "items": [{"ref": "project:validation-result", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    recorded = cast(
        dict[str, object],
        json.loads(
            run_controller(
                project,
                "plan",
                "evidence",
                "record",
                "--manifest",
                str(evidence_input),
            ).stdout
        ),
    )
    run_controller(
        project,
        "plan",
        "verify-entry",
        "--field",
        "validations",
        "--entry-id",
        "V-001",
        "--confirmation",
        "C-ADMISSION",
        "--evidence-manifest",
        cast(str, recorded["path"]),
        "--expected-revision",
        "5",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
    )
    run_controller(
        project,
        "plan",
        "unknown",
        "add",
        "--unknown-id",
        "U-001",
        "--question",
        "Which new local constraint applies?",
        "--owner",
        "agent",
        "--impact",
        "non_blocking",
        "--expected-evidence",
        "A local inspection result.",
        "--expected-revision",
        "6",
    )
    stale = run_controller(
        project,
        "task",
        "verify",
        "--task-id",
        "T-002",
        "--expected-revision",
        "7",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert stale.returncode == 2
    assert "INTAKE_BASIS_STALE" in stale.stderr


@pytest.mark.parametrize(
    ("owner", "decision", "accepted"),
    [
        ("user", "ask", True),
        ("user", "explore", False),
        ("agent", "explore", True),
        ("agent", "ask", False),
        ("user", "proceed", False),
    ],
)
def test_unknown_owner_controls_intake_decision(
    tmp_path: Path,
    owner: str,
    decision: str,
    accepted: bool,
) -> None:
    """Ask maps to user ownership, explore to agent ownership, and blockers stop proceed."""
    unknown: dict[str, object] = {
        "id": "U-001",
        "question": "Who decides?",
        "status": "open",
        "owner": owner,
        "impact": "blocking",
        "blocks": ["task:T-001"],
        "expected_evidence": "The owning party resolves the question.",
    }
    project, session_id = prepare_admitted_project(tmp_path, unknowns=[unknown])
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-owner",
        prompt="advance guarded work",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])
    command = [
        "intake",
        "receipt",
        "--turn-receipt-sha256",
        turn_sha256,
        "--classification",
        "plan_controlled",
        "--decision",
        decision,
        "--rationale",
        "Owner-derived decision.",
        "--targets",
        "task:T-001",
    ]
    if decision in {"ask", "explore"}:
        command.extend(["--current-unknown-id", "U-001"])

    result = run_controller(project, *command, check=False)

    assert (result.returncode == 0) is accepted


@pytest.mark.parametrize(
    ("targets", "accepted"),
    [
        (["task:T-001"], False),
        (["task:T-002"], True),
        (["artifact:A-001"], True),
        (["task:T-002", "artifact:A-001"], True),
        (["task:T-002", "task:T-001"], False),
    ],
)
def test_target_matrix_uses_exact_matching_and_any_blocker_stops_multi_target(
    tmp_path: Path,
    targets: list[str],
    accepted: bool,
) -> None:
    """Exact task blockers neither leak layers nor disappear in multi-target commands."""
    unknown: dict[str, object] = {
        "id": "U-001",
        "question": "Task-one decision?",
        "status": "open",
        "owner": "user",
        "impact": "blocking",
        "blocks": ["task:T-001"],
        "expected_evidence": "A user decision.",
    }
    project, session_id = prepare_admitted_project(tmp_path, unknowns=[unknown])
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-target",
        prompt="test exact targets",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])
    command = [
        "intake",
        "receipt",
        "--turn-receipt-sha256",
        turn_sha256,
        "--classification",
        "plan_controlled",
        "--decision",
        "proceed",
        "--rationale",
        "Target-matrix probe.",
    ]
    for target in targets:
        command.extend(["--targets", target])

    result = run_controller(project, *command, check=False)

    assert (result.returncode == 0) is accepted


def test_unrelated_task_advances_under_exact_current_intake(tmp_path: Path) -> None:
    """A blocker on T-001 does not prevent a current decision for T-002."""
    unknown: dict[str, object] = {
        "id": "U-001",
        "question": "Task-one decision?",
        "status": "open",
        "owner": "user",
        "impact": "blocking",
        "blocks": ["task:T-001"],
        "expected_evidence": "A user decision.",
    }
    project, session_id = prepare_admitted_project(tmp_path, unknowns=[unknown])
    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-unrelated",
        decision="proceed",
        targets=["task:T-002"],
        expected_revision=1,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    records = intake_records_for_assertion(frontmatter)

    started = run_controller(
        project,
        "task",
        "start",
        "--task-id",
        "T-002",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        cast(str, records[-1]["record_sha256"]),
    )

    assert "TASK_UPDATED T-002 in_progress" in started.stdout


def test_non_task_advancement_commands_enforce_their_exact_targets(tmp_path: Path) -> None:
    """Every non-task advancement handler rejects an unrelated intake target."""
    project, session_id = prepare_admitted_project(tmp_path)
    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-command-targets",
        decision="proceed",
        targets=["task:T-002"],
        expected_revision=1,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    records = intake_records_for_assertion(frontmatter)
    intake_sha256 = cast(str, records[-1]["record_sha256"])
    adaptation_path = tmp_path / "adaptation.yaml"
    adaptation_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "plan-adaptation",
                "plan_id": "PLAN-20260729-001",
                "expected_revision": 2,
                "confirmation_id": "C-ADMISSION",
                "rationale": "Exercise the route-level intake gate.",
                "evidence_manifest": "unused-before-intake-gate.json",
                "changes": {
                    "route": {
                        **cast(dict[str, object], frontmatter["route"]),
                        "next_phase": "An intake-gated adaptation.",
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    commands = [
        ("adapt", ["plan", "adapt", "--manifest", str(adaptation_path)]),
        (
            "verify-entry",
            [
                "plan",
                "verify-entry",
                "--field",
                "obligations",
                "--entry-id",
                "O-001",
                "--confirmation",
                "C-ADMISSION",
            ],
        ),
        (
            "finalize-artifact",
            [
                "plan",
                "finalize-artifact",
                "--artifact-id",
                "A-001",
                "--task-id",
                "T-001",
                "--confirmation",
                "C-ADMISSION",
            ],
        ),
        (
            "delivery-complete",
            ["plan", "delivery-complete", "--confirmation", "C-ADMISSION"],
        ),
        (
            "activation-promote",
            [
                "plan",
                "activation-promote",
                "--state",
                "in_progress",
                "--confirmation",
                "C-ADMISSION",
            ],
        ),
        ("complete", ["plan", "complete"]),
    ]

    for label, command in commands:
        arguments = [*command]
        if label != "adapt":
            arguments.extend(["--expected-revision", "2"])
        arguments.extend(
            [
                "--turn-receipt-sha256",
                turn_sha256,
                "--expected-intake-sha256",
                intake_sha256,
            ]
        )
        result = run_controller(
            project,
            *arguments,
            check=False,
        )
        assert result.returncode == 2, label
        assert "INTAKE_TARGET_MISMATCH" in result.stderr, label


def test_schema_v4_plan_adapt_intent_requires_current_intake_before_evidence(
    tmp_path: Path,
) -> None:
    """High-level v4 adaptation keeps the v4 turn and revision gates."""
    project, session_id = prepare_admitted_project(tmp_path)
    plan_id = "PLAN-20260729-001"
    intent_path = project / "adapt-intent.txt"
    intent_path.write_text("Prefer the shorter controller workflow.\n", encoding="utf-8")
    before = evidence_tree_snapshot(project)

    missing_revision = run_controller(
        project,
        "plan",
        "adapt",
        "--intent-from-file",
        str(intent_path),
        "--summary",
        "Record route adaptation intent.",
        check=False,
    )
    assert missing_revision.returncode == 2
    assert "EXPECTED_REVISION_REQUIRED" in missing_revision.stderr
    assert evidence_tree_snapshot(project) == before

    missing_intake = run_controller(
        project,
        "plan",
        "adapt",
        "--intent-from-file",
        str(intent_path),
        "--summary",
        "Record route adaptation intent.",
        "--expected-revision",
        "1",
        check=False,
    )
    assert missing_intake.returncode == 2
    assert "TURN_RECEIPT_REQUIRED" in missing_intake.stderr
    assert evidence_tree_snapshot(project) == before

    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-adapt-intent",
        decision="proceed",
        targets=["route"],
        expected_revision=1,
    )
    frontmatter = read_plan_frontmatter(project, plan_id)
    intake_sha256 = cast(str, intake_records_for_assertion(frontmatter)[-1]["record_sha256"])

    completed = run_controller(
        project,
        "plan",
        "adapt",
        "--intent-from-file",
        str(intent_path),
        "--summary",
        "Record route adaptation intent.",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
    )
    payload: object = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    revised = read_plan_frontmatter(project, plan_id)

    assert payload["status"] == "PLAN_ADAPT_INTENT_RECORDED"
    assert payload["revision"] == 3
    assert revised["revision"] == 3
    assert cast(list[dict[str, object]], revised["revision_history"])[-1]["kind"] == "adaptation"
    assert evidence_tree_snapshot(project) != before


def prepare_activation_repair_project(
    tmp_path: Path,
    *,
    current_target: str = "plugin:work-governance@goal-driven.pending",
    new_basis_ref: str | None = None,
    selected_task_id: str = "T-001",
    primary_scope: str = "route",
    secondary_scope: str | None = None,
) -> tuple[Path, str, str, str]:
    """Prepare the exact accepted-gate bootstrap defect for repair tests."""
    project, session_id = prepare_admitted_project(tmp_path)
    receipt = read_json_object(project / ".work-governance" / "bootstrap-state.json")
    exact_target = f"plugin:work-governance@{receipt['plugin_build']}"
    gate_basis_ref = new_basis_ref or exact_target
    plan_id = "PLAN-20260729-001"
    frontmatter = read_plan_frontmatter(project, plan_id)
    required = cast(
        list[dict[str, object]],
        cast(dict[str, object], frontmatter["confirmations"])["required"],
    )
    required.extend(
        [
            {
                "id": "C-LIVE-OLD",
                "description": "Previously accepted malformed live target.",
                "status": "accepted",
                "ref": "user:test-old-live",
                "accepted_at": "2026-08-04T10:00:00Z",
                "evidence_sha256": "a" * 64,
                "intervention": {
                    "kind": "external_authority",
                    "blocks": ["task:T-001", "activation", "route"],
                    "basis_ref": "plugin:work-governance@1.0.7+codex.old",
                    "basis_sha256": "a" * 64,
                },
            },
            {
                "id": "C-LIVE-REPAIRED",
                "description": "Accept the exact repaired Plugin candidate.",
                "status": "accepted",
                "ref": "user:test-repaired-live",
                "accepted_at": "2026-08-04T11:00:00Z",
                "evidence_sha256": "b" * 64,
                "intervention": {
                    "kind": "external_authority",
                    "blocks": [f"task:{selected_task_id}", "activation", "route"],
                    "basis_ref": gate_basis_ref,
                    "basis_sha256": "b" * 64,
                },
            },
        ]
    )
    task = cast(list[dict[str, object]], frontmatter["tasks"])[0]
    task["status"] = "blocked"
    task["completion_scope"] = primary_scope
    task["requires_confirmation"] = "C-LIVE-OLD"
    if secondary_scope is not None:
        second_task = cast(list[dict[str, object]], frontmatter["tasks"])[1]
        second_task["status"] = "blocked"
        second_task["completion_scope"] = secondary_scope
        second_task["requires_confirmation"] = "C-LIVE-OLD"
    frontmatter["scope"] = {
        "include": ["Test intake."],
        "exclude": [
            {
                "description": "Do not switch the live Plugin before confirmation.",
                "disposition": "pending_confirmation",
                "confirmation_id": "C-LIVE-OLD",
            }
        ],
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "plugin:work-governance@1.0.7+codex.old",
        "target_ref": current_target,
        "confirmation_id": "C-LIVE-OLD",
    }
    frontmatter["route"] = {
        "route_status": "active",
        "slice_status": "activation-repair",
        "next_phase": "Repair the exact legacy contract.",
        "validation_standard": "Every live surface uses one accepted exact-build gate.",
        "confirmation_gate": "C-LIVE-OLD",
    }
    write_plan_frontmatter(project, plan_id, frontmatter)
    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-activation-repair",
        decision="proceed",
        targets=[f"task:{selected_task_id}", "activation", "route"],
        expected_revision=1,
    )
    recorded = read_plan_frontmatter(project, plan_id)
    intake_sha256 = cast(str, intake_records_for_assertion(recorded)[-1]["record_sha256"])
    return project, turn_sha256, intake_sha256, exact_target


def test_activation_repair_atomically_rebinds_exact_contract(tmp_path: Path) -> None:
    """The dedicated repair moves every live surface to one exact accepted gate."""
    project, turn_sha256, intake_sha256, exact_target = prepare_activation_repair_project(tmp_path)

    repaired = run_controller(
        project,
        "plan",
        "activation-repair",
        "--task-id",
        "T-001",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-REPAIRED",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    task = cast(list[dict[str, object]], frontmatter["tasks"])[0]
    scope = cast(dict[str, object], frontmatter["scope"])
    exclusion = cast(list[dict[str, object]], scope["exclude"])[0]
    activation = cast(dict[str, object], frontmatter["activation"])
    route = cast(dict[str, object], frontmatter["route"])
    contract = cast(dict[str, object], frontmatter["contract"])

    assert "ACTIVATION_CONTRACT_REPAIRED" in repaired.stdout
    assert frontmatter["revision"] == 3
    assert contract["revision"] == 2
    assert contract["confirmation_id"] == "C-LIVE-REPAIRED"
    assert contract["confirmed_ref"] == "user:test-repaired-live"
    assert task["status"] == "blocked"
    assert task["requires_confirmation"] == "C-LIVE-REPAIRED"
    assert exclusion["confirmation_id"] == "C-LIVE-REPAIRED"
    assert activation["target_ref"] == exact_target
    assert activation["confirmation_id"] == "C-LIVE-REPAIRED"
    assert route["confirmation_gate"] == "C-LIVE-REPAIRED"
    history = cast(list[dict[str, object]], frontmatter["revision_history"])
    assert history[-1]["kind"] == "activation-contract-repaired"


def test_activation_repair_rejects_gate_drift_without_plan_write(tmp_path: Path) -> None:
    """A target not bound by the new gate leaves the old Plan bytes unchanged."""
    project, turn_sha256, intake_sha256, exact_target = prepare_activation_repair_project(
        tmp_path,
        new_basis_ref="plugin:work-governance@1.0.7+codex.different",
    )
    plan = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    before = plan.read_bytes()

    rejected = run_controller(
        project,
        "plan",
        "activation-repair",
        "--task-id",
        "T-001",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-REPAIRED",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert rejected.returncode == 2
    assert "ACTIVATION_REPAIR_CONFIRMATION_MISMATCH" in rejected.stderr
    assert plan.read_bytes() == before


def test_activation_repair_interruption_preserves_old_plan(tmp_path: Path) -> None:
    """A pre-replace process interruption preserves the complete old Plan bytes."""
    project, turn_sha256, intake_sha256, exact_target = prepare_activation_repair_project(tmp_path)
    plan = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    before = plan.read_bytes()

    interrupted = run_controller(
        project,
        "plan",
        "activation-repair",
        "--task-id",
        "T-001",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-REPAIRED",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
        env={"WORKCTL_TEST_ACTIVATION_REPAIR_INTERRUPT": "before-plan-write"},
    )

    assert interrupted.returncode == 2
    assert "ACTIVATION_REPAIR_TEST_INTERRUPTED_BEFORE_PLAN_WRITE" in interrupted.stderr
    assert plan.read_bytes() == before


def test_activation_repair_rejects_canonical_target_without_plan_write(
    tmp_path: Path,
) -> None:
    """Canonical placeholders stay on activation-promote instead of the repair path."""
    project, turn_sha256, intake_sha256, exact_target = prepare_activation_repair_project(
        tmp_path,
        current_target="plugin:work-governance@1.0.7+codex.pending",
    )
    plan = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    before = plan.read_bytes()

    rejected = run_controller(
        project,
        "plan",
        "activation-repair",
        "--task-id",
        "T-001",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-REPAIRED",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert rejected.returncode == 2
    assert "ACTIVATION_REPAIR_LEGACY_TARGET_REQUIRED" in rejected.stderr
    assert plan.read_bytes() == before


def test_activation_repair_rejects_local_task_without_plan_write(tmp_path: Path) -> None:
    """A local task cannot own or migrate the live route confirmation."""
    project, turn_sha256, intake_sha256, exact_target = prepare_activation_repair_project(
        tmp_path,
        primary_scope="local",
    )
    plan = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    before = plan.read_bytes()

    rejected = run_controller(
        project,
        "plan",
        "activation-repair",
        "--task-id",
        "T-001",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-REPAIRED",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert rejected.returncode == 2
    assert "ACTIVATION_REPAIR_ROUTE_TASK_REQUIRED" in rejected.stderr
    assert plan.read_bytes() == before


def test_activation_repair_rejects_wrong_task_without_plan_write(tmp_path: Path) -> None:
    """A blocked local peer cannot be substituted for the unique route owner."""
    project, turn_sha256, intake_sha256, exact_target = prepare_activation_repair_project(
        tmp_path,
        selected_task_id="T-002",
        secondary_scope="local",
    )
    plan = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    before = plan.read_bytes()

    rejected = run_controller(
        project,
        "plan",
        "activation-repair",
        "--task-id",
        "T-002",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-REPAIRED",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert rejected.returncode == 2
    assert "ACTIVATION_REPAIR_ROUTE_TASK_REQUIRED" in rejected.stderr
    assert plan.read_bytes() == before


def test_activation_repair_rejects_multiple_route_owners_without_plan_write(
    tmp_path: Path,
) -> None:
    """Multiple route tasks sharing the old gate require an explicit future contract."""
    project, turn_sha256, intake_sha256, exact_target = prepare_activation_repair_project(
        tmp_path,
        secondary_scope="route",
    )
    plan = project / ".work-governance" / "_Plan" / "PLAN-20260729-001.md"
    before = plan.read_bytes()

    rejected = run_controller(
        project,
        "plan",
        "activation-repair",
        "--task-id",
        "T-001",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-REPAIRED",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert rejected.returncode == 2
    assert "ACTIVATION_REPAIR_ROUTE_TASK_AMBIGUOUS" in rejected.stderr
    assert plan.read_bytes() == before


def test_activation_start_binds_exact_target_before_runtime_evidence(tmp_path: Path) -> None:
    """An accepted activation gate may replace a placeholder only before activation."""
    project, session_id = prepare_admitted_project(tmp_path)
    plan_id = "PLAN-20260729-001"
    frontmatter = read_plan_frontmatter(project, plan_id)
    confirmations = cast(
        list[dict[str, object]],
        cast(dict[str, object], frontmatter["confirmations"])["required"],
    )
    confirmations.append(
        {
            "id": "C-LIVE-SWITCH",
            "description": "Activate the exact installed build.",
            "status": "accepted",
            "ref": "user:test-live-switch",
            "accepted_at": "2026-07-29T01:00:00Z",
        }
    )
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "plugin:work-governance@1.0.3",
        "target_ref": "plugin:work-governance@1.0.4+codex.pending",
        "confirmation_id": "C-LIVE-SWITCH",
        "decision_ref": "confirmation:C-LIVE-SWITCH",
    }
    write_plan_frontmatter(project, plan_id, frontmatter)
    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-bind-activation-target",
        decision="proceed",
        targets=["activation"],
        expected_revision=1,
    )
    recorded = read_plan_frontmatter(project, plan_id)
    record = intake_records_for_assertion(recorded)[-1]
    intake_sha256 = cast(str, record["record_sha256"])
    exact_target = "plugin:work-governance@1.0.4+codex.20260730014019"

    promoted = run_controller(
        project,
        "plan",
        "activation-promote",
        "--state",
        "in_progress",
        "--target-ref",
        exact_target,
        "--confirmation",
        "C-LIVE-SWITCH",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
    )
    after_start = read_plan_frontmatter(project, plan_id)
    activation = cast(dict[str, object], after_start["activation"])

    assert "ACTIVATION_PROMOTED in_progress revision=3" in promoted.stdout
    assert activation["status"] == "in_progress"
    assert activation["current_ref"] == "plugin:work-governance@1.0.3"
    assert activation["target_ref"] == exact_target

    rejected_rebind = run_controller(
        project,
        "plan",
        "activation-promote",
        "--state",
        "active",
        "--target-ref",
        "plugin:work-governance@different",
        "--confirmation",
        "C-LIVE-SWITCH",
        "--evidence-ref",
        "runtime:fresh-session",
        "--evidence-sha256",
        "a" * 64,
        "--expected-revision",
        "3",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert rejected_rebind.returncode == 2
    assert "ACTIVATION_TARGET_REBIND_INVALID_STATE" in rejected_rebind.stderr

    mismatched_evidence_input = project / "mismatched-activation-evidence.json"
    mismatched_evidence_input.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "work-governance-evidence",
                "plan_id": plan_id,
                "subject": "activation",
                "observed_ref": "plugin:work-governance@1.0.4+codex.different",
                "created_at": "2026-07-29T01:01:00Z",
                "producer_ref": "runtime:test-fresh-session",
                "items": [{"ref": "codex-plugin-list:work-governance", "sha256": "b" * 64}],
            }
        ),
        encoding="utf-8",
    )
    mismatched_record = json.loads(
        run_controller(
            project,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(mismatched_evidence_input),
        ).stdout
    )
    mismatched_activation = run_controller(
        project,
        "plan",
        "activation-promote",
        "--state",
        "active",
        "--confirmation",
        "C-LIVE-SWITCH",
        "--evidence-manifest",
        mismatched_record["path"],
        "--expected-revision",
        "3",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert mismatched_activation.returncode == 2
    assert "EVIDENCE_MANIFEST_OBSERVED_REF_MISMATCH" in mismatched_activation.stderr

    matching_evidence_input = project / "matching-activation-evidence.json"
    matching_evidence_input.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "work-governance-evidence",
                "plan_id": plan_id,
                "subject": "activation",
                "observed_ref": exact_target,
                "created_at": "2026-07-29T01:02:00Z",
                "producer_ref": "runtime:test-fresh-session",
                "items": [{"ref": "codex-plugin-list:work-governance", "sha256": "c" * 64}],
            }
        ),
        encoding="utf-8",
    )
    matching_record = json.loads(
        run_controller(
            project,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(matching_evidence_input),
        ).stdout
    )
    activated = run_controller(
        project,
        "plan",
        "activation-promote",
        "--state",
        "active",
        "--confirmation",
        "C-LIVE-SWITCH",
        "--evidence-manifest",
        matching_record["path"],
        "--expected-revision",
        "3",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
    )
    active_plan = read_plan_frontmatter(project, plan_id)
    active = cast(dict[str, object], active_plan["activation"])
    evidence = cast(dict[str, object], active["evidence"])

    assert "ACTIVATION_PROMOTED active revision=4" in activated.stdout
    assert active["status"] == "active"
    assert active["current_ref"] == exact_target
    assert active["target_ref"] == exact_target
    assert evidence["observed_ref"] == exact_target
    assert evidence["source_ref"] == f"evidence:{matching_record['path']}"


@pytest.mark.parametrize(
    ("existing_target", "requested_target", "expected_error"),
    [
        (
            "plugin:work-governance@1.0.4+codex.exact",
            "plugin:work-governance@1.0.4+codex.different",
            "ACTIVATION_TARGET_NOT_PLACEHOLDER",
        ),
        (
            "plugin:work-governance@1.0.4+codex.pending",
            "plugin:other@1.0.4+codex.exact",
            "ACTIVATION_TARGET_EXACT_REF_REQUIRED",
        ),
        (
            "plugin:work-governance@1.0.4+codex.pending",
            "plugin:work-governance@1.0.4+codex.pending",
            "ACTIVATION_TARGET_EXACT_REF_REQUIRED",
        ),
    ],
)
def test_activation_target_binding_rejects_drift(
    tmp_path: Path,
    existing_target: str,
    requested_target: str,
    expected_error: str,
) -> None:
    """Target binding rejects non-placeholder origins and non-exact replacements."""
    project, session_id = prepare_admitted_project(tmp_path)
    plan_id = "PLAN-20260729-001"
    frontmatter = read_plan_frontmatter(project, plan_id)
    confirmations = cast(
        list[dict[str, object]],
        cast(dict[str, object], frontmatter["confirmations"])["required"],
    )
    confirmations.append(
        {
            "id": "C-LIVE-SWITCH",
            "description": "Activate the exact installed build.",
            "status": "accepted",
            "ref": "user:test-live-switch",
            "accepted_at": "2026-07-29T01:00:00Z",
        }
    )
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "plugin:work-governance@1.0.3",
        "target_ref": existing_target,
        "confirmation_id": "C-LIVE-SWITCH",
        "decision_ref": "confirmation:C-LIVE-SWITCH",
    }
    write_plan_frontmatter(project, plan_id, frontmatter)
    _proposal, _manifest, turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-reject-activation-target-drift",
        decision="proceed",
        targets=["activation"],
        expected_revision=1,
    )
    recorded = read_plan_frontmatter(project, plan_id)
    record = intake_records_for_assertion(recorded)[-1]
    intake_sha256 = cast(str, record["record_sha256"])

    result = run_controller(
        project,
        "plan",
        "activation-promote",
        "--state",
        "in_progress",
        "--target-ref",
        requested_target,
        "--confirmation",
        "C-LIVE-SWITCH",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        turn_sha256,
        "--expected-intake-sha256",
        intake_sha256,
        check=False,
    )

    assert result.returncode == 2
    assert expected_error in result.stderr


def test_route_blocker_covers_artifact_delivery_and_activation(tmp_path: Path) -> None:
    """A route blocker covers every target without adding implicit layer mappings."""
    unknown: dict[str, object] = {
        "id": "U-001",
        "question": "Route decision?",
        "status": "open",
        "owner": "user",
        "impact": "blocking",
        "blocks": ["route"],
        "expected_evidence": "A route-level user decision.",
    }
    project, session_id = prepare_admitted_project(tmp_path, unknowns=[unknown])
    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-route",
        prompt="test route coverage",
    )
    turn_path = project / ".work-governance" / "runtime" / "current-turn-receipt.json"
    turn_sha256 = cast(str, read_json_object(turn_path)["receipt_sha256"])

    for target in ("artifact:A-001", "delivery", "activation"):
        result = run_controller(
            project,
            "intake",
            "receipt",
            "--turn-receipt-sha256",
            turn_sha256,
            "--classification",
            "plan_controlled",
            "--decision",
            "proceed",
            "--rationale",
            "Route coverage probe.",
            "--targets",
            target,
            check=False,
        )
        assert result.returncode == 2
        assert "INTAKE_BLOCKED_BY_UNKNOWN" in result.stderr


def test_ask_record_cannot_advance_and_new_turn_cannot_reuse_prior_decision(
    tmp_path: Path,
) -> None:
    """Ask records block advancement, and overwriting the turn blocks replay."""
    unknown: dict[str, object] = {
        "id": "U-001",
        "question": "User decision?",
        "status": "open",
        "owner": "user",
        "impact": "blocking",
        "blocks": ["task:T-001"],
        "expected_evidence": "A user answer.",
    }
    project, session_id = prepare_admitted_project(tmp_path, unknowns=[unknown])
    _proposal, _manifest, first_turn_sha256 = issue_intake(
        project,
        session_id=session_id,
        turn_id="turn-ask",
        decision="ask",
        targets=["task:T-001"],
        current_unknown_id="U-001",
        expected_revision=1,
    )
    frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    record = intake_records_for_assertion(frontmatter)[-1]
    record_sha256 = cast(str, record["record_sha256"])
    ask_blocked = run_controller(
        project,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        first_turn_sha256,
        "--expected-intake-sha256",
        record_sha256,
        check=False,
    )
    assert "INTAKE_DECISION_NOT_PROCEED" in ask_blocked.stderr

    run_turn_hook(
        project,
        session_id=session_id,
        turn_id="turn-next",
        prompt="another request",
    )
    replay_blocked = run_controller(
        project,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "2",
        "--turn-receipt-sha256",
        first_turn_sha256,
        "--expected-intake-sha256",
        record_sha256,
        check=False,
    )
    assert "TURN_RECEIPT_SUPERSEDED" in replay_blocked.stderr


def test_unknown_classify_repairs_task_projection_and_status_axes(
    tmp_path: Path,
) -> None:
    """Legacy unknown classification makes blocks authoritative and status explicit."""
    legacy_unknown = {
        "id": "U-001",
        "question": "Legacy decision?",
        "status": "open",
        "expected_evidence": "A decision.",
    }
    project, _session_id = prepare_admitted_project(tmp_path)
    legacy_frontmatter = read_plan_frontmatter(project, "PLAN-20260729-001")
    legacy_frontmatter.pop("intake")
    legacy_frontmatter["unknowns"] = [legacy_unknown]
    tasks = cast(list[dict[str, object]], legacy_frontmatter["tasks"])
    tasks[0]["unknowns"] = ["U-001"]
    write_plan_frontmatter(
        project,
        "PLAN-20260729-001",
        legacy_frontmatter,
    )
    status_before = json.loads(run_controller(project, "plan", "status", "--full").stdout)
    assert status_before["unknown_contract_state"] == "LEGACY_REPAIR_REQUIRED"
    classification = {
        "schema_version": 1,
        "kind": "plan-unknown-classification",
        "plan_id": "PLAN-20260729-001",
        "unknown_id": "U-001",
        "owner": "user",
        "impact": "blocking",
        "blocks": ["task:T-001"],
        "expected_evidence": "A user decision.",
    }
    manifest = project / "unknown-classification.yaml"
    manifest.write_text(
        yaml.safe_dump(classification, sort_keys=False),
        encoding="utf-8",
    )
    run_controller(
        project,
        "plan",
        "unknown",
        "classify",
        "--manifest",
        str(manifest),
        "--expected-revision",
        "1",
    )

    status_after = json.loads(run_controller(project, "plan", "status", "--full").stdout)
    tasks = cast(list[dict[str, object]], status_after["tasks"])
    assert status_after["unknown_contract_state"] == "STRICT_READY"
    assert status_after["legacy_unknown_ids"] == []
    assert tasks[0]["unknowns"] == ["U-001"]
