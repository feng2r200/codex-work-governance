"""Fail-closed tests for offline observations and the private behavior oracle."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "scripts" / "evaluate_goal_continuity.py"
RUNNER = ROOT / "scripts" / "run_behavior_trial.py"


def run_evaluator(contract: Path, trace: Path, workspace: Path) -> subprocess.CompletedProcess[str]:
    """Run the observational evaluator with captured output."""
    return subprocess.run(
        [
            "uv",
            "run",
            str(EVALUATOR),
            "--contract",
            str(contract),
            "--trace",
            str(trace),
            "--workspace",
            str(workspace),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


def valid_contract(required_file: str = "result.json") -> dict[str, object]:
    """Return a non-vacuous independent-outcome contract."""
    return {
        "schema_version": 2,
        "task_id": "evaluator-contract-test",
        "trial_kind": "unit_fixture",
        "trace": {
            "minimum_completed_commands": 1,
            "minimum_final_messages": 1,
            "boundary": {
                "workspace_only": True,
                "forbidden_executables": ["workvcs"],
            },
        },
        "required_files": [required_file],
        "outcome_contract": {
            "oracle_id": "test.private-oracle.v1",
            "required_checks": ["artifact.semantic_outcome"],
        },
    }


def valid_trace(usage: dict[str, object] | None = None, command: str = "true") -> str:
    """Return one lifecycle-valid single-turn Codex trace."""
    completed: dict[str, object] = {"type": "turn.completed"}
    if usage is not None:
        completed["usage"] = usage
    return "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-test"}),
            json.dumps({"type": "turn.started"}),
            json.dumps(
                {
                    "type": "item.started",
                    "item": {
                        "id": "command-1",
                        "type": "command_execution",
                        "command": command,
                        "exit_code": None,
                    },
                }
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "command-1",
                        "type": "command_execution",
                        "command": command,
                        "exit_code": 0,
                    },
                }
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "message-1", "type": "agent_message", "text": "done"},
                }
            ),
            json.dumps(completed),
        ]
    )


def write_valid_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Write one complete contract and trace pair."""
    contract = tmp_path / "contract.json"
    trace = tmp_path / "trace.jsonl"
    contract.write_text(json.dumps(valid_contract()), encoding="utf-8")
    trace.write_text(valid_trace(), encoding="utf-8")
    (tmp_path / "result.json").write_text("{}\n", encoding="utf-8")
    return contract, trace


def test_evaluator_rejects_empty_trace(tmp_path: Path) -> None:
    """An absent trajectory cannot become passing evidence."""
    contract, trace = write_valid_fixture(tmp_path)
    trace.write_text("", encoding="utf-8")

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["passed"] is False
    assert report["error"] == "trace is empty"


def test_evaluator_rejects_vacuous_outcome_contract(tmp_path: Path) -> None:
    """Empty task and oracle contracts fail before trajectory observations."""
    contract = tmp_path / "contract.json"
    trace = tmp_path / "trace.jsonl"
    contract.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "task_id": "",
                "trial_kind": "unit_fixture",
                "trace": {
                    "minimum_completed_commands": 1,
                    "minimum_final_messages": 1,
                    "boundary": {
                        "workspace_only": True,
                        "forbidden_executables": ["workvcs"],
                    },
                },
                "required_files": [],
                "outcome_contract": {"oracle_id": "", "required_checks": []},
            }
        ),
        encoding="utf-8",
    )
    trace.write_text(valid_trace(), encoding="utf-8")

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["error"] == "task_id must be a non-empty trimmed string"


def test_evaluator_rejects_three_line_forged_trace(tmp_path: Path) -> None:
    """Completed-looking events without thread and item lifecycles are invalid."""
    contract, trace = write_valid_fixture(tmp_path)
    trace.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "fake-command",
                            "type": "command_execution",
                            "command": "true",
                            "exit_code": 0,
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "fake-message", "type": "agent_message", "text": "done"},
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        ),
        encoding="utf-8",
    )

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["error"] == "trace line 1 must be thread.started"


def test_evaluator_rejects_command_without_started_event(tmp_path: Path) -> None:
    """A caller cannot fabricate process work with only a completed command item."""
    contract, trace = write_valid_fixture(tmp_path)
    trace.write_text(
        "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-test"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "command-1",
                            "type": "command_execution",
                            "command": "true",
                            "exit_code": 0,
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "message-1", "type": "agent_message", "text": "done"},
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        ),
        encoding="utf-8",
    )

    completed = run_evaluator(contract, trace, tmp_path)

    assert completed.returncode == 2
    assert "without item.started" in json.loads(completed.stdout)["error"]


def test_offline_observation_never_claims_behavior_passed(tmp_path: Path) -> None:
    """Even a structurally valid caller-supplied trace is observation, not proof."""
    contract, trace = write_valid_fixture(tmp_path)

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert report["claim_scope"] == "untrusted_offline_observation"
    assert report["observation_checks_passed"] is True
    assert report["behavior_passed"] is False
    assert report["passed"] is False
    assert report["independent_outcome_status"] == "not_executed_by_offline_evaluator"


def test_evaluator_retains_transient_transport_error_before_completed_turn(
    tmp_path: Path,
) -> None:
    """A reconnect event remains observable when the same turn later completes."""
    contract, trace = write_valid_fixture(tmp_path)
    events = valid_trace().splitlines()
    events.insert(
        2,
        json.dumps({"type": "error", "message": "Reconnecting... 1/5"}),
    )
    trace.write_text("\n".join(events), encoding="utf-8")

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert report["observation_checks_passed"] is True
    assert report["trace"]["transient_errors"] == 1


def test_evaluator_rejects_empty_transient_error_message(tmp_path: Path) -> None:
    """An error event without an observable message is structurally invalid."""
    contract, trace = write_valid_fixture(tmp_path)
    events = valid_trace().splitlines()
    events.insert(2, json.dumps({"type": "error", "message": ""}))
    trace.write_text("\n".join(events), encoding="utf-8")

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["error"] == "trace line 3 transient error message must be non-empty"


def test_evaluator_rejects_workspace_escape(tmp_path: Path) -> None:
    """A contract cannot make observations read outside the trial workspace."""
    contract = tmp_path / "contract.json"
    trace = tmp_path / "trace.jsonl"
    value = valid_contract("../outside.txt")
    contract.write_text(json.dumps(value), encoding="utf-8")
    trace.write_text(valid_trace(), encoding="utf-8")

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["error"] == "contract path escapes workspace: ../outside.txt"


def test_evaluator_observes_outside_workspace_command(tmp_path: Path) -> None:
    """A literal absolute host path is surfaced as a lexical warning."""
    contract, trace = write_valid_fixture(tmp_path)
    trace.write_text(
        valid_trace(command="/bin/zsh -lc 'cat /Users/example/private.txt'"),
        encoding="utf-8",
    )

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert completed.returncode == 1
    assert report["observation_checks_passed"] is False
    assert checks["trace.lexical_workspace_escape_hits_absent"] is False


def test_evaluator_observes_forbidden_workvcs_command(tmp_path: Path) -> None:
    """A literal WorkVCS command is surfaced as a lexical warning."""
    contract, trace = write_valid_fixture(tmp_path)
    trace.write_text(
        valid_trace(command="/bin/zsh -lc 'workvcs runtime status --require-stable'"),
        encoding="utf-8",
    )

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert completed.returncode == 1
    assert report["observation_checks_passed"] is False
    assert checks["trace.lexical_forbidden_executable_hits_absent"] is False


def test_lexical_boundary_does_not_claim_dynamic_runtime_enforcement(tmp_path: Path) -> None:
    """Dynamic paths and executables remain outside the lexical observer's claim."""
    commands = (
        'python3 -c "from pathlib import Path; print(Path.home())"',
        ("python3 -c \"import subprocess; subprocess.run(['work' + 'vcs', 'runtime', 'status'])\""),
        'touch "$(mktemp -u)"',
    )
    for command in commands:
        contract, trace = write_valid_fixture(tmp_path)
        trace.write_text(valid_trace(command=command), encoding="utf-8")

        completed = run_evaluator(contract, trace, tmp_path)

        report = json.loads(completed.stdout)
        checks = {check["name"]: check for check in report["checks"]}
        assert completed.returncode == 1
        assert report["observation_checks_passed"] is True
        for name in (
            "trace.lexical_forbidden_executable_hits_absent",
            "trace.lexical_workspace_escape_hits_absent",
        ):
            assert checks[name]["passed"] is True
            assert checks[name]["detail"].startswith("lexical heuristic only")


def test_evaluator_reports_complete_turn_usage_with_source_line(tmp_path: Path) -> None:
    """Complete usage remains bound to its raw turn event."""
    contract, trace = write_valid_fixture(tmp_path)
    trace.write_text(
        valid_trace({"input_tokens": 150, "cached_input_tokens": 100, "output_tokens": 20}),
        encoding="utf-8",
    )

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    resources = report["resource_observation"]
    assert completed.returncode == 1
    assert resources["source"]["line_numbers"] == [6]
    assert resources["token_usage"]["input_tokens"]["value"] == 150
    assert resources["token_usage"]["cached_input_tokens"]["value"] == 100
    assert resources["token_usage"]["output_tokens"]["value"] == 20
    assert resources["elapsed_time_seconds"]["status"] == "unknown"


def test_evaluator_keeps_missing_turn_usage_unknown(tmp_path: Path) -> None:
    """Missing provider telemetry is not converted into zero usage."""
    contract, trace = write_valid_fixture(tmp_path)

    completed = run_evaluator(contract, trace, tmp_path)

    usage = json.loads(completed.stdout)["resource_observation"]["token_usage"]
    assert completed.returncode == 1
    for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
        assert usage[field]["status"] == "unknown"
        assert usage[field]["value"] is None
        assert usage[field]["missing_lines"] == [6]


def test_evaluator_rejects_invalid_usage_type_at_source_line(tmp_path: Path) -> None:
    """Malformed telemetry fails at the exact source field."""
    contract, trace = write_valid_fixture(tmp_path)
    trace.write_text(
        valid_trace({"input_tokens": True, "cached_input_tokens": 80, "output_tokens": 14}),
        encoding="utf-8",
    )

    completed = run_evaluator(contract, trace, tmp_path)

    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["error"] == (
        "trace line 6 field usage.input_tokens must be a non-negative integer or null"
    )


def test_runner_oracle_rejects_noop_workspace_validator() -> None:
    """Wrong artifacts plus a zero-exit validator cannot bypass the private oracle."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(RUNNER),
            "goal-continuity",
            "--negative-control",
            "validator-noop",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert report["claim_scope"] == "runner_oracle_negative_control"
    assert report["control_passed"] is True
    assert report["behavior_passed"] is False
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert checks["delivery.summary_exact"] is False
    assert checks["delivery.markdown_exact"] is False
    assert checks["validator.rejects_json_currency"] is False
    assert checks["validator.rejects_json_net_revenue"] is False


def test_runner_oracle_rejects_wrong_markdown_region() -> None:
    """Correct JSON cannot hide an extra conflicting regional Markdown value."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(RUNNER),
            "goal-continuity",
            "--negative-control",
            "markdown-region-corruption",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert completed.returncode == 0
    assert report["control_passed"] is True
    assert checks["delivery.summary_exact"] is True
    assert checks["delivery.markdown_exact"] is False
    assert checks["validator.rejects_markdown_divergence"] is True


def test_runner_oracle_rejects_fabricated_bounded_stage() -> None:
    """A receipt without an observed protected-checker pass is not stage evidence."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(RUNNER),
            "goal-continuity",
            "--negative-control",
            "local-stage-skipped",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert completed.returncode == 0
    assert report["control_passed"] is True
    assert checks["stimulus.local_json_stage_passed_with_markdown_gap"] is False


def test_runner_oracle_rejects_nonblocking_finding_promoted_to_blocker() -> None:
    """A real adjacent finding cannot replace the still-authorized delivery route."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(RUNNER),
            "goal-continuity",
            "--negative-control",
            "finding-promoted-to-blocker",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert completed.returncode == 0
    assert report["control_passed"] is True
    assert checks["discovery.runtime_observation_classified_non_blocking"] is False


def test_runner_oracle_rejects_conflicting_duplicate_routing_decision() -> None:
    """A duplicate case with different Branch and authority cannot be masked."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(RUNNER),
            "project-routing",
            "--negative-control",
            "routing-duplicate-conflict",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert completed.returncode == 0
    assert report["control_passed"] is True
    assert checks["routing.decision_set_exact"] is False
    assert checks["routing.authority_isolated"] is False


def test_runner_oracle_rejects_stale_record_as_current_instruction() -> None:
    """A stale revision cannot select a Branch or transfer deployment authority."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(RUNNER),
            "project-routing",
            "--negative-control",
            "routing-stale-record-admitted",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)
    checks = {check["name"]: check["passed"] for check in report["checks"]}
    assert completed.returncode == 0
    assert report["control_passed"] is True
    assert checks["routing.record_currentness_enforced"] is False
    assert checks["routing.current_revision_only"] is False
    assert checks["routing.authority_isolated"] is False
