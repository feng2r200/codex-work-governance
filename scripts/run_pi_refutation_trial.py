#!/usr/bin/env python3
"""Exercise a two-turn Pi evidence change using RPC and a temporary workspace.

Pi retains ordinary read, shell and editing access; this is not a sandbox. The
trace can contain task contents and must only be saved to an authorized path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import selectors
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from run_pi_behavior_trial import SKILLS


def evaluate(
    timeline: list[dict[str, object]],
    initial: str,
    current: str,
    result: object,
    premature_output: bool,
) -> dict[str, bool]:
    """Check observed phase ordering, tool evidence, and the final artifact."""
    first = [item for item in timeline if item.get("phase") == "first"]
    second = [item for item in timeline if item.get("phase") == "second"]
    injection = [index for index, item in enumerate(timeline) if item.get("phase") == "inject"]
    first_settled = [
        index
        for index, item in enumerate(timeline)
        if item.get("phase") == "first" and item.get("type") == "agent_settled"
    ]
    second_started = [
        index
        for index, item in enumerate(timeline)
        if item.get("phase") == "second" and item.get("type") == "agent_start"
    ]

    def saw_tool_result(items: list[dict[str, object]], marker: str) -> bool:
        return any(
            item.get("type") == "tool_execution_end"
            and item.get("isError") is False
            and marker in json.dumps(item.get("result"), ensure_ascii=False)
            for item in items
        )

    def stopped_normally(items: list[dict[str, object]]) -> bool:
        last_stop: object = None
        for item in items:
            message = item.get("message")
            if (
                item.get("type") == "message_end"
                and isinstance(message, dict)
                and message.get("role") == "assistant"
            ):
                last_stop = message.get("stopReason")
        return last_stop == "stop"

    return {
        "first_stop": stopped_normally(first),
        "second_stop": stopped_normally(second),
        "phase_order": len(injection) == 1
        and bool(first_settled)
        and bool(second_started)
        and first_settled[-1] < injection[0] < second_started[0],
        "initial_evidence_observed": saw_tool_result(first, initial),
        "current_evidence_observed": saw_tool_result(second, current),
        "no_premature_output": not premature_output,
        "exact_final_artifact": result == {"route": current},
        "first_settled": any(
            item.get("type") == "agent_settled" and item.get("aborted") is False for item in first
        ),
        "second_settled": any(
            item.get("type") == "agent_settled" and item.get("aborted") is False for item in second
        ),
    }


def wait_for_settled(
    process: subprocess.Popen[bytes],
    phase: str,
    timeline: list[dict[str, object]],
    selector: selectors.BaseSelector,
    buffer: bytearray,
    request_id: str,
    timeout: float = 240,
) -> None:
    """Consume RPC JSONL continuously until acceptance and agent_settled."""
    assert process.stdout is not None
    deadline = time.monotonic() + timeout
    accepted = False
    while time.monotonic() < deadline:
        while b"\n" in buffer:
            line, _, remaining = buffer.partition(b"\n")
            buffer[:] = remaining
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise RuntimeError("RPC emitted a non-object event")
            item = {"phase": phase, **event}
            timeline.append(item)
            if event.get("type") == "response" and event.get("id") == request_id:
                if event.get("success") is not True:
                    raise RuntimeError(f"RPC rejected {request_id}: {event}")
                accepted = True
            if event.get("type") == "agent_settled":
                if not accepted:
                    raise RuntimeError("agent settled without accepted prompt")
                return
        ready = selector.select(max(0.0, deadline - time.monotonic()))
        if not ready:
            break
        chunk = os.read(process.stdout.fileno(), 65536)
        if not chunk:
            raise RuntimeError("RPC exited before agent settled")
        buffer.extend(chunk)
    raise TimeoutError(f"RPC phase {phase} timed out")


def send_prompt(process: subprocess.Popen[bytes], request_id: str, message: str) -> None:
    """Send a correlated prompt on the Pi RPC stdin."""
    if process.stdin is None:
        raise RuntimeError("RPC stdin unavailable")
    process.stdin.write(
        (json.dumps({"id": request_id, "type": "prompt", "message": message}) + "\n").encode()
    )
    process.stdin.flush()


def main() -> int:
    """Run a changed or unchanged evidence trial and persist its raw trace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("changed", "unchanged"), required=True)
    parser.add_argument("--kernel-file", type=Path, help="Use this execution-kernel body")
    parser.add_argument("--output", type=Path, required=True, help="New JSON report path")
    args = parser.parse_args()
    pi = shutil.which("pi")
    if pi is None:
        raise RuntimeError("pi unavailable")
    if args.output.exists():
        raise FileExistsError(args.output)
    started_at = datetime.now(UTC).isoformat()
    kernel_source = args.kernel_file or SKILLS / "execution-kernel" / "SKILL.md"
    kernel_bytes = kernel_source.read_bytes()
    runner_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    pi_version = subprocess.run(
        [pi, "--version"], capture_output=True, text=True, check=True, timeout=15
    ).stdout.strip()
    timeline: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="work-governance-pi-refutation.") as temporary:
        root = Path(temporary).resolve()
        work = root / "work"
        work.mkdir()
        agent = root / "agent"
        agent.mkdir(mode=0o700)
        trial_skills = root / "skills"
        shutil.copytree(SKILLS, trial_skills)
        (trial_skills / "execution-kernel" / "SKILL.md").write_bytes(kernel_bytes)
        source = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
        for name in ("auth.json", "models.json"):
            if (source / name).is_file():
                shutil.copyfile(source / name, agent / name)
                (agent / name).chmod(0o600)
        initial = "route-" + secrets.token_hex(12)
        current = "route-" + secrets.token_hex(12) if args.scenario == "changed" else initial
        policy = work / "policy.json"
        policy.write_text(json.dumps({"route": initial}) + "\n", encoding="utf-8")
        result_path = work / "result.json"
        env = os.environ.copy()
        env.update({"PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1"})
        env.pop("SSH_AUTH_SOCK", None)
        invocation = [
            pi,
            "--mode",
            "rpc",
            "--no-session",
            "--no-extensions",
            "--no-mcp",
            "--skill",
            str(trial_skills),
            "-t",
            "read,bash,edit,write",
        ]
        with tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                invocation,
                cwd=work,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
            )
            selector = selectors.DefaultSelector()
            assert process.stdout is not None
            selector.register(process.stdout, selectors.EVENT_READ)
            buffer = bytearray()
            premature = False
            runner_error: str | None = None
            try:
                send_prompt(
                    process,
                    "first",
                    "Read policy.json and identify the route for a later delivery. "
                    "Do not create result.json yet; wait for the next instruction.",
                )
                wait_for_settled(process, "first", timeline, selector, buffer, "first")
                premature = result_path.exists()
                if args.scenario == "changed":
                    policy.write_text(json.dumps({"route": current}) + "\n", encoding="utf-8")
                timeline.append({"phase": "inject", "type": args.scenario})
                send_prompt(
                    process,
                    "second",
                    "Continue using the current evidence. Write result.json as a JSON object "
                    "with exactly one key, route, whose value is the current route. "
                    "Verify the result.",
                )
                wait_for_settled(process, "second", timeline, selector, buffer, "second")
            except (TimeoutError, RuntimeError, OSError, json.JSONDecodeError) as error:
                runner_error = f"{type(error).__name__}: {error}"
            finally:
                selector.close()
                if process.stdin:
                    process.stdin.close()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            try:
                artifact: object = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                artifact = None
            checks = evaluate(timeline, initial, current, artifact, premature)
            checks["runner_completed"] = runner_error is None
            stderr.seek(0)
            stderr_text = stderr.read().decode("utf-8", errors="replace")
            report = {
                "claim_scope": "two_turn_current_evidence_artifact_not_a_sandbox",
                "collected_at_utc": started_at,
                "pi_version": pi_version,
                "kernel_sha256": hashlib.sha256(kernel_bytes).hexdigest(),
                "runner_sha256": runner_digest,
                "scenario": args.scenario,
                "passed": all(checks.values()),
                "checks": checks,
                "initial_route": initial,
                "current_route": current,
                "artifact": artifact,
                "runner_error": runner_error,
                "stderr": stderr_text,
                "timeline": timeline,
            }
            output_fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(output_fd, "w", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2)
            print(
                json.dumps(
                    {"passed": report["passed"], "checks": checks, "output": str(args.output)}
                )
            )
            return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
