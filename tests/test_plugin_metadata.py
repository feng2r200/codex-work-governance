"""Validate plugin metadata and generated command documentation contracts."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import cast

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance"
REFERENCE = REPOSITORY_ROOT / "docs" / "CLI_REFERENCE.md"


def load_yaml_mapping(path: Path) -> Mapping[str, object]:
    """Load one metadata YAML object and reject non-mapping roots."""
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"metadata root must be a mapping: {path}")
    return cast(Mapping[str, object], value)


def test_every_skill_has_valid_openai_metadata() -> None:
    """Ensure each bundled skill exposes the required OpenAI interface fields."""
    skill_root = PLUGIN_ROOT / "skills"
    metadata_paths = sorted(skill_root.glob("*/agents/openai.yaml"))
    assert metadata_paths
    for path in metadata_paths:
        document = load_yaml_mapping(path)
        interface = document.get("interface")
        assert isinstance(interface, dict), path
        typed_interface = cast(Mapping[str, object], interface)
        for field in ("display_name", "short_description", "default_prompt"):
            value = typed_interface.get(field)
            assert isinstance(value, str) and value.strip(), (path, field)
        prompt = cast(str, typed_interface["default_prompt"])
        skill_name = path.parent.parent.name
        assert f"$work-governance:{skill_name}" in prompt


def test_plugin_manifest_describes_goal_driven_runtime() -> None:
    """Keep the plugin manifest aligned with the goal-driven public contract."""
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert isinstance(manifest, dict)
    typed_manifest = cast(Mapping[str, object], manifest)
    assert cast(str, typed_manifest["version"]).startswith("1.1.0+codex.")
    assert "goal-driven" in cast(str, typed_manifest["description"])
    plan = cast(Mapping[str, object], typed_manifest["plan"])
    assert plan["current_schema_version"] == 5
    plan_schema = runpy.run_path(
        str(PLUGIN_ROOT / "scripts" / "workctl_modules" / "plan_schema.py")
    )
    assert plan["current_schema_version"] == plan_schema["CURRENT_PLAN_SCHEMA_VERSION"]
    interface = cast(Mapping[str, object], typed_manifest["interface"])
    assert "durable Plan contracts" in cast(str, interface["longDescription"])


def test_public_workctl_entry_is_bash_first_wrapper() -> None:
    """The public workctl entrypoint is a thin Bash router over the private engine."""
    wrapper = PLUGIN_ROOT / "scripts" / "workctl"
    text = wrapper.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "workctl.py" in text
    assert os.access(wrapper, os.X_OK)


def test_public_workctl_wrapper_uses_registered_python_without_uv(tmp_path: Path) -> None:
    """The public wrapper dispatches directly to Python instead of UV."""
    fake_python = tmp_path / "python"
    python_log = tmp_path / "python.log"
    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${PYTHON_LOG}"
if [[ "${1:-}" == "-c" ]]; then
  exit 0
fi
printf '%s\n' 'direct-python-ok'
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    wrapper = PLUGIN_ROOT / "scripts" / "workctl"

    result = subprocess.run(
        [str(wrapper), "help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "WORK_GOVERNANCE_PYTHON": str(fake_python),
            "PYTHON_LOG": str(python_log),
        },
    )

    assert result.returncode == 0
    assert result.stdout == "direct-python-ok\n"
    calls = python_log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
    assert calls[0].startswith("-c ")
    assert calls[1].endswith("workctl.py help")


def test_public_workctl_wrapper_runs_without_uv_on_path(tmp_path: Path) -> None:
    """A project can use the registered tool even when UV is absent from PATH."""
    wrapper = PLUGIN_ROOT / "scripts" / "workctl"

    result = subprocess.run(
        [str(wrapper), "help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "WORK_GOVERNANCE_PYTHON": sys.executable,
        },
    )

    assert result.returncode == 0
    assert "goal init --stdin|--from-file" in result.stdout


def test_registered_workctl_bootstraps_schema_v5_without_hooks_or_uv(tmp_path: Path) -> None:
    """Direct runtime use initializes schema-v5 work without Hook receipts or UV cache."""
    wrapper = PLUGIN_ROOT / "scripts" / "workctl"
    environment = {
        **os.environ,
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "WORK_GOVERNANCE_PYTHON": sys.executable,
    }
    goal = {
        "plan_id": "PLAN-20260814-901",
        "title": "Hookless Smoke",
        "goal": "Prove direct runtime bootstrap.",
        "success_conditions": ["Direct workctl creates a governed Plan."],
        "tasks": [{"id": "T-001", "description": "Run the hookless smoke."}],
    }

    migrate = subprocess.run(
        [str(wrapper), "layout", "migrate"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    init = subprocess.run(
        [str(wrapper), "goal", "init", "--stdin"],
        cwd=tmp_path,
        input=json.dumps(goal),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    status = subprocess.run(
        [str(wrapper), "intake", "status"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert migrate.returncode == 0, migrate.stderr
    assert init.returncode == 0, init.stderr
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["intake_state"] == "INTAKE_READY"
    assert not (tmp_path / ".work-governance" / "cache" / "uv").exists()


def test_yaml_compat_fallback_loads_and_dumps_governance_yaml() -> None:
    """The controller can read generated YAML when PyYAML is unavailable."""
    previous = os.environ.get("WORK_GOVERNANCE_DISABLE_PYYAML")
    os.environ["WORK_GOVERNANCE_DISABLE_PYYAML"] = "1"
    try:
        namespace = runpy.run_path(
            str(PLUGIN_ROOT / "scripts" / "workctl_modules" / "yaml_compat.py"),
            run_name="yaml_compat_fallback_test",
        )
    finally:
        if previous is None:
            os.environ.pop("WORK_GOVERNANCE_DISABLE_PYYAML", None)
        else:
            os.environ["WORK_GOVERNANCE_DISABLE_PYYAML"] = previous
    safe_load = cast(Callable[[str], object], namespace["safe_load"])
    safe_dump = cast(Callable[..., str], namespace["safe_dump"])

    payload = safe_load(
        """schema_version: 1
active_plan_id: PLAN-20260801-002
plans:
- id: PLAN-20260801-002
  path: PLAN-20260801-002.md
  title: 'Wrapped candidate title with
    continuation text'
  checks:
  - hook
  - workctl
"""
    )

    assert payload == {
        "schema_version": 1,
        "active_plan_id": "PLAN-20260801-002",
        "plans": [
            {
                "id": "PLAN-20260801-002",
                "path": "PLAN-20260801-002.md",
                "title": "Wrapped candidate title with continuation text",
                "checks": ["hook", "workctl"],
            }
        ],
    }
    task_payload = safe_load(
        """tasks:
- id: T-010
  description: 'After C-HOOK-ARCHITECTURE-2026 acceptance, implement the staged Hook
    architecture: remove ordinary v5 turn-receipt dependence, preserve explicit mutable-v4
    compatibility.'
  status: verified
"""
    )

    assert task_payload == {
        "tasks": [
            {
                "id": "T-010",
                "description": (
                    "After C-HOOK-ARCHITECTURE-2026 acceptance, implement the staged Hook "
                    "architecture: remove ordinary v5 turn-receipt dependence, preserve "
                    "explicit mutable-v4 compatibility."
                ),
                "status": "verified",
            }
        ]
    }
    route_payload = safe_load(
        """route:
  validation_standard: The repair is atomic, expected-revision and current-intake
    bound, covers task:T-008, activation, and route, and preserves history.
  confirmation_gate: none
  blocks:
  - task:T-008
  - activation
"""
    )

    assert route_payload == {
        "route": {
            "validation_standard": (
                "The repair is atomic, expected-revision and current-intake bound, "
                "covers task:T-008, activation, and route, and preserves history."
            ),
            "confirmation_gate": "none",
            "blocks": ["task:T-008", "activation"],
        }
    }
    dumped = safe_dump(payload, sort_keys=False, allow_unicode=False)
    assert safe_load(dumped) == payload
    incident_payload = safe_load(
        """checks:
- "Risk feature hit \\u5DF2\\
  \\u7531 fallback\\
  \\ text tied."
"""
    )
    assert incident_payload == {"checks": ["Risk feature hit 已由 fallback text tied."]}


def test_yaml_compat_dump_is_fallback_readable_with_pyyaml_present() -> None:
    """Controller writes must stay readable by the dependency-free cold-start path."""
    namespace = runpy.run_path(
        str(PLUGIN_ROOT / "scripts" / "workctl_modules" / "yaml_compat.py"),
        run_name="yaml_compat_dump_test",
    )
    safe_dump = cast(Callable[..., str], namespace["safe_dump"])
    safe_load = cast(Callable[[str], object], namespace["safe_load"])
    payload = {
        "checks": [
            (
                "Risk feature hit and check explanations no longer use the generic text "
                '"\\u5DF2\\u7531\\u7EDF\\u4E00\\u89C4\\u5219\\u5F15\\u64CE\\u8BA1'
                '\\u7B97\\u3002"; deterministic rule output carries meaningful Chinese '
                "status text tied to the rule and data state."
            )
        ],
        "scope": {"include": [], "exclude": []},
        "created_at": "2026-08-05T15:53:30+00:00",
        "numeric_text": "12345",
        "ref": "user message 2026-07-23: continue",
        "special_float_text": ".nan",
        "hex_text": "0xFF",
        "at_text": "@foo",
        "dash_text": "- foo",
        "sexagesimal_text": "1:20",
        "trailing_space_text": "foo ",
        "underscored_int_text": "1_000",
        "truthy_text": "true",
    }

    dumped = safe_dump(payload, sort_keys=False, allow_unicode=False)
    previous = os.environ.get("WORK_GOVERNANCE_DISABLE_PYYAML")
    os.environ["WORK_GOVERNANCE_DISABLE_PYYAML"] = "1"
    try:
        fallback_namespace = runpy.run_path(
            str(PLUGIN_ROOT / "scripts" / "workctl_modules" / "yaml_compat.py"),
            run_name="yaml_compat_dump_fallback_test",
        )
    finally:
        if previous is None:
            os.environ.pop("WORK_GOVERNANCE_DISABLE_PYYAML", None)
        else:
            os.environ["WORK_GOVERNANCE_DISABLE_PYYAML"] = previous
    fallback_safe_load = cast(Callable[[str], object], fallback_namespace["safe_load"])

    assert "\\\n" not in dumped
    assert safe_load(dumped) == payload
    assert fallback_safe_load(dumped) == payload
    unicode_payload = {"line_break_text": ["foo\u0085bar", "foo\u2028bar", "foo\u2029bar"]}
    unicode_dumped = safe_dump(unicode_payload, sort_keys=False, allow_unicode=True)
    assert safe_load(unicode_dumped) == unicode_payload
    assert fallback_safe_load(unicode_dumped) == unicode_payload


def test_cli_reference_is_generated_from_the_current_parser() -> None:
    """Reject a stale checked-in reference after parser changes."""
    generator = (
        REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts" / "generate_cli_reference.py"
    )
    namespace = runpy.run_path(str(generator), run_name="cli_reference_test")
    load_controller = cast(Callable[[], ModuleType], namespace["load_controller"])
    render_reference = cast(Callable[[argparse.ArgumentParser], str], namespace["render_reference"])
    controller = load_controller()
    build_parser = cast(Callable[[], argparse.ArgumentParser], controller.__dict__["build_parser"])
    assert REFERENCE.read_text(encoding="utf-8") == render_reference(build_parser())
    reference = REFERENCE.read_text(encoding="utf-8")
    assert "### `goal show`" in reference
    assert "### `gate list`" in reference
    assert "### `truth list`" in reference
    assert "### `review status`" in reference
    assert "### `plan status`" in reference
    assert "### `task verify`" in reference
    assert "### `evidence capture`" in reference
    assert "migrate recover" in reference


def test_docs_do_not_recommend_private_tmp_evidence_intermediates() -> None:
    """Documentation must not route evidence through temporary manifest files."""
    needle = "/private" + "/tmp"
    doc_paths = [
        REPOSITORY_ROOT / "README.md",
        *(REPOSITORY_ROOT / "docs").glob("*.md"),
        *PLUGIN_ROOT.glob("skills/*/SKILL.md"),
        *PLUGIN_ROOT.glob("skills/*/references/*.md"),
    ]
    offenders = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in doc_paths
        if needle in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
