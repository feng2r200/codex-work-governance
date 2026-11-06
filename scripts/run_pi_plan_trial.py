#!/usr/bin/env python3
"""Observe real Plan creation and fresh-process recovery in a temporary WorkVCS Store.

The Pi processes have normal tool access; this is not a security sandbox.
The Store is explicit and temporary and the real project's binding is not used.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from run_pi_behavior_trial import SKILLS, command


def fields(output: str) -> dict[str, str]:
    """Parse the native key-value output without inferring absent fields."""
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def evaluate(
    created: dict[str, str], recovered: dict[str, str], token: str, result: str
) -> dict[str, bool]:
    """Compare independently read native Plan identity and the recovered output."""
    plan_id = created.get("plan.0.plan_entity_id")
    return {
        "one_active_plan": created.get("plans") == "1" and created.get("plan.0.status") == "active",
        "plan_persists_same_identity": bool(plan_id)
        and recovered.get("plans") == "1"
        and recovered.get("plan.0.plan_entity_id") == plan_id,
        "goal_recorded": created.get("plan.0.description_json")
        == json.dumps("Produce a recovery result"),
        "strategy_recorded": token in created.get("plan.0.strategy_json", ""),
        "plan_content_persisted": bool(plan_id)
        and all(
            created.get(key) == recovered.get(key)
            for key in ("plan.0.status", "plan.0.description_json", "plan.0.strategy_json")
        ),
        "resumed_output": result == token + "\n",
    }


def run_pi(work: Path, agent: Path, prompt: str, skills: Path = SKILLS) -> dict[str, object]:
    """Run a fresh non-persistent Pi process and return bounded trace evidence."""
    pi = shutil.which("pi")
    if pi is None:
        raise RuntimeError("pi unavailable")
    env = os.environ.copy()
    env.update({"PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1"})
    env.pop("SSH_AUTH_SOCK", None)
    start = time.monotonic()
    invocation = [
        pi,
        "--no-extensions",
        "--no-mcp",
        "--no-session",
        "--skill",
        str(skills),
        "-t",
        "read,bash,edit,write",
        "-p",
        prompt,
        "--mode",
        "json",
    ]
    timed_out = False
    try:
        result = subprocess.run(
            invocation,
            cwd=work,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        exit_code = None
    elapsed = time.monotonic() - start
    events = []
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if timed_out and index == len(lines) - 1:
                break
            raise RuntimeError("Pi emitted invalid JSONL") from exc
    messages = [event["message"] for event in events if event.get("type") == "message_end"]
    assistant = [message for message in messages if message.get("role") == "assistant"]
    return {
        "completed": exit_code == 0
        and bool(assistant)
        and assistant[-1].get("stopReason") == "stop",
        "exit": exit_code,
        "timed_out": timed_out,
        "last_stop_reason": assistant[-1].get("stopReason") if assistant else None,
        "last_error": assistant[-1].get("errorMessage") if assistant else None,
        "model": assistant[-1].get("model") if assistant else None,
        "provider": assistant[-1].get("provider") if assistant else None,
        "elapsed_seconds": round(elapsed, 3),
        "calls": [
            {"tool": event.get("toolName"), "args": event.get("args")}
            for event in events
            if event.get("type") == "tool_execution_start"
        ],
        "usage": [
            message.get("usage") for message in assistant if message.get("usage") is not None
        ],
        "trace_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_tail": stderr[-1000:],
    }


def main() -> int:
    """Create the fixture, invoke two processes, and verify the Store and result."""
    workvcs = shutil.which("workvcs")
    if workvcs is None:
        raise RuntimeError("workvcs unavailable")
    with tempfile.TemporaryDirectory(prefix="work-governance-pi-plan.") as temporary:
        root = Path(temporary).resolve()
        work = root / "work"
        work.mkdir()
        agent = root / "agent"
        agent.mkdir(mode=0o700)
        source = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
        for name in ("auth.json", "models.json"):
            if (source / name).is_file():
                shutil.copyfile(source / name, agent / name)
                (agent / name).chmod(0o600)
        store = root / "trial.sqlite"
        command(work, workvcs, "init", str(store), "--display-name", "temporary Pi Plan trial")
        workspace = fields(
            command(
                work,
                workvcs,
                "workspace",
                "create",
                str(store),
                "--display-name",
                "trial",
                "--initial-branch-name",
                "main",
            )
        )
        branch, head = workspace["branch_id"], workspace["genesis_commit_id"]
        initial = fields(command(work, workvcs, "plan", "list", str(store), "--branch", branch))
        if initial.get("plans") != "0":
            raise RuntimeError("positive-control fixture does not start without a Plan")
        token = "recovered-" + secrets.token_hex(12)
        strategy = f"Next session must write {token} followed by newline to result.txt."
        create_prompt = (
            "This task needs a durable Plan across independent sessions. In the temporary "
            f"WorkVCS Store {store}, branch {branch}, current head {head}, create exactly one "
            "active Plan with description 'Produce a recovery result' and strategy "
            f"'{strategy}'. Use workvcs plan create and do not do the next session's work."
        )
        first = run_pi(work, agent, create_prompt)
        created = fields(command(work, workvcs, "plan", "list", str(store), "--branch", branch))
        recovery_prompt = (
            "A prior independent session recorded your next task in the active Plan in "
            f"temporary WorkVCS Store {store}, branch {branch}. Recover that Plan from the "
            "Store and carry out its next step in this workspace. Do not guess the output."
        )
        second = run_pi(work, agent, recovery_prompt)
        recovered = fields(command(work, workvcs, "plan", "list", str(store), "--branch", branch))
        result_path = work / "result.txt"
        content = result_path.read_text(encoding="utf-8") if result_path.is_file() else ""
        checks = evaluate(created, recovered, token, content)
        checks["both_processes_completed"] = (
            first["completed"] is True and second["completed"] is True
        )
        negative = evaluate({}, {}, token, "")
        controls = all(not negative[key] for key in negative)
        report = {
            "claim_scope": "one_temporary_workvcs_plan_two_pi_processes_not_a_sandbox",
            "passed": all(checks.values()) and controls,
            "checks": checks,
            "negative_control_passed": controls,
            "initial_plan_count": initial.get("plans"),
            "created_plan_id": created.get("plan.0.plan_entity_id"),
            "recovered_plan_id": recovered.get("plan.0.plan_entity_id"),
            "plan_created": created,
            "plan_recovered": recovered,
            "resumed_output": content,
            "first": first,
            "second": second,
        }
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
