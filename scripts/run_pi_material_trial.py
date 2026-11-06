#!/usr/bin/env python3
"""Compare Pi kernel conditions on an independently checked code-change task.

The model and generated code execute with ordinary user privileges. This is not
an isolation boundary. Usage sums are not provider-confirmed billing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from run_pi_behavior_trial import SKILLS
from run_pi_plan_trial import run_pi

STARTER = '''def total_cents(lines, member=False, coupon=None):
    """Return the subtotal for quantity/price pairs."""
    return sum(quantity * price for quantity, price in lines)
'''

REQUEST = """Change pricing.py: implement total_cents(lines, member=False, coupon=None).
lines is a list of (quantity, unit_price_cents) pairs. Require quantity to be a
positive int and price a nonnegative int, excluding bool; invalid values raise
ValueError. member must be a bool. coupon must be None or 'SAVE500', otherwise
raise ValueError. Apply a 10% member discount rounded down to an integer cent,
then subtract 500 cents for SAVE500 only when the discounted amount is at least
3000 cents. Add 600 cents shipping when a nonempty order's post-discount amount
is less than 5000 cents. An empty order totals zero. Return integer cents.
Do not modify files outside the workspace. Verify the implementation.
"""

ORACLE = r"""import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("pricing_trial", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
f = module.total_cents
checks = {}
for name, lines, member, coupon, expected in [
    ("empty", [], False, None, 0),
    ("shipping", [(2, 1000)], False, None, 2600),
    ("free_shipping", [(1, 5000)], False, None, 5000),
    ("member_floor", [(1, 3333)], True, None, 3599),
    ("coupon_threshold", [(1, 3000)], False, "SAVE500", 3100),
    ("coupon_ineligible", [(1, 2999)], False, "SAVE500", 3599),
    ("discount_order", [(1, 5555)], True, "SAVE500", 5099),
]:
    try:
        value = f(lines, member=member, coupon=coupon)
        checks[name] = type(value) is int and value == expected
    except Exception:
        checks[name] = False
for name, lines, member, coupon in [
    ("invalid_quantity", [(0, 100)], False, None),
    ("invalid_price", [(1, -1)], False, None),
    ("bool_quantity", [(True, 100)], False, None),
    ("bool_price", [(1, True)], False, None),
    ("invalid_member", [(1, 100)], 1, None),
    ("invalid_coupon", [(1, 100)], False, "BAD"),
]:
    try:
        f(lines, member=member, coupon=coupon)
        checks[name] = False
    except ValueError:
        checks[name] = True
    except Exception:
        checks[name] = False
print(json.dumps(checks, sort_keys=True))
"""

EXPECTED_CHECKS = {
    "empty",
    "shipping",
    "free_shipping",
    "member_floor",
    "coupon_threshold",
    "coupon_ineligible",
    "discount_order",
    "invalid_quantity",
    "invalid_price",
    "bool_quantity",
    "bool_price",
    "invalid_member",
    "invalid_coupon",
}

GOOD = """def total_cents(lines, member=False, coupon=None):
    if type(member) is not bool or coupon not in (None, "SAVE500"):
        raise ValueError("invalid option")
    subtotal = 0
    for quantity, price in lines:
        if type(quantity) is not int or quantity < 1 or type(price) is not int or price < 0:
            raise ValueError("invalid line")
        subtotal += quantity * price
    if not lines:
        return 0
    if member:
        subtotal = subtotal * 90 // 100
    if coupon == "SAVE500" and subtotal >= 3000:
        subtotal -= 500
    return subtotal + (600 if subtotal < 5000 else 0)
"""


def grade(path: Path) -> dict[str, bool]:
    """Run the external fixed-vector oracle against one implementation."""
    result = subprocess.run(
        [sys.executable, "-I", "-c", ORACLE, str(path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return {"oracle_process": False}
    try:
        value: object = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"oracle_json": False}
    if (
        not isinstance(value, dict)
        or set(value) != EXPECTED_CHECKS
        or not all(type(v) is bool for v in value.values())
    ):
        return {"oracle_shape": False}
    return dict(value)


def main() -> int:
    """Run one full-kernel or empty-body real Pi implementation trial."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-kernel", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="work-governance-pi-material.") as temporary:
        root = Path(temporary).resolve()
        work = root / "work"
        work.mkdir()
        (work / "pricing.py").write_text(STARTER, encoding="utf-8")
        agent = root / "agent"
        agent.mkdir(mode=0o700)
        source = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
        for name in ("auth.json", "models.json"):
            if (source / name).is_file():
                shutil.copyfile(source / name, agent / name)
                (agent / name).chmod(0o600)
        reference = root / "reference.py"
        reference.write_text(GOOD, encoding="utf-8")
        positive = grade(reference)
        negative = grade(work / "pricing.py")
        controls = (
            len(positive) == len(EXPECTED_CHECKS)
            and all(positive.values())
            and not all(negative.values())
        )
        if not controls:
            raise RuntimeError(f"oracle control failed: positive={positive}, negative={negative}")
        skills = SKILLS
        if args.without_kernel:
            skills = root / "control-skills"
            shutil.copytree(SKILLS, skills)
            kernel = skills / "execution-kernel" / "SKILL.md"
            frontmatter = kernel.read_text(encoding="utf-8").split("---", 2)[1]
            kernel.write_text(f"---{frontmatter}---\n\n# Execution Kernel\n", encoding="utf-8")
        run = run_pi(work, agent, REQUEST, skills)
        checks = grade(work / "pricing.py")
        report = {
            "claim_scope": "one_python_code_change_not_a_sandbox_or_general_benchmark",
            "kernel_content": not args.without_kernel,
            "passed": run["completed"] is True and all(checks.values()) and controls,
            "checks": checks,
            "oracle_controls_passed": controls,
            "positive_control": positive,
            "negative_control": negative,
            "implementation": (work / "pricing.py").read_text(encoding="utf-8"),
            "run": run,
        }
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
