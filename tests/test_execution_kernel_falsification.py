"""Challenge the two-turn evidence-change trial oracle without a model."""

import copy
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "pi_refutation_trial", SCRIPTS / "run_pi_refutation_trial.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def events(initial: str, current: str) -> list[dict[str, object]]:
    """Build the smallest positive trace for two observed phases."""
    return [
        {"phase": "first", "type": "tool_execution_end", "isError": False, "result": initial},
        {
            "phase": "first",
            "type": "message_end",
            "message": {"role": "assistant", "stopReason": "stop"},
        },
        {"phase": "first", "type": "agent_settled", "aborted": False},
        {"phase": "inject", "type": "changed"},
        {"phase": "second", "type": "agent_start"},
        {"phase": "second", "type": "tool_execution_end", "isError": False, "result": current},
        {
            "phase": "second",
            "type": "message_end",
            "message": {"role": "assistant", "stopReason": "stop"},
        },
        {"phase": "second", "type": "agent_settled", "aborted": False},
    ]


def test_oracle_accepts_changed_and_unchanged_controls() -> None:
    """Both updated and unchanged inputs require matching real observed evidence."""
    assert all(
        MODULE.evaluate(events("old", "new"), "old", "new", {"route": "new"}, False).values()
    )
    assert all(
        MODULE.evaluate(events("old", "old"), "old", "old", {"route": "old"}, False).values()
    )


def test_oracle_rejects_stale_or_unobserved_evidence() -> None:
    """A stale artifact or failed tool result cannot count as valid re-observation."""
    observed = events("old", "new")
    assert not MODULE.evaluate(observed, "old", "new", {"route": "old"}, False)[
        "exact_final_artifact"
    ]
    failed = copy.deepcopy(observed)
    failed[5]["isError"] = True
    assert not MODULE.evaluate(failed, "old", "new", {"route": "new"}, False)[
        "current_evidence_observed"
    ]
    assert not MODULE.evaluate(observed, "old", "new", {"route": "new"}, True)[
        "no_premature_output"
    ]
    misordered = [*observed[:2], observed[3], observed[2], *observed[4:]]
    assert not MODULE.evaluate(misordered, "old", "new", {"route": "new"}, False)["phase_order"]


def test_oracle_rejects_aborted_or_failed_model_runs() -> None:
    """A correct-looking file is insufficient if a phase aborted or errored."""
    observed = events("old", "new")
    aborted = copy.deepcopy(observed)
    aborted[-1]["aborted"] = True
    assert not MODULE.evaluate(aborted, "old", "new", {"route": "new"}, False)["second_settled"]
    failed = copy.deepcopy(observed)
    failed[-2]["message"] = {"role": "assistant", "stopReason": "error"}
    assert not MODULE.evaluate(failed, "old", "new", {"route": "new"}, False)["second_stop"]
    no_injection = [event for event in observed if event.get("phase") != "inject"]
    assert not MODULE.evaluate(no_injection, "old", "new", {"route": "new"}, False)["phase_order"]
    assert not MODULE.evaluate(observed, "old", "new", "new", False)["exact_final_artifact"]
