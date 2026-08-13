from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "plugins" / "work-governance" / "scripts" / "workctl.py"
KERNEL_CONTROLLER = (
    REPO_ROOT
    / "plugins"
    / "work-governance"
    / "scripts"
    / "workctl_modules"
    / "kernel"
    / "controller.py"
)
LIFECYCLE_SKILL = (
    REPO_ROOT / "plugins" / "work-governance" / "skills" / "work-lifecycle" / "SKILL.md"
)


def nearest_layout_root(cwd: Path) -> Path | None:
    """Return the nearest initialized project root used by a test subprocess."""
    current = cwd.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".work-governance" / "version.yaml").is_file():
            return candidate
    return None


def ensure_test_ready_receipt(
    cwd: Path,
    *,
    allow_legacy_contract: bool,
    bootstrapping: bool = False,
) -> tuple[Path, str] | None:
    """Create a real receipt-bound controller copy; patch legacy behavior only in tests."""
    root = cwd.resolve() if bootstrapping else nearest_layout_root(cwd)
    if root is None:
        return None
    plugin_manifest_sha256 = ("1" if allow_legacy_contract else "2") * 64
    bundle = root / ".work-governance" / "runtime" / "plugin-builds" / plugin_manifest_sha256
    bundle.mkdir(parents=True, exist_ok=True)
    wrapper_source = SCRIPT.read_text(encoding="utf-8")
    controller_source = KERNEL_CONTROLLER.read_text(encoding="utf-8")
    if allow_legacy_contract:
        strict_marker = "STRICT_INITIAL_INTAKE_REQUIRED = True\n"
        if controller_source.count(strict_marker) != 1:
            raise AssertionError("strict initial intake test marker drifted")
        controller_source = controller_source.replace(
            strict_marker,
            "STRICT_INITIAL_INTAKE_REQUIRED = False\n",
            1,
        )
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
        if contract_state_marker not in controller_source:
            raise AssertionError("test contract-state patch marker drifted")
        controller_source = controller_source.replace(
            contract_state_marker,
            legacy_contract_state,
            1,
        )
        marker = (
            "def enforce_active_contract_gate(args: argparse.Namespace, root: Path) -> None:\n"
            '    """Allow only current-schema refresh writes for an outdated active Plan."""\n'
        )
        if marker not in controller_source:
            raise AssertionError("test controller patch marker drifted")
        controller_source = controller_source.replace(marker, marker + "    return\n", 1)
        contract_marker = (
            "def require_plan_contract_ready(frontmatter: dict[str, Any]) -> None:\n"
            '    """Block ordinary writes from silently trusting an outdated active contract."""\n'
        )
        if contract_marker not in controller_source:
            raise AssertionError("test contract-ready patch marker drifted")
        controller_source = controller_source.replace(
            contract_marker,
            contract_marker + "    return\n",
            1,
        )
        intake_marker = (
            "def require_current_intake(\n"
            "    root: Path,\n"
            "    frontmatter: Mapping[str, Any],\n"
            "    *,\n"
            "    turn_receipt_sha256: str | None,\n"
            "    expected_intake_sha256: str | None,\n"
            "    targets: list[str],\n"
            ") -> None:\n"
            '    """Require a current-turn, current-basis intake record covering '
            'all targets."""\n'
        )
        if intake_marker not in controller_source:
            raise AssertionError("test intake patch marker drifted")
        controller_source = controller_source.replace(
            intake_marker,
            intake_marker + "    return\n",
            1,
        )
        confirmation_ref_marker = (
            "def require_confirmation_turn_ref(\n"
            "    root: Path,\n"
            "    *,\n"
            "    ref: str,\n"
            "    turn_receipt_sha256: str | None,\n"
            ") -> dict[str, object]:\n"
            '    """Bind a high-impact decision to the trusted current user turn."""\n'
        )
        if confirmation_ref_marker not in controller_source:
            raise AssertionError("test confirmation-turn patch marker drifted")
        controller_source = controller_source.replace(
            confirmation_ref_marker,
            confirmation_ref_marker + "    return\n",
            1,
        )
    lock_marker = '    with lock_path.open("a+", encoding="utf-8") as handle:\n'
    lock_instrumentation = (
        lock_marker
        + '        attempt_path = os.environ.get("WORKCTL_TEST_LOCK_ATTEMPT_FILE")\n'
        + "        if attempt_path:\n"
        + '            Path(attempt_path).write_text("attempting\\n", encoding="utf-8")\n'
    )
    if controller_source.count(lock_marker) != 1:
        raise AssertionError("stable-lock test patch marker drifted")
    controller_source = controller_source.replace(
        lock_marker,
        lock_instrumentation,
        1,
    )
    legacy_lock_marker = '    with path.open("w", encoding="utf-8") as handle:\n'
    legacy_lock_instrumentation = (
        legacy_lock_marker
        + '        attempt_path = os.environ.get("WORKCTL_TEST_LEGACY_LOCK_ATTEMPT_FILE")\n'
        + "        if attempt_path:\n"
        + '            Path(attempt_path).write_text("attempting\\n", encoding="utf-8")\n'
    )
    if controller_source.count(legacy_lock_marker) != 1:
        raise AssertionError("legacy-lock test patch marker drifted")
    controller_source = controller_source.replace(
        legacy_lock_marker,
        legacy_lock_instrumentation,
        1,
    )
    controller = bundle / "workctl.py"
    lifecycle = bundle / "work-lifecycle.SKILL.md"
    controller.write_text(wrapper_source, encoding="utf-8")
    module_source = SCRIPT.parent / "workctl_modules"
    if module_source.is_dir():
        shutil.copytree(module_source, bundle / "workctl_modules", dirs_exist_ok=True)
    (bundle / "workctl_modules" / "kernel" / "controller.py").write_text(
        controller_source,
        encoding="utf-8",
    )
    lifecycle.write_bytes(LIFECYCLE_SKILL.read_bytes())
    controller_sha256 = hashlib.sha256(controller.read_bytes()).hexdigest()
    lifecycle_sha256 = hashlib.sha256(lifecycle.read_bytes()).hexdigest()
    controller_ref = controller.relative_to(root).as_posix()
    lifecycle_ref = lifecycle.relative_to(root).as_posix()
    runtime_manifest = {
        "schema_version": 1,
        "kind": "work-governance-runtime-bundle",
        "plugin_build": "pytest",
        "plugin_manifest_sha256": plugin_manifest_sha256,
        "current_plan_schema_version": 5,
        "controller_ref": controller_ref,
        "controller_sha256": controller_sha256,
        "lifecycle_ref": lifecycle_ref,
        "lifecycle_sha256": lifecycle_sha256,
    }
    manifest = bundle / "manifest.json"
    manifest.write_text(
        json.dumps(runtime_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema_version": 2,
        "bootstrap_contract_version": 1,
        "action_revision": 5,
        "updated_at": "2026-07-28T00:00:00+00:00",
        "status": "BOOTSTRAPPING" if bootstrapping else "READY",
        "plugin_build": "pytest",
        "plugin_manifest_sha256": plugin_manifest_sha256,
        "current_plan_schema_version": 5,
        "project_input_sha256": "2" * 64,
        "project_output_sha256": "3" * 64,
        "layout_state": "BOOTSTRAPPING" if bootstrapping else "LAYOUT_READY",
        "evidence_ref": "evidence:.work-governance/evidence/bootstrap/pytest.json",
        "session_id": "pytest-session",
        "runtime_bundle_ref": bundle.relative_to(root).as_posix(),
        "runtime_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "controller_ref": controller_ref,
        "controller_sha256": controller_sha256,
        "lifecycle_ref": lifecycle_ref,
        "lifecycle_sha256": lifecycle_sha256,
    }
    receipt_path = (
        root / ".work-governance" / "runtime" / "bootstrap-capability.json"
        if bootstrapping
        else root / ".work-governance" / "bootstrap-state.json"
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if bootstrapping:
        claim = {
            "schema_version": 1,
            "kind": "work-governance-bootstrap-claim",
            "bootstrap_contract_version": 1,
            "action_revision": 4,
            "project_root": root.as_posix(),
            "created_at": "2026-07-28T00:00:00+00:00",
            "creator": "workctl",
            "controller_sha256": controller_sha256,
            "project_input_sha256": "4" * 64,
        }
        (root / ".work-governance" / "runtime" / "bootstrap-claim.json").write_text(
            json.dumps(claim, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return controller, hashlib.sha256(receipt_path.read_bytes()).hexdigest()


def run_workctl(
    cwd: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    supplied_environment = env or {}
    receipt = None
    layout_mutation = (
        len(args) >= 2 and args[0] == "layout" and args[1] not in {"status", "validate"}
    )
    if args and (args[0] != "layout" or layout_mutation):
        receipt = ensure_test_ready_receipt(
            cwd,
            allow_legacy_contract=(
                supplied_environment.get("TEST_WORKCTL_ALLOW_LEGACY_CONTRACT", "1") == "1"
            ),
            bootstrapping=layout_mutation,
        )
    executable = SCRIPT if receipt is None else receipt[0]
    command = [sys.executable, str(executable)]
    if receipt is not None:
        command.extend(["--receipt-sha256", receipt[1]])
    command.extend(args)
    result = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **supplied_environment},
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"workctl failed: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    return result


def init_plan(cwd: Path) -> None:
    run_workctl(cwd, "layout", "migrate")
    write_legacy_plan_fixture(cwd)


def write_legacy_plan_fixture(
    cwd: Path,
    *,
    plan_id: str = "PLAN-20260723-001",
    title: str = "Test",
) -> None:
    """Write a schema-v3 authority fixture without reopening production admission."""
    timestamp = "2026-07-23T00:00:00+00:00"
    plan_root = cwd / ".work-governance" / "_Plan"
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
    write_markdown_plan(
        plan_root / f"{plan_id}.md",
        frontmatter,
        "# Decision Summary\n\nInitialized test fixture.\n",
    )


def plan_path(cwd: Path) -> Path:
    return cwd / ".work-governance" / "_Plan" / "PLAN-20260723-001.md"


def read_plan(cwd: Path) -> tuple[dict[str, Any], str]:
    text = plan_path(cwd).read_text(encoding="utf-8")
    _, raw, body = text.split("---\n", 2)
    payload = yaml.safe_load(raw)
    assert isinstance(payload, dict)
    return payload, body


def read_plan_by_id(cwd: Path, plan_id: str) -> tuple[dict[str, Any], str]:
    text = (cwd / ".work-governance" / "_Plan" / f"{plan_id}.md").read_text(encoding="utf-8")
    _, raw, body = text.split("---\n", 2)
    payload = yaml.safe_load(raw)
    assert isinstance(payload, dict)
    return payload, body


def write_plan(cwd: Path, frontmatter: dict[str, Any], body: str = "# Body\n") -> None:
    text = yaml.safe_dump(frontmatter, sort_keys=False)
    plan_path(cwd).write_text(f"---\n{text}---\n{body}", encoding="utf-8")


def rewrite_plan_with_pyyaml_escaped_continuation(path: Path) -> None:
    """Inject the escaped quoted-scalar shape produced by PyYAML line wrapping."""
    text = path.read_text(encoding="utf-8")
    old = "  validation_standard: Every obligation has direct fresh evidence.\n"
    new = "\n".join(
        [
            '  validation_standard: "Risk feature hit \\u5DF2\\',
            "    \\u7531 fallback\\",
            '    \\ text tied."',
        ]
    )
    if old not in text:
        raise AssertionError("validation_standard fixture line drifted")
    path.write_text(text.replace(old, new + "\n", 1), encoding="utf-8")


def rewrite_plan_with_invalid_double_quoted_escape(path: Path) -> None:
    """Inject a genuinely invalid active Plan frontmatter syntax error."""
    text = path.read_text(encoding="utf-8")
    old = "  validation_standard: Every obligation has direct fresh evidence.\n"
    new = '  validation_standard: "Bad \\q escape"\n'
    if old not in text:
        raise AssertionError("validation_standard fixture line drifted")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def set_layout_action_revision(cwd: Path, revision: int) -> None:
    """Rewrite only the committed layout action revision in a test fixture."""
    version_path = cwd / ".work-governance" / "version.yaml"
    payload = yaml.safe_load(version_path.read_text(encoding="utf-8"))
    payload["legacy_migration_action_revision"] = revision
    version_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def sha256_path(path: Path) -> str:
    """Return a test fixture file's SHA256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_tree_snapshot(path: Path) -> dict[str, bytes]:
    """Capture regular-file bytes below a test directory."""
    return {
        candidate.relative_to(path).as_posix(): candidate.read_bytes()
        for candidate in sorted(path.rglob("*"))
        if candidate.is_file()
    }


def tree_inventory_snapshot(path: Path) -> dict[str, tuple[str, bytes | str]]:
    """Capture directories, symlinks, and regular bytes without following links."""
    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for candidate in sorted(path.rglob("*")):
        relative = candidate.relative_to(path).as_posix()
        if candidate.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(candidate))
        elif candidate.is_dir():
            snapshot[relative] = ("directory", "")
        elif candidate.is_file():
            snapshot[relative] = ("file", candidate.read_bytes())
    return snapshot


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
    run_workctl(cwd, "layout", "migrate")
    path = cwd / ".work-governance" / "_Plan" / f"{plan_id}.md"
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
    (cwd / ".work-governance" / "_Plan" / "index.yaml").write_text(
        yaml.safe_dump(index, sort_keys=False),
        encoding="utf-8",
    )
    return path


def adopt_legacy(cwd: Path, *, ref: str = "user:test-legacy-adoption") -> dict[str, Any]:
    """Bind the current legacy fixture snapshot to this physical worktree."""
    status = json.loads(run_workctl(cwd, "layout", "status").stdout)
    legacy = status["legacy"]
    result = run_workctl(
        cwd,
        "layout",
        "adopt",
        "--expected-manifest-sha256",
        legacy["manifest_sha256"],
        "--expected-active-plan-id",
        legacy["active_plan_id"],
        "--ref",
        ref,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "LEGACY_ADOPTED"
    return cast(dict[str, Any], payload)


def write_migratable_legacy(
    cwd: Path,
    plan_id: str = "PLAN-20260723-001",
    *,
    adopt: bool = True,
) -> Path:
    """Create a governed schema-v2 project-root layout eligible for migration."""
    path = cwd / "_Plan" / f"{plan_id}.md"
    write_markdown_plan(path, canonical_frontmatter(plan_id))
    index = {
        "schema_version": 1,
        "active_plan_id": plan_id,
        "plans": [
            {
                "id": plan_id,
                "path": path.name,
                "title": "Migratable Plan",
                "created_at": "2026-07-23T00:00:00+00:00",
            }
        ],
    }
    (cwd / "_Plan" / "index.yaml").write_text(
        yaml.safe_dump(index, sort_keys=False),
        encoding="utf-8",
    )
    pointer = cwd / "_Plan" / "PLAN-20260720-999.md"
    pointer.write_text(
        "# Generated Work Governance pointer\n\n"
        "- Marker: `WORK_GOVERNANCE_NON_AUTHORITY_POINTER`\n"
        f"- Canonical Plan: [{plan_id}]({plan_id}.md)\n",
        encoding="utf-8",
    )
    if adopt:
        adopt_legacy(cwd)
    return path


def write_legacy_reconciliation_proposal(cwd: Path) -> Path:
    """Create the closed pending proposal shape observed in PharmaceuticalGroup."""
    proposal = cwd / "_Plan" / "proposals" / "MIG-20260727-001"
    prepared = proposal / "PLAN-20260727-001.prepared.md"
    replacement = proposal / "AGENTS.proposed.md"
    manifest = proposal / "reconciliation.yaml"
    prepared_frontmatter = canonical_frontmatter("PLAN-20260727-001")
    prepared_frontmatter["schema_version"] = 3
    prepared_frontmatter.pop("authority")
    prepared_frontmatter["delivery"] = {
        "status": "pending",
        "boundary": "prepared-reconciliation",
        "evidence_ref": "project:MIG-20260727-001",
    }
    prepared_frontmatter["activation"] = {
        "status": "deferred",
        "current_ref": "legacy",
        "target_ref": "reconciled",
    }
    write_markdown_plan(prepared, prepared_frontmatter, "# Pending reconciled authority\n")
    replacement.write_text(
        "# AGENTS.md\n\nPending proposal bytes; never apply during layout migration.\n",
        encoding="utf-8",
    )
    active = cwd / "_Plan" / "PLAN-20260723-001.md"
    payload = {
        "migration_id": "MIG-20260727-001",
        "target_plan": {"prepared_file": prepared.name},
        "git_baseline": "34095d9dcb71ed51841de984350c7fbc871e8358",
        "sources": [
            {
                "path": "_Plan/PLAN-20260723-001.md",
                "role": "unmerged-source",
                "sha256": sha256_path(active),
                "revision": 1,
                "classification": "CONFIRMED_AUTHORITY",
            },
            {
                "path": "docs/Plan.md",
                "role": "merged-source",
                "sha256": "0" * 64,
                "classification": "CONFIRMED_AUTHORITY",
            },
        ],
        "agents_rewrite": {
            "path": "AGENTS.md",
            "sha256": "1" * 64,
            "replacement_file": replacement.name,
        },
        "confirmations": {},
    }
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return proposal


def claim_governance_root(cwd: Path) -> None:
    """Create the durable first-owner claim used by the controller."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_test_fixture")
    namespace["create_governance_claim"](cwd, creator="workctl")


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
                "path": ".work-governance/_Plan/PLAN-20260723-001.md",
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
            "`.work-governance/_Plan/PLAN-20260724-002.md` is the authoritative execution Plan "
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


def write_reconcile_upgrade_fixture(cwd: Path) -> Path:
    """Build exact child manifests for the composed two-transaction route."""
    reconciliation_manifest = write_reconciliation_fixture(cwd)
    prepared = cwd / "prepared.md"
    prepared_text = prepared.read_text(encoding="utf-8")
    _, prepared_raw, prepared_body = prepared_text.split("---\n", 2)
    prepared_frontmatter = cast(dict[str, Any], yaml.safe_load(prepared_raw))
    prepared_frontmatter["confirmations"]["required"].append(
        {
            "id": "C-CONTRACT-UPGRADE",
            "description": "Upgrade the reconciled schema-v3 Plan contract.",
            "status": "accepted",
            "ref": "user:contract-upgrade",
            "accepted_at": "2026-07-30T00:03:00+00:00",
        }
    )
    write_markdown_plan(prepared, prepared_frontmatter, prepared_body)
    bind_reconciliation_confirmations(
        cwd,
        reconciliation_manifest,
        include_agents_confirmation=False,
    )

    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_composed_fixture")
    _, target_doc, _ = namespace["prepare_reconciliation"](
        cwd,
        reconciliation_manifest,
        require_confirmations=True,
    )
    schema3_bytes = namespace["dump_plan"](target_doc).encode("utf-8")
    plan_id = cast(str, target_doc.frontmatter["plan_id"])

    evidence = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "contract-upgrade",
        "created_at": "2026-07-30T00:04:00+00:00",
        "producer_ref": "user:contract-upgrade",
        "items": [{"ref": "project:confirmed-contract", "sha256": "b" * 64}],
    }
    evidence_bytes = (
        json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        + b"\n"
    )
    evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
    evidence_path = (
        cwd / ".work-governance" / "_Plan" / ".evidence" / plan_id / f"{evidence_sha256}.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_bytes(evidence_bytes)

    contract_upgrade_manifest = cwd / "upgrade.yaml"
    contract_upgrade_manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "plan-contract-upgrade",
                "transaction_id": "UPG-20260730-001",
                "plan_id": plan_id,
                "expected_revision": target_doc.frontmatter["revision"],
                "plan_sha256": hashlib.sha256(schema3_bytes).hexdigest(),
                "confirmation_id": "C-CONTRACT-UPGRADE",
                "confirmation_ref": "user:contract-upgrade",
                "evidence_manifest": evidence_path.relative_to(cwd).as_posix(),
                "goal": {
                    "statement": "Preserve the reconciled authority and install schema v4.",
                    "success_conditions": ["Reconciliation commits before contract upgrade."],
                },
                "unknowns": [],
                "task_metadata": {
                    "T-001": {
                        "unknowns": [],
                        "expected_evidence_delta": (
                            "The reconciled route remains dependency-ready."
                        ),
                    }
                },
                "validation_provenance": {
                    "V-001": {
                        "kind": "code-invariant",
                        "source_ref": "project:index-last-reconciliation",
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    composed_manifest = cwd / "reconcile-upgrade.yaml"
    composed_manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "plan-reconcile-upgrade",
                "workflow_id": "RCU-20260730-001",
                "reconciliation_manifest": reconciliation_manifest.name,
                "reconciliation_manifest_sha256": sha256_path(reconciliation_manifest),
                "contract_upgrade_manifest": contract_upgrade_manifest.name,
                "contract_upgrade_manifest_sha256": sha256_path(contract_upgrade_manifest),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return composed_manifest


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
    """Build an active schema-v4 successor contract."""
    frontmatter = schema_v4_admission_plan(plan_id)
    frontmatter["title"] = "Successor Plan"
    frontmatter["goal"] = {
        "statement": "Deliver the successor route.",
        "success_conditions": ["The successor obligation and validation are verified."],
    }
    frontmatter["scope"] = {"include": ["Execute the successor route."], "exclude": []}
    frontmatter["obligations"] = [
        {"id": "O-001", "description": "Deliver the successor.", "status": "pending"}
    ]
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Execute safely.",
            "status": "pending",
            "unknowns": [],
            "expected_evidence_delta": "The successor output becomes reviewable.",
        }
    ]
    frontmatter["validations"] = [
        {
            "id": "V-001",
            "description": "Validate the successor.",
            "status": "pending",
            "provenance": {
                "kind": "confirmed-obligation",
                "source_ref": "project:O-001",
            },
        }
    ]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "successor.txt", "status": "pending"}]
    frontmatter["delivery"] = {
        "status": "pending",
        "boundary": "successor-delivery",
        "evidence_ref": "project:successor-not-yet-delivered",
    }
    frontmatter["route"] = {
        "route_status": "active",
        "slice_status": "initialized",
        "next_phase": "Execute T-001.",
        "validation_standard": "Fresh evidence covers O-001 and V-001.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {"route_status": "active", "next_step": "Execute T-001."}
    return frontmatter


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
    index = cwd / ".work-governance" / "_Plan" / "index.yaml"
    manifest = {
        "schema_version": 1,
        "rollover_id": "ROL-20260727-001",
        "source_plan": {
            "path": ".work-governance/_Plan/PLAN-20260723-001.md",
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


def retirement_disposition(
    *,
    item_id: str | None = None,
    disposition: str = "superseded",
) -> dict[str, str]:
    """Build one exact retirement disposition bound to the approving user."""
    record = {
        "disposition": disposition,
        "reason": "The user replaced the obsolete route.",
        "resolution_ref": "user:approved-retirement",
    }
    if item_id is not None:
        record["id"] = item_id
    return record


def write_retirement_fixture(cwd: Path) -> Path:
    """Create one active schema-v4 Plan and its exact retirement proposal."""
    run_workctl(cwd, "layout", "migrate")
    plan_id = "PLAN-20260728-009"
    frontmatter = schema_v4_admission_plan(plan_id)
    frontmatter["obligations"] = [
        {"id": "O-001", "description": "Deliver the obsolete route.", "status": "pending"}
    ]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "obsolete.txt", "status": "pending"}]
    prepared = cwd / "retirement-source.md"
    write_markdown_plan(prepared, frontmatter, "# Obsolete route\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-009",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = cwd / "retirement-admission.yaml"
    admission_path.write_text(
        yaml.safe_dump(admission, sort_keys=False),
        encoding="utf-8",
    )
    run_workctl(cwd, "plan", "admit", "apply", "--manifest", str(admission_path))
    source = cwd / ".work-governance" / "_Plan" / f"{plan_id}.md"
    index = cwd / ".work-governance" / "_Plan" / "index.yaml"
    manifest = {
        "schema_version": 1,
        "kind": "plan-retirement",
        "retirement_id": "RET-20260729-001",
        "source_plan": {
            "path": f".work-governance/_Plan/{plan_id}.md",
            "plan_id": plan_id,
            "revision": 1,
            "sha256": sha256_path(source),
        },
        "index_baseline": {
            "active_plan_id": plan_id,
            "sha256": sha256_path(index),
        },
        "reason": "The user replaced the obsolete route with a fresh analysis.",
        "dispositions": {
            "obligations": [retirement_disposition(item_id="O-001")],
            "tasks": [retirement_disposition(item_id="T-001")],
            "validations": [retirement_disposition(item_id="V-001")],
            "artifacts": [retirement_disposition(item_id="A-001", disposition="preserved")],
            "delivery": retirement_disposition(),
            "route": retirement_disposition(),
            "handoff": retirement_disposition(),
        },
        "confirmations": {},
    }
    manifest_path = cwd / "retirement.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return manifest_path


def bind_retirement_confirmation(cwd: Path, manifest_path: Path) -> dict[str, Any]:
    """Bind C-PLAN-RETIREMENT to the exact dry-run proposal digest."""
    dry_run = cast(
        dict[str, Any],
        json.loads(
            run_workctl(
                cwd,
                "plan",
                "retire",
                "apply",
                "--manifest",
                str(manifest_path),
                "--dry-run",
            ).stdout
        ),
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["confirmations"]["retirement"] = {
        "id": "C-PLAN-RETIREMENT",
        "ref": "user:approved-retirement",
        "accepted_at": "2026-07-29T10:00:00+00:00",
        "evidence_sha256": dry_run["proposal_sha256"],
    }
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return dry_run


def test_layout_not_applicable_commits_contract_without_plan(tmp_path: Path) -> None:
    """No-Plan bootstrap commits only the layout contract and local lock."""
    before = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migrated = run_workctl(tmp_path, "layout", "migrate")
    after = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    governance = tmp_path / ".work-governance"
    assert before["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert before["legacy"]["classification"] == "NOT_APPLICABLE"
    assert migrated.stdout.strip() == "LAYOUT_COMMITTED not_applicable"
    assert after["layout_state"] == "LAYOUT_READY"
    assert after["plan_authority_state"] == "UNMANAGED_EMPTY"
    assert not (governance / "_Plan").exists()
    assert (governance / ".gitignore").read_text(encoding="utf-8") == (
        "/logs/\n"
        "/worktrees/\n"
        "/cache/\n"
        "/proposals/\n"
        "/evidence/\n"
        "/runtime/\n"
        "/bootstrap-state.json\n"
        "/workctl.lock\n"
    )
    version = yaml.safe_load((governance / "version.yaml").read_text(encoding="utf-8"))
    assert version["schema_version"] == 1
    assert version["layout_version"] == 1
    assert version["bootstrap_contract_version"] == 1
    assert version["plugin_compatibility"] == ">=1.0.0,<2.0.0"
    assert version["migration"]["status"] == "not_applicable"
    completion = version["migration"]["completion_evidence"]
    receipt = {
        "action": "layout-not-applicable",
        "completed_at": completion["completed_at"],
        "legacy_classification": "NOT_APPLICABLE",
    }
    assert completion["kind"] == "not-applicable-receipt"
    assert completion["path"] == "not-applicable"
    assert (
        completion["sha256"]
        == hashlib.sha256(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"


def test_layout_validate_does_not_parse_active_plan_frontmatter(tmp_path: Path) -> None:
    """Layout validation stays scoped to layout even when the active Plan is unreadable."""
    run_workctl(tmp_path, "layout", "migrate")
    write_legacy_plan_fixture(tmp_path, plan_id="PLAN-20260805-001")
    rewrite_plan_with_invalid_double_quoted_escape(
        tmp_path / ".work-governance" / "_Plan" / "PLAN-20260805-001.md"
    )

    layout = run_workctl(
        tmp_path,
        "layout",
        "validate",
        env={"WORK_GOVERNANCE_DISABLE_PYYAML": "1"},
    )
    status = json.loads(
        run_workctl(
            tmp_path,
            "layout",
            "status",
            env={"WORK_GOVERNANCE_DISABLE_PYYAML": "1"},
        ).stdout
    )
    plan = run_workctl(
        tmp_path,
        "plan",
        "validate",
        check=False,
        env={"WORK_GOVERNANCE_DISABLE_PYYAML": "1"},
    )

    assert layout.stdout.strip() == "LAYOUT_VALID"
    assert status["layout_state"] == "LAYOUT_READY"
    assert status["plan_authority_state"] == "MIGRATION_RECOVERY_REQUIRED"
    assert plan.returncode == 1
    assert "INVALID_PLAN_FRONTMATTER_YAML" in plan.stderr
    assert "Traceback" not in plan.stderr


def test_pyyaml_escaped_continuation_plan_validates_without_pyyaml(
    tmp_path: Path,
) -> None:
    """The fallback reader accepts the PyYAML continuation shape from the incident."""
    run_workctl(tmp_path, "layout", "migrate")
    write_legacy_plan_fixture(tmp_path, plan_id="PLAN-20260805-001")
    active = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260805-001.md"
    rewrite_plan_with_pyyaml_escaped_continuation(active)

    validation = run_workctl(
        tmp_path,
        "plan",
        "validate",
        env={"WORK_GOVERNANCE_DISABLE_PYYAML": "1"},
    )

    assert validation.stdout.strip() == "PLAN_VALID"


def test_layout_preserves_ordinary_business_plan_directory(tmp_path: Path) -> None:
    """A project-owned root _Plan with no controller features is never absorbed."""
    business = tmp_path / "_Plan"
    business.mkdir()
    artifact = business / "roadmap.txt"
    artifact.write_text("business bytes\n", encoding="utf-8")

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    run_workctl(tmp_path, "layout", "migrate")

    assert status["legacy"]["classification"] == "NOT_APPLICABLE"
    assert artifact.read_bytes() == b"business bytes\n"
    assert not (tmp_path / ".work-governance" / "_Plan").exists()


def test_layout_classifier_requires_explicit_worktree_adoption(tmp_path: Path) -> None:
    """A valid-looking Plan tree is not absorbed without an explicit local receipt."""
    source = write_migratable_legacy(tmp_path, adopt=False)

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert status["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert status["legacy"]["classification"] == "AMBIGUOUS"
    assert any(
        "lacks an explicit worktree adoption receipt" in reason
        for reason in status["legacy"]["blocking_reasons"]
    )
    assert migration.returncode == 2
    assert source.is_file()


def test_layout_migrates_observed_pending_reconciliation_proposal_side_tree(
    tmp_path: Path,
) -> None:
    """A valid old proposal remains pending and byte-identical outside Plan authority."""
    source = write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    proposal_before = file_tree_snapshot(proposal)

    before_adoption = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert before_adoption["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert before_adoption["legacy"]["blocking_reasons"] == [
        "legacy authority lacks an explicit worktree adoption receipt"
    ]

    adopt_legacy(tmp_path)
    ready_to_migrate = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    assert ready_to_migrate["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"

    run_workctl(tmp_path, "layout", "migrate")

    target_proposal = tmp_path / ".work-governance" / "proposals" / "MIG-20260727-001"
    assert file_tree_snapshot(target_proposal) == proposal_before
    assert not (tmp_path / ".work-governance" / "_Plan" / "proposals").exists()
    assert not (tmp_path / "_Plan").exists()
    migrated = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260723-001.md"
    migrated_frontmatter = yaml.safe_load(migrated.read_text(encoding="utf-8").split("---\n")[1])
    assert migrated_frontmatter["revision"] == 2
    assert source.name == migrated.name
    assert (
        yaml.safe_load((target_proposal / "reconciliation.yaml").read_text(encoding="utf-8"))[
            "confirmations"
        ]
        == {}
    )


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "mixed-business-file",
        "symlink",
        "malformed-manifest",
        "broken-prepared-reference",
        "nonempty-confirmations",
    ],
)
def test_layout_rejects_unproven_legacy_proposal_content(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    """Directory naming alone never proves proposal ownership."""
    write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    if invalid_kind == "mixed-business-file":
        (proposal / "business.txt").write_text("not governance-owned\n", encoding="utf-8")
    elif invalid_kind == "symlink":
        (proposal / "linked.md").symlink_to(tmp_path / "_Plan" / "index.yaml")
    elif invalid_kind == "malformed-manifest":
        (proposal / "reconciliation.yaml").write_text("- not-a-mapping\n", encoding="utf-8")
    elif invalid_kind == "broken-prepared-reference":
        (proposal / "PLAN-20260727-001.prepared.md").unlink()
    else:
        manifest_path = proposal / "reconciliation.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["confirmations"] = {
            "C-MIGRATION-BASELINE": {
                "status": "accepted",
                "ref": "user:prior-decision",
            }
        }
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    assert status["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert any(
        "legacy proposal" in reason or "LAYOUT_PATH_SYMLINK" in reason
        for reason in status["legacy"]["blocking_reasons"]
    )
    manifest_sha256 = status["legacy"]["manifest_sha256"]
    if isinstance(manifest_sha256, str):
        adoption = run_workctl(
            tmp_path,
            "layout",
            "adopt",
            "--expected-manifest-sha256",
            manifest_sha256,
            "--expected-active-plan-id",
            "PLAN-20260723-001",
            "--ref",
            "user:test-invalid-proposal",
            check=False,
        )
        assert adoption.returncode == 2
    assert (tmp_path / "_Plan").is_dir()


def test_layout_recovers_after_proposal_side_tree_activation(tmp_path: Path) -> None:
    """A crash after proposal rename resumes without duplicate or guessed content."""
    write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    proposal_before = file_tree_snapshot(proposal)
    adopt_legacy(tmp_path)

    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "proposal-activation"},
    )

    assert interrupted.returncode == 2
    assert "LAYOUT_TEST_INTERRUPTED: proposal-activation" in interrupted.stderr
    target = tmp_path / ".work-governance" / "proposals" / "MIG-20260727-001"
    assert file_tree_snapshot(target) == proposal_before
    assert not (tmp_path / ".work-governance" / "version.yaml").exists()

    recovered = run_workctl(tmp_path, "layout", "recover")

    assert "LAYOUT_COMMITTED" in recovered.stdout
    assert file_tree_snapshot(target) == proposal_before
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"


def test_layout_recovers_between_multiple_proposal_activations(tmp_path: Path) -> None:
    """A crash between per-proposal renames resumes the journal-bound remainder."""
    write_migratable_legacy(tmp_path, adopt=False)
    first = write_legacy_reconciliation_proposal(tmp_path)
    second = first.parent / "MIG-20260727-002"
    shutil.copytree(first, second)
    second_manifest_path = second / "reconciliation.yaml"
    second_manifest = yaml.safe_load(second_manifest_path.read_text(encoding="utf-8"))
    second_manifest["migration_id"] = second.name
    second_manifest_path.write_text(
        yaml.safe_dump(second_manifest, sort_keys=False),
        encoding="utf-8",
    )
    first_before = file_tree_snapshot(first)
    second_before = file_tree_snapshot(second)
    adopt_legacy(tmp_path)

    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "proposal-activation-MIG-20260727-001"},
    )
    target_root = tmp_path / ".work-governance" / "proposals"
    journal_path = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*/journal.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    staged_root = Path(journal["paths"]["staged_proposals"])
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert interrupted.returncode == 2
    assert "LAYOUT_TEST_INTERRUPTED: proposal-activation-MIG-20260727-001" in interrupted.stderr
    assert file_tree_snapshot(target_root / first.name) == first_before
    assert file_tree_snapshot(staged_root / second.name) == second_before
    assert status["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"

    recovered = run_workctl(tmp_path, "layout", "recover")

    assert recovered.stdout.startswith("LAYOUT_COMMITTED LAY-")
    assert file_tree_snapshot(target_root / first.name) == first_before
    assert file_tree_snapshot(target_root / second.name) == second_before
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"


def test_layout_recovery_rejects_staged_proposal_drift(tmp_path: Path) -> None:
    """A changed staged proposal cannot cross the activation boundary."""
    write_migratable_legacy(tmp_path, adopt=False)
    write_legacy_reconciliation_proposal(tmp_path)
    adopt_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "staged"},
    )
    assert interrupted.returncode == 2
    journal_path = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*/journal.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    staged_manifest = (
        Path(journal["paths"]["staged_proposals"]) / "MIG-20260727-001" / "reconciliation.yaml"
    )
    staged_manifest.write_text(
        staged_manifest.read_text(encoding="utf-8") + "# drift\n",
        encoding="utf-8",
    )

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "STAGED_LAYOUT_PROPOSALS_MANIFEST_MISMATCH" in recovery.stderr
    assert (tmp_path / "_Plan").is_dir()


def test_layout_recovery_rejects_original_evidence_drift_after_staging(
    tmp_path: Path,
) -> None:
    """A staged recovery cannot commit after its durable original copy changes."""
    write_migratable_legacy(tmp_path, adopt=False)
    write_legacy_reconciliation_proposal(tmp_path)
    adopt_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "staged"},
    )
    assert interrupted.returncode == 2
    governance = tmp_path / ".work-governance"
    journal_path = next((governance / "runtime").glob("LAY-*/journal.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    original = Path(journal["paths"]["original_evidence"]) / str(journal["active_plan_path"])
    original.write_bytes(original.read_bytes() + b"\nORIGINAL-EVIDENCE-DRIFT\n")

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "LAYOUT_ORIGINAL_EVIDENCE_MANIFEST_MISMATCH" in recovery.stderr
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "staged"
    assert not (governance / "version.yaml").exists()
    assert (tmp_path / "_Plan").is_dir()


def test_controller_resolves_only_the_nearest_linked_worktree_plan(tmp_path: Path) -> None:
    """Nested invocations use the physical linked worktree that owns their Git marker."""
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
    run_workctl(repository, "layout", "migrate")
    write_legacy_plan_fixture(
        repository,
        plan_id="PLAN-20260727-101",
        title="Main Plan",
    )
    run_workctl(linked, "layout", "migrate")
    write_legacy_plan_fixture(
        linked,
        plan_id="PLAN-20260727-202",
        title="Feature Plan",
    )
    main_nested = repository / "src" / "deep"
    linked_nested = linked / "src" / "deep"
    main_nested.mkdir(parents=True)
    linked_nested.mkdir(parents=True)
    main_before = sha256_path(repository / ".work-governance" / "_Plan" / "PLAN-20260727-101.md")
    linked_before = sha256_path(linked / ".work-governance" / "_Plan" / "PLAN-20260727-202.md")

    main_status = json.loads(run_workctl(main_nested, "plan", "status").stdout)
    linked_status = json.loads(run_workctl(linked_nested, "plan", "status").stdout)

    assert main_status["plan_id"] == "PLAN-20260727-101"
    assert linked_status["plan_id"] == "PLAN-20260727-202"
    assert (
        sha256_path(repository / ".work-governance" / "_Plan" / "PLAN-20260727-101.md")
        == main_before
    )
    assert (
        sha256_path(linked / ".work-governance" / "_Plan" / "PLAN-20260727-202.md") == linked_before
    )


def test_legacy_adoption_receipt_cannot_replay_across_worktrees(tmp_path: Path) -> None:
    """A receipt copied from main does not authorize an identical sibling snapshot."""
    repository = tmp_path / "repository"
    repository.mkdir()
    write_migratable_legacy(repository, adopt=False)
    (repository / ".gitignore").write_text("/.worktree/\n", encoding="utf-8")
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
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "legacy baseline"], cwd=repository, check=True)
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
    main_receipt = adopt_legacy(repository)
    claim_governance_root(linked)
    linked_receipt = linked / ".work-governance" / "runtime" / "legacy-adoption.json"
    shutil.copy2(repository / main_receipt["receipt"], linked_receipt)

    replayed = json.loads(run_workctl(linked, "layout", "status").stdout)

    assert replayed["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert any(
        "does not match this worktree" in reason
        for reason in replayed["legacy"]["blocking_reasons"]
    )
    adopt_legacy(linked, ref="user:test-linked-adoption")
    adopted = json.loads(run_workctl(linked, "layout", "status").stdout)
    assert adopted["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert (repository / "_Plan").is_dir()
    assert (linked / "_Plan").is_dir()


@pytest.mark.parametrize("ignore_bytes", [None, "business-cache/\n"])
def test_layout_never_claims_a_preexisting_unversioned_governance_root(
    tmp_path: Path, ignore_bytes: str | None
) -> None:
    """An existing same-named project directory cannot be adopted by convention."""
    governance = tmp_path / ".work-governance"
    governance.mkdir()
    business = governance / "business.txt"
    business.write_bytes(b"project-owned bytes\n")
    if ignore_bytes is not None:
        (governance / ".gitignore").write_text(ignore_bytes, encoding="utf-8")

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert status["layout_state"] == "ENVIRONMENT_BLOCKED"
    assert migration.returncode == 2
    assert "GOVERNANCE_ROOT_OWNERSHIP_UNPROVEN" in migration.stderr
    assert business.read_bytes() == b"project-owned bytes\n"
    if ignore_bytes is not None:
        assert (governance / ".gitignore").read_text(encoding="utf-8") == ignore_bytes


def test_unauthenticated_controller_cannot_create_a_governance_claim(
    tmp_path: Path,
) -> None:
    """A test interruption variable cannot bypass the receipt gate on a fresh root."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "layout", "migrate"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "WORKCTL_TEST_BOOTSTRAP_INTERRUPT_AFTER_CLAIM": "1",
        },
    )

    assert result.returncode == 2
    assert "BOOTSTRAP_RECEIPT_REQUIRED" in result.stderr
    assert not (tmp_path / ".work-governance").exists()
    assert not (tmp_path / ".work-governance.bootstrap").exists()


def test_durable_replace_fsyncs_both_directory_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cross-directory rename is not considered durable until both parents sync."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_durability_fixture")
    filesystem_module = namespace["module_filesystem"]
    source = tmp_path / "source" / "tree"
    target = tmp_path / "target" / "tree"
    events: list[tuple[str, Path, Path | None]] = []

    monkeypatch.setattr(
        filesystem_module.os,
        "replace",
        lambda old, new: events.append(("replace", old, new)),
    )
    monkeypatch.setattr(
        filesystem_module,
        "fsync_directory",
        lambda path: events.append(("fsync", path, None)),
    )

    namespace["durable_replace"](source, target)

    assert events == [
        ("replace", source, target),
        ("fsync", source.parent, None),
        ("fsync", target.parent, None),
    ]


def test_transaction_durability_orders_file_data_before_directory_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staged trees and copied files sync data before their containing entries."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_data_durability_fixture")
    filesystem_module = namespace["module_filesystem"]
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

    namespace["fsync_tree"](tree)
    tree_events = list(events)
    assert [event[0] for event in tree_events] == [
        "file-fsync",
        "file-fsync",
        "dir-fsync",
        "dir-fsync",
    ]
    assert tree_events[-2:] == [("dir-fsync", child), ("dir-fsync", tree)]

    events.clear()
    namespace["durable_copy_file"](tree / "root.txt", target)
    assert target.read_bytes() == b"root\n"
    assert [event[0] for event in events] == ["file-fsync", "dir-fsync"]
    assert events[-1] == ("dir-fsync", target_parent)

    events.clear()
    namespace["durable_unlink"](target)
    assert not target.exists()
    assert events == [("dir-fsync", target_parent)]


def test_layout_claim_does_not_authorize_unregistered_local_content(tmp_path: Path) -> None:
    """A valid claim cannot be used to absorb business content under an allowed name."""
    claim_governance_root(tmp_path)
    business = tmp_path / ".work-governance" / "logs" / "business.log"
    business.parent.mkdir()
    business.write_bytes(b"project-owned bytes\n")

    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert migration.returncode == 2
    assert "uncommitted governance local path is not empty: logs" in migration.stderr
    assert business.read_bytes() == b"project-owned bytes\n"
    assert not (tmp_path / ".work-governance" / "version.yaml").exists()


def test_ordinary_controller_commands_require_layout_ready(tmp_path: Path) -> None:
    """Plan commands fail closed until the independent layout axis is ready."""
    blocked = run_workctl(tmp_path, "plan", "authority", "check", check=False)
    run_workctl(tmp_path, "layout", "migrate")
    ready = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)

    assert blocked.returncode == 2
    assert "LAYOUT_BLOCKED: LAYOUT_MIGRATION_REQUIRED" in blocked.stderr
    assert ready["authority_state"] == "UNMANAGED_EMPTY"


def test_plan_init_writes_only_canonical_governance_root(tmp_path: Path) -> None:
    """Normal authority creation never targets the project-root legacy directory."""
    init_plan(tmp_path)

    assert plan_path(tmp_path).is_file()
    assert (tmp_path / ".work-governance" / "_Plan" / "index.yaml").is_file()
    assert not (tmp_path / "_Plan").exists()
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    assert status["layout_state"] == "LAYOUT_READY"
    assert status["plan_authority_state"] == "PLAN_SCHEMA_REFRESH_REQUIRED"


def test_layout_migrates_strict_legacy_authority_and_commits_version(
    tmp_path: Path,
) -> None:
    """A strictly classified legacy authority migrates and validates end to end."""
    source = write_migratable_legacy(tmp_path)
    before_revision = canonical_frontmatter("PLAN-20260723-001")["revision"]

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migrated = run_workctl(tmp_path, "layout", "migrate")
    final = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    target = tmp_path / ".work-governance" / "_Plan" / source.name
    frontmatter, _body = read_plan(tmp_path)
    version = yaml.safe_load(
        (tmp_path / ".work-governance" / "version.yaml").read_text(encoding="utf-8")
    )
    assert status["legacy"]["classification"] == "MIGRATABLE"
    assert migrated.stdout.startswith("LAYOUT_COMMITTED LAY-")
    assert final["layout_state"] == "LAYOUT_READY"
    assert final["plan_authority_state"] == "PLAN_SCHEMA_REFRESH_REQUIRED"
    assert target.is_file()
    assert not (tmp_path / "_Plan").exists()
    assert frontmatter["revision"] == before_revision + 1
    assert version["migration"]["status"] == "migrated"
    proof = list((tmp_path / ".work-governance" / "_Plan" / ".migrations").glob("LAY-*.yaml"))
    assert len(proof) == 1
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"
    refresh = json.loads(
        run_workctl(
            tmp_path,
            "migrate",
            "inspect",
            env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
        ).stdout
    )
    assert refresh["requires_migration"] is True
    assert refresh["migration_mode"] == "archive_legacy_and_rebuild_current_plan"


def test_current_controller_honors_supported_prior_adoption_receipt(
    tmp_path: Path,
) -> None:
    """A user-bound action-3 adoption remains authoritative across the action upgrade."""
    write_migratable_legacy(tmp_path)
    adoption = tmp_path / ".work-governance" / "runtime" / "legacy-adoption.json"
    payload = json.loads(adoption.read_text(encoding="utf-8"))
    payload["action_revision"] = 3
    payload["controller_sha256"] = "a" * 64
    adoption.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migrated = run_workctl(tmp_path, "layout", "migrate")

    assert status["legacy"]["classification"] == "MIGRATABLE"
    assert migrated.stdout.startswith("LAYOUT_COMMITTED LAY-")
    assert (
        json.loads(run_workctl(tmp_path, "layout", "status").stdout)["layout_state"]
        == "LAYOUT_READY"
    )


def test_layout_migrates_schema_one_confirmation_without_inventing_timestamp(
    tmp_path: Path,
) -> None:
    """A pre-timestamp schema-v1 decision remains truthful during migration."""
    source = write_migratable_legacy(tmp_path, adopt=False)
    frontmatter = legacy_frontmatter("PLAN-20260723-001")
    frontmatter["confirmations"]["accepted"] = [
        {
            "id": "C-001",
            "description": "Legacy user authorization.",
            "status": "accepted",
            "ref": "user message 2026-07-23: continue",
        }
    ]
    frontmatter["scope"]["include"].extend(["_Plan/", "_Plan/business-output"])
    frontmatter["scope"]["exclude"].append("_Plan")
    write_markdown_plan(source, frontmatter)
    adopt_legacy(tmp_path)

    before = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migrated = run_workctl(tmp_path, "layout", "migrate")
    after, _body = read_plan(tmp_path)
    decision = after["confirmations"]["accepted"][0]

    assert before["legacy"]["classification"] == "MIGRATABLE"
    assert migrated.stdout.startswith("LAYOUT_COMMITTED LAY-")
    assert after["revision"] == frontmatter["revision"] + 1
    assert decision["ref"] == "user message 2026-07-23: continue"
    assert "accepted_at" not in decision
    assert "decided_at" not in decision
    assert ".work-governance/_Plan/" in after["scope"]["include"]
    assert ".work-governance/_Plan" in after["scope"]["exclude"]
    assert "_Plan/business-output" in after["scope"]["include"]
    assert "_Plan/" not in after["scope"]["include"]
    assert "_Plan" not in after["scope"]["exclude"]
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    plan_validation = run_workctl(
        tmp_path,
        "plan",
        "validate",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
    )
    assert status["layout_state"] == "LAYOUT_READY"
    assert status["plan_authority_state"] == "PLAN_SCHEMA_REFRESH_REQUIRED"
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"
    assert plan_validation.returncode == 1
    assert "authority state is PLAN_SCHEMA_REFRESH_REQUIRED" in plan_validation.stderr


def test_layout_classifier_rejects_invalid_current_schema_before_transaction(
    tmp_path: Path,
) -> None:
    """Current-schema incompatibility fails closed before a journal is created."""
    source = write_migratable_legacy(tmp_path, adopt=False)
    frontmatter = canonical_frontmatter("PLAN-20260723-001")
    frontmatter["confirmations"]["accepted"] = [
        {
            "id": "C-001",
            "description": "Malformed current-schema authorization.",
            "status": "accepted",
            "ref": "user:test",
        }
    ]
    write_markdown_plan(source, frontmatter)

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert status["legacy"]["classification"] == "AMBIGUOUS"
    assert status["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert any(
        "C-001 resolved confirmation requires a timestamp" in blocker
        for blocker in status["legacy"]["blocking_reasons"]
    )
    assert migration.returncode == 2
    assert "LAYOUT_MIGRATION_BLOCKED: LEGACY_CLASSIFICATION_REQUIRED" in migration.stderr
    runtime = tmp_path / ".work-governance" / "runtime"
    assert not any(path.name.startswith("LAY-") for path in runtime.iterdir())


@pytest.mark.parametrize(
    "phase",
    ["staged", "legacy-rename", "legacy-backup", "plan-activation", "version"],
)
def test_layout_recover_forwards_every_interruption(tmp_path: Path, phase: str) -> None:
    """Each durable transaction phase converges through layout recover."""
    write_migratable_legacy(tmp_path)

    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": phase},
    )
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    recovered = run_workctl(tmp_path, "layout", "recover")

    assert interrupted.returncode == 2
    assert f"LAYOUT_TEST_INTERRUPTED: {phase}" in interrupted.stderr
    assert status["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"
    assert recovered.stdout.startswith("LAYOUT_COMMITTED LAY-")
    assert (
        json.loads(run_workctl(tmp_path, "layout", "status").stdout)["layout_state"]
        == "LAYOUT_READY"
    )


def test_layout_recovery_refuses_activation_guard_drift(tmp_path: Path) -> None:
    """Recovery does not guess after the old-root activation marker changes."""
    write_migratable_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "legacy-backup"},
    )
    assert interrupted.returncode == 2
    guard = tmp_path / "_Plan"
    assert guard.is_file()
    guard.write_text("drifted marker\n", encoding="utf-8")

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "LAYOUT_ACTIVATION_GUARD_DRIFT" in recovery.stderr
    assert not (tmp_path / ".work-governance" / "version.yaml").exists()


def test_layout_proof_is_immutable_and_version_supplies_commitment(tmp_path: Path) -> None:
    """The proof stays prepared; only the hash-binding version commits the layout."""
    write_migratable_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "plan-activation"},
    )
    assert interrupted.returncode == 2
    proof_path = next((tmp_path / ".work-governance" / "_Plan" / ".migrations").glob("LAY-*.yaml"))
    prepared = yaml.safe_load(proof_path.read_text(encoding="utf-8"))

    assert prepared["status"] == "prepared"
    assert "completed_at" not in prepared

    run_workctl(tmp_path, "layout", "recover")
    final_proof = yaml.safe_load(proof_path.read_text(encoding="utf-8"))
    version = yaml.safe_load(
        (tmp_path / ".work-governance" / "version.yaml").read_text(encoding="utf-8")
    )
    assert final_proof == prepared
    assert (
        version["migration"]["completion_evidence"]["sha256"]
        == hashlib.sha256(proof_path.read_bytes()).hexdigest()
    )


def test_layout_rejects_forged_proof_even_when_version_hash_is_updated(
    tmp_path: Path,
) -> None:
    """Completion evidence must satisfy its schema, not merely match arbitrary bytes."""
    write_migratable_legacy(tmp_path)
    run_workctl(tmp_path, "layout", "migrate")
    proof_path = next((tmp_path / ".work-governance" / "_Plan" / ".migrations").glob("LAY-*.yaml"))
    version_path = tmp_path / ".work-governance" / "version.yaml"
    proof = yaml.safe_load(proof_path.read_text(encoding="utf-8"))
    proof["kind"] = "project-owned-bytes"
    proof_path.write_text(yaml.safe_dump(proof, sort_keys=False), encoding="utf-8")
    version = yaml.safe_load(version_path.read_text(encoding="utf-8"))
    version["migration"]["completion_evidence"]["sha256"] = hashlib.sha256(
        proof_path.read_bytes()
    ).hexdigest()
    version_path.write_text(yaml.safe_dump(version, sort_keys=False), encoding="utf-8")

    validation = run_workctl(tmp_path, "layout", "validate", check=False)

    assert validation.returncode == 2
    assert "migration proof fields do not match the commitment" in validation.stderr


def test_layout_recovery_rejects_snapshot_drift(tmp_path: Path) -> None:
    """A staged transaction never activates after any legacy input changes."""
    source = write_migratable_legacy(tmp_path)
    run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "staged"},
    )
    source.write_text(source.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "LEGACY_LAYOUT_INPUT_DRIFT" in recovery.stderr
    assert (tmp_path / "_Plan").is_dir()
    assert not (tmp_path / ".work-governance" / "_Plan").exists()


def test_layout_recovery_rejects_proven_log_drift(tmp_path: Path) -> None:
    """A proven governance log remains frozen after transaction staging."""
    write_migratable_legacy(tmp_path)
    governed_log = tmp_path / ".logs" / "PLAN-20260723-001.jsonl"
    governed_log.parent.mkdir()
    governed_log.write_text(
        '{"kind":"validation","plan_id":"PLAN-20260723-001"}\n',
        encoding="utf-8",
    )
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "staged"},
    )
    assert interrupted.returncode == 2
    governed_log.write_text(
        governed_log.read_text(encoding="utf-8") + "drift\n",
        encoding="utf-8",
    )

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "LAYOUT_LOG_INPUT_DRIFT: .logs/PLAN-20260723-001.jsonl" in recovery.stderr
    assert (tmp_path / "_Plan").is_dir()
    assert not (tmp_path / ".work-governance" / "_Plan").exists()


def test_layout_recovery_rejects_staging_drift(tmp_path: Path) -> None:
    """The staged target manifest is immutable after its validation point."""
    write_migratable_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "staged"},
    )
    assert interrupted.returncode == 2
    journal_path = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*/journal.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    staged_active = Path(journal["paths"]["staged_plan"]) / journal["active_plan_path"]
    staged_active.write_text(
        staged_active.read_text(encoding="utf-8") + "drift\n",
        encoding="utf-8",
    )

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "STAGED_LAYOUT_MANIFEST_MISMATCH" in recovery.stderr


def test_layout_moves_only_proven_logs(tmp_path: Path) -> None:
    """Plan-scoped logs move while unrelated business logs remain byte-identical."""
    write_migratable_legacy(tmp_path)
    legacy_logs = tmp_path / ".logs"
    legacy_logs.mkdir()
    governed = legacy_logs / "PLAN-20260723-001.jsonl"
    governed.write_text(
        '{"kind":"validation","plan_id":"PLAN-20260723-001","revision":1}\n',
        encoding="utf-8",
    )
    business = legacy_logs / "business.log"
    business.write_bytes(b"business bytes\n")

    run_workctl(tmp_path, "layout", "migrate")

    migrated = tmp_path / ".work-governance" / "logs" / "PLAN-20260723-001.jsonl"
    assert migrated.is_file()
    assert not governed.exists()
    assert business.read_bytes() == b"business bytes\n"


def test_layout_reappeared_legacy_features_fail_closed(tmp_path: Path) -> None:
    """A post-migration old-controller write is detected instead of reabsorbed."""
    write_migratable_legacy(tmp_path)
    run_workctl(tmp_path, "layout", "migrate")
    reappeared = tmp_path / "_Plan"
    reappeared.mkdir()
    (reappeared / ".workctl.lock").write_text("", encoding="utf-8")

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    blocked = run_workctl(tmp_path, "plan", "status", check=False)

    assert status["layout_state"] == "LEGACY_ROOT_REAPPEARED"
    assert blocked.returncode == 2
    assert "LAYOUT_BLOCKED: LEGACY_ROOT_REAPPEARED" in blocked.stderr


@pytest.mark.parametrize("hazard", ["mixed-child", "symlink", "partial-index"])
def test_layout_classifier_fails_closed_on_ambiguous_legacy_roots(
    tmp_path: Path, hazard: str
) -> None:
    """Partial, mixed, and symlinked legacy roots require explicit classification."""
    if hazard == "partial-index":
        legacy = tmp_path / "_Plan"
        legacy.mkdir()
        (legacy / "index.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    else:
        source = write_migratable_legacy(tmp_path)
        if hazard == "mixed-child":
            (source.parent / "business.txt").write_text("project-owned bytes\n", encoding="utf-8")
        else:
            outside = tmp_path / "outside.md"
            outside.write_text("outside\n", encoding="utf-8")
            (source.parent / "linked.md").symlink_to(outside)

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert status["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert status["legacy"]["classification"] == "AMBIGUOUS"
    assert migration.returncode == 2
    assert "LAYOUT_MIGRATION_BLOCKED: LEGACY_CLASSIFICATION_REQUIRED" in migration.stderr


@pytest.mark.parametrize("hazard", ["stable-lock", "logs-root"])
def test_layout_rejects_canonical_control_symlinks_before_outside_write(
    tmp_path: Path, hazard: str
) -> None:
    """Canonical lock and local runtime roots cannot redirect controller writes."""
    governance = tmp_path / ".work-governance"
    governance.mkdir()
    outside = tmp_path / "outside"
    if hazard == "stable-lock":
        outside.write_text("outside bytes\n", encoding="utf-8")
        (governance / "workctl.lock").symlink_to(outside)
    else:
        outside.mkdir()
        (governance / "logs").symlink_to(outside, target_is_directory=True)

    status = run_workctl(tmp_path, "layout", "status", check=False)
    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert status.returncode == 0
    assert json.loads(status.stdout)["layout_state"] == "ENVIRONMENT_BLOCKED"
    assert migration.returncode == 2
    if outside.is_file():
        assert outside.read_bytes() == b"outside bytes\n"
    else:
        assert list(outside.iterdir()) == []


def test_layout_rejects_nested_evidence_symlink_before_transaction_write(
    tmp_path: Path,
) -> None:
    """A nested evidence parent cannot redirect migration proof copies."""
    write_migratable_legacy(tmp_path)
    evidence = tmp_path / ".work-governance" / "evidence"
    evidence.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (evidence / "layout-migrations").symlink_to(outside, target_is_directory=True)

    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert migration.returncode == 2
    assert "uncommitted governance evidence is not transaction-bound" in migration.stderr
    assert list(outside.iterdir()) == []
    assert (tmp_path / "_Plan").is_dir()


@pytest.mark.parametrize(
    "hazard",
    [
        "lock-symlink",
        "rules-symlink",
        "unregistered-active-plan",
        "unfinished-indexed-plan",
    ],
)
def test_layout_classifier_rejects_unclosed_governance_inventory(
    tmp_path: Path, hazard: str
) -> None:
    """Every control path and Plan-like direct child needs deterministic ownership."""
    source = write_migratable_legacy(tmp_path)
    if hazard == "lock-symlink":
        outside = tmp_path / "outside.lock"
        outside.write_text("", encoding="utf-8")
        (source.parent / ".workctl.lock").symlink_to(outside)
    elif hazard == "rules-symlink":
        outside = tmp_path / "rules.md"
        outside.write_text("rules\n", encoding="utf-8")
        (tmp_path / "AGENTS.md").symlink_to(outside)
    elif hazard == "unregistered-active-plan":
        extra = source.parent / "PLAN-20260722-999.md"
        write_markdown_plan(extra, canonical_frontmatter("PLAN-20260722-999"))
    else:
        extra = source.parent / "PLAN-20260722-999.md"
        write_markdown_plan(extra, canonical_frontmatter("PLAN-20260722-999"))
        index_path = source.parent / "index.yaml"
        index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        index["plans"].append(
            {
                "id": "PLAN-20260722-999",
                "path": extra.name,
                "title": "Unfinished candidate",
                "created_at": "2026-07-22T00:00:00+00:00",
            }
        )
        index_path.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert status["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert status["legacy"]["classification"] == "AMBIGUOUS"


@pytest.mark.parametrize(
    "rules_bytes",
    [
        b"`_Plan/PLAN-20260723-001.md` is the authoritative current execution Plan.\n",
        (b"<!-- WORK_GOVERNANCE:BEGIN -->\n`_Plan/PLAN-20260723-001.md` is authoritative.\n"),
    ],
)
def test_layout_never_requires_or_rewrites_project_rule_markers(
    tmp_path: Path,
    rules_bytes: bytes,
) -> None:
    """User-authored project rules are preserved and are not migration credentials."""
    write_migratable_legacy(tmp_path)
    rules = tmp_path / "AGENTS.md"
    rules.write_bytes(rules_bytes)

    run_workctl(tmp_path, "layout", "migrate")

    assert rules.read_bytes() == rules_bytes


def test_layout_incomplete_legacy_journal_requires_recovery(tmp_path: Path) -> None:
    """An unfinished old structural transaction is never absorbed."""
    source = write_migratable_legacy(tmp_path)
    journal = source.parent / ".migrations" / "MIG-20260727-001.yaml"
    journal.parent.mkdir()
    journal.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "migration_id": "MIG-20260727-001",
                "status": "applying",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert status["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"
    assert status["legacy"]["classification"] == "RECOVERY_REQUIRED"
    assert migration.returncode == 2
    assert "LAYOUT_MIGRATION_BLOCKED: LAYOUT_RECOVERY_REQUIRED" in migration.stderr


def test_layout_old_and_new_authorities_require_reconciliation(tmp_path: Path) -> None:
    """Two pre-commit authority roots cannot be selected by precedence."""
    source = write_migratable_legacy(tmp_path)
    canonical = tmp_path / ".work-governance" / "_Plan"
    shutil.copytree(source.parent, canonical)

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert status["layout_state"] == "RECONCILIATION_REQUIRED"
    assert migration.returncode == 2
    assert "LAYOUT_MIGRATION_BLOCKED: RECONCILIATION_REQUIRED" in migration.stderr


def test_layout_rejects_stale_explicit_project_authority_route(tmp_path: Path) -> None:
    """A project rule naming another legacy Plan blocks automatic migration."""
    write_migratable_legacy(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        "`_Plan/PLAN-20260722-999.md` is the authoritative current execution Plan.\n",
        encoding="utf-8",
    )

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert status["layout_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert any(
        "routes legacy authority" in reason for reason in status["legacy"]["blocking_reasons"]
    )


def test_layout_converts_only_allowlisted_operational_content(tmp_path: Path) -> None:
    """Managed paths change while historical and business prose remain byte-identical."""
    source = write_migratable_legacy(tmp_path)
    frontmatter = canonical_frontmatter("PLAN-20260723-001")
    frontmatter["delivery"] = {
        "status": "pending",
        "boundary": "local",
        "evidence_ref": "evidence:.logs/PLAN-20260723-001/probe.json",
    }
    frontmatter["artifacts"] = [
        {
            "id": "A-001",
            "path": "_Plan/business-output.txt",
            "status": "pending",
            "state_evidence_ref": "evidence:.logs/PLAN-20260723-001/state.json",
        }
    ]
    write_markdown_plan(source, frontmatter, "Business prose: _Plan/keep-this.md\n")
    archive = source.parent / "archive" / "historical.md"
    archive.parent.mkdir()
    archive_bytes = b"Historical evidence: _Plan/keep-this.md and .logs/business.log\n"
    archive.write_bytes(archive_bytes)
    (tmp_path / "AGENTS.md").write_text(
        "Business note: `_Plan/do-not-rewrite.md`.\n"
        "<!-- WORK_GOVERNANCE:BEGIN -->\n"
        "`_Plan/PLAN-20260723-001.md` is the authoritative current execution Plan.\n"
        "<!-- WORK_GOVERNANCE:END -->\n",
        encoding="utf-8",
    )
    governed_log = tmp_path / ".logs" / "PLAN-20260723-001" / "probe.json"
    governed_log.parent.mkdir(parents=True)
    governed_log.write_text(
        '{"schema_version":1,"plan_id":"PLAN-20260723-001"}\n',
        encoding="utf-8",
    )
    state_log = tmp_path / ".logs" / "PLAN-20260723-001" / "state.json"
    state_log.write_text(
        '{"schema_version":1,"plan_id":"PLAN-20260723-001"}\n',
        encoding="utf-8",
    )
    agents_before = (tmp_path / "AGENTS.md").read_bytes()
    adopt_legacy(tmp_path)

    run_workctl(tmp_path, "layout", "migrate")
    migrated, body = read_plan(tmp_path)

    assert migrated["revision"] == 2
    assert migrated["delivery"]["evidence_ref"] == (
        "evidence:.work-governance/logs/PLAN-20260723-001/probe.json"
    )
    assert migrated["artifacts"][0]["path"] == "_Plan/business-output.txt"
    assert migrated["artifacts"][0]["state_evidence_ref"] == (
        "evidence:.work-governance/logs/PLAN-20260723-001/state.json"
    )
    assert (tmp_path / ".work-governance" / "logs" / "PLAN-20260723-001" / "state.json").is_file()
    assert body == "Business prose: _Plan/keep-this.md\n"
    assert (
        tmp_path / ".work-governance" / "_Plan" / "archive" / "historical.md"
    ).read_bytes() == archive_bytes
    assert (tmp_path / "AGENTS.md").read_bytes() == agents_before


def test_layout_rewrites_a_project_reference_to_the_migrated_plan_file(
    tmp_path: Path,
) -> None:
    """A machine reference cannot keep targeting the released root _Plan name."""
    source = write_migratable_legacy(tmp_path)
    frontmatter = canonical_frontmatter("PLAN-20260723-001")
    frontmatter["delivery"] = {
        "status": "pending",
        "boundary": "local",
        "evidence_ref": "project:_Plan/PLAN-20260723-001.md",
    }
    write_markdown_plan(source, frontmatter)
    adopt_legacy(tmp_path)

    run_workctl(tmp_path, "layout", "migrate")
    migrated, _ = read_plan(tmp_path)

    assert migrated["delivery"]["evidence_ref"] == (
        "project:.work-governance/_Plan/PLAN-20260723-001.md"
    )


def test_layout_moves_and_rewrites_lineage_and_journal_evidence_refs(
    tmp_path: Path,
) -> None:
    """Every converted evidence ref is backed by the exact log file moved."""
    active = write_migratable_legacy(tmp_path)
    legacy = active.parent
    predecessor = legacy / "PLAN-20260722-001.md"
    predecessor_frontmatter = canonical_frontmatter("PLAN-20260722-001")
    predecessor_frontmatter["status"] = "complete"
    predecessor_frontmatter["delivery"] = {
        "evidence_ref": "evidence:.logs/PLAN-20260722-001/predecessor.json"
    }
    write_markdown_plan(predecessor, predecessor_frontmatter)
    active_frontmatter = canonical_frontmatter("PLAN-20260723-001")
    active_frontmatter["authority"]["predecessor"] = {
        "path": "_Plan/PLAN-20260722-001.md",
        "plan_id": "PLAN-20260722-001",
        "revision": 1,
        "sha256": sha256_path(predecessor),
    }
    active_frontmatter["authority"]["rollover_id"] = "ROL-20260727-001"
    active_frontmatter["authority"]["confirmations"]["rollover"] = "C-PLAN-ROLLOVER"
    active_frontmatter["confirmations"]["required"] = [
        {
            "id": "C-PLAN-ROLLOVER",
            "description": "Approve successor lineage.",
            "status": "accepted",
            "ref": "user:test-rollover",
            "accepted_at": "2026-07-27T00:00:00+00:00",
            "evidence_sha256": "1" * 64,
        }
    ]
    write_markdown_plan(active, active_frontmatter)
    index_path = legacy / "index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    index["plans"].insert(
        0,
        {
            "id": "PLAN-20260722-001",
            "path": predecessor.name,
            "title": "Predecessor",
            "created_at": "2026-07-22T00:00:00+00:00",
        },
    )
    index_path.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")
    migration_journal = legacy / ".migrations" / "MIG-20260727-001.yaml"
    migration_journal.parent.mkdir()
    migration_journal.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "migration_id": "MIG-20260727-001",
                "status": "committed",
                "evidence_ref": "evidence:.logs/PLAN-20260723-001/rollover.json",
                "sources": [
                    {"staged_path": ("_Plan/.migrations/MIG-20260727-001/staging/source-plan.md")}
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    predecessor_log = tmp_path / ".logs" / "PLAN-20260722-001" / "predecessor.json"
    rollover_log = tmp_path / ".logs" / "PLAN-20260723-001" / "rollover.json"
    predecessor_log.parent.mkdir(parents=True)
    rollover_log.parent.mkdir(parents=True)
    predecessor_log.write_text("predecessor evidence\n", encoding="utf-8")
    rollover_log.write_text("rollover evidence\n", encoding="utf-8")
    adopt_legacy(tmp_path)

    run_workctl(tmp_path, "layout", "migrate")

    predecessor_text = (tmp_path / ".work-governance" / "_Plan" / predecessor.name).read_text(
        encoding="utf-8"
    )
    _, predecessor_yaml, _ = predecessor_text.split("---\n", 2)
    migrated_predecessor = yaml.safe_load(predecessor_yaml)
    migrated_journal = yaml.safe_load(
        (
            tmp_path / ".work-governance" / "_Plan" / ".migrations" / migration_journal.name
        ).read_text(encoding="utf-8")
    )
    assert migrated_predecessor["delivery"]["evidence_ref"] == (
        "evidence:.work-governance/logs/PLAN-20260722-001/predecessor.json"
    )
    assert migrated_journal["evidence_ref"] == (
        "evidence:.work-governance/logs/PLAN-20260723-001/rollover.json"
    )
    assert migrated_journal["sources"][0]["staged_path"] == (
        ".work-governance/_Plan/.migrations/MIG-20260727-001/staging/source-plan.md"
    )
    assert (
        tmp_path / ".work-governance" / "logs" / "PLAN-20260722-001" / "predecessor.json"
    ).is_file()
    assert (
        tmp_path / ".work-governance" / "logs" / "PLAN-20260723-001" / "rollover.json"
    ).is_file()


@pytest.mark.parametrize("reference_field", ["evidence_ref", "state_evidence_ref"])
def test_layout_rejects_a_converted_evidence_ref_without_source_log(
    tmp_path: Path,
    reference_field: str,
) -> None:
    """Missing evidence fails before a transaction and remains directly retryable."""
    active = write_migratable_legacy(tmp_path)
    frontmatter = canonical_frontmatter("PLAN-20260723-001")
    if reference_field == "evidence_ref":
        frontmatter["delivery"] = {"evidence_ref": "evidence:.logs/PLAN-20260723-001/missing.json"}
    else:
        frontmatter["artifacts"] = [
            {
                "id": "A-001",
                "path": "artifact.txt",
                "status": "pending",
                "state_evidence_ref": "evidence:.logs/PLAN-20260723-001/missing.json",
            }
        ]
    write_markdown_plan(active, frontmatter)
    adopt_legacy(tmp_path)

    migration = run_workctl(tmp_path, "layout", "migrate", check=False)
    after_failure = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert migration.returncode == 2
    assert "LAYOUT_EVIDENCE_REFERENCE_MISSING" in migration.stderr
    assert after_failure["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert not list((tmp_path / ".work-governance" / "runtime").glob("LAY-*"))
    assert active.is_file()
    assert not (tmp_path / ".work-governance" / "_Plan").exists()
    missing_log = tmp_path / ".logs" / "PLAN-20260723-001" / "missing.json"
    missing_log.parent.mkdir(parents=True)
    missing_log.write_text(
        '{"schema_version": 1, "plan_id": "PLAN-20260723-001"}\n',
        encoding="utf-8",
    )
    run_workctl(tmp_path, "layout", "migrate")
    assert (
        json.loads(run_workctl(tmp_path, "layout", "status").stdout)["layout_state"]
        == "LAYOUT_READY"
    )


def test_layout_recovery_abandons_a_preparing_interruption(tmp_path: Path) -> None:
    """A crash after the initial journal but before staging never strands recovery."""
    active = write_migratable_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    transaction = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*"))
    assert {child.name for child in transaction.iterdir()} == {"journal.json"}
    recovered = run_workctl(tmp_path, "layout", "recover")
    final = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert interrupted.returncode == 2
    assert "LAYOUT_TEST_INTERRUPTED: preparing" in interrupted.stderr
    assert status["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"
    assert recovered.stdout.startswith("LAYOUT_PREPARATION_PRESERVED LAY-")
    assert final["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert json.loads((transaction / "journal.json").read_text(encoding="utf-8"))["status"] == (
        "aborted"
    )
    assert transaction.is_dir()
    assert active.is_file()
    assert not (tmp_path / ".work-governance" / "_Plan").exists()
    run_workctl(tmp_path, "layout", "migrate")
    assert (
        json.loads(run_workctl(tmp_path, "layout", "status").stdout)["layout_state"]
        == "LAYOUT_READY"
    )


def test_layout_recovery_abandons_preparing_with_unstaged_proposal(
    tmp_path: Path,
) -> None:
    """A snapshot crash before proposal staging remains safely recoverable."""
    active = write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    proposal_before = file_tree_snapshot(proposal)
    adopt_legacy(tmp_path)

    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    recovered = run_workctl(tmp_path, "layout", "recover")
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert interrupted.returncode == 2
    assert recovered.stdout.startswith("LAYOUT_PREPARATION_PRESERVED LAY-")
    assert status["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert active.is_file()
    assert file_tree_snapshot(proposal) == proposal_before


def test_layout_recovery_abandons_partial_proposal_staging(tmp_path: Path) -> None:
    """A proposal copied into an otherwise incomplete staging tree is safely preserved."""
    active = write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    proposal_before = file_tree_snapshot(proposal)
    adopt_legacy(tmp_path)

    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "proposal-staging"},
    )
    governance = tmp_path / ".work-governance"
    transaction = next((governance / "runtime").glob("LAY-*"))
    staged_proposal = transaction / "staging" / "proposals" / proposal.name
    (staged_proposal / "AGENTS.proposed.md").unlink()

    recovered = run_workctl(tmp_path, "layout", "recover")
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert interrupted.returncode == 2
    assert "LAYOUT_TEST_INTERRUPTED: proposal-staging" in interrupted.stderr
    assert recovered.stdout.startswith("LAYOUT_PREPARATION_PRESERVED LAY-")
    assert status["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert active.is_file()
    assert file_tree_snapshot(proposal) == proposal_before
    assert not (staged_proposal / "AGENTS.proposed.md").exists()


def test_layout_recovery_abandons_partial_legacy_plan_copy(tmp_path: Path) -> None:
    """A crash while the legacy Plan copy still owns proposals remains safely recoverable."""
    active = write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    proposal_before = file_tree_snapshot(proposal)
    adopt_legacy(tmp_path)

    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "legacy-plan-staging"},
    )
    governance = tmp_path / ".work-governance"
    transaction = next((governance / "runtime").glob("LAY-*"))
    staged_proposal = transaction / "staging" / "_Plan" / "proposals" / proposal.name
    (staged_proposal / "AGENTS.proposed.md").unlink()

    recovered = run_workctl(tmp_path, "layout", "recover")
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert interrupted.returncode == 2
    assert "LAYOUT_TEST_INTERRUPTED: legacy-plan-staging" in interrupted.stderr
    assert recovered.stdout.startswith("LAYOUT_PREPARATION_PRESERVED LAY-")
    assert status["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert active.is_file()
    assert file_tree_snapshot(proposal) == proposal_before
    assert not (staged_proposal / "AGENTS.proposed.md").exists()


def test_layout_preparing_rejects_known_proposal_path_byte_drift(tmp_path: Path) -> None:
    """A source path allowlist cannot authorize changed proposal bytes during Plan copy."""
    write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    proposal_before = file_tree_snapshot(proposal)
    adopt_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "legacy-plan-staging"},
    )
    assert interrupted.returncode == 2
    governance = tmp_path / ".work-governance"
    transaction = next((governance / "runtime").glob("LAY-*"))
    staged_replacement = (
        transaction / "staging" / "_Plan" / "proposals" / proposal.name / "AGENTS.proposed.md"
    )
    staged_replacement.write_text("DRIFTED KNOWN PATH\n", encoding="utf-8")

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "LAYOUT_PREPARATION_INVENTORY_INVALID" in recovery.stderr
    assert staged_replacement.read_text(encoding="utf-8") == "DRIFTED KNOWN PATH\n"
    assert file_tree_snapshot(proposal) == proposal_before


def test_layout_preparing_rejects_rehashed_proposal_submanifest(tmp_path: Path) -> None:
    """A self-consistent proposal sub-manifest cannot authorize bytes absent from the source."""
    write_migratable_legacy(tmp_path, adopt=False)
    proposal = write_legacy_reconciliation_proposal(tmp_path)
    proposal_before = file_tree_snapshot(proposal)
    adopt_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    assert interrupted.returncode == 2
    governance = tmp_path / ".work-governance"
    transaction = next((governance / "runtime").glob("LAY-*"))
    unknown = transaction / "staging" / "proposals" / "MIG-20990101-999"
    unknown.mkdir(parents=True)
    payload = b"UNBOUND\n"
    unknown_file = unknown / "unknown.bin"
    unknown_file.write_bytes(payload)
    proposal_manifest = [
        {"path": unknown.name, "kind": "directory"},
        {
            "path": f"{unknown.name}/{unknown_file.name}",
            "kind": "file",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    ]
    journal_path = transaction / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["legacy_proposals_manifest"] = proposal_manifest
    journal["legacy_proposals_sha256"] = hashlib.sha256(
        json.dumps(proposal_manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "INVALID_PREPARING_LAYOUT_JOURNAL" in recovery.stderr
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "preparing"
    assert unknown_file.read_bytes() == payload
    assert file_tree_snapshot(proposal) == proposal_before


def test_layout_recovery_resumes_after_preparing_receipt_interrupt(
    tmp_path: Path,
) -> None:
    """A crash between receipt persistence and aborted journal update is idempotent."""
    write_migratable_legacy(tmp_path)
    run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "recover",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing-receipt"},
    )
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    recovered = run_workctl(tmp_path, "layout", "recover")
    transaction = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*"))

    assert interrupted.returncode == 2
    assert "LAYOUT_TEST_INTERRUPTED: preparing-receipt" in interrupted.stderr
    assert status["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"
    assert recovered.stdout.startswith("LAYOUT_PREPARATION_PRESERVED LAY-")
    assert (transaction / "preparing-journal.json").is_file()
    assert json.loads((transaction / "journal.json").read_text(encoding="utf-8"))["status"] == (
        "aborted"
    )


@pytest.mark.parametrize("temp_kind", ["preparing-receipt", "journal"])
def test_layout_recovery_preserves_atomic_writer_orphan_temp(
    tmp_path: Path, temp_kind: str
) -> None:
    """A hard-crash atomic-writer temp is retained but does not strand recovery."""
    write_migratable_legacy(tmp_path)
    run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    transaction = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*"))
    if temp_kind == "journal":
        interrupted = run_workctl(
            tmp_path,
            "layout",
            "recover",
            check=False,
            env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing-receipt"},
        )
        assert interrupted.returncode == 2
        orphan = transaction / ".journal.json.crash"
    else:
        orphan = transaction / ".preparing-journal.json.crash"
    orphan.write_bytes(b"ORPHAN-ATOMIC-TEMP")

    recovered = run_workctl(tmp_path, "layout", "recover")
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert recovered.stdout.startswith("LAYOUT_PREPARATION_PRESERVED LAY-")
    assert orphan.read_bytes() == b"ORPHAN-ATOMIC-TEMP"
    assert json.loads((transaction / "journal.json").read_text(encoding="utf-8"))["status"] == (
        "aborted"
    )
    assert status["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"


def test_layout_recovery_rejects_symlinked_atomic_writer_temp(tmp_path: Path) -> None:
    """An atomic-writer-looking symlink is foreign inventory and blocks recovery."""
    write_migratable_legacy(tmp_path)
    run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    transaction = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*"))
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"OUTSIDE")
    orphan = transaction / ".journal.json.crash"
    orphan.symlink_to(outside)

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "LAYOUT_PREPARATION_INVENTORY_INVALID" in recovery.stderr
    assert orphan.is_symlink()
    assert outside.read_bytes() == b"OUTSIDE"


@pytest.mark.parametrize(
    ("drift_kind", "expected_error"),
    [
        ("source", "LEGACY_LAYOUT_INPUT_DRIFT"),
        ("unknown-transaction", "LAYOUT_PREPARATION_INVENTORY_INVALID"),
        ("unknown-backup", "LAYOUT_PREPARATION_INVENTORY_INVALID"),
        ("unknown-evidence", "LAYOUT_PREPARATION_INVENTORY_INVALID"),
        ("unknown-staged-plan", "LAYOUT_PREPARATION_INVENTORY_INVALID"),
        ("unknown-staged-logs", "LAYOUT_PREPARATION_INVENTORY_INVALID"),
        ("unknown-original-plan", "LAYOUT_PREPARATION_INVENTORY_INVALID"),
        ("symlink", "LAYOUT_PATH_SYMLINK"),
        ("activated", "LAYOUT_PREPARATION_ABANDON_UNSAFE"),
        ("journal", "INVALID_PREPARING_LAYOUT_JOURNAL"),
        ("git-baseline", "LAYOUT_GIT_BASELINE_DRIFT"),
    ],
)
def test_layout_preparing_recovery_rejects_drift(
    tmp_path: Path, drift_kind: str, expected_error: str
) -> None:
    """Preparing cleanup preserves evidence whenever source or transaction state drifts."""
    active = write_migratable_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    assert interrupted.returncode == 2
    governance = tmp_path / ".work-governance"
    transaction = next((governance / "runtime").glob("LAY-*"))
    sentinel = transaction / "sentinel.txt"
    if drift_kind == "source":
        active.write_text(active.read_text(encoding="utf-8") + "\nsource drift\n", encoding="utf-8")
    elif drift_kind == "unknown-transaction":
        sentinel.write_text("preserve me\n", encoding="utf-8")
    elif drift_kind == "unknown-backup":
        sentinel = transaction / "backup" / "sentinel.txt"
        sentinel.parent.mkdir()
        sentinel.write_text("preserve me\n", encoding="utf-8")
    elif drift_kind == "unknown-evidence":
        sentinel = governance / "evidence" / "layout-migrations" / transaction.name / "sentinel.txt"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("preserve me\n", encoding="utf-8")
    elif drift_kind == "unknown-staged-plan":
        sentinel = transaction / "staging" / "_Plan" / "unregistered.bin"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("preserve me\n", encoding="utf-8")
    elif drift_kind == "unknown-staged-logs":
        sentinel = transaction / "staging" / "logs" / "unregistered.bin"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("preserve me\n", encoding="utf-8")
    elif drift_kind == "unknown-original-plan":
        sentinel = (
            governance
            / "evidence"
            / "layout-migrations"
            / transaction.name
            / "legacy-_Plan"
            / "unregistered.bin"
        )
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("preserve me\n", encoding="utf-8")
    elif drift_kind == "symlink":
        staging = transaction / "staging"
        staged_plan = staging / "_Plan"
        staged_plan.mkdir(parents=True)
        outside = tmp_path / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        (staged_plan / "outside-link").symlink_to(outside)
    elif drift_kind == "activated":
        (governance / "_Plan").mkdir()
    else:
        journal_path = transaction / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if drift_kind == "journal":
            journal["unknown"] = True
        else:
            journal["git_baseline"] = {"repository": True, "head": "drift"}
        journal_path.write_text(json.dumps(journal), encoding="utf-8")

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert expected_error in recovery.stderr
    assert transaction.is_dir()
    if drift_kind.startswith("unknown"):
        assert sentinel.read_text(encoding="utf-8") == "preserve me\n"


@pytest.mark.parametrize(
    "replacement_kind",
    ["staged-plan-file", "original-plan-file", "registered-directory"],
)
def test_layout_preparing_recovery_preserves_registered_path_foreign_bytes(
    tmp_path: Path, replacement_kind: str
) -> None:
    """Known path names cannot authorize deletion of unbound bytes or changed types."""
    active = write_migratable_legacy(tmp_path)
    if replacement_kind == "registered-directory":
        archive = active.parent / "archive"
        archive.mkdir()
        (archive / "source.txt").write_text("source\n", encoding="utf-8")
    adopt_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    assert interrupted.returncode == 2
    governance = tmp_path / ".work-governance"
    transaction = next((governance / "runtime").glob("LAY-*"))
    if replacement_kind == "staged-plan-file":
        sentinel = transaction / "staging" / "_Plan" / active.name
    elif replacement_kind == "original-plan-file":
        sentinel = (
            governance
            / "evidence"
            / "layout-migrations"
            / transaction.name
            / "legacy-_Plan"
            / active.name
        )
    else:
        sentinel = transaction / "staging" / "_Plan" / "archive"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"UNBOUND-FOREIGN-BYTES")

    recovered = run_workctl(
        tmp_path,
        "layout",
        "recover",
        check=replacement_kind != "original-plan-file",
    )

    assert sentinel.read_bytes() == b"UNBOUND-FOREIGN-BYTES"
    assert transaction.is_dir()
    journal_status = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))[
        "status"
    ]
    if replacement_kind == "original-plan-file":
        # The durable original-evidence copy is hash-bound to the legacy source.
        # Foreign bytes there invalidate the preparation inventory and must not
        # be normalized into an aborted transaction.
        assert recovered.returncode == 2
        assert "LAYOUT_PREPARATION_INVENTORY_INVALID" in recovered.stderr
        assert journal_status == "preparing"
    else:
        assert recovered.stdout.startswith("LAYOUT_PREPARATION_PRESERVED LAY-")
        assert journal_status == "aborted"
    assert not (governance / "_Plan").exists()


@pytest.mark.parametrize(
    "forgery",
    ["minimal", "id-mismatch", "marker-only", "invalid-planned"],
)
def test_layout_aborted_journal_must_authenticate(tmp_path: Path, forgery: str) -> None:
    """Forged aborted markers remain recovery-required instead of being ignored."""
    write_migratable_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "preparing"},
    )
    assert interrupted.returncode == 2
    transaction = next((tmp_path / ".work-governance" / "runtime").glob("LAY-*"))
    journal_path = transaction / "journal.json"
    if forgery == "invalid-planned":
        run_workctl(tmp_path, "layout", "recover")
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if forgery == "minimal":
        journal = {
            "schema_version": 1,
            "kind": "layout-migration",
            "transaction_id": transaction.name,
            "status": "aborted",
        }
    elif forgery == "id-mismatch":
        journal["transaction_id"] = "LAY-20260727T120000Z-deadbeef-abcdef12"
        journal["status"] = "aborted"
        journal["completed_operations"] = ["snapshot", "preparation-preserved"]
    elif forgery == "marker-only":
        journal["status"] = "aborted"
        journal["completed_operations"] = ["snapshot", "preparation-preserved"]
    else:
        journal["planned_log_files"] = [42]
        journal["planned_project_files"] = [{"unbound": "bytes"}]
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert status["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"
    assert transaction.is_dir()


def test_layout_transaction_nonce_is_unique_at_a_fixed_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retained transactions cannot collide when time and process identity repeat."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_nonce_test")
    real_datetime = cast(Any, namespace["datetime"])
    fixed = real_datetime(2026, 7, 27, 12, 0, 0, tzinfo=namespace["UTC"])

    class FixedDatetime:
        @classmethod
        def now(cls, _timezone: object) -> Any:
            return fixed

    nonces = iter(["1" * 32, "2" * 32])
    sizes: list[int] = []

    def fake_token_hex(size: int) -> str:
        sizes.append(size)
        return next(nonces)

    monkeypatch.setattr(namespace["secrets"], "token_hex", fake_token_hex)
    new_id = cast(Callable[[str], str], namespace["new_layout_transaction_id"])
    new_id.__globals__["datetime"] = FixedDatetime

    first = new_id("a" * 64)
    second = new_id("a" * 64)

    assert first == f"LAY-20260727T120000Z-aaaaaaaa-{'1' * 32}"
    assert second == f"LAY-20260727T120000Z-aaaaaaaa-{'2' * 32}"
    assert first != second
    assert sizes == [16, 16]


def test_layout_rejects_unsupported_lineage_path(tmp_path: Path) -> None:
    """Only direct legacy, canonical, or filename predecessor paths are accepted."""
    source = write_migratable_legacy(tmp_path)
    predecessor = source.parent / "PLAN-20260722-001.md"
    predecessor_frontmatter = canonical_frontmatter("PLAN-20260722-001")
    predecessor_frontmatter["status"] = "complete"
    write_markdown_plan(predecessor, predecessor_frontmatter)
    frontmatter = canonical_frontmatter("PLAN-20260723-001")
    frontmatter["authority"]["predecessor"] = {
        "path": "archive/PLAN-20260722-001.md",
        "plan_id": "PLAN-20260722-001",
        "revision": 1,
        "sha256": sha256_path(predecessor),
    }
    frontmatter["authority"]["rollover_id"] = "ROL-20260723-001"
    frontmatter["authority"]["confirmations"]["rollover"] = "C-PLAN-ROLLOVER"
    write_markdown_plan(source, frontmatter)
    adopt_legacy(tmp_path)

    migration = run_workctl(tmp_path, "layout", "migrate", check=False)

    assert migration.returncode == 2
    assert "LAYOUT_LINEAGE_PATH_UNSUPPORTED" in migration.stderr


def test_layout_holds_stable_lock_while_waiting_for_legacy_lock(
    tmp_path: Path,
) -> None:
    """A new controller cannot pass another migration waiting on the old lock."""
    source = write_migratable_legacy(tmp_path)
    legacy_lock = source.parent / ".workctl.lock"
    holder_ready = tmp_path / "legacy-holder-ready"
    release_holder = tmp_path / "release-legacy-holder"
    first_stable_attempt = tmp_path / "first-stable-attempt"
    first_legacy_attempt = tmp_path / "first-legacy-attempt"
    second_stable_attempt = tmp_path / "second-stable-attempt"
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
    deadline = time.monotonic() + 8
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
            str(legacy_lock),
            str(holder_ready),
            str(release_holder),
        ],
        cwd=tmp_path,
    )
    first: subprocess.Popen[str] | None = None
    second: subprocess.Popen[str] | None = None
    try:
        deadline = time.monotonic() + 3
        while not holder_ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert holder_ready.exists()
        receipt = ensure_test_ready_receipt(
            tmp_path,
            allow_legacy_contract=True,
            bootstrapping=True,
        )
        assert receipt is not None
        migration_command = [
            sys.executable,
            str(receipt[0]),
            "--receipt-sha256",
            receipt[1],
            "layout",
            "migrate",
        ]
        first = subprocess.Popen(
            migration_command,
            cwd=tmp_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "WORKCTL_TEST_LOCK_ATTEMPT_FILE": str(first_stable_attempt),
                "WORKCTL_TEST_LEGACY_LOCK_ATTEMPT_FILE": str(first_legacy_attempt),
            },
        )
        deadline = time.monotonic() + 3
        while not first_legacy_attempt.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert first_stable_attempt.exists()
        assert first_legacy_attempt.exists()
        assert first.poll() is None
        second = subprocess.Popen(
            migration_command,
            cwd=tmp_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "WORKCTL_TEST_LOCK_ATTEMPT_FILE": str(second_stable_attempt),
            },
        )
        deadline = time.monotonic() + 3
        while not second_stable_attempt.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert second_stable_attempt.exists()
        assert second.poll() is None
        release_holder.write_text("release\n", encoding="utf-8")
        assert holder.wait(timeout=3) == 0
        first_stdout, first_stderr = first.communicate(timeout=5)
        second_stdout, second_stderr = second.communicate(timeout=5)
        assert first.returncode == 0, (first_stdout, first_stderr)
        assert second.returncode == 0, (second_stdout, second_stderr)
        assert first_stdout.startswith("LAYOUT_COMMITTED LAY-")
        assert second_stdout.strip() == "LAYOUT_ALREADY_READY"
    finally:
        release_holder.touch(exist_ok=True)
        for process in (first, second, holder):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=3)


def test_layout_recovery_rejects_git_baseline_drift(tmp_path: Path) -> None:
    """Recovery cannot activate after tracked project state changes."""
    write_migratable_legacy(tmp_path)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Work Governance Test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    adopt_legacy(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "staged"},
    )
    assert interrupted.returncode == 2
    tracked.write_text("drift\n", encoding="utf-8")

    recovery = run_workctl(tmp_path, "layout", "recover", check=False)

    assert recovery.returncode == 2
    assert "LAYOUT_GIT_BASELINE_DRIFT" in recovery.stderr
    assert (tmp_path / "_Plan").is_dir()
    assert not (tmp_path / ".work-governance" / "_Plan").exists()


def test_layout_manifests_and_completion_proof_are_reproducible(
    tmp_path: Path,
) -> None:
    """Source evidence, final Plan baseline, and version proof all rehash."""
    source = write_migratable_legacy(tmp_path)
    source_bytes = source.read_bytes()

    run_workctl(tmp_path, "layout", "migrate")

    journals = list((tmp_path / ".work-governance" / "runtime").glob("LAY-*/journal.json"))
    assert len(journals) == 1
    journal = json.loads(journals[0].read_text(encoding="utf-8"))
    namespace = runpy.run_path(str(SCRIPT))
    tree_manifest = cast(Callable[..., list[dict[str, object]]], namespace["tree_manifest"])
    manifest_digest = cast(Callable[[list[dict[str, object]]], str], namespace["manifest_sha256"])
    original = Path(journal["paths"]["original_evidence"])
    canonical = tmp_path / ".work-governance" / "_Plan"
    assert (
        manifest_digest(tree_manifest(original, exclude_names={".workctl.lock"}))
        == journal["legacy_manifest_sha256"]
    )
    assert (
        manifest_digest(tree_manifest(canonical, exclude_names={".workctl.lock"}))
        == journal["new_layout_baseline_sha256"]
    )
    assert (original / source.name).read_bytes() == source_bytes
    version = yaml.safe_load(
        (tmp_path / ".work-governance" / "version.yaml").read_text(encoding="utf-8")
    )
    evidence = version["migration"]["completion_evidence"]
    proof = tmp_path / evidence["path"]
    proof_payload = yaml.safe_load(proof.read_text(encoding="utf-8"))
    assert evidence["kind"] == "migration-proof"
    assert sha256_path(proof) == evidence["sha256"]
    assert proof_payload["legacy_adoption_sha256"] == journal["legacy_adoption_sha256"]
    assert "project_files" not in journal
    assert "planned_project_files" not in journal
    assert all(
        conversion["kind"] not in {"managed-project-marker", "generated-pointer"}
        for conversion in journal["conversion_table"]
    )
    assert version["migration"]["legacy_manifest_sha256"] == (journal["legacy_manifest_sha256"])
    assert (
        version["migration"]["new_layout_baseline_sha256"]
        == (journal["new_layout_baseline_sha256"])
    )


def test_normal_plan_revision_does_not_reopen_layout_migration(
    tmp_path: Path,
) -> None:
    """The migration baseline proves layout activation, not future Plan bytes."""
    write_migratable_legacy(tmp_path)
    run_workctl(tmp_path, "layout", "migrate")
    version_before = (tmp_path / ".work-governance" / "version.yaml").read_bytes()

    revised = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "2",
    )

    assert "TASK_UPDATED T-001 in_progress revision=3" in revised.stdout
    assert (tmp_path / ".work-governance" / "version.yaml").read_bytes() == version_before
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"


def test_old_committed_layout_corrects_exact_scope_root_with_version_last(
    tmp_path: Path,
) -> None:
    """An observed action-3 residual is corrected once without absorbing child paths."""
    write_migratable_legacy(tmp_path)
    run_workctl(tmp_path, "layout", "migrate")
    original_proof = next(
        (tmp_path / ".work-governance" / "_Plan" / ".migrations").glob("LAY-*.yaml")
    )
    original_proof_bytes = original_proof.read_bytes()
    frontmatter, body = read_plan(tmp_path)
    frontmatter["scope"]["include"].extend(["_Plan/", "_Plan/business-output"])
    write_plan(tmp_path, frontmatter, body)
    revision_before = frontmatter["revision"]
    plan_before_bytes = plan_path(tmp_path).read_bytes()
    set_layout_action_revision(tmp_path, 3)

    required = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    migrated = run_workctl(tmp_path, "layout", "migrate")
    final = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    corrected, _body = read_plan(tmp_path)
    version = yaml.safe_load(
        (tmp_path / ".work-governance" / "version.yaml").read_text(encoding="utf-8")
    )
    proofs = sorted((tmp_path / ".work-governance" / "_Plan" / ".migrations").glob("LAY-*.yaml"))
    correction_proof = next(path for path in proofs if path != original_proof)
    proof_payload = yaml.safe_load(correction_proof.read_text(encoding="utf-8"))
    transaction = next(
        path
        for path in (tmp_path / ".work-governance" / "runtime").glob("LAY-*")
        if path.name == correction_proof.stem
    )
    journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
    evidence_plan = (
        tmp_path
        / ".work-governance"
        / "evidence"
        / "layout-action-upgrades"
        / transaction.name
        / "active-plan.before.md"
    )

    assert required["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
    assert required["plan_authority_state"] == "NOT_INSPECTED"
    assert migrated.stdout.startswith("LAYOUT_ACTION_UPGRADED LAY-")
    assert final["layout_state"] == "LAYOUT_READY"
    assert corrected["revision"] == revision_before + 1
    assert ".work-governance/_Plan/" in corrected["scope"]["include"]
    assert "_Plan/business-output" in corrected["scope"]["include"]
    assert "_Plan/" not in corrected["scope"]["include"]
    assert version["legacy_migration_action_revision"] == 4
    assert original_proof.read_bytes() == original_proof_bytes
    assert len(proofs) == 2
    assert proof_payload["kind"] == "layout-action-upgrade-proof"
    assert proof_payload["from_action_revision"] == 3
    assert proof_payload["to_action_revision"] == 4
    assert evidence_plan.read_bytes() == plan_before_bytes
    assert journal["status"] == "committed"
    assert journal["conversion_table"] == [
        {
            "path": ".work-governance/_Plan/PLAN-20260723-001.md",
            "kind": "active-plan-scope-root",
            "before_sha256": hashlib.sha256(plan_before_bytes).hexdigest(),
            "after_sha256": sha256_path(plan_path(tmp_path)),
        }
    ]
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"
    assert run_workctl(tmp_path, "layout", "migrate").stdout.strip() == "LAYOUT_ALREADY_READY"
    assert read_plan(tmp_path)[0]["revision"] == revision_before + 1


def test_old_no_plan_layout_upgrades_without_creating_authority(tmp_path: Path) -> None:
    """A No-Plan layout changes only its action contract and local transaction evidence."""
    run_workctl(tmp_path, "layout", "migrate")
    set_layout_action_revision(tmp_path, 3)

    migrated = run_workctl(tmp_path, "layout", "migrate")
    version = yaml.safe_load(
        (tmp_path / ".work-governance" / "version.yaml").read_text(encoding="utf-8")
    )

    assert migrated.stdout.startswith("LAYOUT_ACTION_UPGRADED LAY-")
    assert version["legacy_migration_action_revision"] == 4
    assert not (tmp_path / ".work-governance" / "_Plan").exists()
    assert run_workctl(tmp_path, "layout", "validate").stdout.strip() == "LAYOUT_VALID"


@pytest.mark.parametrize(
    "phase",
    [
        "action-upgrade-preparing",
        "action-upgrade-staged",
        "action-upgrade-plan",
        "action-upgrade-proof",
        "action-upgrade-version",
    ],
)
def test_action_upgrade_recovers_each_durable_boundary(
    tmp_path: Path,
    phase: str,
) -> None:
    """Preparation is safely abandoned; every activation boundary forwards once."""
    write_migratable_legacy(tmp_path)
    run_workctl(tmp_path, "layout", "migrate")
    frontmatter, body = read_plan(tmp_path)
    frontmatter["scope"]["include"].append("_Plan/")
    write_plan(tmp_path, frontmatter, body)
    revision_before = frontmatter["revision"]
    set_layout_action_revision(tmp_path, 3)

    interrupted = run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": phase},
    )
    recovery_required = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    recovered = run_workctl(tmp_path, "layout", "recover")
    if phase == "action-upgrade-preparing":
        pending = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
        assert pending["layout_state"] == "LAYOUT_MIGRATION_REQUIRED"
        run_workctl(tmp_path, "layout", "migrate")

    final = json.loads(run_workctl(tmp_path, "layout", "status").stdout)
    corrected, _body = read_plan(tmp_path)

    assert interrupted.returncode == 2
    assert f"LAYOUT_TEST_INTERRUPTED: {phase}" in interrupted.stderr
    assert recovery_required["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"
    if phase == "action-upgrade-preparing":
        assert recovered.stdout.startswith("LAYOUT_ACTION_UPGRADE_PREPARATION_PRESERVED")
    else:
        assert recovered.stdout.startswith("LAYOUT_ACTION_UPGRADED")
    assert final["layout_state"] == "LAYOUT_READY"
    assert corrected["revision"] == revision_before + 1
    assert "_Plan/" not in corrected["scope"]["include"]


def test_action_upgrade_recovery_rejects_active_plan_drift(tmp_path: Path) -> None:
    """A staged correction cannot overwrite a changed active Plan."""
    write_migratable_legacy(tmp_path)
    run_workctl(tmp_path, "layout", "migrate")
    frontmatter, body = read_plan(tmp_path)
    frontmatter["scope"]["include"].append("_Plan/")
    write_plan(tmp_path, frontmatter, body)
    set_layout_action_revision(tmp_path, 3)
    run_workctl(
        tmp_path,
        "layout",
        "migrate",
        check=False,
        env={"WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER": "action-upgrade-staged"},
    )
    plan_path(tmp_path).write_bytes(plan_path(tmp_path).read_bytes() + b"\nexternal drift\n")

    recovered = run_workctl(tmp_path, "layout", "recover", check=False)
    status = json.loads(run_workctl(tmp_path, "layout", "status").stdout)

    assert recovered.returncode == 2
    assert "ACTION_UPGRADE_ACTIVE_PLAN_DRIFT" in recovered.stderr
    assert status["layout_state"] == "LAYOUT_RECOVERY_REQUIRED"


def test_layout_converts_lineage_pointer_and_operational_journal_once(
    tmp_path: Path,
) -> None:
    """Recursive hashes and allowlisted operational paths converge in staging."""
    active = write_migratable_legacy(tmp_path)
    legacy = active.parent
    predecessor = legacy / "PLAN-20260722-001.md"
    predecessor_frontmatter = canonical_frontmatter("PLAN-20260722-001")
    predecessor_frontmatter["status"] = "complete"
    write_markdown_plan(predecessor, predecessor_frontmatter)
    active_frontmatter = canonical_frontmatter("PLAN-20260723-001")
    active_frontmatter["authority"]["predecessor"] = {
        "path": "_Plan/PLAN-20260722-001.md",
        "plan_id": "PLAN-20260722-001",
        "revision": 1,
        "sha256": sha256_path(predecessor),
    }
    active_frontmatter["authority"]["rollover_id"] = "ROL-20260727-001"
    active_frontmatter["authority"]["confirmations"]["rollover"] = "C-PLAN-ROLLOVER"
    active_frontmatter["confirmations"]["required"] = [
        {
            "id": "C-PLAN-ROLLOVER",
            "description": "Approve the successor.",
            "status": "accepted",
            "ref": "user:test-rollover",
            "accepted_at": "2026-07-27T00:00:00+00:00",
            "evidence_sha256": "1" * 64,
        }
    ]
    write_markdown_plan(active, active_frontmatter)
    index_path = legacy / "index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    index["plans"].insert(
        0,
        {
            "id": "PLAN-20260722-001",
            "path": predecessor.name,
            "title": "Predecessor",
            "created_at": "2026-07-22T00:00:00+00:00",
        },
    )
    index_path.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")
    pointer = legacy / "PLAN-20260724-999.md"
    pointer.write_text(
        "# Historical pointer\n\n"
        "- Marker: `WORK_GOVERNANCE_NON_AUTHORITY_POINTER`\n"
        "- Canonical Plan: [PLAN-20260723-001](PLAN-20260723-001.md)\n"
        "- Recorded path: `_Plan/PLAN-20260723-001.md`\n",
        encoding="utf-8",
    )
    rollover = legacy / ".rollovers" / "ROL-20260727-001.yaml"
    rollover.parent.mkdir()
    rollover.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "rollover_id": "ROL-20260727-001",
                "status": "committed",
                "source_plan": {
                    "path": "_Plan/PLAN-20260722-001.md",
                    "plan_id": "PLAN-20260722-001",
                },
                "description": "Historical prose keeps _Plan/business.md",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    pointer_before = pointer.read_bytes()
    adopt_legacy(tmp_path)

    run_workctl(tmp_path, "layout", "migrate")

    migrated_active, _ = read_plan(tmp_path)
    migrated_predecessor = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260722-001.md"
    _, predecessor_raw, _ = migrated_predecessor.read_text(encoding="utf-8").split("---\n", 2)
    predecessor_after = yaml.safe_load(predecessor_raw)
    migrated_pointer = (tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-999.md").read_text(
        encoding="utf-8"
    )
    migrated_rollover = yaml.safe_load(
        (tmp_path / ".work-governance" / "_Plan" / ".rollovers" / rollover.name).read_text(
            encoding="utf-8"
        )
    )
    assert migrated_active["revision"] == 2
    assert predecessor_after["revision"] == 1
    assert migrated_active["authority"]["predecessor"] == {
        "path": ".work-governance/_Plan/PLAN-20260722-001.md",
        "plan_id": "PLAN-20260722-001",
        "revision": 1,
        "sha256": sha256_path(migrated_predecessor),
    }
    assert migrated_pointer.encode() == pointer_before
    assert migrated_rollover["source_plan"]["path"] == ".work-governance/_Plan/PLAN-20260722-001.md"
    assert migrated_rollover["description"] == "Historical prose keeps _Plan/business.md"


def test_layout_preserves_registered_legacy_worktree_path(tmp_path: Path) -> None:
    """Layout migration never moves an already registered old worktree."""
    write_migratable_legacy(tmp_path)
    (tmp_path / ".gitignore").write_text("/.worktree/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Work Governance Test"],
        cwd=tmp_path,
        check=True,
    )
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    legacy_worktree = tmp_path / ".worktree" / "legacy"
    subprocess.run(
        [
            "git",
            "worktree",
            "add",
            "-q",
            "-b",
            "legacy-worktree",
            str(legacy_worktree),
            "HEAD",
        ],
        cwd=tmp_path,
        check=True,
    )
    marker = legacy_worktree / "tracked.txt"
    marker_bytes = marker.read_bytes()
    adopt_legacy(tmp_path)

    run_workctl(tmp_path, "layout", "migrate")

    registered = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert str(legacy_worktree) in registered
    assert marker.read_bytes() == marker_bytes
    assert (
        subprocess.run(
            ["git", "status", "--short"],
            cwd=legacy_worktree,
            text=True,
            capture_output=True,
            check=True,
        ).returncode
        == 0
    )
    namespace = runpy.run_path(str(SCRIPT))
    worktrees_dir = cast(Callable[[Path], Path], namespace["worktrees_dir"])
    assert worktrees_dir(tmp_path) == (tmp_path / ".work-governance" / "worktrees")


def test_plan_init_status_and_active_conflict(tmp_path: Path) -> None:
    init_plan(tmp_path)

    status = run_workctl(tmp_path, "plan", "status")
    payload = json.loads(status.stdout)
    assert payload["plan_id"] == "PLAN-20260723-001"
    assert payload["current_task"] is None
    assert payload["ready"] == []
    assert "revision_history" not in payload

    full_status = run_workctl(tmp_path, "plan", "status", "--full")
    full_payload = json.loads(full_status.stdout)
    assert full_payload["revision"] == 1

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
    assert "PLAN_ADMISSION_REQUIRED" in duplicate.stderr


def test_plan_status_default_is_bounded_and_history_is_opt_in(tmp_path: Path) -> None:
    """Routine status stays compact while the full report remains available."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["goal"] = {
        "statement": "A compact status goal.",
        "success_conditions": ["Do not echo revision history by default."],
    }
    frontmatter["tasks"] = [
        {"id": "T-001", "description": "Ready task", "status": "pending"},
        {
            "id": "T-002",
            "description": "Blocked task",
            "status": "blocked",
            "depends_on": ["T-001"],
        },
    ]
    write_plan(tmp_path, frontmatter, body)

    compact = run_workctl(tmp_path, "plan", "status")
    assert len(compact.stdout.encode()) < 8 * 1024
    payload = json.loads(compact.stdout)
    assert set(payload) == {
        "plan_id",
        "goal",
        "current_task",
        "ready",
        "blocked",
        "blocked_details",
        "parallel_ready",
        "confirmation_gates",
        "next_suggestion",
    }
    assert payload["ready"] == ["task:T-001"]
    assert payload["parallel_ready"] == ["task:T-001"]
    assert payload["blocked"] == ["task:T-002"]
    assert payload["blocked_details"][0]["task"] == "task:T-002"
    assert payload["next_suggestion"] == "Start task:T-001"

    full = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)
    assert "revision_history" in full


def test_stable_help_and_scheduler_commands_keep_plan_revision_unchanged(
    tmp_path: Path,
) -> None:
    """The public workflow aliases use runtime scheduling without Plan revision churn."""
    help_result = run_workctl(tmp_path, "help", "plan")
    help_payload = json.loads(help_result.stdout)
    assert "plan ready" in help_payload["commands"]
    assert "plan show [--full]" in help_payload["commands"]

    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [
        {"id": "T-001", "description": "First", "status": "pending"},
        {"id": "T-002", "description": "Second", "status": "pending"},
    ]
    write_plan(tmp_path, frontmatter, body)
    reprioritized = run_workctl(
        tmp_path,
        "task",
        "reprioritize",
        "--task-id",
        "T-002",
        "--priority",
        "5",
        "--expected-state-sequence",
        "0",
    )
    assert "TASK_REPRIORITIZED T-002 priority=5 state_sequence=1" in reprioritized.stdout
    assert read_plan(tmp_path)[0]["revision"] == 1
    assert json.loads(run_workctl(tmp_path, "plan", "ready").stdout) == [
        "task:T-002",
        "task:T-001",
    ]
    assert json.loads(run_workctl(tmp_path, "plan", "next").stdout) == {
        "blocked_details": [],
        "current_task": "task:T-002",
        "next_suggestion": "Start task:T-002",
        "parallel_ready": ["task:T-002", "task:T-001"],
    }


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


def test_evidence_record_accepts_stdin_without_a_temp_manifest(tmp_path: Path) -> None:
    """Bounded evidence can be canonicalized directly from standard input."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    payload = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": frontmatter["plan_id"],
        "subject": "task:T-001",
        "created_at": "2026-07-29T00:00:00Z",
        "producer_ref": "project:stdin",
        "items": [{"ref": "project:result", "sha256": "a" * 64}],
    }

    result = run_workctl(
        tmp_path,
        "plan",
        "evidence",
        "record",
        "--stdin",
        input_text=json.dumps(payload),
    )
    recorded = json.loads(result.stdout)
    evidence_path = tmp_path / recorded["path"]
    assert evidence_path.is_file()
    assert recorded["sha256"] == hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == payload


def test_task_verify_evidence_stdin_records_and_binds_atomically(tmp_path: Path) -> None:
    """One verify command records canonical evidence and binds it to the task."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [
        {"id": "T-001", "description": "Verify evidence", "status": "in_progress"}
    ]
    write_plan(tmp_path, frontmatter, body)
    payload = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": frontmatter["plan_id"],
        "subject": "task:T-001",
        "created_at": "2026-07-29T00:00:00Z",
        "producer_ref": "project:atomic-verify",
        "items": [{"ref": "project:result", "sha256": "b" * 64}],
    }

    result = run_workctl(
        tmp_path,
        "task",
        "verify",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
        "--evidence-stdin",
        input_text=json.dumps(payload),
    )
    assert "TASK_UPDATED T-001 verified" in result.stdout
    revised, _ = read_plan(tmp_path)
    task = revised["tasks"][0]
    assert task["status"] == "verified"
    assert task["evidence_ref"].startswith("evidence:.work-governance/_Plan/.evidence/")
    assert task["evidence_sha256"]
    evidence_path = tmp_path / task["evidence_ref"].removeprefix("evidence:")
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == payload


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
    index = yaml.safe_load(
        (tmp_path / ".work-governance" / "_Plan" / "index.yaml").read_text(encoding="utf-8")
    )
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
    lock_path = tmp_path / ".work-governance" / "workctl.lock"
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

    receipt = ensure_test_ready_receipt(tmp_path, allow_legacy_contract=True)
    assert receipt is not None
    command = [
        sys.executable,
        str(receipt[0]),
        "--receipt-sha256",
        receipt[1],
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
        env={
            **os.environ,
            "WORKCTL_TEST_LOCK_ATTEMPT_FILE": str(writer_attempt_path),
        },
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


def test_exclusive_lock_times_out_with_holder_diagnostics(tmp_path: Path) -> None:
    """Contention is bounded and reports the current holder metadata."""
    init_plan(tmp_path)
    lock_path = tmp_path / ".work-governance" / "workctl.lock"
    holder_ready_path = tmp_path / "holder-ready"
    release_path = tmp_path / "release-holder"
    holder_script = """
import fcntl
import json
import pathlib
import sys
import time

lock_path = pathlib.Path(sys.argv[1])
ready_path = pathlib.Path(sys.argv[2])
release_path = pathlib.Path(sys.argv[3])
with lock_path.open("w", encoding="utf-8") as handle:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    json.dump({"pid": 4242, "acquired_at": "2026-08-01T00:00:00Z"}, handle)
    handle.flush()
    ready_path.write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 3
    while not release_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
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

    started_at = time.monotonic()
    result = run_workctl(
        tmp_path,
        "plan",
        "revise",
        "--status",
        "validating",
        "--expected-revision",
        "1",
        check=False,
        env={"WORK_GOVERNANCE_LOCK_TIMEOUT_SECONDS": "0.2"},
    )
    elapsed = time.monotonic() - started_at
    release_path.write_text("release\n", encoding="utf-8")
    assert holder.wait(timeout=2) == 0

    assert result.returncode == 2
    assert elapsed < 1.5
    assert "WORKCTL_LOCK_TIMEOUT" in result.stderr
    assert "holder_pid=4242" in result.stderr
    assert "holder_acquired_at=2026-08-01T00:00:00Z" in result.stderr


def test_exclusive_lock_replaces_stale_holder_metadata(tmp_path: Path) -> None:
    """Unlocked stale diagnostics never block and are replaced on acquisition."""
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [{"id": "T-001", "description": "Task", "status": "pending"}]
    write_plan(tmp_path, frontmatter, body)
    lock_path = tmp_path / ".work-governance" / "workctl.lock"
    lock_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pid": 4242,
                "acquired_at": "2026-07-31T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    revised = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
    )
    observed = json.loads(lock_path.read_text(encoding="utf-8"))

    assert "TASK_UPDATED T-001 in_progress revision=2" in revised.stdout
    assert observed["schema_version"] == 1
    assert observed["pid"] != 4242
    assert observed["acquired_at"] != "2026-07-31T00:00:00Z"


def test_suspect_artifact_blocks_validation_and_task_progress(tmp_path: Path) -> None:
    init_plan(tmp_path)
    frontmatter, body = read_plan(tmp_path)
    frontmatter["tasks"] = [{"id": "T-001", "description": "Task", "status": "pending"}]
    frontmatter["artifacts"] = [{"id": "A-001", "path": "out.txt", "status": "suspect"}]
    write_plan(tmp_path, frontmatter, body)

    layout_validation = run_workctl(tmp_path, "layout", "validate")
    validation = run_workctl(tmp_path, "plan", "validate", check=False)
    assert layout_validation.stdout.strip() == "LAYOUT_VALID"
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

    log_path = tmp_path / ".work-governance" / "logs" / "PLAN-20260723-001.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["message"] == "first"
    assert json.loads(lines[1])["message"] == "second"


def test_authority_state_unmanaged_empty_allows_governed_init(tmp_path: Path) -> None:
    """No Plan is unmanaged until init creates schema-v3 governed metadata."""
    run_workctl(tmp_path, "layout", "migrate")
    before = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    assert before["authority_state"] == "UNMANAGED_EMPTY"

    init_plan(tmp_path)

    after = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)
    assert after["authority_state"] == "GOVERNED_ACTIVE"
    assert after["candidates"][0]["classification"] == "CONFIRMED_AUTHORITY"
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_docs_plan_designated_by_agents_requires_migration(tmp_path: Path) -> None:
    """A rule-designated legacy Plan is confirmed authority, not a filename guess."""
    run_workctl(tmp_path, "layout", "migrate")
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


def test_outdated_active_plan_does_not_bypass_confirmed_second_authority(
    tmp_path: Path,
) -> None:
    """Current-schema refresh cannot hide a project-rule confirmed authority conflict."""
    init_plan(tmp_path)
    docs_plan = tmp_path / "docs" / "Plan.md"
    write_markdown_plan(docs_plan, legacy_frontmatter("PLAN-20260722-002"))
    (tmp_path / "AGENTS.md").write_text(
        "`docs/Plan.md` is the authoritative execution Plan and must be updated.\n",
        encoding="utf-8",
    )

    report = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "authority",
            "inspect",
            env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
        ).stdout
    )

    assert report["authority_state"] == "RECONCILIATION_REQUIRED"
    assert any(
        reason.startswith("unreconciled confirmed authority: docs/Plan.md")
        for reason in report["blocking_reasons"]
    )


def test_root_plan_rule_is_ignored_after_layout_ready(tmp_path: Path) -> None:
    """Project rules cannot return the legacy root to normal authority discovery."""
    init_plan(tmp_path)
    root_plan = tmp_path / "_Plan" / "Plan.md"
    write_markdown_plan(root_plan, legacy_frontmatter("PLAN-20260722-999"))
    original_bytes = root_plan.read_bytes()
    conventional_plan = tmp_path / "Plan.md"
    conventional_plan.write_text("# Business planning notes\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "`_Plan/Plan.md` is the authoritative execution Plan and must be updated.\n",
        encoding="utf-8",
    )

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)

    assert report["authority_state"] == "GOVERNED_ACTIVE"
    assert "_Plan/Plan.md" not in {candidate["path"] for candidate in report["candidates"]}
    conventional_candidate = next(
        candidate for candidate in report["candidates"] if candidate["path"] == "Plan.md"
    )
    assert conventional_candidate["classification"] == "NON_AUTHORITY"
    assert "project-rule-explicit" not in conventional_candidate["signals"]
    assert root_plan.read_bytes() == original_bytes


@pytest.mark.parametrize("candidate", ["_Plan/Plan.md", "./_Plan/Plan.md"])
def test_root_plan_explicit_authority_candidate_is_rejected(
    tmp_path: Path,
    candidate: str,
) -> None:
    """Explicit semantic input cannot bypass the legacy-root authority boundary."""
    init_plan(tmp_path)
    root_plan = tmp_path / "_Plan" / "Plan.md"
    write_markdown_plan(root_plan, legacy_frontmatter("PLAN-20260722-999"))
    original_bytes = root_plan.read_bytes()

    result = run_workctl(
        tmp_path,
        "plan",
        "authority",
        "inspect",
        "--candidate",
        f"{candidate}=CONFIRMED_AUTHORITY",
        check=False,
    )

    assert result.returncode == 2
    assert f"LEGACY_ROOT_AUTHORITY_FORBIDDEN: {candidate}" in result.stderr
    assert root_plan.read_bytes() == original_bytes


def test_root_plan_symlink_cannot_become_normal_authority(tmp_path: Path) -> None:
    """A conventional path resolving into root ``_Plan`` is ignored."""
    init_plan(tmp_path)
    root_plan = tmp_path / "_Plan" / "Plan.md"
    write_markdown_plan(root_plan, legacy_frontmatter("PLAN-20260722-999"))
    (tmp_path / "Plan.md").symlink_to(root_plan.relative_to(tmp_path))
    (tmp_path / "AGENTS.md").write_text(
        "`Plan.md` is the authoritative execution Plan and must be updated.\n",
        encoding="utf-8",
    )

    report = json.loads(run_workctl(tmp_path, "plan", "authority", "inspect").stdout)

    assert report["authority_state"] == "GOVERNED_ACTIVE"
    assert "_Plan/Plan.md" not in {candidate["path"] for candidate in report["candidates"]}


def test_phase_plan_and_next_step_text_do_not_trigger_authority(tmp_path: Path) -> None:
    """Plan-like words alone do not create execution authority."""
    run_workctl(tmp_path, "layout", "migrate")
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
    run_workctl(tmp_path, "layout", "migrate")
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
    run_workctl(tmp_path, "layout", "migrate")
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
                "archive_path": (
                    ".work-governance/_Plan/archive/MIG-20260724-001/legacy/docs/Plan.md"
                ),
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


def test_reconcile_rejects_root_plan_source_without_writing_it(tmp_path: Path) -> None:
    """Reconciliation cannot archive or pointer-write a project-root Plan."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    docs_plan = tmp_path / "docs" / "Plan.md"
    root_plan = tmp_path / "_Plan" / "Plan.md"
    root_plan.parent.mkdir()
    shutil.copy2(docs_plan, root_plan)
    original_bytes = root_plan.read_bytes()
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"][0]["path"] = "_Plan/Plan.md"
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
    assert "LEGACY_ROOT_AUTHORITY_FORBIDDEN: _Plan/Plan.md" in result.stderr
    assert root_plan.read_bytes() == original_bytes
    assert not (tmp_path / ".work-governance" / "_Plan" / ".migrations").exists()


def test_reconcile_rejects_root_plan_as_agents_rewrite_target(tmp_path: Path) -> None:
    """The separately confirmed rules rewrite is exactly scoped to root AGENTS.md."""
    manifest_path = write_reconciliation_fixture(tmp_path, include_agents_rewrite=True)
    agents_path = tmp_path / "AGENTS.md"
    root_rules = tmp_path / "_Plan" / "Rules.md"
    root_rules.parent.mkdir()
    shutil.copy2(agents_path, root_rules)
    original_bytes = root_rules.read_bytes()
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["agents_rewrite"]["path"] = "_Plan/Rules.md"
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
    assert "LEGACY_ROOT_AUTHORITY_FORBIDDEN: _Plan/Rules.md" in result.stderr
    assert root_rules.read_bytes() == original_bytes
    assert not (tmp_path / ".work-governance" / "_Plan" / ".migrations").exists()


@pytest.mark.parametrize(
    "symlink_component",
    ["migrations", "migration", "staging"],
)
def test_reconcile_stage_rejects_symlink_into_root_plan_before_writing(
    tmp_path: Path,
    symlink_component: str,
) -> None:
    """Initial staging cannot traverse a transaction symlink into root ``_Plan``."""
    manifest_path = write_reconciliation_fixture(tmp_path)
    bind_reconciliation_confirmations(
        tmp_path,
        manifest_path,
        include_agents_confirmation=False,
    )
    root_plan = tmp_path / "_Plan"
    root_plan.mkdir()
    (root_plan / "business-plan.md").write_bytes(b"ROOT-BUSINESS-BYTES")
    canonical_plan = tmp_path / ".work-governance" / "_Plan"
    migrations = canonical_plan / ".migrations"
    migration_dir = migrations / "MIG-20260724-001"
    if symlink_component == "migrations":
        migrations.symlink_to(root_plan, target_is_directory=True)
    else:
        migrations.mkdir()
        if symlink_component == "migration":
            migration_dir.symlink_to(root_plan, target_is_directory=True)
        else:
            migration_dir.mkdir()
            (migration_dir / "staging").symlink_to(root_plan, target_is_directory=True)
    root_before = tree_inventory_snapshot(root_plan)
    canonical_before = tree_inventory_snapshot(canonical_plan)

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
    assert "LAYOUT_PATH_SYMLINK: .work-governance/_Plan/.migrations" in result.stderr
    assert tree_inventory_snapshot(root_plan) == root_before
    assert tree_inventory_snapshot(canonical_plan) == canonical_before
    assert not (root_plan / "target-plan.md").exists()
    assert not (root_plan / "sources").exists()


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
    assert not (tmp_path / ".work-governance" / "_Plan" / ".migrations").exists()


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
        source
        for source in manifest["sources"]
        if source["path"] != ".work-governance/_Plan/PLAN-20260723-001.md"
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
    assert (
        "MISSING_MIGRATION_SOURCES: .work-governance/_Plan/PLAN-20260723-001.md"
    ) in result.stderr


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
    report = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)
    canonical = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-002.md"
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
    assert "(../.work-governance/_Plan/PLAN-20260724-002.md)" in (
        tmp_path / "docs" / "Plan.md"
    ).read_text(encoding="utf-8")
    assert "WORK_GOVERNANCE_NON_AUTHORITY_POINTER" in (
        tmp_path / ".work-governance" / "_Plan" / "PLAN-20260723-001.md"
    ).read_text(encoding="utf-8")
    assert (
        tmp_path
        / ".work-governance"
        / "_Plan"
        / "archive"
        / "MIG-20260724-001"
        / "legacy"
        / "docs"
        / "Plan.md"
    ).is_file()
    assert (
        tmp_path
        / ".work-governance"
        / "_Plan"
        / "archive"
        / "MIG-20260724-001"
        / "unmerged"
        / "PLAN-20260723-001.md"
    ).is_file()
    assert frontmatter["authority"]["canonical_plan_id"] == "PLAN-20260724-002"
    assert frontmatter["schema_version"] == 3
    assert frontmatter["delivery"]["status"] == "pending"
    assert frontmatter["activation"]["status"] == "deferred"
    assert len(frontmatter["authority"]["sources"]) == 2
    assert "`.work-governance/_Plan/PLAN-20260724-002.md`" in (tmp_path / "AGENTS.md").read_text(
        encoding="utf-8"
    )
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
    index = yaml.safe_load(
        (tmp_path / ".work-governance" / "_Plan" / "index.yaml").read_text(encoding="utf-8")
    )

    assert result.returncode == 2
    assert "SOURCE_DRIFT: docs/Plan.md" in result.stderr
    assert index["active_plan_id"] == "PLAN-20260723-001"
    assert not (tmp_path / ".work-governance" / "_Plan" / ".migrations").exists()


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
    journal_path = tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
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
        env={
            "WORKCTL_TEST_INTERRUPT_AFTER": ("pointer:.work-governance/_Plan/PLAN-20260723-001.md")
        },
    )
    assert interrupted.returncode == 2
    staged_agents = (
        tmp_path
        / ".work-governance"
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


@pytest.mark.parametrize(
    "tampered_field",
    ["archive_path", "target_path", "agents_rewrite.path"],
)
def test_recovery_preflights_all_paths_before_any_write(
    tmp_path: Path,
    tampered_field: str,
) -> None:
    """A forged journal path fails before root or canonical transaction bytes change."""
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
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "archive:docs/Plan.md"},
    )
    assert interrupted.returncode == 2

    root_plan = tmp_path / "_Plan"
    root_plan.mkdir()
    (root_plan / "business-plan.md").write_bytes(b"ROOT-BUSINESS-BYTES")
    journal_path = tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    journal = yaml.safe_load(journal_path.read_text(encoding="utf-8"))
    forbidden_path = "_Plan/recovery-write.md"
    if tampered_field == "archive_path":
        journal["sources"][1]["archive_path"] = forbidden_path
    elif tampered_field == "target_path":
        journal["target_path"] = forbidden_path
    else:
        journal["agents_rewrite"]["path"] = forbidden_path
    journal_path.write_text(yaml.safe_dump(journal, sort_keys=False), encoding="utf-8")
    root_before = file_tree_snapshot(root_plan)
    transaction_before = file_tree_snapshot(journal_path.parent)

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "recover",
        "--migration-id",
        "MIG-20260724-001",
        check=False,
    )

    assert recovered.returncode == 2
    assert f"LEGACY_ROOT_AUTHORITY_FORBIDDEN: {forbidden_path}" in recovered.stderr
    assert file_tree_snapshot(root_plan) == root_before
    assert file_tree_snapshot(journal_path.parent) == transaction_before
    assert not (tmp_path / forbidden_path).exists()


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
    journal_path = tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
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
    archive = (
        tmp_path
        / ".work-governance"
        / "_Plan"
        / "archive"
        / "MIG-20260724-001"
        / "legacy"
        / "docs"
        / "Plan.md"
    )
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
    archive = (
        tmp_path
        / ".work-governance"
        / "_Plan"
        / "archive"
        / "MIG-20260724-001"
        / "legacy"
        / "docs"
        / "Plan.md"
    )
    source = tmp_path / "docs" / "Plan.md"
    source.write_bytes(archive.read_bytes())

    before = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    recovered = run_workctl(tmp_path, "plan", "reconcile", "recover", check=False)

    assert before["authority_state"] == "AUTHORITY_REVIEW_REQUIRED"
    assert recovered.returncode == 2
    assert "NO_INCOMPLETE_MIGRATION" in recovered.stderr


def test_retirement_dry_run_is_stable_and_requires_complete_dispositions(
    tmp_path: Path,
) -> None:
    """Retirement exposes one stable digest and covers every unfinished blocker."""
    manifest_path = write_retirement_fixture(tmp_path)

    first = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "retire",
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
            "retire",
            "apply",
            "--manifest",
            str(manifest_path),
            "--dry-run",
        ).stdout
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["dispositions"]["obligations"] = []
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    incomplete = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    assert first == second
    assert first["confirmations_required"] == ["C-PLAN-RETIREMENT"]
    assert first["source_plan"]["plan_id"] == "PLAN-20260728-009"
    assert first["index_outcome"] == "NO_PLAN"
    assert incomplete.returncode == 2
    assert "RETIREMENT_DISPOSITION_MISSING: obligations O-001" in incomplete.stderr


def test_retirement_requires_digest_bound_confirmation(tmp_path: Path) -> None:
    """Apply rejects missing or mismatched retirement confirmation evidence."""
    manifest_path = write_retirement_fixture(tmp_path)
    missing = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )
    bind_retirement_confirmation(tmp_path, manifest_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["confirmations"]["retirement"]["evidence_sha256"] = "0" * 64
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    mismatch = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert missing.returncode == 2
    assert "MANIFEST_CONFIRMATION_REQUIRED: retirement" in missing.stderr
    assert mismatch.returncode == 2
    assert "CONFIRMATION_EVIDENCE_MISMATCH: retirement" in mismatch.stderr
    assert not (tmp_path / ".work-governance" / "_Plan" / ".retirements").exists()


def test_retirement_preserves_original_and_leaves_admission_ready_no_plan(
    tmp_path: Path,
) -> None:
    """A confirmed retirement archives truth and removes active authority last."""
    manifest_path = write_retirement_fixture(tmp_path)
    bind_retirement_confirmation(tmp_path, manifest_path)
    source = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260728-009.md"
    original_bytes = source.read_bytes()

    result = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
    )
    retired, _ = read_plan_by_id(tmp_path, "PLAN-20260728-009")
    authority = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    archive = (
        tmp_path
        / ".work-governance"
        / "_Plan"
        / ".retirements"
        / "RET-20260729-001"
        / "original.md"
    )

    assert "PLAN_RETIREMENT_COMMITTED RET-20260729-001" in result.stdout
    assert retired["status"] == "retired"
    assert retired["retirement"]["proposal_sha256"]
    assert retired["retirement"]["dispositions"]["obligations"][0]["id"] == "O-001"
    assert archive.read_bytes() == original_bytes
    assert not (tmp_path / ".work-governance" / "_Plan" / "index.yaml").exists()
    assert authority["authority_state"] == "UNMANAGED_EMPTY"
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_retirement_allows_non_authoritative_migration_pointer(
    tmp_path: Path,
) -> None:
    """Retirement leaves a valid migration pointer outside Plan validation."""
    manifest_path = write_retirement_fixture(tmp_path)
    bind_retirement_confirmation(tmp_path, manifest_path)
    pointer = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-001.md"
    pointer_bytes = (
        b"# Non-authoritative migration pointer\n\n"
        b"This path no longer controls current or future execution.\n\n"
        b"- Canonical Plan: [PLAN-20260728-009.md](PLAN-20260728-009.md)\n"
        b"- Migration: `MIG-20260724-001`\n"
        b"- Marker: `WORK_GOVERNANCE_NON_AUTHORITY_POINTER`\n"
    )
    pointer.write_bytes(pointer_bytes)

    result = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
    )

    assert "PLAN_RETIREMENT_COMMITTED RET-20260729-001" in result.stdout
    assert pointer.read_bytes() == pointer_bytes
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_interrupted_retirement_freezes_work_then_recovers_idempotently(
    tmp_path: Path,
) -> None:
    """A source-written/index-present interruption requires named recovery."""
    manifest_path = write_retirement_fixture(tmp_path)
    bind_retirement_confirmation(tmp_path, manifest_path)

    interrupted = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "retirement-source-plan"},
    )
    during = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "2",
        check=False,
    )
    recovered = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "recover",
        "--retirement-id",
        "RET-20260729-001",
    )
    repeated = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "recover",
        "--retirement-id",
        "RET-20260729-001",
    )
    after = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)

    assert interrupted.returncode == 2
    assert "SIMULATED_MIGRATION_INTERRUPT: retirement-source-plan" in interrupted.stderr
    assert during["authority_state"] == "MIGRATION_RECOVERY_REQUIRED"
    assert blocked.returncode == 2
    assert "AUTHORITY_BLOCKED: MIGRATION_RECOVERY_REQUIRED" in blocked.stderr
    assert "PLAN_RETIREMENT_COMMITTED" in recovered.stdout
    assert "PLAN_RETIREMENT_ALREADY_COMMITTED" in repeated.stdout
    assert after["authority_state"] == "UNMANAGED_EMPTY"


def test_retirement_recovery_rejects_confirmation_journal_tampering(
    tmp_path: Path,
) -> None:
    """Recovery authenticates the complete confirmation provenance."""
    manifest_path = write_retirement_fixture(tmp_path)
    bind_retirement_confirmation(tmp_path, manifest_path)
    run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "retirement-source-plan"},
    )
    journal_path = (
        tmp_path / ".work-governance" / "_Plan" / ".retirements" / "RET-20260729-001.yaml"
    )
    journal = yaml.safe_load(journal_path.read_text(encoding="utf-8"))
    journal["retirement_confirmation"]["ref"] = "user:tampered-retirement-ref"
    journal_path.write_text(
        yaml.safe_dump(journal, sort_keys=False),
        encoding="utf-8",
    )

    recovery = run_workctl(
        tmp_path,
        "plan",
        "retire",
        "recover",
        "--retirement-id",
        "RET-20260729-001",
        check=False,
    )

    assert recovery.returncode == 2
    assert "RETIREMENT_CONFIRMATION_MISMATCH" in recovery.stderr
    assert (tmp_path / ".work-governance" / "_Plan" / "index.yaml").is_file()


def test_incomplete_retirement_blocks_competing_plan_recovery_routes(
    tmp_path: Path,
) -> None:
    """Only retirement recovery may run while retirement is incomplete."""
    manifest_path = write_retirement_fixture(tmp_path)
    bind_retirement_confirmation(tmp_path, manifest_path)
    run_workctl(
        tmp_path,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_INTERRUPT_AFTER": "retirement-source-plan"},
    )

    rollover = run_workctl(
        tmp_path,
        "plan",
        "rollover",
        "recover",
        "--rollover-id",
        "ROL-20260729-001",
        check=False,
    )
    reconciliation = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "recover",
        check=False,
    )

    assert rollover.returncode == 2
    assert "RETIREMENT_RECOVERY_REQUIRED" in rollover.stderr
    assert reconciliation.returncode == 2
    assert "RETIREMENT_RECOVERY_REQUIRED" in reconciliation.stderr


def test_retirement_rejects_source_index_and_project_rule_drift(
    tmp_path: Path,
) -> None:
    """Retirement never guesses across source, index, or explicit-rule drift."""
    source_case = tmp_path / "source-case"
    source_case.mkdir()
    manifest_path = write_retirement_fixture(source_case)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["source_plan"]["sha256"] = "0" * 64
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    source_drift = run_workctl(
        source_case,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    index_case = tmp_path / "index-case"
    index_case.mkdir()
    manifest_path = write_retirement_fixture(index_case)
    bind_retirement_confirmation(index_case, manifest_path)
    index_path = index_case / ".work-governance" / "_Plan" / "index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    index["review_marker"] = "drift"
    index_path.write_text(
        yaml.safe_dump(index, sort_keys=False),
        encoding="utf-8",
    )
    index_drift = run_workctl(
        index_case,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    rules_case = tmp_path / "rules-case"
    rules_case.mkdir()
    manifest_path = write_retirement_fixture(rules_case)
    (rules_case / "AGENTS.md").write_text(
        "`.work-governance/_Plan/PLAN-20260728-009.md` is the authoritative "
        "current execution Plan.\n",
        encoding="utf-8",
    )
    rule_drift = run_workctl(
        rules_case,
        "plan",
        "retire",
        "apply",
        "--manifest",
        str(manifest_path),
        "--dry-run",
        check=False,
    )

    assert source_drift.returncode == 2
    assert "RETIREMENT_SOURCE_HASH_MISMATCH" in source_drift.stderr
    assert index_drift.returncode == 2
    assert "INDEX_BASELINE_DRIFT" in index_drift.stderr
    assert rule_drift.returncode == 2
    assert "RETIREMENT_PROJECT_RULE_REWRITE_REQUIRED" in rule_drift.stderr


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
            "path": ".work-governance/_Plan/PLAN-20260723-001.md",
            "plan_id": "PLAN-20260723-001",
            "revision": 1,
            "sha256": sha256_path(source),
        },
        "index_baseline": {
            "active_plan_id": "PLAN-20260723-001",
            "sha256": sha256_path(tmp_path / ".work-governance" / "_Plan" / "index.yaml"),
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


def test_rollover_requires_schema_v4_successor(tmp_path: Path) -> None:
    """A new route cannot reactivate the legacy mutable contract."""
    manifest_path = write_rollover_fixture(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    prepared = tmp_path / manifest["target_plan"]["prepared_file"]
    _, raw, body = prepared.read_text(encoding="utf-8").split("---\n", 2)
    frontmatter = yaml.safe_load(raw)
    assert isinstance(frontmatter, dict)
    frontmatter["schema_version"] = 3
    frontmatter.pop("goal")
    frontmatter.pop("contract")
    frontmatter.pop("unknowns")
    frontmatter.pop("revision_history")
    for task in frontmatter["tasks"]:
        task.pop("unknowns")
        task.pop("expected_evidence_delta")
    for validation in frontmatter["validations"]:
        validation.pop("provenance")
    write_markdown_plan(prepared, frontmatter, body)
    manifest["target_plan"]["sha256"] = sha256_path(prepared)
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
    assert "ROLLOVER_TARGET_MUST_USE_SCHEMA_VERSION_4" in result.stderr


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
    index_path = index_case / ".work-governance" / "_Plan" / "index.yaml"
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
    assert not (index_case / ".work-governance" / "_Plan" / ".rollovers").exists()

    target_case = tmp_path / "target-case"
    target_case.mkdir()
    manifest_path = write_rollover_fixture(target_case)
    bind_rollover_confirmation(target_case, manifest_path)
    target = target_case / ".work-governance" / "_Plan" / "PLAN-20260727-001.md"
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
    assert not (target_case / ".work-governance" / "_Plan" / ".rollovers").exists()


def test_rollover_rejects_stale_project_rule_routing(tmp_path: Path) -> None:
    """An explicit predecessor path cannot become competing authority after activation."""
    manifest_path = write_rollover_fixture(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        "`.work-governance/_Plan/PLAN-20260723-001.md` is the authoritative "
        "current execution Plan.\n",
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
    assert not (tmp_path / ".work-governance" / "_Plan" / ".rollovers").exists()


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
    assert not (tmp_path / ".work-governance" / "_Plan" / ".rollovers").exists()


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
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)
    index = yaml.safe_load(
        (tmp_path / ".work-governance" / "_Plan" / "index.yaml").read_text(encoding="utf-8")
    )
    successor = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260727-001.md"
    _, raw_frontmatter, _ = successor.read_text(encoding="utf-8").split("---\n", 2)
    successor_frontmatter = yaml.safe_load(raw_frontmatter)
    predecessor_candidate = next(
        candidate
        for candidate in status["authority_candidates"]
        if candidate["path"] == ".work-governance/_Plan/PLAN-20260723-001.md"
    )

    assert "ROLLOVER_COMMITTED ROL-20260727-001" in result.stdout
    assert sha256_path(predecessor) == predecessor_sha256
    assert index["active_plan_id"] == "PLAN-20260727-001"
    assert {item["id"] for item in index["plans"]} == {
        "PLAN-20260723-001",
        "PLAN-20260727-001",
    }
    assert successor_frontmatter["authority"]["predecessor"] == {
        "path": ".work-governance/_Plan/PLAN-20260723-001.md",
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
    target = target_case / ".work-governance" / "_Plan" / "PLAN-20260727-001.md"
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
    journal_path = tmp_path / ".work-governance" / "_Plan" / ".rollovers" / "ROL-20260727-001.yaml"
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
    journal_path = tmp_path / ".work-governance" / "_Plan" / ".rollovers" / "ROL-20260727-001.yaml"
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
                "path": ".work-governance/_Plan/PLAN-20260723-001.md",
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
    assert not (tmp_path / ".work-governance" / "_Plan" / ".migrations").exists()
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
    rollovers = tmp_path / ".work-governance" / "_Plan" / ".rollovers"
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
    assert "ROLLOVER_PATH_SYMLINK: .work-governance/_Plan/.rollovers" in result.stderr
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


def test_verified_tasks_do_not_make_historical_active_plan_terminal(
    tmp_path: Path,
) -> None:
    """Task completion evidence cannot replace closeout transitions for old active Plans."""
    plan_id = "PLAN-20260806-001"
    run_workctl(tmp_path, "layout", "migrate")
    frontmatter = schema_v4_admission_plan(plan_id)
    frontmatter["title"] = "Governance friction reduction round 1"
    frontmatter["obligations"] = [
        {"id": f"O-{index:03d}", "description": f"Obligation {index}", "status": "pending"}
        for index in range(1, 3)
    ]
    frontmatter["tasks"] = [
        {
            "id": f"T-{index:03d}",
            "description": f"Task {index}",
            "status": "verified",
            "unknowns": [],
            "expected_evidence_delta": f"Task {index} evidence is recorded.",
            "evidence_ref": f"evidence:.work-governance/_Plan/.evidence/{plan_id}/{index}.json",
            "evidence_sha256": f"{index}" * 64,
            "verified_at": "2026-08-06T15:57:14+00:00",
        }
        for index in range(1, 3)
    ]
    frontmatter["validations"] = [
        {
            "id": "V-001",
            "description": "Validation",
            "status": "pending",
            "provenance": {"kind": "confirmed-obligation", "source_ref": "project:O-001"},
        }
    ]
    frontmatter["artifacts"] = [
        {
            "id": "A-001",
            "path": "plugins/work-governance/scripts/workctl.py",
            "status": "pending",
        }
    ]
    frontmatter["delivery"] = {
        "status": "pending",
        "boundary": "local-branch-and-local-commit",
        "evidence_ref": "project:not-yet-delivered",
    }
    frontmatter["activation"] = {
        "status": "not_required",
        "current_ref": "not-applicable",
        "target_ref": "not-applicable",
        "decision_ref": "user:local-implementation-boundary",
    }
    frontmatter["route"] = {
        "route_status": "active",
        "slice_status": "admitted",
        "next_phase": "Execute T-001 baseline and implementation mapping.",
        "validation_standard": "Fresh local command and file evidence covers the selected task.",
        "confirmation_gate": "none",
    }
    frontmatter["handoff"] = {
        "route_status": "active",
        "next_step": "Execute T-001 baseline and implementation mapping.",
    }
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, frontmatter, "# Historical Active Plan\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260806-001",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = tmp_path / "admission.yaml"
    admission_path.write_text(yaml.safe_dump(admission, sort_keys=False), encoding="utf-8")
    run_workctl(tmp_path, "plan", "admit", "apply", "--manifest", str(admission_path))

    closeout = run_workctl(tmp_path, "plan", "closeout-check", check=False)
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)
    blockers = json.loads(closeout.stdout)["blockers"]

    assert closeout.returncode == 1
    assert not any(blocker.startswith("tasks not complete") for blocker in blockers)
    assert "obligations not complete: O-001" in blockers
    assert "validations not complete: V-001" in blockers
    assert "artifact not final: A-001" in blockers
    assert "delivery is not complete" in blockers
    assert "route_status is not terminal" in blockers
    assert "handoff route_status is not terminal" in blockers
    assert "closeout evidence manifest required" in blockers
    assert status["completion_claims"]["level"] == "in_progress"
    assert status["completion_claims"]["route_complete"] is False
    assert status["completion_claims"]["no_required_next_step_allowed"] is False


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
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)
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


def activation_closeout_fixture(
    plan_id: str,
    *,
    explicit_binding: bool,
    exclusion_count: int = 1,
) -> dict[str, Any]:
    """Build one schema-v4 live route ready for observed activation evidence."""
    frontmatter = schema_v4_admission_plan(plan_id)
    frontmatter["obligations"] = []
    frontmatter["tasks"] = []
    frontmatter["validations"] = []
    frontmatter["artifacts"] = []
    live_confirmation = {
        "id": "C-LIVE",
        "description": "Activate the exact candidate.",
        "status": "accepted",
        "ref": "user:live-accepted",
        "accepted_at": "2026-08-01T10:00:00+00:00",
        "intervention": {
            "kind": "external_authority",
            "blocks": ["activation", "route"],
            "basis_ref": "evidence:exact-live-candidate",
            "basis_sha256": "b" * 64,
        },
    }
    cast(list[dict[str, Any]], frontmatter["confirmations"]["required"]).append(live_confirmation)
    descriptions = [f"Switch live plugin surface {number}." for number in range(exclusion_count)]
    frontmatter["scope"]["exclude"] = [
        {
            "description": description,
            "disposition": "pending_confirmation",
            "confirmation_id": "C-LIVE",
        }
        for description in descriptions
    ]
    frontmatter["delivery"] = {
        "status": "complete",
        "boundary": "immutable-local-candidate",
        "evidence_ref": "git:exact-candidate",
    }
    activation: dict[str, Any] = {
        "status": "pending_confirmation",
        "current_ref": "plugin:work-governance@1.0.6+codex.old",
        "target_ref": "plugin:work-governance@1.0.7+codex.exact",
        "confirmation_id": "C-LIVE",
    }
    if explicit_binding:
        activation["resolves_exclusions"] = descriptions
    frontmatter["activation"] = activation
    frontmatter["route"] = {
        "route_status": "active",
        "slice_status": "live-authorized",
        "next_phase": "Activate and close the exact route.",
        "validation_standard": "Observed runtime identity matches the frozen target.",
        "confirmation_gate": "C-LIVE",
    }
    frontmatter["handoff"] = {
        "route_status": "active",
        "next_step": "Activate and close the exact route.",
    }
    return frontmatter


def record_test_evidence(
    cwd: Path,
    plan_id: str,
    *,
    subject: str,
    observed_ref: str | None = None,
) -> dict[str, Any]:
    """Record one canonical subject-specific test evidence manifest."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": subject,
        "created_at": "2026-08-01T10:01:00+00:00",
        "producer_ref": "runtime:activation-closeout-test",
        "items": [{"ref": f"runtime:{subject}-result", "sha256": "c" * 64}],
    }
    if observed_ref is not None:
        payload["observed_ref"] = observed_ref
    manifest = cwd / f"{subject}-evidence.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return cast(
        dict[str, Any],
        json.loads(
            run_workctl(
                cwd,
                "plan",
                "evidence",
                "record",
                "--manifest",
                str(manifest),
            ).stdout
        ),
    )


def test_activation_resolves_explicit_exclusion_and_atomic_closeout(
    tmp_path: Path,
) -> None:
    """Observed activation and terminal Plan closeout need no structural extra turn."""
    plan_id = "PLAN-20260801-201"
    admit_schema_v4_test_plan(
        tmp_path,
        activation_closeout_fixture(plan_id, explicit_binding=True),
        transaction_id="ADM-20260801-201",
    )
    admitted, _ = read_plan_by_id(tmp_path, plan_id)
    assert admitted["scope"]["exclude"][0]["disposition"] == "pending_confirmation"

    run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "in_progress",
        "--confirmation",
        "C-LIVE",
        "--expected-revision",
        "1",
    )
    target_ref = "plugin:work-governance@1.0.7+codex.exact"
    activation_evidence = record_test_evidence(
        tmp_path,
        plan_id,
        subject="activation",
        observed_ref=target_ref,
    )
    run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "active",
        "--confirmation",
        "C-LIVE",
        "--evidence-manifest",
        str(activation_evidence["path"]),
        "--expected-revision",
        "2",
    )
    activated, _ = read_plan_by_id(tmp_path, plan_id)
    exclusion = activated["scope"]["exclude"][0]
    assert exclusion["disposition"] == "completed"
    assert exclusion["resolution_ref"] == "user:live-accepted"

    closeout_evidence = record_test_evidence(tmp_path, plan_id, subject="closeout")
    completed = run_workctl(
        tmp_path,
        "plan",
        "complete",
        "--finalize-route",
        "--confirmation",
        "C-LIVE",
        "--evidence-manifest",
        str(closeout_evidence["path"]),
        "--expected-revision",
        "3",
    )
    final, _ = read_plan_by_id(tmp_path, plan_id)

    assert "PLAN_COMPLETED revision=4" in completed.stdout
    assert final["status"] == "complete"
    assert final["route"]["route_status"] == "terminal"
    assert final["route"]["confirmation_gate"] == "none"
    assert final["handoff"] == {"route_status": "terminal", "next_step": "none"}
    assert final["revision_history"][-1]["confirmation_id"] == "C-LIVE"


def test_activation_legacy_single_match_reconciles_exclusion(tmp_path: Path) -> None:
    """A legacy Plan gets compatibility only for one exact confirmation match."""
    plan_id = "PLAN-20260801-202"
    admit_schema_v4_test_plan(
        tmp_path,
        activation_closeout_fixture(plan_id, explicit_binding=False),
        transaction_id="ADM-20260801-202",
    )
    run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "in_progress",
        "--confirmation",
        "C-LIVE",
        "--expected-revision",
        "1",
    )
    evidence = record_test_evidence(
        tmp_path,
        plan_id,
        subject="activation",
        observed_ref="plugin:work-governance@1.0.7+codex.exact",
    )
    run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "active",
        "--confirmation",
        "C-LIVE",
        "--evidence-manifest",
        str(evidence["path"]),
        "--expected-revision",
        "2",
    )
    activated, _ = read_plan_by_id(tmp_path, plan_id)

    assert activated["scope"]["exclude"][0]["disposition"] == "completed"
    assert "resolves_exclusions" not in activated["activation"]


def test_activation_legacy_ambiguous_exclusions_fail_closed(tmp_path: Path) -> None:
    """Compatibility must not guess when multiple exclusions share one gate."""
    plan_id = "PLAN-20260801-203"
    admit_schema_v4_test_plan(
        tmp_path,
        activation_closeout_fixture(
            plan_id,
            explicit_binding=False,
            exclusion_count=2,
        ),
        transaction_id="ADM-20260801-203",
    )
    run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "in_progress",
        "--confirmation",
        "C-LIVE",
        "--expected-revision",
        "1",
    )
    evidence = record_test_evidence(
        tmp_path,
        plan_id,
        subject="activation",
        observed_ref="plugin:work-governance@1.0.7+codex.exact",
    )
    blocked = run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "active",
        "--confirmation",
        "C-LIVE",
        "--evidence-manifest",
        str(evidence["path"]),
        "--expected-revision",
        "2",
        check=False,
    )
    unchanged, _ = read_plan_by_id(tmp_path, plan_id)

    assert "ACTIVATION_EXCLUSION_BINDING_REQUIRED" in blocked.stderr
    assert unchanged["activation"]["status"] == "in_progress"
    assert all(
        exclusion["disposition"] == "pending_confirmation"
        for exclusion in unchanged["scope"]["exclude"]
    )


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


def test_schema_v3_activation_promote_rejects_target_binding(tmp_path: Path) -> None:
    """Legacy Plans must upgrade before using intake-bound exact target repair."""
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
            }
        ]
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "plugin:work-governance@1.0.3",
        "target_ref": "plugin:work-governance@1.0.4+codex.pending",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    write_plan(tmp_path, frontmatter, body)

    result = run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "in_progress",
        "--target-ref",
        "plugin:work-governance@1.0.4+codex.exact",
        "--confirmation",
        "C-LIVE-SWITCH",
        "--expected-revision",
        "1",
        check=False,
    )

    assert result.returncode == 2
    assert "ACTIVATION_TARGET_REQUIRES_SCHEMA_V4" in result.stderr


def test_schema_v3_activation_promote_without_target_remains_supported(tmp_path: Path) -> None:
    """The optional target repair does not break the legacy promotion call."""
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
            }
        ]
    }
    frontmatter["activation"] = {
        "status": "pending_confirmation",
        "current_ref": "work-governance@old",
        "target_ref": "work-governance@candidate",
        "confirmation_id": "C-LIVE-SWITCH",
    }
    write_plan(tmp_path, frontmatter, body)

    result = run_workctl(
        tmp_path,
        "plan",
        "activation-promote",
        "--state",
        "in_progress",
        "--confirmation",
        "C-LIVE-SWITCH",
        "--expected-revision",
        "1",
    )
    revised, _ = read_plan(tmp_path)

    assert "ACTIVATION_PROMOTED in_progress revision=2" in result.stdout
    assert revised["activation"]["status"] == "in_progress"
    assert revised["activation"]["target_ref"] == "work-governance@candidate"


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


def test_generic_patch_cannot_change_activation_target(tmp_path: Path) -> None:
    """Activation target changes require the dedicated intake-bound command."""
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
    assert "ACTIVATION_TARGET_REQUIRES_DEDICATED_COMMAND" in result.stderr


def test_accepted_activation_target_cannot_drift_through_generic_patch(
    tmp_path: Path,
) -> None:
    """An accepted gate does not restore the removed generic target mutation path."""
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
    assert "ACTIVATION_TARGET_REQUIRES_DEDICATED_COMMAND" in result.stderr


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
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)

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
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)

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
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)

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
    index_path = tmp_path / ".work-governance" / "_Plan" / "index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    index["plans"][0]["status"] = "active"
    index_path.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")

    closeout = run_workctl(tmp_path, "plan", "closeout-check", check=False)

    assert closeout.returncode == 1
    payload = json.loads(closeout.stdout)
    assert any(
        "index must not duplicate mutable Plan fields" in item for item in payload["blockers"]
    )


def schema_v4_admission_plan(plan_id: str) -> dict[str, Any]:
    """Build the smallest confirmed schema-v4 authority used by observed probes."""
    created_at = "2026-07-28T10:00:00+00:00"
    return {
        "schema_version": 4,
        "plan_id": plan_id,
        "title": "Observed failure admission",
        "status": "active",
        "mode": "autonomous",
        "revision": 1,
        "created_at": created_at,
        "updated_at": created_at,
        "goal": {
            "statement": "Remove the observed initial confirmation deadlock.",
            "success_conditions": ["A public transaction admits one confirmed Plan."],
        },
        "contract": {
            "revision": 1,
            "confirmation_id": "C-ADMISSION",
            "confirmed_ref": "user:observed-admission",
        },
        "scope": {"include": ["Exercise public Plan admission."], "exclude": []},
        "confirmations": {
            "required": [
                {
                    "id": "C-ADMISSION",
                    "description": "Admit this exact Plan contract.",
                    "status": "accepted",
                    "ref": "user:observed-admission",
                    "accepted_at": created_at,
                }
            ]
        },
        "unknowns": [],
        "obligations": [],
        "tasks": [
            {
                "id": "T-001",
                "description": "Exercise public confirmation creation.",
                "status": "pending",
                "unknowns": [],
                "expected_evidence_delta": "A confirmation can be created and decided.",
            }
        ],
        "validations": [
            {
                "id": "V-001",
                "description": "Public admission removes the deadlock.",
                "status": "pending",
                "provenance": {
                    "kind": "observed-failure",
                    "source_ref": "runtime:session-019fa658-initial-confirmation",
                },
            }
        ],
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
            "boundary": "local-candidate",
            "evidence_ref": "project:not-yet-delivered",
        },
        "activation": {
            "status": "not_required",
            "current_ref": "not-applicable",
            "target_ref": "not-applicable",
            "decision_ref": "user:source-only",
        },
        "route": {
            "route_status": "active",
            "slice_status": "admitted",
            "next_phase": "Exercise T-001.",
            "validation_standard": "Observed-failure evidence proves the public path.",
            "confirmation_gate": "none",
        },
        "handoff": {"route_status": "active", "next_step": "Exercise T-001."},
        "revision_history": [
            {
                "revision": 1,
                "kind": "admission",
                "changed_at": created_at,
                "rationale": "Admit the user-confirmed contract.",
                "confirmation_id": "C-ADMISSION",
            }
        ],
    }


def test_transactional_admission_removes_initial_confirmation_deadlock(
    tmp_path: Path,
) -> None:
    """A No-Plan project admits and extends authority through public commands only."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-001"
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, schema_v4_admission_plan(plan_id), "# Admitted Plan\n")
    manifest = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-001",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    manifest_path = tmp_path / "admission.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    applied = run_workctl(tmp_path, "plan", "admit", "apply", "--manifest", str(manifest_path))
    added = run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "add",
        "--confirmation-id",
        "C-EXECUTE",
        "--description",
        "Authorize observed execution.",
        "--intervention-kind",
        "plan_contract",
        "--blocks",
        "task:T-001",
        "--basis-ref",
        "user:execute-contract",
        "--basis-sha256",
        "a" * 64,
        "--expected-revision",
        "1",
    )
    decided = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-EXECUTE",
        "--ref",
        "user:execute",
        "--evidence-sha256",
        "a" * 64,
        "--expected-revision",
        "2",
    )
    frontmatter, _ = read_plan_by_id(tmp_path, plan_id)

    assert "PLAN_ADMISSION_COMMITTED" in applied.stdout
    assert "CONFIRMATION_ADDED" in added.stdout
    assert "CONFIRMATION_DECIDED C-EXECUTE accepted" in decided.stdout
    assert frontmatter["schema_version"] == 4
    assert frontmatter["revision"] == 3
    assert frontmatter["confirmations"]["required"][-1]["status"] == "accepted"


def test_immutable_evidence_survives_process_log_append(tmp_path: Path) -> None:
    """Terminal evidence is a versioned record, never a mutable process-log hash."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-001"
    frontmatter = schema_v4_admission_plan(plan_id)
    frontmatter["obligations"] = [
        {"id": "O-001", "description": "Keep evidence immutable.", "status": "pending"}
    ]
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, frontmatter, "# Evidence Plan\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-002",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = tmp_path / "admission.yaml"
    admission_path.write_text(yaml.safe_dump(admission, sort_keys=False), encoding="utf-8")
    run_workctl(tmp_path, "plan", "admit", "apply", "--manifest", str(admission_path))
    evidence_input = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "obligation:O-001",
        "created_at": "2026-07-28T10:01:00+00:00",
        "producer_ref": "runtime:observed-evidence-probe",
        "items": [{"ref": "project:result.txt", "sha256": "a" * 64}],
    }
    evidence_input_path = tmp_path / "evidence.json"
    evidence_input_path.write_text(json.dumps(evidence_input), encoding="utf-8")
    recorded = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(evidence_input_path),
        ).stdout
    )

    run_workctl(
        tmp_path,
        "log",
        "append",
        "--kind",
        "probe",
        "--message",
        "mutable process detail",
        "--expected-revision",
        "1",
    )
    run_workctl(
        tmp_path,
        "plan",
        "verify-entry",
        "--field",
        "obligations",
        "--entry-id",
        "O-001",
        "--confirmation",
        "C-ADMISSION",
        "--evidence-manifest",
        recorded["path"],
        "--expected-revision",
        "1",
    )
    revised, _ = read_plan_by_id(tmp_path, plan_id)

    assert revised["obligations"][0]["evidence_ref"] == f"evidence:{recorded['path']}"
    assert revised["obligations"][0]["evidence_sha256"] == recorded["sha256"]
    assert (tmp_path / recorded["path"]).is_file()


def test_normal_plan_init_requires_transactional_admission(tmp_path: Path) -> None:
    """The public empty-first path is closed instead of recreating the deadlock."""
    run_workctl(tmp_path, "layout", "migrate")

    blocked = run_workctl(
        tmp_path,
        "plan",
        "init",
        "--plan-id",
        "PLAN-20260728-001",
        "--title",
        "Blocked empty Plan",
        check=False,
    )

    assert blocked.returncode == 2
    assert "PLAN_ADMISSION_REQUIRED" in blocked.stderr
    assert not (tmp_path / ".work-governance" / "_Plan" / "index.yaml").exists()


@pytest.mark.parametrize("receipt_state", ["missing", "malformed"])
def test_mutation_requires_valid_receipt_even_with_forged_sessionstart_environment(
    tmp_path: Path,
    receipt_state: str,
) -> None:
    """Missing or damaged local state cannot turn the receipt-v2 gate off."""
    run_workctl(tmp_path, "layout", "migrate")
    receipt = ensure_test_ready_receipt(tmp_path, allow_legacy_contract=False)
    assert receipt is not None
    receipt_path = tmp_path / ".work-governance" / "bootstrap-state.json"
    supplied_sha256 = receipt[1]
    if receipt_state == "missing":
        receipt_path.unlink()
    else:
        receipt_path.write_text("{}\n", encoding="utf-8")
        supplied_sha256 = sha256_path(receipt_path)

    result = subprocess.run(
        [
            sys.executable,
            str(receipt[0]),
            "--receipt-sha256",
            supplied_sha256,
            "plan",
            "init",
            "--plan-id",
            "PLAN-20260728-099",
            "--title",
            "Must remain blocked",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "WORK_GOVERNANCE_SESSIONSTART": "1"},
    )

    assert result.returncode == 2
    assert "BOOTSTRAP_RECEIPT_INVALID" in result.stderr
    assert not (tmp_path / ".work-governance" / "_Plan" / "index.yaml").exists()


def test_ready_receipt_requires_current_bootstrap_action_revision(
    tmp_path: Path,
) -> None:
    """A hash-matching READY receipt cannot authorize an older action contract."""
    run_workctl(tmp_path, "layout", "migrate")
    receipt = ensure_test_ready_receipt(tmp_path, allow_legacy_contract=False)
    assert receipt is not None
    receipt_path = tmp_path / ".work-governance" / "bootstrap-state.json"
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["action_revision"] = 4
    receipt_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(receipt[0]),
            "--receipt-sha256",
            sha256_path(receipt_path),
            "plan",
            "init",
            "--plan-id",
            "PLAN-20260728-098",
            "--title",
            "Older action must remain blocked",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "BOOTSTRAP_RECEIPT_INVALID" in result.stderr
    assert not (tmp_path / ".work-governance" / "_Plan" / "index.yaml").exists()


def test_bootstrap_capability_requires_current_action_revision(
    tmp_path: Path,
) -> None:
    """A hash-matching capability cannot mutate layout under an older action."""
    receipt = ensure_test_ready_receipt(
        tmp_path,
        allow_legacy_contract=False,
        bootstrapping=True,
    )
    assert receipt is not None
    capability_path = tmp_path / ".work-governance" / "runtime" / "bootstrap-capability.json"
    payload = json.loads(capability_path.read_text(encoding="utf-8"))
    payload["action_revision"] = 4
    capability_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(receipt[0]),
            "--receipt-sha256",
            sha256_path(capability_path),
            "layout",
            "migrate",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "BOOTSTRAP_RECEIPT_INVALID" in result.stderr
    assert not (tmp_path / ".work-governance" / "version.yaml").exists()


def test_interrupted_plan_admission_recovers_forward_with_index_last(
    tmp_path: Path,
) -> None:
    """A crash after Plan installation cannot leave authority guessed or overwritten."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-001"
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, schema_v4_admission_plan(plan_id), "# Recovery Plan\n")
    manifest = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-003",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    manifest_path = tmp_path / "admission.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    interrupted = run_workctl(
        tmp_path,
        "plan",
        "admit",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_ADMISSION_INTERRUPT_AFTER": "plan-installed"},
    )
    target = tmp_path / ".work-governance" / "_Plan" / f"{plan_id}.md"
    index = tmp_path / ".work-governance" / "_Plan" / "index.yaml"

    assert interrupted.returncode == 2
    assert "PLAN_ADMISSION_TEST_INTERRUPTED: plan-installed" in interrupted.stderr
    assert target.is_file()
    assert not index.exists()

    recovered = run_workctl(
        tmp_path,
        "plan",
        "admit",
        "recover",
        "--transaction-id",
        "ADM-20260728-003",
    )

    assert "PLAN_ADMISSION_COMMITTED" in recovered.stdout
    assert yaml.safe_load(index.read_text(encoding="utf-8"))["active_plan_id"] == plan_id
    assert run_workctl(tmp_path, "plan", "validate").stdout.strip() == "PLAN_VALID"


def test_plan_admission_recovery_rejects_noncanonical_target_before_write(
    tmp_path: Path,
) -> None:
    """A forged ignored journal cannot recreate the project-root legacy authority."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-008"
    transaction_id = "ADM-20260728-008"
    transaction = tmp_path / ".work-governance" / "runtime" / "plan-admissions" / transaction_id
    staged = transaction / "staging" / f"{plan_id}.md"
    write_markdown_plan(staged, schema_v4_admission_plan(plan_id), "# Forged Recovery\n")
    journal = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": transaction_id,
        "status": "prepared",
        "created_at": "2026-07-28T10:08:00+00:00",
        "updated_at": "2026-07-28T10:08:00+00:00",
        "plan_id": plan_id,
        "plan_sha256": sha256_path(staged),
        "manifest_sha256": "a" * 64,
        "staged_path": staged.relative_to(tmp_path).as_posix(),
        "target_path": "_Plan/recovery-write.md",
    }
    journal_path = transaction / "journal.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "admit",
        "recover",
        "--transaction-id",
        transaction_id,
        check=False,
    )

    assert result.returncode == 2
    assert "INVALID_PLAN_ADMISSION_JOURNAL" in result.stderr
    assert not (tmp_path / "_Plan").exists()


def test_composed_reconciliation_upgrade_entry_is_registered(tmp_path: Path) -> None:
    """One public command owns the ordered reconciliation-to-upgrade route."""
    run_workctl(tmp_path, "layout", "migrate")

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--help",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_composed_reconciliation_upgrade_preserves_child_order_and_journals(
    tmp_path: Path,
) -> None:
    """One invocation commits schema v3 before the independent schema-v4 child."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )

    plan_id = "PLAN-20260724-002"
    active, _ = read_plan_by_id(tmp_path, plan_id)
    migration = yaml.safe_load(
        (
            tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
        ).read_text(encoding="utf-8")
    )
    upgrade = json.loads(
        (
            tmp_path
            / ".work-governance"
            / "runtime"
            / "contract-upgrades"
            / "UPG-20260730-001"
            / "journal.json"
        ).read_text(encoding="utf-8")
    )
    parent = json.loads(
        (
            tmp_path
            / ".work-governance"
            / "runtime"
            / "reconcile-upgrades"
            / "RCU-20260730-001"
            / "journal.json"
        ).read_text(encoding="utf-8")
    )

    assert "RECONCILE_UPGRADE_COMMITTED" in result.stdout
    assert active["schema_version"] == 4
    assert migration["status"] == "committed"
    assert upgrade["status"] == "committed"
    assert parent["status"] == "committed"
    assert parent["schema3_plan_sha256"] == migration["target_sha256"]
    assert migration["target_sha256"] == upgrade["source_sha256"]
    assert upgrade["target_sha256"] == sha256_path(
        tmp_path / ".work-governance" / "_Plan" / f"{plan_id}.md"
    )


def test_composed_reconciliation_upgrade_recovers_between_children(
    tmp_path: Path,
) -> None:
    """Parent recovery resumes only the upgrade after reconciliation commits."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)

    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_RECONCILE_UPGRADE_INTERRUPT_AFTER": ("reconciliation-committed"),
        },
    )
    schema3, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    interrupted_parent = json.loads(parent_path.read_text(encoding="utf-8"))

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    schema4, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")
    recovered_parent = json.loads(parent_path.read_text(encoding="utf-8"))

    assert interrupted.returncode == 2
    assert "RECONCILE_UPGRADE_TEST_INTERRUPTED: reconciliation-committed" in interrupted.stderr
    assert schema3["schema_version"] == 3
    assert interrupted_parent["status"] == "reconciliation-committed"
    assert "RECONCILE_UPGRADE_COMMITTED" in recovered.stdout
    assert schema4["schema_version"] == 4
    assert recovered_parent["status"] == "committed"


@pytest.mark.parametrize(
    ("stage_kind", "expected_journals", "retry_command"),
    [
        ("parent", (False, False, False), "apply"),
        ("reconciliation", (True, False, False), "recover"),
        ("contract-upgrade", (True, True, False), "recover"),
    ],
)
def test_composed_reconciliation_upgrade_recovers_before_journal_publication(
    tmp_path: Path,
    stage_kind: str,
    expected_journals: tuple[bool, bool, bool],
    retry_command: str,
) -> None:
    """Exact partial staging is resumable before each transaction journal exists."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_STAGE_INTERRUPT_BEFORE_JOURNAL": stage_kind,
        },
    )
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    migration_path = (
        tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    )
    upgrade_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "contract-upgrades"
        / "UPG-20260730-001"
        / "journal.json"
    )
    observed_journals = (
        parent_path.is_file(),
        migration_path.is_file(),
        upgrade_path.is_file(),
    )
    if stage_kind == "parent":
        time.sleep(1.1)

    if retry_command == "apply":
        recovered = run_workctl(
            tmp_path,
            "plan",
            "reconcile-upgrade",
            "apply",
            "--manifest",
            str(manifest_path),
            env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
        )
    else:
        recovered = run_workctl(
            tmp_path,
            "plan",
            "reconcile-upgrade",
            "recover",
            "--workflow-id",
            "RCU-20260730-001",
            env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
        )
    active, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    migration = cast(
        dict[str, Any],
        yaml.safe_load(migration_path.read_text(encoding="utf-8")),
    )
    upgrade = json.loads(upgrade_path.read_text(encoding="utf-8"))

    assert interrupted.returncode == 2
    assert f"TRANSACTION_STAGE_TEST_INTERRUPTED: {stage_kind}" in interrupted.stderr
    assert observed_journals == expected_journals
    assert "RECONCILE_UPGRADE_COMMITTED" in recovered.stdout
    assert active["schema_version"] == 4
    assert active["updated_at"] == "2026-07-30T00:03:00+00:00"
    assert parent["status"] == "committed"
    assert migration["status"] == "committed"
    assert upgrade["status"] == "committed"


def test_composed_reconciliation_upgrade_rejects_partial_staging_drift(
    tmp_path: Path,
) -> None:
    """A retry cannot authenticate changed parent bytes that lack a journal."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_STAGE_INTERRUPT_BEFORE_JOURNAL": "parent",
        },
    )
    parent_dir = (
        tmp_path / ".work-governance" / "runtime" / "reconcile-upgrades" / "RCU-20260730-001"
    )
    (parent_dir / "staging" / "schema3-plan.md").write_bytes(b"drift\n")

    retried = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )

    assert interrupted.returncode == 2
    assert retried.returncode == 2
    assert "RECONCILE_UPGRADE_TRANSACTION_CONFLICT" in retried.stderr
    assert not (parent_dir / "journal.json").exists()
    assert not (
        tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    ).exists()


def test_composed_reconciliation_upgrade_recovers_during_reconciliation_child(
    tmp_path: Path,
) -> None:
    """Recovery finishes a migration interrupted after index activation."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_INTERRUPT_AFTER": "index-activation",
        },
    )
    migration_path = (
        tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    )
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    migration = cast(
        dict[str, Any],
        yaml.safe_load(migration_path.read_text(encoding="utf-8")),
    )
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    schema3, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    schema4, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    assert interrupted.returncode == 2
    assert "SIMULATED_MIGRATION_INTERRUPT: index-activation" in interrupted.stderr
    assert migration["status"] == "applying"
    assert parent["status"] == "children-staged"
    assert schema3["schema_version"] == 3
    assert "RECONCILE_UPGRADE_COMMITTED" in recovered.stdout
    assert schema4["schema_version"] == 4


def test_composed_reconciliation_upgrade_recovers_during_upgrade_child(
    tmp_path: Path,
) -> None:
    """Recovery authenticates schema-v4 bytes left by an interrupted upgrade."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_UPGRADE_INTERRUPT_AFTER": "plan-replaced",
        },
    )
    upgrade_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "contract-upgrades"
        / "UPG-20260730-001"
        / "journal.json"
    )
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    upgrade = json.loads(upgrade_path.read_text(encoding="utf-8"))
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    interrupted_active, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    recovered_upgrade = json.loads(upgrade_path.read_text(encoding="utf-8"))
    recovered_parent = json.loads(parent_path.read_text(encoding="utf-8"))

    assert interrupted.returncode == 2
    assert "PLAN_CONTRACT_UPGRADE_TEST_INTERRUPTED: plan-replaced" in interrupted.stderr
    assert interrupted_active["schema_version"] == 4
    assert upgrade["status"] == "plan-replaced"
    assert parent["status"] == "reconciliation-committed"
    assert "RECONCILE_UPGRADE_COMMITTED" in recovered.stdout
    assert recovered_upgrade["status"] == "committed"
    assert recovered_parent["status"] == "committed"


def test_composed_reconciliation_upgrade_blocks_mutation_during_upgrade_cutover(
    tmp_path: Path,
) -> None:
    """An incomplete parent makes schema-v4 cutover globally recovery-only."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_UPGRADE_INTERRUPT_AFTER": "plan-replaced",
        },
    )
    active_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-002.md"
    migration_path = (
        tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    )
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    upgrade_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "contract-upgrades"
        / "UPG-20260730-001"
        / "journal.json"
    )
    protected_paths = [active_path, migration_path, parent_path, upgrade_path]
    before = [sha256_path(path) for path in protected_paths]
    active, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    status = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "status",
            "--full",
            env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
        ).stdout
    )
    mutation = run_workctl(
        tmp_path,
        "task",
        "block",
        "--task-id",
        "T-001",
        "--expected-revision",
        str(active["revision"]),
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )

    assert interrupted.returncode == 2
    assert status["authority_state"] == "MIGRATION_RECOVERY_REQUIRED"
    assert any(
        "incomplete reconcile-upgrade journal" in reason for reason in status["blocking_reasons"]
    )
    assert any(
        "incomplete contract-upgrade journal" in reason for reason in status["blocking_reasons"]
    )
    assert mutation.returncode == 2
    assert "AUTHORITY_BLOCKED: MIGRATION_RECOVERY_REQUIRED" in mutation.stderr
    assert [sha256_path(path) for path in protected_paths] == before

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    final_active, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    assert "RECONCILE_UPGRADE_COMMITTED" in recovered.stdout
    assert final_active["schema_version"] == 4


def test_composed_reconciliation_upgrade_blocks_fresh_reconciliation_transactions(
    tmp_path: Path,
) -> None:
    """Recovery-only state cannot stage a second parent or ordinary reconciliation."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_STAGE_INTERRUPT_BEFORE_JOURNAL": "reconciliation",
        },
    )
    second_manifest_path = tmp_path / "reconcile-upgrade-b.yaml"
    second_manifest = cast(
        dict[str, Any],
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")),
    )
    second_manifest["workflow_id"] = "RCU-20260730-002"
    second_manifest_path.write_text(
        yaml.safe_dump(second_manifest, sort_keys=False),
        encoding="utf-8",
    )
    parent_a = tmp_path / ".work-governance" / "runtime" / "reconcile-upgrades" / "RCU-20260730-001"
    parent_b = parent_a.parent / "RCU-20260730-002"
    migration = tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001"
    plan_dir = tmp_path / ".work-governance" / "_Plan"
    protected_files = sorted(
        [
            *(path for path in parent_a.rglob("*") if path.is_file()),
            *(path for path in migration.rglob("*") if path.is_file()),
            *plan_dir.glob("PLAN-*.md"),
            *(path for path in [plan_dir / "index.yaml"] if path.is_file()),
        ],
        key=lambda path: path.as_posix(),
    )
    before = {path.relative_to(tmp_path).as_posix(): sha256_path(path) for path in protected_files}

    second_parent = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(second_manifest_path),
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    ordinary_reconciliation = run_workctl(
        tmp_path,
        "plan",
        "reconcile",
        "apply",
        "--manifest",
        str(tmp_path / "reconcile.yaml"),
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    after_files = sorted(
        [
            *(path for path in parent_a.rglob("*") if path.is_file()),
            *(path for path in migration.rglob("*") if path.is_file()),
            *plan_dir.glob("PLAN-*.md"),
            *(path for path in [plan_dir / "index.yaml"] if path.is_file()),
        ],
        key=lambda path: path.as_posix(),
    )
    after = {path.relative_to(tmp_path).as_posix(): sha256_path(path) for path in after_files}

    assert interrupted.returncode == 2
    assert second_parent.returncode == 2
    assert "MIGRATION_RECOVERY_REQUIRED" in second_parent.stderr
    assert ordinary_reconciliation.returncode == 2
    assert "MIGRATION_RECOVERY_REQUIRED" in ordinary_reconciliation.stderr
    assert not parent_b.exists()
    assert after == before

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    final_active, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    assert "RECONCILE_UPGRADE_COMMITTED" in recovered.stdout
    assert final_active["schema_version"] == 4


def test_composed_reconciliation_upgrade_rejects_wrong_child_order(
    tmp_path: Path,
) -> None:
    """A prepared upgrade cannot accept schema-v4 authority before its child runs."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_RECONCILE_UPGRADE_INTERRUPT_AFTER": ("reconciliation-committed"),
        },
    )
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    upgrade_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "contract-upgrades"
        / "UPG-20260730-001"
        / "journal.json"
    )
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    active_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-002.md"
    schema4_staged = tmp_path / str(parent["schema4_staged_path"])
    shutil.copyfile(schema4_staged, active_path)

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    upgrade = json.loads(upgrade_path.read_text(encoding="utf-8"))

    assert interrupted.returncode == 2
    assert recovered.returncode == 2
    assert "RECONCILE_UPGRADE_CHILD_ORDER_VIOLATION" in recovered.stderr
    assert upgrade["status"] == "prepared"


def test_composed_reconciliation_upgrade_committed_recovery_is_idempotent(
    tmp_path: Path,
) -> None:
    """A committed recovery call revalidates without rewriting any journal."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    paths = [
        tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-002.md",
        tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml",
        tmp_path
        / ".work-governance"
        / "runtime"
        / "contract-upgrades"
        / "UPG-20260730-001"
        / "journal.json",
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json",
    ]
    before = [sha256_path(path) for path in paths]

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )

    assert "RECONCILE_UPGRADE_ALREADY_COMMITTED" in recovered.stdout
    assert [sha256_path(path) for path in paths] == before


def test_composed_reconciliation_upgrade_rejects_parent_binding_drift(
    tmp_path: Path,
) -> None:
    """A changed parent binding fails closed without touching active schema v4."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    active_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-002.md"
    active_before = sha256_path(active_path)
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    parent["schema4_plan_sha256"] = "d" * 64
    parent_path.write_text(json.dumps(parent), encoding="utf-8")

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )

    assert recovered.returncode == 2
    assert "RECONCILE_UPGRADE_BINDING_DRIFT" in recovered.stderr
    assert sha256_path(active_path) == active_before


def test_composed_reconciliation_upgrade_rejects_stale_confirmation_before_staging(
    tmp_path: Path,
) -> None:
    """A stale reconciliation decision aborts before any transaction is staged."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    reconciliation_path = tmp_path / "reconcile.yaml"
    reconciliation = cast(
        dict[str, Any],
        yaml.safe_load(reconciliation_path.read_text(encoding="utf-8")),
    )
    reconciliation["confirmations"]["baseline"]["evidence_sha256"] = "e" * 64
    reconciliation_path.write_text(
        yaml.safe_dump(reconciliation, sort_keys=False),
        encoding="utf-8",
    )
    manifest = cast(
        dict[str, Any],
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")),
    )
    manifest["reconciliation_manifest_sha256"] = sha256_path(reconciliation_path)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )

    assert result.returncode == 2
    assert "CONFIRMATION_EVIDENCE_MISMATCH: baseline" in result.stderr
    assert not (
        tmp_path / ".work-governance" / "runtime" / "reconcile-upgrades" / "RCU-20260730-001"
    ).exists()
    assert not (
        tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    ).exists()


def test_composed_reconciliation_upgrade_rejects_forged_parent_commit(
    tmp_path: Path,
) -> None:
    """A forged parent status cannot skip its uncommitted upgrade child."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_RECONCILE_UPGRADE_INTERRUPT_AFTER": ("reconciliation-committed"),
        },
    )
    parent_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "reconcile-upgrades"
        / "RCU-20260730-001"
        / "journal.json"
    )
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    parent["status"] = "committed"
    parent_path.write_text(json.dumps(parent), encoding="utf-8")

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    active, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    assert interrupted.returncode == 2
    assert recovered.returncode == 2
    assert "RECONCILE_UPGRADE_COMMITTED_STATE_INVALID" in recovered.stderr
    assert "RECONCILE_UPGRADE_ALREADY_COMMITTED" not in recovered.stdout
    assert active["schema_version"] == 3


def test_composed_reconciliation_upgrade_rejects_forged_upgrade_child_commit(
    tmp_path: Path,
) -> None:
    """A forged child status cannot authenticate absent schema-v4 authority."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={
            "TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1",
            "WORKCTL_TEST_RECONCILE_UPGRADE_INTERRUPT_AFTER": ("reconciliation-committed"),
        },
    )
    upgrade_path = (
        tmp_path
        / ".work-governance"
        / "runtime"
        / "contract-upgrades"
        / "UPG-20260730-001"
        / "journal.json"
    )
    upgrade = json.loads(upgrade_path.read_text(encoding="utf-8"))
    upgrade["status"] = "committed"
    upgrade_path.write_text(json.dumps(upgrade), encoding="utf-8")

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    active, _ = read_plan_by_id(tmp_path, "PLAN-20260724-002")

    assert interrupted.returncode == 2
    assert recovered.returncode == 2
    assert "CONTRACT_UPGRADE_COMMITTED_STATE_DRIFT" in recovered.stderr
    assert active["schema_version"] == 3


def test_composed_reconciliation_upgrade_rejects_forged_migration_binding(
    tmp_path: Path,
) -> None:
    """A committed migration child remains bound to its accepted proposal."""
    manifest_path = write_reconcile_upgrade_fixture(tmp_path)
    run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "apply",
        "--manifest",
        str(manifest_path),
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )
    migration_path = (
        tmp_path / ".work-governance" / "_Plan" / ".migrations" / "MIG-20260724-001.yaml"
    )
    migration = cast(
        dict[str, Any],
        yaml.safe_load(migration_path.read_text(encoding="utf-8")),
    )
    migration["prepared_plan_sha256"] = "c" * 64
    migration_path.write_text(yaml.safe_dump(migration, sort_keys=False), encoding="utf-8")
    active_path = tmp_path / ".work-governance" / "_Plan" / "PLAN-20260724-002.md"
    active_before = sha256_path(active_path)

    recovered = run_workctl(
        tmp_path,
        "plan",
        "reconcile-upgrade",
        "recover",
        "--workflow-id",
        "RCU-20260730-001",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "1"},
    )

    assert recovered.returncode == 2
    assert "MIGRATION_COMMITTED_BINDING_DRIFT" in recovered.stderr
    assert sha256_path(active_path) == active_before


def test_active_schema_v3_requires_current_schema_refresh(tmp_path: Path) -> None:
    """A live v3 contract is read-only debt until current-schema refresh archives it."""
    init_plan(tmp_path)
    required = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "contract",
            "upgrade",
            "status",
            env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
        ).stdout
    )
    refresh = json.loads(
        run_workctl(
            tmp_path,
            "migrate",
            "inspect",
            env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
        ).stdout
    )
    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
    )
    obsolete_upgrade = run_workctl(
        tmp_path,
        "plan",
        "contract",
        "upgrade",
        "apply",
        "--manifest",
        "missing-upgrade.yaml",
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
    )

    assert required["contract_state"] == "PLAN_SCHEMA_REFRESH_REQUIRED"
    assert refresh["requires_migration"] is True
    assert refresh["migration_mode"] == "archive_legacy_and_rebuild_current_plan"
    assert "PLAN_SCHEMA_REFRESH_REQUIRED" in blocked.stderr
    assert obsolete_upgrade.returncode == 2
    assert "PLAN_SCHEMA_REFRESH_REQUIRED" in obsolete_upgrade.stderr


def test_contract_upgrade_recovery_rejects_noncanonical_target_before_write(
    tmp_path: Path,
) -> None:
    """Historical contract-upgrade recovery still rejects forged journal targets."""
    init_plan(tmp_path)
    plan_id = "PLAN-20260723-001"
    transaction_id = "UPG-20260728-009"
    transaction = tmp_path / ".work-governance" / "runtime" / "contract-upgrades" / transaction_id
    staged = transaction / "staging" / f"{plan_id}.md"
    write_markdown_plan(staged, schema_v4_admission_plan(plan_id), "# Forged Upgrade\n")
    journal = {
        "schema_version": 1,
        "kind": "plan-contract-upgrade",
        "transaction_id": transaction_id,
        "status": "prepared",
        "created_at": "2026-07-28T10:09:00+00:00",
        "updated_at": "2026-07-28T10:09:00+00:00",
        "plan_id": plan_id,
        "source_sha256": sha256_path(plan_path(tmp_path)),
        "target_sha256": sha256_path(staged),
        "manifest_sha256": "b" * 64,
        "staged_path": staged.relative_to(tmp_path).as_posix(),
        "target_path": "_Plan/recovery-write.md",
    }
    journal_path = transaction / "journal.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    result = run_workctl(
        tmp_path,
        "plan",
        "contract",
        "upgrade",
        "recover",
        "--transaction-id",
        transaction_id,
        check=False,
        env={"TEST_WORKCTL_ALLOW_LEGACY_CONTRACT": "0"},
    )

    assert result.returncode == 2
    assert "INVALID_CONTRACT_UPGRADE_JOURNAL" in result.stderr
    assert not (tmp_path / "_Plan").exists()


def admit_schema_v4_test_plan(
    cwd: Path,
    frontmatter: dict[str, Any],
    *,
    transaction_id: str,
) -> str:
    """Admit one schema-v4 fixture and return its Plan ID."""
    run_workctl(cwd, "layout", "migrate")
    plan_id = str(frontmatter["plan_id"])
    prepared = cwd / "candidate.md"
    write_markdown_plan(prepared, frontmatter, "# Strict governance fixture\n")
    manifest = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": transaction_id,
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    manifest_path = cwd / "admission.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    run_workctl(cwd, "plan", "admit", "apply", "--manifest", str(manifest_path))
    return plan_id


def test_pending_confirmation_requires_strict_classification_and_exact_basis(
    tmp_path: Path,
) -> None:
    """Legacy pending gates stay readable but cannot decide until exact classification."""
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        schema_v4_admission_plan("PLAN-20260731-101"),
        transaction_id="ADM-20260731-101",
    )
    frontmatter, body = read_plan_by_id(tmp_path, plan_id)
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-LEGACY-PENDING",
            "description": "Legacy decision without typed intervention.",
            "status": "pending",
        }
    )
    plan_file = tmp_path / ".work-governance" / "_Plan" / f"{plan_id}.md"
    write_markdown_plan(plan_file, frontmatter, body)

    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)
    blocked = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-LEGACY-PENDING",
        "--ref",
        "user:decision",
        "--evidence-sha256",
        "a" * 64,
        "--expected-revision",
        "1",
        check=False,
    )
    classification = {
        "schema_version": 1,
        "kind": "confirmation-intervention-classification",
        "plan_id": plan_id,
        "confirmation_id": "C-LEGACY-PENDING",
        "intervention": {
            "kind": "plan_contract",
            "blocks": ["task:T-001"],
            "basis_ref": "user:exact-plan-contract",
            "basis_sha256": "a" * 64,
        },
    }
    classification_path = tmp_path / "classification.yaml"
    classification_path.write_text(
        yaml.safe_dump(classification, sort_keys=False),
        encoding="utf-8",
    )
    run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "classify",
        "--manifest",
        str(classification_path),
        "--expected-revision",
        "1",
    )
    wrong_basis = run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-LEGACY-PENDING",
        "--ref",
        "user:decision",
        "--evidence-sha256",
        "b" * 64,
        "--expected-revision",
        "2",
        check=False,
    )
    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-LEGACY-PENDING",
        "--ref",
        "user:decision",
        "--evidence-sha256",
        "a" * 64,
        "--expected-revision",
        "2",
    )
    final = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)

    assert status["intervention_contract_state"] == "LEGACY_CLASSIFICATION_REQUIRED"
    assert status["user_intervention"]["state"] == "PLAN_DECISION_REQUIRED"
    assert "CONFIRMATION_CLASSIFICATION_REQUIRED" in blocked.stderr
    assert "CONFIRMATION_EVIDENCE_BASIS_MISMATCH" in wrong_basis.stderr
    assert final["intervention_contract_state"] == "STRICT_READY"
    assert final["user_intervention"]["state"] == "NOT_REQUIRED"


def test_future_authority_gate_is_information_until_its_target_is_current(
    tmp_path: Path,
) -> None:
    """A future live gate does not turn ordinary progress reporting into a wait."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-102")
    frontmatter["tasks"].append(
        {
            "id": "T-002",
            "description": "Run the separately authorized live switch.",
            "status": "pending",
            "depends_on": ["T-001"],
            "unknowns": [],
            "expected_evidence_delta": "The live boundary is exact.",
            "requires_confirmation": "C-LIVE",
        }
    )
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-LIVE",
            "description": "Authorize the exact external switch.",
            "status": "pending",
            "intervention": {
                "kind": "external_authority",
                "blocks": ["task:T-002", "activation"],
                "basis_ref": "project:future-live-basis",
            },
        }
    )
    admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-102",
    )

    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)

    assert status["intervention_contract_state"] == "STRICT_READY"
    assert status["user_intervention"]["current_targets"] == ["task:T-001"]
    assert status["user_intervention"]["state"] == "NOT_REQUIRED"


def test_current_advancement_targets_wrapper_delegates_to_scheduler_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The single-file controller wrapper delegates current-target selection to scheduler."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_advancement_fixture")
    calls: list[tuple[object, object]] = []

    def fake_current_targets(frontmatter: object, verified_states: object) -> list[str]:
        """Record wrapper inputs and return a sentinel scheduler result."""
        calls.append((frontmatter, verified_states))
        return ["task:T-SENTINEL"]

    wrapper = namespace["current_advancement_targets"]
    monkeypatch.setitem(
        wrapper.__globals__,
        "MODULE_CURRENT_ADVANCEMENT_TARGETS",
        fake_current_targets,
    )
    frontmatter: dict[str, object] = {"delivery": {"status": "pending"}}

    payload = wrapper(frontmatter)

    assert payload == ["task:T-SENTINEL"]
    assert calls == [(frontmatter, namespace["VERIFIED_TASK_STATES"])]


def test_scheduler_state_wrappers_delegate_to_scheduler_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Scheduler state wrappers preserve controller-owned paths and error translation."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_scheduler_state_fixture")
    path_calls: list[tuple[Path, str, str, object]] = []
    load_calls: list[tuple[Path, str, str, object]] = []
    dump_calls: list[object] = []

    def fake_state_path(
        root: Path,
        plan_id: str,
        governance_dir_name: str,
        reject_symlink_components: object,
    ) -> Path:
        path_calls.append((root, plan_id, governance_dir_name, reject_symlink_components))
        return root / "scheduler-state.json"

    def fake_load_state(
        root: Path,
        plan_id: str,
        governance_dir_name: str,
        reject_symlink_components: object,
    ) -> dict[str, object]:
        load_calls.append((root, plan_id, governance_dir_name, reject_symlink_components))
        return {"schema_version": 1, "plan_id": plan_id, "state_sequence": 0, "priorities": {}}

    def fake_dump_state(state: object) -> str:
        dump_calls.append(state)
        return "SERIALIZED\n"

    path_wrapper = namespace["scheduler_state_path"]
    load_wrapper = namespace["load_scheduler_state"]
    dump_wrapper = namespace["dump_scheduler_state"]
    monkeypatch.setitem(path_wrapper.__globals__, "MODULE_SCHEDULER_STATE_PATH", fake_state_path)
    monkeypatch.setitem(load_wrapper.__globals__, "MODULE_LOAD_SCHEDULER_STATE", fake_load_state)
    monkeypatch.setitem(dump_wrapper.__globals__, "MODULE_DUMP_SCHEDULER_STATE", fake_dump_state)

    assert path_wrapper(tmp_path, "PLAN-20260806-001") == tmp_path / "scheduler-state.json"
    assert load_wrapper(tmp_path, "PLAN-20260806-001") == {
        "schema_version": 1,
        "plan_id": "PLAN-20260806-001",
        "state_sequence": 0,
        "priorities": {},
    }
    assert dump_wrapper({"state_sequence": 0}) == "SERIALIZED\n"
    assert path_calls == [
        (
            tmp_path,
            "PLAN-20260806-001",
            namespace["GOVERNANCE_DIR_NAME"],
            namespace["reject_symlink_components"],
        )
    ]
    assert load_calls == path_calls
    assert dump_calls == [{"state_sequence": 0}]

    def broken_load_state(
        _root: Path,
        _plan_id: str,
        _governance_dir_name: str,
        _reject_symlink_components: object,
    ) -> dict[str, object]:
        raise namespace["ModuleSchedulerStateError"]("bad state")

    monkeypatch.setitem(load_wrapper.__globals__, "MODULE_LOAD_SCHEDULER_STATE", broken_load_state)
    with pytest.raises(namespace["WorkctlError"], match="SCHEDULER_STATE_INVALID"):
        load_wrapper(tmp_path, "PLAN-20260806-001")


def test_ready_and_blocked_task_wrappers_delegate_to_scheduler_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ready and blocked wrappers use scheduler projections without inline fallback."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_scheduler_projection_fixture")
    ready_calls: list[tuple[list[Any], object]] = []
    blocked_calls: list[list[Any]] = []

    def fake_ready_targets(tasks: list[object], priorities: object) -> list[str]:
        ready_calls.append((tasks, priorities))
        return ["task:T-READY"]

    def fake_blocked_targets(tasks: list[object]) -> list[str]:
        blocked_calls.append(tasks)
        return ["task:T-BLOCKED"]

    ready_wrapper = namespace["ready_task_targets"]
    blocked_wrapper = namespace["blocked_task_targets"]
    monkeypatch.setitem(ready_wrapper.__globals__, "MODULE_READY_TASK_TARGETS", fake_ready_targets)
    monkeypatch.setitem(
        blocked_wrapper.__globals__,
        "MODULE_BLOCKED_TASK_TARGETS",
        fake_blocked_targets,
    )
    frontmatter = {
        "tasks": [
            {"id": "T-001", "status": "pending", "depends_on": ["T-000"]},
            {"id": "T-002", "status": "blocked", "depends_on": "malformed"},
        ],
    }

    assert ready_wrapper(frontmatter, {"T-001": 3}) == ["task:T-READY"]
    assert blocked_wrapper(frontmatter) == ["task:T-BLOCKED"]

    ready_tasks, ready_priorities = ready_calls[0]
    blocked_tasks = blocked_calls[0]
    assert ready_priorities == {"T-001": 3}
    assert [(task.task_id, task.status, task.dependencies) for task in ready_tasks] == [
        ("T-001", "pending", ("T-000",)),
        ("T-002", "blocked", ()),
    ]
    assert blocked_tasks == ready_tasks

    monkeypatch.setitem(ready_wrapper.__globals__, "TaskProjection", None)
    with pytest.raises(namespace["WorkctlError"], match="SCHEDULER_MODULE_UNAVAILABLE"):
        ready_wrapper(frontmatter)


def test_status_projection_wrappers_delegate_to_status_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Status projection wrappers inject controller-owned constants and callbacks."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_status_projection_fixture")
    blocking_calls: list[tuple[object, object]] = []
    pending_calls: list[object] = []
    detail_calls: list[tuple[object, object, object, object]] = []
    review_calls: list[tuple[Path, object, str]] = []

    def fake_blocking_artifacts(frontmatter: object, blocking_states: object) -> dict[str, str]:
        blocking_calls.append((frontmatter, blocking_states))
        return {"A-001": "suspect"}

    def fake_pending_ids(frontmatter: object) -> list[str]:
        pending_calls.append(frontmatter)
        return ["C-001"]

    def fake_independent_review_blockers(
        root: Path,
        frontmatter: object,
        target: str,
    ) -> list[str]:
        review_calls.append((root, frontmatter, target))
        return ["artifact_review"]

    def fake_task_blocking_details(
        frontmatter: object,
        *,
        independent_review_blockers: Callable[[str], list[str]],
        blocking_artifact_states: object,
        verified_task_states: object,
    ) -> list[dict[str, object]]:
        detail_calls.append(
            (
                frontmatter,
                blocking_artifact_states,
                verified_task_states,
                independent_review_blockers,
            )
        )
        review_modes = independent_review_blockers("task:T-001")
        return [{"task": "task:T-001", "reasons": [{"modes": review_modes}]}]

    blocking_wrapper = namespace["blocking_artifacts"]
    pending_wrapper = namespace["pending_confirmation_ids"]
    details_wrapper = namespace["task_blocking_details"]
    monkeypatch.setitem(
        blocking_wrapper.__globals__,
        "module_blocking_artifacts",
        fake_blocking_artifacts,
    )
    monkeypatch.setitem(
        pending_wrapper.__globals__,
        "module_pending_confirmation_ids",
        fake_pending_ids,
    )
    monkeypatch.setitem(
        details_wrapper.__globals__,
        "module_task_blocking_details",
        fake_task_blocking_details,
    )
    monkeypatch.setitem(
        details_wrapper.__globals__,
        "independent_review_blockers",
        fake_independent_review_blockers,
    )
    frontmatter: dict[str, object] = {"tasks": []}

    assert blocking_wrapper(frontmatter) == {"A-001": "suspect"}
    assert pending_wrapper(frontmatter) == ["C-001"]
    assert details_wrapper(tmp_path, frontmatter) == [
        {"task": "task:T-001", "reasons": [{"modes": ["artifact_review"]}]}
    ]
    assert blocking_calls == [(frontmatter, namespace["BLOCKING_ARTIFACT_STATES"])]
    assert pending_calls == [frontmatter]
    assert detail_calls[0][:3] == (
        frontmatter,
        namespace["BLOCKING_ARTIFACT_STATES"],
        namespace["VERIFIED_TASK_STATES"],
    )
    assert review_calls == [(tmp_path, frontmatter, "task:T-001")]


def test_workflow_input_and_contract_wrappers_delegate_to_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow wrappers keep all contract parsing and normalization in modules."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_workflow_contract_fixture")
    input_calls: list[tuple[bool, object, bool, int, bool]] = []
    parse_calls: list[tuple[bytes, str]] = []
    string_calls: list[tuple[object, str]] = []
    list_calls: list[tuple[object, str]] = []
    task_calls: list[tuple[object, object]] = []
    confirmation_calls: list[object] = []

    def fake_read_workflow_input_bytes(
        *,
        use_stdin: bool,
        raw_path: object,
        required: bool,
        max_bytes: int,
        stdin_reader: object,
    ) -> bytes:
        input_calls.append((use_stdin, raw_path, required, max_bytes, callable(stdin_reader)))
        return b"title: delegated\n"

    def fake_parse_workflow_mapping(content: bytes, *, error_prefix: str) -> dict[str, object]:
        parse_calls.append((content, error_prefix))
        return {"parsed": True}

    def fake_non_empty_string(value: object, *, field: str) -> str:
        string_calls.append((value, field))
        return "delegated-string"

    def fake_workflow_string_list(value: object, *, field: str) -> list[str]:
        list_calls.append((value, field))
        return ["delegated-list"]

    def fake_normalize_goal_tasks(
        raw_tasks: object,
        *,
        task_id_pattern: object,
    ) -> list[dict[str, object]]:
        task_calls.append((raw_tasks, task_id_pattern))
        return [{"id": "T-001", "description": "Delegated", "depends_on": []}]

    def fake_normalize_goal_confirmations(
        raw_confirmations: object,
    ) -> dict[str, list[dict[str, object]]]:
        confirmation_calls.append(raw_confirmations)
        return {"required": [], "accepted": [{"id": "C-001"}]}

    read_wrapper = namespace["read_workflow_input_bytes"]
    parse_wrapper = namespace["parse_workflow_mapping"]
    string_wrapper = namespace["non_empty_string"]
    list_wrapper = namespace["workflow_string_list"]
    tasks_wrapper = namespace["normalize_goal_tasks"]
    confirmations_wrapper = namespace["normalize_goal_confirmations"]
    monkeypatch.setitem(
        read_wrapper.__globals__,
        "module_read_workflow_input_bytes",
        fake_read_workflow_input_bytes,
    )
    monkeypatch.setitem(
        parse_wrapper.__globals__,
        "module_parse_workflow_mapping",
        fake_parse_workflow_mapping,
    )
    monkeypatch.setitem(
        string_wrapper.__globals__,
        "module_non_empty_string",
        fake_non_empty_string,
    )
    monkeypatch.setitem(
        list_wrapper.__globals__,
        "module_workflow_string_list",
        fake_workflow_string_list,
    )
    monkeypatch.setitem(
        tasks_wrapper.__globals__,
        "module_normalize_goal_tasks",
        fake_normalize_goal_tasks,
    )
    monkeypatch.setitem(
        confirmations_wrapper.__globals__,
        "module_normalize_goal_confirmations",
        fake_normalize_goal_confirmations,
    )

    args = SimpleNamespace(contract_stdin=True, contract_file="ignored.yaml")
    assert (
        read_wrapper(
            args,
            stdin_attr="contract_stdin",
            file_attr="contract_file",
            required=True,
            max_bytes=32,
        )
        == b"title: delegated\n"
    )
    assert parse_wrapper(b"title: delegated\n", error_prefix="GOAL_CONTRACT") == {"parsed": True}
    assert string_wrapper(" raw ", field="GOAL_TITLE") == "delegated-string"
    assert list_wrapper([" raw "], field="GOAL_SUCCESS_CONDITIONS") == ["delegated-list"]
    assert tasks_wrapper(["task"]) == [
        {"id": "T-001", "description": "Delegated", "depends_on": []}
    ]
    assert confirmations_wrapper({"accepted": [{"id": "C-001"}]}) == {
        "required": [],
        "accepted": [{"id": "C-001"}],
    }
    assert input_calls == [(True, "ignored.yaml", True, 32, True)]
    assert parse_calls == [(b"title: delegated\n", "GOAL_CONTRACT")]
    assert string_calls == [(" raw ", "GOAL_TITLE")]
    assert list_calls == [([" raw "], "GOAL_SUCCESS_CONDITIONS")]
    assert task_calls == [(["task"], namespace["ENTRY_ID_PATTERNS"]["tasks"])]
    assert confirmation_calls == [{"accepted": [{"id": "C-001"}]}]

    def broken_contract(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise namespace["ModuleWorkflowContractError"]("BROKEN_CONTRACT")

    monkeypatch.setitem(
        parse_wrapper.__globals__,
        "module_parse_workflow_mapping",
        broken_contract,
    )
    with pytest.raises(namespace["WorkctlError"], match="BROKEN_CONTRACT"):
        parse_wrapper(b"bad", error_prefix="GOAL_CONTRACT")

    monkeypatch.setitem(read_wrapper.__globals__, "module_read_workflow_input_bytes", None)
    with pytest.raises(namespace["WorkctlError"], match="WORKFLOW_INPUT_MODULE_UNAVAILABLE"):
        read_wrapper(
            SimpleNamespace(contract_stdin=False, contract_file=None),
            stdin_attr="contract_stdin",
            file_attr="contract_file",
            required=False,
        )


def test_evidence_wrappers_delegate_to_evidence_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence wrappers centralize encoding, parsing, and validation in the module."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_evidence_wrapper_fixture")
    canonical_calls: list[object] = []
    parse_calls: list[tuple[bytes, int]] = []
    validate_calls: list[tuple[object, str, str | None, object, object, int]] = []

    def fake_canonical_evidence_bytes(payload: object) -> bytes:
        canonical_calls.append(payload)
        return b"CANONICAL\n"

    def fake_parse_evidence_bytes(content: bytes, max_bytes: int) -> dict[str, object]:
        parse_calls.append((content, max_bytes))
        return {"parsed": True}

    def fake_validate_evidence_payload(
        payload: object,
        *,
        expected_plan_id: str,
        expected_subject: str | None,
        valid_reference: object,
        sha256_pattern: object,
        max_items: int,
    ) -> None:
        validate_calls.append(
            (
                payload,
                expected_plan_id,
                expected_subject,
                valid_reference,
                sha256_pattern,
                max_items,
            )
        )

    canonical_wrapper = namespace["canonical_evidence_bytes"]
    parse_wrapper = namespace["parse_evidence_content"]
    validate_wrapper = namespace["validate_evidence_payload"]
    monkeypatch.setitem(
        canonical_wrapper.__globals__,
        "MODULE_CANONICAL_EVIDENCE_BYTES",
        fake_canonical_evidence_bytes,
    )
    monkeypatch.setitem(
        parse_wrapper.__globals__,
        "MODULE_PARSE_EVIDENCE_BYTES",
        fake_parse_evidence_bytes,
    )
    monkeypatch.setitem(
        validate_wrapper.__globals__,
        "module_evidence",
        SimpleNamespace(validate_evidence_payload=fake_validate_evidence_payload),
    )
    payload = {"schema_version": 1, "plan_id": "PLAN-20260806-001"}

    assert canonical_wrapper(payload) == b"CANONICAL\n"
    assert parse_wrapper(b"{}") == {"parsed": True}
    validate_wrapper(
        payload,
        expected_plan_id="PLAN-20260806-001",
        expected_subject="task:T-001",
    )

    assert canonical_calls == [payload]
    assert parse_calls == [(b"{}", namespace["EVIDENCE_MANIFEST_MAX_BYTES"])]
    assert validate_calls[0] == (
        payload,
        "PLAN-20260806-001",
        "task:T-001",
        namespace["valid_reference"],
        namespace["SHA256_RE"],
        namespace["EVIDENCE_MANIFEST_MAX_ITEMS"],
    )

    def broken_validate(*_args: object, **_kwargs: object) -> None:
        raise ValueError("INVALID_EVIDENCE_MANIFEST_ITEM")

    monkeypatch.setitem(
        validate_wrapper.__globals__,
        "module_evidence",
        SimpleNamespace(validate_evidence_payload=broken_validate),
    )
    with pytest.raises(namespace["WorkctlError"], match="INVALID_EVIDENCE_MANIFEST_ITEM"):
        validate_wrapper(payload, expected_plan_id="PLAN-20260806-001")

    monkeypatch.setitem(canonical_wrapper.__globals__, "MODULE_CANONICAL_EVIDENCE_BYTES", None)
    with pytest.raises(namespace["WorkctlError"], match="EVIDENCE_MODULE_UNAVAILABLE"):
        canonical_wrapper(payload)


def test_storage_wrappers_delegate_to_storage_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime event encoding and redaction fail closed if storage helpers are unavailable."""
    namespace = runpy.run_path(str(SCRIPT), run_name="workctl_storage_wrapper_fixture")
    event_calls: list[object] = []
    redact_calls: list[object] = []

    def fake_canonical_event_bytes(event: object) -> bytes:
        event_calls.append(event)
        return b"EVENT\n"

    def fake_redacted_copy(value: object) -> object:
        redact_calls.append(value)
        return {"redacted": True}

    event_wrapper = namespace["canonical_event_payload_bytes"]
    redact_wrapper = namespace["redacted_runtime_copy"]
    monkeypatch.setitem(
        event_wrapper.__globals__,
        "canonical_event_bytes",
        fake_canonical_event_bytes,
    )
    monkeypatch.setitem(redact_wrapper.__globals__, "redacted_copy", fake_redacted_copy)
    event = {"event": "task.verified"}
    payload = {"note": "secret"}

    assert event_wrapper(event) == b"EVENT\n"
    assert redact_wrapper(payload) == {"redacted": True}
    assert event_calls == [event]
    assert redact_calls == [payload]

    monkeypatch.setitem(event_wrapper.__globals__, "canonical_event_bytes", None)
    with pytest.raises(namespace["WorkctlError"], match="STORAGE_MODULE_UNAVAILABLE"):
        event_wrapper(event)
    monkeypatch.setitem(redact_wrapper.__globals__, "redacted_copy", None)
    with pytest.raises(namespace["WorkctlError"], match="STORAGE_MODULE_UNAVAILABLE"):
        redact_wrapper(payload)


def test_schema_v4_admission_rejects_unclassified_pending_gate(tmp_path: Path) -> None:
    """New authority cannot introduce a generic pending continuation gate."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-105")
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-CONTINUE",
            "description": "Generic continuation request.",
            "status": "pending",
        }
    )
    run_workctl(tmp_path, "layout", "migrate")
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, frontmatter, "# Invalid generic gate\n")
    manifest = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260731-105",
        "prepared_plan": prepared.name,
        "plan_id": frontmatter["plan_id"],
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    manifest_path = tmp_path / "admission.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    rejected = run_workctl(
        tmp_path,
        "plan",
        "admit",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )

    assert "INTERVENTION_CONTRACT_LEGACY_CLASSIFICATION_REQUIRED" in rejected.stderr


def test_accepted_bootstrap_placeholder_classifies_only_matching_decision_digest(
    tmp_path: Path,
) -> None:
    """Post-install migration can tighten an already exact old-controller decision."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-106")
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-LIVE",
            "description": "Old-controller exact live decision.",
            "status": "accepted",
            "ref": "user:live-switch",
            "accepted_at": "2026-07-31T10:00:00+00:00",
            "evidence_sha256": "a" * 64,
            "intervention": {
                "kind": "external_authority",
                "blocks": ["task:T-001", "activation", "route"],
                "basis_ref": "evidence:pending-exact-live-basis",
            },
        }
    )
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-106",
    )
    classification = {
        "schema_version": 1,
        "kind": "confirmation-intervention-classification",
        "plan_id": plan_id,
        "confirmation_id": "C-LIVE",
        "intervention": {
            "kind": "external_authority",
            "blocks": ["task:T-001", "activation", "route"],
            "basis_ref": "evidence:exact-live-basis",
            "basis_sha256": "b" * 64,
        },
    }
    path = tmp_path / "classification.yaml"
    path.write_text(yaml.safe_dump(classification, sort_keys=False), encoding="utf-8")
    mismatch = run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "classify",
        "--manifest",
        str(path),
        "--expected-revision",
        "1",
        check=False,
    )
    cast(dict[str, Any], classification["intervention"])["basis_sha256"] = "a" * 64
    path.write_text(yaml.safe_dump(classification, sort_keys=False), encoding="utf-8")
    run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "classify",
        "--manifest",
        str(path),
        "--expected-revision",
        "1",
    )
    updated, _ = read_plan_by_id(tmp_path, plan_id)
    live = next(item for item in updated["confirmations"]["required"] if item["id"] == "C-LIVE")

    assert "ACCEPTED_PLACEHOLDER_BASIS_MISMATCH" in mismatch.stderr
    assert live["status"] == "accepted"
    assert live["intervention"]["basis_sha256"] == "a" * 64


def test_pending_strict_external_gate_rebinds_only_exact_basis(
    tmp_path: Path,
) -> None:
    """A pre-candidate gate may update its basis without changing its authority."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-107")
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-LIVE",
            "description": "Authorize only the immutable live candidate.",
            "status": "pending",
            "intervention": {
                "kind": "external_authority",
                "blocks": ["task:T-001", "activation", "route"],
                "basis_ref": "evidence:preliminary-live-basis",
                "basis_sha256": "a" * 64,
            },
        }
    )
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-107",
    )
    classification = {
        "schema_version": 1,
        "kind": "confirmation-intervention-classification",
        "plan_id": plan_id,
        "confirmation_id": "C-LIVE",
        "supersedes_basis_sha256": "c" * 64,
        "intervention": {
            "kind": "external_authority",
            "blocks": ["task:T-001", "activation", "route"],
            "basis_ref": "evidence:exact-live-basis",
            "basis_sha256": "b" * 64,
        },
    }
    path = tmp_path / "classification.yaml"
    path.write_text(yaml.safe_dump(classification, sort_keys=False), encoding="utf-8")
    mismatch = run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "classify",
        "--manifest",
        str(path),
        "--expected-revision",
        "1",
        check=False,
    )
    classification["supersedes_basis_sha256"] = "a" * 64
    path.write_text(yaml.safe_dump(classification, sort_keys=False), encoding="utf-8")
    rebound = run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "classify",
        "--manifest",
        str(path),
        "--expected-revision",
        "1",
    )
    updated, _ = read_plan_by_id(tmp_path, plan_id)
    live = next(item for item in updated["confirmations"]["required"] if item["id"] == "C-LIVE")

    assert "CONFIRMATION_STRICT_REBIND_MISMATCH" in mismatch.stderr
    assert "CONFIRMATION_REBOUND C-LIVE revision=2" in rebound.stdout
    assert live["status"] == "pending"
    assert live["intervention"]["basis_ref"] == "evidence:exact-live-basis"
    assert live["intervention"]["basis_sha256"] == "b" * 64


def test_pending_strict_gate_rebind_cannot_change_protected_targets(
    tmp_path: Path,
) -> None:
    """Basis refresh never widens or narrows the decision's blocked targets."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-108")
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-LIVE",
            "description": "Authorize only the immutable live candidate.",
            "status": "pending",
            "intervention": {
                "kind": "external_authority",
                "blocks": ["task:T-001", "activation", "route"],
                "basis_ref": "evidence:preliminary-live-basis",
                "basis_sha256": "a" * 64,
            },
        }
    )
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-108",
    )
    classification = {
        "schema_version": 1,
        "kind": "confirmation-intervention-classification",
        "plan_id": plan_id,
        "confirmation_id": "C-LIVE",
        "supersedes_basis_sha256": "a" * 64,
        "intervention": {
            "kind": "external_authority",
            "blocks": ["activation", "route"],
            "basis_ref": "evidence:exact-live-basis",
            "basis_sha256": "b" * 64,
        },
    }
    path = tmp_path / "classification.yaml"
    path.write_text(yaml.safe_dump(classification, sort_keys=False), encoding="utf-8")

    rejected = run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "classify",
        "--manifest",
        str(path),
        "--expected-revision",
        "1",
        check=False,
    )

    assert "CONFIRMATION_STRICT_REBIND_MISMATCH" in rejected.stderr


def independent_validation_fixture() -> dict[str, Any]:
    """Build three pending review modes with only artifact_review blocking T-001."""
    pending_route_review = {
        "state": "pending",
        "blocks": ["route"],
        "review_context_ref": "context:pending-review",
        "reviewed_contract_sha256": None,
        "reviewed_artifacts": [],
        "findings": [],
        "evidence_ref": "project:pending-independent-review",
        "evidence_sha256": None,
    }
    return {
        "required": True,
        "state": "pending",
        "required_modes": ["plan_challenge", "artifact_review", "evidence_audit"],
        "implementation_context_ref": "context:implementation",
        "reviews": [
            {"mode": "plan_challenge", **pending_route_review},
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
                **{
                    **pending_route_review,
                    "review_context_ref": "context:pending-evidence-audit",
                    "evidence_ref": "project:pending-evidence-audit",
                },
            },
        ],
    }


def local_task_plan_challenge_fixture(plan_id: str) -> dict[str, Any]:
    """Build a Plan whose only task blocker is one pending Plan challenge."""
    frontmatter = schema_v4_admission_plan(plan_id)
    contract = independent_validation_fixture()
    reviews = cast(list[dict[str, Any]], contract["reviews"])
    reviews[0]["blocks"] = ["task:T-001", "delivery", "activation", "route"]
    reviews[1]["blocks"] = ["activation", "route"]
    frontmatter["independent_validation"] = contract
    return frontmatter


def test_pending_plan_challenge_is_advisory_for_ordinary_local_task(
    tmp_path: Path,
) -> None:
    """Unavailable Plan challenge must not stall reversible local implementation."""
    frontmatter = local_task_plan_challenge_fixture("PLAN-20260801-101")
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260801-101",
    )

    started = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "1",
    )
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)

    assert "TASK_UPDATED T-001 in_progress" in started.stdout
    assert status["plan_id"] == plan_id
    assert any(
        blocker == "independent review blocks route: plan_challenge"
        for blocker in status["closeout_readiness"]["blockers"]
    )


def test_irp_stocklens_review_shape_can_start_t002_without_replanning(
    tmp_path: Path,
) -> None:
    """The observed rev-24 target shape resumes T-002 under advisory challenge."""
    frontmatter = schema_v4_admission_plan("PLAN-20260801-105")
    frontmatter["title"] = "Stock verification workbench target-shaped fixture"
    frontmatter["tasks"] = [
        {
            "id": "T-001",
            "description": "Fix the verified target baseline.",
            "status": "verified",
            "depends_on": [],
            "unknowns": [],
            "expected_evidence_delta": "The target baseline is fixed.",
        },
        {
            "id": "T-002",
            "description": "Write versioned product and API truth.",
            "status": "pending",
            "depends_on": ["T-001"],
            "unknowns": [],
            "expected_evidence_delta": "Versioned product truth is reviewable.",
        },
    ]
    contract = independent_validation_fixture()
    reviews = cast(list[dict[str, Any]], contract["reviews"])
    reviews[0]["blocks"] = ["task:T-002", "delivery", "route"]
    reviews[1]["blocks"] = ["delivery", "route"]
    frontmatter["independent_validation"] = contract
    admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260801-105",
    )

    started = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-002",
        "--expected-revision",
        "1",
    )

    assert "TASK_UPDATED T-002 in_progress" in started.stdout


@pytest.mark.parametrize("protected_kind", ["route", "confirmation"])
def test_pending_plan_challenge_still_blocks_protected_tasks(
    tmp_path: Path,
    protected_kind: str,
) -> None:
    """Route-scoped and confirmation-gated work never use the advisory release."""
    plan_suffix = "102" if protected_kind == "route" else "103"
    frontmatter = local_task_plan_challenge_fixture(f"PLAN-20260801-{plan_suffix}")
    task = cast(list[dict[str, Any]], frontmatter["tasks"])[0]
    if protected_kind == "route":
        task["completion_scope"] = "route"
    else:
        task["requires_confirmation"] = "C-ADMISSION"
    admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id=f"ADM-20260801-{plan_suffix}",
    )

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

    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked.stderr


def test_pending_plan_challenge_high_finding_still_blocks_local_task(
    tmp_path: Path,
) -> None:
    """A concrete high finding is stronger than reviewer-availability fallback."""
    frontmatter = local_task_plan_challenge_fixture("PLAN-20260801-104")
    reviews = cast(
        list[dict[str, Any]],
        cast(dict[str, Any], frontmatter["independent_validation"])["reviews"],
    )
    reviews[0]["findings"] = [
        {
            "id": "F-HIGH",
            "severity": "high",
            "status": "open",
            "description": "The local task can violate the confirmed contract.",
        }
    ]
    admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260801-104",
    )

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

    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked.stderr


def record_review_evidence(
    cwd: Path,
    plan_id: str,
    *,
    producer_ref: str = "context:implementation",
    subject: str = "independent-review:artifact_review",
) -> dict[str, Any]:
    """Install canonical evidence binding the reviewed contract and artifact digests."""
    evidence = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": subject,
        "created_at": "2026-07-31T10:00:00+00:00",
        "producer_ref": producer_ref,
        "items": [
            {"ref": "project:reviewed-contract", "sha256": "a" * 64},
            {"ref": "git:candidate-commit", "sha256": "b" * 64},
        ],
    }
    path = cwd / "review-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return cast(
        dict[str, Any],
        json.loads(
            run_workctl(
                cwd,
                "plan",
                "evidence",
                "record",
                "--manifest",
                str(path),
            ).stdout
        ),
    )


def review_record_manifest(
    plan_id: str,
    evidence_path: str,
    *,
    state: str,
    review_context_ref: str,
    findings: list[dict[str, Any]] | None = None,
    risk_confirmation_id: str | None = None,
    isolation_attestation: str | None = None,
) -> dict[str, Any]:
    """Build one strict artifact-review manifest."""
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "independent-review",
        "plan_id": plan_id,
        "mode": "artifact_review",
        "state": state,
        "implementation_context_ref": "context:implementation",
        "review_context_ref": review_context_ref,
        "reviewed_contract": {
            "ref": "project:reviewed-contract",
            "sha256": "a" * 64,
        },
        "reviewed_artifacts": [{"ref": "git:candidate-commit", "sha256": "b" * 64}],
        "findings": findings or [],
        "evidence_manifest": evidence_path,
        "isolation_attestation": isolation_attestation,
        "bootstrap_evidence": [],
    }
    if risk_confirmation_id is not None:
        manifest["risk_acceptance_confirmation_id"] = risk_confirmation_id
    return manifest


def record_isolation_attestation(
    cwd: Path,
    plan_id: str,
    *,
    implementation_context_ref: str,
    review_context_ref: str,
    review_evidence_ref: str,
    review_evidence_sha256: str,
    producer_ref: str = "runtime:codex-collaboration",
) -> dict[str, Any]:
    """Install canonical collaboration evidence binding both contexts and review bytes."""
    evidence = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "isolation-attestation:artifact_review",
        "created_at": "2026-07-31T10:01:00+00:00",
        "producer_ref": producer_ref,
        "items": [
            {
                "ref": implementation_context_ref,
                "sha256": hashlib.sha256(implementation_context_ref.encode()).hexdigest(),
            },
            {
                "ref": review_context_ref,
                "sha256": hashlib.sha256(review_context_ref.encode()).hexdigest(),
            },
            {
                "ref": review_evidence_ref,
                "sha256": review_evidence_sha256,
            },
        ],
    }
    path = cwd / "isolation-attestation.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return cast(
        dict[str, Any],
        json.loads(
            run_workctl(
                cwd,
                "plan",
                "evidence",
                "record",
                "--manifest",
                str(path),
            ).stdout
        ),
    )


def test_same_context_review_can_only_record_degraded_and_remains_blocking(
    tmp_path: Path,
) -> None:
    """A same-context self-review cannot satisfy a high-impact advancement gate."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-103")
    frontmatter["independent_validation"] = independent_validation_fixture()
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-103",
    )
    evidence = record_review_evidence(tmp_path, plan_id)
    manifest_path = tmp_path / "review.yaml"
    verified = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="verified",
        review_context_ref="context:implementation",
    )
    manifest_path.write_text(yaml.safe_dump(verified, sort_keys=False), encoding="utf-8")
    rejected = run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
        check=False,
    )
    degraded = {
        **verified,
        "state": "degraded",
        "risk_acceptance_confirmation_id": "C-SAME-CONTEXT-RISK",
    }
    manifest_path.write_text(yaml.safe_dump(degraded, sort_keys=False), encoding="utf-8")
    run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
    )
    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "2",
        check=False,
    )
    status = json.loads(run_workctl(tmp_path, "plan", "status", "--full").stdout)

    assert "INDEPENDENT_REVIEW_CONTEXT_NOT_ISOLATED" in rejected.stderr
    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked.stderr
    assert status["independent_validation"]["state"] == "pending"
    assert any(
        blocker == "independent review blocks route: artifact_review"
        for blocker in status["closeout_readiness"]["blockers"]
    )


def test_degraded_review_requires_a_reserved_risk_confirmation_id(
    tmp_path: Path,
) -> None:
    """A degraded record cannot rely on later global confirmation discovery."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-112")
    frontmatter["independent_validation"] = independent_validation_fixture()
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-112",
    )
    evidence = record_review_evidence(tmp_path, plan_id)
    manifest = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="degraded",
        review_context_ref="context:implementation",
    )
    manifest_path = tmp_path / "review.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    rejected = run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
        check=False,
    )

    assert "DEGRADED_REVIEW_RISK_CONFIRMATION_ID_REQUIRED" in rejected.stderr


@pytest.mark.parametrize("preexisting_status", ["pending", "accepted"])
def test_preexisting_confirmation_cannot_be_adopted_by_degraded_review(
    tmp_path: Path,
    preexisting_status: str,
) -> None:
    """A new authority cannot preload a gate for a future degraded review."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-113")
    frontmatter["independent_validation"] = independent_validation_fixture()
    preexisting = {
        "id": "C-PREEXISTING-REVIEW-RISK",
        "description": "Preload risk authority before review evidence exists.",
        "status": preexisting_status,
        "intervention": {
            "kind": "external_authority",
            "blocks": ["task:T-001", "activation", "route"],
            "basis_ref": "evidence:precomputed-degraded-review",
            "basis_sha256": "c" * 64,
        },
    }
    if preexisting_status == "accepted":
        preexisting["ref"] = "user:preloaded-review-risk"
        preexisting["accepted_at"] = "2026-07-31T10:00:00+00:00"
    cast(list[dict[str, Any]], frontmatter["confirmations"]["required"]).append(preexisting)
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-113",
    )
    evidence = record_review_evidence(tmp_path, plan_id)
    manifest = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="degraded",
        review_context_ref="context:implementation",
        risk_confirmation_id="C-PREEXISTING-REVIEW-RISK",
    )
    manifest_path = tmp_path / "review.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    rejected = run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
        check=False,
    )
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

    assert "DEGRADED_REVIEW_PREEXISTING_RISK_FORBIDDEN" in rejected.stderr
    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked.stderr


def test_distinct_context_labels_without_platform_attestation_cannot_verify(
    tmp_path: Path,
) -> None:
    """Different free-form labels alone cannot certify an isolated review."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-105")
    frontmatter["independent_validation"] = independent_validation_fixture()
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-105",
    )
    review_context = "context:isolated-artifact-review"
    evidence = record_review_evidence(
        tmp_path,
        plan_id,
        producer_ref=review_context,
    )
    manifest = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="verified",
        review_context_ref=review_context,
    )
    manifest_path = tmp_path / "review.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    rejected = run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
        check=False,
    )

    assert "INDEPENDENT_REVIEW_TRUSTED_ATTESTATION_UNAVAILABLE" in rejected.stderr


def test_caller_controlled_canonical_attestation_cannot_verify_review(
    tmp_path: Path,
) -> None:
    """Public evidence canonicalization cannot authenticate a platform attestor."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-106")
    frontmatter["independent_validation"] = independent_validation_fixture()
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-106",
    )
    review_context = "context:isolated-artifact-review"
    evidence = record_review_evidence(
        tmp_path,
        plan_id,
        producer_ref=review_context,
    )
    evidence_ref = f"evidence:{evidence['path']}"
    attestation = record_isolation_attestation(
        tmp_path,
        plan_id,
        implementation_context_ref="context:implementation",
        review_context_ref=review_context,
        review_evidence_ref=evidence_ref,
        review_evidence_sha256=str(evidence["sha256"]),
    )
    manifest = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="verified",
        review_context_ref=review_context,
        isolation_attestation=str(attestation["path"]),
    )
    manifest_path = tmp_path / "review.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    rejected = run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
        check=False,
    )

    assert "INDEPENDENT_REVIEW_TRUSTED_ATTESTATION_UNAVAILABLE" in rejected.stderr


def test_review_release_revalidates_canonical_evidence_bytes(
    tmp_path: Path,
) -> None:
    """Evidence drift restores the block even after exact degraded-risk acceptance."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-111")
    frontmatter["independent_validation"] = independent_validation_fixture()
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-111",
    )
    evidence = record_review_evidence(tmp_path, plan_id)
    manifest = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="degraded",
        review_context_ref="context:implementation",
        risk_confirmation_id="C-TAMPERED-REVIEW-RISK",
    )
    manifest_path = tmp_path / "review.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
    )
    run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "add",
        "--confirmation-id",
        "C-TAMPERED-REVIEW-RISK",
        "--description",
        "Accept the exact degraded review risk.",
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
        str(evidence["sha256"]),
        "--expected-revision",
        "2",
    )
    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-TAMPERED-REVIEW-RISK",
        "--ref",
        "user:tampered-review-risk",
        "--evidence-sha256",
        str(evidence["sha256"]),
        "--expected-revision",
        "3",
    )
    stored = tmp_path / str(evidence["path"])
    stored.write_bytes(stored.read_bytes() + b" ")

    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "4",
        check=False,
    )

    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked.stderr


def test_review_evidence_producer_must_equal_the_declared_review_context(
    tmp_path: Path,
) -> None:
    """A context label cannot claim review evidence produced by another context."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-107")
    frontmatter["independent_validation"] = independent_validation_fixture()
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-107",
    )
    evidence = record_review_evidence(
        tmp_path,
        plan_id,
        producer_ref="context:unrelated-producer",
    )
    manifest = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="degraded",
        review_context_ref="context:isolated-artifact-review",
        risk_confirmation_id="C-PRODUCER-RISK",
    )
    manifest_path = tmp_path / "review.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    rejected = run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
        check=False,
    )

    assert "INDEPENDENT_REVIEW_PRODUCER_CONTEXT_MISMATCH" in rejected.stderr


def test_schema_v4_admission_rejects_preloaded_verified_review(
    tmp_path: Path,
) -> None:
    """A new authority cannot arrive with a self-certified review already released."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260731-108"
    frontmatter = schema_v4_admission_plan(plan_id)
    contract = independent_validation_fixture()
    artifact_review = next(
        review for review in contract["reviews"] if review["mode"] == "artifact_review"
    )
    artifact_review.update(
        {
            "state": "verified",
            "review_context_ref": "context:preloaded-review",
            "reviewed_contract_ref": "project:reviewed-contract",
            "reviewed_contract_sha256": "a" * 64,
            "reviewed_artifacts": [{"ref": "git:candidate", "sha256": "b" * 64}],
            "evidence_ref": "evidence:preloaded-review",
            "evidence_sha256": "c" * 64,
            "isolation_attestation_ref": "evidence:preloaded-isolation",
            "isolation_attestation_sha256": "d" * 64,
        }
    )
    frontmatter["independent_validation"] = contract
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, frontmatter, "# Preloaded review\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260731-108",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = tmp_path / "admission.yaml"
    admission_path.write_text(yaml.safe_dump(admission, sort_keys=False), encoding="utf-8")

    rejected = run_workctl(
        tmp_path,
        "plan",
        "admit",
        "apply",
        "--manifest",
        str(admission_path),
        check=False,
    )

    assert "verified requires an authenticated platform attestor" in rejected.stderr


def test_bootstrap_release_rejects_canonical_evidence_for_the_wrong_subject(
    tmp_path: Path,
) -> None:
    """Bootstrap evidence must prove the mapped entry rather than a nearby fact."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-109")
    contract = independent_validation_fixture()
    artifact_review = next(
        review for review in contract["reviews"] if review["mode"] == "artifact_review"
    )
    artifact_review["bootstrap_release"] = {
        "controller_build": "plugin:test-build",
        "evidence_mapping": ["validation:V-001"],
        "releases": ["task:T-001"],
    }
    frontmatter["independent_validation"] = contract
    cast(dict[str, Any], frontmatter["activation"])["current_ref"] = "plugin:test-build"
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-109",
    )
    wrong_subject = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "task:T-001",
        "created_at": "2026-07-31T10:02:00+00:00",
        "producer_ref": "runtime:bootstrap-probe",
        "items": [{"ref": "project:nearby-result", "sha256": "e" * 64}],
    }
    evidence_path = tmp_path / "wrong-bootstrap-subject.json"
    evidence_path.write_text(json.dumps(wrong_subject), encoding="utf-8")
    evidence = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(evidence_path),
        ).stdout
    )
    current, body = read_plan_by_id(tmp_path, plan_id)
    validation = cast(list[dict[str, Any]], current["validations"])[0]
    validation["status"] = "verified"
    validation["evidence_ref"] = f"evidence:{evidence['path']}"
    validation["evidence_sha256"] = str(evidence["sha256"])
    write_markdown_plan(
        tmp_path / ".work-governance" / "_Plan" / f"{plan_id}.md",
        current,
        body,
    )

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

    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked.stderr


def test_degraded_review_needs_exact_risk_acceptance_and_open_high_still_blocks(
    tmp_path: Path,
) -> None:
    """Exact risk acceptance releases degradation but never an unresolved high finding."""
    frontmatter = schema_v4_admission_plan("PLAN-20260731-104")
    frontmatter["independent_validation"] = independent_validation_fixture()
    plan_id = admit_schema_v4_test_plan(
        tmp_path,
        frontmatter,
        transaction_id="ADM-20260731-104",
    )
    evidence = record_review_evidence(tmp_path, plan_id)
    manifest = review_record_manifest(
        plan_id,
        str(evidence["path"]),
        state="degraded",
        review_context_ref="context:implementation",
        risk_confirmation_id="C-REVIEW-RISK",
        findings=[
            {
                "id": "F-001",
                "severity": "high",
                "status": "open",
                "description": "The audited artifact remains unsafe.",
            }
        ],
    )
    manifest_path = tmp_path / "review.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    run_workctl(
        tmp_path,
        "plan",
        "independent-review",
        "record",
        "--manifest",
        str(manifest_path),
        "--expected-revision",
        "1",
    )
    fabricated = run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "add",
        "--confirmation-id",
        "C-REVIEW-RISK",
        "--description",
        "Accept the exact degraded review risk.",
        "--status",
        "accepted",
        "--ref",
        "user:review-risk",
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
        str(evidence["sha256"]),
        "--expected-revision",
        "2",
        check=False,
    )
    run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "add",
        "--confirmation-id",
        "C-REVIEW-RISK",
        "--description",
        "Accept the exact degraded review risk.",
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
        str(evidence["sha256"]),
        "--expected-revision",
        "2",
    )
    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-REVIEW-RISK",
        "--ref",
        "user:review-risk",
        "--evidence-sha256",
        str(evidence["sha256"]),
        "--expected-revision",
        "3",
    )
    blocked = run_workctl(
        tmp_path,
        "task",
        "start",
        "--task-id",
        "T-001",
        "--expected-revision",
        "4",
        check=False,
    )

    assert "CONFIRMATION_ACCEPTED_REQUIRES_PLAN_CONFIRM" in fabricated.stderr
    assert "INDEPENDENT_REVIEW_REQUIRED" in blocked.stderr


def test_evidence_subject_and_hash_are_verified_before_terminal_transition(
    tmp_path: Path,
) -> None:
    """A stored path is insufficient when its subject or immutable bytes disagree."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-001"
    frontmatter = schema_v4_admission_plan(plan_id)
    frontmatter["obligations"] = [
        {"id": "O-001", "description": "Verify exact evidence.", "status": "pending"}
    ]
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, frontmatter, "# Exact Evidence\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-004",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = tmp_path / "admission.yaml"
    admission_path.write_text(yaml.safe_dump(admission, sort_keys=False), encoding="utf-8")
    run_workctl(tmp_path, "plan", "admit", "apply", "--manifest", str(admission_path))
    wrong_subject = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "validation:V-001",
        "created_at": "2026-07-28T10:03:00+00:00",
        "producer_ref": "runtime:wrong-subject-probe",
        "items": [{"ref": "project:result.txt", "sha256": "c" * 64}],
    }
    evidence_input = tmp_path / "evidence.json"
    evidence_input.write_text(json.dumps(wrong_subject), encoding="utf-8")
    recorded = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(evidence_input),
        ).stdout
    )
    subject_blocked = run_workctl(
        tmp_path,
        "plan",
        "verify-entry",
        "--field",
        "obligations",
        "--entry-id",
        "O-001",
        "--confirmation",
        "C-ADMISSION",
        "--evidence-manifest",
        recorded["path"],
        "--expected-revision",
        "1",
        check=False,
    )
    assert "EVIDENCE_MANIFEST_SUBJECT_MISMATCH" in subject_blocked.stderr

    stored = tmp_path / recorded["path"]
    stored.write_bytes(stored.read_bytes() + b" ")
    hash_blocked = run_workctl(
        tmp_path,
        "plan",
        "validate",
        "--evidence-manifest",
        recorded["path"],
        check=False,
    )
    assert "EVIDENCE_MANIFEST_HASH_MISMATCH" in hash_blocked.stderr


def test_unknown_resolution_and_plan_adaptation_preserve_confirmed_goal(
    tmp_path: Path,
) -> None:
    """Evidence can change the execution path without silently changing the goal."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-001"
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, schema_v4_admission_plan(plan_id), "# Adaptable Plan\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-005",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = tmp_path / "admission.yaml"
    admission_path.write_text(yaml.safe_dump(admission, sort_keys=False), encoding="utf-8")
    run_workctl(tmp_path, "plan", "admit", "apply", "--manifest", str(admission_path))
    original, _ = read_plan_by_id(tmp_path, plan_id)

    run_workctl(
        tmp_path,
        "plan",
        "unknown",
        "add",
        "--unknown-id",
        "U-001",
        "--question",
        "Which runtime path is authoritative?",
        "--owner",
        "agent",
        "--impact",
        "non_blocking",
        "--expected-evidence",
        "A receipt-bound controller path.",
        "--expected-revision",
        "1",
    )
    unknown_evidence = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "unknown:U-001",
        "created_at": "2026-07-28T10:04:00+00:00",
        "producer_ref": "runtime:receipt-path-probe",
        "items": [{"ref": "runtime:bootstrap-state", "sha256": "d" * 64}],
    }
    unknown_input = tmp_path / "unknown-evidence.json"
    unknown_input.write_text(json.dumps(unknown_evidence), encoding="utf-8")
    unknown_record = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(unknown_input),
        ).stdout
    )
    run_workctl(
        tmp_path,
        "plan",
        "unknown",
        "resolve",
        "--unknown-id",
        "U-001",
        "--resolution",
        "Use the receipt-bound runtime bundle.",
        "--evidence-manifest",
        unknown_record["path"],
        "--expected-revision",
        "2",
    )
    adaptation_evidence = {
        "schema_version": 1,
        "kind": "work-governance-evidence",
        "plan_id": plan_id,
        "subject": "adaptation:4",
        "created_at": "2026-07-28T10:05:00+00:00",
        "producer_ref": "runtime:adaptation-probe",
        "items": [{"ref": "runtime:bootstrap-state", "sha256": "e" * 64}],
    }
    adaptation_input = tmp_path / "adaptation-evidence.json"
    adaptation_input.write_text(json.dumps(adaptation_evidence), encoding="utf-8")
    adaptation_record = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(adaptation_input),
        ).stdout
    )
    adaptation = {
        "schema_version": 1,
        "kind": "plan-adaptation",
        "plan_id": plan_id,
        "expected_revision": 3,
        "confirmation_id": "C-ADMISSION",
        "rationale": "The runtime receipt resolved U-001 and changes the next probe.",
        "evidence_manifest": adaptation_record["path"],
        "changes": {
            "route": {
                "route_status": "active",
                "slice_status": "unknown-resolved",
                "next_phase": "Exercise the receipt-bound controller.",
                "validation_standard": "The exact receipt hash authorizes the command.",
                "confirmation_gate": "none",
            },
            "handoff": {
                "route_status": "active",
                "next_step": "Exercise the receipt-bound controller.",
            },
        },
    }
    adaptation_path = tmp_path / "adaptation.yaml"
    adaptation_path.write_text(yaml.safe_dump(adaptation, sort_keys=False), encoding="utf-8")

    run_workctl(tmp_path, "plan", "adapt", "--manifest", str(adaptation_path))
    revised, _ = read_plan_by_id(tmp_path, plan_id)

    assert revised["goal"] == original["goal"]
    assert revised["contract"] == original["contract"]
    assert revised["unknowns"][0]["status"] == "resolved"
    assert revised["revision_history"][-1]["kind"] == "adaptation"


def test_schema_v4_contract_revision_is_confirmation_and_evidence_bound(
    tmp_path: Path,
) -> None:
    """A goal change records a distinct contract revision and immutable evidence."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-006"
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, schema_v4_admission_plan(plan_id), "# Revisable Plan\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-006",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = tmp_path / "admission.yaml"
    admission_path.write_text(yaml.safe_dump(admission, sort_keys=False), encoding="utf-8")
    run_workctl(tmp_path, "plan", "admit", "apply", "--manifest", str(admission_path))
    run_workctl(
        tmp_path,
        "plan",
        "confirmation",
        "add",
        "--confirmation-id",
        "C-CONTRACT",
        "--description",
        "Approve the revised goal.",
        "--intervention-kind",
        "plan_contract",
        "--blocks",
        "route",
        "--basis-ref",
        "user:revised-goal",
        "--basis-sha256",
        "f" * 64,
        "--expected-revision",
        "1",
    )
    run_workctl(
        tmp_path,
        "plan",
        "confirm",
        "--confirmation-id",
        "C-CONTRACT",
        "--ref",
        "user:revised-goal",
        "--evidence-sha256",
        "f" * 64,
        "--expected-revision",
        "2",
    )
    evidence_input = tmp_path / "contract-evidence.json"
    evidence_input.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "work-governance-evidence",
                "plan_id": plan_id,
                "subject": "contract-revision:2",
                "created_at": "2026-07-28T10:06:00+00:00",
                "producer_ref": "user:revised-goal",
                "items": [{"ref": "project:confirmed-goal", "sha256": "f" * 64}],
            }
        ),
        encoding="utf-8",
    )
    recorded = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "evidence",
            "record",
            "--manifest",
            str(evidence_input),
        ).stdout
    )
    revision_manifest = {
        "schema_version": 1,
        "kind": "plan-contract-revision",
        "plan_id": plan_id,
        "expected_revision": 3,
        "confirmation_id": "C-CONTRACT",
        "rationale": "Align the contract with the confirmed user-visible result.",
        "evidence_manifest": recorded["path"],
        "changes": {
            "goal": {
                "statement": "Deliver the confirmed revised result.",
                "success_conditions": ["The revised result is directly verified."],
            }
        },
    }
    revision_path = tmp_path / "contract-revision.yaml"
    revision_path.write_text(
        yaml.safe_dump(revision_manifest, sort_keys=False),
        encoding="utf-8",
    )

    run_workctl(
        tmp_path,
        "plan",
        "contract",
        "revise",
        "--manifest",
        str(revision_path),
    )
    revised, _ = read_plan_by_id(tmp_path, plan_id)

    assert revised["revision"] == 4
    assert revised["contract"] == {
        "revision": 2,
        "confirmation_id": "C-CONTRACT",
        "confirmed_ref": "user:revised-goal",
    }
    assert revised["goal"]["statement"] == "Deliver the confirmed revised result."
    assert revised["revision_history"][-1]["kind"] == "contract-revision"


def test_schema_v4_closeout_keeps_delivery_and_exclusion_gates(
    tmp_path: Path,
) -> None:
    """The new contract must retain the route gates inherited from schema v3."""
    run_workctl(tmp_path, "layout", "migrate")
    plan_id = "PLAN-20260728-007"
    frontmatter = schema_v4_admission_plan(plan_id)
    prepared = tmp_path / "candidate.md"
    write_markdown_plan(prepared, frontmatter, "# Gated Closeout\n")
    admission = {
        "schema_version": 1,
        "kind": "plan-admission",
        "transaction_id": "ADM-20260728-007",
        "prepared_plan": prepared.name,
        "plan_id": plan_id,
        "plan_sha256": sha256_path(prepared),
        "confirmation_id": "C-ADMISSION",
        "confirmation_ref": "user:observed-admission",
    }
    admission_path = tmp_path / "admission.yaml"
    admission_path.write_text(yaml.safe_dump(admission, sort_keys=False), encoding="utf-8")
    run_workctl(tmp_path, "plan", "admit", "apply", "--manifest", str(admission_path))
    active, body = read_plan_by_id(tmp_path, plan_id)
    active["tasks"][0]["status"] = "verified"
    active["validations"][0]["status"] = "verified"
    active["scope"]["exclude"] = [
        {"description": "Await a required future route.", "disposition": "deferred"}
    ]
    active["route"] = {
        "route_status": "terminal",
        "slice_status": "complete",
        "next_phase": "none",
        "validation_standard": "Current evidence is complete.",
        "confirmation_gate": "none",
    }
    active["handoff"] = {"route_status": "terminal", "next_step": "none"}
    write_markdown_plan(
        tmp_path / ".work-governance" / "_Plan" / f"{plan_id}.md",
        active,
        body,
    )

    result = run_workctl(tmp_path, "plan", "closeout-check", check=False)
    blockers = json.loads(result.stdout)["blockers"]

    assert result.returncode == 1
    assert "delivery is not complete" in blockers
    assert any("scope exclusion is unresolved" in blocker for blocker in blockers)


def write_structural_rebase_fixture(cwd: Path) -> Path:
    """Create a governed v4 Plan with pending gates and review mappings to rebase."""
    init_plan(cwd)
    frontmatter = schema_v4_admission_plan("PLAN-20260723-001")
    frontmatter["confirmations"]["required"].append(
        {
            "id": "C-GOAL-3",
            "description": "Authorize goal 3 after goals 1 and 2.",
            "status": "pending",
            "intervention": {
                "kind": "plan_contract",
                "blocks": ["task:T-001", "route"],
                "basis_ref": "evidence:pending-goals-1-2",
                "basis_sha256": "0" * 64,
            },
        }
    )
    reviews = []
    for mode in ("plan_challenge", "artifact_review", "evidence_audit"):
        reviews.append(
            {
                "mode": mode,
                "state": "pending",
                "blocks": ["task:T-001", "delivery", "route"],
                "review_context_ref": f"runtime:pending-{mode}",
                "reviewed_contract_ref": None,
                "reviewed_contract_sha256": None,
                "reviewed_artifacts": [],
                "findings": [],
                "evidence_ref": f"evidence:pending-{mode}",
                "evidence_sha256": None,
            }
        )
    frontmatter["independent_validation"] = {
        "required": True,
        "state": "pending",
        "required_modes": ["plan_challenge", "artifact_review", "evidence_audit"],
        "implementation_context_ref": "runtime:implementation",
        "reviews": reviews,
    }
    write_plan(cwd, frontmatter)
    source = plan_path(cwd)
    index = cwd / ".work-governance" / "_Plan" / "index.yaml"
    target_confirmations = yaml.safe_load(
        yaml.safe_dump(frontmatter["confirmations"], sort_keys=False)
    )
    target_goal = next(
        item for item in target_confirmations["required"] if item["id"] == "C-GOAL-3"
    )
    target_goal["description"] = "Authorize goal 3 after the baseline is active."
    target_goal["intervention"]["basis_ref"] = "evidence:pending-baseline-production"
    target_confirmations["required"].append(
        {
            "id": "C-POST-PROD-EXPANSION-ACTIVATION",
            "description": "Authorize post-production incremental activation.",
            "status": "pending",
            "intervention": {
                "kind": "external_authority",
                "blocks": ["task:T-003", "route"],
                "basis_ref": "evidence:pending-post-production-expansion",
            },
        }
    )
    target_reviews = yaml.safe_load(yaml.safe_dump(reviews, sort_keys=False))
    for review in target_reviews:
        review["blocks"] = ["task:T-002", "delivery", "route"]
    manifest = {
        "schema_version": 1,
        "kind": "plan-structural-rebase",
        "transaction_id": "SRB-20260803-001",
        "plan_id": frontmatter["plan_id"],
        "expected_revision": frontmatter["revision"],
        "plan_sha256": sha256_path(source),
        "index_sha256": sha256_path(index),
        "authorization": {
            "id": "C-PLAN-STRUCTURAL-REBASE",
            "ref": "user:confirmed-structural-rebase",
            "accepted_at": "2026-08-03T10:00:00+00:00",
            "basis_sha256": "a" * 64,
        },
        "rationale": "Split baseline activation from post-production expansion.",
        "confirmation_rebindings": ["C-GOAL-3"],
        "changes": {
            "goal": {
                "statement": "Activate a baseline before post-production goals.",
                "success_conditions": ["Baseline and expansion routes remain independently gated."],
            },
            "scope": {"include": ["Activate the baseline first."], "exclude": []},
            "obligations": [
                {"id": "O-001", "description": "Deliver the baseline.", "status": "pending"}
            ],
            "tasks": [
                frontmatter["tasks"][0],
                {
                    "id": "T-002",
                    "description": "Review the full expansion release.",
                    "status": "pending",
                    "unknowns": [],
                    "expected_evidence_delta": "The full release becomes independently reviewable.",
                },
                {
                    "id": "T-003",
                    "description": "Activate the post-production increment.",
                    "status": "pending",
                    "unknowns": [],
                    "requires_confirmation": "C-POST-PROD-EXPANSION-ACTIVATION",
                    "expected_evidence_delta": (
                        "The increment has production verification evidence."
                    ),
                },
            ],
            "validations": frontmatter["validations"],
            "route": {
                "route_status": "active",
                "slice_status": "baseline",
                "next_phase": "Execute T-001 before expansion.",
                "validation_standard": "Fresh evidence covers the baseline and expansion gates.",
                "confirmation_gate": "none",
            },
            "handoff": {"route_status": "active", "next_step": "Execute T-001."},
            "confirmations": target_confirmations,
            "independent_validation": {
                "required": True,
                "state": "pending",
                "required_modes": ["plan_challenge", "artifact_review", "evidence_audit"],
                "implementation_context_ref": "runtime:implementation",
                "reviews": target_reviews,
            },
        },
    }
    manifest_path = cwd / "structural-rebase.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def test_structural_rebase_is_stable_and_rebinds_only_pending_controls(tmp_path: Path) -> None:
    """A dry-run binds the same Plan before an atomic, review-safe rebase."""
    manifest_path = write_structural_rebase_fixture(tmp_path)
    first = json.loads(
        run_workctl(
            tmp_path,
            "plan",
            "structural-rebase",
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
            "structural-rebase",
            "apply",
            "--manifest",
            str(manifest_path),
            "--dry-run",
        ).stdout
    )
    assert first == second
    run_workctl(tmp_path, "plan", "structural-rebase", "apply", "--manifest", str(manifest_path))
    rebased, _ = read_plan(tmp_path)
    assert rebased["revision"] == 2
    assert rebased["contract"]["confirmation_id"] == "C-PLAN-STRUCTURAL-REBASE"
    assert {item["id"] for item in rebased["tasks"]} == {"T-001", "T-002", "T-003"}
    assert rebased["independent_validation"]["reviews"][0]["blocks"][0] == "task:T-002"
    assert (
        json.loads(
            (
                tmp_path
                / ".work-governance"
                / "runtime"
                / "structural-rebases"
                / "SRB-20260803-001"
                / "journal.json"
            ).read_text(encoding="utf-8")
        )["status"]
        == "committed"
    )


def test_structural_rebase_recovers_after_the_plan_replace_boundary(tmp_path: Path) -> None:
    """An interrupted Plan replacement freezes authority until named recovery commits."""
    manifest_path = write_structural_rebase_fixture(tmp_path)
    interrupted = run_workctl(
        tmp_path,
        "plan",
        "structural-rebase",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
        env={"WORKCTL_TEST_STRUCTURAL_REBASE_INTERRUPT_AFTER": "plan-replaced"},
    )
    assert interrupted.returncode == 2
    assert "STRUCTURAL_REBASE_TEST_INTERRUPTED" in interrupted.stderr
    during = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    assert during["authority_state"] == "MIGRATION_RECOVERY_REQUIRED"
    assert "plan structural-rebase recover" in during["allowed_commands"]
    run_workctl(
        tmp_path, "plan", "structural-rebase", "recover", "--transaction-id", "SRB-20260803-001"
    )
    after = json.loads(run_workctl(tmp_path, "plan", "authority", "check").stdout)
    assert after["authority_state"] == "GOVERNED_ACTIVE"


def test_structural_rebase_rejects_stale_source_before_creating_a_journal(tmp_path: Path) -> None:
    """A stale source hash fails before the rebase can publish recovery state."""
    manifest_path = write_structural_rebase_fixture(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["plan_sha256"] = "0" * 64
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    result = run_workctl(
        tmp_path,
        "plan",
        "structural-rebase",
        "apply",
        "--manifest",
        str(manifest_path),
        check=False,
    )
    assert result.returncode == 2
    assert "STRUCTURAL_REBASE_INPUT_DRIFT" in result.stderr
    assert not (tmp_path / ".work-governance" / "runtime" / "structural-rebases").exists()
