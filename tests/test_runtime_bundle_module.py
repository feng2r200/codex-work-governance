from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

runtime_bundle_module = importlib.import_module("workctl_modules.runtime_bundle")
filesystem_module = importlib.import_module("workctl_modules.filesystem")
RuntimeBundleError = runtime_bundle_module.RuntimeBundleError

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def test_runtime_bundle_manifest_payload_preserves_optional_module_files() -> None:
    """Runtime bundle manifest projection keeps the controller contract stable."""
    base = runtime_bundle_module.runtime_bundle_manifest_payload(
        plugin_build="pytest",
        plugin_manifest_sha256="1" * 64,
        current_plan_schema_version=5,
        controller_ref=".work-governance/runtime/plugin-builds/x/workctl.py",
        controller_sha256="2" * 64,
        lifecycle_ref=".work-governance/runtime/plugin-builds/x/work-lifecycle.SKILL.md",
        lifecycle_sha256="3" * 64,
    )
    with_module_files = runtime_bundle_module.runtime_bundle_manifest_payload(
        plugin_build="pytest",
        plugin_manifest_sha256="1" * 64,
        current_plan_schema_version=5,
        controller_ref=".work-governance/runtime/plugin-builds/x/workctl.py",
        controller_sha256="2" * 64,
        lifecycle_ref=".work-governance/runtime/plugin-builds/x/work-lifecycle.SKILL.md",
        lifecycle_sha256="3" * 64,
        module_files=[],
    )

    assert "module_files" not in base
    assert with_module_files["module_files"] == []


def test_validated_runtime_bundle_module_files_returns_typed_entries(tmp_path: Path) -> None:
    """Runtime-file validation checks shape, location, and content digest."""
    bundle = tmp_path / "bundle"
    module_path = bundle / "workctl_modules" / "kernel" / "controller.py"
    vendor_path = bundle / "vendor" / "yaml" / "__init__.py"
    license_path = bundle / "vendor" / "pyyaml-6.0.3.dist-info" / "licenses" / "LICENSE"
    module_path.parent.mkdir(parents=True)
    vendor_path.parent.mkdir(parents=True)
    license_path.parent.mkdir(parents=True)
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    vendor_path.write_text("__version__ = '6.0.3'\n", encoding="utf-8")
    license_path.write_text("license\n", encoding="utf-8")
    module_digest = filesystem_module.sha256_file(module_path)
    vendor_digest = filesystem_module.sha256_file(vendor_path)
    license_digest = filesystem_module.sha256_file(license_path)
    manifest = {
        "module_files": [
            {"path": "workctl_modules/kernel/controller.py", "sha256": module_digest},
            {"path": "vendor/yaml/__init__.py", "sha256": vendor_digest},
            {
                "path": "vendor/pyyaml-6.0.3.dist-info/licenses/LICENSE",
                "sha256": license_digest,
            },
        ]
    }

    assert runtime_bundle_module.validated_runtime_bundle_module_files(
        bundle,
        manifest,
        sha256_pattern=SHA256_RE,
    ) == [
        {"path": "workctl_modules/kernel/controller.py", "sha256": module_digest},
        {"path": "vendor/yaml/__init__.py", "sha256": vendor_digest},
        {
            "path": "vendor/pyyaml-6.0.3.dist-info/licenses/LICENSE",
            "sha256": license_digest,
        },
    ]


def test_validated_runtime_bundle_module_files_rejects_invalid_entries(
    tmp_path: Path,
) -> None:
    """Module-file validation fails closed for malformed entries and drift."""
    bundle = tmp_path / "bundle"
    module_path = bundle / "workctl_modules" / "helper.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeBundleError, match="BOOTSTRAP_RUNTIME_BUNDLE_INVALID"):
        runtime_bundle_module.validated_runtime_bundle_module_files(
            bundle,
            {"module_files": "bad"},
            sha256_pattern=SHA256_RE,
        )
    vendor_so = bundle / "vendor" / "yaml" / "_yaml.cpython-312-darwin.so"
    vendor_so.parent.mkdir(parents=True, exist_ok=True)
    vendor_so.write_text("binary\n", encoding="utf-8")
    with pytest.raises(RuntimeBundleError, match="BOOTSTRAP_RUNTIME_BUNDLE_INVALID"):
        runtime_bundle_module.validated_runtime_bundle_module_files(
            bundle,
            {
                "module_files": [
                    {
                        "path": "vendor/yaml/_yaml.cpython-312-darwin.so",
                        "sha256": filesystem_module.sha256_file(vendor_so),
                    }
                ]
            },
            sha256_pattern=SHA256_RE,
        )
    with pytest.raises(RuntimeBundleError, match="BOOTSTRAP_RUNTIME_BUNDLE_INVALID"):
        runtime_bundle_module.validated_runtime_bundle_module_files(
            bundle,
            {"module_files": [{"path": "workctl_modules/helper.py", "sha256": "0" * 64}]},
            sha256_pattern=SHA256_RE,
        )
    with pytest.raises(RuntimeBundleError, match="BOOTSTRAP_RUNTIME_BUNDLE_INVALID"):
        runtime_bundle_module.validated_runtime_bundle_module_files(
            bundle,
            {
                "module_files": [
                    {
                        "path": "helper.py",
                        "sha256": filesystem_module.sha256_file(module_path),
                    }
                ]
            },
            sha256_pattern=SHA256_RE,
        )
    with pytest.raises(RuntimeBundleError, match="BOOTSTRAP_RUNTIME_BUNDLE_INVALID"):
        runtime_bundle_module.validated_runtime_bundle_module_files(
            bundle,
            {
                "module_files": [
                    {
                        "path": "workctl_modules/../workctl.py",
                        "sha256": filesystem_module.sha256_file(module_path),
                    }
                ]
            },
            sha256_pattern=SHA256_RE,
        )
