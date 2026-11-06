"""Exercise Plan recovery identity, content, and continuation checks."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("pi_plan_trial", SCRIPTS / "run_pi_plan_trial.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_plan_oracle_requires_persistence_and_correct_continuation() -> None:
    """Changing identity, strategy, or result cannot count as recovery."""
    token = "recovered-token"
    created = {
        "plans": "1",
        "plan.0.status": "active",
        "plan.0.plan_entity_id": "id",
        "plan.0.description_json": json.dumps("Produce a recovery result"),
        "plan.0.strategy_json": json.dumps(token),
    }
    assert all(MODULE.evaluate(created, created.copy(), token, token + "\n").values())
    assert not MODULE.evaluate(
        created, dict(created, **{"plan.0.plan_entity_id": "other"}), token, token + "\n"
    )["plan_persists_same_identity"]
    assert not MODULE.evaluate(
        created, dict(created, **{"plan.0.strategy_json": "other"}), token, token + "\n"
    )["plan_content_persisted"]
    assert not MODULE.evaluate(created, created, token, "wrong\n")["resumed_output"]


def test_timeout_is_reported_and_partial_trace_is_kept(tmp_path: Path) -> None:
    """A timed-out Pi is a visible failure, not an empty successful report."""
    partial = b'{"type":"tool_execution_start","toolName":"read","args":{"path":"x"}}\n{'
    failure = subprocess.TimeoutExpired("pi", 300, output=partial, stderr=b"timeout")
    with (
        patch.object(MODULE.shutil, "which", return_value="/test/pi"),
        patch.object(MODULE.subprocess, "run", side_effect=failure),
    ):
        report = MODULE.run_pi(tmp_path, tmp_path, "test")
    assert report["timed_out"] is True
    assert report["completed"] is False
    assert report["exit"] is None
    assert report["calls"] == [{"tool": "read", "args": {"path": "x"}}]
