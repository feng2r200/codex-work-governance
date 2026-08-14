"""Packaged PyYAML adapter for the Work Governance controller.

The public ``workctl`` runtime does not install dependencies at execution time.
PyYAML must be present in ``scripts/vendor`` as part of the installed Plugin
package. If that dependency is missing or resolves from outside the Plugin
bundle, fail before any Plan or layout mutation can happen.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, cast

_VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
_VENDOR_DIR_TEXT = str(_VENDOR_DIR)

if _VENDOR_DIR_TEXT not in sys.path:
    sys.path.insert(0, _VENDOR_DIR_TEXT)

for module_name in tuple(sys.modules):
    if module_name == "yaml" or module_name.startswith("yaml."):
        module = sys.modules[module_name]
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            continue
        try:
            Path(module_file).resolve().relative_to(_VENDOR_DIR.resolve())
        except ValueError:
            del sys.modules[module_name]

_previous_dont_write_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    try:
        import yaml as _pyyaml_module
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "WORKCTL_PACKAGED_DEPENDENCY_MISSING: PyYAML is required under "
            "plugins/work-governance/scripts/vendor; rebuild and reinstall the Plugin package."
        ) from exc
finally:
    sys.dont_write_bytecode = _previous_dont_write_bytecode

_pyyaml = cast(ModuleType, _pyyaml_module)
_pyyaml_file = Path(cast(str, _pyyaml.__file__)).resolve()
try:
    _pyyaml_file.relative_to(_VENDOR_DIR.resolve())
except ValueError as exc:
    raise RuntimeError(
        "WORKCTL_PACKAGED_DEPENDENCY_MISSING: PyYAML resolved outside the Plugin vendor "
        f"directory: {_pyyaml_file}"
    ) from exc

YAMLError: type[Exception] = cast(type[Exception], _pyyaml.YAMLError)


def safe_load(stream: str | bytes) -> Any:
    """Load YAML using the PyYAML copy packaged with the Plugin."""
    return _pyyaml.safe_load(stream)


def safe_dump(
    data: object,
    *,
    sort_keys: bool = True,
    allow_unicode: bool = True,
) -> str:
    """Dump YAML using the PyYAML copy packaged with the Plugin."""
    effective_allow_unicode = allow_unicode and not _contains_yaml_line_break(data)
    return cast(
        str,
        _pyyaml.safe_dump(
            data,
            sort_keys=sort_keys,
            allow_unicode=effective_allow_unicode,
            default_flow_style=False,
            width=4096,
        ),
    )


def _contains_yaml_line_break(value: object) -> bool:
    """Return whether PyYAML should escape non-ASCII YAML line-break characters."""
    if isinstance(value, str):
        return any(character in value for character in "\u0085\u2028\u2029")
    if isinstance(value, Mapping):
        return any(
            _contains_yaml_line_break(key) or _contains_yaml_line_break(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return any(_contains_yaml_line_break(item) for item in value)
    return False
