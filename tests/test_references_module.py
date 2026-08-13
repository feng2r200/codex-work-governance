from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

references_module = importlib.import_module("workctl_modules.references")
valid_reference = references_module.valid_reference


def test_valid_reference_uses_the_caller_owned_pattern() -> None:
    """Reference validation keeps the controller's pattern as the single rule source."""
    pattern = re.compile(r"^(project|runtime):\S+$")

    assert valid_reference("project:src/work.py", pattern)
    assert valid_reference("runtime:plans/PLAN-20260806-001", pattern)
    assert not valid_reference("user:turn", pattern)
    assert not valid_reference("project:has space", pattern)
    assert not valid_reference(7, pattern)
