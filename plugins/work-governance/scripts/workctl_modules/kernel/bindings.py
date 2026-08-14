"""Scoped dependency binding for extracted kernel domain modules."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

_MISSING = object()


def call_with_bound_globals[T](
    target_globals: dict[str, Any],
    bindings: Mapping[str, Any],
    function: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Call ``function`` after binding missing controller dependencies by name."""
    inserted: list[str] = []
    for name, value in bindings.items():
        if name.startswith("__") or name in target_globals:
            continue
        target_globals[name] = value
        inserted.append(name)
    try:
        return function(*args, **kwargs)
    finally:
        for name in inserted:
            if target_globals.get(name, _MISSING) is bindings.get(name):
                target_globals.pop(name, None)
