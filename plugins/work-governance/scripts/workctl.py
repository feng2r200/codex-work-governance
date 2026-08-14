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

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

if TYPE_CHECKING:

    def main(argv: list[str] | None = None) -> int: ...

else:
    from workctl_modules.kernel.controller import *  # noqa: F401,F403,E402
    from workctl_modules.kernel.controller import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
