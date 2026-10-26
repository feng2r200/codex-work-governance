"""Contract tests for the native WorkVCS continuation-readiness consumer."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "plugins" / "work-governance" / "runtime" / "hook_runtime.py"


class RuntimeModule(Protocol):
    """Typed surface exercised from the dynamically loaded Hook runtime."""

    def evaluate_continuation_policy(self, event: dict[str, object]) -> dict[str, object]: ...

    def _parse_json_output(self, output: str, label: str) -> dict[str, object]: ...

    def _validate_native_readiness(
        self, snapshot: dict[str, object], expected_scope_id: str
    ) -> tuple[str, list[dict[str, str]]]: ...

    def _continuation_readiness_response(
        self,
        snapshot: dict[str, object],
        scope_id: str,
        previous_digest: str | None,
    ) -> dict[str, object]: ...

    def _validated_store_path(self, event: dict[str, object]) -> Path: ...

    def inspect_continuation_readiness(self, event: dict[str, object]) -> dict[str, object]: ...


def load_runtime_module() -> RuntimeModule:
    """Load the Hook runtime behind its exact Python surface."""
    spec = importlib.util.spec_from_file_location("work_governance_readiness", RUNTIME)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(RuntimeModule, module)


def native_snapshot() -> dict[str, object]:
    """Return one structurally complete native readiness response."""
    scope_id = "01900000-0000-7000-8000-000000000001"
    workspace_id = "01900000-0000-7000-8000-000000000002"
    branch_id = "01900000-0000-7000-8000-000000000003"
    task_id = "01900000-0000-7000-8000-000000000004"
    listener_id = "01900000-0000-7000-8000-000000000005"
    carrier_id = "01900000-0000-7000-8000-000000000006"
    claim_id = "01900000-0000-7000-8000-000000000007"
    return {
        "schema_version": 1,
        "read_only": True,
        "store_opened_readonly": True,
        "provider_protocol_ready": True,
        "product_membership_verified": False,
        "product_dispatch_authorized": False,
        "currentness_digest": "1" * 64,
        "scope": {
            "scope_id": scope_id,
            "workspace_id": workspace_id,
            "branch_id": branch_id,
            "task_entity_id": task_id,
            "project_id": "g-p-readiness-test",
            "project_policy_revision": 5,
            "project_policy_receipt_digest": "2" * 64,
            "project_binding_source": "continuation.scope_bound",
            "listener_session_id": listener_id,
            "listener_revision": 2,
            "carrier_session_id": carrier_id,
            "carrier_claim_id": claim_id,
            "owner_epoch": 3,
            "updated_at_us": 4,
        },
        "policy": {
            "resolution": "scope_binding",
            "candidate_count": 1,
            "project_id": "g-p-readiness-test",
            "enabled": True,
            "revision": 5,
            "actor_session_id": listener_id,
            "receipt_digest": "2" * 64,
            "updated_at_us": 6,
        },
        "listener": {
            "session_id": listener_id,
            "lifecycle_state": "active",
            "role": "listener",
            "thread_id": "thread-listener",
            "thread_session_count": 1,
            "historical_created_target_count": 0,
            "active_workspace_id": workspace_id,
            "active_branch_id": branch_id,
            "last_activity_at_us": 7,
        },
        "carrier": {
            "session_id": carrier_id,
            "lifecycle_state": "active",
            "role": "work",
            "thread_id": "thread-work",
            "thread_session_count": 1,
            "historical_created_target_count": 0,
            "active_workspace_id": workspace_id,
            "active_branch_id": branch_id,
            "last_activity_at_us": 8,
            "provenance": "work",
            "promotion_rotation_id": None,
            "promotion_project_id": None,
        },
        "claim": {
            "claim_id": claim_id,
            "active": True,
            "session_id": carrier_id,
            "workspace_id": workspace_id,
            "branch_id": branch_id,
            "task_entity_id": task_id,
            "mode": "exclusive",
            "last_activity_at_us": 9,
        },
        "branch": {
            "branch_id": branch_id,
            "workspace_id": workspace_id,
            "lifecycle_state": "active",
            "head_commit_id": "01900000-0000-7000-8000-000000000008",
            "head_state_digest": "3" * 64,
            "projection_status": "current",
            "projected_commit_id": "01900000-0000-7000-8000-000000000008",
            "projection_state_digest": "3" * 64,
            "projection_current": True,
        },
        "task": {
            "task_entity_id": task_id,
            "current": True,
            "entity_version_id": "01900000-0000-7000-8000-000000000009",
            "state_digest": "4" * 64,
            "status": "active",
        },
        "rotation": {
            "active": False,
            "rotation_id": None,
            "state": None,
            "scope_currentness_digest": None,
            "abort_only": None,
            "listener_session_id": None,
            "listener_revision": None,
            "candidate_session_id": None,
            "last_activity_at_us": None,
        },
        "gaps": [],
    }


def test_policy_evaluator_never_promotes_caller_fields_to_authorization() -> None:
    """Caller evidence remains a non-authoritative recommendation input."""
    runtime = load_runtime_module()
    event: dict[str, object] = {
        "schema_version": 1,
        "continuation_enabled": True,
        "durable_provider_available": True,
        "project_opt_in_receipt_kind": "workvcs_project_policy",
        "project_opt_in_receipt_digest": "1" * 64,
        "project_opt_in_revision": 1,
        "project_opt_in_verified_at_us": 1,
        "project_id": "g-p-readiness-test",
        "scope_id": "scope-1",
        "workspace_id": "workspace-1",
        "branch_id": "branch-1",
        "task_entity_id": "task-1",
        "listener_session_id": "listener-1",
        "listener_revision": 1,
        "source_session_id": "source-1",
        "source_claim_id": "claim-1",
        "owner_epoch": 1,
        "handoff_digest": "2" * 64,
        "scope_currentness_digest": "3" * 64,
        "continuation_packet_digest": "4" * 64,
        "continuation_packet_bytes": 1,
        "continuation_packet_items": 1,
        "continuation_packet_token_budget": 1,
        "initial_message_digest": "5" * 64,
        "adapter_kind": "codex-app",
        "adapter_version": "v1",
        "evaluated_at_us": 1,
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
            "repeated_compaction": True,
            "unchanged_context_replay": False,
            "coordination_drag": False,
        },
        "evidence_references": [{"kind": "record", "reference": "record-1", "digest": "6" * 64}],
    }

    result = runtime.evaluate_continuation_policy(event)

    assert result["action"] == "prepare_rotation"
    assert result["decision_scope"] == "policy_recommendation"
    assert result["control_inputs_authoritative"] is False
    assert result["requires_provider_readback_before_dispatch"] is True
    assert result["requires_product_control_plane_authorization"] is True
    assert result["causes_product_effects"] is False


def test_native_json_schema_accepts_all_atomic_layers() -> None:
    """The consumer accepts one complete typed aggregate without focused reads."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()

    digest, gaps = runtime._validate_native_readiness(
        snapshot, "01900000-0000-7000-8000-000000000001"
    )

    assert digest == "1" * 64
    assert gaps == []


def test_provider_ready_snapshot_never_becomes_product_dispatch_authority() -> None:
    """A complete native provider snapshot still leaves product effects unavailable."""
    runtime = load_runtime_module()

    response = runtime._continuation_readiness_response(
        native_snapshot(),
        "01900000-0000-7000-8000-000000000001",
        None,
    )

    assert response["provider_protocol_ready"] is True
    assert response["automatic_rotation_ready"] is False
    assert response["safe_to_dispatch_product_effect"] is False
    provider = response["provider_snapshot"]
    assert isinstance(provider, dict)
    assert provider["product_membership_verified"] is False
    assert provider["product_dispatch_authorized"] is False


def test_native_json_schema_rejects_non_readonly_store_open() -> None:
    """A provider response cannot claim readiness without readonly-open proof."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    snapshot["store_opened_readonly"] = False

    with pytest.raises(RuntimeError, match="did not prove a read-only Store open"):
        runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")


@pytest.mark.parametrize(
    "field",
    ("product_membership_verified", "product_dispatch_authorized"),
)
def test_native_json_schema_requires_explicit_false_product_boundary(field: str) -> None:
    """Provider readiness cannot silently become product membership or dispatch authority."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    del snapshot[field]
    with pytest.raises(RuntimeError, match=field):
        runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")

    snapshot[field] = True
    with pytest.raises(RuntimeError, match="cannot assert product membership"):
        runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")


def test_native_json_schema_rejects_scope_identity_mismatch() -> None:
    """The native aggregate must bind the exact requested continuation scope."""
    runtime = load_runtime_module()

    with pytest.raises(RuntimeError, match="scope.scope_id does not match"):
        runtime._validate_native_readiness(native_snapshot(), "different-scope")


def test_native_json_schema_preserves_typed_gaps() -> None:
    """Provider gap codes and diagnostics remain typed native evidence."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    snapshot["provider_protocol_ready"] = False
    snapshot["gaps"] = [{"code": "listener_not_active", "detail": "listener lifecycle is ended"}]

    _, gaps = runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")

    assert gaps == [{"code": "listener_not_active", "detail": "listener lifecycle is ended"}]


@pytest.mark.parametrize(
    ("provider_protocol_ready", "gaps"),
    (
        (
            True,
            [{"code": "listener_not_active", "detail": "listener lifecycle is ended"}],
        ),
        (False, []),
    ),
)
def test_native_json_schema_rejects_ready_gap_inconsistency(
    provider_protocol_ready: bool,
    gaps: list[dict[str, str]],
) -> None:
    """The typed provider decision and its gap set must describe one state."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    snapshot["provider_protocol_ready"] = provider_protocol_ready
    snapshot["gaps"] = gaps

    with pytest.raises(RuntimeError, match="must equal gaps.is_empty"):
        runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")


def test_native_json_schema_rejects_partial_scope_project_binding() -> None:
    """A scope cannot carry only part of its native exact-Project receipt."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    scope = snapshot["scope"]
    assert isinstance(scope, dict)
    del scope["project_policy_receipt_digest"]

    with pytest.raises(RuntimeError, match="partial Project binding"):
        runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")


def test_native_json_schema_rejects_policy_that_disagrees_with_scope_binding() -> None:
    """The consumer requires the native policy receipt to match its bound scope."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    policy = snapshot["policy"]
    assert isinstance(policy, dict)
    policy["project_id"] = "g-p-other-project"

    with pytest.raises(RuntimeError, match="does not match the scope-bound Project"):
        runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")


def test_native_json_schema_accepts_newer_current_policy_revision() -> None:
    """The immutable scope receipt and the current policy may have different revisions."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    policy = snapshot["policy"]
    assert isinstance(policy, dict)
    policy["revision"] = 6
    policy["receipt_digest"] = "5" * 64

    digest, gaps = runtime._validate_native_readiness(
        snapshot, "01900000-0000-7000-8000-000000000001"
    )

    assert digest == "1" * 64
    assert gaps == []


def test_native_json_schema_accepts_explicit_missing_project_binding_gap() -> None:
    """A typed missing binding remains valid not-ready evidence instead of being guessed."""
    runtime = load_runtime_module()
    snapshot = native_snapshot()
    scope = snapshot["scope"]
    policy = snapshot["policy"]
    assert isinstance(scope, dict)
    assert isinstance(policy, dict)
    for field in (
        "project_id",
        "project_policy_revision",
        "project_policy_receipt_digest",
        "project_binding_source",
    ):
        scope[field] = None
    policy.update(
        {
            "resolution": "project_binding_missing",
            "candidate_count": 0,
            "project_id": None,
            "enabled": None,
            "revision": None,
            "actor_session_id": None,
            "receipt_digest": None,
            "updated_at_us": None,
        }
    )
    snapshot["provider_protocol_ready"] = False
    snapshot["gaps"] = [
        {
            "code": "project_binding_missing",
            "detail": "continuation scope has no exact Project binding",
        }
    ]

    _, gaps = runtime._validate_native_readiness(snapshot, "01900000-0000-7000-8000-000000000001")

    assert gaps == [
        {
            "code": "project_binding_missing",
            "detail": "continuation scope has no exact Project binding",
        }
    ]


def test_json_parser_rejects_key_value_and_non_object_output() -> None:
    """The consumer no longer accepts legacy line-oriented provider output."""
    runtime = load_runtime_module()

    with pytest.raises(RuntimeError, match="not valid JSON"):
        runtime._parse_json_output("read_only=true\n", "fixture")
    with pytest.raises(RuntimeError, match="must be a JSON object"):
        runtime._parse_json_output("[]", "fixture")


def test_store_path_rejects_symbolic_links_and_group_writable_files(tmp_path: Path) -> None:
    """Readiness accepts only an owner-controlled regular Store path."""
    runtime = load_runtime_module()
    store = tmp_path / "store.sqlite"
    store.write_bytes(b"not-a-store")
    store.chmod(0o600)
    link = tmp_path / "store-link.sqlite"
    link.symlink_to(store)

    assert runtime._validated_store_path({"store_path": str(store)}) == store
    with pytest.raises(RuntimeError, match="not a real regular file"):
        runtime._validated_store_path({"store_path": str(link)})

    store.chmod(0o620)
    try:
        with pytest.raises(RuntimeError, match="not safely owner-controlled"):
            runtime._validated_store_path({"store_path": str(store)})
    finally:
        os.chmod(store, 0o600)


def test_readiness_schema_rejects_caller_supplied_authorization(tmp_path: Path) -> None:
    """The closed readiness schema rejects caller-created authorization."""
    runtime = load_runtime_module()
    store = tmp_path / "store.sqlite"
    store.write_bytes(b"not-read-because-schema-fails-first")
    store.chmod(0o600)

    with pytest.raises(RuntimeError, match="unsupported fields: product_authorized"):
        runtime.inspect_continuation_readiness(
            {
                "schema_version": 1,
                "store_path": str(store),
                "scope_id": "01900000-0000-7000-8000-000000000001",
                "product_authorized": True,
            }
        )
