"""Validate plugin metadata and generated command documentation contracts."""

from __future__ import annotations

import argparse
import json
import runpy
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
    assert "goal-driven" in cast(str, typed_manifest["description"])
    interface = cast(Mapping[str, object], typed_manifest["interface"])
    assert "durable Plan contracts" in cast(str, interface["longDescription"])


def test_cli_reference_is_generated_from_the_current_parser() -> None:
    """Reject a stale checked-in reference after parser changes."""
    generator = (
        REPOSITORY_ROOT
        / "plugins"
        / "work-governance"
        / "scripts"
        / "generate_cli_reference.py"
    )
    namespace = runpy.run_path(str(generator), run_name="cli_reference_test")
    load_controller = cast(Callable[[], ModuleType], namespace["load_controller"])
    render_reference = cast(
        Callable[[argparse.ArgumentParser], str], namespace["render_reference"]
    )
    controller = load_controller()
    build_parser = cast(Callable[[], argparse.ArgumentParser], controller.__dict__["build_parser"])
    assert REFERENCE.read_text(encoding="utf-8") == render_reference(build_parser())
    reference = REFERENCE.read_text(encoding="utf-8")
    assert "### `plan status`" in reference
    assert "### `task verify`" in reference
    assert "migrate recover" in reference
