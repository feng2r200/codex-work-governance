"""Runtime bundle manifest projections and module-file validation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from re import Pattern

from workctl_modules.filesystem import FilesystemError, sha256_file


class RuntimeBundleError(ValueError):
    """Raised when a runtime bundle manifest is malformed or drifted."""


def runtime_bundle_manifest_payload(
    *,
    plugin_build: object,
    plugin_manifest_sha256: object,
    current_plan_schema_version: object,
    controller_ref: object,
    controller_sha256: object,
    lifecycle_ref: object,
    lifecycle_sha256: object,
    module_files: object | None = None,
) -> dict[str, object]:
    """Build the canonical runtime bundle manifest projection."""
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-runtime-bundle",
        "plugin_build": plugin_build,
        "plugin_manifest_sha256": plugin_manifest_sha256,
        "current_plan_schema_version": current_plan_schema_version,
        "controller_ref": controller_ref,
        "controller_sha256": controller_sha256,
        "lifecycle_ref": lifecycle_ref,
        "lifecycle_sha256": lifecycle_sha256,
    }
    if module_files is not None:
        payload["module_files"] = module_files
    return payload


def validated_runtime_bundle_module_files(
    bundle: Path,
    manifest: Mapping[str, object],
    *,
    sha256_pattern: Pattern[str],
) -> list[dict[str, str]] | None:
    """Validate the optional module file manifest and return it unchanged."""
    module_files = manifest.get("module_files")
    if module_files is None:
        return None
    if not isinstance(module_files, list):
        raise RuntimeBundleError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
    typed_files: list[dict[str, str]] = []
    for entry in module_files:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256"}
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("sha256"), str)
            or sha256_pattern.fullmatch(entry["sha256"]) is None
        ):
            raise RuntimeBundleError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
        module_path = bundle / entry["path"]
        try:
            digest = sha256_file(module_path)
        except FilesystemError as exc:
            raise RuntimeBundleError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID") from exc
        if (
            module_path.parent.parent != bundle
            or module_path.is_symlink()
            or digest != entry["sha256"]
        ):
            raise RuntimeBundleError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
        typed_files.append({"path": entry["path"], "sha256": entry["sha256"]})
    return typed_files
