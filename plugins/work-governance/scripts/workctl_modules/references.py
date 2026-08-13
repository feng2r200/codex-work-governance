"""Pure typed reference validation helpers."""

from __future__ import annotations

import re


def valid_reference(value: object, pattern: re.Pattern[str]) -> bool:
    """Return whether a value matches the controller's typed reference pattern."""
    return isinstance(value, str) and pattern.fullmatch(value) is not None
