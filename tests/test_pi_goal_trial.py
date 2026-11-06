"""Challenge Pi goal-continuity artifact checks with positive and negative cases."""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("pi_goal_trial", SCRIPTS / "run_pi_goal_trial.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_goal_oracle_accepts_good_and_rejects_wrong_results() -> None:
    """The artifact oracle catches wrong outputs and nonblocking classification."""
    expected = {"currency": "CNY"}
    decision = {
        "observations": [
            {"observation_id": "id", "blocks_current_delivery": False, "basis": "contract"}
        ]
    }
    receipt = {
        "passed": True,
        "markdown_present_at_check": False,
        "remaining_required_outputs": ["delivery/summary.md"],
        "observation_id": "id",
        "summary_semantic_sha256": MODULE.digest_json(expected),
    }
    evaluate = MODULE.evaluate
    good = evaluate(expected, "markdown", decision, receipt, expected, "markdown", "id", True, True)
    assert all(good.values())
    wrong = evaluate({}, "wrong", {}, {}, expected, "markdown", "id", False, True)
    assert not wrong["summary_exact"]
    assert not wrong["markdown_exact"]
    assert not wrong["nonblocking_observation"]
    assert not wrong["stage_receipt"]
    assert not wrong["protected_inputs_unchanged"]
    numeric_type_mismatch = evaluate(
        {"fulfilled_orders": True},
        "markdown",
        decision,
        receipt,
        {"fulfilled_orders": 1},
        "markdown",
        "id",
        True,
        True,
    )
    assert not numeric_type_mismatch["summary_exact"]
