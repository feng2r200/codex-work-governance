import concurrent.futures
import hashlib
import importlib.util
import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-hook-runtime.py"
MANIFEST = ROOT / "plugins" / "work-governance" / "runtime" / "package.json"
RUNTIME = ROOT / "plugins" / "work-governance" / "runtime" / "hook_runtime.py"
HOOKS = ROOT / "plugins" / "work-governance" / "hooks" / "hooks.json"
CONTRACT = "wg-hook-v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def package_digest() -> str:
    return hashlib.sha256(canonical(json.loads(MANIFEST.read_text(encoding="utf-8")))).hexdigest()


def install(home: Path) -> tuple[Path, str]:
    digest = package_digest()
    subprocess.run(
        [str(INSTALLER), "--home", str(home), "package", "--expected-digest", digest],
        check=True,
    )
    subprocess.run(
        [str(INSTALLER), "--home", str(home), "launcher", "--probe-digest", digest],
        check=True,
    )
    return home / ".local" / "bin" / "work-governance-hook", digest


def install_user_hooks(home: Path, digest: str) -> tuple[dict[str, object], Path]:
    completed = subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(home),
            "user-hook",
            "install",
            "--expected-package-digest",
            digest,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout), home / ".codex" / "hooks.json"


def user_hook_status(home: Path, digest: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(home),
            "user-hook",
            "status",
            "--expected-package-digest",
            digest,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def rollback_user_hooks(
    home: Path, digest: str, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(home),
            "user-hook",
            "rollback",
            "--expected-package-digest",
            digest,
        ],
        check=check,
        capture_output=True,
        text=True,
    )


def load_installer_module() -> object:
    spec = importlib.util.spec_from_file_location("hook_runtime_installer", INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_runtime_module() -> object:
    spec = importlib.util.spec_from_file_location("work_governance_hook_runtime", RUNTIME)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def continuation_event() -> dict[str, object]:
    return {
        "schema_version": 1,
        "continuation_enabled": True,
        "durable_provider_available": True,
        "project_opt_in_receipt_kind": "workvcs_project_policy",
        "project_opt_in_receipt_digest": "1" * 64,
        "project_opt_in_revision": 4,
        "project_opt_in_verified_at_us": 1_790_000_000_000_000,
        "project_id": "g-p-continuation-test",
        "scope_id": "01900000-0000-7000-8000-000000000001",
        "workspace_id": "01900000-0000-7000-8000-000000000002",
        "branch_id": "01900000-0000-7000-8000-000000000003",
        "task_entity_id": "01900000-0000-7000-8000-000000000004",
        "listener_session_id": "01900000-0000-7000-8000-000000000005",
        "listener_revision": 3,
        "source_session_id": "01900000-0000-7000-8000-000000000006",
        "source_claim_id": "01900000-0000-7000-8000-000000000007",
        "owner_epoch": 2,
        "handoff_digest": "2" * 64,
        "scope_currentness_digest": "3" * 64,
        "continuation_packet_digest": "4" * 64,
        "continuation_packet_bytes": 4_096,
        "continuation_packet_items": 12,
        "continuation_packet_token_budget": 2_048,
        "initial_message_digest": "5" * 64,
        "adapter_kind": "codex-app",
        "adapter_version": "test-v1",
        "evaluated_at_us": 1_790_000_000_000_000,
        "actor_role": "listener",
        "source_role": "work",
        "target_role": "work_candidate",
        "source_committed": True,
        "source_is_current_carrier": True,
        "source_has_exclusive_claim": True,
        "listener_matches": True,
        "listener_revision_matches": True,
        "scope_currentness_matches": True,
        "project_binding_matches": True,
        "active_rotation": False,
        "prior_rotation_terminal": True,
        "cooldown_satisfied": True,
        "safe_semantic_point": True,
        "handoff_fresh": True,
        "progress_since_last_rotation": True,
        "expected_benefit": "high",
        "continuation_risk": "low",
        "signals": {
            "context_pressure": True,
            "repeated_compaction": False,
            "unchanged_context_replay": True,
            "coordination_drag": False,
        },
        "evidence_references": [
            {
                "kind": "workvcs_record",
                "reference": "record:01900000-0000-7000-8000-000000000008",
                "digest": "6" * 64,
            },
            {
                "kind": "runtime_observation",
                "reference": "observation:continuation-pressure",
                "digest": "7" * 64,
            },
        ],
    }


def managed_commands(config: dict[str, object]) -> list[str]:
    hooks = config["hooks"]
    assert isinstance(hooks, dict)
    commands: list[str] = []
    for groups in hooks.values():
        assert isinstance(groups, list)
        for group in groups:
            assert isinstance(group, dict)
            handlers = group["hooks"]
            assert isinstance(handlers, list)
            for handler in handlers:
                assert isinstance(handler, dict)
                command = handler.get("command")
                if isinstance(command, str) and command.startswith(
                    "$HOME/.local/bin/work-governance-hook dispatch --contract wg-hook-v1 "
                ):
                    commands.append(command)
    return sorted(commands)


def clone_package(home: Path, source_digest: str, marker: str) -> str:
    source = home / ".local/libexec/work-governance" / source_digest
    manifest = json.loads((source / "package.json").read_text(encoding="utf-8"))
    manifest["test_release_marker"] = marker
    digest = hashlib.sha256(canonical(manifest)).hexdigest()
    destination = source.parent / digest
    destination.mkdir(mode=0o700)
    for entry in manifest["files"]:
        shutil.copyfile(source / entry["path"], destination / entry["path"])
        (destination / entry["path"]).chmod(0o600)
    (destination / "package.json").write_bytes(canonical(manifest) + b"\n")
    (destination / "package.json").chmod(0o600)
    return digest


def install_probe_counter_launcher(
    launcher: Path, digest: str, counter: Path, *, fail_after: int | None = None
) -> bytes:
    source = f"""#!/usr/bin/python3 -I
import json
import sys
from pathlib import Path

expected = {digest!r}
counter = Path({str(counter)!r})
value = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(value))
actual = sys.argv[sys.argv.index("--package-digest") + 1]
if actual != expected or ({fail_after!r} is not None and value > {fail_after!r}):
    raise SystemExit(70)
print(json.dumps({{"contract": "wg-hook-v1", "package_digest": actual, "ok": True}}))
""".encode()
    launcher.write_bytes(source)
    launcher.chmod(0o700)
    return source


def invoke(
    launcher: Path,
    home: Path,
    digest: str,
    handler: str,
    event: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(launcher),
            "dispatch",
            "--contract",
            CONTRACT,
            "--package-digest",
            digest,
            "--handler",
            handler,
        ],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/untrusted", "PYTHONPATH": "/untrusted"},
        cwd="/",
        check=False,
    )


def invoke_raw(
    launcher: Path,
    home: Path,
    digest: str,
    handler: str,
    event: bytes,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            str(launcher),
            "dispatch",
            "--contract",
            CONTRACT,
            "--package-digest",
            digest,
            "--handler",
            handler,
        ],
        input=event,
        capture_output=True,
        env={"HOME": str(home), "PATH": "/untrusted", "PYTHONPATH": "/untrusted"},
        cwd="/",
        check=False,
    )


def test_continuation_policy_admits_only_the_nearest_valid_control() -> None:
    runtime = load_runtime_module()
    result = runtime.evaluate_continuation_policy(continuation_event())

    assert result["action"] == "prepare_rotation"
    assert result["causes_product_effects"] is False
    assert result["pressure_signal_count"] == 2
    evaluator_receipt = result["evaluator_receipt"]
    assert isinstance(evaluator_receipt, dict)
    assert evaluator_receipt["evaluator_version"] == "wg-continuation-v1"
    assert evaluator_receipt["action"] == "prepare_rotation"
    assert evaluator_receipt["result"]["action"] == "prepare_rotation"
    assert evaluator_receipt["result"]["gate_summary"] == evaluator_receipt["gate_summary"]
    assert evaluator_receipt["evidence_references"] == continuation_event()["evidence_references"]
    assert (
        result["evaluator_receipt_digest"]
        == hashlib.sha256(canonical(evaluator_receipt)).hexdigest()
    )
    assert result["policy_decision"] == {
        "schema_version": 1,
        "action": "prepare_rotation",
        "continuation_enabled": True,
        "durable_provider_available": True,
        "project_opt_in_receipt_kind": "workvcs_project_policy",
        "project_opt_in_receipt_digest": "1" * 64,
        "project_opt_in_revision": 4,
        "project_opt_in_verified_at_us": 1_790_000_000_000_000,
        "project_id": "g-p-continuation-test",
        "scope_id": "01900000-0000-7000-8000-000000000001",
        "workspace_id": "01900000-0000-7000-8000-000000000002",
        "branch_id": "01900000-0000-7000-8000-000000000003",
        "task_entity_id": "01900000-0000-7000-8000-000000000004",
        "listener_session_id": "01900000-0000-7000-8000-000000000005",
        "listener_revision": 3,
        "source_session_id": "01900000-0000-7000-8000-000000000006",
        "source_claim_id": "01900000-0000-7000-8000-000000000007",
        "owner_epoch": 2,
        "handoff_digest": "2" * 64,
        "scope_currentness_digest": "3" * 64,
        "continuation_packet_digest": "4" * 64,
        "continuation_packet_bytes": 4_096,
        "continuation_packet_items": 12,
        "continuation_packet_token_budget": 2_048,
        "initial_message_digest": "5" * 64,
        "adapter_kind": "codex-app",
        "adapter_version": "test-v1",
        "evaluated_at_us": 1_790_000_000_000_000,
        "evaluator_version": "wg-continuation-v1",
        "evaluator_result_digest": evaluator_receipt["result_digest"],
        "evaluator_receipt": evaluator_receipt,
        "evaluator_receipt_digest": result["evaluator_receipt_digest"],
    }
    assert result["target_contract"] == {
        "conversation_kind": "work",
        "creation_method": "create_thread",
        "forked": False,
        "exact_project_required": True,
        "project_binding_provenance_required": True,
        "creation_operation_correlation_required": True,
        "creation_request_digest_required": True,
        "bounded_continuation_packet_required": True,
        "continuation_packet_max_bytes": 8_192,
        "continuation_packet_max_items": 64,
        "continuation_packet_token_budget_max": 4_096,
        "initial_message_digest_required": True,
        "source_transcript_included": False,
        "durable_dispatch_before_product_call_required": True,
        "dispatch_currentness_revalidation_required": True,
        "product_receipt_required": True,
        "product_receipt_actor_binding_required": True,
        "current_listener_revision_required": True,
        "stable_thread_id_required": True,
        "resolved_thread_id_required": True,
        "user_visible": True,
        "auditable": True,
        "interactive": True,
        "target_authored_acceptance_required": True,
        "created_target_global_role_reservation_required": True,
        "created_target_source_exception": "exact_committed_candidate_claim_scope",
        "lost_listener_drift_recovery_mode": "abort_only",
        "abort_only_recovery_may_create_target": False,
        "abort_only_recovery_may_commit": False,
        "abort_only_recovery_requires_original_operation_reconciliation": True,
        "abort_only_recovery_requires_state_specific_terminal_evidence": True,
        "prohibited_targets": ["listener", "subagent", "side_chat", "hidden_task"],
    }


def test_continuation_evaluator_receipt_is_deterministic_and_sensitive_to_evidence() -> None:
    runtime = load_runtime_module()
    first = runtime.evaluate_continuation_policy(continuation_event())
    replay = runtime.evaluate_continuation_policy(continuation_event())

    assert replay["evaluator_receipt"] == first["evaluator_receipt"]
    assert replay["evaluator_receipt_digest"] == first["evaluator_receipt_digest"]
    assert replay["policy_decision"] == first["policy_decision"]

    changed_gate = continuation_event()
    changed_gate["safe_semantic_point"] = False
    gate_result = runtime.evaluate_continuation_policy(changed_gate)
    assert gate_result["action"] == "stay"
    assert gate_result["evaluator_receipt_digest"] != first["evaluator_receipt_digest"]
    assert (
        gate_result["policy_decision"]["evaluator_result_digest"]
        != first["policy_decision"]["evaluator_result_digest"]
    )

    changed_evidence = continuation_event()
    references = changed_evidence["evidence_references"]
    assert isinstance(references, list)
    references[1] = {
        "kind": "runtime_observation",
        "reference": "observation:continuation-pressure-refreshed",
        "digest": "8" * 64,
    }
    evidence_result = runtime.evaluate_continuation_policy(changed_evidence)
    assert evidence_result["action"] == "prepare_rotation"
    assert evidence_result["evaluator_receipt_digest"] != first["evaluator_receipt_digest"]
    assert (
        evidence_result["policy_decision"]["evaluator_result_digest"]
        != first["policy_decision"]["evaluator_result_digest"]
    )


@pytest.mark.parametrize(
    "evidence_references",
    [
        None,
        [],
        [
            {
                "kind": "runtime_observation",
                "reference": f"observation:{index}",
                "digest": "6" * 64,
            }
            for index in range(33)
        ],
        [
            {
                "kind": "runtime_observation",
                "reference": "observation:duplicate",
                "digest": "6" * 64,
            },
            {
                "kind": "runtime_observation",
                "reference": "observation:duplicate",
                "digest": "6" * 64,
            },
        ],
        [
            {
                "kind": "runtime\nobservation",
                "reference": "observation:invalid-kind",
                "digest": "6" * 64,
            }
        ],
        [
            {
                "kind": "runtime_observation",
                "reference": "observation:invalid-digest",
                "digest": "not-a-digest",
            }
        ],
    ],
)
def test_continuation_evaluator_rejects_unbounded_or_malformed_evidence(
    evidence_references: object,
) -> None:
    runtime = load_runtime_module()
    event = continuation_event()
    event["evidence_references"] = evidence_references

    with pytest.raises(RuntimeError):
        runtime.evaluate_continuation_policy(event)


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("actor_role",), "subagent", "actor_must_be_bound_listener"),
        (("actor_role",), "side_chat", "actor_must_be_bound_listener"),
        (("source_role",), "listener", "source_role_not_rotatable"),
        (("target_role",), "listener", "target_must_be_work_candidate"),
        (("source_is_current_carrier",), False, "source_not_current_carrier"),
        (("source_has_exclusive_claim",), False, "source_missing_exclusive_claim"),
        (("listener_revision_matches",), False, "listener_revision_mismatch"),
        (("scope_currentness_matches",), False, "scope_currentness_mismatch"),
        (("project_binding_matches",), False, "project_binding_mismatch"),
        (("active_rotation",), True, "rotation_already_active_or_unknown"),
        (("safe_semantic_point",), False, "unsafe_semantic_point"),
        (("handoff_fresh",), False, "handoff_not_fresh"),
        (("cooldown_satisfied",), False, "cooldown_not_satisfied"),
        (("expected_benefit",), "medium", "expected_benefit_not_high"),
        (("continuation_risk",), "high", "continuation_risk_high"),
        (("continuation_enabled",), False, "project_not_opted_in"),
        (("durable_provider_available",), False, "durable_provider_unavailable"),
    ],
)
def test_continuation_policy_rejects_unsafe_or_fragmenting_cases(
    path: tuple[str, ...], value: object, reason: str
) -> None:
    runtime = load_runtime_module()
    event = continuation_event()
    event[path[0]] = value

    result = runtime.evaluate_continuation_policy(event)

    assert result["action"] == "stay"
    assert reason in result["reasons"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_id", "scope\nforged-output=true"),
        ("handoff_digest", "not-a-digest"),
        ("listener_revision", 0),
        ("owner_epoch", True),
        ("evaluated_at_us", -1),
        ("project_opt_in_revision", 0),
        ("continuation_packet_digest", "not-a-digest"),
        ("continuation_packet_bytes", 8_193),
        ("continuation_packet_items", 65),
        ("continuation_packet_token_budget", 4_097),
    ],
)
def test_continuation_policy_fails_closed_on_malformed_decision_identity(
    field: str, value: object
) -> None:
    """Malformed durable-decision identity must never produce a rotation recommendation."""
    runtime = load_runtime_module()
    event = continuation_event()
    event[field] = value

    with pytest.raises(RuntimeError):
        runtime.evaluate_continuation_policy(event)


def test_compaction_alone_never_triggers_continuation() -> None:
    runtime = load_runtime_module()
    event = continuation_event()
    event["signals"] = {
        "context_pressure": False,
        "repeated_compaction": True,
        "unchanged_context_replay": False,
        "coordination_drag": False,
    }

    result = runtime.evaluate_continuation_policy(event)

    assert result["action"] == "stay"
    assert result["pressure_signal_count"] == 1
    assert "insufficient_pressure_diversity" in result["reasons"]


def test_committed_work_candidate_can_be_the_next_rotation_source() -> None:
    runtime = load_runtime_module()
    event = continuation_event()
    event["source_role"] = "work_candidate"

    result = runtime.evaluate_continuation_policy(event)

    assert result["action"] == "prepare_rotation"


def test_uncommitted_work_candidate_cannot_chain_rotation() -> None:
    runtime = load_runtime_module()
    event = continuation_event()
    event["source_role"] = "work_candidate"
    event["source_committed"] = False

    result = runtime.evaluate_continuation_policy(event)

    assert result["action"] == "stay"
    assert "work_candidate_not_committed" in result["reasons"]


def test_installed_runtime_evaluator_is_deterministic_and_has_no_state_side_effect(
    tmp_path: Path,
) -> None:
    launcher, digest = install(tmp_path)
    event = continuation_event()
    first = invoke(launcher, tmp_path, digest, "evaluate-continuation", event)
    second = invoke(launcher, tmp_path, digest, "evaluate-continuation", event)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["action"] == "prepare_rotation"
    assert not (tmp_path / ".local/state/work-governance-hook").exists()


def test_install_probe_and_no_change_hook_output(tmp_path: Path) -> None:
    launcher, digest = install(tmp_path)
    completed = invoke(
        launcher,
        tmp_path,
        digest,
        "post-tool-use",
        {"session_id": "s1", "tool_input": "secret"},
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    observation = (tmp_path / ".local/state/work-governance-hook/v1/observations.jsonl").read_text()
    assert "secret" not in observation
    assert "tool_input" not in observation


def test_changed_context_emits_once_per_handler(tmp_path: Path) -> None:
    launcher, digest = install(tmp_path)
    subprocess.run(
        [
            str(launcher),
            "stage-context",
            "--contract",
            CONTRACT,
            "--package-digest",
            digest,
            "--session-id",
            "s1",
            "--context",
            "bounded active context",
        ],
        check=True,
        env={"HOME": str(tmp_path)},
    )
    first = invoke(launcher, tmp_path, digest, "session-start", {"session_id": "s1"})
    second = invoke(launcher, tmp_path, digest, "session-start", {"session_id": "s1"})
    assert first.returncode == 0
    assert (
        json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
        == "bounded active context"
    )
    assert second.returncode == 0
    assert second.stdout == ""

    subprocess.run(
        [
            str(launcher),
            "stage-context",
            "--contract",
            CONTRACT,
            "--package-digest",
            digest,
            "--session-id",
            "s1",
            "--context",
            "bounded active context",
        ],
        check=True,
        env={"HOME": str(tmp_path)},
    )
    identical = invoke(launcher, tmp_path, digest, "session-start", {"session_id": "s1"})
    assert identical.returncode == 0
    assert identical.stdout == ""


def test_concurrent_context_event_emits_exactly_once(tmp_path: Path) -> None:
    launcher, digest = install(tmp_path)
    subprocess.run(
        [
            str(launcher),
            "stage-context",
            "--contract",
            CONTRACT,
            "--package-digest",
            digest,
            "--session-id",
            "concurrent",
            "--context",
            "one phase packet",
        ],
        check=True,
        env={"HOME": str(tmp_path)},
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: invoke(
                    launcher,
                    tmp_path,
                    digest,
                    "pre-compact",
                    {"session_id": "concurrent"},
                ),
                range(4),
            )
        )
    assert all(result.returncode == 0 for result in results)
    assert sum(bool(result.stdout) for result in results) == 1


def test_user_hook_install_preserves_unrelated_configuration_and_reports_review_boundary(
    tmp_path: Path,
) -> None:
    _, digest = install(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    config_path = config_dir / "hooks.json"
    existing = {
        "description": "existing user hooks",
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": "/usr/bin/true"},
                    ]
                }
            ]
        },
    }
    config_path.write_bytes(canonical(existing) + b"\n")
    config_path.chmod(0o600)

    result, installed_path = install_user_hooks(tmp_path, digest)

    assert installed_path == config_path
    assert result["hook_config_installed"] is True
    assert result["package_digest"] == digest
    assert result["rollback_state"] == "available"
    assert result["trust_state"] == "requires_codex_review"
    installed = json.loads(config_path.read_text(encoding="utf-8"))
    assert installed["description"] == "existing user hooks"
    assert "/usr/bin/true" in json.dumps(installed, sort_keys=True)
    source = json.loads(HOOKS.read_text(encoding="utf-8"))
    assert managed_commands(installed) == managed_commands(source)

    status_json = user_hook_status(tmp_path, digest)
    assert status_json["hook_config_installed"] is True
    assert status_json["hook_definitions_match"] is True
    assert status_json["managed_hook_commands"] == 3
    assert status_json["rollback_state"] == "available"
    assert status_json["trust_state"] == "requires_codex_review"


def test_user_hook_install_replaces_only_prior_managed_definition(tmp_path: Path) -> None:
    _, digest = install(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    source = json.loads(HOOKS.read_text(encoding="utf-8"))
    old_digest = "f" * 64
    old_command = managed_commands(source)[0].replace(digest, old_digest)
    existing = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": old_command},
                        {"type": "command", "command": "/usr/bin/true"},
                    ]
                }
            ]
        }
    }
    config_path = config_dir / "hooks.json"
    config_path.write_bytes(canonical(existing) + b"\n")
    config_path.chmod(0o600)

    install_user_hooks(tmp_path, digest)

    installed = json.loads(config_path.read_text(encoding="utf-8"))
    encoded = json.dumps(installed, sort_keys=True)
    assert old_digest not in encoded
    assert "/usr/bin/true" in encoded
    assert managed_commands(installed) == managed_commands(source)


def test_user_hook_install_rejects_invalid_or_unsafe_existing_configuration(tmp_path: Path) -> None:
    _, digest = install(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    config_path = config_dir / "hooks.json"
    malformed = b'{"hooks": []}\n'
    config_path.write_bytes(malformed)
    config_path.chmod(0o600)

    malformed_result = subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(tmp_path),
            "user-hook",
            "install",
            "--expected-package-digest",
            digest,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert malformed_result.returncode != 0
    assert config_path.read_bytes() == malformed

    config_path.unlink()
    target = tmp_path / "other-hooks.json"
    target.write_text('{"hooks": {}}\n', encoding="utf-8")
    config_path.symlink_to(target)
    unsafe_result = subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(tmp_path),
            "user-hook",
            "install",
            "--expected-package-digest",
            digest,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert unsafe_result.returncode != 0
    assert config_path.is_symlink()
    assert target.read_text(encoding="utf-8") == '{"hooks": {}}\n'


@pytest.mark.parametrize("fault", ["wrong_event", "matcher_changed", "duplicate_handler"])
def test_user_hook_status_requires_exact_event_mapping_and_matcher(
    tmp_path: Path, fault: str
) -> None:
    _, digest = install(tmp_path)
    _, config_path = install_user_hooks(tmp_path, digest)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    hooks = config["hooks"]
    assert isinstance(hooks, dict)
    if fault == "wrong_event":
        session_start = hooks["SessionStart"]
        pre_compact = hooks["PreCompact"]
        hooks["SessionStart"] = pre_compact
        hooks["PreCompact"] = session_start
    elif fault == "matcher_changed":
        post_tool_use = hooks["PostToolUse"]
        assert isinstance(post_tool_use, list)
        group = post_tool_use[0]
        assert isinstance(group, dict)
        group["matcher"] = "Bash"
    else:
        session_start = hooks["SessionStart"]
        assert isinstance(session_start, list)
        session_start.append(json.loads(canonical(session_start[0])))
    config_path.write_bytes(canonical(config) + b"\n")
    config_path.chmod(0o600)

    status = user_hook_status(tmp_path, digest)

    assert status["hook_definitions_match"] is False
    assert status["trust_state"] == "definition_mismatch"


def test_user_hook_rollback_preserves_unrelated_changes_and_verifies_old_package(
    tmp_path: Path,
) -> None:
    _, digest = install(tmp_path)
    old_digest = clone_package(tmp_path, digest, "previous")
    source = json.loads(HOOKS.read_text(encoding="utf-8"))
    existing = json.loads(json.dumps(source).replace(digest, old_digest))
    existing["description"] = "existing user hooks"
    existing["hooks"]["SessionStart"].append(
        {"hooks": [{"type": "command", "command": "/usr/bin/true"}]}
    )
    existing["hooks"]["Other"] = [{"hooks": [{"type": "command", "command": "/usr/bin/false"}]}]
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    config_path = config_dir / "hooks.json"
    config_path.write_bytes(canonical(existing) + b"\n")
    config_path.chmod(0o600)

    installed, _ = install_user_hooks(tmp_path, digest)
    receipt_path = Path(str(installed["rollback_receipt_path"]))
    assert receipt_path.is_file()
    receipt_bytes = receipt_path.read_bytes()
    repeated, _ = install_user_hooks(tmp_path, digest)
    assert repeated["rollback_state"] == "available"
    assert receipt_path.read_bytes() == receipt_bytes
    active = json.loads(config_path.read_text(encoding="utf-8"))
    active["hooks"]["Other"].append(
        {"hooks": [{"type": "command", "command": "/usr/bin/printf late-change"}]}
    )
    config_path.write_bytes(canonical(active) + b"\n")
    config_path.chmod(0o600)

    completed = rollback_user_hooks(tmp_path, digest)

    result = json.loads(completed.stdout)
    assert result["restored_package_digests"] == [old_digest]
    assert result["rollback_state"] == "consumed"
    restored = json.loads(config_path.read_text(encoding="utf-8"))
    assert managed_commands(restored) == managed_commands(existing)
    assert digest not in json.dumps(restored, sort_keys=True)
    assert "/usr/bin/true" in json.dumps(restored, sort_keys=True)
    assert "/usr/bin/false" in json.dumps(restored, sort_keys=True)
    assert "/usr/bin/printf late-change" in json.dumps(restored, sort_keys=True)
    assert not receipt_path.exists()
    status = user_hook_status(tmp_path, digest)
    assert status["hook_definitions_match"] is False
    assert status["rollback_state"] == "missing"


def test_repeated_fresh_user_hook_install_retains_rollback_to_absent_configuration(
    tmp_path: Path,
) -> None:
    _, digest = install(tmp_path)
    first, config_path = install_user_hooks(tmp_path, digest)
    receipt_path = Path(str(first["rollback_receipt_path"]))
    receipt_bytes = receipt_path.read_bytes()

    repeated, repeated_config_path = install_user_hooks(tmp_path, digest)

    assert repeated_config_path == config_path
    assert repeated["rollback_state"] == "available"
    assert receipt_path.read_bytes() == receipt_bytes
    completed = rollback_user_hooks(tmp_path, digest)
    result = json.loads(completed.stdout)
    assert result["hook_config_installed"] is False
    assert result["restored_package_digests"] == []
    assert result["rollback_state"] == "consumed"
    assert not config_path.exists()
    assert not receipt_path.exists()


def test_repeated_candidate_install_never_fabricates_a_missing_rollback_receipt(
    tmp_path: Path,
) -> None:
    _, digest = install(tmp_path)
    installed, config_path = install_user_hooks(tmp_path, digest)
    receipt_path = Path(str(installed["rollback_receipt_path"]))
    receipt_path.unlink()
    candidate_bytes = config_path.read_bytes()

    repeated, _ = install_user_hooks(tmp_path, digest)

    assert repeated["rollback_state"] == "missing"
    assert config_path.read_bytes() == candidate_bytes
    assert not receipt_path.exists()
    assert user_hook_status(tmp_path, digest)["rollback_state"] == "missing"


def test_user_hook_rollback_refuses_changed_definition_or_missing_old_package(
    tmp_path: Path,
) -> None:
    _, digest = install(tmp_path)
    old_digest = clone_package(tmp_path, digest, "previous")
    source = json.loads(HOOKS.read_text(encoding="utf-8"))
    existing = json.loads(json.dumps(source).replace(digest, old_digest))
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    config_path = config_dir / "hooks.json"
    config_path.write_bytes(canonical(existing) + b"\n")
    config_path.chmod(0o600)
    install_user_hooks(tmp_path, digest)

    changed = json.loads(config_path.read_text(encoding="utf-8"))
    changed["hooks"]["PostToolUse"][0]["matcher"] = "Bash"
    config_path.write_bytes(canonical(changed) + b"\n")
    config_path.chmod(0o600)
    changed_bytes = config_path.read_bytes()
    changed_result = rollback_user_hooks(tmp_path, digest, check=False)
    assert changed_result.returncode != 0
    assert config_path.read_bytes() == changed_bytes

    config_path.write_bytes(canonical(existing) + b"\n")
    config_path.chmod(0o600)
    install_user_hooks(tmp_path, digest)
    shutil.rmtree(tmp_path / ".local/libexec/work-governance" / old_digest)
    candidate_bytes = config_path.read_bytes()
    missing_package_result = rollback_user_hooks(tmp_path, digest, check=False)
    assert missing_package_result.returncode != 0
    assert config_path.read_bytes() == candidate_bytes


def test_user_hook_install_reports_clean_rollback_when_atomic_write_never_happens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, digest = install(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    config_path = config_dir / "hooks.json"
    previous = b'{"hooks": {}}\n'
    config_path.write_bytes(previous)
    config_path.chmod(0o600)
    module = load_installer_module()
    original_atomic_replace = module._atomic_replace

    def fail_before_replace(target: Path, content: bytes, mode: int, prefix: str) -> None:
        if target == config_path:
            raise OSError("simulated temporary-file creation failure")
        original_atomic_replace(target, content, mode, prefix)

    monkeypatch.setattr(module, "_atomic_replace", fail_before_replace)

    with pytest.raises(RuntimeError, match="previous configuration restored") as error:
        module._install_user_hooks(tmp_path, digest)

    assert "rollback failed" not in str(error.value)
    assert config_path.read_bytes() == previous
    assert not (config_dir / ".work-governance-hooks.rollback.json").exists()


def test_user_hook_install_reports_clean_rollback_when_rename_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, digest = install(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    config_path = config_dir / "hooks.json"
    previous = b'{"hooks": {}}\n'
    config_path.write_bytes(previous)
    config_path.chmod(0o600)
    module = load_installer_module()
    original_replace = module.os.replace

    def fail_rename(source: Path, target: Path) -> None:
        if target == config_path:
            raise OSError("simulated rename failure")
        original_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_rename)

    with pytest.raises(RuntimeError, match="previous configuration restored") as error:
        module._install_user_hooks(tmp_path, digest)

    assert "rollback failed" not in str(error.value)
    assert config_path.read_bytes() == previous


def test_user_hook_install_restores_candidate_when_readback_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, digest = install(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(mode=0o700)
    config_path = config_dir / "hooks.json"
    previous = b'{"hooks": {}}\n'
    config_path.write_bytes(previous)
    config_path.chmod(0o600)
    module = load_installer_module()
    original_atomic_replace = module._atomic_replace
    original_read = module._read_private_regular
    wrote_candidate = False
    injected_readback_failure = False

    def track_candidate_write(target: Path, content: bytes, mode: int, prefix: str) -> None:
        nonlocal wrote_candidate
        original_atomic_replace(target, content, mode, prefix)
        if target == config_path:
            wrote_candidate = True

    def fail_one_readback(path: Path, description: str) -> bytes | None:
        nonlocal injected_readback_failure
        if (
            wrote_candidate
            and not injected_readback_failure
            and path == config_path
            and description == "user Hook configuration"
        ):
            injected_readback_failure = True
            return b"unexpected readback"
        return original_read(path, description)

    monkeypatch.setattr(module, "_atomic_replace", track_candidate_write)
    monkeypatch.setattr(module, "_read_private_regular", fail_one_readback)

    with pytest.raises(RuntimeError, match="previous configuration restored") as error:
        module._install_user_hooks(tmp_path, digest)

    assert "rollback failed" not in str(error.value)
    assert config_path.read_bytes() == previous


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{", b"Expecting"),
        (b"x" * 262_145, b"exceeds the bounded input limit"),
    ],
    ids=["malformed", "oversized"],
)
def test_malformed_and_oversized_input_fail_explicitly(
    tmp_path: Path, payload: bytes, message: bytes
) -> None:
    launcher, digest = install(tmp_path)
    completed = invoke_raw(launcher, tmp_path, digest, "post-tool-use", payload)
    assert completed.returncode != 0
    assert message in completed.stderr


@pytest.mark.parametrize("fault", ["runtime_tamper", "package_symlink", "world_writable"])
def test_integrity_faults_fail_explicitly(tmp_path: Path, fault: str) -> None:
    launcher, digest = install(tmp_path)
    package = tmp_path / ".local/libexec/work-governance" / digest
    if fault == "runtime_tamper":
        (package / "hook_runtime.py").write_text("pass\n", encoding="utf-8")
    elif fault == "package_symlink":
        moved = package.with_name(f"{digest}.real")
        package.rename(moved)
        package.symlink_to(moved, target_is_directory=True)
    else:
        package.chmod(0o777)
    completed = invoke(launcher, tmp_path, digest, "post-tool-use", {})
    assert completed.returncode != 0
    assert "work-governance-hook:" in completed.stderr


def test_launcher_replacement_can_probe_old_and_new_packages(tmp_path: Path) -> None:
    launcher, digest = install(tmp_path)
    old_digest = clone_package(tmp_path, digest, "old")
    old_launcher = launcher.read_bytes() + b"\n# previous launcher\n"
    launcher.write_bytes(old_launcher)
    launcher.chmod(0o700)
    subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(tmp_path),
            "launcher",
            "--probe-digest",
            old_digest,
            "--probe-digest",
            digest,
            "--rollback-digest",
            old_digest,
        ],
        check=True,
    )
    assert old_digest != digest
    assert launcher.read_bytes() != old_launcher
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o700


def test_launcher_probe_failure_restores_previous_launcher(tmp_path: Path) -> None:
    launcher, digest = install(tmp_path)
    old_digest = clone_package(tmp_path, digest, "rollback")
    counter = tmp_path / "rollback-probes"
    previous = install_probe_counter_launcher(launcher, old_digest, counter)
    completed = subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(tmp_path),
            "launcher",
            "--probe-digest",
            old_digest,
            "--probe-digest",
            "0" * 64,
            "--rollback-digest",
            old_digest,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert launcher.read_bytes() == previous
    assert counter.read_text() == "2"
    assert "rollback launcher restored and verified" in completed.stderr


def test_launcher_reports_rollback_probe_failure_distinctly(tmp_path: Path) -> None:
    launcher, digest = install(tmp_path)
    old_digest = clone_package(tmp_path, digest, "broken-rollback")
    counter = tmp_path / "rollback-probes"
    previous = install_probe_counter_launcher(launcher, old_digest, counter, fail_after=1)
    completed = subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(tmp_path),
            "launcher",
            "--probe-digest",
            old_digest,
            "--probe-digest",
            "0" * 64,
            "--rollback-digest",
            old_digest,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert launcher.read_bytes() == previous
    assert counter.read_text() == "2"
    assert "rollback launcher probe failed" in completed.stderr


def test_concurrent_package_and_launcher_installation_is_serialized(tmp_path: Path) -> None:
    digest = package_digest()
    package_command = [
        str(INSTALLER),
        "--home",
        str(tmp_path),
        "package",
        "--expected-digest",
        digest,
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        package_results = list(
            executor.map(
                lambda _: subprocess.run(package_command, capture_output=True, check=False),
                range(2),
            )
        )
    assert all(result.returncode == 0 for result in package_results), [
        result.stderr.decode(errors="replace") for result in package_results
    ]

    subprocess.run(
        [
            str(INSTALLER),
            "--home",
            str(tmp_path),
            "launcher",
            "--probe-digest",
            digest,
        ],
        check=True,
    )

    launcher_command = [
        str(INSTALLER),
        "--home",
        str(tmp_path),
        "launcher",
        "--probe-digest",
        digest,
        "--rollback-digest",
        digest,
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        launcher_results = list(
            executor.map(
                lambda _: subprocess.run(launcher_command, capture_output=True, check=False),
                range(2),
            )
        )
    assert all(result.returncode == 0 for result in launcher_results), [
        result.stderr.decode(errors="replace") for result in launcher_results
    ]


def test_partial_package_is_never_selected(tmp_path: Path) -> None:
    launcher, digest = install(tmp_path)
    partial = tmp_path / ".local/libexec/work-governance" / ("0" * 64)
    partial.mkdir(mode=0o700)
    (partial / "package.json").write_text("{}", encoding="utf-8")
    completed = invoke(launcher, tmp_path, digest, "post-tool-use", {})
    assert completed.returncode == 0
    shutil.rmtree(partial)
