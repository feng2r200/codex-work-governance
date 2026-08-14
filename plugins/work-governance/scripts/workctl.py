#!/usr/bin/env python3
"""Public Work Governance controller entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if sys.version_info < (3, 12):  # noqa: UP036 - clearer failure for direct invocation.
    print(
        "PYTHON_3_12_REQUIRED: run through scripts/workctl or set "
        "WORK_GOVERNANCE_PYTHON to Python >= 3.12",
        file=sys.stderr,
    )
    raise SystemExit(2)

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = SCRIPT_DIR / "vendor"
for import_root in (SCRIPT_DIR, VENDOR_DIR):
    import_root_text = str(import_root)
    if import_root_text not in sys.path:
        sys.path.insert(0, import_root_text)

if TYPE_CHECKING:

    def main(argv: list[str] | None = None) -> int: ...

else:
    try:
        from workctl_modules.kernel.controller import *  # noqa: F401,F403,E402
        from workctl_modules.kernel.controller import main  # noqa: E402
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("WORKCTL_PACKAGED_DEPENDENCY_MISSING:"):
            print(message, file=sys.stderr)
            raise SystemExit(2) from exc
        raise

if __name__ == "__main__":
    raise SystemExit(main())
