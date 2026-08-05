"""Validate plugin metadata and generated command documentation contracts."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
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
    interface = cast(Mapping[str, object], typed_manifest["interface"])
    assert "durable Plan contracts" in cast(str, interface["longDescription"])


def test_public_workctl_entry_is_bash_first_wrapper() -> None:
    """The public workctl entrypoint is a thin Bash router over the private engine."""
    wrapper = PLUGIN_ROOT / "scripts" / "workctl"
    text = wrapper.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "workctl.py" in text
    assert os.access(wrapper, os.X_OK)


def test_public_workctl_wrapper_prewarms_for_script_dependency_cache_miss(
    tmp_path: Path,
) -> None:
    """The public wrapper recovers from a script dependency cache miss."""
    fake_uv = tmp_path / "uv"
    uv_log = tmp_path / "uv.log"
    fake_uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${UV_LOG}"
if [[ "$*" == *"--offline"* ]]; then
  printf '%s\n' 'script dependency was not found in the cache' >&2
  printf '%s\n' 'Packages were unavailable because the network was disabled' >&2
  exit 1
fi
printf '%s\n' 'network-prewarm-ok'
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    wrapper = PLUGIN_ROOT / "scripts" / "workctl"

    result = subprocess.run(
        [str(wrapper), "help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "UV": str(fake_uv),
            "UV_LOG": str(uv_log),
            "WORK_GOVERNANCE_PROJECT_ROOT": str(tmp_path),
        },
    )

    assert result.returncode == 0
    assert result.stdout == "network-prewarm-ok\n"
    calls = uv_log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
    assert "--offline" in calls[0]
    assert "--offline" not in calls[1]


def test_public_workctl_wrapper_can_remain_strictly_offline(tmp_path: Path) -> None:
    """Strict-offline mode preserves fail-closed behavior for dependency misses."""
    fake_uv = tmp_path / "uv"
    uv_log = tmp_path / "uv.log"
    fake_uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${UV_LOG}"
printf '%s\n' 'script dependency was not found in the cache' >&2
printf '%s\n' 'Packages were unavailable because the network was disabled' >&2
exit 1
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    wrapper = PLUGIN_ROOT / "scripts" / "workctl"

    result = subprocess.run(
        [str(wrapper), "help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "UV": str(fake_uv),
            "UV_LOG": str(uv_log),
            "WORK_GOVERNANCE_PROJECT_ROOT": str(tmp_path),
            "WORK_GOVERNANCE_STRICT_OFFLINE": "1",
        },
    )

    assert result.returncode == 1
    assert "script dependency was not found in the cache" in result.stderr
    calls = uv_log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert "--offline" in calls[0]


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
    dumped = safe_dump(payload, sort_keys=False, allow_unicode=False)
    assert safe_load(dumped) == payload


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
