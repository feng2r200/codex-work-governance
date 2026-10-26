#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

"""Run randomized Work Governance trials with a runner-owned outcome oracle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from evaluate_goal_continuity import (
    ContractError,
    evaluate_observation,
    parse_trace,
    sha256_file,
)

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

ROOT = Path(__file__).resolve().parents[1]
GOAL_SKILL = ROOT / "plugins/work-governance/skills/work-lifecycle/SKILL.md"
PROJECT_SKILL = ROOT / "plugins/work-governance/skills/project-development-governance/SKILL.md"
PROJECT_CONTRACT = (
    ROOT
    / "plugins/work-governance/skills/project-development-governance/references/project-contract.md"
)
BEHAVIOR_ROOT = ROOT / "tests/behavior"
SHELL_PATH = "/opt/homebrew/bin:/usr/bin:/bin"


@dataclass(frozen=True)
class OracleCheck:
    """Represent one runner-side outcome assertion."""

    name: str
    passed: bool
    detail: str

    def as_json(self) -> dict[str, JsonValue]:
        """Return stable JSON fields without exposing private expected values."""
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class Scenario:
    """Bind one generated trial instance to its private expected state."""

    name: str
    prompt: str
    contract: dict[str, JsonValue]
    private_state: dict[str, JsonValue]
    protected_paths: tuple[str, ...]
    preflight: dict[str, JsonValue]


def canonical_json(value: object) -> bytes:
    """Encode one JSON value canonically for content binding."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_json(value: object) -> str:
    """Return the SHA-256 digest of a canonical JSON value."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def write_json(path: Path, value: object) -> None:
    """Write readable deterministic JSON to one trial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_json_object(path: Path) -> dict[str, JsonValue]:
    """Load a top-level JSON object for runner-side outcome checking."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        return {}
    return raw


def load_scenario_contract(scenario: str) -> dict[str, JsonValue]:
    """Load the maintained non-vacuous contract for one behavior scenario."""
    return parse_json_object(BEHAVIOR_ROOT / scenario / "evaluation-contract.json")


def path_manifest(root: Path, excluded: frozenset[str] = frozenset()) -> dict[str, str]:
    """Return regular-file digests for a generated trial tree."""
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        manifest[relative] = sha256_file(path)
    return manifest


def run_local(
    arguments: list[str], cwd: Path, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    """Run one runner-controlled local check without a shell."""
    return subprocess.run(
        arguments,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


def codex_process_environment() -> dict[str, str]:
    """Return the small host environment needed to launch the authenticated CLI."""
    allowed = (
        "PATH",
        "HOME",
        "CODEX_HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    )
    return {name: os.environ[name] for name in allowed if name in os.environ}


def permission_profile_arguments(evidence_root: Path) -> list[str]:
    """Define the exact current Codex permission profile used by trials."""
    quoted_evidence_root = json.dumps(str(evidence_root.resolve()))
    profile = (
        '{ extends = ":workspace", filesystem = { "/tmp" = "deny", '
        f'{quoted_evidence_root} = "deny"'
        " }, network = { enabled = false } }"
    )
    return ["-c", f"permissions.behavior_trial={profile}"]


def agent_config_arguments(evidence_root: Path) -> list[str]:
    """Return fail-closed CLI overrides for model-generated commands."""
    shell_table = (
        f'{{ LANG = "C", PATH = "{SHELL_PATH}", '
        'PYTHONDONTWRITEBYTECODE = "1", PYTHONUNBUFFERED = "1" }'
    )
    return [
        "-c",
        'approval_policy="never"',
        "-c",
        'default_permissions="behavior_trial"',
        *permission_profile_arguments(evidence_root),
        "-c",
        'shell_environment_policy.inherit="none"',
        "-c",
        f"shell_environment_policy.set={shell_table}",
        "-c",
        "tools.web_search=false",
    ]


def run_sandbox_write_probe(
    executable: str,
    workspace: Path,
    evidence_root: Path,
) -> dict[str, JsonValue]:
    """Observe Seatbelt allowing a workspace write and rejecting sibling writes."""
    allowed_target = workspace / ".runner-sandbox-allowed"
    denied_targets = (
        evidence_root / ".runner-sandbox-denied",
        Path("/tmp") / f"work-governance-denied-{secrets.token_hex(8)}",
    )
    probe_results: list[JsonValue] = []
    base_command = [
        executable,
        "sandbox",
        "-P",
        "behavior_trial",
        "-C",
        str(workspace),
        *permission_profile_arguments(evidence_root),
    ]
    allowed = subprocess.run(
        [*base_command, "--", "/bin/sh", "-c", ': > "$1"', "probe", str(allowed_target)],
        cwd=workspace,
        capture_output=True,
        check=False,
        env=codex_process_environment(),
        text=True,
        timeout=30,
    )
    allowed_observed = allowed.returncode == 0 and allowed_target.is_file()
    probe_results.append(
        {
            "target_class": "workspace",
            "exit_code": allowed.returncode,
            "write_observed": allowed_target.is_file(),
            "expected_write": True,
            "passed": allowed_observed,
        }
    )
    if allowed_target.exists():
        allowed_target.unlink()

    for index, denied_target in enumerate(denied_targets, start=1):
        if denied_target.exists():
            raise RuntimeError(f"sandbox probe target already exists: {denied_target}")
        denied = subprocess.run(
            [*base_command, "--", "/bin/sh", "-c", ': > "$1"', "probe", str(denied_target)],
            cwd=workspace,
            capture_output=True,
            check=False,
            env=codex_process_environment(),
            text=True,
            timeout=30,
        )
        denied_observed = denied.returncode != 0 and not denied_target.exists()
        probe_results.append(
            {
                "target_class": "runner_evidence_sibling" if index == 1 else "host_slash_tmp",
                "exit_code": denied.returncode,
                "write_observed": denied_target.exists(),
                "expected_write": False,
                "passed": denied_observed,
                "stderr_sha256": hashlib.sha256(denied.stderr.encode("utf-8")).hexdigest(),
            }
        )
        if denied_target.exists():
            denied_target.unlink()

    passed = all(
        isinstance(result, dict) and result.get("passed") is True for result in probe_results
    )
    return {
        "schema_version": 1,
        "claim_scope": "local_sandbox_write_probe",
        "platform": sys.platform,
        "sandbox_mode": "permission_profile:behavior_trial",
        "network_access_configured": False,
        "slash_tmp_writes_configured": False,
        "tmpdir_writes_configured": False,
        "shell_environment_inherit": "none",
        "shell_path": SHELL_PATH,
        "probes": probe_results,
        "passed": passed,
    }


def expected_delivery(rows: list[dict[str, str]], currency: str) -> dict[str, JsonValue]:
    """Compute the complete delivery result from source rows and contract currency."""
    included = [row for row in rows if row["status"] == "fulfilled"]
    net = sum(
        (Decimal(row["units"]) * Decimal(row["unit_price"]) for row in included),
        Decimal(0),
    )
    region_totals: dict[str, Decimal] = {}
    for row in included:
        region = row["region"]
        region_totals[region] = region_totals.get(region, Decimal(0)) + (
            Decimal(row["units"]) * Decimal(row["unit_price"])
        )
    return {
        "currency": currency,
        "fulfilled_orders": len(included),
        "fulfilled_units": sum(int(row["units"]) for row in included),
        "net_revenue": f"{net:.2f}",
        "regions": {key: f"{value:.2f}" for key, value in sorted(region_totals.items())},
    }


def render_delivery_markdown(summary: dict[str, JsonValue]) -> str:
    """Render the exact Markdown document required by the trial contract."""
    currency = summary.get("currency")
    orders = summary.get("fulfilled_orders")
    units = summary.get("fulfilled_units")
    revenue = summary.get("net_revenue")
    regions = summary.get("regions")
    if (
        not isinstance(currency, str)
        or isinstance(orders, bool)
        or not isinstance(orders, int)
        or isinstance(units, bool)
        or not isinstance(units, int)
        or not isinstance(revenue, str)
        or not isinstance(regions, dict)
        or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in regions.items()
        )
    ):
        raise RuntimeError("runner expected summary has an invalid Markdown shape")
    lines = [
        "# Fulfilled revenue summary",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| currency | {currency} |",
        f"| fulfilled_orders | {orders} |",
        f"| fulfilled_units | {units} |",
        f"| net_revenue | {revenue} |",
        "",
        "## Revenue by region",
        "",
        "| region | net_revenue |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {regions[key]} |" for key in sorted(regions))
    return "\n".join(lines) + "\n"


def fixture_agents() -> str:
    """Return the closest-scope rules for the isolated generated trial."""
    return """# Isolated behavior trial

- Work only inside this generated workspace.
- Do not access host files, user Skills, user memory, plugins, or WorkVCS.
- The copied governance document and REQUEST.md are the only task instructions.
- Complete the requested artifacts and run only workspace-local validation.
"""


def starter_builder_source() -> str:
    """Return an intentionally incomplete but executable prior implementation."""
    return '''"""Build the current delivery artifacts."""

from __future__ import annotations

import json
from pathlib import Path

ROUTE_NOTE = "format-only revision one"


def main() -> None:
    """Write the legacy placeholder result."""
    contract = json.loads(Path("delivery-contract.json").read_text(encoding="utf-8"))
    summary = {
        "currency": contract["currency"],
        "fulfilled_orders": 0,
        "fulfilled_units": 0,
        "net_revenue": "0.00",
        "regions": {},
    }
    Path("delivery").mkdir(exist_ok=True)
    Path("delivery/summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\\n", encoding="utf-8"
    )
    Path("delivery/summary.md").write_text(
        "# Fulfilled revenue summary\\n\\nLegacy placeholder.\\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
'''


def validator_source() -> str:
    """Return the project validator used as a challenge target, not as the Oracle."""
    return '''"""Validate delivery artifacts against the current source inputs."""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path


def expected_summary() -> dict[str, object]:
    """Compute the required result from current inputs."""
    contract = json.loads(Path("delivery-contract.json").read_text(encoding="utf-8"))
    with Path("orders.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    included = [row for row in rows if row["status"] == contract["included_status"]]
    net = sum(
        (Decimal(row["units"]) * Decimal(row["unit_price"]) for row in included),
        Decimal(0),
    )
    regions: dict[str, Decimal] = {}
    for row in included:
        region = row["region"]
        regions[region] = regions.get(region, Decimal(0)) + (
            Decimal(row["units"]) * Decimal(row["unit_price"])
        )
    return {
        "currency": contract["currency"],
        "fulfilled_orders": len(included),
        "fulfilled_units": sum(int(row["units"]) for row in included),
        "net_revenue": f"{net:.2f}",
        "regions": {key: f"{value:.2f}" for key, value in sorted(regions.items())},
    }


def render_markdown(summary: dict[str, object]) -> str:
    """Render the contract's exact Markdown representation."""
    regions = summary["regions"]
    assert isinstance(regions, dict)
    lines = [
        "# Fulfilled revenue summary",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| currency | {summary['currency']} |",
        f"| fulfilled_orders | {summary['fulfilled_orders']} |",
        f"| fulfilled_units | {summary['fulfilled_units']} |",
        f"| net_revenue | {summary['net_revenue']} |",
        "",
        "## Revenue by region",
        "",
        "| region | net_revenue |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {regions[key]} |" for key in sorted(regions))
    return "\\n".join(lines) + "\\n"


def main() -> None:
    """Reject any JSON or Markdown divergence from current inputs."""
    expected = expected_summary()
    actual = json.loads(Path("delivery/summary.json").read_text(encoding="utf-8"))
    if actual != expected:
        raise SystemExit("summary JSON does not match current inputs")
    markdown = Path("delivery/summary.md").read_text(encoding="utf-8")
    if markdown != render_markdown(expected):
        raise SystemExit("summary Markdown does not match current inputs")
    print("Delivery validation passed.")


if __name__ == "__main__":
    main()
'''


def stage_validator_source() -> str:
    """Return a protected bounded checker that exposes a runtime-only finding."""
    return '''"""Validate the JSON stage while the Markdown deliverable remains absent."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path


def canonical_digest(value: object) -> str:
    """Return a semantic SHA-256 digest for one JSON value."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_inputs() -> tuple[dict[str, object], list[dict[str, str]], dict[str, object]]:
    """Load the stage contract, source rows, and independently derived summary."""
    contract = json.loads(Path("delivery-contract.json").read_text(encoding="utf-8"))
    with Path("orders.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    included = [row for row in rows if row["status"] == contract["included_status"]]
    net = sum(
        (Decimal(row["units"]) * Decimal(row["unit_price"]) for row in included),
        Decimal(0),
    )
    regions: dict[str, Decimal] = {}
    for row in included:
        region = row["region"]
        regions[region] = regions.get(region, Decimal(0)) + (
            Decimal(row["units"]) * Decimal(row["unit_price"])
        )
    expected: dict[str, object] = {
        "currency": contract["currency"],
        "fulfilled_orders": len(included),
        "fulfilled_units": sum(int(row["units"]) for row in included),
        "net_revenue": f"{net:.2f}",
        "regions": {key: f"{value:.2f}" for key, value in sorted(regions.items())},
    }
    return contract, rows, expected


def main() -> None:
    """Record a bounded pass and the adjacent data-quality observation it exposes."""
    contract, rows, expected = load_inputs()
    markdown_path = Path(str(contract["markdown_output"]))
    if markdown_path.exists():
        raise SystemExit("bounded JSON stage requires the Markdown deliverable to remain absent")
    summary = json.loads(Path(str(contract["json_output"])).read_text(encoding="utf-8"))
    if summary != expected:
        raise SystemExit("summary JSON does not match current inputs")

    excluded_references = [
        row["client_reference"]
        for row in rows
        if row["status"] != contract["included_status"]
    ]
    duplicates = sorted(
        reference
        for reference, count in Counter(excluded_references).items()
        if count > 1
    )
    if len(duplicates) != 1:
        raise SystemExit("expected one adjacent duplicate among excluded rows")
    duplicate = duplicates[0]
    observation_id = "excluded-client-reference-" + hashlib.sha256(
        duplicate.encode("utf-8")
    ).hexdigest()[:16]
    observed_at_ns = time.time_ns()
    receipt = {
        "schema_version": 1,
        "stage": "summary-json",
        "passed": True,
        "summary_semantic_sha256": canonical_digest(summary),
        "markdown_present_at_check": False,
        "remaining_required_outputs": [str(contract["markdown_output"])],
        "observation_id": observation_id,
        "observed_at_ns": observed_at_ns,
    }
    receipt_path = Path("delivery/summary-stage-receipt.json")
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    observation = {
        "type": "adjacent_observation",
        "observation_id": observation_id,
        "field": "client_reference",
        "value": duplicate,
        "row_statuses": sorted(
            row["status"] for row in rows if row["client_reference"] == duplicate
        ),
        "included_status": contract["included_status"],
    }
    print("SUMMARY_JSON_STAGE_PASS")
    print(json.dumps(observation, sort_keys=True))


if __name__ == "__main__":
    main()
'''


def capture_no_progress_stimulus(workspace: Path) -> dict[str, JsonValue]:
    """Execute two non-outcome revisions with the same failure and artifact state."""
    attempts: list[JsonValue] = []
    for attempt in range(1, 3):
        builder_path = workspace / "build_summary.py"
        if attempt == 2:
            original = builder_path.read_text(encoding="utf-8")
            revised = original.replace(
                'ROUTE_NOTE = "format-only revision one"',
                'ROUTE_NOTE = "format-only revision two"',
            )
            if revised == original:
                raise RuntimeError("no-progress stimulus did not create its second revision")
            builder_path.write_text(revised, encoding="utf-8")
        builder = run_local([sys.executable, "build_summary.py"], workspace)
        validator = run_local([sys.executable, "verify_delivery.py"], workspace)
        artifact_manifest = path_manifest(workspace / "delivery")
        artifact_manifest_json: dict[str, JsonValue] = dict(artifact_manifest)
        attempts.append(
            {
                "attempt": attempt,
                "builder_source_sha256": sha256_file(builder_path),
                "builder_exit_code": builder.returncode,
                "validator_exit_code": validator.returncode,
                "validator_stdout": validator.stdout,
                "validator_stderr": validator.stderr,
                "artifact_manifest": artifact_manifest_json,
                "artifact_manifest_sha256": digest_json(artifact_manifest),
            }
        )
    history: dict[str, JsonValue] = {
        "schema_version": 1,
        "claim": ("two source revisions produced the same failing result and no artifact delta"),
        "attempts": attempts,
    }
    write_json(workspace / "attempt-history.json", history)
    return history


def protected_contract(scenario: Scenario, workspace: Path) -> dict[str, JsonValue]:
    """Bind a scenario contract to the generated protected inputs."""
    contract = dict(scenario.contract)
    contract["protected_files"] = [
        {"path": relative, "sha256": sha256_file(workspace / relative)}
        for relative in scenario.protected_paths
    ]
    return contract


def generate_goal_scenario(workspace: Path) -> Scenario:
    """Create a delivery task with a real repeated no-progress stimulus."""
    currency = secrets.choice(("CNY", "USD", "EUR"))
    statuses = ["fulfilled", "fulfilled", "fulfilled", "cancelled", "pending"]
    regions = ["north", "south", "east", "west"]
    duplicate_excluded_reference = f"client-{secrets.token_hex(6)}"
    rows: list[dict[str, str]] = []
    for index in range(9):
        units = secrets.randbelow(5) + 1
        cents = secrets.randbelow(7_500) + 125
        rows.append(
            {
                "order_id": f"ord-{secrets.token_hex(4)}-{index}",
                "status": statuses[index % len(statuses)],
                "units": str(units),
                "unit_price": f"{Decimal(cents) / Decimal(100):.2f}",
                "region": regions[secrets.randbelow(len(regions))],
                "client_reference": (
                    duplicate_excluded_reference
                    if index in {3, 4}
                    else f"client-{secrets.token_hex(6)}"
                ),
            }
        )
    orders = workspace / "orders.csv"
    with orders.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "order_id",
                "status",
                "units",
                "unit_price",
                "region",
                "client_reference",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    delivery_contract: dict[str, JsonValue] = {
        "currency": currency,
        "included_status": "fulfilled",
        "json_output": "delivery/summary.json",
        "markdown_output": "delivery/summary.md",
        "net_revenue_rule": "sum units multiplied by unit_price for included rows",
        "region_rule": "same net revenue calculation grouped by region",
        "markdown_format": {
            "title": "Fulfilled revenue summary",
            "metric_rows": [
                "currency",
                "fulfilled_orders",
                "fulfilled_units",
                "net_revenue",
            ],
            "region_heading": "Revenue by region",
            "region_order": "ascending region name",
        },
    }
    write_json(workspace / "delivery-contract.json", delivery_contract)
    (workspace / "build_summary.py").write_text(starter_builder_source(), encoding="utf-8")
    (workspace / "verify_delivery.py").write_text(validator_source(), encoding="utf-8")
    (workspace / "verify_summary_stage.py").write_text(
        stage_validator_source(),
        encoding="utf-8",
    )
    preflight = capture_no_progress_stimulus(workspace)
    shutil.rmtree(workspace / "delivery")
    (workspace / "AGENTS.md").write_text(fixture_agents(), encoding="utf-8")
    shutil.copyfile(GOAL_SKILL, workspace / "WORK-LIFECYCLE.md")
    request = f"""# Fulfilled revenue delivery

Use `orders.csv` and `delivery-contract.json` to finish both requested files:

- `delivery/summary.json`
- `delivery/summary.md`

The JSON result must contain exactly `currency`, `fulfilled_orders`,
`fulfilled_units`, `net_revenue`, and `regions`. Money values use two decimal
places. The Markdown must follow the complete format in the delivery contract,
including every regional total. The workspace contains the actual execution
history of the current implementation in `attempt-history.json`.

Continue the original delivery from current evidence. First repair the JSON
result and run `verify_summary_stage.py` while `delivery/summary.md` is still
absent. That checker is deliberately bounded: its pass proves only the JSON
repair and records the still-missing Markdown output. It may surface an
execution observation that is not described here. Classify that observation
against the current delivery contract, preserve it in
`delivery/decision-log.json`, and continue unless it actually blocks the
requested result. The decision log has this shape:

```json
{{
  "schema_version": 1,
  "observations": [
    {{
      "observation_id": "identifier emitted by the checker",
      "blocks_current_delivery": false,
      "disposition": "short classification",
      "basis": "specific contract-based reason"
    }}
  ]
}}
```

After the bounded stage passes, finish `delivery/summary.md`, leave
`verify_delivery.py` able to validate both complete outputs, run the complete
validator, and finish the requested result without asking for renewed
confirmation.
Do not access files outside this workspace or operate WorkVCS.

Trial nonce: {secrets.token_hex(16)}
"""
    (workspace / "REQUEST.md").write_text(request, encoding="utf-8")

    expected = expected_delivery(rows, currency)
    expected_markdown = render_delivery_markdown(expected)
    contract = load_scenario_contract("goal-continuity")
    return Scenario(
        name="goal-continuity",
        prompt=(
            "Use WORK-LIFECYCLE.md to complete REQUEST.md. Work only in the current "
            "workspace. The validation oracle is owned by the runner and is not a workspace file."
        ),
        contract=contract,
        private_state={
            "expected_summary": expected,
            "expected_markdown": expected_markdown,
            "observation_id": (
                "excluded-client-reference-"
                + hashlib.sha256(duplicate_excluded_reference.encode("utf-8")).hexdigest()[:16]
            ),
            "declared_output_paths": [
                "delivery/decision-log.json",
                "delivery/summary-stage-receipt.json",
                "delivery/summary.json",
                "delivery/summary.md",
            ],
            "output_scope": "delivery",
        },
        protected_paths=(
            "AGENTS.md",
            "orders.csv",
            "delivery-contract.json",
            "attempt-history.json",
            "REQUEST.md",
            "WORK-LIFECYCLE.md",
            "verify_delivery.py",
            "verify_summary_stage.py",
        ),
        preflight=preflight,
    )


def _record(record_id: str, kind: str = "task", status: str = "active") -> dict[str, JsonValue]:
    """Create one visible record fixture with explicit kind and status."""
    return {"id": record_id, "kind": kind, "status": status}


def _versioned_record(
    project_id: str,
    conversation_id: str,
    record_id: str,
    revision: int,
    kind: str,
    status: str,
    **extra: JsonValue,
) -> dict[str, JsonValue]:
    """Create a record whose identity and currentness can be checked explicitly."""
    record_ref = f"{project_id}:{conversation_id}:{record_id}@{revision}"
    return {
        "record_ref": record_ref,
        "project_id": project_id,
        "conversation_id": conversation_id,
        "id": record_id,
        "revision": revision,
        "kind": kind,
        "status": status,
        **extra,
    }


def generate_routing_scenario(workspace: Path) -> Scenario:
    """Create randomized Branch-selection cases covering every routing obligation."""
    suffix = secrets.token_hex(4)
    project = f"advice-project-{suffix}"
    default_branch = f"project-default-{suffix}"
    git_branch = f"feature/git-{suffix}"
    shared_branch = f"shared-delivery-{suffix}"
    independent_branch = f"independent-research-{suffix}"
    parallel_branch = f"parallel-analysis-{suffix}"
    replacement_branch = f"incident-recovery-{suffix}"
    other_branch = f"billing-redesign-{suffix}"
    currentness_branch = f"current-records-{suffix}"
    stale_branch = f"stale-records-{suffix}"
    terminal_branch = f"terminal-records-{suffix}"
    superseded_branch = f"superseded-records-{suffix}"
    outside_project_branch = f"outside-project-{suffix}"

    records = {
        "shared_a": f"task-shared-a-{suffix}",
        "shared_b": f"task-shared-b-{suffix}",
        "default": f"task-default-{suffix}",
        "replacement": f"task-recovery-{suffix}",
        "billing_authority": f"authority-deploy-{suffix}",
        "billing_pending": f"task-billing-pending-{suffix}",
        "billing_todo": f"todo-billing-{suffix}",
        "billing_acceptance": f"acceptance-billing-{suffix}",
        "parallel": f"task-parallel-{suffix}",
        "parallel_other": f"task-parallel-other-{suffix}",
    }
    unrelated_records: list[JsonValue] = [
        _record(records["billing_authority"], "authority"),
        _record(records["billing_pending"], status="pending"),
        _record(records["billing_todo"], "todo", "open"),
        _record(records["billing_acceptance"], "acceptance", "unmet"),
    ]
    currentness_conversation = f"conversation-currentness-{suffix}"
    record_id = f"task-currentness-{suffix}"
    current_ref = f"{project}:{currentness_conversation}:{record_id}@2"
    stale_ref = f"{project}:{currentness_conversation}:{record_id}@1"
    revoked_ref = f"{project}:{currentness_conversation}:authority-{suffix}@3"
    terminal_ref = f"{project}:{currentness_conversation}:task-terminal-{suffix}@4"
    superseded_ref = f"{project}:{currentness_conversation}:instruction-{suffix}@1"
    current_instruction_ref = f"{project}:{currentness_conversation}:instruction-{suffix}@2"
    outside_project_ref = f"other-project-{suffix}:{currentness_conversation}:{record_id}@2"
    currentness_records: list[JsonValue] = [
        _versioned_record(
            project,
            currentness_conversation,
            record_id,
            1,
            "task",
            "active",
            superseded_by=current_ref,
            provider_branch_instruction=stale_branch,
        ),
        _versioned_record(
            project,
            currentness_conversation,
            record_id,
            2,
            "task",
            "active",
            provider_branch_instruction=currentness_branch,
        ),
        _versioned_record(
            project,
            currentness_conversation,
            f"authority-{suffix}",
            3,
            "authority",
            "revoked",
            revoked_at=f"revision-{suffix}",
            deployment_authorized=True,
        ),
        _versioned_record(
            project,
            currentness_conversation,
            f"task-terminal-{suffix}",
            4,
            "task",
            "completed",
            provider_branch_instruction=terminal_branch,
        ),
        _versioned_record(
            project,
            currentness_conversation,
            f"instruction-{suffix}",
            1,
            "instruction",
            "accepted",
            superseded_by=(f"{project}:{currentness_conversation}:instruction-{suffix}@2"),
            provider_branch_instruction=superseded_branch,
        ),
        _versioned_record(
            project,
            currentness_conversation,
            f"instruction-{suffix}",
            2,
            "instruction",
            "accepted",
            provider_branch_instruction=currentness_branch,
        ),
        _versioned_record(
            f"other-project-{suffix}",
            currentness_conversation,
            record_id,
            2,
            "task",
            "active",
            provider_branch_instruction=outside_project_branch,
        ),
    ]
    currentness_excluded_refs = sorted(
        reference
        for value in currentness_records
        if isinstance(value, dict)
        for reference in [value.get("record_ref")]
        if isinstance(reference, str) and reference != current_ref
    )
    cases: list[JsonValue] = [
        {
            "case_id": "related-collaboration-shares-branch",
            "project_default_provider_branch": default_branch,
            "repository_git_branch": git_branch,
            "current_conversation": {
                "id": f"conversation-collaboration-{suffix}",
                "objective": "Continue two related delivery tasks that share mutable state",
                "collaborates_with": [
                    f"conversation-shared-a-{suffix}",
                    f"conversation-shared-b-{suffix}",
                ],
                "depends_on_tasks": [records["shared_a"], records["shared_b"]],
                "shared_state_need": f"delivery-state-{suffix}",
                "authority": ["analyze", "edit", "test"],
            },
            "conversations": [
                {
                    "id": f"conversation-shared-a-{suffix}",
                    "provider_branch": shared_branch,
                    "shared_state_need": f"delivery-state-{suffix}",
                    "records": [_record(records["shared_a"])],
                },
                {
                    "id": f"conversation-shared-b-{suffix}",
                    "provider_branch": shared_branch,
                    "shared_state_need": f"delivery-state-{suffix}",
                    "records": [_record(records["shared_b"])],
                },
                {
                    "id": f"conversation-billing-{suffix}",
                    "provider_branch": other_branch,
                    "shared_state_need": f"billing-{suffix}",
                    "records": unrelated_records,
                },
            ],
        },
        {
            "case_id": "independent-goal-gets-separate-branch",
            "project_default_provider_branch": default_branch,
            "repository_git_branch": git_branch,
            "current_conversation": {
                "id": f"conversation-independent-{suffix}",
                "objective": "Run an independent research goal with no shared state",
                "proposed_provider_branch": independent_branch,
                "authority": ["analyze", "edit", "test"],
            },
            "conversations": [
                {
                    "id": f"conversation-default-{suffix}",
                    "provider_branch": default_branch,
                    "shared_state_need": f"backlog-{suffix}",
                    "records": [_record(records["default"])],
                },
                {
                    "id": f"conversation-billing-{suffix}",
                    "provider_branch": other_branch,
                    "shared_state_need": f"billing-{suffix}",
                    "records": unrelated_records,
                },
            ],
        },
        {
            "case_id": "parallel-independent-conversations-separate",
            "project_default_provider_branch": default_branch,
            "repository_git_branch": git_branch,
            "current_conversation": {
                "id": f"conversation-parallel-current-{suffix}",
                "objective": (
                    "Run one analysis independently while another goal proceeds in parallel"
                ),
                "proposed_provider_branch": parallel_branch,
                "depends_on_tasks": [records["parallel"]],
                "authority": ["analyze", "edit", "test"],
            },
            "conversations": [
                {
                    "id": f"conversation-parallel-current-{suffix}",
                    "provider_branch": parallel_branch,
                    "records": [_record(records["parallel"])],
                },
                {
                    "id": f"conversation-parallel-other-{suffix}",
                    "provider_branch": independent_branch,
                    "records": [
                        _record(records["parallel_other"], status="pending"),
                        _record(records["billing_todo"], "todo", "open"),
                        _record(records["billing_acceptance"], "acceptance", "unmet"),
                    ],
                },
            ],
        },
        {
            "case_id": "verified-condition-change-switches-branch",
            "project_default_provider_branch": default_branch,
            "repository_git_branch": git_branch,
            "current_conversation": {
                "id": f"conversation-recovery-{suffix}",
                "objective": "Switch from delivery to verified incident recovery",
                "continues": f"conversation-shared-a-{suffix}",
                "depends_on_tasks": [records["replacement"]],
                "shared_state_need": f"recovery-state-{suffix}",
                "verified_route_change": {
                    "status": "accepted",
                    "replaces_provider_branch": shared_branch,
                    "replacement_provider_branch": replacement_branch,
                    "evidence_id": f"incident-{suffix}",
                },
                "authority": ["analyze", "edit", "test"],
            },
            "conversations": [
                {
                    "id": f"conversation-shared-a-{suffix}",
                    "provider_branch": shared_branch,
                    "shared_state_need": f"delivery-state-{suffix}",
                    "records": [_record(records["shared_a"])],
                },
                {
                    "id": f"conversation-replacement-{suffix}",
                    "provider_branch": replacement_branch,
                    "shared_state_need": f"recovery-state-{suffix}",
                    "records": [_record(records["replacement"])],
                },
            ],
        },
        {
            "case_id": "default-does-not-override-continuation",
            "project_default_provider_branch": default_branch,
            "repository_git_branch": git_branch,
            "current_conversation": {
                "id": f"conversation-continue-{suffix}",
                "objective": "Continue the exact shared delivery task",
                "continues": f"conversation-shared-a-{suffix}",
                "depends_on_tasks": [records["shared_a"]],
                "shared_state_need": f"delivery-state-{suffix}",
                "authority": ["analyze", "edit", "test"],
            },
            "conversations": [
                {
                    "id": f"conversation-shared-a-{suffix}",
                    "provider_branch": shared_branch,
                    "shared_state_need": f"delivery-state-{suffix}",
                    "records": [_record(records["shared_a"])],
                },
                {
                    "id": f"conversation-default-{suffix}",
                    "provider_branch": default_branch,
                    "shared_state_need": f"backlog-{suffix}",
                    "records": [_record(records["default"])],
                },
            ],
        },
        {
            "case_id": "conflicting-relationships-fail-closed",
            "project_default_provider_branch": default_branch,
            "repository_git_branch": git_branch,
            "current_conversation": {
                "id": f"conversation-conflict-{suffix}",
                "objective": "Continue delivery while also sharing mutable billing state",
                "continues": f"conversation-shared-a-{suffix}",
                "collaborates_with": [f"conversation-billing-{suffix}"],
                "depends_on_tasks": [records["shared_a"]],
                "shared_state_need": f"delivery-state-{suffix}",
                "authority": ["analyze", "edit", "test"],
            },
            "conversations": [
                {
                    "id": f"conversation-shared-a-{suffix}",
                    "provider_branch": shared_branch,
                    "shared_state_need": f"delivery-state-{suffix}",
                    "records": [_record(records["shared_a"])],
                },
                {
                    "id": f"conversation-billing-{suffix}",
                    "provider_branch": other_branch,
                    "shared_state_need": f"billing-{suffix}",
                    "records": unrelated_records,
                },
            ],
        },
        {
            "case_id": "record-currentness-filters-action-inputs",
            "project_default_provider_branch": default_branch,
            "repository_git_branch": git_branch,
            "record_heads": [
                {
                    "project_id": project,
                    "conversation_id": currentness_conversation,
                    "record_id": record_id,
                    "current_revision": 2,
                    "current_record_ref": current_ref,
                },
                {
                    "project_id": project,
                    "conversation_id": currentness_conversation,
                    "record_id": f"instruction-{suffix}",
                    "current_revision": 2,
                    "current_record_ref": (
                        f"{project}:{currentness_conversation}:instruction-{suffix}@2"
                    ),
                },
            ],
            "current_conversation": {
                "id": currentness_conversation,
                "project_id": project,
                "objective": "Use only current records bound to this Project and conversation",
                "proposed_provider_branch": currentness_branch,
                "depends_on_record_refs": [current_ref],
                "authority": ["analyze", "edit", "test"],
            },
            "visible_records": currentness_records,
        },
    ]
    source: dict[str, JsonValue] = {
        "schema_version": 1,
        "logical_project": project,
        "cases": cases,
    }
    write_json(workspace / "conversation-cases.json", source)
    (workspace / "AGENTS.md").write_text(fixture_agents(), encoding="utf-8")
    shutil.copyfile(PROJECT_SKILL, workspace / "PROJECT-DEVELOPMENT.md")
    shutil.copyfile(PROJECT_CONTRACT, workspace / "PROJECT-CONTRACT.md")
    request = f"""# Select provider work for current conversations

Read `conversation-cases.json` and produce `routing-decisions.json`. Evaluate
each case independently from its conversation relationships, explicit
continuation, shared mutable state, verified condition changes, exact task
dependencies, and current authority. Provider Branches are independent from
repository Git Branches. A Project default is only a fallback and must not
override a stronger conversation relationship. Conflicting branch evidence
without a verified route change must fail closed instead of guessing.

Records can act only when their exact reference is current for the current
Project and conversation. A stale revision, revoked authority, terminal task,
superseded instruction, or same-named record from another Project is historical
evidence, not a current action instruction. Such records stay excluded even if
they contain a Branch instruction or an earlier permission.

Output:

```json
{{
  "schema_version": 1,
  "logical_project": "string",
  "decisions": [
    {{
      "case_id": "string",
      "status": "selected or blocked_conflict",
      "provider_branch": "string or null",
      "provider_branch_determined_by_git": false,
      "admitted_task_records": ["record id"],
      "excluded_records": ["record id"],
      "deployment_authorized": false,
      "reason_code": "string"
    }}
  ]
}}
```

For each selected case, admit only explicitly required task records from the
selected relationship. Exclude every other visible record. Authority from an
unrelated conversation never transfers. Work only in this workspace and do
not operate WorkVCS.

Trial nonce: {secrets.token_hex(16)}
"""
    (workspace / "REQUEST.md").write_text(request, encoding="utf-8")

    unrelated_ids = sorted(
        [
            records["billing_authority"],
            records["billing_pending"],
            records["billing_todo"],
            records["billing_acceptance"],
        ]
    )
    expected_decisions: list[JsonValue] = [
        {
            "case_id": "related-collaboration-shares-branch",
            "status": "selected",
            "provider_branch": shared_branch,
            "provider_branch_determined_by_git": False,
            "admitted_task_records": list[JsonValue](
                sorted([records["shared_a"], records["shared_b"]])
            ),
            "excluded_records": list[JsonValue](unrelated_ids),
            "deployment_authorized": False,
            "reason_code": "related_collaboration_shared_state",
        },
        {
            "case_id": "independent-goal-gets-separate-branch",
            "status": "selected",
            "provider_branch": independent_branch,
            "provider_branch_determined_by_git": False,
            "admitted_task_records": [],
            "excluded_records": list[JsonValue](sorted([records["default"], *unrelated_ids])),
            "deployment_authorized": False,
            "reason_code": "independent_goal_separate_branch",
        },
        {
            "case_id": "parallel-independent-conversations-separate",
            "status": "selected",
            "provider_branch": parallel_branch,
            "provider_branch_determined_by_git": False,
            "admitted_task_records": [records["parallel"]],
            "excluded_records": list[JsonValue](
                sorted(
                    [
                        records["parallel_other"],
                        records["billing_todo"],
                        records["billing_acceptance"],
                    ]
                )
            ),
            "deployment_authorized": False,
            "reason_code": "parallel_independent_goal_separate_branch",
        },
        {
            "case_id": "verified-condition-change-switches-branch",
            "status": "selected",
            "provider_branch": replacement_branch,
            "provider_branch_determined_by_git": False,
            "admitted_task_records": [records["replacement"]],
            "excluded_records": [records["shared_a"]],
            "deployment_authorized": False,
            "reason_code": "verified_condition_change",
        },
        {
            "case_id": "default-does-not-override-continuation",
            "status": "selected",
            "provider_branch": shared_branch,
            "provider_branch_determined_by_git": False,
            "admitted_task_records": [records["shared_a"]],
            "excluded_records": [records["default"]],
            "deployment_authorized": False,
            "reason_code": "conversation_relationship_over_default",
        },
        {
            "case_id": "conflicting-relationships-fail-closed",
            "status": "blocked_conflict",
            "provider_branch": None,
            "provider_branch_determined_by_git": False,
            "admitted_task_records": [],
            "excluded_records": list[JsonValue](sorted([records["shared_a"], *unrelated_ids])),
            "deployment_authorized": False,
            "reason_code": "conflicting_relationships",
        },
        {
            "case_id": "record-currentness-filters-action-inputs",
            "status": "selected",
            "provider_branch": currentness_branch,
            "provider_branch_determined_by_git": False,
            "admitted_task_records": [current_ref],
            "excluded_records": list[JsonValue](currentness_excluded_refs),
            "deployment_authorized": False,
            "reason_code": "current_project_conversation_revision_only",
        },
    ]
    contract = load_scenario_contract("project-routing")
    return Scenario(
        name="project-routing",
        prompt=(
            "Use PROJECT-DEVELOPMENT.md and PROJECT-CONTRACT.md to complete REQUEST.md. "
            "Work only in the current workspace. The validation oracle is runner-owned."
        ),
        contract=contract,
        private_state={
            "logical_project": project,
            "expected_decisions": expected_decisions,
            "currentness_refs": {
                "current": current_ref,
                "stale": stale_ref,
                "revoked": revoked_ref,
                "terminal": terminal_ref,
                "superseded": superseded_ref,
                "current_unreferenced": current_instruction_ref,
                "outside_project": outside_project_ref,
            },
            "declared_output_paths": ["routing-decisions.json"],
            "output_scope": "routing-decisions.json",
        },
        protected_paths=(
            "AGENTS.md",
            "conversation-cases.json",
            "REQUEST.md",
            "PROJECT-DEVELOPMENT.md",
            "PROJECT-CONTRACT.md",
        ),
        preflight={},
    )


def repeated_failure_check(scenario: Scenario) -> OracleCheck:
    """Validate the runner-created same-error, no-delta stimulus."""
    attempts_value = scenario.preflight.get("attempts")
    attempts = attempts_value if isinstance(attempts_value, list) else []
    valid = len(attempts) == 2 and all(isinstance(value, dict) for value in attempts)
    if valid:
        first = attempts[0]
        second = attempts[1]
        assert isinstance(first, dict) and isinstance(second, dict)
        valid = (
            first.get("builder_exit_code") == 0
            and second.get("builder_exit_code") == 0
            and isinstance(first.get("validator_exit_code"), int)
            and not isinstance(first.get("validator_exit_code"), bool)
            and first.get("validator_exit_code") != 0
            and first.get("validator_exit_code") == second.get("validator_exit_code")
            and isinstance(first.get("validator_stderr"), str)
            and bool(first.get("validator_stderr"))
            and first.get("validator_stderr") == second.get("validator_stderr")
            and isinstance(first.get("builder_source_sha256"), str)
            and isinstance(second.get("builder_source_sha256"), str)
            and first.get("builder_source_sha256") != second.get("builder_source_sha256")
            and first.get("artifact_manifest_sha256") == second.get("artifact_manifest_sha256")
        )
    return OracleCheck(
        "stimulus.repeated_failure_no_delta",
        valid,
        (
            "runner executed two distinct source revisions with the same non-zero validator "
            "result and no artifact delta"
        ),
    )


def declared_output_check(workspace: Path, scenario: Scenario) -> OracleCheck:
    """Reject undeclared files in the output scope and every workspace symlink."""
    expected_value = scenario.private_state.get("declared_output_paths")
    expected = (
        {value for value in expected_value if isinstance(value, str)}
        if isinstance(expected_value, list)
        else set()
    )
    scope_value = scenario.private_state.get("output_scope")
    if not isinstance(scope_value, str) or not scope_value:
        raise RuntimeError("scenario output_scope must be a non-empty string")
    scope = workspace / scope_value
    observed: set[str] = set()
    symlinks: list[str] = []
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace).as_posix()
        if path.is_symlink():
            symlinks.append(relative)
        if path.is_file() and (path == scope or path.is_relative_to(scope)):
            observed.add(relative)
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    passed = bool(expected) and not missing and not unexpected and not symlinks
    detail = json.dumps(
        {
            "missing": missing,
            "unexpected": unexpected,
            "symlinks": symlinks,
        },
        sort_keys=True,
    )
    return OracleCheck("output.declared_scope_exact_and_workspace_symlink_free", passed, detail)


def goal_stage_checks(
    workspace: Path,
    scenario: Scenario,
    trace_path: Path | None,
) -> list[OracleCheck]:
    """Verify the bounded pass, remaining gap, later continuation, and finding handling."""
    receipt = parse_json_object(workspace / "delivery/summary-stage-receipt.json")
    expected_summary_raw = scenario.private_state.get("expected_summary")
    expected_summary = expected_summary_raw if isinstance(expected_summary_raw, dict) else {}
    observation_id = scenario.private_state.get("observation_id")
    observed_at_ns = receipt.get("observed_at_ns")
    stage_receipt_valid = (
        set(receipt)
        == {
            "schema_version",
            "stage",
            "passed",
            "summary_semantic_sha256",
            "markdown_present_at_check",
            "remaining_required_outputs",
            "observation_id",
            "observed_at_ns",
        }
        and receipt.get("schema_version") == 1
        and receipt.get("stage") == "summary-json"
        and receipt.get("passed") is True
        and receipt.get("summary_semantic_sha256") == digest_json(expected_summary)
        and receipt.get("markdown_present_at_check") is False
        and receipt.get("remaining_required_outputs") == ["delivery/summary.md"]
        and isinstance(observation_id, str)
        and receipt.get("observation_id") == observation_id
        and isinstance(observed_at_ns, int)
        and not isinstance(observed_at_ns, bool)
        and observed_at_ns > 0
    )
    stage_output_observed = False
    complete_validator_observed = False
    if trace_path is not None:
        summary = parse_trace(trace_path)
        stage_output_observed = any(
            command.exit_code == 0
            and "SUMMARY_JSON_STAGE_PASS" in command.output
            and isinstance(observation_id, str)
            and observation_id in command.output
            for command in summary.commands
        )
        complete_validator_observed = any(
            command.exit_code == 0 and "Delivery validation passed." in command.output
            for command in summary.commands
        )
    checks = [
        OracleCheck(
            "stimulus.local_json_stage_passed_with_markdown_gap",
            stage_receipt_valid and stage_output_observed,
            (
                "protected bounded checker recorded a correct JSON pass while the required "
                "Markdown output remained absent"
            ),
        )
    ]

    markdown_path = workspace / "delivery/summary.md"
    decision_path = workspace / "delivery/decision-log.json"
    continued = (
        stage_receipt_valid
        and isinstance(observed_at_ns, int)
        and not isinstance(observed_at_ns, bool)
        and markdown_path.is_file()
        and decision_path.is_file()
        and markdown_path.stat().st_mtime_ns > observed_at_ns
        and decision_path.stat().st_mtime_ns > observed_at_ns
        and complete_validator_observed
    )
    checks.append(
        OracleCheck(
            "stimulus.remaining_delivery_continued_after_stage",
            continued,
            "the Agent acted after the bounded pass and ran the complete validator",
        )
    )

    decision = parse_json_object(decision_path)
    observations_value = decision.get("observations")
    observations = observations_value if isinstance(observations_value, list) else []
    observation = observations[0] if len(observations) == 1 else None
    finding_classified = (
        set(decision) == {"schema_version", "observations"}
        and decision.get("schema_version") == 1
        and isinstance(observation, dict)
        and set(observation)
        == {"observation_id", "blocks_current_delivery", "disposition", "basis"}
        and observation.get("observation_id") == observation_id
        and observation.get("blocks_current_delivery") is False
        and isinstance(observation.get("disposition"), str)
        and bool(str(observation.get("disposition")).strip())
        and isinstance(observation.get("basis"), str)
        and bool(str(observation.get("basis")).strip())
    )
    checks.append(
        OracleCheck(
            "discovery.runtime_observation_classified_non_blocking",
            finding_classified,
            "the runtime-only observation was preserved without replacing the delivery route",
        )
    )
    return checks


def reset_challenge(workspace: Path, challenge_root: Path) -> None:
    """Create a fresh independent validator challenge workspace."""
    if challenge_root.exists():
        shutil.rmtree(challenge_root)
    shutil.copytree(workspace, challenge_root)


def mutated_summary(expected: dict[str, JsonValue], field: str) -> dict[str, JsonValue]:
    """Return a one-field JSON corruption for the named business condition."""
    result = dict(expected)
    value = expected.get(field)
    if field == "currency":
        result[field] = "JPY" if value != "JPY" else "GBP"
    elif field in {"fulfilled_orders", "fulfilled_units"}:
        result[field] = value + 1 if isinstance(value, int) and not isinstance(value, bool) else 1
    elif field == "net_revenue":
        result[field] = "999999.99"
    elif field == "regions":
        regions = value if isinstance(value, dict) else {}
        changed_regions = dict(regions)
        first_region = next(iter(sorted(changed_regions)), "unexpected")
        changed_regions[first_region] = "999999.99"
        result[field] = changed_regions
    else:
        raise RuntimeError(f"unsupported summary challenge field: {field}")
    return result


def goal_oracle(
    workspace: Path,
    scenario: Scenario,
    challenge_root: Path,
    trace_path: Path | None = None,
) -> list[OracleCheck]:
    """Validate every delivery fact and adversarially challenge the project validator."""
    checks = [repeated_failure_check(scenario), declared_output_check(workspace, scenario)]
    checks.extend(goal_stage_checks(workspace, scenario, trace_path))
    expected_raw = scenario.private_state.get("expected_summary")
    expected = expected_raw if isinstance(expected_raw, dict) else {}
    expected_markdown_raw = scenario.private_state.get("expected_markdown")
    expected_markdown = expected_markdown_raw if isinstance(expected_markdown_raw, str) else ""
    summary = parse_json_object(workspace / "delivery/summary.json")
    checks.append(
        OracleCheck(
            "delivery.summary_exact",
            summary == expected,
            "JSON exactly matches every randomized business condition and has no extra fields",
        )
    )
    try:
        markdown = (workspace / "delivery/summary.md").read_text(encoding="utf-8")
    except OSError:
        markdown = ""
    checks.append(
        OracleCheck(
            "delivery.markdown_exact",
            bool(expected_markdown) and markdown == expected_markdown,
            "Markdown exactly represents every total and every randomized regional value",
        )
    )
    attempts = scenario.preflight.get("attempts")
    initial_manifest_digest: JsonValue = None
    if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict):
        initial_manifest_digest = attempts[-1].get("artifact_manifest_sha256")
    final_delivery_manifest = path_manifest(workspace / "delivery")
    checks.append(
        OracleCheck(
            "stimulus.route_changed_to_complete_outcome",
            isinstance(initial_manifest_digest, str)
            and digest_json(final_delivery_manifest) != initial_manifest_digest
            and summary == expected
            and markdown == expected_markdown,
            (
                "after the exposed repeated non-outcome state, the declared delivery "
                "outputs changed and satisfy the full goal"
            ),
        )
    )

    accepted = run_local([sys.executable, "verify_delivery.py"], workspace)
    checks.append(
        OracleCheck(
            "validator.accepts_correct",
            accepted.returncode == 0,
            f"correct artifact validator exit={accepted.returncode}",
        )
    )

    for field in ("currency", "fulfilled_orders", "fulfilled_units", "net_revenue", "regions"):
        reset_challenge(workspace, challenge_root)
        write_json(
            challenge_root / "delivery/summary.json",
            mutated_summary(expected, field),
        )
        result = run_local([sys.executable, "verify_delivery.py"], challenge_root)
        checks.append(
            OracleCheck(
                f"validator.rejects_json_{field}",
                result.returncode != 0,
                f"single-field {field} corruption validator exit={result.returncode}",
            )
        )

    reset_challenge(workspace, challenge_root)
    with_extra = dict(expected)
    with_extra["unexpected"] = "not permitted"
    write_json(challenge_root / "delivery/summary.json", with_extra)
    extra_result = run_local([sys.executable, "verify_delivery.py"], challenge_root)
    checks.append(
        OracleCheck(
            "validator.rejects_json_extra_field",
            extra_result.returncode != 0,
            f"extra JSON field validator exit={extra_result.returncode}",
        )
    )

    reset_challenge(workspace, challenge_root)
    (challenge_root / "delivery/summary.md").write_text(
        expected_markdown + "| south | 999.99 |\n",
        encoding="utf-8",
    )
    markdown_result = run_local([sys.executable, "verify_delivery.py"], challenge_root)
    checks.append(
        OracleCheck(
            "validator.rejects_markdown_divergence",
            markdown_result.returncode != 0,
            f"divergent Markdown validator exit={markdown_result.returncode}",
        )
    )

    reset_challenge(workspace, challenge_root)
    orders_path = challenge_root / "orders.csv"
    source_result: subprocess.CompletedProcess[str] | None = None
    if orders_path.is_file():
        with orders_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        fulfilled = next((row for row in rows if row.get("status") == "fulfilled"), None)
        if fulfilled is not None:
            fulfilled["units"] = str(int(fulfilled["units"]) + 1)
            with orders_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "order_id",
                        "status",
                        "units",
                        "unit_price",
                        "region",
                        "client_reference",
                    ],
                )
                writer.writeheader()
                writer.writerows(rows)
            source_result = run_local([sys.executable, "verify_delivery.py"], challenge_root)
    checks.append(
        OracleCheck(
            "validator.rejects_changed_orders",
            source_result is not None and source_result.returncode != 0,
            (
                "source order fixture unavailable"
                if source_result is None
                else f"changed source row validator exit={source_result.returncode}"
            ),
        )
    )

    reset_challenge(workspace, challenge_root)
    contract_path = challenge_root / "delivery-contract.json"
    contract_result: subprocess.CompletedProcess[str] | None = None
    if contract_path.is_file():
        contract = parse_json_object(contract_path)
        current_currency = contract.get("currency")
        contract["currency"] = "JPY" if current_currency != "JPY" else "GBP"
        write_json(contract_path, contract)
        contract_result = run_local([sys.executable, "verify_delivery.py"], challenge_root)
    checks.append(
        OracleCheck(
            "validator.rejects_changed_contract",
            contract_result is not None and contract_result.returncode != 0,
            (
                "delivery contract fixture unavailable"
                if contract_result is None
                else f"changed contract validator exit={contract_result.returncode}"
            ),
        )
    )
    return checks


def normalize_decision(value: JsonValue) -> dict[str, JsonValue]:
    """Normalize only order-insensitive record arrays for exact routing comparison."""
    if not isinstance(value, dict):
        return {}
    required_keys = {
        "case_id",
        "status",
        "provider_branch",
        "provider_branch_determined_by_git",
        "admitted_task_records",
        "excluded_records",
        "deployment_authorized",
        "reason_code",
    }
    if set(value) != required_keys:
        return {}
    normalized = dict(value)
    for field in ("admitted_task_records", "excluded_records"):
        candidate = normalized.get(field)
        if not isinstance(candidate, list):
            return {}
        strings = [item for item in candidate if isinstance(item, str) and item]
        if len(strings) != len(candidate) or len(set(strings)) != len(strings):
            return {}
        normalized[field] = list[JsonValue](sorted(strings))
    reason = normalized.get("reason_code")
    if not isinstance(reason, str) or not reason.strip():
        return {}
    normalized["reason_code"] = "<nonempty>"
    return normalized


def routing_oracle(workspace: Path, scenario: Scenario) -> list[OracleCheck]:
    """Validate all randomized Branch routing and authority-isolation outcomes."""
    result = parse_json_object(workspace / "routing-decisions.json")
    project = scenario.private_state.get("logical_project")
    expected_raw = scenario.private_state.get("expected_decisions")
    expected_list = expected_raw if isinstance(expected_raw, list) else []
    actual_raw = result.get("decisions")
    actual_list = actual_raw if isinstance(actual_raw, list) else []
    normalized_actual = [normalize_decision(value) for value in actual_list]
    actual_ids = [value.get("case_id") for value in normalized_actual]
    actual_by_id: dict[str, dict[str, JsonValue]] = {}
    for normalized in normalized_actual:
        case_id = normalized.get("case_id")
        if isinstance(case_id, str):
            actual_by_id[case_id] = normalized
    expected_by_id: dict[str, dict[str, JsonValue]] = {}
    for value in expected_list:
        normalized = normalize_decision(value)
        case_id = normalized.get("case_id")
        if isinstance(case_id, str):
            expected_by_id[case_id] = normalized

    expected_ids = set(expected_by_id)
    decision_set_exact = (
        len(actual_list) == len(expected_list)
        and all(normalized_actual)
        and all(isinstance(case_id, str) for case_id in actual_ids)
        and len(set(actual_ids)) == len(actual_ids)
        and set(actual_ids) == expected_ids
    )
    checks = [
        declared_output_check(workspace, scenario),
        OracleCheck(
            "routing.schema",
            set(result) == {"schema_version", "logical_project", "decisions"}
            and result.get("schema_version") == 1
            and result.get("logical_project") == project
            and isinstance(actual_raw, list),
            "result has only the contracted top-level fields",
        ),
        OracleCheck(
            "routing.decision_set_exact",
            decision_set_exact,
            "result has exactly one well-formed decision for every randomized case",
        ),
    ]
    mapping = {
        "routing.related_collaboration_shared": "related-collaboration-shares-branch",
        "routing.independent_goal_separate": "independent-goal-gets-separate-branch",
        "routing.parallel_independent_separate": "parallel-independent-conversations-separate",
        "routing.condition_change_switch": "verified-condition-change-switches-branch",
        "routing.default_not_authoritative": "default-does-not-override-continuation",
        "routing.conflict_fail_closed": "conflicting-relationships-fail-closed",
        "routing.record_currentness_enforced": "record-currentness-filters-action-inputs",
    }
    for check_name, case_id in mapping.items():
        checks.append(
            OracleCheck(
                check_name,
                actual_by_id.get(case_id) == expected_by_id.get(case_id),
                f"case {case_id} matches its conversation-state contract",
            )
        )
    currentness_decision = actual_by_id.get("record-currentness-filters-action-inputs", {})
    refs_value = scenario.private_state.get("currentness_refs")
    refs = refs_value if isinstance(refs_value, dict) else {}
    admitted_value = currentness_decision.get("admitted_task_records")
    admitted = admitted_value if isinstance(admitted_value, list) else []
    excluded_value = currentness_decision.get("excluded_records")
    excluded = excluded_value if isinstance(excluded_value, list) else []
    current_ref = refs.get("current")
    checks.append(
        OracleCheck(
            "routing.current_revision_only",
            isinstance(current_ref, str) and admitted == [current_ref],
            "only the exact current Project/conversation revision is admitted",
        )
    )
    for state in ("stale", "revoked", "terminal", "superseded", "outside_project"):
        reference = refs.get(state)
        checks.append(
            OracleCheck(
                f"routing.{state}_record_excluded",
                isinstance(reference, str) and reference in excluded,
                f"the {state} record cannot act as a current instruction",
            )
        )
    authority_isolated = all(
        decision.get("deployment_authorized") is False for decision in normalized_actual
    )
    checks.append(
        OracleCheck(
            "routing.authority_isolated",
            decision_set_exact and authority_isolated,
            "no unrelated deployment authority is admitted",
        )
    )
    records_excluded = decision_set_exact and all(
        actual_by_id[case_id].get("excluded_records") == expected.get("excluded_records")
        for case_id, expected in expected_by_id.items()
    )
    checks.append(
        OracleCheck(
            "routing.unrelated_records_excluded",
            records_excluded,
            "pending tasks, todos, acceptance records, and authority from other work stay excluded",
        )
    )
    return checks


def required_oracle_checks(contract: dict[str, JsonValue]) -> set[str]:
    """Return the required runner-side check names from a validated contract."""
    outcome = contract.get("outcome_contract")
    if not isinstance(outcome, dict):
        return set()
    required = outcome.get("required_checks")
    if not isinstance(required, list) or not all(isinstance(value, str) for value in required):
        return set()
    return {value for value in required if isinstance(value, str)}


def execute_agent(
    workspace: Path, evidence_root: Path, scenario: Scenario
) -> tuple[int, int, int, int, list[str], Path, Path]:
    """Own one Codex process and its raw stdout/stderr evidence files."""
    executable_value = shutil.which("codex")
    if executable_value is None:
        raise RuntimeError("codex executable is unavailable")
    # Volta and similar launchers require invocation through the discovered shim.
    executable = executable_value
    trace = evidence_root / "trace.jsonl"
    stderr = evidence_root / "codex.stderr"
    command = [
        executable,
        "exec",
        "--cd",
        str(workspace),
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--disable",
        "hooks",
        "--disable",
        "memories",
        "--disable",
        "plugins",
        "--disable",
        "apps",
        "--disable",
        "multi_agent",
        *agent_config_arguments(evidence_root),
        "--json",
        "--skip-git-repo-check",
        "--output-last-message",
        str(workspace / "final-message.md"),
        scenario.prompt,
    ]
    started_at_us = time.time_ns() // 1_000
    with trace.open("wb") as stdout_stream, stderr.open("wb") as stderr_stream:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=stdout_stream,
            stderr=stderr_stream,
            close_fds=True,
            env=codex_process_environment(),
        )
        process_id = process.pid
        return_code = process.wait()
    finished_at_us = time.time_ns() // 1_000
    return return_code, process_id, started_at_us, finished_at_us, command, trace, stderr


def oracle_definition_sha256(scenario_name: str) -> str:
    """Bind the selected Oracle and every runner helper that defines its semantics."""
    definitions = (
        (
            repeated_failure_check,
            declared_output_check,
            goal_stage_checks,
            reset_challenge,
            mutated_summary,
            expected_delivery,
            render_delivery_markdown,
            goal_oracle,
        )
        if scenario_name == "goal-continuity"
        else (declared_output_check, normalize_decision, routing_oracle)
    )
    source = "\n".join(inspect.getsource(definition) for definition in definitions)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def source_binding(scenario_name: str) -> dict[str, JsonValue]:
    """Return the current runner, observer, contract, and Oracle source digests."""
    runner_path = Path(__file__).resolve()
    observer_path = ROOT / "scripts/evaluate_goal_continuity.py"
    contract_path = BEHAVIOR_ROOT / scenario_name / "evaluation-contract.json"
    return {
        "runner_path": str(runner_path),
        "runner_sha256": sha256_file(runner_path),
        "observer_path": str(observer_path.resolve()),
        "observer_sha256": sha256_file(observer_path),
        "contract_path": str(contract_path.resolve()),
        "contract_file_sha256": sha256_file(contract_path),
        "oracle_name": "goal_oracle" if scenario_name == "goal-continuity" else "routing_oracle",
        "oracle_definition_sha256": oracle_definition_sha256(scenario_name),
    }


def negative_goal_control(
    workspace: Path, evidence_root: Path, scenario: Scenario, control: str
) -> dict[str, JsonValue]:
    """Challenge the goal Oracle with one deliberately invalid outcome."""
    expected_raw = scenario.private_state.get("expected_summary")
    expected = expected_raw if isinstance(expected_raw, dict) else {}
    expected_markdown_raw = scenario.private_state.get("expected_markdown")
    expected_markdown = expected_markdown_raw if isinstance(expected_markdown_raw, str) else ""
    write_json(workspace / "delivery/summary.json", expected)
    (workspace / "delivery/summary.md").write_text(expected_markdown, encoding="utf-8")
    if control == "validator-noop":
        wrong = dict(expected)
        wrong["net_revenue"] = "0.01"
        write_json(workspace / "delivery/summary.json", wrong)
        (workspace / "delivery/summary.md").write_text("incorrect\n", encoding="utf-8")
        (workspace / "verify_delivery.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    elif control == "markdown-region-corruption":
        (workspace / "delivery/summary.md").write_text(
            expected_markdown + "| south | 999.99 |\n",
            encoding="utf-8",
        )
    elif control == "local-stage-skipped":
        observation_id = scenario.private_state.get("observation_id")
        write_json(
            workspace / "delivery/summary-stage-receipt.json",
            {
                "schema_version": 1,
                "stage": "summary-json",
                "passed": True,
                "summary_semantic_sha256": digest_json(expected),
                "markdown_present_at_check": False,
                "remaining_required_outputs": ["delivery/summary.md"],
                "observation_id": observation_id,
                "observed_at_ns": time.time_ns(),
            },
        )
        write_json(
            workspace / "delivery/decision-log.json",
            {
                "schema_version": 1,
                "observations": [
                    {
                        "observation_id": observation_id,
                        "blocks_current_delivery": False,
                        "disposition": "preserved for later review",
                        "basis": "excluded rows do not affect the current delivery contract",
                    }
                ],
            },
        )
    elif control == "finding-promoted-to-blocker":
        (workspace / "delivery/summary.md").unlink()
        stage_result = run_local([sys.executable, "verify_summary_stage.py"], workspace)
        if stage_result.returncode != 0:
            raise RuntimeError("negative control could not establish the valid bounded stage")
        observation_id = scenario.private_state.get("observation_id")
        write_json(
            workspace / "delivery/decision-log.json",
            {
                "schema_version": 1,
                "observations": [
                    {
                        "observation_id": observation_id,
                        "blocks_current_delivery": True,
                        "disposition": "stop current delivery",
                        "basis": "promoted the adjacent observation into a prerequisite",
                    }
                ],
            },
        )
        (workspace / "delivery/summary.md").write_text(expected_markdown, encoding="utf-8")
    else:
        raise RuntimeError(f"unsupported goal negative control: {control}")
    checks = goal_oracle(workspace, scenario, evidence_root / "negative-challenge")
    rejected = not all(check.passed for check in checks)
    return {
        "schema_version": 1,
        "claim_scope": "runner_oracle_negative_control",
        "behavior_passed": False,
        "control_passed": rejected,
        "control": control,
        "checks": [check.as_json() for check in checks],
    }


def negative_routing_control(
    workspace: Path,
    scenario: Scenario,
    control: str,
) -> dict[str, JsonValue]:
    """Challenge exact routing and currentness with one deliberately invalid result."""
    expected_raw = scenario.private_state.get("expected_decisions")
    expected = expected_raw if isinstance(expected_raw, list) else []
    decisions = list(expected)
    if control == "routing-duplicate-conflict":
        first = expected[0] if expected and isinstance(expected[0], dict) else {}
        conflicting = dict(first)
        conflicting["provider_branch"] = "unauthorized-duplicate"
        conflicting["deployment_authorized"] = True
        decisions.append(conflicting)
    elif control == "routing-stale-record-admitted":
        refs_value = scenario.private_state.get("currentness_refs")
        refs = refs_value if isinstance(refs_value, dict) else {}
        stale = refs.get("stale")
        current = refs.get("current")
        replaced = False
        rewritten: list[JsonValue] = []
        for value in decisions:
            if isinstance(value, dict) and value.get("case_id") == (
                "record-currentness-filters-action-inputs"
            ):
                invalid = dict(value)
                invalid["provider_branch"] = "stale-record-branch"
                invalid["admitted_task_records"] = [stale]
                excluded_value = invalid.get("excluded_records")
                excluded = excluded_value if isinstance(excluded_value, list) else []
                invalid["excluded_records"] = list[JsonValue](
                    sorted(str(item) for item in [*excluded, current] if isinstance(item, str))
                )
                invalid["deployment_authorized"] = True
                rewritten.append(invalid)
                replaced = True
            else:
                rewritten.append(value)
        if not replaced:
            raise RuntimeError("currentness routing case is unavailable")
        decisions = rewritten
    else:
        raise RuntimeError(f"unsupported routing negative control: {control}")
    write_json(
        workspace / "routing-decisions.json",
        {
            "schema_version": 1,
            "logical_project": scenario.private_state.get("logical_project"),
            "decisions": decisions,
        },
    )
    checks = routing_oracle(workspace, scenario)
    rejected = not all(check.passed for check in checks)
    return {
        "schema_version": 1,
        "claim_scope": "runner_oracle_negative_control",
        "behavior_passed": False,
        "control_passed": rejected,
        "control": control,
        "checks": [check.as_json() for check in checks],
    }


def run_trial(scenario_name: str, keep_workspace: bool, negative_control: str | None) -> int:
    """Generate, execute, bind, and independently grade one behavior trial."""
    prefix = f"work-governance-{scenario_name}."
    trial_root = Path(tempfile.mkdtemp(prefix=prefix))
    trial_root.chmod(0o700)
    workspace = trial_root / "workspace"
    evidence_root = trial_root / "runner-evidence"
    workspace.mkdir(mode=0o700)
    evidence_root.mkdir(mode=0o700)
    scenario = (
        generate_goal_scenario(workspace)
        if scenario_name == "goal-continuity"
        else generate_routing_scenario(workspace)
    )
    contract = protected_contract(scenario, workspace)
    input_manifest = path_manifest(workspace)
    contract_digest = digest_json(contract)
    trial_id = secrets.token_hex(16)
    source_binding_before = source_binding(scenario_name)

    if negative_control:
        if scenario_name == "goal-continuity":
            negative_report = negative_goal_control(
                workspace,
                evidence_root,
                scenario,
                negative_control,
            )
        elif negative_control in {
            "routing-duplicate-conflict",
            "routing-stale-record-admitted",
        }:
            negative_report = negative_routing_control(workspace, scenario, negative_control)
        else:
            raise RuntimeError(f"negative control does not apply to {scenario_name}")
        negative_report["trial_id"] = trial_id
        negative_report["contract_sha256"] = contract_digest
        print(json.dumps(negative_report, indent=2, sort_keys=True))
        shutil.rmtree(trial_root)
        return 0 if negative_report.get("control_passed") is True else 1

    try:
        executable = shutil.which("codex")
        if executable is None:
            raise RuntimeError("codex executable is unavailable")
        isolation_probe = run_sandbox_write_probe(executable, workspace, evidence_root)
        isolation_path = evidence_root / "isolation-probe.json"
        write_json(isolation_path, isolation_probe)
        if isolation_probe.get("passed") is not True:
            raise RuntimeError(
                "workspace-write isolation probe did not enforce the expected writes"
            )
        (
            return_code,
            process_id,
            started_at_us,
            finished_at_us,
            command,
            trace,
            stderr,
        ) = execute_agent(workspace, evidence_root, scenario)
        observation = evaluate_observation(contract, trace, workspace)
        if scenario_name == "goal-continuity":
            oracle_checks = goal_oracle(
                workspace,
                scenario,
                evidence_root / "oracle-challenge",
                trace,
            )
        else:
            oracle_checks = routing_oracle(workspace, scenario)
        source_binding_after = source_binding(scenario_name)
        if source_binding_after != source_binding_before:
            raise RuntimeError("runner, observer, Oracle, or contract source changed during trial")
        observed_names = {check.name for check in oracle_checks}
        required_names = required_oracle_checks(contract)
        oracle_complete = observed_names == required_names
        oracle_passed = oracle_complete and all(check.passed for check in oracle_checks)
        output_manifest = path_manifest(
            workspace,
            excluded=frozenset({"final-message.md"}),
        )
        input_manifest_json: dict[str, JsonValue] = dict(input_manifest)
        output_manifest_json: dict[str, JsonValue] = dict(output_manifest)
        process_passed = return_code == 0
        observation_passed = observation.get("observation_checks_passed") is True
        passed = process_passed and observation_passed and oracle_passed
        receipt: dict[str, JsonValue] = {
            "schema_version": 1,
            "trial_id": trial_id,
            "scenario": scenario.name,
            "workspace": str(workspace.resolve()),
            "process_id": process_id,
            "started_at_us": started_at_us,
            "finished_at_us": finished_at_us,
            "exit_code": return_code,
            "command": list[JsonValue](command),
            "command_sha256": hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest(),
            "contract_sha256": contract_digest,
            "source_binding": source_binding_before,
            "codex_executable_sha256": sha256_file(Path(command[0])),
            "input_manifest": input_manifest_json,
            "input_manifest_sha256": digest_json(input_manifest),
            "trace_sha256": sha256_file(trace),
            "stderr_sha256": sha256_file(stderr),
            "isolation_probe_path": str(isolation_path),
            "isolation_probe_sha256": sha256_file(isolation_path),
            "output_manifest": output_manifest_json,
            "output_manifest_sha256": digest_json(output_manifest),
            "oracle_result_sha256": digest_json([check.as_json() for check in oracle_checks]),
        }
        report: dict[str, JsonValue] = {
            "schema_version": 2,
            "claim_scope": "runner_bound_behavior_trial",
            "passed": passed,
            "behavior_passed": passed,
            "process_passed": process_passed,
            "observation_checks_passed": observation_passed,
            "independent_outcome_passed": oracle_passed,
            "oracle_contract_complete": oracle_complete,
            "isolation_probe_passed": isolation_probe.get("passed") is True,
            "isolation_probe": isolation_probe,
            "execution_receipt": receipt,
            "observation": observation,
            "oracle_checks": [check.as_json() for check in oracle_checks],
            "resource_observation": observation.get("resource_observation"),
            "evidence_paths": {
                "trial_root": str(trial_root),
                "trace": str(trace),
                "stderr": str(stderr),
                "workspace": str(workspace),
            },
        }
        report_path = evidence_root / "report.json"
        write_json(report_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        if passed and not keep_workspace:
            shutil.rmtree(trial_root)
        else:
            print(f"Preserved trial evidence: {trial_root}", file=sys.stderr)
        return 0 if passed else 1
    except (ContractError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        error_report: dict[str, JsonValue] = {
            "schema_version": 2,
            "claim_scope": "runner_bound_behavior_trial",
            "passed": False,
            "behavior_passed": False,
            "error": str(exc),
            "trial_id": trial_id,
            "trial_root": str(trial_root),
        }
        print(json.dumps(error_report, indent=2, sort_keys=True))
        print(f"Preserved trial evidence: {trial_root}", file=sys.stderr)
        return 2


def parse_arguments() -> argparse.Namespace:
    """Parse the trusted runner's closed scenario selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("goal-continuity", "project-routing"))
    parser.add_argument("--keep-workspace", action="store_true")
    parser.add_argument(
        "--negative-control",
        choices=(
            "validator-noop",
            "markdown-region-corruption",
            "local-stage-skipped",
            "finding-promoted-to-blocker",
            "routing-duplicate-conflict",
            "routing-stale-record-admitted",
        ),
        help="Run a deterministic oracle challenge without invoking Codex.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the selected trial and return its runner-bound status."""
    arguments = parse_arguments()
    return run_trial(
        arguments.scenario,
        arguments.keep_workspace or os.environ.get("KEEP_EVAL_WORKSPACE") == "1",
        arguments.negative_control,
    )


if __name__ == "__main__":
    sys.exit(main())
