#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Deterministic controller for Work Governance Plan files."""

# workctl_modules imports depend on SCRIPT_DIR being present for runpy/runtime-bundle execution.
# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import contextlib
import copy
import ctypes
import difflib
import errno
import fcntl
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from workctl_modules import WORKFLOW_HELP as MODULE_WORKFLOW_HELP
from workctl_modules import WORKFLOW_HELP_ALIASES as MODULE_WORKFLOW_HELP_ALIASES
from workctl_modules import SchedulerStateError as ModuleSchedulerStateError
from workctl_modules import blocked_task_targets as MODULE_BLOCKED_TASK_TARGETS
from workctl_modules import canonical_evidence_bytes as MODULE_CANONICAL_EVIDENCE_BYTES
from workctl_modules import confirmation as module_confirmation
from workctl_modules import current_advancement_targets as MODULE_CURRENT_ADVANCEMENT_TARGETS
from workctl_modules import dump_scheduler_state as MODULE_DUMP_SCHEDULER_STATE
from workctl_modules import evidence as module_evidence
from workctl_modules import load_scheduler_state as MODULE_LOAD_SCHEDULER_STATE
from workctl_modules import parse_evidence_bytes as MODULE_PARSE_EVIDENCE_BYTES
from workctl_modules import ready_task_targets as MODULE_READY_TASK_TARGETS
from workctl_modules import scheduler_state_path as MODULE_SCHEDULER_STATE_PATH
from workctl_modules import yaml_compat as yaml
from workctl_modules.authority import candidate_to_dict as module_candidate_to_dict
from workctl_modules.authority import parse_candidate_specs as module_parse_candidate_specs
from workctl_modules.confirmation import confirmation_lookup as module_confirmation_lookup
from workctl_modules import filesystem as module_filesystem
from workctl_modules.filesystem import FilesystemError as ModuleFilesystemError
from workctl_modules.history import PlanHistoryError as ModulePlanHistoryError
from workctl_modules.history import find_plan_history_target as module_find_plan_history_target
from workctl_modules.history import (
    tolerant_plan_history_summary as module_tolerant_plan_history_summary,
)
from workctl_modules.migration import (
    REFRESH_NEXT_MODEL_ACTION,
    REFRESH_NOT_MIGRATED,
    build_v5_contract,
    build_v5_state,
    legacy_plan_summary,
    migration_projection,
)
from workctl_modules.migration import archive_path_for_source as module_archive_path_for_source
from workctl_modules.migration import pointer_text as module_pointer_text
from workctl_modules.model import TaskProjection
from workctl_modules import paths as module_paths
from workctl_modules.paths import PathError as ModulePathError
from workctl_modules.plan_schema import CURRENT_PLAN_SCHEMA_VERSION
from workctl_modules.references import valid_reference as module_valid_reference
from workctl_modules.risk import action_reversibility as module_action_reversibility
from workctl_modules.risk import risk_factors_for_action as module_risk_factors_for_action
from workctl_modules.risk import risk_inspection_payload as module_risk_inspection_payload
from workctl_modules.status import blocking_artifacts as module_blocking_artifacts
from workctl_modules.status import compact_plan_status as module_compact_plan_status
from workctl_modules.status import completion_claims as module_completion_claims
from workctl_modules.status import (
    current_schema_refresh_status as module_current_schema_refresh_status,
)
from workctl_modules.status import downstream_task_targets as module_downstream_task_targets
from workctl_modules.status import legacy_refresh_projection as module_legacy_refresh_projection
from workctl_modules.status import pending_confirmation_ids as module_pending_confirmation_ids
from workctl_modules.status import queue_projection as module_queue_projection
from workctl_modules.status import task_artifact_blockers as module_task_artifact_blockers
from workctl_modules.status import task_blocking_details as module_task_blocking_details
from workctl_modules.status import task_confirmation_blocker as module_task_confirmation_blocker
from workctl_modules.status import incomplete_entries as module_incomplete_entries
from workctl_modules.status import unresolved_exclusions as module_unresolved_exclusions
from workctl_modules.status import (
    user_intervention_projection as module_user_intervention_projection,
)
from workctl_modules.storage import canonical_event_bytes, redacted_copy
from workctl_modules.workflow_contract import WorkflowContractError as ModuleWorkflowContractError
from workctl_modules.workflow_contract import non_empty_string as module_non_empty_string
from workctl_modules.workflow_contract import (
    normalize_goal_confirmations as module_normalize_goal_confirmations,
)
from workctl_modules.workflow_contract import normalize_goal_tasks as module_normalize_goal_tasks
from workctl_modules.workflow_contract import (
    parse_workflow_mapping as module_parse_workflow_mapping,
)
from workctl_modules.workflow_contract import workflow_string_list as module_workflow_string_list
from workctl_modules.workflow_input import WorkflowInputError as ModuleWorkflowInputError
from workctl_modules.workflow_input import (
    read_workflow_input_bytes as module_read_workflow_input_bytes,
)
from workctl_modules.worktree import WorktreeLedgerError as ModuleWorktreeLedgerError
from workctl_modules.worktree import append_worktree_event as module_append_worktree_event
from workctl_modules.worktree import build_worktree_event as module_build_worktree_event
from workctl_modules.worktree import close_worktree_ledger as module_close_worktree_ledger
from workctl_modules.worktree import encode_worktree_ledger as module_encode_worktree_ledger
from workctl_modules.worktree import load_worktree_ledger as module_load_worktree_ledger
from workctl_modules.worktree import open_worktree_ledger as module_open_worktree_ledger
from workctl_modules.worktree import worktree_ledger_path as module_worktree_ledger_path

PLAN_ID_RE = re.compile(r"^PLAN-\d{8}-\d{3}$")
MIGRATION_ID_RE = re.compile(r"^MIG-\d{8}-\d{3}$")
ROLLOVER_ID_RE = re.compile(r"^ROL-\d{8}-\d{3}$")
RETIREMENT_ID_RE = re.compile(r"^RET-\d{8}-\d{3}$")
ADMISSION_ID_RE = re.compile(r"^ADM-\d{8}-\d{3}$")
CONTRACT_UPGRADE_ID_RE = re.compile(r"^UPG-\d{8}-\d{3}$")
RECONCILE_UPGRADE_ID_RE = re.compile(r"^RCU-\d{8}-\d{3}$")
STRUCTURAL_REBASE_ID_RE = re.compile(r"^SRB-\d{8}-\d{3}$")
ACTION_AUTHORIZATION_ID_RE = re.compile(r"^AUTH-[0-9a-f]{32}$")
ACTION_AUTHORITY_LEASE_ID_RE = re.compile(r"^LEASE-[0-9a-f]{32}$")
ROLLOVER_CONFIRMATION_PAYLOAD_VERSION = 2
UNKNOWN_ID_RE = re.compile(r"^U-\d{3}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
STRICT_INITIAL_INTAKE_REQUIRED = True
TARGET_REF_RE = re.compile(
    r"^(route|delivery|activation|task:T-\d{3}|obligation:O-\d{3}|"
    r"validation:V-\d{3}|artifact:A-\d{3})$"
)
ACTIVATION_TARGET_PLACEHOLDER_RE = re.compile(
    r"^(plugin:[A-Za-z0-9][A-Za-z0-9._-]*@[^@\s+]+\+codex\.)pending$"
)
LEGACY_ACTIVATION_TARGET_PLACEHOLDER_RE = re.compile(
    r"^plugin:(?P<plugin>[A-Za-z0-9][A-Za-z0-9._-]*)@[^@\s+]+\.pending$"
)
EXACT_ACTIVATION_TARGET_RE = re.compile(
    r"^plugin:(?P<plugin>[A-Za-z0-9][A-Za-z0-9._-]*)@"
    r"[^@\s+]+\+codex\.(?P<cachebuster>[A-Za-z0-9][A-Za-z0-9._-]*)$"
)
ACTIVATION_CACHEBUSTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REFERENCE_RE = re.compile(
    r"^(user|project|git|runtime|evidence|handoff|codex-plugin-list|context|plugin):\S+$"
)
EVIDENCE_REFERENCE_FIELDS = {"evidence_ref", "state_evidence_ref"}
ENTRY_ID_PATTERNS = {
    "obligations": re.compile(r"^O-\d{3}$"),
    "tasks": re.compile(r"^T-\d{3}$"),
    "validations": re.compile(r"^V-\d{3}$"),
    "artifacts": re.compile(r"^A-\d{3}$"),
}
BLOCKING_ARTIFACT_STATES = {"suspect", "quarantined", "rollback-pending"}
VERIFIED_TASK_STATES = {"verified", "skipped"}
PATCHABLE_PLAN_FIELDS = {
    "scope",
    "obligations",
    "tasks",
    "validations",
    "artifacts",
    "delivery",
    "activation",
    "route",
    "handoff",
}
PLAN_STATES = {
    "active",
    "candidate-ready",
    "switching",
    "validating",
    "publishing",
    "complete",
    "retired",
    "blocked",
}
WORK_ITEM_STATES = {"pending", "in_progress", "blocked", "verified", "skipped"}
ARTIFACT_STATES = {"pending", "final"} | BLOCKING_ARTIFACT_STATES
EXCLUSION_DISPOSITIONS = {
    "not_required",
    "deferred",
    "pending_confirmation",
    "transferred",
    "forbidden",
    "completed",
}
BLOCKING_EXCLUSION_DISPOSITIONS = {"deferred", "pending_confirmation"}
DELIVERY_STATES = {"pending", "in_progress", "complete"}
ACTIVATION_STATES = {
    "not_required",
    "deferred",
    "pending_confirmation",
    "in_progress",
    "active",
    "declined",
}
BLOCKING_ACTIVATION_STATES = {"deferred", "pending_confirmation", "in_progress"}
ROUTE_STATES = {"active", "awaiting_confirmation", "terminal"}
CONFIRMATION_STATES = {"pending", "accepted", "declined"}
INTERVENTION_KINDS = {
    "plan_contract",
    "external_authority",
    "deviation_recovery",
}
HIGH_IMPACT_ACTION_KINDS = {
    "remote_write",
    "production_change",
    "destructive_operation",
    "secret_handling",
    "substantive_rollback",
}
MODEL_RISK_ACTION_KINDS = HIGH_IMPACT_ACTION_KINDS | {
    "local_edit",
    "local_commit",
    "remote_read",
    "data_read",
    "data_write",
}
WORKTREE_LEDGER_ID_RE = re.compile(r"^WT-[A-Za-z0-9._-]{1,80}$")
MAX_ACTION_AUTHORIZATION_TTL_SECONDS = 900
MAX_ACTION_LEASE_TTL_SECONDS = 86400
MAX_ACTION_LEASE_AUTHORIZATIONS = 100
ACTION_DIGEST_POLICIES = {"exact-list", "dynamic"}
INTERVENTION_CONTRACT_STATES = {
    "STRICT_READY",
    "LEGACY_CLASSIFICATION_REQUIRED",
    "INVALID",
}
USER_INTERVENTION_STATES = {
    "NOT_REQUIRED",
    "REQUIREMENT_INPUT_REQUIRED",
    "PLAN_DECISION_REQUIRED",
    "AUTHORITY_REQUIRED",
    "DEVIATION_DECISION_REQUIRED",
}
INDEPENDENT_REVIEW_MODES = {
    "plan_challenge",
    "artifact_review",
    "evidence_audit",
}
INDEPENDENT_REVIEW_STATES = {"pending", "verified", "degraded"}
INDEPENDENT_FINDING_SEVERITIES = {"blocker", "high", "medium", "low"}
INDEPENDENT_FINDING_STATES = {"open", "resolved"}
INDEPENDENT_BLOCKING_SEVERITIES = {"blocker", "high"}
UNKNOWN_STATES = {"open", "resolved"}
UNKNOWN_OWNERS = {"user", "agent"}
UNKNOWN_IMPACTS = {"blocking", "non_blocking"}
INTAKE_DECISIONS = {"proceed", "explore", "ask"}
INTAKE_CLASSIFICATIONS = {"no_plan", "plan_controlled"}
VALIDATION_PROVENANCE_KINDS = {
    "confirmed-obligation",
    "observed-failure",
    "code-invariant",
    "supported-integration-boundary",
}
REVISION_KINDS = {
    "admission",
    "adaptation",
    "contract-revision",
    "contract-upgrade",
    "structural-rebase",
    "confirmation-added",
    "confirmation-classified",
    "confirmation-decided",
    "unknown-added",
    "unknown-classified",
    "unknown-resolved",
    "intake-recorded",
    "controlled-transition",
    "activation-contract-repaired",
    "independent-review-recorded",
    "retirement",
}
RETIREMENT_DISPOSITIONS = {
    "superseded",
    "not_required",
    "transferred",
    "preserved",
}
EVIDENCE_MANIFEST_MAX_BYTES = 64 * 1024
EVIDENCE_MANIFEST_MAX_ITEMS = 64
EVIDENCE_CAPTURE_MAX_BYTES = 1024 * 1024
EVIDENCE_CAPTURE_KIND_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
EVIDENCE_CAPTURE_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
EVIDENCE_CAPTURE_ID_RE = re.compile(r"^E-\d{8}T\d{6}Z-[0-9a-f]{12}$")
REVIEWER_ACQUISITION_ID_RE = re.compile(r"^RA-[0-9a-f]{32}$")
REVIEWER_ACQUISITION_MECHANISM_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
REVIEWER_ACQUISITION_MAX_BYTES = 64 * 1024
REVIEWER_ACQUISITION_MAX_COOLDOWN_SECONDS = 86400
REVIEWER_ACQUISITION_MAX_ATTEMPTS = 32
REVIEWER_FAILURE_CLASSES = {
    "network_proxy_blocked",
    "auth_unavailable",
    "command_missing",
    "timeout",
    "attestor_untrusted",
    "unknown_failure",
}
MECHANISM_SCOPED_REVIEWER_FAILURE_CLASSES = {
    "network_proxy_blocked",
    "auth_unavailable",
    "command_missing",
    "timeout",
    "attestor_untrusted",
}
TASK_TRANSITIONS = {
    "pending": {"in_progress", "blocked", "skipped"},
    "in_progress": {"blocked", "verified", "skipped"},
    "blocked": {"in_progress", "skipped"},
    "verified": set(),
    "skipped": set(),
}
AUTHORITY_STATES = {
    "UNMANAGED_EMPTY",
    "MIGRATION_REQUIRED",
    "AUTHORITY_REGISTRATION_REQUIRED",
    "AUTHORITY_REVIEW_REQUIRED",
    "RECONCILIATION_REQUIRED",
    "GOVERNED_ACTIVE",
    "PLAN_SCHEMA_REFRESH_REQUIRED",
    "MIGRATION_RECOVERY_REQUIRED",
}
AUTHORITY_CLASSIFICATIONS = {
    "CONFIRMED_AUTHORITY",
    "LIKELY_AUTHORITY",
    "NON_AUTHORITY",
}
SOURCE_ROLES = {"merged-source", "unmerged-source"}
POINTER_MARKER = "WORK_GOVERNANCE_NON_AUTHORITY_POINTER"
AUTHORITY_MODEL = "single-active"
AUTHORITY_STATE = "governed"
AUTHORITY_BLOCKED_COMMANDS = [
    "plan authority inspect",
    "plan authority check",
    "plan schema-validate",
    "plan validate",
    "plan status",
    "plan reconcile apply",
    "plan reconcile recover",
    "plan reconcile-upgrade apply",
    "plan reconcile-upgrade recover",
    "plan contract upgrade status",
    "plan contract upgrade recover",
    "plan structural-rebase recover",
    "plan rollover apply",
    "plan rollover recover",
    "plan retire apply",
    "plan retire recover",
]
SCHEMA_REFRESH_ALLOWED_COMMANDS = [
    "plan authority inspect",
    "plan authority check",
    "plan schema-validate",
    "plan validate",
    "plan status",
    "plan show",
    "plan history list|show",
    "goal show",
    "gate list|check",
    "truth list|conflicts",
    "review status|request",
    "risk inspect",
    "migrate inspect|apply|recover",
    "migrate rollback-info",
    "doctor",
]
GOVERNANCE_DIR_NAME = ".work-governance"
PLAN_DIR_NAME = "_Plan"
LAYOUT_SCHEMA_VERSION = 1
LAYOUT_VERSION = 1
BOOTSTRAP_CONTRACT_VERSION = 1
READY_RECEIPT_SCHEMA_VERSION = 2
READY_RECEIPT_KEYS = {
    "schema_version",
    "bootstrap_contract_version",
    "action_revision",
    "updated_at",
    "status",
    "plugin_build",
    "plugin_manifest_sha256",
    "current_plan_schema_version",
    "project_input_sha256",
    "project_output_sha256",
    "layout_state",
    "evidence_ref",
    "session_id",
    "runtime_bundle_ref",
    "runtime_manifest_sha256",
    "controller_ref",
    "controller_sha256",
    "lifecycle_ref",
    "lifecycle_sha256",
}
PLUGIN_COMPATIBILITY = ">=1.0.0,<2.0.0"
LEGACY_MIGRATION_ACTION_REVISION = 4
SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS = {
    2,
    3,
    LEGACY_MIGRATION_ACTION_REVISION,
}
BOOTSTRAP_ACTION_REVISION = 5
SUPPORTED_BOOTSTRAP_ACTION_REVISIONS = {2, 3, 4, BOOTSTRAP_ACTION_REVISION}
BOOTSTRAP_CLAIM_NAME = "bootstrap-claim.json"
BOOTSTRAP_CAPABILITY_NAME = "bootstrap-capability.json"
SESSIONS_DIR_NAME = "sessions"
LOCK_TIMEOUT_SECONDS = 15.0
LEGACY_ADOPTION_NAME = "legacy-adoption.json"
BOOTSTRAP_STAGING_NAME = ".work-governance.bootstrap"
BOOTSTRAP_CLAIM_KEYS = {
    "schema_version",
    "kind",
    "bootstrap_contract_version",
    "action_revision",
    "project_root",
    "created_at",
    "creator",
    "controller_sha256",
    "project_input_sha256",
}
LEGACY_ADOPTION_KEYS = {
    "schema_version",
    "kind",
    "action_revision",
    "project_root",
    "worktree_identity",
    "active_plan_id",
    "active_plan_path",
    "legacy_manifest_sha256",
    "controller_sha256",
    "confirmation_ref",
    "created_at",
}
BLOCKED_BOOTSTRAP_RECEIPT_KEYS = {
    "schema_version",
    "bootstrap_contract_version",
    "action_revision",
    "updated_at",
    "status",
    "reason",
    "plugin_build",
    "plugin_manifest_sha256",
    "project_input_sha256",
    "claim_sha256",
    "evidence_ref",
    "evidence_sha256",
}
BLOCKED_BOOTSTRAP_EVIDENCE_CONTEXT_KEYS = {"hook_source", "session_id"}
BOOTSTRAP_HOOK_SOURCES = {"startup", "resume", "clear", "compact"}
BOOTSTRAP_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
BOOTSTRAP_EVIDENCE_NAME_RE = re.compile(r"^\d{8}T\d{6}\.\d{6}Z-\d+\.json$")
LAYOUT_TRANSACTION_RE = re.compile(
    r"^LAY-\d{8}T\d{6}Z-[0-9a-f]{8}(?:-[0-9a-f]{8}(?:[0-9a-f]{8}){0,3})?$"
)
PREPARING_LAYOUT_JOURNAL_KEYS = {
    "schema_version",
    "kind",
    "transaction_id",
    "status",
    "created_at",
    "updated_at",
    "active_plan_id",
    "active_plan_path",
    "legacy_manifest",
    "legacy_manifest_sha256",
    "legacy_proposals_manifest",
    "legacy_proposals_sha256",
    "legacy_adoption_sha256",
    "git_baseline",
    "planned_log_files",
    "paths",
    "completed_operations",
}
ABORTED_LAYOUT_JOURNAL_KEYS = {
    *PREPARING_LAYOUT_JOURNAL_KEYS,
    "preparing_journal_sha256",
}
ACTIVE_LAYOUT_JOURNAL_KEYS = {
    "schema_version",
    "kind",
    "transaction_id",
    "status",
    "created_at",
    "updated_at",
    "active_plan_id",
    "active_plan_path",
    "legacy_manifest",
    "legacy_manifest_sha256",
    "legacy_proposals_manifest",
    "legacy_proposals_sha256",
    "legacy_adoption_sha256",
    "git_baseline",
    "paths",
    "completed_operations",
    "new_layout_manifest",
    "new_layout_baseline_sha256",
    "conversion_table",
    "conversion_table_sha256",
    "log_files",
    "proposal_trees",
    "new_proposals_baseline_sha256",
}
ACTION_UPGRADE_JOURNAL_KEYS = {
    "schema_version",
    "kind",
    "transaction_id",
    "status",
    "created_at",
    "updated_at",
    "from_action_revision",
    "to_action_revision",
    "version_before_sha256",
    "version_after_sha256",
    "git_baseline",
    "active_plan_id",
    "active_plan_path",
    "active_plan_before_sha256",
    "active_plan_after_sha256",
    "active_plan_revision_before",
    "active_plan_revision_after",
    "index_sha256",
    "conversion_table",
    "conversion_table_sha256",
    "proof_relative_path",
    "proof_sha256",
    "paths",
    "completed_operations",
}
ACTION_UPGRADE_PROOF_KEYS = {
    "schema_version",
    "kind",
    "transaction_id",
    "status",
    "from_action_revision",
    "to_action_revision",
    "active_plan_id",
    "active_plan_path",
    "active_plan_before_sha256",
    "active_plan_after_sha256",
    "active_plan_revision_before",
    "active_plan_revision_after",
    "version_before_sha256",
    "version_after_sha256",
    "conversion_table_sha256",
    "created_at",
}
LAYOUT_STATES = {
    "LAYOUT_READY",
    "LEGACY_CLASSIFICATION_REQUIRED",
    "LAYOUT_MIGRATION_REQUIRED",
    "LAYOUT_RECOVERY_REQUIRED",
    "RECONCILIATION_REQUIRED",
    "LEGACY_ROOT_REAPPEARED",
    "ENVIRONMENT_BLOCKED",
}
LAYOUT_GITIGNORE = """/logs/
/worktrees/
/cache/
/proposals/
/evidence/
/runtime/
/bootstrap-state.json
/workctl.lock
"""
LAYOUT_VERSION_KEYS = {
    "schema_version",
    "layout_version",
    "bootstrap_contract_version",
    "plugin_compatibility",
    "legacy_migration_action_revision",
    "migration",
}
LAYOUT_MIGRATION_KEYS = {
    "status",
    "transaction_id",
    "legacy_manifest_sha256",
    "new_layout_baseline_sha256",
    "completion_evidence",
}
LAYOUT_PROOF_KEYS = {
    "schema_version",
    "kind",
    "transaction_id",
    "status",
    "legacy_manifest_sha256",
    "legacy_adoption_sha256",
    "conversion_table_sha256",
    "created_at",
}
LAYOUT_PROPOSAL_PROOF_KEYS = {
    *LAYOUT_PROOF_KEYS,
    "legacy_proposals_sha256",
    "new_proposals_baseline_sha256",
}
LEGACY_LAYOUT_DIRECT_NAMES = {
    "index.yaml",
    ".workctl.lock",
    "archive",
    ".migrations",
    ".rollovers",
    "proposals",
}
LEGACY_LAYOUT_FEATURE_NAMES = LEGACY_LAYOUT_DIRECT_NAMES - {"proposals"}
LAYOUT_ALLOWED_COMMANDS = [
    "layout status",
    "layout validate",
    "layout adopt",
    "layout migrate",
    "layout recover",
]


class WorkctlError(RuntimeError):
    """User-facing controller error."""


@dataclass(frozen=True)
class PlanDocument:
    path: Path
    frontmatter: dict[str, Any]
    body: str


@dataclass(frozen=True)
class AuthorityCandidate:
    """Describe one semantic Plan-authority candidate."""

    path: str
    classification: str
    origin: str
    signals: list[str]
    sha256: str
    plan_id: str | None = None
    revision: int | None = None
    status: str | None = None


@dataclass(frozen=True)
class AuthorityReport:
    """Describe the deterministic authority state for a project."""

    state: str
    candidates: list[AuthorityCandidate]
    blockers: list[str]
    allowed_commands: list[str]


@dataclass(frozen=True)
class LegacyLayoutReport:
    """Describe deterministic classification of a project-root legacy Plan tree."""

    classification: str
    blockers: list[str]
    active_plan_id: str | None
    active_plan_path: str | None
    manifest_sha256: str | None


@dataclass(frozen=True)
class LayoutReport:
    """Describe the independent project layout state."""

    state: str
    blockers: list[str]
    legacy: LegacyLayoutReport
    allowed_commands: list[str]


@dataclass(frozen=True)
class ReconciliationRecoveryInventory:
    """Prevalidated paths used by a reconciliation recovery transaction."""

    staged_plan: Path
    target: Path
    sources: list[dict[str, Any]]
    agents_record: dict[str, Any] | None


@dataclass(frozen=True)
class ContractUpgradePreparation:
    """Hold an authenticated schema-v3 source and its prepared schema-v4 target."""

    manifest: dict[str, Any]
    upgraded: PlanDocument
    source_sha256: str
    intake_binding: dict[str, object] | None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def valid_reference(value: object) -> bool:
    """Return whether a value is a typed, non-whitespace authority reference."""
    return module_valid_reference(value, REFERENCE_RE)


def project_root() -> Path:
    """Resolve the physical root of the current Git worktree or local directory."""
    return module_paths.project_root()


def governance_root(root: Path) -> Path:
    """Return the only project-level root owned by Work Governance 1.0."""
    return module_paths.governance_root(root, GOVERNANCE_DIR_NAME)


def plan_dir(root: Path) -> Path:
    """Return the only normal Plan authority directory."""
    return module_paths.plan_dir(root, GOVERNANCE_DIR_NAME, PLAN_DIR_NAME)


def legacy_plan_dir(root: Path) -> Path:
    """Return the project-root legacy Plan directory used only by layout migration."""
    return module_paths.legacy_plan_dir(root, PLAN_DIR_NAME)


def legacy_logs_dir(root: Path) -> Path:
    """Return the old shared log root used only by migration compatibility."""
    return module_paths.legacy_logs_dir(root)


def logs_dir(root: Path) -> Path:
    """Return the local append-only process evidence directory."""
    return module_paths.logs_dir(root, GOVERNANCE_DIR_NAME)


def worktrees_dir(root: Path) -> Path:
    """Return the default directory for worktrees created after layout 1."""
    return module_paths.worktrees_dir(root, GOVERNANCE_DIR_NAME)


def cache_dir(root: Path) -> Path:
    """Return the Plugin-owned project cache directory."""
    return module_paths.cache_dir(root, GOVERNANCE_DIR_NAME)


def uv_cache_dir(root: Path) -> Path:
    """Return the isolated UV cache used by bootstrap and the controller."""
    return module_paths.uv_cache_dir(root, GOVERNANCE_DIR_NAME)


def proposals_dir(root: Path) -> Path:
    """Return the local non-authoritative proposal directory."""
    return module_paths.proposals_dir(root, GOVERNANCE_DIR_NAME)


def evidence_dir(root: Path) -> Path:
    """Return the local validation evidence directory."""
    return module_paths.evidence_dir(root, GOVERNANCE_DIR_NAME)


def runtime_dir(root: Path) -> Path:
    """Return the local recoverable transaction and staging directory."""
    return module_paths.runtime_dir(root, GOVERNANCE_DIR_NAME)


def bootstrap_claim_path(root: Path) -> Path:
    """Return the durable marker proving who first created the governance root."""
    return module_paths.bootstrap_claim_path(root, GOVERNANCE_DIR_NAME, BOOTSTRAP_CLAIM_NAME)


def legacy_adoption_path(root: Path) -> Path:
    """Return the worktree-local explicit legacy adoption receipt."""
    return module_paths.legacy_adoption_path(root, GOVERNANCE_DIR_NAME, LEGACY_ADOPTION_NAME)


def bootstrap_staging_path(root: Path) -> Path:
    """Return the sibling used to durably prepare a first-owner claim."""
    return module_paths.bootstrap_staging_path(root, BOOTSTRAP_STAGING_NAME)


def version_path(root: Path) -> Path:
    """Return the versioned layout contract."""
    return module_paths.version_path(root, GOVERNANCE_DIR_NAME)


def governance_ignore_path(root: Path) -> Path:
    """Return the versioned local-content ignore contract."""
    return module_paths.governance_ignore_path(root, GOVERNANCE_DIR_NAME)


def bootstrap_state_path(root: Path) -> Path:
    """Return the local exact-build and incremental bootstrap receipt."""
    return module_paths.bootstrap_state_path(root, GOVERNANCE_DIR_NAME)


def session_state_dir(root: Path, session_id: str) -> Path:
    """Return a bounded project-local directory for one Codex session."""
    try:
        return module_paths.session_state_dir(
            root,
            session_id,
            governance_dir_name=GOVERNANCE_DIR_NAME,
            sessions_dir_name=SESSIONS_DIR_NAME,
            session_id_pattern=SESSION_ID_RE,
        )
    except ModulePathError as exc:
        raise WorkctlError(str(exc)) from exc


def session_receipt_path(root: Path, session_id: str) -> Path:
    """Return the canonical READY receipt path for one Codex session."""
    try:
        return module_paths.session_receipt_path(
            root,
            session_id,
            governance_dir_name=GOVERNANCE_DIR_NAME,
            sessions_dir_name=SESSIONS_DIR_NAME,
            session_id_pattern=SESSION_ID_RE,
        )
    except ModulePathError as exc:
        raise WorkctlError(str(exc)) from exc


def session_capability_path(root: Path, session_id: str) -> Path:
    """Return the bootstrap-only capability path for one Codex session."""
    try:
        return module_paths.session_capability_path(
            root,
            session_id,
            governance_dir_name=GOVERNANCE_DIR_NAME,
            sessions_dir_name=SESSIONS_DIR_NAME,
            session_id_pattern=SESSION_ID_RE,
            bootstrap_capability_name=BOOTSTRAP_CAPABILITY_NAME,
        )
    except ModulePathError as exc:
        raise WorkctlError(str(exc)) from exc


def scoped_session_paths(root: Path, name: str) -> list[Path]:
    """List regular session control paths without following session-root symlinks."""
    try:
        return module_paths.scoped_session_paths(
            root,
            name,
            governance_dir_name=GOVERNANCE_DIR_NAME,
            sessions_dir_name=SESSIONS_DIR_NAME,
            session_id_pattern=SESSION_ID_RE,
        )
    except ModulePathError as exc:
        raise WorkctlError(str(exc)) from exc


def ready_receipt_paths(root: Path, *, allow_bootstrapping: bool) -> list[Path]:
    """Return legacy plus session-scoped receipt candidates."""
    try:
        return module_paths.ready_receipt_paths(
            root,
            allow_bootstrapping=allow_bootstrapping,
            governance_dir_name=GOVERNANCE_DIR_NAME,
            sessions_dir_name=SESSIONS_DIR_NAME,
            session_id_pattern=SESSION_ID_RE,
            bootstrap_capability_name=BOOTSTRAP_CAPABILITY_NAME,
        )
    except ModulePathError as exc:
        raise WorkctlError(str(exc)) from exc


def load_controller_receipt_v2(
    path: Path,
    *,
    allow_bootstrapping: bool,
) -> dict[str, Any] | None:
    """Load a structurally valid READY or bootstrap-only controller receipt."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != READY_RECEIPT_KEYS
        or payload.get("schema_version") != READY_RECEIPT_SCHEMA_VERSION
        or payload.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
        or payload.get("action_revision") != BOOTSTRAP_ACTION_REVISION
        or not isinstance(payload.get("session_id"), str)
        or not payload.get("session_id")
        or payload.get("current_plan_schema_version") != CURRENT_PLAN_SCHEMA_VERSION
    ):
        return None
    status_and_layout = (payload.get("status"), payload.get("layout_state"))
    allowed_states = {("READY", "LAYOUT_READY")}
    if allow_bootstrapping:
        allowed_states.add(("BOOTSTRAPPING", "BOOTSTRAPPING"))
    if status_and_layout not in allowed_states:
        return None
    for field in (
        "plugin_manifest_sha256",
        "project_input_sha256",
        "project_output_sha256",
        "runtime_manifest_sha256",
        "controller_sha256",
        "lifecycle_sha256",
    ):
        value = payload.get(field)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            return None
    return cast(dict[str, Any], payload)


def load_ready_receipt_v2(root: Path) -> dict[str, Any] | None:
    """Load one structurally valid READY receipt for read-only compatibility."""
    for path in ready_receipt_paths(root, allow_bootstrapping=False):
        receipt = load_controller_receipt_v2(path, allow_bootstrapping=False)
        if receipt is not None:
            return receipt
    return None


def bootstrap_capability_path(root: Path) -> Path:
    """Return the current SessionStart-only capability used for layout writes."""
    return module_paths.bootstrap_capability_path(
        root,
        GOVERNANCE_DIR_NAME,
        BOOTSTRAP_CAPABILITY_NAME,
    )


def workctl_lock_path(root: Path) -> Path:
    """Return the stable lock shared by every Work Governance 1.x controller."""
    return module_paths.workctl_lock_path(root, GOVERNANCE_DIR_NAME)


def index_path(root: Path) -> Path:
    return module_paths.index_path(root, GOVERNANCE_DIR_NAME, PLAN_DIR_NAME)


def plan_relative_path(*parts: str) -> str:
    """Build a project-relative path below the canonical Plan directory."""
    return module_paths.plan_relative_path(
        *parts,
        governance_dir_name=GOVERNANCE_DIR_NAME,
        plan_dir_name=PLAN_DIR_NAME,
    )


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA256 digest for *content*."""
    return module_filesystem.sha256_bytes(content)


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest for a regular file."""
    try:
        return module_filesystem.sha256_file(path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def relative_project_path(root: Path, path: Path) -> str:
    """Return a stable project-relative POSIX path."""
    try:
        return module_filesystem.relative_project_path(root, path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def reject_symlink_components(root: Path, path: Path) -> None:
    """Reject an existing symlink in a project-local control path chain."""
    try:
        module_filesystem.reject_symlink_components(root, path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def checked_project_path(root: Path, raw_path: str) -> Path:
    """Resolve a manifest path while preventing project-root escape."""
    try:
        return module_filesystem.checked_project_path(root, raw_path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def runtime_bundle_manifest_payload(
    *,
    plugin_build: object,
    plugin_manifest_sha256: object,
    current_plan_schema_version: object,
    controller_ref: object,
    controller_sha256: object,
    lifecycle_ref: object,
    lifecycle_sha256: object,
    module_files: object | None = None,
) -> dict[str, object]:
    """Build the canonical runtime bundle manifest projection."""
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-runtime-bundle",
        "plugin_build": plugin_build,
        "plugin_manifest_sha256": plugin_manifest_sha256,
        "current_plan_schema_version": current_plan_schema_version,
        "controller_ref": controller_ref,
        "controller_sha256": controller_sha256,
        "lifecycle_ref": lifecycle_ref,
        "lifecycle_sha256": lifecycle_sha256,
    }
    if module_files is not None:
        payload["module_files"] = module_files
    return payload


def validated_runtime_bundle_module_files(
    bundle: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, str]] | None:
    """Validate the optional module file manifest and return it unchanged."""
    module_files = manifest.get("module_files")
    if module_files is None:
        return None
    if not isinstance(module_files, list):
        raise WorkctlError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
    typed_files: list[dict[str, str]] = []
    for entry in module_files:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256"}
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("sha256"), str)
            or not SHA256_RE.fullmatch(entry["sha256"])
        ):
            raise WorkctlError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
        module_path = bundle / entry["path"]
        if (
            module_path.parent.parent != bundle
            or module_path.is_symlink()
            or not module_path.is_file()
            or sha256_file(module_path) != entry["sha256"]
        ):
            raise WorkctlError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
        typed_files.append({"path": entry["path"], "sha256": entry["sha256"]})
    return typed_files


def validate_current_ready_receipt(
    root: Path,
    supplied_sha256: str | None,
    *,
    require_current_controller: bool,
    allow_bootstrapping: bool = False,
) -> dict[str, Any]:
    """Bind a command to the latest READY receipt and exact runtime bundle."""
    if not isinstance(supplied_sha256, str) or SHA256_RE.fullmatch(supplied_sha256) is None:
        raise WorkctlError("BOOTSTRAP_RECEIPT_REQUIRED")
    candidates = ready_receipt_paths(root, allow_bootstrapping=allow_bootstrapping)
    regular_candidates = [path for path in candidates if not path.is_symlink() and path.is_file()]
    receipt_path = next(
        (path for path in regular_candidates if sha256_file(path) == supplied_sha256),
        None,
    )
    if receipt_path is None and regular_candidates:
        raise WorkctlError("BOOTSTRAP_RECEIPT_SUPERSEDED")
    if receipt_path is None:
        raise WorkctlError("BOOTSTRAP_RECEIPT_INVALID")
    receipt = load_controller_receipt_v2(
        receipt_path,
        allow_bootstrapping=allow_bootstrapping,
    )
    if receipt is None:
        raise WorkctlError("BOOTSTRAP_RECEIPT_INVALID")
    bundle = checked_project_path(root, str(receipt["runtime_bundle_ref"]))
    controller = checked_project_path(root, str(receipt["controller_ref"]))
    lifecycle = checked_project_path(root, str(receipt["lifecycle_ref"]))
    manifest = bundle / "manifest.json"
    reject_symlink_components(root, bundle)
    if (
        bundle.is_symlink()
        or not bundle.is_dir()
        or controller.parent != bundle
        or lifecycle.parent != bundle
        or controller.name != "workctl.py"
        or lifecycle.name != "work-lifecycle.SKILL.md"
        or controller.is_symlink()
        or lifecycle.is_symlink()
        or not controller.is_file()
        or not lifecycle.is_file()
        or manifest.is_symlink()
        or not manifest.is_file()
        or sha256_file(controller) != receipt["controller_sha256"]
        or sha256_file(lifecycle) != receipt["lifecycle_sha256"]
        or sha256_file(manifest) != receipt["runtime_manifest_sha256"]
    ):
        raise WorkctlError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
    try:
        runtime_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WorkctlError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID") from exc
    if not isinstance(runtime_manifest, dict):
        raise WorkctlError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
    module_files = validated_runtime_bundle_module_files(bundle, runtime_manifest)
    expected_manifest = runtime_bundle_manifest_payload(
        plugin_build=receipt["plugin_build"],
        plugin_manifest_sha256=receipt["plugin_manifest_sha256"],
        current_plan_schema_version=CURRENT_PLAN_SCHEMA_VERSION,
        controller_ref=receipt["controller_ref"],
        controller_sha256=receipt["controller_sha256"],
        lifecycle_ref=receipt["lifecycle_ref"],
        lifecycle_sha256=receipt["lifecycle_sha256"],
        module_files=module_files,
    )
    if runtime_manifest != expected_manifest:
        raise WorkctlError("BOOTSTRAP_RUNTIME_BUNDLE_INVALID")
    if require_current_controller and Path(__file__).resolve() != controller:
        raise WorkctlError("CONTROLLER_RECEIPT_MISMATCH")
    return receipt


def is_legacy_plan_authority_path(root: Path, raw_path: str, path: Path) -> bool:
    """Return whether a normal authority path enters the project-root ``_Plan``."""
    normalized = Path(os.path.normpath(raw_path))
    lexical_legacy = bool(normalized.parts and normalized.parts[0] == PLAN_DIR_NAME)
    legacy = legacy_plan_dir(root).resolve()
    resolved = path.resolve()
    physical_legacy = resolved == legacy or legacy in resolved.parents
    return lexical_legacy or physical_legacy


def reject_legacy_plan_authority_path(root: Path, raw_path: str, path: Path) -> None:
    """Prevent normal authority commands from reading or writing root ``_Plan``."""
    if is_legacy_plan_authority_path(root, raw_path, path):
        raise WorkctlError(f"LEGACY_ROOT_AUTHORITY_FORBIDDEN: {raw_path}")


def tree_manifest(path: Path, *, exclude_names: set[str] | None = None) -> list[dict[str, object]]:
    """Return a stable, content-addressed manifest for one regular directory tree.

    Symlinks are rejected because a migration input must be closed under the
    project directory. Transient lock files may be excluded by exact name.
    """
    if path.is_symlink() or not path.is_dir():
        raise WorkctlError(f"MANIFEST_ROOT_INVALID: {path}")
    excluded = exclude_names or set()
    entries: list[dict[str, object]] = []
    for candidate in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        relative = candidate.relative_to(path).as_posix()
        if candidate.name in excluded:
            continue
        if candidate.is_symlink():
            raise WorkctlError(f"LAYOUT_PATH_SYMLINK: {candidate}")
        if candidate.is_dir():
            entries.append({"path": relative, "kind": "directory"})
        elif candidate.is_file():
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size": candidate.stat().st_size,
                    "sha256": sha256_file(candidate),
                }
            )
        else:
            raise WorkctlError(f"LAYOUT_PATH_NOT_REGULAR: {candidate}")
    return entries


def manifest_sha256(entries: list[dict[str, object]]) -> str:
    """Hash a stable tree manifest without depending on YAML presentation."""
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def proposal_manifest_from_plan_manifest(
    legacy_manifest: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Project the exact ``proposals/`` subtree from a complete legacy Plan manifest."""
    prefix = "proposals/"
    projected: list[dict[str, object]] = []
    for entry in legacy_manifest:
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.startswith(prefix):
            continue
        projected.append(
            {
                **entry,
                "path": raw_path.removeprefix(prefix),
            }
        )
    return projected


def manifest_matches_allowed_subset(
    path: Path,
    allowed_paths: set[str],
    expected_file_hashes: dict[str, str] | None = None,
) -> bool:
    """Return whether a regular tree contains only journal-bound paths and bytes."""
    expected_hashes = expected_file_hashes or {}
    for entry in tree_manifest(path):
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or raw_path not in allowed_paths:
            return False
        if (
            entry.get("kind") == "file"
            and raw_path in expected_hashes
            and entry.get("sha256") != expected_hashes[raw_path]
        ):
            return False
    return True


def bootstrap_claim_input_sha256(root: Path) -> str:
    """Fingerprint ownership-relevant project inputs before root bootstrap."""
    inputs: list[dict[str, object]] = []
    for name, path in (
        ("legacy-plan", legacy_plan_dir(root)),
        ("legacy-logs", legacy_logs_dir(root)),
        ("agents", root / "AGENTS.md"),
        ("claude", root / "CLAUDE.md"),
    ):
        if not path.exists() and not path.is_symlink():
            manifest: list[dict[str, object]] = []
        elif path.is_symlink():
            manifest = [{"path": ".", "kind": "symlink", "target": os.readlink(path)}]
        elif path.is_file():
            manifest = [
                {
                    "path": ".",
                    "kind": "file",
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            ]
        elif path.is_dir():
            try:
                manifest = tree_manifest(path, exclude_names={".workctl.lock"})
            except WorkctlError as exc:
                manifest = [{"path": ".", "kind": "unclosed", "reason": str(exc)}]
        else:
            manifest = [{"path": ".", "kind": "other"}]
        inputs.append({"name": name, "manifest": manifest})
    return sha256_bytes(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode())


def governance_claim_errors(root: Path, governance: Path | None = None) -> list[str]:
    """Validate the durable claim for an uncommitted governance root."""
    base = governance if governance is not None else governance_root(root)
    path = base / "runtime" / BOOTSTRAP_CLAIM_NAME
    if path.is_symlink() or not path.is_file():
        return ["uncommitted governance root lacks a regular bootstrap claim"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["uncommitted governance root has an invalid bootstrap claim"]
    if not isinstance(payload, dict) or set(payload) != BOOTSTRAP_CLAIM_KEYS:
        return ["uncommitted governance root has an invalid bootstrap claim contract"]
    errors: list[str] = []
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != "work-governance-bootstrap-claim"
        or payload.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
        or payload.get("action_revision") not in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS
        or payload.get("project_root") != root.resolve().as_posix()
        or payload.get("creator") not in {"workctl", "session-start"}
        or not isinstance(payload.get("created_at"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("controller_sha256")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("project_input_sha256")))
    ):
        errors.append("uncommitted governance root bootstrap claim fields are invalid")
    return errors


def uncommitted_governance_footprint_errors(root: Path) -> list[str]:
    """Reject content not produced by bootstrap or a registered layout transaction."""
    governance = governance_root(root)
    allowed = {
        PLAN_DIR_NAME,
        "logs",
        "worktrees",
        "cache",
        "proposals",
        "evidence",
        "runtime",
        ".gitignore",
        "bootstrap-state.json",
        "workctl.lock",
    }
    errors: list[str] = []
    unexpected = sorted(child.name for child in governance.iterdir() if child.name not in allowed)
    if unexpected:
        errors.append("uncommitted governance root has unknown entries: " + ", ".join(unexpected))
    ignore = governance / ".gitignore"
    if (ignore.exists() or ignore.is_symlink()) and (
        ignore.is_symlink() or not ignore.is_file() or ignore.read_text() != LAYOUT_GITIGNORE
    ):
        errors.append("uncommitted governance root has a non-canonical .gitignore")
    bootstrap_evidence, bootstrap_errors = uncommitted_bootstrap_record(root)
    errors.extend(bootstrap_errors)
    bootstrap_evidence, bootstrap_history_errors = uncommitted_bootstrap_evidence_history(
        root,
        bootstrap_evidence,
    )
    errors.extend(bootstrap_history_errors)
    for name in ("logs", "worktrees"):
        path = governance / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            errors.append(f"uncommitted governance local path is invalid: {name}")
        elif path.is_dir() and any(path.iterdir()):
            errors.append(f"uncommitted governance local path is not empty: {name}")
    cache = governance / "cache"
    if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
        errors.append("uncommitted governance cache path is invalid")
    elif cache.is_dir():
        cache_children = sorted(child.name for child in cache.iterdir() if child.name != "uv")
        if cache_children:
            errors.append(
                "uncommitted governance cache has unknown entries: " + ", ".join(cache_children)
            )
        uv_path = cache / "uv"
        if uv_path.is_symlink() or (uv_path.exists() and not uv_path.is_dir()):
            errors.append("uncommitted governance UV cache path is invalid")
    runtime = governance / "runtime"
    transaction_names: set[str] = set()
    if runtime.is_symlink() or not runtime.is_dir():
        errors.append("uncommitted governance runtime path is invalid")
    else:
        bundles_root = runtime / "plugin-builds"
        if bundles_root.exists() or bundles_root.is_symlink():
            if bundles_root.is_symlink() or not bundles_root.is_dir():
                errors.append("uncommitted runtime plugin-builds path is invalid")
            else:
                bundles = list(bundles_root.iterdir())
                if len(bundles) > 16:
                    errors.append("uncommitted runtime has too many plugin bundles")
                for bundle in bundles:
                    manifest_path = bundle / "manifest.json"
                    if (
                        bundle.is_symlink()
                        or not bundle.is_dir()
                        or SHA256_RE.fullmatch(bundle.name) is None
                        or manifest_path.is_symlink()
                        or not manifest_path.is_file()
                    ):
                        errors.append("uncommitted runtime plugin bundle is invalid")
                        continue
                    try:
                        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        errors.append("uncommitted runtime plugin manifest is invalid")
                        continue
                    if not isinstance(payload, dict):
                        errors.append("uncommitted runtime plugin manifest is invalid")
                        continue
                    controller = bundle / "workctl.py"
                    lifecycle = bundle / "work-lifecycle.SKILL.md"
                    if "current_plan_schema_version" in payload:
                        version = payload["current_plan_schema_version"]
                        if not isinstance(version, int) or version < 1:
                            errors.append("uncommitted runtime plugin manifest is invalid")
                            continue
                    else:
                        version = None
                    try:
                        module_files = validated_runtime_bundle_module_files(bundle, payload)
                    except WorkctlError:
                        errors.append("uncommitted runtime plugin module is invalid")
                        continue
                    expected = runtime_bundle_manifest_payload(
                        plugin_build=payload.get("plugin_build"),
                        plugin_manifest_sha256=bundle.name,
                        current_plan_schema_version=version,
                        controller_ref=relative_project_path(root, controller),
                        controller_sha256=sha256_file(controller)
                        if controller.is_file() and not controller.is_symlink()
                        else None,
                        lifecycle_ref=relative_project_path(root, lifecycle),
                        lifecycle_sha256=sha256_file(lifecycle)
                        if lifecycle.is_file() and not lifecycle.is_symlink()
                        else None,
                        module_files=module_files,
                    )
                    if version is None:
                        expected.pop("current_plan_schema_version", None)
                    if payload != expected:
                        errors.append("uncommitted runtime plugin bundle is invalid")
        capability = runtime / BOOTSTRAP_CAPABILITY_NAME
        if capability.exists() or capability.is_symlink():
            try:
                if capability.is_symlink() or not capability.is_file():
                    raise WorkctlError("bootstrap capability is not regular")
                validate_current_ready_receipt(
                    root,
                    sha256_file(capability),
                    require_current_controller=False,
                    allow_bootstrapping=True,
                )
            except WorkctlError:
                errors.append("uncommitted runtime bootstrap capability is invalid")
        runtime_unknown = sorted(
            child.name
            for child in runtime.iterdir()
            if child.name != BOOTSTRAP_CLAIM_NAME
            and child.name != BOOTSTRAP_CAPABILITY_NAME
            and child.name != LEGACY_ADOPTION_NAME
            and child.name != "plugin-builds"
            and LAYOUT_TRANSACTION_RE.fullmatch(child.name) is None
        )
        if runtime_unknown:
            errors.append(
                "uncommitted governance runtime has unknown entries: " + ", ".join(runtime_unknown)
            )
        transaction_names = {
            child.name
            for child in runtime.iterdir()
            if LAYOUT_TRANSACTION_RE.fullmatch(child.name) is not None
        }
        adoption = runtime / LEGACY_ADOPTION_NAME
        if adoption.is_symlink() or (adoption.exists() and not adoption.is_file()):
            errors.append("uncommitted legacy adoption receipt is not regular")
    proposals = proposals_dir(root)
    if proposals.is_symlink() or (proposals.exists() and not proposals.is_dir()):
        errors.append("uncommitted governance local path is invalid: proposals")
    else:
        expected_proposals: dict[str, list[dict[str, object]]] = {}
        active_journal_count = 0
        invalid_active_journal = False
        for transaction_name in sorted(transaction_names):
            journal_path = runtime / transaction_name / "journal.json"
            try:
                journal = load_layout_journal(journal_path)
                if journal.get("status") not in {"plan-activated", "version-pending"}:
                    continue
                active_journal_count += 1
                validate_active_layout_journal_artifacts(root, journal_path, journal)
                for record in layout_proposal_records(root, journal):
                    expected_proposals[str(record["migration_id"])] = cast(
                        list[dict[str, object]],
                        record["manifest"],
                    )
            except WorkctlError:
                invalid_active_journal = True
        actual_names = (
            {child.name for child in proposals.iterdir()} if proposals.is_dir() else set()
        )
        if (
            invalid_active_journal
            or active_journal_count > 1
            or not actual_names.issubset(expected_proposals)
        ):
            errors.append("uncommitted governance proposals are not transaction-bound")
        else:
            for name in actual_names:
                candidate = proposals / name
                if (
                    candidate.is_symlink()
                    or not candidate.is_dir()
                    or tree_manifest(candidate) != expected_proposals[name]
                ):
                    errors.append("uncommitted governance proposals are not transaction-bound")
                    break
    evidence = governance / "evidence"
    if evidence.is_symlink() or (evidence.exists() and not evidence.is_dir()):
        errors.append("uncommitted governance local path is invalid: evidence")
    elif evidence.is_dir() and any(evidence.iterdir()):
        migrations = evidence / "layout-migrations"
        bootstrap = evidence / "bootstrap"
        migration_children = (
            list(migrations.iterdir())
            if migrations.is_dir() and not migrations.is_symlink()
            else []
        )
        migration_names = {child.name for child in migration_children}
        allowed_evidence_children = {
            name
            for name, condition in (
                (
                    "bootstrap",
                    bootstrap.is_dir()
                    and not bootstrap.is_symlink()
                    and {child.resolve() for child in bootstrap.iterdir()} == bootstrap_evidence,
                ),
                (
                    "layout-migrations",
                    migrations.is_dir() and not migrations.is_symlink() and bool(transaction_names),
                ),
            )
            if condition
        }
        if (
            {child.name for child in evidence.iterdir()} != allowed_evidence_children
            or not migration_names.issubset(transaction_names)
            or any(child.is_symlink() or not child.is_dir() for child in migration_children)
        ):
            errors.append("uncommitted governance evidence is not transaction-bound")
    if (
        (governance / PLAN_DIR_NAME).exists()
        and not transaction_names
        and not legacy_plan_dir(root).exists()
    ):
        errors.append("uncommitted canonical Plan root lacks a layout transaction")
    return errors


def uncommitted_bootstrap_record(root: Path) -> tuple[set[Path], list[str]]:
    """Validate one claim-bound blocked receipt and its exact evidence bytes."""
    receipt_path = bootstrap_state_path(root)
    try:
        reject_symlink_components(root, receipt_path)
    except WorkctlError as exc:
        return set(), [str(exc)]
    if not receipt_path.exists() and not receipt_path.is_symlink():
        return set(), []
    if receipt_path.is_symlink() or not receipt_path.is_file():
        return set(), ["uncommitted bootstrap receipt is not regular"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), ["uncommitted bootstrap receipt is invalid"]
    if not isinstance(receipt, dict) or set(receipt) != BLOCKED_BOOTSTRAP_RECEIPT_KEYS:
        return set(), ["uncommitted bootstrap receipt contract is invalid"]
    errors: list[str] = []
    claim = bootstrap_claim_path(root)
    try:
        reject_symlink_components(root, claim)
    except WorkctlError as exc:
        return set(), [str(exc)]
    evidence_ref = receipt.get("evidence_ref")
    expected_prefix = f"evidence:{GOVERNANCE_DIR_NAME}/evidence/bootstrap/"
    if (
        receipt.get("schema_version") != 1
        or receipt.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
        or receipt.get("action_revision") not in SUPPORTED_BOOTSTRAP_ACTION_REVISIONS
        or receipt.get("status") != "ENVIRONMENT_BLOCKED"
        or not isinstance(receipt.get("updated_at"), str)
        or not isinstance(receipt.get("reason"), str)
        or not isinstance(receipt.get("plugin_build"), str)
        or SHA256_RE.fullmatch(str(receipt.get("plugin_manifest_sha256"))) is None
        or SHA256_RE.fullmatch(str(receipt.get("project_input_sha256"))) is None
        or SHA256_RE.fullmatch(str(receipt.get("claim_sha256"))) is None
        or SHA256_RE.fullmatch(str(receipt.get("evidence_sha256"))) is None
        or not isinstance(evidence_ref, str)
        or not evidence_ref.startswith(expected_prefix)
        or not claim.is_file()
        or sha256_file(claim) != receipt.get("claim_sha256")
    ):
        errors.append("uncommitted bootstrap receipt fields are invalid")
        return set(), errors
    try:
        evidence_relative = strict_bootstrap_evidence_relative(
            evidence_ref.removeprefix("evidence:")
        )
    except WorkctlError as exc:
        return set(), [str(exc)]
    evidence_path = root / evidence_relative
    try:
        reject_symlink_components(root, evidence_path)
    except WorkctlError as exc:
        return set(), [str(exc)]
    if (
        evidence_path.is_symlink()
        or not evidence_path.is_file()
        or sha256_file(evidence_path) != receipt.get("evidence_sha256")
    ):
        return set(), ["uncommitted bootstrap evidence is missing or drifted"]
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), ["uncommitted bootstrap evidence is invalid"]
    legacy_evidence_keys = (BLOCKED_BOOTSTRAP_RECEIPT_KEYS - {"evidence_sha256"}) | {"commands"}
    current_evidence_keys = legacy_evidence_keys | BLOCKED_BOOTSTRAP_EVIDENCE_CONTEXT_KEYS
    evidence_keys = set(evidence) if isinstance(evidence, dict) else set()
    if (
        not isinstance(evidence, dict)
        or evidence_keys not in (legacy_evidence_keys, current_evidence_keys)
        or (
            receipt.get("action_revision") == BOOTSTRAP_ACTION_REVISION
            and evidence_keys != current_evidence_keys
        )
        or (
            evidence_keys == current_evidence_keys
            and (
                evidence.get("hook_source") not in {*BOOTSTRAP_HOOK_SOURCES, None}
                or (
                    evidence.get("session_id") is not None
                    and BOOTSTRAP_SESSION_ID_RE.fullmatch(str(evidence.get("session_id"))) is None
                )
            )
        )
        or not isinstance(evidence.get("commands"), list)
        or any(evidence.get(key) != receipt.get(key) for key in receipt if key != "evidence_sha256")
    ):
        return set(), ["uncommitted bootstrap evidence contract is invalid"]
    return {evidence_path.resolve()}, []


def uncommitted_bootstrap_evidence_history(
    root: Path,
    current_evidence: set[Path],
) -> tuple[set[Path], list[str]]:
    """Validate prior non-authoritative blocked evidence retained before layout commit."""
    bootstrap = governance_root(root) / "evidence" / "bootstrap"
    if not bootstrap.exists() and not bootstrap.is_symlink():
        return current_evidence, []
    if bootstrap.is_symlink() or not bootstrap.is_dir():
        return current_evidence, ["uncommitted bootstrap evidence directory is invalid"]
    evidence_children = tuple(sorted(bootstrap.iterdir()))
    if evidence_children and len(current_evidence) != 1:
        return current_evidence, [
            "uncommitted bootstrap evidence history lacks one current receipt"
        ]

    claim_path = bootstrap_claim_path(root)
    if claim_path.is_symlink() or not claim_path.is_file():
        return current_evidence, ["uncommitted bootstrap evidence lacks a regular claim"]
    claim_sha256 = sha256_file(claim_path)

    allowed = set(current_evidence)
    errors: list[str] = []
    legacy_keys = (BLOCKED_BOOTSTRAP_RECEIPT_KEYS - {"evidence_sha256"}) | {"commands"}
    current_keys = legacy_keys | BLOCKED_BOOTSTRAP_EVIDENCE_CONTEXT_KEYS
    for evidence_path in evidence_children:
        relative = evidence_path.relative_to(root).as_posix()
        try:
            strict_bootstrap_evidence_relative(relative)
            reject_symlink_components(root, evidence_path)
        except WorkctlError as exc:
            errors.append(str(exc))
            continue
        if evidence_path.is_symlink() or not evidence_path.is_file():
            errors.append(f"uncommitted bootstrap evidence is not regular: {relative}")
            continue
        resolved = evidence_path.resolve()
        if resolved in current_evidence:
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"uncommitted bootstrap evidence is invalid: {relative}")
            continue
        expected_ref = f"evidence:{relative}"
        commands = evidence.get("commands") if isinstance(evidence, dict) else None
        evidence_keys = set(evidence) if isinstance(evidence, dict) else set()
        if (
            not isinstance(evidence, dict)
            or evidence_keys not in (legacy_keys, current_keys)
            or (
                evidence.get("action_revision") == BOOTSTRAP_ACTION_REVISION
                and evidence_keys != current_keys
            )
            or (
                evidence_keys == current_keys
                and (
                    evidence.get("hook_source") not in {*BOOTSTRAP_HOOK_SOURCES, None}
                    or (
                        evidence.get("session_id") is not None
                        and BOOTSTRAP_SESSION_ID_RE.fullmatch(str(evidence.get("session_id")))
                        is None
                    )
                )
            )
            or evidence.get("schema_version") != 1
            or evidence.get("bootstrap_contract_version") != BOOTSTRAP_CONTRACT_VERSION
            or evidence.get("action_revision") not in SUPPORTED_BOOTSTRAP_ACTION_REVISIONS
            or evidence.get("status") != "ENVIRONMENT_BLOCKED"
            or evidence.get("claim_sha256") != claim_sha256
            or SHA256_RE.fullmatch(str(evidence.get("project_input_sha256"))) is None
            or evidence.get("evidence_ref") != expected_ref
            or not isinstance(evidence.get("updated_at"), str)
            or not isinstance(evidence.get("reason"), str)
            or not isinstance(evidence.get("plugin_build"), str)
            or SHA256_RE.fullmatch(str(evidence.get("plugin_manifest_sha256"))) is None
            or not isinstance(commands, list)
            or any(
                not isinstance(command, dict)
                or set(command) != {"command", "returncode", "stderr", "stdout"}
                or not isinstance(command.get("command"), list)
                or not all(isinstance(argument, str) for argument in command["command"])
                or type(command.get("returncode")) is not int
                or not isinstance(command.get("stderr"), str)
                or not isinstance(command.get("stdout"), str)
                for command in commands
            )
        ):
            errors.append(f"uncommitted bootstrap evidence contract is invalid: {relative}")
            continue
        allowed.add(resolved)
    return allowed, errors


def strict_bootstrap_evidence_relative(raw_path: str) -> Path:
    """Parse one direct bootstrap evidence child without traversal segments."""
    path = Path(raw_path)
    expected_parent = Path(GOVERNANCE_DIR_NAME) / "evidence" / "bootstrap"
    if (
        not raw_path
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parent != expected_parent
        or BOOTSTRAP_EVIDENCE_NAME_RE.fullmatch(path.name) is None
    ):
        raise WorkctlError(f"INVALID_BOOTSTRAP_EVIDENCE_PATH: {raw_path}")
    return path


def rename_directory_noreplace(source: Path, target: Path) -> None:
    """Atomically activate a prepared root without replacing any target."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    if sys.platform == "darwin" and hasattr(library, "renamex_np"):
        result = library.renamex_np(
            ctypes.c_char_p(source_bytes),
            ctypes.c_char_p(target_bytes),
            ctypes.c_uint(0x00000004),
        )
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        result = library.renameat2(
            ctypes.c_int(-100),
            ctypes.c_char_p(source_bytes),
            ctypes.c_int(-100),
            ctypes.c_char_p(target_bytes),
            ctypes.c_uint(1),
        )
    else:
        raise WorkctlError("ATOMIC_NOREPLACE_RENAME_UNAVAILABLE")
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise WorkctlError("GOVERNANCE_ROOT_OWNERSHIP_CONFLICT")
        raise WorkctlError(f"GOVERNANCE_ROOT_ACTIVATION_FAILED: {os.strerror(error_number)}")


def create_governance_claim(root: Path, *, creator: str) -> None:
    """Prepare a claimed sibling, then atomically activate it without overwrite."""
    governance = governance_root(root)
    staging = bootstrap_staging_path(root)
    if staging.exists() or staging.is_symlink():
        staging_children = (
            sorted(child.name for child in staging.iterdir())
            if staging.is_dir() and not staging.is_symlink()
            else []
        )
        runtime_children = (
            sorted(child.name for child in (staging / "runtime").iterdir())
            if (staging / "runtime").is_dir() and not (staging / "runtime").is_symlink()
            else []
        )
        if (
            staging.is_symlink()
            or not staging.is_dir()
            or staging_children != ["runtime"]
            or runtime_children != [BOOTSTRAP_CLAIM_NAME]
            or governance_claim_errors(root, staging)
        ):
            raise WorkctlError("GOVERNANCE_BOOTSTRAP_STAGING_INVALID")
    else:
        staging.mkdir()
        (staging / "runtime").mkdir()
        fsync_directory(staging)
        payload = {
            "schema_version": 1,
            "kind": "work-governance-bootstrap-claim",
            "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
            "action_revision": LEGACY_MIGRATION_ACTION_REVISION,
            "project_root": root.resolve().as_posix(),
            "created_at": utc_now(),
            "creator": creator,
            "controller_sha256": sha256_file(Path(__file__)),
            "project_input_sha256": bootstrap_claim_input_sha256(root),
        }
        claim = staging / "runtime" / BOOTSTRAP_CLAIM_NAME
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(claim, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            fsync_directory(claim.parent)
        fsync_directory(staging)
        fsync_directory(root)
    if os.environ.get("WORKCTL_TEST_BOOTSTRAP_INTERRUPT_AFTER_CLAIM") == "1":
        raise WorkctlError("BOOTSTRAP_TEST_INTERRUPTED_AFTER_CLAIM")
    rename_directory_noreplace(staging, governance)
    fsync_directory(root)


def ensure_governance_ownership(root: Path) -> None:
    """Prove or establish ownership before any canonical-root mutation."""
    governance = governance_root(root)
    if not governance.exists() and not governance.is_symlink():
        create_governance_claim(root, creator="workctl")
        return
    if governance.is_symlink() or not governance.is_dir():
        raise WorkctlError("GOVERNANCE_ROOT_OWNERSHIP_UNPROVEN")
    if version_path(root).is_file():
        errors = layout_version_errors(root)
        if errors:
            raise WorkctlError("GOVERNANCE_VERSION_UNPROVEN: " + "; ".join(errors))
        return
    errors = governance_claim_errors(root)
    errors.extend(uncommitted_governance_footprint_errors(root))
    if errors:
        raise WorkctlError("GOVERNANCE_ROOT_OWNERSHIP_UNPROVEN: " + "; ".join(errors))


def ensure_layout_gitignore(root: Path) -> None:
    """Create the ignore contract only when no conflicting bytes exist."""
    path = governance_ignore_path(root)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_text() != LAYOUT_GITIGNORE:
            raise WorkctlError("LAYOUT_GITIGNORE_CONFLICT")
        return
    write_atomic(path, LAYOUT_GITIGNORE)


def layout_version_errors(root: Path) -> list[str]:
    """Validate the versioned layout and ignore contracts without mutating them."""
    path = version_path(root)
    if not path.is_file():
        return [f"missing {GOVERNANCE_DIR_NAME}/version.yaml"]
    try:
        payload = load_yaml_file(path)
    except (WorkctlError, yaml.YAMLError) as exc:
        return [str(exc)]
    errors: list[str] = []
    if set(payload) != LAYOUT_VERSION_KEYS:
        errors.append("version.yaml keys must match the layout contract")
    expected_scalars = {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "layout_version": LAYOUT_VERSION,
        "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
        "plugin_compatibility": PLUGIN_COMPATIBILITY,
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            errors.append(f"version.yaml {field} must be {expected}")
    if (
        payload.get("legacy_migration_action_revision")
        not in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS
    ):
        errors.append("version.yaml legacy_migration_action_revision must be a supported revision")
    migration = payload.get("migration")
    if not isinstance(migration, dict):
        errors.append("version.yaml migration must be a mapping")
    else:
        if set(migration) != LAYOUT_MIGRATION_KEYS:
            errors.append("version.yaml migration keys must match the layout contract")
        status = migration.get("status")
        if status not in {"migrated", "not_applicable"}:
            errors.append("version.yaml migration.status must be migrated or not_applicable")
        transaction_id = migration.get("transaction_id")
        if status == "migrated":
            if (
                not isinstance(transaction_id, str)
                or LAYOUT_TRANSACTION_RE.fullmatch(transaction_id) is None
            ):
                errors.append("version.yaml migrated transaction_id is invalid")
        elif transaction_id != "not-applicable":
            errors.append("version.yaml not_applicable transaction_id must be not-applicable")
        for field in ("legacy_manifest_sha256", "new_layout_baseline_sha256"):
            value = migration.get(field)
            if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                errors.append(f"version.yaml migration.{field} must be a SHA256 digest")
        evidence = migration.get("completion_evidence")
        if not isinstance(evidence, dict):
            errors.append("version.yaml migration.completion_evidence must be a mapping")
        else:
            if set(evidence) != {"kind", "path", "sha256", "completed_at"}:
                errors.append("version.yaml completion evidence keys must match the contract")
            if not isinstance(evidence.get("completed_at"), str) or not evidence.get(
                "completed_at"
            ):
                errors.append("version.yaml completion evidence requires completed_at")
            evidence_sha256 = evidence.get("sha256")
            if not isinstance(evidence_sha256, str) or SHA256_RE.fullmatch(evidence_sha256) is None:
                errors.append("version.yaml completion evidence requires sha256")
            evidence_kind = evidence.get("kind")
            evidence_path = evidence.get("path")
            if status == "migrated":
                expected_path = plan_relative_path(".migrations", f"{transaction_id}.yaml")
                if evidence_kind != "migration-proof" or evidence_path != expected_path:
                    errors.append(
                        "version.yaml migrated completion evidence must name the transaction proof"
                    )
                proof_path = root / expected_path
                if (
                    proof_path.is_symlink()
                    or not proof_path.is_file()
                    or (
                        isinstance(evidence_sha256, str)
                        and sha256_file(proof_path) != evidence_sha256
                    )
                ):
                    errors.append("version.yaml migration proof is missing or drifted")
                else:
                    try:
                        proof = load_yaml_file(proof_path)
                    except (WorkctlError, yaml.YAMLError) as exc:
                        errors.append(f"version.yaml migration proof is invalid: {exc}")
                    else:
                        if set(proof) not in (
                            LAYOUT_PROOF_KEYS,
                            LAYOUT_PROPOSAL_PROOF_KEYS,
                        ):
                            errors.append(
                                "version.yaml migration proof keys must match the contract"
                            )
                        if (
                            proof.get("schema_version") != 1
                            or proof.get("kind") != "layout-migration-proof"
                            or proof.get("transaction_id") != transaction_id
                            or proof.get("status") != "prepared"
                            or proof.get("legacy_manifest_sha256")
                            != migration.get("legacy_manifest_sha256")
                            or not isinstance(proof.get("legacy_adoption_sha256"), str)
                            or SHA256_RE.fullmatch(str(proof.get("legacy_adoption_sha256"))) is None
                            or not isinstance(proof.get("conversion_table_sha256"), str)
                            or SHA256_RE.fullmatch(str(proof.get("conversion_table_sha256")))
                            is None
                            or not isinstance(proof.get("created_at"), str)
                            or not proof.get("created_at")
                        ):
                            errors.append(
                                "version.yaml migration proof fields do not match the commitment"
                            )
                        if set(proof) == LAYOUT_PROPOSAL_PROOF_KEYS and (
                            SHA256_RE.fullmatch(str(proof.get("legacy_proposals_sha256"))) is None
                            or SHA256_RE.fullmatch(str(proof.get("new_proposals_baseline_sha256")))
                            is None
                        ):
                            errors.append(
                                "version.yaml migration proposal proof fields are invalid"
                            )
            elif evidence_kind != "not-applicable-receipt" or evidence_path != "not-applicable":
                errors.append("version.yaml not_applicable completion evidence is invalid")
    ignore = governance_ignore_path(root)
    if not ignore.is_file():
        errors.append(f"missing {GOVERNANCE_DIR_NAME}/.gitignore")
    elif ignore.read_text(encoding="utf-8") != LAYOUT_GITIGNORE:
        errors.append(f"{GOVERNANCE_DIR_NAME}/.gitignore does not match the exact contract")
    return errors


def layout_journal_paths(root: Path, *, include_committed: bool = False) -> list[Path]:
    """Return layout transaction journals in deterministic transaction order."""
    base = runtime_dir(root)
    if base.is_symlink():
        raise WorkctlError(f"LAYOUT_PATH_SYMLINK: {base}")
    if not base.is_dir():
        return []
    journals: list[Path] = []
    for transaction_dir in sorted(base.glob("LAY-*")):
        if transaction_dir.is_symlink():
            raise WorkctlError(f"LAYOUT_PATH_SYMLINK: {transaction_dir}")
        journal = transaction_dir / "journal.json"
        if not journal.is_file():
            journals.append(journal)
            continue
        if include_committed:
            journals.append(journal)
            continue
        try:
            payload = json.loads(journal.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            journals.append(journal)
            continue
        if not isinstance(payload, dict) or payload.get("status") not in {"committed", "aborted"}:
            journals.append(journal)
            continue
        try:
            loaded = load_layout_journal(journal)
            if loaded.get("status") == "aborted":
                if loaded.get("kind") == "layout-action-upgrade":
                    validate_aborted_action_upgrade_journal(root, journal, loaded)
                else:
                    validate_aborted_layout_journal(root, journal, loaded)
        except WorkctlError:
            journals.append(journal)
    return journals


def legacy_layout_feature_names(path: Path) -> set[str]:
    """Return exact direct-child names that identify the old controller layout."""
    if not path.is_dir() or path.is_symlink():
        return set()
    features: set[str] = set()
    for child in path.iterdir():
        if child.name in LEGACY_LAYOUT_FEATURE_NAMES or re.fullmatch(
            r"PLAN-\d{8}-\d{3}\.md", child.name
        ):
            features.add(child.name)
    return features


def safe_proposal_child_name(value: object, *, suffix: str) -> str | None:
    """Return one traversal-free proposal-local file name with the required suffix."""
    if not isinstance(value, str):
        return None
    candidate = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or candidate.name != value
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or not value.endswith(suffix)
    ):
        return None
    return value


def legacy_prepared_plan_errors(
    prepared_doc: PlanDocument,
    migration_id: str,
    sources: list[dict[str, Any]],
) -> list[str]:
    """Validate a prepared Plan in its pre-reconciliation state.

    Reconciliation proposals legitimately omit ``authority`` until their exact
    confirmations and source archives are applied. Project the deterministic
    authority fields on a copy and reuse the canonical Plan validator without
    mutating or accepting the pending proposal.
    """
    projected = copy.deepcopy(prepared_doc.frontmatter)
    try:
        upgrade_reconciled_plan_to_schema3(projected, migration_id)
    except WorkctlError as exc:
        return [str(exc)]
    projected["authority"] = {
        "model": AUTHORITY_MODEL,
        "state": AUTHORITY_STATE,
        "canonical_plan_id": projected.get("plan_id"),
        "migration_id": migration_id,
        "sources": sources,
        "confirmations": {},
    }
    errors = validate_frontmatter(projected, reject_blocking_artifacts=False)
    if not prepared_doc.body.strip():
        errors.append("Plan body must not be empty")
    return errors


def legacy_proposal_errors(legacy_plan: Path) -> list[str]:
    """Validate the closed legacy reconciliation-proposal side tree.

    Proposal ownership is proven structurally, not from the directory name.
    External source hashes are retained as proposal bytes but are not re-certified
    by layout migration, and any already-bound confirmation remains fail-closed.
    """
    proposals = legacy_plan / "proposals"
    if not proposals.exists() and not proposals.is_symlink():
        return []
    if proposals.is_symlink() or not proposals.is_dir():
        return ["legacy proposals path must be a non-symlinked ordinary directory"]
    try:
        tree_manifest(proposals)
    except WorkctlError as exc:
        return [f"legacy proposals tree is not closed: {exc}"]

    errors: list[str] = []
    for proposal in sorted(proposals.iterdir(), key=lambda item: item.name):
        if (
            proposal.is_symlink()
            or not proposal.is_dir()
            or MIGRATION_ID_RE.fullmatch(proposal.name) is None
        ):
            errors.append(f"legacy proposals has an unsupported entry: {proposal.name}")
            continue
        manifest_path = proposal / "reconciliation.yaml"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            errors.append(f"legacy proposal {proposal.name} lacks reconciliation.yaml")
            continue
        try:
            manifest = load_yaml_file(manifest_path)
        except (WorkctlError, yaml.YAMLError):
            errors.append(f"legacy proposal {proposal.name} manifest is invalid")
            continue
        required_keys = {"migration_id", "target_plan", "sources", "confirmations"}
        allowed_keys = {*required_keys, "schema_version", "git_baseline", "agents_rewrite"}
        if not required_keys.issubset(manifest) or not set(manifest).issubset(allowed_keys):
            errors.append(f"legacy proposal {proposal.name} manifest keys are unsupported")
            continue
        if manifest.get("schema_version") not in {None, 1}:
            errors.append(f"legacy proposal {proposal.name} schema is unsupported")
        if manifest.get("migration_id") != proposal.name:
            errors.append(f"legacy proposal {proposal.name} migration_id does not match")

        target_value = manifest.get("target_plan")
        prepared_name: str | None = None
        prepared_doc: PlanDocument | None = None
        if not isinstance(target_value, dict) or set(target_value) != {"prepared_file"}:
            errors.append(f"legacy proposal {proposal.name} target_plan is unsupported")
        else:
            prepared_name = safe_proposal_child_name(
                target_value.get("prepared_file"),
                suffix=".prepared.md",
            )
            if prepared_name is None:
                errors.append(f"legacy proposal {proposal.name} prepared file is invalid")
        if prepared_name is not None:
            prepared_path = proposal / prepared_name
            if prepared_path.is_symlink() or not prepared_path.is_file():
                errors.append(f"legacy proposal {proposal.name} prepared Plan is missing")
            else:
                try:
                    prepared_doc = load_plan(prepared_path)
                except WorkctlError:
                    errors.append(f"legacy proposal {proposal.name} prepared Plan is invalid")

        sources = manifest.get("sources")
        validated_sources: list[dict[str, Any]] = []
        if not isinstance(sources, list) or not sources:
            errors.append(f"legacy proposal {proposal.name} sources must be a non-empty list")
        else:
            seen_sources: set[str] = set()
            for number, source in enumerate(sources):
                source_label = f"legacy proposal {proposal.name} source[{number}]"
                if not isinstance(source, dict):
                    errors.append(f"{source_label} must be a mapping")
                    continue
                required_source_keys = {"path", "role", "sha256", "classification"}
                allowed_source_keys = {*required_source_keys, "revision"}
                if not required_source_keys.issubset(source) or not set(source).issubset(
                    allowed_source_keys
                ):
                    errors.append(f"{source_label} keys are unsupported")
                    continue
                source_path = source.get("path")
                if (
                    not isinstance(source_path, str)
                    or not source_path
                    or Path(source_path).is_absolute()
                    or any(part in {"", ".", ".."} for part in Path(source_path).parts)
                    or source_path in seen_sources
                ):
                    errors.append(f"{source_label} path is invalid")
                else:
                    seen_sources.add(source_path)
                if source.get("role") not in SOURCE_ROLES:
                    errors.append(f"{source_label} role is unsupported")
                if source.get("classification") != "CONFIRMED_AUTHORITY":
                    errors.append(f"{source_label} classification is unsupported")
                if SHA256_RE.fullmatch(str(source.get("sha256"))) is None:
                    errors.append(f"{source_label} sha256 is invalid")
                revision = source.get("revision")
                if revision is not None and (type(revision) is not int or revision < 1):
                    errors.append(f"{source_label} revision is invalid")
                if not any(error.startswith(source_label) for error in errors):
                    assert isinstance(source_path, str)
                    normalized_source: dict[str, Any] = {
                        "path": source_path,
                        "role": source["role"],
                        "sha256": source["sha256"],
                        "archive_path": archive_path_for_source(proposal.name, source_path),
                        "classification": source["classification"],
                    }
                    if revision is not None:
                        normalized_source["revision"] = revision
                    validated_sources.append(normalized_source)

        if prepared_doc is not None:
            prepared_errors = legacy_prepared_plan_errors(
                prepared_doc,
                proposal.name,
                validated_sources,
            )
            if prepared_doc.frontmatter.get("status") != "active" or prepared_errors:
                errors.append(
                    f"legacy proposal {proposal.name} prepared Plan contract is unsupported"
                )

        git_baseline = manifest.get("git_baseline")
        if git_baseline is not None and (
            not isinstance(git_baseline, str)
            or re.fullmatch(r"[0-9a-f]{40,64}", git_baseline) is None
        ):
            errors.append(f"legacy proposal {proposal.name} git_baseline is invalid")
        confirmations_value = manifest.get("confirmations")
        if not isinstance(confirmations_value, dict) or confirmations_value:
            errors.append(
                f"legacy proposal {proposal.name} has confirmations requiring reclassification"
            )

        expected_children = {"reconciliation.yaml"}
        if prepared_name is not None:
            expected_children.add(prepared_name)
        agents_value = manifest.get("agents_rewrite")
        if agents_value is not None:
            replacement_name: str | None = None
            if not isinstance(agents_value, dict) or set(agents_value) != {
                "path",
                "sha256",
                "replacement_file",
            }:
                errors.append(f"legacy proposal {proposal.name} agents_rewrite is unsupported")
            else:
                replacement_name = safe_proposal_child_name(
                    agents_value.get("replacement_file"),
                    suffix=".proposed.md",
                )
                if (
                    agents_value.get("path") != "AGENTS.md"
                    or SHA256_RE.fullmatch(str(agents_value.get("sha256"))) is None
                    or replacement_name is None
                ):
                    errors.append(f"legacy proposal {proposal.name} agents_rewrite is invalid")
            if replacement_name is not None:
                replacement_path = proposal / replacement_name
                expected_children.add(replacement_name)
                if replacement_path.is_symlink() or not replacement_path.is_file():
                    errors.append(f"legacy proposal {proposal.name} AGENTS replacement is missing")

        actual_children = {child.name for child in proposal.iterdir()}
        if actual_children != expected_children:
            errors.append(f"legacy proposal {proposal.name} inventory is not closed")
    return errors


def legacy_journal_errors(path: Path) -> list[str]:
    """Validate that every old migration and rollover journal is committed."""
    errors: list[str] = []
    for directory_name in (".migrations", ".rollovers"):
        directory = path / directory_name
        if directory.is_symlink():
            errors.append(f"legacy journal directory is a symlink: {directory_name}")
            continue
        if not directory.exists():
            continue
        if not directory.is_dir():
            errors.append(f"legacy journal path is not a directory: {directory_name}")
            continue
        for journal in sorted(directory.glob("*.yaml")):
            if journal.is_symlink():
                errors.append(f"legacy journal is a symlink: {journal.name}")
                continue
            try:
                payload = load_yaml_file(journal)
            except (WorkctlError, yaml.YAMLError):
                errors.append(f"legacy journal is invalid: {journal.name}")
                continue
            if payload.get("status") != "committed":
                errors.append(f"legacy journal is incomplete: {journal.name}")
    return errors


def legacy_pointer_errors(path: Path, indexed_plan_ids: set[str]) -> list[str]:
    """Validate generated pointer targets while leaving pointer bytes unchanged."""
    errors: list[str] = []
    target_pattern = re.compile(r"Canonical Plan:\s*\[[^\]]+\]\(([^)]+)\)")
    for pointer in sorted(path.glob("PLAN-*.md")):
        if not pointer.is_file() or pointer.is_symlink():
            continue
        text = pointer.read_text(encoding="utf-8", errors="replace")
        if POINTER_MARKER not in text:
            continue
        match = target_pattern.search(text)
        if match is None:
            errors.append(f"generated pointer has no canonical target: {pointer.name}")
            continue
        raw_target = match.group(1)
        target = (pointer.parent / raw_target).resolve()
        try:
            target.relative_to(path.resolve())
        except ValueError:
            errors.append(f"generated pointer escapes legacy root: {pointer.name}")
            continue
        plan_id = target.stem
        if not target.is_file() or plan_id not in indexed_plan_ids:
            errors.append(f"generated pointer target is not registered: {pointer.name}")
    return errors


def legacy_project_rule_errors(root: Path, active_name: str) -> list[str]:
    """Reject explicit legacy authority routing that does not name the active Plan."""
    errors: list[str] = []
    authority_pattern = re.compile(
        r"\b(authoritative|current|must\s+(?:read|update)|single\s+active)\b"
        r"|执行权威|当前.*计划|必须(?:读取|更新)|唯一.*计划",
        re.IGNORECASE,
    )
    plan_pattern = re.compile(r"_Plan/(PLAN-\d{8}-\d{3}\.md)")
    for rules_name in ("AGENTS.md", "CLAUDE.md"):
        rules = root / rules_name
        if rules.is_symlink():
            errors.append(f"{rules_name} is a symlink")
            continue
        if not rules.is_file():
            continue
        text = rules.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if authority_pattern.search(line) is None:
                continue
            for match in plan_pattern.finditer(line):
                if match.group(1) != active_name:
                    errors.append(
                        f"{rules_name}:{line_number} routes legacy authority to "
                        f"{match.group(1)} instead of {active_name}"
                    )
    return errors


def git_worktree_identity(root: Path) -> dict[str, object]:
    """Return a stable identity that distinguishes linked Git worktrees."""
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return {"repository": False, "project_root": root.resolve().as_posix()}
    commands = {
        "project_root": ["git", "rev-parse", "--show-toplevel"],
        "git_dir": ["git", "rev-parse", "--absolute-git-dir"],
        "git_common_dir": [
            "git",
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
    }
    values: dict[str, str] = {}
    for field, command in commands.items():
        result = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise WorkctlError("LEGACY_ADOPTION_GIT_IDENTITY_UNAVAILABLE")
        values[field] = Path(result.stdout.strip()).resolve().as_posix()
    if values["project_root"] != root.resolve().as_posix():
        raise WorkctlError("LEGACY_ADOPTION_PROJECT_ROOT_MISMATCH")
    return {"repository": True, **values}


def legacy_adoption_errors(
    root: Path,
    active_plan_id: str,
    active_name: str,
    legacy_manifest_sha256: str,
) -> list[str]:
    """Validate the explicit worktree-local receipt for one legacy snapshot."""
    receipt_path = legacy_adoption_path(root)
    if receipt_path.is_symlink() or not receipt_path.is_file():
        return ["legacy authority lacks an explicit worktree adoption receipt"]
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["legacy adoption receipt is invalid"]
    if not isinstance(payload, dict) or set(payload) != LEGACY_ADOPTION_KEYS:
        return ["legacy adoption receipt contract is invalid"]
    try:
        identity = git_worktree_identity(root)
    except WorkctlError as exc:
        return [str(exc)]
    expected = {
        "schema_version": 1,
        "kind": "work-governance-legacy-adoption",
        "project_root": root.resolve().as_posix(),
        "worktree_identity": identity,
        "active_plan_id": active_plan_id,
        "active_plan_path": active_name,
        "legacy_manifest_sha256": legacy_manifest_sha256,
    }
    if (
        any(payload.get(field) != value for field, value in expected.items())
        or payload.get("action_revision") not in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS
        or SHA256_RE.fullmatch(str(payload.get("controller_sha256"))) is None
    ):
        return ["legacy adoption receipt does not match this worktree and legacy snapshot"]
    if (
        not valid_reference(payload.get("confirmation_ref"))
        or not isinstance(payload.get("created_at"), str)
        or not payload.get("created_at")
    ):
        return ["legacy adoption receipt authority fields are invalid"]
    return []


def classify_legacy_layout(
    root: Path,
    *,
    require_adoption: bool = True,
) -> LegacyLayoutReport:
    """Classify the project-root ``_Plan`` using a strict conjunction."""
    path = legacy_plan_dir(root)
    if not path.exists() and not path.is_symlink():
        return LegacyLayoutReport("NOT_APPLICABLE", [], None, None, None)
    if path.is_symlink() or not path.is_dir():
        return LegacyLayoutReport(
            "AMBIGUOUS",
            ["legacy _Plan must be a non-symlinked ordinary directory"],
            None,
            None,
            None,
        )
    features = legacy_layout_feature_names(path)
    if not features:
        return LegacyLayoutReport("NOT_APPLICABLE", [], None, None, None)
    blockers: list[str] = []
    legacy_lock = path / ".workctl.lock"
    if legacy_lock.is_symlink() or (legacy_lock.exists() and not legacy_lock.is_file()):
        blockers.append("legacy .workctl.lock must be regular or absent")
    try:
        manifest = tree_manifest(path, exclude_names={".workctl.lock"})
        digest = manifest_sha256(manifest)
    except WorkctlError as exc:
        return LegacyLayoutReport("AMBIGUOUS", [str(exc)], None, None, None)
    allowed_names = set(LEGACY_LAYOUT_DIRECT_NAMES)
    allowed_names.update(
        child.name for child in path.iterdir() if re.fullmatch(r"PLAN-\d{8}-\d{3}\.md", child.name)
    )
    unexpected = sorted(child.name for child in path.iterdir() if child.name not in allowed_names)
    if unexpected:
        blockers.append("legacy _Plan has unregistered direct children: " + ", ".join(unexpected))
    blockers.extend(legacy_proposal_errors(path))
    index = path / "index.yaml"
    if not index.is_file() or index.is_symlink():
        blockers.append("legacy _Plan has features but no regular index.yaml")
        return LegacyLayoutReport("AMBIGUOUS", blockers, None, None, digest)
    try:
        index_payload = load_yaml_file(index)
    except (WorkctlError, yaml.YAMLError) as exc:
        blockers.append(str(exc))
        return LegacyLayoutReport("AMBIGUOUS", blockers, None, None, digest)
    active_plan_id = index_payload.get("active_plan_id")
    if (
        index_payload.get("schema_version") != 1
        or not isinstance(active_plan_id, str)
        or PLAN_ID_RE.fullmatch(active_plan_id) is None
    ):
        blockers.append("legacy index schema or active_plan_id is unsupported")
        return LegacyLayoutReport("AMBIGUOUS", blockers, None, None, digest)
    plans = index_payload.get("plans")
    if not isinstance(plans, list):
        blockers.append("legacy index plans must be a list")
        return LegacyLayoutReport("AMBIGUOUS", blockers, active_plan_id, None, digest)
    active_items = [
        item for item in plans if isinstance(item, dict) and item.get("id") == active_plan_id
    ]
    if len(active_items) != 1:
        blockers.append("legacy index must identify exactly one active Plan entry")
        return LegacyLayoutReport("AMBIGUOUS", blockers, active_plan_id, None, digest)
    active_name = active_items[0].get("path")
    if (
        not isinstance(active_name, str)
        or Path(active_name).name != active_name
        or not re.fullmatch(r"PLAN-\d{8}-\d{3}\.md", active_name)
    ):
        blockers.append("legacy active Plan must be a direct PLAN-*.md child")
        return LegacyLayoutReport("AMBIGUOUS", blockers, active_plan_id, None, digest)
    active_path = path / active_name
    if active_path.is_symlink() or not active_path.is_file():
        blockers.append("legacy active Plan is missing or not regular")
        return LegacyLayoutReport("AMBIGUOUS", blockers, active_plan_id, active_name, digest)
    try:
        active_doc = load_plan(active_path)
    except (WorkctlError, yaml.YAMLError) as exc:
        blockers.append(str(exc))
        return LegacyLayoutReport("AMBIGUOUS", blockers, active_plan_id, active_name, digest)
    if active_doc.frontmatter.get("plan_id") != active_plan_id:
        blockers.append("legacy index and active Plan IDs differ")
    schema = active_doc.frontmatter.get("schema_version")
    if schema not in {1, 2, 3}:
        blockers.append("legacy active Plan schema is unsupported")
    authority = active_doc.frontmatter.get("authority")
    if schema in {2, 3} and (
        not isinstance(authority, dict)
        or authority.get("model") != AUTHORITY_MODEL
        or authority.get("state") != AUTHORITY_STATE
        or authority.get("canonical_plan_id") != active_plan_id
    ):
        blockers.append("legacy active Plan authority model is unsupported")
    if schema in {1, 2, 3}:
        blockers.extend(
            f"legacy active Plan validation failed: {error}"
            for error in validate_frontmatter(
                active_doc.frontmatter,
                reject_blocking_artifacts=True,
            )
        )
    indexed_ids = {
        str(item["id"])
        for item in plans
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    indexed_names: set[str] = set()
    seen_ids: set[str] = set()
    for item in plans:
        if not isinstance(item, dict):
            blockers.append("legacy index Plan entries must be mappings")
            continue
        item_id = item.get("id")
        item_name = item.get("path")
        if (
            not isinstance(item_id, str)
            or PLAN_ID_RE.fullmatch(item_id) is None
            or item_id in seen_ids
        ):
            blockers.append("legacy index Plan IDs must be unique and valid")
            continue
        seen_ids.add(item_id)
        if (
            not isinstance(item_name, str)
            or Path(item_name).name != item_name
            or not re.fullmatch(r"PLAN-\d{8}-\d{3}\.md", item_name)
            or item_name in indexed_names
        ):
            blockers.append("legacy index Plan paths must be unique direct children")
            continue
        indexed_names.add(item_name)
        item_path = path / item_name
        if item_path.is_symlink() or not item_path.is_file():
            blockers.append(f"legacy indexed Plan is missing or not regular: {item_name}")
            continue
        text = item_path.read_text(encoding="utf-8", errors="replace")
        if POINTER_MARKER in text:
            if item_id == active_plan_id:
                blockers.append("legacy active Plan cannot be a pointer")
            continue
        try:
            item_doc = load_plan(item_path)
        except (WorkctlError, yaml.YAMLError):
            blockers.append(f"legacy indexed Plan is invalid: {item_name}")
            continue
        item_schema = item_doc.frontmatter.get("schema_version")
        if item_doc.frontmatter.get("plan_id") != item_id or item_schema not in {1, 2, 3}:
            blockers.append(f"legacy indexed Plan contract is unsupported: {item_name}")
            continue
        item_authority = item_doc.frontmatter.get("authority")
        if item_schema in {2, 3} and (
            not isinstance(item_authority, dict)
            or item_authority.get("model") != AUTHORITY_MODEL
            or item_authority.get("state") != AUTHORITY_STATE
            or item_authority.get("canonical_plan_id") != item_id
        ):
            blockers.append(f"legacy indexed Plan authority is unsupported: {item_name}")
        if item_id != active_plan_id and item_doc.frontmatter.get("status") != "complete":
            blockers.append(f"legacy non-active indexed Plan is not complete: {item_name}")
    for candidate in sorted(path.glob("PLAN-*.md")):
        if candidate.name in indexed_names or candidate.is_symlink():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if POINTER_MARKER in text:
            continue
        try:
            historical = load_plan(candidate)
        except (WorkctlError, yaml.YAMLError):
            blockers.append(
                f"legacy unregistered Plan-like file is not historical: {candidate.name}"
            )
            continue
        if (
            historical.frontmatter.get("plan_id") != candidate.stem
            or historical.frontmatter.get("schema_version") not in {1, 2, 3}
            or historical.frontmatter.get("status") != "complete"
        ):
            blockers.append(
                f"legacy unregistered Plan-like file is not historical: {candidate.name}"
            )
    blockers.extend(legacy_pointer_errors(path, indexed_ids))
    try:
        blockers.extend(legacy_project_rule_errors(root, active_name))
        if require_adoption:
            blockers.extend(
                legacy_adoption_errors(
                    root,
                    active_plan_id,
                    active_name,
                    digest,
                )
            )
    except WorkctlError as exc:
        blockers.append(str(exc))
    journal_errors = legacy_journal_errors(path)
    if journal_errors:
        return LegacyLayoutReport(
            "RECOVERY_REQUIRED",
            [*blockers, *journal_errors],
            active_plan_id,
            active_name,
            digest,
        )
    if blockers:
        return LegacyLayoutReport("AMBIGUOUS", blockers, active_plan_id, active_name, digest)
    return LegacyLayoutReport("MIGRATABLE", [], active_plan_id, active_name, digest)


def inspect_layout(root: Path) -> LayoutReport:
    """Return the independent, fail-closed project layout state."""
    blocked = layout_control_path_errors(root)
    if blocked:
        legacy = classify_legacy_layout(root)
        return LayoutReport("ENVIRONMENT_BLOCKED", blocked, legacy, LAYOUT_ALLOWED_COMMANDS)
    try:
        journals = layout_journal_paths(root)
    except WorkctlError as exc:
        legacy = classify_legacy_layout(root)
        return LayoutReport("ENVIRONMENT_BLOCKED", [str(exc)], legacy, LAYOUT_ALLOWED_COMMANDS)
    legacy = classify_legacy_layout(root)
    if journals:
        return LayoutReport(
            "LAYOUT_RECOVERY_REQUIRED",
            [
                f"incomplete layout journal: {relative_project_path(root, path)}"
                for path in journals
            ],
            legacy,
            LAYOUT_ALLOWED_COMMANDS,
        )
    version_exists = version_path(root).is_file()
    if version_exists:
        errors = layout_version_errors(root)
        if errors:
            return LayoutReport("ENVIRONMENT_BLOCKED", errors, legacy, LAYOUT_ALLOWED_COMMANDS)
        if legacy.classification not in {"NOT_APPLICABLE"}:
            return LayoutReport(
                "LEGACY_ROOT_REAPPEARED",
                ["legacy work-governance features reappeared after layout commitment"],
                legacy,
                LAYOUT_ALLOWED_COMMANDS,
            )
        version = load_yaml_file(version_path(root))
        action_revision = version.get("legacy_migration_action_revision")
        if action_revision != LEGACY_MIGRATION_ACTION_REVISION:
            return LayoutReport(
                "LAYOUT_MIGRATION_REQUIRED",
                [
                    "committed layout action revision "
                    f"{action_revision} requires upgrade to "
                    f"{LEGACY_MIGRATION_ACTION_REVISION}"
                ],
                legacy,
                LAYOUT_ALLOWED_COMMANDS,
            )
        return LayoutReport("LAYOUT_READY", [], legacy, LAYOUT_ALLOWED_COMMANDS)
    if plan_dir(root).exists() and legacy.classification != "NOT_APPLICABLE":
        return LayoutReport(
            "RECONCILIATION_REQUIRED",
            ["legacy and new Plan roots coexist before version commitment"],
            legacy,
            LAYOUT_ALLOWED_COMMANDS,
        )
    if plan_dir(root).exists():
        return LayoutReport(
            "ENVIRONMENT_BLOCKED",
            ["new Plan root exists without committed version.yaml"],
            legacy,
            LAYOUT_ALLOWED_COMMANDS,
        )
    if legacy.classification == "RECOVERY_REQUIRED":
        return LayoutReport(
            "LAYOUT_RECOVERY_REQUIRED", legacy.blockers, legacy, LAYOUT_ALLOWED_COMMANDS
        )
    if legacy.classification == "AMBIGUOUS":
        return LayoutReport(
            "LEGACY_CLASSIFICATION_REQUIRED", legacy.blockers, legacy, LAYOUT_ALLOWED_COMMANDS
        )
    return LayoutReport(
        "LAYOUT_MIGRATION_REQUIRED",
        [],
        legacy,
        LAYOUT_ALLOWED_COMMANDS,
    )


def layout_control_path_errors(root: Path) -> list[str]:
    """Validate the closed top-level layout inventory and control path types."""
    governance = governance_root(root)
    if governance.is_symlink():
        return [f"control path is a symlink: {GOVERNANCE_DIR_NAME}"]
    if governance.exists() and not governance.is_dir():
        return [f"control path is not a directory: {GOVERNANCE_DIR_NAME}"]
    if not governance.is_dir():
        return []
    directory_paths = (
        plan_dir(root),
        logs_dir(root),
        worktrees_dir(root),
        cache_dir(root),
        uv_cache_dir(root),
        proposals_dir(root),
        evidence_dir(root),
        runtime_dir(root),
    )
    file_paths = (
        version_path(root),
        governance_ignore_path(root),
        bootstrap_state_path(root),
        workctl_lock_path(root),
    )
    errors: list[str] = []
    if not version_path(root).is_file():
        errors.extend(governance_claim_errors(root))
        if not errors:
            errors.extend(uncommitted_governance_footprint_errors(root))
    for path in directory_paths:
        if path.is_symlink():
            errors.append(f"control path is a symlink: {path.relative_to(root).as_posix()}")
        elif path.exists() and not path.is_dir():
            errors.append(f"control path is not a directory: {path.relative_to(root).as_posix()}")
    for path in file_paths:
        if path.is_symlink():
            errors.append(f"control path is a symlink: {path.relative_to(root).as_posix()}")
        elif path.exists() and not path.is_file():
            errors.append(f"control path is not a file: {path.relative_to(root).as_posix()}")
    allowed = {
        PLAN_DIR_NAME,
        "logs",
        "worktrees",
        "cache",
        "proposals",
        "evidence",
        "runtime",
        "version.yaml",
        ".gitignore",
        "bootstrap-state.json",
        "workctl.lock",
    }
    unexpected = sorted(child.name for child in governance.iterdir() if child.name not in allowed)
    if unexpected:
        errors.append("governance root has unregistered direct children: " + ", ".join(unexpected))
    ignore = governance_ignore_path(root)
    if (
        not version_path(root).is_file()
        and ignore.is_file()
        and ignore.read_text(encoding="utf-8") != LAYOUT_GITIGNORE
    ):
        errors.append("uncommitted governance root has a non-canonical .gitignore")
    return errors


def require_layout_ready(root: Path) -> None:
    """Block ordinary controller operations until layout commitment is valid."""
    report = inspect_layout(root)
    if report.state != "LAYOUT_READY":
        details = "; ".join(report.blockers)
        suffix = f": {details}" if details else ""
        raise WorkctlError(f"LAYOUT_BLOCKED: {report.state}{suffix}")


def optional_plan_metadata(path: Path) -> tuple[str | None, int | None, str | None]:
    """Read identifying Plan metadata without turning discovery into validation."""
    try:
        doc = load_plan(path)
    except (OSError, WorkctlError, yaml.YAMLError):
        return None, None, None
    plan_id = doc.frontmatter.get("plan_id")
    revision = doc.frontmatter.get("revision")
    status = doc.frontmatter.get("status")
    return (
        plan_id if isinstance(plan_id, str) else None,
        revision if type(revision) is int else None,
        status if isinstance(status, str) else None,
    )


def candidate_signals(path: Path, *, active: bool, rules_confirmed: bool) -> list[str]:
    """Collect open-text signals used only for candidate classification."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    signals: list[str] = []
    if active:
        signals.append("index-active")
    if rules_confirmed:
        signals.append("project-rule-explicit")
    if POINTER_MARKER in text:
        signals.append("migration-pointer")
    if re.search(
        r"\b(authoritative|single active|only active|current execution plan)\b"
        r"|执行权威|唯一(?:活跃|执行).*计划|当前执行计划",
        lowered,
    ):
        signals.append("self-claims-authority")
    control_patterns = {
        "controls-goal": r"\b(target|goal|objective)\b|目标",
        "controls-phases": r"\b(phase|milestone)\b|阶段",
        "controls-queue": r"\b(queue|task|next step)\b|队列|任务|下一步",
        "controls-gates": r"\b(confirmation|gate|stop condition)\b|确认门|停止条件",
    }
    for signal, pattern in control_patterns.items():
        if re.search(pattern, lowered):
            signals.append(signal)
    if re.search(
        r"\b(archive|evidence|log|technical design|phase design)\b|归档|证据|日志|技术方案", lowered
    ):
        signals.append("non-authority-document")
    return signals


def project_rule_references(root: Path) -> dict[str, list[str]]:
    """Find Plan paths explicitly designated by project governance files."""
    references: dict[str, list[str]] = {}
    path_pattern = re.compile(
        r"(?<![A-Za-z0-9._/-])"
        r"(?:\.work-governance/_Plan/[A-Za-z0-9._/-]+\.md"
        r"|docs/[A-Za-z0-9._/-]*[Pp]lan\.md|[Pp]lan\.md)"
        r"(?![A-Za-z0-9._/-])"
    )
    authority_pattern = re.compile(
        r"\b(authoritative|current|must\s+(?:read|update)|single\s+active)\b"
        r"|执行权威|当前.*计划|必须(?:读取|更新)|唯一.*计划",
        re.IGNORECASE,
    )
    for rules_name in ("AGENTS.md", "CLAUDE.md"):
        rules_path = root / rules_name
        if not rules_path.is_file():
            continue
        for line_number, line in enumerate(
            rules_path.read_text(encoding="utf-8", errors="replace").splitlines(),
            start=1,
        ):
            if authority_pattern.search(line) is None:
                continue
            for match in path_pattern.finditer(line):
                raw_path = match.group(0)
                references.setdefault(raw_path, []).append(f"{rules_name}:{line_number}")
    return references


def classify_candidate(
    path: Path,
    *,
    active: bool,
    rules_confirmed: bool,
    explicit_classification: str | None,
) -> tuple[str, list[str]]:
    """Classify a candidate without treating filenames as authority proof."""
    signals = candidate_signals(path, active=active, rules_confirmed=rules_confirmed)
    if explicit_classification is not None:
        signals.append("agent-classification")
        return explicit_classification, signals
    if active or rules_confirmed:
        return "CONFIRMED_AUTHORITY", signals
    if "migration-pointer" in signals:
        return "NON_AUTHORITY", signals
    _, _, status = optional_plan_metadata(path)
    if status in {"complete", "retired"}:
        signals.append("completed-plan" if status == "complete" else "retired-plan")
        return "NON_AUTHORITY", signals
    control_signal_count = sum(signal.startswith("controls-") for signal in signals)
    if "self-claims-authority" in signals and control_signal_count >= 2:
        return "LIKELY_AUTHORITY", signals
    return "NON_AUTHORITY", signals


def discover_authority_candidates(
    root: Path,
    explicit_candidates: dict[str, str] | None = None,
) -> list[AuthorityCandidate]:
    """Discover active, rule-designated, conventional, and lineage Plan candidates."""
    explicit_by_identity: dict[tuple[int, int], str] = {}
    explicit_paths: list[Path] = []
    for raw_path, classification in (explicit_candidates or {}).items():
        path = checked_project_path(root, raw_path)
        reject_legacy_plan_authority_path(root, raw_path, path)
        if not path.is_file():
            raise WorkctlError(f"MISSING_CANDIDATE: {raw_path}")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        existing = explicit_by_identity.get(identity)
        if existing is not None and existing != classification:
            raise WorkctlError(
                f"CONFLICTING_CANDIDATE_CLASSIFICATION: {relative_project_path(root, path)}"
            )
        explicit_by_identity[identity] = classification
        explicit_paths.append(path)
    rules = project_rule_references(root)
    active_path: Path | None = None
    if index_path(root).is_file():
        try:
            active_path = active_plan_path(root).resolve()
        except WorkctlError:
            active_path = None

    candidate_origins: dict[Path, set[str]] = {}

    def add_candidate(path: Path, origins: list[str] | set[str] | tuple[str, ...]) -> None:
        """Add one physical file once even on case-insensitive filesystems."""
        if not path.is_file():
            return
        raw_path = relative_project_path(root, path)
        if is_legacy_plan_authority_path(root, raw_path, path):
            return
        for existing_path in candidate_origins:
            if os.path.samefile(existing_path, path):
                candidate_origins[existing_path].update(origins)
                return
        candidate_origins[path] = set(origins)

    for raw_path, rule_origins in rules.items():
        path = checked_project_path(root, raw_path)
        add_candidate(path, rule_origins)
    for raw_path in ("Plan.md", "plan.md", "docs/Plan.md", "docs/plan.md"):
        path = checked_project_path(root, raw_path)
        add_candidate(path, ("conventional-path",))
    if plan_dir(root).is_dir():
        for path in sorted(plan_dir(root).glob("*.md")):
            if path.is_file():
                add_candidate(path.resolve(), ("governance-plan-file",))
    for path in explicit_paths:
        add_candidate(path, ("agent-input",))
    if active_path is not None and active_path.is_file():
        add_candidate(active_path, ("index",))

    candidates: list[AuthorityCandidate] = []
    for path, origins in sorted(candidate_origins.items(), key=lambda item: item[0].as_posix()):
        raw_path = relative_project_path(root, path)
        active = active_path is not None and path.resolve() == active_path
        rules_confirmed = any(
            origin.startswith("AGENTS.md:") or origin.startswith("CLAUDE.md:") for origin in origins
        )
        classification, signals = classify_candidate(
            path,
            active=active,
            rules_confirmed=rules_confirmed,
            explicit_classification=explicit_by_identity.get(
                (path.stat().st_dev, path.stat().st_ino)
            ),
        )
        plan_id, revision, status = optional_plan_metadata(path)
        candidates.append(
            AuthorityCandidate(
                path=raw_path,
                classification=classification,
                origin=",".join(sorted(origins)),
                signals=signals,
                sha256=sha256_file(path),
                plan_id=plan_id,
                revision=revision,
                status=status,
            )
        )
    return candidates


def incomplete_migration_journals(root: Path) -> list[Path]:
    """Return migration journals that have not reached committed state."""
    migrations_dir = plan_dir(root) / ".migrations"
    if not migrations_dir.is_dir():
        return []
    journals: list[Path] = []
    for path in sorted(migrations_dir.glob("MIG-*.yaml")):
        try:
            payload = load_yaml_file(path)
        except WorkctlError:
            journals.append(path)
            continue
        if payload.get("status") != "committed":
            journals.append(path)
    return journals


def incomplete_rollover_journals(root: Path) -> list[Path]:
    """Return rollover journals that have not reached committed state."""
    rollovers_dir = plan_dir(root) / ".rollovers"
    if rollovers_dir.is_symlink():
        raise WorkctlError(f"ROLLOVER_PATH_SYMLINK: {plan_relative_path('.rollovers')}")
    if not rollovers_dir.is_dir():
        return []
    journals: list[Path] = []
    for path in sorted(rollovers_dir.glob("ROL-*.yaml")):
        try:
            payload = load_yaml_file(path)
        except WorkctlError:
            journals.append(path)
            continue
        if payload.get("status") != "committed":
            journals.append(path)
    return journals


def incomplete_retirement_journals(root: Path) -> list[Path]:
    """Return retirement journals that have not reached committed state."""
    retirements_dir = plan_dir(root) / ".retirements"
    if retirements_dir.is_symlink():
        raise WorkctlError(f"RETIREMENT_PATH_SYMLINK: {plan_relative_path('.retirements')}")
    if not retirements_dir.is_dir():
        return []
    journals: list[Path] = []
    for path in sorted(retirements_dir.glob("RET-*.yaml")):
        try:
            payload = load_yaml_file(path)
        except WorkctlError:
            journals.append(path)
            continue
        if payload.get("status") != "committed":
            journals.append(path)
    return journals


def runtime_transaction_journals(
    root: Path,
    directory_name: str,
    id_pattern: re.Pattern[str],
    *,
    error: str,
) -> list[Path]:
    """Return canonical runtime journals after rejecting unsafe inventory entries."""
    base = governance_root(root) / "runtime" / directory_name
    if base.is_symlink():
        raise WorkctlError(error)
    if not base.is_dir():
        return []
    journals: list[Path] = []
    for transaction in sorted(base.iterdir(), key=lambda path: path.name):
        if (
            transaction.is_symlink()
            or not transaction.is_dir()
            or id_pattern.fullmatch(transaction.name) is None
        ):
            raise WorkctlError(error)
        journal = transaction / "journal.json"
        if journal.is_symlink():
            raise WorkctlError(error)
        if journal.exists():
            if not journal.is_file():
                raise WorkctlError(error)
            journals.append(journal)
    return journals


def incomplete_contract_upgrade_journals(root: Path) -> list[Path]:
    """Return contract-upgrade journals that have not reached committed state."""
    journals: list[Path] = []
    for path in runtime_transaction_journals(
        root,
        "contract-upgrades",
        CONTRACT_UPGRADE_ID_RE,
        error="INVALID_CONTRACT_UPGRADE_TRANSACTION_INVENTORY",
    ):
        try:
            payload = load_yaml_file(path)
        except WorkctlError:
            journals.append(path)
            continue
        if payload.get("status") != "committed":
            journals.append(path)
    return journals


def incomplete_reconcile_upgrade_journals(root: Path) -> list[Path]:
    """Return composed parent journals that have not reached committed state."""
    journals: list[Path] = []
    for path in runtime_transaction_journals(
        root,
        "reconcile-upgrades",
        RECONCILE_UPGRADE_ID_RE,
        error="INVALID_RECONCILE_UPGRADE_TRANSACTION_INVENTORY",
    ):
        try:
            payload = load_yaml_file(path)
        except WorkctlError:
            journals.append(path)
            continue
        if payload.get("status") != "committed":
            journals.append(path)
    return journals


def incomplete_structural_rebase_journals(root: Path) -> list[Path]:
    """Return structural-rebase journals that have not reached committed state."""
    journals: list[Path] = []
    for path in runtime_transaction_journals(
        root,
        "structural-rebases",
        STRUCTURAL_REBASE_ID_RE,
        error="INVALID_STRUCTURAL_REBASE_TRANSACTION_INVENTORY",
    ):
        try:
            payload = load_yaml_file(path)
        except WorkctlError:
            journals.append(path)
            continue
        if payload.get("status") != "committed":
            journals.append(path)
    return journals


def ignored_transaction_journals(
    root: Path,
    ignore_journal: Path | None,
) -> set[Path]:
    """Expand an authenticated child journal exemption to its parent workflow."""
    if ignore_journal is None:
        return set()
    ignored = {ignore_journal.resolve()}
    for parent_path in runtime_transaction_journals(
        root,
        "reconcile-upgrades",
        RECONCILE_UPGRADE_ID_RE,
        error="INVALID_RECONCILE_UPGRADE_TRANSACTION_INVENTORY",
    ):
        try:
            parent = load_reconcile_upgrade_journal(root, parent_path)
            migration = checked_project_path(root, str(parent["migration_journal"]))
            upgrade = checked_project_path(root, str(parent["contract_upgrade_journal"]))
        except WorkctlError:
            continue
        related = {parent_path.resolve(), migration.resolve(), upgrade.resolve()}
        if ignored & related:
            ignored.update(related)
    return ignored


def rollover_transaction_paths(
    root: Path,
    rollover_id: str,
) -> tuple[Path, Path, Path]:
    """Resolve rollover paths and reject every symlink before file access."""
    raw_rollovers_dir = plan_dir(root) / ".rollovers"
    raw_rollover_dir = raw_rollovers_dir / rollover_id
    raw_staging_dir = raw_rollover_dir / "staging"
    raw_journal_path = raw_rollovers_dir / f"{rollover_id}.yaml"
    for raw_path in (
        plan_dir(root),
        raw_rollovers_dir,
        raw_rollover_dir,
        raw_staging_dir,
        raw_journal_path,
    ):
        if raw_path.is_symlink():
            raise WorkctlError(f"ROLLOVER_PATH_SYMLINK: {raw_path.relative_to(root).as_posix()}")
    rollover_dir = checked_project_path(root, plan_relative_path(".rollovers", rollover_id))
    staging_dir = checked_project_path(
        root,
        plan_relative_path(".rollovers", rollover_id, "staging"),
    )
    journal_path = checked_project_path(
        root,
        plan_relative_path(".rollovers", f"{rollover_id}.yaml"),
    )
    return rollover_dir, staging_dir, journal_path


def retirement_transaction_paths(
    root: Path,
    retirement_id: str,
) -> tuple[Path, Path, Path, Path]:
    """Resolve retirement paths and reject every symlink before file access."""
    raw_retirements_dir = plan_dir(root) / ".retirements"
    raw_retirement_dir = raw_retirements_dir / retirement_id
    raw_staging_dir = raw_retirement_dir / "staging"
    raw_archive_path = raw_retirement_dir / "original.md"
    raw_journal_path = raw_retirements_dir / f"{retirement_id}.yaml"
    for raw_path in (
        plan_dir(root),
        raw_retirements_dir,
        raw_retirement_dir,
        raw_staging_dir,
        raw_archive_path,
        raw_journal_path,
    ):
        if raw_path.is_symlink():
            raise WorkctlError(f"RETIREMENT_PATH_SYMLINK: {raw_path.relative_to(root).as_posix()}")
    retirement_dir = checked_project_path(
        root,
        plan_relative_path(".retirements", retirement_id),
    )
    staging_dir = checked_project_path(
        root,
        plan_relative_path(".retirements", retirement_id, "staging"),
    )
    archive_path = checked_project_path(
        root,
        plan_relative_path(".retirements", retirement_id, "original.md"),
    )
    journal_path = checked_project_path(
        root,
        plan_relative_path(".retirements", f"{retirement_id}.yaml"),
    )
    return retirement_dir, staging_dir, archive_path, journal_path


def reconciliation_transaction_paths(
    root: Path,
    migration_id: str,
) -> tuple[Path, Path, Path]:
    """Resolve reconciliation paths only after rejecting symlink components."""
    raw_migrations_dir = plan_dir(root) / ".migrations"
    raw_migration_dir = raw_migrations_dir / migration_id
    raw_staging_dir = raw_migration_dir / "staging"
    raw_journal_path = raw_migrations_dir / f"{migration_id}.yaml"
    for raw_path in (
        plan_dir(root),
        raw_migrations_dir,
        raw_migration_dir,
        raw_staging_dir,
        raw_journal_path,
    ):
        reject_symlink_components(root, raw_path)
    migration_dir = checked_project_path(
        root,
        plan_relative_path(".migrations", migration_id),
    )
    staging_dir = checked_project_path(
        root,
        plan_relative_path(".migrations", migration_id, "staging"),
    )
    journal_path = checked_project_path(
        root,
        plan_relative_path(".migrations", f"{migration_id}.yaml"),
    )
    return migration_dir, staging_dir, journal_path


def authority_metadata_errors(
    root: Path,
    doc: PlanDocument,
    *,
    seen: set[Path] | None = None,
) -> list[str]:
    """Validate deterministic single-active authority metadata and lineage."""
    errors: list[str] = []
    resolved_path = doc.path.resolve()
    lineage = set() if seen is None else set(seen)
    if resolved_path in lineage:
        return [f"authority predecessor cycle: {relative_project_path(root, doc.path)}"]
    lineage.add(resolved_path)
    authority = doc.frontmatter.get("authority")
    if not isinstance(authority, dict):
        return ["active Plan lacks authority metadata"]
    if authority.get("model") != AUTHORITY_MODEL:
        errors.append(f"authority.model must be {AUTHORITY_MODEL}")
    if authority.get("state") != AUTHORITY_STATE:
        errors.append(f"authority.state must be {AUTHORITY_STATE}")
    if authority.get("canonical_plan_id") != doc.frontmatter.get("plan_id"):
        errors.append("authority.canonical_plan_id must match plan_id")
    rollover_id = authority.get("rollover_id")
    predecessor = authority.get("predecessor")
    predecessor_doc: PlanDocument | None = None
    if predecessor is None:
        if rollover_id is not None:
            errors.append("authority.rollover_id requires authority.predecessor")
    elif not isinstance(predecessor, dict):
        errors.append("authority.predecessor must be a mapping")
    else:
        if not isinstance(rollover_id, str) or ROLLOVER_ID_RE.fullmatch(rollover_id) is None:
            errors.append("authority.rollover_id must match ROL-YYYYMMDD-NNN")
        predecessor_path = predecessor.get("path")
        predecessor_id = predecessor.get("plan_id")
        predecessor_revision = predecessor.get("revision")
        predecessor_sha256 = predecessor.get("sha256")
        if not isinstance(predecessor_path, str):
            errors.append("authority.predecessor.path is required")
        else:
            try:
                predecessor_file = checked_project_path(root, predecessor_path)
            except WorkctlError as exc:
                errors.append(str(exc))
            else:
                if predecessor_file.resolve() == resolved_path:
                    errors.append("authority predecessor cannot reference itself")
                elif not predecessor_file.is_file():
                    errors.append(f"authority predecessor missing: {predecessor_path}")
                elif (
                    isinstance(predecessor_sha256, str)
                    and SHA256_RE.fullmatch(predecessor_sha256) is not None
                    and sha256_file(predecessor_file) != predecessor_sha256
                ):
                    errors.append(f"authority predecessor hash mismatch: {predecessor_path}")
                else:
                    try:
                        predecessor_doc = load_plan(predecessor_file)
                    except WorkctlError as exc:
                        errors.append(str(exc))
        if not isinstance(predecessor_id, str) or PLAN_ID_RE.fullmatch(predecessor_id) is None:
            errors.append("authority.predecessor.plan_id must match PLAN-YYYYMMDD-NNN")
        if type(predecessor_revision) is not int or predecessor_revision < 1:
            errors.append("authority.predecessor.revision must be a positive integer")
        if (
            not isinstance(predecessor_sha256, str)
            or SHA256_RE.fullmatch(predecessor_sha256) is None
        ):
            errors.append("authority.predecessor.sha256 must be a SHA256 digest")
        if predecessor_doc is not None:
            if predecessor_doc.frontmatter.get("plan_id") != predecessor_id:
                errors.append("authority predecessor plan_id mismatch")
            if predecessor_doc.frontmatter.get("revision") != predecessor_revision:
                errors.append("authority predecessor revision mismatch")
            if predecessor_doc.frontmatter.get("status") != "complete":
                errors.append("authority predecessor must be complete")
    migration_id = authority.get("migration_id")
    if migration_id is not None and (
        not isinstance(migration_id, str) or MIGRATION_ID_RE.fullmatch(migration_id) is None
    ):
        errors.append("authority.migration_id must match MIG-YYYYMMDD-NNN")
    sources = authority.get("sources", [])
    if not isinstance(sources, list):
        return [*errors, "authority.sources must be a list"]
    for source in sources:
        if not isinstance(source, dict):
            errors.append("authority.sources entries must be mappings")
            continue
        source_path = source.get("path")
        source_hash = source.get("sha256")
        archive_path = source.get("archive_path")
        role = source.get("role")
        if not isinstance(source_path, str):
            errors.append("authority source requires path")
            continue
        if role not in SOURCE_ROLES:
            errors.append(f"authority source {source_path} has invalid role")
        if not isinstance(source_hash, str) or SHA256_RE.fullmatch(source_hash) is None:
            errors.append(f"authority source {source_path} has invalid sha256")
        if not isinstance(archive_path, str):
            errors.append(f"authority source {source_path} requires archive_path")
            continue
        try:
            archive = checked_project_path(root, archive_path)
            original = checked_project_path(root, source_path)
        except WorkctlError as exc:
            errors.append(str(exc))
            continue
        if not archive.is_file():
            errors.append(f"authority archive missing: {archive_path}")
        elif isinstance(source_hash, str) and sha256_file(archive) != source_hash:
            errors.append(f"authority archive hash mismatch: {archive_path}")
        if not original.is_file():
            errors.append(f"authority source pointer missing: {source_path}")
        else:
            pointer = original.read_text(encoding="utf-8", errors="replace")
            if POINTER_MARKER not in pointer:
                errors.append(f"authority source is not a migration pointer: {source_path}")
            if isinstance(migration_id, str) and migration_id not in pointer:
                errors.append(f"authority source pointer has wrong migration: {source_path}")
            canonical_name = doc.path.name
            if canonical_name not in pointer:
                errors.append(f"authority source pointer has wrong canonical Plan: {source_path}")
    confirmation_map = authority.get("confirmations", {})
    if not isinstance(confirmation_map, dict):
        errors.append("authority.confirmations must be a mapping")
    else:
        if predecessor is not None:
            rollover_confirmation_id = confirmation_map.get("rollover")
            if not isinstance(rollover_confirmation_id, str):
                errors.append("authority.confirmations.rollover is required for rollovers")
            else:
                try:
                    require_confirmation(doc.frontmatter, rollover_confirmation_id)
                except WorkctlError as exc:
                    errors.append(str(exc))
                rollover_confirmation = confirmations(doc.frontmatter).get(rollover_confirmation_id)
                evidence_sha256 = (
                    rollover_confirmation.get("evidence_sha256") if rollover_confirmation else None
                )
                if (
                    not isinstance(evidence_sha256, str)
                    or SHA256_RE.fullmatch(evidence_sha256) is None
                ):
                    errors.append(f"{rollover_confirmation_id} requires evidence_sha256")
        if migration_id is not None:
            baseline_id = confirmation_map.get("baseline")
            if not isinstance(baseline_id, str):
                errors.append("authority.confirmations.baseline is required for migrations")
            else:
                try:
                    require_confirmation(doc.frontmatter, baseline_id)
                except WorkctlError as exc:
                    errors.append(str(exc))
                baseline = confirmations(doc.frontmatter).get(baseline_id)
                evidence_sha256 = baseline.get("evidence_sha256") if baseline else None
                if (
                    not isinstance(evidence_sha256, str)
                    or SHA256_RE.fullmatch(evidence_sha256) is None
                ):
                    errors.append(f"{baseline_id} requires evidence_sha256")
            agents_id = confirmation_map.get("agents_rewrite")
            if agents_id is not None:
                if not isinstance(agents_id, str):
                    errors.append("authority.confirmations.agents_rewrite must be a string")
                else:
                    try:
                        require_confirmation(doc.frontmatter, agents_id)
                    except WorkctlError as exc:
                        errors.append(str(exc))
                    agents_confirmation = confirmations(doc.frontmatter).get(agents_id)
                    evidence_sha256 = (
                        agents_confirmation.get("evidence_sha256") if agents_confirmation else None
                    )
                    if (
                        not isinstance(evidence_sha256, str)
                        or SHA256_RE.fullmatch(evidence_sha256) is None
                    ):
                        errors.append(f"{agents_id} requires evidence_sha256")
    if predecessor_doc is not None:
        errors.extend(
            f"predecessor lineage: {error}"
            for error in authority_metadata_errors(root, predecessor_doc, seen=lineage)
        )
    return errors


def allowed_commands_for_state(state: str) -> list[str]:
    """Return commands that may run in an authority state."""
    if state == "PLAN_SCHEMA_REFRESH_REQUIRED":
        return list(SCHEMA_REFRESH_ALLOWED_COMMANDS)
    commands = list(AUTHORITY_BLOCKED_COMMANDS)
    if state == "UNMANAGED_EMPTY":
        commands.append("plan admit apply")
    if state == "GOVERNED_ACTIVE":
        commands.extend(
            [
                "plan revise",
                "plan adapt",
                "plan structural-rebase apply",
                "plan intake record",
                "plan unknown add|classify|resolve",
                "plan confirm",
                "plan closeout-check",
                "plan complete",
                "plan verify-entry",
                "plan artifact-state",
                "plan finalize-artifact",
                "plan delivery-complete",
                "plan activation-promote",
                "task start|block|verify|skip",
                "plan ready|next|blocked",
                "task reprioritize",
                "evidence record",
                "migrate inspect|apply|recover",
                "log append",
            ]
        )
    return commands


def incomplete_v5_migration_journals(root: Path) -> list[Path]:
    """Return unfinished current-schema refresh journals for authority recovery."""
    base = v5_migration_base(root)
    if not base.is_dir():
        return []
    result: list[Path] = []
    for journal in sorted(base.glob("MIG-*/journal.json")):
        try:
            if load_yaml_file(journal).get("status") != "committed":
                result.append(journal)
        except WorkctlError:
            result.append(journal)
    return result


def inspect_authority(
    root: Path,
    explicit_candidates: dict[str, str] | None = None,
    *,
    ignore_journal: Path | None = None,
) -> AuthorityReport:
    """Resolve the deterministic authority state for a project."""
    candidates = discover_authority_candidates(root, explicit_candidates)
    blockers: list[str] = []
    ignored_journals = ignored_transaction_journals(root, ignore_journal)
    migration_journals = [
        journal
        for journal in incomplete_migration_journals(root)
        if journal.resolve() not in ignored_journals
    ]
    rollover_journals = [
        journal
        for journal in incomplete_rollover_journals(root)
        if journal.resolve() not in ignored_journals
    ]
    retirement_journals = [
        journal
        for journal in incomplete_retirement_journals(root)
        if journal.resolve() not in ignored_journals
    ]
    contract_upgrade_journals = [
        journal
        for journal in incomplete_contract_upgrade_journals(root)
        if journal.resolve() not in ignored_journals
    ]
    reconcile_upgrade_journals = [
        journal
        for journal in incomplete_reconcile_upgrade_journals(root)
        if journal.resolve() not in ignored_journals
    ]
    structural_rebase_journals = [
        journal
        for journal in incomplete_structural_rebase_journals(root)
        if journal.resolve() not in ignored_journals
    ]
    v5_migration_journals = incomplete_v5_migration_journals(root)
    if (
        migration_journals
        or rollover_journals
        or retirement_journals
        or contract_upgrade_journals
        or reconcile_upgrade_journals
        or structural_rebase_journals
        or v5_migration_journals
    ):
        blockers.extend(
            f"incomplete migration journal: {relative_project_path(root, journal)}"
            for journal in migration_journals
        )
        blockers.extend(
            f"incomplete rollover journal: {relative_project_path(root, journal)}"
            for journal in rollover_journals
        )
        blockers.extend(
            f"incomplete retirement journal: {relative_project_path(root, journal)}"
            for journal in retirement_journals
        )
        blockers.extend(
            f"incomplete contract-upgrade journal: {relative_project_path(root, journal)}"
            for journal in contract_upgrade_journals
        )
        blockers.extend(
            f"incomplete reconcile-upgrade journal: {relative_project_path(root, journal)}"
            for journal in reconcile_upgrade_journals
        )
        blockers.extend(
            f"incomplete structural-rebase journal: {relative_project_path(root, journal)}"
            for journal in structural_rebase_journals
        )
        blockers.extend(
            f"incomplete current-schema refresh journal: {relative_project_path(root, journal)}"
            for journal in v5_migration_journals
        )
        state = "MIGRATION_RECOVERY_REQUIRED"
        return AuthorityReport(state, candidates, blockers, allowed_commands_for_state(state))

    active_doc: PlanDocument | None = None
    active_candidate: AuthorityCandidate | None = None
    if index_path(root).is_file():
        try:
            active_doc = load_plan(active_plan_path(root))
            active_relative = relative_project_path(root, active_doc.path)
            active_candidate = next(
                (candidate for candidate in candidates if candidate.path == active_relative),
                None,
            )
        except WorkctlError as exc:
            blockers.append(str(exc))
            state = "MIGRATION_RECOVERY_REQUIRED"
            return AuthorityReport(state, candidates, blockers, allowed_commands_for_state(state))

    if active_doc is None:
        confirmed = [
            candidate
            for candidate in candidates
            if candidate.classification == "CONFIRMED_AUTHORITY"
        ]
        likely = [
            candidate for candidate in candidates if candidate.classification == "LIKELY_AUTHORITY"
        ]
        if confirmed:
            blockers.append("historical execution authority must be migrated")
            state = "MIGRATION_REQUIRED"
        elif likely:
            blockers.append("candidate authority requires semantic confirmation")
            state = "AUTHORITY_REVIEW_REQUIRED"
        else:
            state = "UNMANAGED_EMPTY"
        return AuthorityReport(state, candidates, blockers, allowed_commands_for_state(state))

    has_authority_metadata = isinstance(active_doc.frontmatter.get("authority"), dict)
    uses_minimal_v5_authority = (
        active_doc.frontmatter.get("schema_version") == 5 and not has_authority_metadata
    )
    lineage_errors = (
        []
        if uses_minimal_v5_authority
        else authority_metadata_errors(root, active_doc)
    )
    external_confirmed = [
        candidate
        for candidate in candidates
        if candidate is not active_candidate
        and candidate.classification == "CONFIRMED_AUTHORITY"
        and (
            "migration-pointer" not in candidate.signals
            or "project-rule-explicit" in candidate.signals
        )
    ]
    external_likely = [
        candidate
        for candidate in candidates
        if candidate is not active_candidate
        and candidate.classification == "LIKELY_AUTHORITY"
        and "migration-pointer" not in candidate.signals
    ]
    active_contract_state = contract_state(active_doc.frontmatter)
    if external_confirmed:
        blockers.extend(
            f"unreconciled confirmed authority: {candidate.path}"
            for candidate in external_confirmed
        )
        state = "RECONCILIATION_REQUIRED"
    elif external_likely:
        blockers.extend(
            f"candidate authority requires review: {candidate.path}"
            for candidate in external_likely
        )
        state = "AUTHORITY_REVIEW_REQUIRED"
    elif active_contract_state == "PLAN_SCHEMA_REFRESH_REQUIRED":
        blockers.append("active Plan requires current-schema refresh")
        state = active_contract_state
    elif not has_authority_metadata and not uses_minimal_v5_authority:
        blockers.append("active Plan requires authority metadata registration")
        state = "AUTHORITY_REGISTRATION_REQUIRED"
    elif lineage_errors:
        blockers.extend(lineage_errors)
        state = "MIGRATION_RECOVERY_REQUIRED"
    else:
        state = "GOVERNED_ACTIVE"
    return AuthorityReport(state, candidates, blockers, allowed_commands_for_state(state))


def require_governed_authority(root: Path) -> AuthorityReport:
    """Fail closed unless the project has one valid governed active Plan."""
    report = inspect_authority(root)
    if report.state != "GOVERNED_ACTIVE":
        raise WorkctlError(
            f"AUTHORITY_BLOCKED: {report.state}; allowed={','.join(report.allowed_commands)}"
        )
    return report


def require_current_schema_refresh_authority(root: Path) -> AuthorityReport:
    """Allow only ordinary governed state or the explicit old-Plan refresh state."""
    report = inspect_authority(root)
    if report.state not in {"GOVERNED_ACTIVE", "PLAN_SCHEMA_REFRESH_REQUIRED"}:
        raise WorkctlError(
            f"AUTHORITY_BLOCKED: {report.state}; allowed={','.join(report.allowed_commands)}"
        )
    return report


def active_plan_path(root: Path) -> Path:
    index = load_yaml_file(index_path(root))
    active = index.get("active_plan_id")
    if not isinstance(active, str) or not active:
        raise WorkctlError(
            f"NO_ACTIVE_PLAN: {plan_relative_path('index.yaml')} has no active_plan_id"
        )
    for item in index.get("plans", []):
        if isinstance(item, dict) and item.get("id") == active:
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                raise WorkctlError("INVALID_INDEX: active plan has no path")
            return plan_dir(root) / raw_path
    raise WorkctlError(f"NO_ACTIVE_PLAN: active plan {active} is not listed")


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WorkctlError(f"MISSING_FILE: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise WorkctlError(f"INVALID_YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkctlError(f"INVALID_YAML: {path} must contain a mapping")
    return data


def load_plan(path: Path) -> PlanDocument:
    if not path.is_file():
        raise WorkctlError(f"MISSING_FILE: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkctlError(f"INVALID_PLAN: {path}: {exc}") from exc
    if not text.startswith("---\n"):
        raise WorkctlError("INVALID_PLAN: plan must start with YAML frontmatter")
    try:
        _, raw_frontmatter, body = text.split("---\n", 2)
    except ValueError as exc:
        raise WorkctlError("INVALID_PLAN: plan frontmatter is not closed") from exc
    try:
        frontmatter = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError as exc:
        raise WorkctlError(f"INVALID_PLAN_FRONTMATTER_YAML: {path}: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise WorkctlError("INVALID_PLAN: plan frontmatter must be a mapping")
    return PlanDocument(path=path, frontmatter=frontmatter, body=body)


def dump_plan(doc: PlanDocument) -> str:
    frontmatter = yaml.safe_dump(
        doc.frontmatter,
        sort_keys=False,
        allow_unicode=False,
    )
    return f"---\n{frontmatter}---\n{doc.body.lstrip()}"


def fsync_directory(path: Path) -> None:
    """Synchronize one directory entry set to durable storage."""
    try:
        module_filesystem.fsync_directory(path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def fsync_tree(path: Path) -> None:
    """Synchronize every regular file, then every directory from leaves upward."""
    try:
        module_filesystem.fsync_tree(path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def ensure_directory_durable(path: Path) -> None:
    """Create a directory chain and synchronize each new parent entry."""
    try:
        module_filesystem.ensure_directory_durable(path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def write_atomic_bytes(path: Path, content: bytes) -> None:
    """Atomically and durably replace a file with exact bytes."""
    try:
        module_filesystem.write_atomic_bytes(path, content)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def write_atomic(path: Path, text: str) -> None:
    """Atomically replace a UTF-8 text file."""
    try:
        module_filesystem.write_atomic(path, text)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def durable_replace(source: Path, target: Path) -> None:
    """Rename one path and durably synchronize both affected parent entries."""
    try:
        module_filesystem.durable_replace(source, target)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def durable_copy_file(source: Path, target: Path) -> None:
    """Copy one regular file through a synced temp file and durable rename."""
    try:
        module_filesystem.durable_copy_file(source, target)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


def durable_unlink(path: Path) -> None:
    """Remove one file and synchronize the parent directory entry."""
    try:
        module_filesystem.durable_unlink(path)
    except ModuleFilesystemError as exc:
        raise WorkctlError(str(exc)) from exc


@contextlib.contextmanager
def lock(root: Path) -> Iterator[None]:
    """Hold the stable controller lock with bounded contention diagnostics."""
    ensure_governance_ownership(root)
    lock_path = workctl_lock_path(root)
    governance = governance_root(root)
    if governance.is_symlink() or (governance.exists() and not governance.is_dir()):
        raise WorkctlError("LAYOUT_STABLE_LOCK_PARENT_INVALID")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
        raise WorkctlError("LAYOUT_STABLE_LOCK_INVALID")
    with lock_path.open("a+", encoding="utf-8") as handle:
        raw_timeout = os.environ.get("WORK_GOVERNANCE_LOCK_TIMEOUT_SECONDS")
        try:
            timeout = LOCK_TIMEOUT_SECONDS if raw_timeout is None else float(raw_timeout)
        except ValueError as exc:
            raise WorkctlError("WORKCTL_LOCK_TIMEOUT_CONFIG_INVALID") from exc
        if not 0.05 <= timeout <= 60.0:
            raise WorkctlError("WORKCTL_LOCK_TIMEOUT_CONFIG_INVALID")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    handle.seek(0)
                    raw_holder = handle.read(2048)
                    try:
                        holder: object = json.loads(raw_holder) if raw_holder else {}
                    except json.JSONDecodeError:
                        holder = {}
                    holder_pid = (
                        str(holder.get("pid"))
                        if isinstance(holder, dict) and holder.get("pid") is not None
                        else "unavailable"
                    )
                    holder_acquired_at = (
                        str(holder.get("acquired_at"))
                        if isinstance(holder, dict) and holder.get("acquired_at") is not None
                        else "unavailable"
                    )
                    raise WorkctlError(
                        "WORKCTL_LOCK_TIMEOUT: "
                        f"timeout_seconds={timeout:g} "
                        f"holder_pid={holder_pid} "
                        f"holder_acquired_at={holder_acquired_at}"
                    ) from None
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            handle.seek(0)
            handle.truncate()
            json.dump(
                {
                    "schema_version": 1,
                    "pid": os.getpid(),
                    "acquired_at": utc_now(),
                },
                handle,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def require_expected_revision(frontmatter: dict[str, Any], expected: int | None) -> None:
    if expected is None:
        raise WorkctlError("EXPECTED_REVISION_REQUIRED")
    current = frontmatter.get("revision")
    if current != expected:
        raise WorkctlError(f"REVISION_MISMATCH: expected {expected}, found {current}")


def append_revision_record(
    frontmatter: dict[str, Any],
    *,
    revision: int,
    kind: str,
    rationale: str,
    confirmation_id: str | None = None,
    evidence_manifest: str | None = None,
    changed_at: str | None = None,
) -> None:
    """Append one immutable schema-v4 revision provenance record."""
    if kind not in REVISION_KINDS:
        raise WorkctlError(f"INVALID_REVISION_KIND: {kind}")
    history = frontmatter.setdefault("revision_history", [])
    if not isinstance(history, list):
        raise WorkctlError("INVALID_PLAN: revision_history must be a list")
    if any(isinstance(item, dict) and item.get("revision") == revision for item in history):
        raise WorkctlError(f"REVISION_RECORD_EXISTS: {revision}")
    record: dict[str, Any] = {
        "revision": revision,
        "kind": kind,
        "changed_at": changed_at or utc_now(),
        "rationale": rationale,
    }
    if confirmation_id is not None:
        record["confirmation_id"] = confirmation_id
    if evidence_manifest is not None:
        record["evidence_manifest"] = evidence_manifest
    record["decision_basis_sha256"] = decision_basis_sha256(frontmatter)
    history.append(record)


def bump_revision(
    frontmatter: dict[str, Any],
    *,
    kind: str = "controlled-transition",
    rationale: str = "Apply one controller-validated state transition.",
    confirmation_id: str | None = None,
    evidence_manifest: str | None = None,
    timestamp: str | None = None,
) -> None:
    revision = frontmatter.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise WorkctlError("INVALID_PLAN: revision must be a positive integer")
    next_revision = revision + 1
    frontmatter["revision"] = next_revision
    if frontmatter.get("schema_version") == 5:
        frontmatter["contract_revision"] = next_revision
    frontmatter["updated_at"] = timestamp or utc_now()
    if frontmatter.get("schema_version") == 4:
        append_revision_record(
            frontmatter,
            revision=next_revision,
            kind=kind,
            rationale=rationale,
            confirmation_id=confirmation_id,
            evidence_manifest=evidence_manifest,
            changed_at=timestamp,
        )


def contract_state(frontmatter: dict[str, Any]) -> str:
    """Return the current-schema state independently from Plan authority."""
    schema_version = frontmatter.get("schema_version")
    status = frontmatter.get("status")
    if schema_version == CURRENT_PLAN_SCHEMA_VERSION:
        return "PLAN_CONTRACT_READY"
    if status not in {"complete", "retired"}:
        return "PLAN_SCHEMA_REFRESH_REQUIRED"
    return "PLAN_CONTRACT_LEGACY_READABLE"


def require_plan_contract_ready(frontmatter: dict[str, Any]) -> None:
    """Block ordinary writes from silently trusting an outdated active contract."""
    state = contract_state(frontmatter)
    if state != "PLAN_CONTRACT_READY":
        raise WorkctlError(state)


def blocking_artifacts(frontmatter: dict[str, Any]) -> dict[str, str]:
    """Return blocking artifact IDs and states from a Plan."""
    if module_blocking_artifacts is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: blocking_artifacts")
    return module_blocking_artifacts(frontmatter, BLOCKING_ARTIFACT_STATES)


def require_no_blocking_artifacts(
    frontmatter: dict[str, Any],
    recovery_task: dict[str, Any] | None = None,
) -> None:
    """Block progress unless the task explicitly repairs a suspect artifact."""
    blocked = blocking_artifacts(frontmatter)
    if not blocked:
        return
    non_suspect = {
        artifact_id: status for artifact_id, status in blocked.items() if status != "suspect"
    }
    if non_suspect:
        artifact_id = sorted(non_suspect)[0]
        raise WorkctlError(f"BLOCKED_BY_ARTIFACT: {artifact_id} is {non_suspect[artifact_id]}")
    resolves = recovery_task.get("resolves_artifacts", []) if recovery_task else []
    if (
        isinstance(resolves, list)
        and resolves
        and all(isinstance(artifact_id, str) and artifact_id in blocked for artifact_id in resolves)
    ):
        return
    artifact_id = sorted(blocked)[0]
    raise WorkctlError(f"BLOCKED_BY_ARTIFACT: {artifact_id} is {blocked[artifact_id]}")


def confirmations(frontmatter: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return cast(dict[str, dict[str, Any]], module_confirmation_lookup(frontmatter))


def intervention_errors(
    frontmatter: Mapping[str, Any],
    item: Mapping[str, Any],
) -> list[str]:
    """Validate one typed user-intervention contract without rejecting legacy gates."""
    intervention = item.get("intervention")
    if intervention is None:
        return []
    confirmation_id = str(item.get("id", "unknown"))
    if not isinstance(intervention, dict):
        return [f"{confirmation_id}.intervention must be a mapping"]
    errors: list[str] = []
    kind = intervention.get("kind")
    if kind not in INTERVENTION_KINDS:
        errors.append(f"{confirmation_id}.intervention.kind must be supported")
    action_kind = intervention.get("action_kind")
    if action_kind is not None:
        if action_kind not in HIGH_IMPACT_ACTION_KINDS:
            errors.append(f"{confirmation_id}.intervention.action_kind must be supported")
        elif (action_kind == "substantive_rollback" and kind != "deviation_recovery") or (
            action_kind != "substantive_rollback" and kind != "external_authority"
        ):
            errors.append(f"{confirmation_id}.intervention.action_kind does not match kind")
    blocks = intervention.get("blocks")
    if (
        not isinstance(blocks, list)
        or not blocks
        or not all(valid_target_ref(target) for target in blocks)
    ):
        errors.append(f"{confirmation_id}.intervention.blocks must be non-empty target refs")
    elif len(blocks) != len(set(blocks)):
        errors.append(f"{confirmation_id}.intervention.blocks must be unique")
    else:
        for target in blocks:
            try:
                require_target_exists(frontmatter, target)
            except WorkctlError:
                errors.append(f"{confirmation_id}.intervention.blocks names unknown {target}")
    if not valid_reference(intervention.get("basis_ref")):
        errors.append(f"{confirmation_id}.intervention.basis_ref must be typed")
    basis_sha256 = intervention.get("basis_sha256")
    if kind in {"plan_contract", "deviation_recovery"}:
        if not isinstance(basis_sha256, str) or SHA256_RE.fullmatch(basis_sha256) is None:
            errors.append(f"{confirmation_id}.intervention.basis_sha256 is required")
    elif basis_sha256 is not None and (
        not isinstance(basis_sha256, str) or SHA256_RE.fullmatch(basis_sha256) is None
    ):
        errors.append(f"{confirmation_id}.intervention.basis_sha256 must be a SHA256 digest")
    return errors


def intervention_contract_state(frontmatter: Mapping[str, Any]) -> str:
    """Project strict, legacy-classification, or invalid intervention metadata."""
    raw = frontmatter.get("confirmations", {})
    if not isinstance(raw, dict):
        return "INVALID"
    legacy_pending = False
    for group in ("required", "accepted"):
        values = raw.get(group, [])
        if not isinstance(values, list):
            return "INVALID"
        for item in values:
            if not isinstance(item, dict):
                return "INVALID"
            if intervention_errors(frontmatter, item):
                return "INVALID"
            if item.get("status") == "pending" and item.get("intervention") is None:
                legacy_pending = True
    return "LEGACY_CLASSIFICATION_REQUIRED" if legacy_pending else "STRICT_READY"


def require_strict_intervention_contract(frontmatter: Mapping[str, Any]) -> None:
    """Reject structural advancement while a pending gate lacks a strict contract."""
    state = intervention_contract_state(frontmatter)
    if state != "STRICT_READY":
        raise WorkctlError(f"INTERVENTION_CONTRACT_{state}")


def intervention_placeholder(item: Mapping[str, Any]) -> bool:
    """Return whether an external-authority gate still carries a bootstrap placeholder."""
    intervention = item.get("intervention")
    return bool(
        isinstance(intervention, dict)
        and intervention.get("kind") == "external_authority"
        and isinstance(intervention.get("basis_ref"), str)
        and str(intervention["basis_ref"]).startswith("evidence:pending-")
    )


def current_advancement_targets(frontmatter: Mapping[str, Any]) -> list[str]:
    """Return the smallest dependency-ready target set for intervention projection."""
    if MODULE_CURRENT_ADVANCEMENT_TARGETS is None:
        raise WorkctlError("SCHEDULER_MODULE_UNAVAILABLE: current_advancement_targets")
    return MODULE_CURRENT_ADVANCEMENT_TARGETS(frontmatter, VERIFIED_TASK_STATES)


def scheduler_state_path(root: Path, plan_id: str) -> Path:
    """Return the ignored runtime scheduler state path for one active Plan."""
    if MODULE_SCHEDULER_STATE_PATH is None:
        raise WorkctlError("SCHEDULER_MODULE_UNAVAILABLE: scheduler_state_path")
    return MODULE_SCHEDULER_STATE_PATH(
        root,
        plan_id,
        GOVERNANCE_DIR_NAME,
        reject_symlink_components,
    )


def load_scheduler_state(root: Path, plan_id: str) -> dict[str, Any]:
    """Load a bounded scheduler snapshot without changing the Plan contract."""
    if MODULE_LOAD_SCHEDULER_STATE is None:
        raise WorkctlError("SCHEDULER_MODULE_UNAVAILABLE: load_scheduler_state")
    try:
        return cast(
            dict[str, Any],
            MODULE_LOAD_SCHEDULER_STATE(
                root,
                plan_id,
                GOVERNANCE_DIR_NAME,
                reject_symlink_components,
            ),
        )
    except ModuleSchedulerStateError as exc:
        raise WorkctlError("SCHEDULER_STATE_INVALID") from exc


def dump_scheduler_state(state: Mapping[str, Any]) -> str:
    """Serialize scheduler state with stable formatting for atomic persistence."""
    if MODULE_DUMP_SCHEDULER_STATE is None:
        raise WorkctlError("SCHEDULER_MODULE_UNAVAILABLE: dump_scheduler_state")
    return MODULE_DUMP_SCHEDULER_STATE(state)


def v5_runtime_dir(root: Path, plan_id: str) -> Path:
    """Return the durable runtime bundle directory for one schema-v5 Plan."""
    path = governance_root(root) / "runtime" / "plans" / plan_id
    reject_symlink_components(root, path)
    return path


def v5_state_path(root: Path, plan_id: str) -> Path:
    return v5_runtime_dir(root, plan_id) / "state.json"


def v5_event_path(root: Path, plan_id: str) -> Path:
    return v5_runtime_dir(root, plan_id) / "events.jsonl"


def v5_state_defaults(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Build a valid empty runtime state for a newly created v5 contract."""
    if build_v5_state is None:
        raise WorkctlError("SCHEMA_V5_RUNTIME_MODULE_UNAVAILABLE")
    return build_v5_state(frontmatter, updated_at=str(frontmatter.get("updated_at", utc_now())))


def v5_redact_evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove credential-bearing fields before strict evidence canonicalization."""
    sensitive = ("api_key", "apikey", "authorization", "password", "secret", "token")

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if not any(part in key.lower() for part in sensitive)
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str) and "Bearer " in value:
            return value.split("Bearer ", 1)[0] + "Bearer [REDACTED]"
        return value

    return cast(dict[str, Any], clean(dict(payload)))


def load_v5_state(root: Path, frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Load and validate the independent v5 state snapshot."""
    plan_id = str(frontmatter.get("plan_id"))
    path = v5_state_path(root, plan_id)
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("SCHEMA_V5_STATE_MISSING")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkctlError("SCHEMA_V5_STATE_INVALID") from exc
    if not isinstance(payload, dict):
        raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    tasks = payload.get("tasks")
    priorities = payload.get("priorities")
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != "work-governance-plan-state"
        or payload.get("plan_id") != plan_id
        or type(payload.get("state_sequence")) is not int
        or payload["state_sequence"] < 0
        or type(payload.get("event_sequence")) is not int
        or payload["event_sequence"] < 0
        or not isinstance(tasks, dict)
        or not isinstance(priorities, dict)
        or any(type(value) is not int for value in priorities.values())
    ):
        raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    for task_id, task in tasks.items():
        if (
            not isinstance(task_id, str)
            or not isinstance(task, dict)
            or task.get("status") not in WORK_ITEM_STATES
        ):
            raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    event_path = v5_event_path(root, plan_id)
    if event_path.is_symlink() or not event_path.is_file():
        raise WorkctlError("SCHEMA_V5_EVENT_MISSING")
    event_lines = event_path.read_text(encoding="utf-8").splitlines()
    expected_events = payload["event_sequence"]
    if isinstance(payload.get("pending_event"), dict):
        expected_events -= 1
    if len(event_lines) != expected_events:
        raise WorkctlError("SCHEMA_V5_EVENT_SEQUENCE_MISMATCH")
    return cast(dict[str, Any], payload)


def v5_runtime_frontmatter(
    root: Path,
    frontmatter: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Overlay runtime task state for scheduling without mutating the contract."""
    runtime = copy.deepcopy(dict(frontmatter))
    if state is None:
        state = load_v5_state(root, frontmatter)
    state_tasks = state.get("tasks", {})
    for task in runtime.get("tasks", []) if isinstance(runtime.get("tasks"), list) else []:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        current = state_tasks.get(task["id"]) if isinstance(state_tasks, dict) else None
        if isinstance(current, dict):
            for key, value in current.items():
                if key != "status" or isinstance(value, str):
                    task[key] = copy.deepcopy(value)
    return runtime


def v5_read_events(root: Path, plan_id: str) -> list[dict[str, Any]]:
    """Read the append-only v5 event ledger with canonical JSON validation."""
    path = v5_event_path(root, plan_id)
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("SCHEMA_V5_EVENT_MISSING")
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkctlError("SCHEMA_V5_EVENT_INVALID") from exc
        if not isinstance(item, dict) or item.get("plan_id") != plan_id:
            raise WorkctlError("SCHEMA_V5_EVENT_INVALID")
        events.append(cast(dict[str, Any], item))
    return events


def canonical_event_payload_bytes(event: Mapping[str, Any]) -> bytes:
    """Return canonical bytes for one runtime event."""
    if canonical_event_bytes is None:
        raise WorkctlError("STORAGE_MODULE_UNAVAILABLE: canonical_event_bytes")
    return canonical_event_bytes(event)


def redacted_runtime_copy(value: Any) -> Any:
    """Return the storage-module redacted projection used in runtime payloads."""
    if redacted_copy is None:
        raise WorkctlError("STORAGE_MODULE_UNAVAILABLE: redacted_copy")
    return redacted_copy(value)


def v5_append_event(root: Path, plan_id: str, event: Mapping[str, Any]) -> None:
    """Append one canonical event and fsync the event ledger."""
    path = v5_event_path(root, plan_id)
    ensure_directory_durable(path.parent)
    encoded = canonical_event_payload_bytes(event)
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(path.parent)


def v5_persist_state_transition(
    root: Path,
    frontmatter: Mapping[str, Any],
    state: dict[str, Any],
    *,
    event: str,
    subject: str,
    payload: Mapping[str, Any],
) -> None:
    """Persist state before event, then complete the event with recoverable intent."""
    plan_id = str(frontmatter["plan_id"])
    next_event_sequence = int(state["event_sequence"]) + 1
    next_state_sequence = int(state["state_sequence"]) + 1
    event_payload = {
        "schema_version": 1,
        "kind": "work-governance-plan-event",
        "plan_id": plan_id,
        "event_sequence": next_event_sequence,
        "state_sequence": next_state_sequence,
        "event": event,
        "subject": subject,
        "payload": redacted_runtime_copy(dict(payload)),
        "recorded_at": utc_now(),
    }
    state["state_sequence"] = next_state_sequence
    state["event_sequence"] = next_event_sequence
    state["updated_at"] = utc_now()
    state["pending_event"] = event_payload
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")
    if os.environ.get("WORKCTL_TEST_V5_INTERRUPT_AFTER_STATE") == "1":
        raise WorkctlError("SCHEMA_V5_TEST_INTERRUPTED_AFTER_STATE")
    v5_append_event(root, plan_id, event_payload)
    state.pop("pending_event", None)
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")


def v5_recover_pending_event(root: Path, frontmatter: Mapping[str, Any]) -> None:
    """Finish a state-first transition left by a process interruption."""
    plan_id = str(frontmatter["plan_id"])
    state = load_v5_state(root, frontmatter)
    pending = state.get("pending_event")
    if not isinstance(pending, dict):
        return
    payload = pending.get("payload")
    contract_sha256 = payload.get("contract_sha256") if isinstance(payload, dict) else None
    if isinstance(contract_sha256, str):
        plan_path = active_plan_path(root)
        if plan_path.is_symlink() or not plan_path.is_file():
            raise WorkctlError("SCHEMA_V5_PENDING_CONTRACT_INVALID")
        if sha256_file(plan_path) != contract_sha256:
            state["event_sequence"] = int(state["event_sequence"]) - 1
            state.pop("pending_event", None)
            write_atomic(
                v5_state_path(root, plan_id),
                json.dumps(state, indent=2, sort_keys=True) + "\n",
            )
            return
    events = v5_read_events(root, plan_id)
    if not events or events[-1] != pending:
        v5_append_event(root, plan_id, pending)
    state.pop("pending_event", None)
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")


def v5_persist_contract_transition(
    root: Path,
    doc: PlanDocument,
    *,
    event: str,
    subject: str,
    payload: Mapping[str, Any],
) -> None:
    """Atomically replace a v5 contract with a recoverable ledger event intent."""
    plan_id = str(doc.frontmatter["plan_id"])
    state = load_v5_state(root, doc.frontmatter)
    target_bytes = dump_plan(doc).encode("utf-8")
    contract_sha256 = sha256_bytes(target_bytes)
    next_event_sequence = int(state["event_sequence"]) + 1
    event_payload = {
        "schema_version": 1,
        "kind": "work-governance-plan-event",
        "plan_id": plan_id,
        "event_sequence": next_event_sequence,
        "state_sequence": int(state["state_sequence"]),
        "event": event,
        "subject": subject,
        "payload": {
            **cast(dict[str, Any], redacted_runtime_copy(dict(payload))),
            "contract_revision": doc.frontmatter["contract_revision"],
            "contract_sha256": contract_sha256,
        },
        "recorded_at": utc_now(),
    }
    state["event_sequence"] = next_event_sequence
    state["updated_at"] = utc_now()
    state["pending_event"] = event_payload
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")
    if os.environ.get("WORKCTL_TEST_V5_CONTRACT_INTERRUPT") == "before-plan":
        raise WorkctlError("SCHEMA_V5_TEST_INTERRUPTED_BEFORE_CONTRACT")
    write_atomic_bytes(doc.path, target_bytes)
    if os.environ.get("WORKCTL_TEST_V5_CONTRACT_INTERRUPT") == "after-plan":
        raise WorkctlError("SCHEMA_V5_TEST_INTERRUPTED_AFTER_CONTRACT")
    v5_append_event(root, plan_id, event_payload)
    state.pop("pending_event", None)
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")


def scheduler_task_projections(frontmatter: Mapping[str, Any]) -> list[Any]:
    """Convert Plan task mappings to the scheduler module's typed projections."""
    if TaskProjection is None:
        raise WorkctlError("SCHEDULER_MODULE_UNAVAILABLE: TaskProjection")
    raw_tasks = frontmatter.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return []
    projections: list[Any] = []
    for task in raw_tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(dependency, str) for dependency in dependencies
        ):
            dependencies = []
        projections.append(
            TaskProjection(
                task_id=task["id"],
                status=str(task.get("status", "pending")),
                dependencies=tuple(dependencies),
            )
        )
    return projections


def ready_task_targets(
    frontmatter: Mapping[str, Any],
    priorities: Mapping[str, int] | None = None,
) -> list[str]:
    """Return every pending task whose hard dependencies are verified."""
    if MODULE_READY_TASK_TARGETS is None:
        raise WorkctlError("SCHEDULER_MODULE_UNAVAILABLE: ready_task_targets")
    return MODULE_READY_TASK_TARGETS(
        scheduler_task_projections(frontmatter),
        priorities,
    )


def blocked_task_targets(frontmatter: Mapping[str, Any]) -> list[str]:
    """Return explicitly blocked tasks without treating dependency waits as failures."""
    if MODULE_BLOCKED_TASK_TARGETS is None:
        raise WorkctlError("SCHEDULER_MODULE_UNAVAILABLE: blocked_task_targets")
    return MODULE_BLOCKED_TASK_TARGETS(scheduler_task_projections(frontmatter))


def downstream_task_targets(
    task_id: str,
    task_map: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Return non-terminal tasks that transitively depend on one blocked task."""
    if module_downstream_task_targets is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: downstream_task_targets")
    return module_downstream_task_targets(task_id, task_map, VERIFIED_TASK_STATES)


def task_artifact_blockers(
    frontmatter: Mapping[str, Any],
    task: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Project artifact blockers with the same recovery exception as task advancement."""
    if module_task_artifact_blockers is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: task_artifact_blockers")
    return module_task_artifact_blockers(frontmatter, task, BLOCKING_ARTIFACT_STATES)


def task_confirmation_blocker(
    frontmatter: Mapping[str, Any],
    task: Mapping[str, Any],
) -> dict[str, str] | None:
    """Return the pending task gate that blocks a normal start/verify path."""
    if module_task_confirmation_blocker is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: task_confirmation_blocker")
    return module_task_confirmation_blocker(frontmatter, task)


def task_blocking_details(
    root: Path,
    frontmatter: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Explain every task that cannot currently advance and what it blocks downstream."""
    if module_task_blocking_details is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: task_blocking_details")

    def review_blockers(target: str) -> Sequence[str]:
        return independent_review_blockers(root, frontmatter, target)

    return cast(
        list[dict[str, Any]],
        module_task_blocking_details(
            frontmatter,
            independent_review_blockers=review_blockers,
            blocking_artifact_states=BLOCKING_ARTIFACT_STATES,
            verified_task_states=VERIFIED_TASK_STATES,
        ),
    )


def pending_confirmation_ids(frontmatter: Mapping[str, Any]) -> list[str]:
    """Return pending confirmation IDs in stable Plan order."""
    if module_pending_confirmation_ids is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: pending_confirmation_ids")
    return module_pending_confirmation_ids(frontmatter)


def legacy_refresh_projection(
    root: Path,
    frontmatter: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Project archive-backed refresh guidance for a rebuilt current-schema Plan."""
    if module_legacy_refresh_projection is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: legacy_refresh_projection")

    def archive_status(archive_path: str, expected_sha256: object) -> Mapping[str, object]:
        try:
            archive_file = checked_project_path(root, archive_path)
            reject_symlink_components(root, archive_file)
            if not archive_file.is_file():
                return {"archive_status": "missing"}
            actual_sha256 = sha256_file(archive_file)
            if isinstance(expected_sha256, str) and expected_sha256 != actual_sha256:
                return {
                    "archive_status": "sha256_mismatch",
                    "actual_archive_sha256": actual_sha256,
                }
            payload: dict[str, object] = {"archive_status": "readable"}
            if callable(legacy_plan_summary):
                payload["legacy_summary"] = legacy_plan_summary(
                    load_plan(archive_file).frontmatter
                )
            return payload
        except WorkctlError as exc:
            return {"archive_status": "unreadable", "archive_error": str(exc)}

    return cast(
        dict[str, Any] | None,
        module_legacy_refresh_projection(
            frontmatter,
            archive_status_projection=archive_status,
        ),
    )


def current_schema_refresh_status(
    root: Path,
    frontmatter: Mapping[str, Any],
    report: AuthorityReport,
    *,
    full: bool,
) -> dict[str, Any]:
    """Build a status view for an outdated active Plan without scheduling tasks."""
    if module_current_schema_refresh_status is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: current_schema_refresh_status")
    if not callable(migration_projection):
        raise WorkctlError("MIGRATION_MODULE_UNAVAILABLE: migration_projection")

    def refresh_projection(document: Mapping[str, object]) -> Mapping[str, object]:
        return migration_projection(cast(Mapping[str, Any], document))

    def current_contract_state(document: Mapping[str, object]) -> str:
        return contract_state(dict(document))

    return cast(
        dict[str, Any],
        module_current_schema_refresh_status(
            frontmatter,
            authority_state=report.state,
            blocking_reasons=report.blockers,
            current_schema_version=CURRENT_PLAN_SCHEMA_VERSION,
            migration_projection=refresh_projection,
            contract_state=current_contract_state,
            full=full,
            authority_candidates=(
                [candidate_to_dict(item) for item in report.candidates] if full else ()
            ),
            allowed_commands=report.allowed_commands if full else (),
        ),
    )


def compact_plan_status(
    root: Path,
    frontmatter: Mapping[str, Any],
    *,
    scheduler: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the bounded default status view without revision history."""
    if module_compact_plan_status is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: compact_plan_status")

    def ready_targets(
        document: Mapping[str, object],
        priorities: Mapping[str, int],
    ) -> Sequence[str]:
        return ready_task_targets(cast(Mapping[str, Any], document), priorities)

    def blocking_details(document: Mapping[str, object]) -> Sequence[Mapping[str, object]]:
        return task_blocking_details(root, cast(Mapping[str, Any], document))

    def confirmations(document: Mapping[str, object]) -> Sequence[str]:
        return pending_confirmation_ids(cast(Mapping[str, Any], document))

    def refresh_projection(document: Mapping[str, object]) -> Mapping[str, object] | None:
        return legacy_refresh_projection(root, cast(Mapping[str, Any], document))

    return cast(
        dict[str, Any],
        module_compact_plan_status(
            frontmatter,
            scheduler=scheduler,
            ready_task_targets=ready_targets,
            task_blocking_details=blocking_details,
            pending_confirmation_ids=confirmations,
            legacy_refresh_projection=refresh_projection,
        ),
    )


def user_intervention_projection(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Describe only the user-owned input that blocks the current advancement target."""
    if module_user_intervention_projection is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: user_intervention_projection")
    return cast(
        dict[str, Any],
        module_user_intervention_projection(
            frontmatter,
            current_targets=current_advancement_targets(frontmatter),
        ),
    )


def require_confirmation(frontmatter: dict[str, Any], confirmation_id: str | None) -> None:
    if not confirmation_id:
        return
    item = confirmations(frontmatter).get(confirmation_id)
    if not item or item.get("status") != "accepted" or not item.get("ref"):
        raise WorkctlError(f"CONFIRMATION_REQUIRED: {confirmation_id}")


def require_task_confirmation(
    frontmatter: dict[str, Any],
    task: dict[str, Any],
    target_status: str,
) -> None:
    """Enforce accepted execution or declined skip decisions for gated tasks."""
    confirmation_id = task.get("requires_confirmation")
    if not isinstance(confirmation_id, str):
        return
    item = confirmations(frontmatter).get(confirmation_id)
    if target_status == "skipped":
        if item and item.get("status") in {"accepted", "declined"} and item.get("ref"):
            return
    elif item and item.get("status") == "accepted" and item.get("ref"):
        return
    raise WorkctlError(f"CONFIRMATION_REQUIRED: {confirmation_id}")


def confirmation_resolved_for_closeout(
    frontmatter: dict[str, Any],
    item: dict[str, Any],
) -> bool:
    """Return whether a required decision is consistently resolved."""
    status = item.get("status")
    if status == "accepted":
        return bool(item.get("ref"))
    if status != "declined" or not item.get("ref"):
        return False
    confirmation_id = item.get("id")
    for task in frontmatter.get("tasks", []):
        if (
            isinstance(task, dict)
            and task.get("requires_confirmation") == confirmation_id
            and task.get("status") != "skipped"
        ):
            return False
    scope = frontmatter.get("scope", {})
    exclusions = scope.get("exclude", []) if isinstance(scope, dict) else []
    for exclusion in exclusions if isinstance(exclusions, list) else []:
        if (
            isinstance(exclusion, dict)
            and exclusion.get("confirmation_id") == confirmation_id
            and exclusion.get("disposition") == "pending_confirmation"
        ):
            return False
    activation = frontmatter.get("activation", {})
    if isinstance(activation, dict) and activation.get("confirmation_id") == confirmation_id:
        return activation.get("status") == "declined"
    return True


def tasks_by_id(frontmatter: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in frontmatter.get("tasks", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            result[item["id"]] = item
    return result


def entries_by_id(frontmatter: dict[str, Any], field: str) -> dict[str, dict[str, Any]]:
    """Index one structured Plan collection by entry ID."""
    result: dict[str, dict[str, Any]] = {}
    values = frontmatter.get(field, [])
    if not isinstance(values, list):
        return result
    for item in values:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            result[item["id"]] = item
    return result


def task_for(frontmatter: dict[str, Any], task_id: str) -> dict[str, Any]:
    task = tasks_by_id(frontmatter).get(task_id)
    if task is None:
        raise WorkctlError(f"UNKNOWN_TASK: {task_id}")
    return task


def set_v5_task_status(args: argparse.Namespace, status: str, doc: PlanDocument) -> None:
    """Transition one v5 task in runtime state without rewriting the contract."""
    root = project_root()
    plan_id = str(doc.frontmatter["plan_id"])
    expected = args.expected_state_sequence
    if expected is None:
        raise WorkctlError("EXPECTED_STATE_SEQUENCE_REQUIRED")
    v5_recover_pending_event(root, doc.frontmatter)
    state = load_v5_state(root, doc.frontmatter)
    if state["state_sequence"] != expected:
        raise WorkctlError(
            f"STATE_SEQUENCE_MISMATCH: expected {expected}, found {state['state_sequence']}"
        )
    task = task_for(doc.frontmatter, args.task_id)
    state_task = state["tasks"].get(args.task_id)
    if not isinstance(state_task, dict):
        raise WorkctlError("SCHEMA_V5_STATE_TASK_MISSING")
    runtime = v5_runtime_frontmatter(root, doc.frontmatter, state)
    runtime_task = task_for(runtime, args.task_id)
    current_status = str(state_task.get("status"))
    allowed = TASK_TRANSITIONS.get(current_status, set())
    if status not in allowed:
        raise WorkctlError(f"INVALID_TASK_TRANSITION: {args.task_id} {current_status} -> {status}")
    if status != "blocked":
        require_no_blocking_artifacts(doc.frontmatter, task)
    if status in {"in_progress", "verified", "skipped"}:
        require_dependencies_verified(runtime, runtime_task)
        require_independent_target(
            root,
            doc.frontmatter,
            f"task:{args.task_id}",
        )
        require_task_confirmation(doc.frontmatter, task, status)
    evidence_ref: str | None = None
    evidence_sha256: str | None = None
    payload = evidence_payload_from_args(args)
    if status == "verified":
        if payload is None:
            raise WorkctlError("EVIDENCE_MANIFEST_REQUIRED")
        payload = v5_redact_evidence_payload(payload)
        evidence_ref, evidence_sha256 = record_evidence_payload(
            root,
            plan_id=plan_id,
            payload=payload,
            expected_subject=f"task:{args.task_id}",
        )
    state_task["status"] = status
    if args.note:
        state_task["note"] = redacted_runtime_copy(args.note)
    if evidence_ref is not None and evidence_sha256 is not None:
        state_task["evidence_ref"] = evidence_ref
        state_task["evidence_sha256"] = evidence_sha256
        state_task["verified_at"] = utc_now()
    state["current_task"] = f"task:{args.task_id}" if status == "in_progress" else None
    v5_persist_state_transition(
        root,
        doc.frontmatter,
        state,
        event=f"task.{status}",
        subject=f"task:{args.task_id}",
        payload={
            "status": status,
            "evidence_ref": evidence_ref,
            "evidence_sha256": evidence_sha256,
            "note": args.note,
        },
    )
    print(f"TASK_UPDATED {args.task_id} {status} state_sequence={state['state_sequence']}")


def require_dependencies_verified(frontmatter: dict[str, Any], task: dict[str, Any]) -> None:
    all_tasks = tasks_by_id(frontmatter)
    for dep_id in task.get("depends_on", []) or []:
        dep = all_tasks.get(dep_id)
        if dep is None:
            raise WorkctlError(f"UNKNOWN_DEPENDENCY: {dep_id}")
        if dep.get("status") not in VERIFIED_TASK_STATES:
            raise WorkctlError(f"DEPENDENCY_NOT_VERIFIED: {dep_id}")


def set_task_status(args: argparse.Namespace, status: str) -> None:
    root = project_root()
    if status != "verified" and (
        getattr(args, "evidence_stdin", False)
        or getattr(args, "evidence_manifest", None) is not None
    ):
        raise WorkctlError("TASK_EVIDENCE_ONLY_ALLOWED_FOR_VERIFY")
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        if doc.frontmatter.get("schema_version") == 5:
            set_v5_task_status(args, status, doc)
            return
        evidence_payload = evidence_payload_from_args(args) if status == "verified" else None
        if args.expected_revision is None:
            raise WorkctlError("EXPECTED_REVISION_REQUIRED")
        require_expected_revision(doc.frontmatter, args.expected_revision)
        task = task_for(doc.frontmatter, args.task_id)
        if status != "blocked":
            require_current_intake(
                root,
                doc.frontmatter,
                turn_receipt_sha256=args.turn_receipt_sha256,
                expected_intake_sha256=args.expected_intake_sha256,
                targets=[f"task:{args.task_id}"],
            )
            require_no_blocking_artifacts(doc.frontmatter, task)
        current_status = task.get("status")
        allowed = TASK_TRANSITIONS.get(str(current_status), set())
        if status not in allowed:
            raise WorkctlError(
                f"INVALID_TASK_TRANSITION: {args.task_id} {current_status} -> {status}"
            )
        if status in {"in_progress", "verified", "skipped"}:
            require_dependencies_verified(doc.frontmatter, task)
            require_independent_target(
                root,
                doc.frontmatter,
                f"task:{args.task_id}",
            )
            require_task_confirmation(doc.frontmatter, task, status)
        evidence_ref: str | None = None
        evidence_sha256: str | None = None
        if status == "verified":
            if evidence_payload is not None:
                evidence_ref, evidence_sha256 = record_evidence_payload(
                    root,
                    plan_id=str(doc.frontmatter["plan_id"]),
                    payload=evidence_payload,
                    expected_subject=f"task:{args.task_id}",
                )
            elif isinstance(getattr(args, "evidence_manifest", None), str):
                evidence_ref, evidence_sha256 = verify_evidence_manifest(
                    root,
                    args.evidence_manifest,
                    plan_id=str(doc.frontmatter["plan_id"]),
                    subject=f"task:{args.task_id}",
                )
        task["status"] = status
        if args.note:
            task["note"] = args.note
        if evidence_ref is not None and evidence_sha256 is not None:
            task["evidence_ref"] = evidence_ref
            task["evidence_sha256"] = evidence_sha256
            task["verified_at"] = utc_now()
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"TASK_UPDATED {args.task_id} {status} revision={doc.frontmatter['revision']}")


def retirement_metadata_errors(frontmatter: dict[str, Any]) -> list[str]:
    """Validate the immutable retirement record on a retired Plan."""
    status = frontmatter.get("status")
    retirement = frontmatter.get("retirement")
    if status != "retired":
        return [] if retirement is None else ["only a retired Plan may carry retirement metadata"]
    if not isinstance(retirement, dict):
        return ["retired Plan requires retirement metadata"]
    errors: list[str] = []
    retirement_id = retirement.get("retirement_id")
    if not isinstance(retirement_id, str) or RETIREMENT_ID_RE.fullmatch(retirement_id) is None:
        errors.append("retirement.retirement_id must match RET-YYYYMMDD-NNN")
    if not isinstance(retirement.get("reason"), str) or not retirement.get("reason"):
        errors.append("retirement.reason is required")
    for field in ("proposal_sha256", "original_sha256"):
        value = retirement.get(field)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            errors.append(f"retirement.{field} must be a SHA256 digest")
    original_path = retirement.get("original_path")
    if not isinstance(original_path, str) or not original_path:
        errors.append("retirement.original_path is required")
    confirmation = retirement.get("confirmation")
    if not isinstance(confirmation, dict):
        errors.append("retirement.confirmation must be a mapping")
    else:
        if confirmation.get("id") != "C-PLAN-RETIREMENT":
            errors.append("retirement confirmation must be C-PLAN-RETIREMENT")
        if not valid_reference(confirmation.get("ref")):
            errors.append("retirement confirmation ref must be typed")
        evidence_sha256 = confirmation.get("evidence_sha256")
        if not isinstance(evidence_sha256, str) or SHA256_RE.fullmatch(evidence_sha256) is None:
            errors.append("retirement confirmation evidence_sha256 is required")
    if not isinstance(retirement.get("dispositions"), dict):
        errors.append("retirement.dispositions must be a mapping")
    return errors


def independent_validation_errors(frontmatter: Mapping[str, Any]) -> list[str]:
    """Validate the optional Plan-level independent-review contract."""
    contract = frontmatter.get("independent_validation")
    if contract is None:
        return []
    if not isinstance(contract, dict):
        return ["independent_validation must be a mapping"]
    errors: list[str] = []
    required = contract.get("required")
    if type(required) is not bool:
        errors.append("independent_validation.required must be boolean")
    if contract.get("state") not in INDEPENDENT_REVIEW_STATES:
        errors.append("independent_validation.state must be pending, verified, or degraded")
    required_modes = contract.get("required_modes")
    if (
        not isinstance(required_modes, list)
        or not all(mode in INDEPENDENT_REVIEW_MODES for mode in required_modes)
        or len(required_modes) != len(set(required_modes))
    ):
        errors.append("independent_validation.required_modes must be unique supported modes")
    elif required and set(required_modes) != INDEPENDENT_REVIEW_MODES:
        errors.append("required independent_validation must include all review modes")
    if not valid_reference(contract.get("implementation_context_ref")):
        errors.append("independent_validation.implementation_context_ref must be typed")
    reviews = contract.get("reviews")
    seen_modes: set[str] = set()
    if not isinstance(reviews, list):
        return [*errors, "independent_validation.reviews must be a list"]
    for index, review in enumerate(reviews):
        prefix = f"independent_validation.reviews[{index}]"
        if not isinstance(review, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        mode = review.get("mode")
        if mode not in INDEPENDENT_REVIEW_MODES:
            errors.append(f"{prefix}.mode must be supported")
        elif mode in seen_modes:
            errors.append(f"duplicate independent review mode {mode}")
        else:
            seen_modes.add(str(mode))
        state = review.get("state")
        if state not in INDEPENDENT_REVIEW_STATES:
            errors.append(f"{prefix}.state must be pending, verified, or degraded")
        blocks = review.get("blocks")
        if (
            not isinstance(blocks, list)
            or not blocks
            or not all(valid_target_ref(target) for target in blocks)
            or len(blocks) != len(set(blocks))
        ):
            errors.append(f"{prefix}.blocks must be unique non-empty target refs")
        else:
            for target in blocks:
                try:
                    require_target_exists(frontmatter, target)
                except WorkctlError:
                    errors.append(f"{prefix}.blocks names unknown {target}")
        if not valid_reference(review.get("review_context_ref")):
            errors.append(f"{prefix}.review_context_ref must be typed")
        contract_ref = review.get("reviewed_contract_ref")
        contract_sha = review.get("reviewed_contract_sha256")
        if state == "pending":
            if contract_ref is not None and not valid_reference(contract_ref):
                errors.append(f"{prefix}.reviewed_contract_ref must be null or typed")
            if contract_sha is not None and (
                not isinstance(contract_sha, str) or SHA256_RE.fullmatch(contract_sha) is None
            ):
                errors.append(f"{prefix}.reviewed_contract_sha256 must be null or SHA256")
        else:
            if not valid_reference(contract_ref):
                errors.append(f"{prefix}.reviewed_contract_ref is required")
            if not isinstance(contract_sha, str) or SHA256_RE.fullmatch(contract_sha) is None:
                errors.append(f"{prefix}.reviewed_contract_sha256 is required")
        reviewed_artifacts = review.get("reviewed_artifacts")
        if not isinstance(reviewed_artifacts, list):
            errors.append(f"{prefix}.reviewed_artifacts must be a list")
        else:
            if state in {"verified", "degraded"} and not reviewed_artifacts:
                errors.append(f"{prefix}.reviewed_artifacts is required")
            for artifact in reviewed_artifacts:
                if (
                    not isinstance(artifact, dict)
                    or set(artifact) != {"ref", "sha256"}
                    or not valid_reference(artifact.get("ref"))
                    or not isinstance(artifact.get("sha256"), str)
                    or SHA256_RE.fullmatch(str(artifact.get("sha256"))) is None
                ):
                    errors.append(f"{prefix}.reviewed_artifacts entries must bind ref and SHA256")
        findings = review.get("findings")
        if not isinstance(findings, list):
            errors.append(f"{prefix}.findings must be a list")
        else:
            finding_ids: set[str] = set()
            for finding in findings:
                if not isinstance(finding, dict):
                    errors.append(f"{prefix}.findings entries must be mappings")
                    continue
                finding_id = finding.get("id")
                if not isinstance(finding_id, str) or not finding_id:
                    errors.append(f"{prefix}.findings requires ids")
                elif finding_id in finding_ids:
                    errors.append(f"{prefix}.findings duplicate id {finding_id}")
                else:
                    finding_ids.add(finding_id)
                if finding.get("severity") not in INDEPENDENT_FINDING_SEVERITIES:
                    errors.append(f"{prefix}.findings severity must be supported")
                if finding.get("status") not in INDEPENDENT_FINDING_STATES:
                    errors.append(f"{prefix}.findings status must be open or resolved")
                if not isinstance(finding.get("description"), str) or not finding.get(
                    "description"
                ):
                    errors.append(f"{prefix}.findings description is required")
                evidence_ref = finding.get("evidence_ref")
                if evidence_ref is not None and not valid_reference(evidence_ref):
                    errors.append(f"{prefix}.findings evidence_ref must be typed")
        if not valid_reference(review.get("evidence_ref")):
            errors.append(f"{prefix}.evidence_ref must be typed")
        evidence_sha = review.get("evidence_sha256")
        if state == "pending":
            if evidence_sha is not None and (
                not isinstance(evidence_sha, str) or SHA256_RE.fullmatch(evidence_sha) is None
            ):
                errors.append(f"{prefix}.evidence_sha256 must be null or SHA256")
        elif not isinstance(evidence_sha, str) or SHA256_RE.fullmatch(evidence_sha) is None:
            errors.append(f"{prefix}.evidence_sha256 is required")
        isolation_ref = review.get("isolation_attestation_ref")
        isolation_sha = review.get("isolation_attestation_sha256")
        if state == "verified":
            errors.append(
                f"{prefix}.verified requires an authenticated platform attestor that is unavailable"
            )
        elif isolation_ref is not None or isolation_sha is not None:
            errors.append(f"{prefix}.isolation attestation is valid only for verified state")
        risk_confirmation = review.get("risk_acceptance_confirmation_id")
        if state == "degraded":
            if not isinstance(risk_confirmation, str) or not risk_confirmation.startswith("C-"):
                errors.append(
                    f"{prefix}.risk_acceptance_confirmation_id is required for degraded state"
                )
        elif risk_confirmation is not None:
            errors.append(
                f"{prefix}.risk_acceptance_confirmation_id is valid only for degraded state"
            )
        bootstrap = review.get("bootstrap_release")
        if bootstrap is not None:
            if not isinstance(bootstrap, dict):
                errors.append(f"{prefix}.bootstrap_release must be a mapping")
            else:
                if not valid_reference(bootstrap.get("controller_build")):
                    errors.append(f"{prefix}.bootstrap_release.controller_build must be typed")
                for field in ("evidence_mapping", "releases"):
                    values = bootstrap.get(field)
                    if (
                        not isinstance(values, list)
                        or not values
                        or not all(valid_target_ref(target) for target in values)
                        or len(values) != len(set(values))
                    ):
                        errors.append(
                            f"{prefix}.bootstrap_release.{field} must be unique target refs"
                        )
                    else:
                        for target in values:
                            try:
                                require_target_exists(frontmatter, target)
                            except WorkctlError:
                                errors.append(
                                    f"{prefix}.bootstrap_release.{field} names unknown {target}"
                                )
                releases = bootstrap.get("releases", [])
                if (
                    isinstance(releases, list)
                    and isinstance(blocks, list)
                    and not set(releases).issubset(blocks)
                ):
                    errors.append(f"{prefix}.bootstrap_release.releases must be blocked targets")
    if isinstance(required_modes, list) and set(required_modes) != seen_modes:
        errors.append("independent_validation reviews must exactly match required_modes")
    if contract.get("state") != aggregate_independent_review_state(contract):
        errors.append("independent_validation.state must match required review states")
    return errors


def validate_v5_frontmatter(
    frontmatter: dict[str, Any],
    *,
    reject_blocking_artifacts: bool,
) -> list[str]:
    """Validate the durable v5 contract without requiring legacy runtime fields."""
    errors: list[str] = []
    plan_id = frontmatter.get("plan_id")
    if not isinstance(plan_id, str) or PLAN_ID_RE.fullmatch(plan_id) is None:
        errors.append("plan_id must match PLAN-YYYYMMDD-NNN")
    if not isinstance(frontmatter.get("title"), str) or not frontmatter.get("title"):
        errors.append("title must be a non-empty string")
    if frontmatter.get("status") not in PLAN_STATES:
        errors.append("status must be a supported Plan state")
    if (
        type(frontmatter.get("contract_revision")) is not int
        or frontmatter["contract_revision"] < 1
    ):
        errors.append("contract_revision must be a positive integer")
    if "revision" in frontmatter:
        if type(frontmatter.get("revision")) is not int or frontmatter["revision"] < 1:
            errors.append("revision must be a positive integer compatibility value")
        elif frontmatter["revision"] != frontmatter.get("contract_revision"):
            errors.append("revision must equal contract_revision for schema_version 5")
    if "revision_history" in frontmatter:
        errors.append("revision_history must be stored in the v5 event ledger")
    for field in ("state_ref", "event_ref", "evidence_store_ref"):
        if field in frontmatter and not valid_reference(frontmatter.get(field)):
            errors.append(f"{field} must be a typed reference")
    truth_refs = frontmatter.get("truth_refs", [])
    if not isinstance(truth_refs, list) or not all(valid_reference(item) for item in truth_refs):
        errors.append("truth_refs must be a list of typed references")
    goal = frontmatter.get("goal")
    success_conditions = frontmatter.get("success_conditions")
    if isinstance(goal, dict):
        if not isinstance(goal.get("statement"), str) or not goal.get("statement"):
            errors.append("goal.statement must be a non-empty string")
        if success_conditions is None:
            success_conditions = goal.get("success_conditions")
    elif not isinstance(goal, str) or not goal:
        errors.append("goal must be a non-empty string or mapping")
    if (
        not isinstance(success_conditions, list)
        or not success_conditions
        or not all(isinstance(item, str) and item for item in success_conditions)
    ):
        errors.append("success_conditions must be a non-empty list of strings")

    raw_tasks = frontmatter.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        errors.append("tasks must be a non-empty list")
        raw_tasks = []
    task_ids: set[str] = set()
    for task in raw_tasks:
        if not isinstance(task, dict):
            errors.append("tasks entries must be mappings")
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or ENTRY_ID_PATTERNS["tasks"].fullmatch(task_id) is None:
            errors.append("tasks entries must have valid ids")
            continue
        if task_id in task_ids:
            errors.append(f"duplicate tasks id {task_id}")
        task_ids.add(task_id)
        if not isinstance(task.get("description"), str) or not task.get("description"):
            errors.append(f"{task_id} requires a description")
        if "status" in task and task.get("status") not in WORK_ITEM_STATES:
            errors.append(f"{task_id} has an unsupported status")
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(dependency, str) for dependency in dependencies
        ):
            errors.append(f"{task_id} depends_on must be a list of ids")
    for task in raw_tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        for dependency in task.get("depends_on", []) or []:
            if dependency not in task_ids:
                errors.append(f"{task['id']} depends on unknown task {dependency}")

    raw_confirmations = frontmatter.get("confirmations")
    if not isinstance(raw_confirmations, dict):
        errors.append("confirmations must be a mapping")
    else:
        seen_confirmation_ids: set[str] = set()
        for group in ("required", "accepted"):
            values = raw_confirmations.get(group, [])
            if not isinstance(values, list):
                errors.append(f"confirmations.{group} must be a list")
                continue
            for item in values:
                if not isinstance(item, dict):
                    errors.append(f"confirmations.{group} entries must be mappings")
                    continue
                confirmation_id = item.get("id")
                if not isinstance(confirmation_id, str) or not confirmation_id.startswith("C-"):
                    errors.append(f"confirmations.{group} entries must have C- ids")
                    continue
                if confirmation_id in seen_confirmation_ids:
                    errors.append(f"duplicate confirmation id {confirmation_id}")
                seen_confirmation_ids.add(confirmation_id)
                if not isinstance(item.get("description"), str) or not item.get("description"):
                    errors.append(f"{confirmation_id} requires a description")
                if item.get("status") not in CONFIRMATION_STATES:
                    errors.append(f"{confirmation_id} has an unsupported status")
                errors.extend(intervention_errors(frontmatter, item))
                if item.get("status") in {"accepted", "declined"}:
                    if not valid_reference(item.get("ref")):
                        errors.append(f"{confirmation_id} ref must be a typed authority reference")
                    timestamp = item.get("accepted_at") or item.get("decided_at")
                    if not isinstance(timestamp, str) or not timestamp:
                        errors.append(
                            f"{confirmation_id} resolved confirmation requires a timestamp"
                        )

    artifacts = frontmatter.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list when present")
    elif reject_blocking_artifacts:
        for artifact in artifacts:
            if (
                isinstance(artifact, dict)
                and artifact.get("id")
                and artifact.get("status") in BLOCKING_ARTIFACT_STATES
            ):
                errors.append(f"{artifact['id']} is {artifact.get('status')}")
    return errors


def validate_v5_runtime_bundle(root: Path, frontmatter: Mapping[str, Any]) -> list[str]:
    """Validate v5 state/event separation and task mapping without changing bytes."""
    try:
        state = load_v5_state(root, frontmatter)
    except WorkctlError as exc:
        return [str(exc)]
    errors: list[str] = []
    contract_tasks = {
        task.get("id")
        for task in frontmatter.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }
    state_tasks = set(state.get("tasks", {}))
    if state_tasks != contract_tasks:
        errors.append("schema-v5 state tasks must exactly match contract tasks")
    for event in v5_read_events(root, str(frontmatter["plan_id"])):
        if (
            type(event.get("event_sequence")) is not int
            or type(event.get("state_sequence")) is not int
            or not isinstance(event.get("event"), str)
            or not isinstance(event.get("subject"), str)
            or not isinstance(event.get("payload"), dict)
            or "api_key" in json.dumps(event, sort_keys=True).lower()
        ):
            errors.append("schema-v5 event ledger contains invalid or secret-bearing data")
            break
    return errors


def validate_frontmatter(
    frontmatter: dict[str, Any],
    *,
    reject_blocking_artifacts: bool,
) -> list[str]:
    errors: list[str] = []
    schema_version = frontmatter.get("schema_version")
    if schema_version == 5:
        return validate_v5_frontmatter(
            frontmatter,
            reject_blocking_artifacts=reject_blocking_artifacts,
        )
    if schema_version not in {1, 2, 3, 4}:
        errors.append("schema_version must be 1, 2, 3, 4, or 5")
    plan_id = frontmatter.get("plan_id")
    if not isinstance(plan_id, str) or PLAN_ID_RE.fullmatch(plan_id) is None:
        errors.append("plan_id must match PLAN-YYYYMMDD-NNN")
    revision = frontmatter.get("revision")
    if type(revision) is not int or revision < 1:
        errors.append("revision must be a positive integer")
    if frontmatter.get("status") not in PLAN_STATES:
        errors.append("status must be a supported Plan state")
    errors.extend(retirement_metadata_errors(frontmatter))
    errors.extend(independent_validation_errors(frontmatter))
    if frontmatter.get("mode") not in {"autonomous", "strict"}:
        errors.append("mode must be autonomous or strict")
    for field in ("title", "created_at", "updated_at"):
        value = frontmatter.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{field} must be a non-empty string")

    scope = frontmatter.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope must be a mapping")
    else:
        include = scope.get("include")
        if not isinstance(include, list) or not all(isinstance(value, str) for value in include):
            errors.append("scope.include must be a list of strings")
        exclude = scope.get("exclude")
        if not isinstance(exclude, list):
            errors.append("scope.exclude must be a list")
        elif schema_version in {3, 4}:
            exclusion_descriptions: set[str] = set()
            for exclusion_number, exclusion in enumerate(exclude):
                prefix = f"scope.exclude[{exclusion_number}]"
                if not isinstance(exclusion, dict):
                    errors.append(f"{prefix} must be a mapping for schema_version 3 or 4")
                    continue
                description = exclusion.get("description")
                if not isinstance(description, str) or not description:
                    errors.append(f"{prefix}.description must be a non-empty string")
                elif description in exclusion_descriptions:
                    errors.append(f"duplicate scope exclusion description {description}")
                else:
                    exclusion_descriptions.add(description)
                disposition = exclusion.get("disposition")
                if disposition not in EXCLUSION_DISPOSITIONS:
                    errors.append(f"{prefix}.disposition must be supported")
                if disposition in {
                    "not_required",
                    "forbidden",
                    "completed",
                    "transferred",
                } and not valid_reference(exclusion.get("resolution_ref")):
                    errors.append(
                        f"{prefix}.resolution_ref must be a typed reference for {disposition}"
                    )
                if disposition == "transferred" and (
                    not exclusion.get("owner") or not valid_reference(exclusion.get("handoff_ref"))
                ):
                    errors.append(
                        f"{prefix} transferred exclusion requires owner and typed handoff_ref"
                    )
                if disposition == "pending_confirmation" and not isinstance(
                    exclusion.get("confirmation_id"), str
                ):
                    errors.append(f"{prefix}.confirmation_id is required")
        elif not all(isinstance(value, str) for value in exclude):
            errors.append("scope.exclude must be a list of strings")

    confirmation_ids: set[str] = set()
    raw_confirmations = frontmatter.get("confirmations")
    if not isinstance(raw_confirmations, dict):
        errors.append("confirmations must be a mapping")
    else:
        for group in ("required", "accepted"):
            values = raw_confirmations.get(group, [])
            if not isinstance(values, list):
                errors.append(f"confirmations.{group} must be a list")
                continue
            for item in values:
                if not isinstance(item, dict):
                    errors.append(f"confirmations.{group} entries must be mappings")
                    continue
                confirmation_id = item.get("id")
                if not isinstance(confirmation_id, str) or not confirmation_id.startswith("C-"):
                    errors.append(f"confirmations.{group} entries must have C- ids")
                    continue
                if confirmation_id in confirmation_ids:
                    errors.append(f"duplicate confirmation id {confirmation_id}")
                confirmation_ids.add(confirmation_id)
                description = item.get("description")
                if not isinstance(description, str) or not description:
                    errors.append(f"{confirmation_id} requires a description")
                confirmation_status = item.get("status")
                if confirmation_status not in CONFIRMATION_STATES:
                    errors.append(f"{confirmation_id} has an unsupported status")
                errors.extend(intervention_errors(frontmatter, item))
                if confirmation_status in {"accepted", "declined"}:
                    if not item.get("ref"):
                        errors.append(f"{confirmation_id} resolved confirmation requires ref")
                    elif schema_version in {3, 4} and not valid_reference(item.get("ref")):
                        errors.append(f"{confirmation_id} ref must be a typed authority reference")
                    if schema_version in {2, 3, 4}:
                        timestamp = item.get("accepted_at") or item.get("decided_at")
                        if not isinstance(timestamp, str) or not timestamp:
                            errors.append(
                                f"{confirmation_id} resolved confirmation requires a timestamp"
                            )

    item_ids: dict[str, set[str]] = {}
    for field, pattern in ENTRY_ID_PATTERNS.items():
        values = frontmatter.get(field)
        ids: set[str] = set()
        item_ids[field] = ids
        if not isinstance(values, list):
            errors.append(f"{field} must be a list")
            continue
        allowed_states = ARTIFACT_STATES if field == "artifacts" else WORK_ITEM_STATES
        for item in values:
            if not isinstance(item, dict):
                errors.append(f"{field} entries must be mappings")
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or pattern.fullmatch(item_id) is None:
                errors.append(f"{field} entries must have valid ids")
                continue
            if item_id in ids:
                errors.append(f"duplicate {field} id {item_id}")
            ids.add(item_id)
            if field != "artifacts":
                description = item.get("description")
                if not isinstance(description, str) or not description:
                    errors.append(f"{item_id} requires a description")
            else:
                artifact_path = item.get("path")
                if not isinstance(artifact_path, str) or not artifact_path:
                    errors.append(f"{item_id} requires a non-empty path")
            if item.get("status") not in allowed_states:
                errors.append(f"{item_id} has an unsupported status")
            if (
                field == "artifacts"
                and reject_blocking_artifacts
                and item.get("status") in BLOCKING_ARTIFACT_STATES
            ):
                errors.append(f"{item_id} is {item.get('status')}")

    task_ids = item_ids["tasks"]
    raw_tasks = frontmatter.get("tasks")
    if isinstance(raw_tasks, list):
        for task in raw_tasks:
            if not isinstance(task, dict) or not isinstance(task.get("id"), str):
                continue
            dependencies = task.get("depends_on", [])
            if not isinstance(dependencies, list) or not all(
                isinstance(dependency, str) for dependency in dependencies
            ):
                errors.append(f"{task['id']} depends_on must be a list of ids")
            else:
                for dependency in dependencies:
                    if dependency not in task_ids:
                        errors.append(f"{task['id']} depends on unknown task {dependency}")
            confirmation_id = task.get("requires_confirmation")
            if confirmation_id is not None and confirmation_id not in confirmation_ids:
                errors.append(f"{task['id']} requires unknown confirmation {confirmation_id}")
            completion_scope = task.get("completion_scope", "local")
            if completion_scope not in {"local", "route"}:
                errors.append(f"{task['id']} completion_scope must be local or route")
            resolves_artifacts = task.get("resolves_artifacts", [])
            if not isinstance(resolves_artifacts, list) or not all(
                isinstance(artifact_id, str) for artifact_id in resolves_artifacts
            ):
                errors.append(f"{task['id']} resolves_artifacts must be a list of ids")
            else:
                for artifact_id in resolves_artifacts:
                    if artifact_id not in item_ids["artifacts"]:
                        errors.append(f"{task['id']} resolves unknown artifact {artifact_id}")

    if schema_version in {2, 3, 4}:
        authority = frontmatter.get("authority")
        if not isinstance(authority, dict):
            errors.append("authority must be a mapping for schema_version 2")
        else:
            if authority.get("model") != AUTHORITY_MODEL:
                errors.append(f"authority.model must be {AUTHORITY_MODEL}")
            if authority.get("state") != AUTHORITY_STATE:
                errors.append(f"authority.state must be {AUTHORITY_STATE}")
            if authority.get("canonical_plan_id") != plan_id:
                errors.append("authority.canonical_plan_id must match plan_id")
            rollover_id = authority.get("rollover_id")
            predecessor = authority.get("predecessor")
            if predecessor is None:
                if rollover_id is not None:
                    errors.append("authority.rollover_id requires authority.predecessor")
            elif not isinstance(predecessor, dict):
                errors.append("authority.predecessor must be a mapping")
            else:
                if (
                    not isinstance(rollover_id, str)
                    or ROLLOVER_ID_RE.fullmatch(rollover_id) is None
                ):
                    errors.append("authority.rollover_id must match ROL-YYYYMMDD-NNN")
                predecessor_path = predecessor.get("path")
                if (
                    not isinstance(predecessor_path, str)
                    or not predecessor_path
                    or Path(predecessor_path).is_absolute()
                    or ".." in Path(predecessor_path).parts
                ):
                    errors.append("authority.predecessor.path must be a project-relative path")
                predecessor_id = predecessor.get("plan_id")
                if (
                    not isinstance(predecessor_id, str)
                    or PLAN_ID_RE.fullmatch(predecessor_id) is None
                ):
                    errors.append("authority.predecessor.plan_id must match PLAN-YYYYMMDD-NNN")
                predecessor_revision = predecessor.get("revision")
                if type(predecessor_revision) is not int or predecessor_revision < 1:
                    errors.append("authority.predecessor.revision must be a positive integer")
                predecessor_sha256 = predecessor.get("sha256")
                if (
                    not isinstance(predecessor_sha256, str)
                    or SHA256_RE.fullmatch(predecessor_sha256) is None
                ):
                    errors.append("authority.predecessor.sha256 must be a SHA256 digest")
            migration_id = authority.get("migration_id")
            if migration_id is not None and (
                not isinstance(migration_id, str) or MIGRATION_ID_RE.fullmatch(migration_id) is None
            ):
                errors.append("authority.migration_id must match MIG-YYYYMMDD-NNN")
            sources = authority.get("sources")
            if not isinstance(sources, list):
                errors.append("authority.sources must be a list")
            else:
                for source_number, source in enumerate(sources):
                    prefix = f"authority.sources[{source_number}]"
                    if not isinstance(source, dict):
                        errors.append(f"{prefix} must be a mapping")
                        continue
                    source_path = source.get("path")
                    if (
                        not isinstance(source_path, str)
                        or not source_path
                        or Path(source_path).is_absolute()
                        or ".." in Path(source_path).parts
                    ):
                        errors.append(f"{prefix}.path must be a project-relative path")
                    if source.get("role") not in SOURCE_ROLES:
                        errors.append(f"{prefix}.role must be a supported source role")
                    source_hash = source.get("sha256")
                    if not isinstance(source_hash, str) or SHA256_RE.fullmatch(source_hash) is None:
                        errors.append(f"{prefix}.sha256 must be a SHA256 digest")
                    archive_path = source.get("archive_path")
                    if (
                        not isinstance(archive_path, str)
                        or not archive_path
                        or Path(archive_path).is_absolute()
                        or ".." in Path(archive_path).parts
                    ):
                        errors.append(f"{prefix}.archive_path must be a project-relative path")
                    classification = source.get("classification")
                    if classification is not None and classification != "CONFIRMED_AUTHORITY":
                        errors.append(f"{prefix}.classification must be CONFIRMED_AUTHORITY")
                    source_revision = source.get("revision")
                    if source_revision is not None and (
                        type(source_revision) is not int or source_revision < 1
                    ):
                        errors.append(f"{prefix}.revision must be a positive integer")
            confirmations_value = authority.get("confirmations")
            if not isinstance(confirmations_value, dict):
                errors.append("authority.confirmations must be a mapping")
            elif not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in confirmations_value.items()
            ):
                errors.append("authority.confirmations entries must map strings to strings")
            elif predecessor is not None and not isinstance(
                confirmations_value.get("rollover"), str
            ):
                errors.append("authority.confirmations.rollover is required for rollovers")
        route = frontmatter.get("route")
        if not isinstance(route, dict):
            errors.append("route must be a mapping for schema_version 2 or 3")
        else:
            allowed_route_states = (
                ROUTE_STATES if schema_version in {3, 4} else {"active", "terminal"}
            )
            if route.get("route_status") not in allowed_route_states:
                errors.append(
                    "route.route_status must be " + ", ".join(sorted(allowed_route_states))
                )
            for field in (
                "slice_status",
                "next_phase",
                "validation_standard",
                "confirmation_gate",
            ):
                if not isinstance(route.get(field), str):
                    errors.append(f"route.{field} must be a string")
            confirmation_gate = route.get("confirmation_gate")
            if (
                isinstance(confirmation_gate, str)
                and confirmation_gate not in {"", "none"}
                and confirmation_gate not in confirmation_ids
            ):
                errors.append("route.confirmation_gate must name a known confirmation")
        handoff = frontmatter.get("handoff")
        if not isinstance(handoff, dict):
            errors.append("handoff must be a mapping for schema_version 2 or 3")
        else:
            for field in ("next_step", "route_status"):
                if not isinstance(handoff.get(field), str):
                    errors.append(f"handoff.{field} must be a string")
            if isinstance(route, dict) and handoff.get("route_status") != route.get("route_status"):
                errors.append("handoff.route_status must match route.route_status")

        if schema_version in {3, 4}:
            raw_scope = frontmatter.get("scope")
            structured_exclusions = (
                raw_scope.get("exclude", []) if isinstance(raw_scope, dict) else []
            )
            if isinstance(structured_exclusions, list):
                for exclusion_number, exclusion in enumerate(structured_exclusions):
                    if not isinstance(exclusion, dict):
                        continue
                    if exclusion.get("disposition") == "pending_confirmation":
                        confirmation_id = exclusion.get("confirmation_id")
                        if confirmation_id not in confirmation_ids:
                            errors.append(
                                f"scope.exclude[{exclusion_number}].confirmation_id "
                                "must name a known confirmation"
                            )

            delivery = frontmatter.get("delivery")
            if not isinstance(delivery, dict):
                errors.append("delivery must be a mapping for schema_version 3")
            else:
                if delivery.get("status") not in DELIVERY_STATES:
                    errors.append("delivery.status must be supported")
                if not isinstance(delivery.get("boundary"), str) or not delivery.get("boundary"):
                    errors.append("delivery.boundary must be a non-empty string")
                if not valid_reference(delivery.get("evidence_ref")):
                    errors.append("delivery.evidence_ref must be a typed reference")

            activation = frontmatter.get("activation")
            if not isinstance(activation, dict):
                errors.append("activation must be a mapping for schema_version 3")
            else:
                activation_status = activation.get("status")
                if activation_status not in ACTIVATION_STATES:
                    errors.append("activation.status must be supported")
                for field in ("current_ref", "target_ref"):
                    if not isinstance(activation.get(field), str) or not activation.get(field):
                        errors.append(f"activation.{field} must be a non-empty string")
                activation_confirmation = activation.get("confirmation_id")
                resolves_exclusions = activation.get("resolves_exclusions")
                if resolves_exclusions is not None:
                    if (
                        not isinstance(resolves_exclusions, list)
                        or not resolves_exclusions
                        or not all(
                            isinstance(description, str) and description
                            for description in resolves_exclusions
                        )
                        or len(resolves_exclusions) != len(set(resolves_exclusions))
                    ):
                        errors.append(
                            "activation.resolves_exclusions must be a unique non-empty list"
                        )
                    else:
                        exclusions_by_name = {
                            str(exclusion["description"]): exclusion
                            for exclusion in structured_exclusions
                            if isinstance(exclusion, dict)
                            and isinstance(exclusion.get("description"), str)
                        }
                        activation_decision = (
                            confirmations(frontmatter).get(activation_confirmation)
                            if isinstance(activation_confirmation, str)
                            else None
                        )
                        for description in resolves_exclusions:
                            exclusion = exclusions_by_name.get(description)
                            if exclusion is None:
                                errors.append(
                                    "activation.resolves_exclusions names an unknown exclusion"
                                )
                                continue
                            if exclusion.get("confirmation_id") != activation_confirmation:
                                errors.append(
                                    "activation.resolves_exclusions confirmation mismatch"
                                )
                            if activation_status == "active":
                                if exclusion.get("disposition") != "completed":
                                    errors.append(
                                        "active activation requires bound exclusions completed"
                                    )
                                elif not isinstance(activation_decision, dict) or exclusion.get(
                                    "resolution_ref"
                                ) != activation_decision.get("ref"):
                                    errors.append(
                                        "active activation exclusion resolution_ref mismatch"
                                    )
                            elif exclusion.get("disposition") != "pending_confirmation":
                                errors.append(
                                    "inactive activation bound exclusions must remain pending"
                                )
                if activation_status in {"pending_confirmation", "in_progress"}:
                    if activation_confirmation not in confirmation_ids:
                        errors.append("activation.confirmation_id must name a known confirmation")
                    elif activation_status == "in_progress":
                        confirmation = confirmations(frontmatter).get(activation_confirmation)
                        if confirmation is None or confirmation.get("status") != "accepted":
                            errors.append(
                                "activation in_progress requires an accepted confirmation"
                            )
                if activation_status == "active":
                    if activation.get("current_ref") != activation.get("target_ref"):
                        errors.append("activation active requires current_ref to match target_ref")
                    evidence = activation.get("evidence")
                    if not isinstance(evidence, dict):
                        errors.append("activation active requires runtime evidence")
                    else:
                        if evidence.get("observed_ref") != activation.get("current_ref"):
                            errors.append("activation evidence observed_ref must match current_ref")
                        if not valid_reference(evidence.get("source_ref")):
                            errors.append(
                                "activation evidence source_ref must be a typed reference"
                            )
                        if not isinstance(evidence.get("checked_at"), str) or not evidence.get(
                            "checked_at"
                        ):
                            errors.append("activation evidence requires checked_at")
                        if (
                            not isinstance(evidence.get("sha256"), str)
                            or SHA256_RE.fullmatch(evidence["sha256"]) is None
                        ):
                            errors.append("activation evidence requires a SHA256 digest")
                    activation_confirmation = activation.get("confirmation_id")
                    if activation_confirmation is not None:
                        confirmation = confirmations(frontmatter).get(activation_confirmation)
                        if confirmation is None or confirmation.get("status") != "accepted":
                            errors.append("activation active requires its accepted confirmation")
                if activation_status in {"not_required", "declined"} and not valid_reference(
                    activation.get("decision_ref")
                ):
                    errors.append(f"activation {activation_status} requires a typed decision_ref")
                if activation_status == "declined":
                    activation_confirmation = activation.get("confirmation_id")
                    confirmation = (
                        confirmations(frontmatter).get(activation_confirmation)
                        if isinstance(activation_confirmation, str)
                        else None
                    )
                    if confirmation is None or confirmation.get("status") != "declined":
                        errors.append("activation declined requires its declined confirmation")

            if isinstance(route, dict):
                route_status = route.get("route_status")
                next_phase = route.get("next_phase")
                if route_status == "terminal" and next_phase not in {"", "none"}:
                    errors.append("terminal route requires next_phase none")
                if route_status != "terminal" and next_phase in {"", "none"}:
                    errors.append("non-terminal route requires a next_phase")
                if route_status == "awaiting_confirmation":
                    gate = route.get("confirmation_gate")
                    if gate in {"", "none"}:
                        errors.append("awaiting_confirmation route requires a confirmation gate")
                if route_status == "terminal":
                    if isinstance(delivery, dict) and delivery.get("status") != "complete":
                        errors.append("terminal route requires complete delivery")
                    if (
                        isinstance(activation, dict)
                        and activation.get("status") in BLOCKING_ACTIVATION_STATES
                    ):
                        errors.append("terminal route cannot retain unresolved activation")
                    if isinstance(structured_exclusions, list) and any(
                        isinstance(exclusion, dict)
                        and exclusion.get("disposition") in BLOCKING_EXCLUSION_DISPOSITIONS
                        for exclusion in structured_exclusions
                    ):
                        errors.append("terminal route cannot retain unresolved scope exclusions")
            if isinstance(handoff, dict):
                next_step = handoff.get("next_step")
                if handoff.get("route_status") == "terminal" and next_step not in {
                    "",
                    "none",
                }:
                    errors.append("terminal handoff requires next_step none")
                if handoff.get("route_status") != "terminal" and next_step in {
                    "",
                    "none",
                }:
                    errors.append("non-terminal handoff requires a next_step")

        if schema_version == 4:
            errors.extend(intake_contract_errors(frontmatter))
            goal = frontmatter.get("goal")
            if not isinstance(goal, dict):
                errors.append("goal must be a mapping for schema_version 4")
            else:
                if not isinstance(goal.get("statement"), str) or not goal.get("statement"):
                    errors.append("goal.statement must be a non-empty string")
                success_conditions = goal.get("success_conditions")
                if (
                    not isinstance(success_conditions, list)
                    or not success_conditions
                    or not all(isinstance(item, str) and item for item in success_conditions)
                ):
                    errors.append("goal.success_conditions must be a non-empty list of strings")

            contract = frontmatter.get("contract")
            if not isinstance(contract, dict):
                errors.append("contract must be a mapping for schema_version 4")
            else:
                contract_revision = contract.get("revision")
                if type(contract_revision) is not int or contract_revision < 1:
                    errors.append("contract.revision must be a positive integer")
                contract_confirmation = contract.get("confirmation_id")
                if contract_confirmation not in confirmation_ids:
                    errors.append("contract.confirmation_id must name a known confirmation")
                contract_ref = contract.get("confirmed_ref")
                if not valid_reference(contract_ref):
                    errors.append("contract.confirmed_ref must be a typed reference")
                confirmation = (
                    confirmations(frontmatter).get(contract_confirmation)
                    if isinstance(contract_confirmation, str)
                    else None
                )
                if (
                    confirmation is None
                    or confirmation.get("status") != "accepted"
                    or confirmation.get("ref") != contract_ref
                ):
                    errors.append("contract must match its accepted confirmation")

            unknown_ids: set[str] = set()
            unknowns = frontmatter.get("unknowns")
            if not isinstance(unknowns, list):
                errors.append("unknowns must be a list for schema_version 4")
            else:
                for item in unknowns:
                    if not isinstance(item, dict):
                        errors.append("unknowns entries must be mappings")
                        continue
                    unknown_id = item.get("id")
                    if (
                        not isinstance(unknown_id, str)
                        or UNKNOWN_ID_RE.fullmatch(unknown_id) is None
                    ):
                        errors.append("unknowns entries must have U-NNN ids")
                        continue
                    if unknown_id in unknown_ids:
                        errors.append(f"duplicate unknown id {unknown_id}")
                    unknown_ids.add(unknown_id)
                    if not isinstance(item.get("question"), str) or not item.get("question"):
                        errors.append(f"{unknown_id} requires a question")
                    if item.get("status") not in UNKNOWN_STATES:
                        errors.append(f"{unknown_id} has an unsupported status")
                    if item.get("status") == "resolved":
                        if not isinstance(item.get("resolution"), str) or not item.get(
                            "resolution"
                        ):
                            errors.append(f"{unknown_id} resolved unknown requires resolution")
                        if not valid_reference(item.get("evidence_manifest")):
                            errors.append(
                                f"{unknown_id} resolved unknown requires evidence_manifest"
                            )
                    if frontmatter.get("intake") is not None:
                        blocks = item.get("blocks")
                        if item.get("owner") not in UNKNOWN_OWNERS:
                            errors.append(f"{unknown_id} owner must be user or agent")
                        if item.get("impact") not in UNKNOWN_IMPACTS:
                            errors.append(f"{unknown_id} impact must be blocking or non_blocking")
                        if (
                            not isinstance(blocks, list)
                            or not all(valid_target_ref(target) for target in blocks)
                            or len(blocks) != len(set(cast(list[str], blocks)))
                        ):
                            errors.append(f"{unknown_id} blocks must be unique target refs")
                        elif (item.get("impact") == "blocking") != bool(blocks):
                            errors.append(f"{unknown_id} impact and blocks conflict")
                        elif isinstance(blocks, list):
                            for block in blocks:
                                try:
                                    require_target_exists(frontmatter, str(block))
                                except WorkctlError:
                                    errors.append(f"{unknown_id} blocks unknown target {block}")
                        if not isinstance(item.get("expected_evidence"), str) or not item.get(
                            "expected_evidence"
                        ):
                            errors.append(f"{unknown_id} requires expected_evidence")

            if isinstance(raw_tasks, list):
                for task in raw_tasks:
                    if not isinstance(task, dict) or not isinstance(task.get("id"), str):
                        continue
                    linked_unknowns = task.get("unknowns")
                    if not isinstance(linked_unknowns, list) or not all(
                        isinstance(item, str) for item in linked_unknowns
                    ):
                        errors.append(f"{task['id']} unknowns must be a list of ids")
                    else:
                        for unknown_id in linked_unknowns:
                            if unknown_id not in unknown_ids:
                                errors.append(f"{task['id']} links unknown unknown {unknown_id}")
                        if frontmatter.get("intake") is not None:
                            expected_unknowns = {
                                unknown_id
                                for unknown_id, unknown in unknowns_by_id(frontmatter).items()
                                if isinstance(unknown.get("blocks"), list)
                                and f"task:{task['id']}" in unknown["blocks"]
                            }
                            if (
                                len(linked_unknowns) != len(set(linked_unknowns))
                                or set(linked_unknowns) != expected_unknowns
                            ):
                                errors.append(
                                    f"{task['id']} unknowns must equal unknown.blocks projection"
                                )
                    expected_delta = task.get("expected_evidence_delta")
                    if not isinstance(expected_delta, str) or not expected_delta:
                        errors.append(
                            f"{task['id']} requires expected_evidence_delta for schema_version 4"
                        )

            raw_validations = frontmatter.get("validations")
            if isinstance(raw_validations, list):
                for validation in raw_validations:
                    if not isinstance(validation, dict) or not isinstance(
                        validation.get("id"), str
                    ):
                        continue
                    provenance = validation.get("provenance")
                    if not isinstance(provenance, dict):
                        errors.append(f"{validation['id']} requires validation provenance")
                        continue
                    if provenance.get("kind") not in VALIDATION_PROVENANCE_KINDS:
                        errors.append(f"{validation['id']} provenance.kind is unsupported")
                    if not valid_reference(provenance.get("source_ref")):
                        errors.append(f"{validation['id']} provenance.source_ref must be typed")

            history = frontmatter.get("revision_history")
            history_revisions: list[int] = []
            if not isinstance(history, list) or not history:
                errors.append("revision_history must be a non-empty list for schema_version 4")
            else:
                for record in history:
                    if not isinstance(record, dict):
                        errors.append("revision_history entries must be mappings")
                        continue
                    record_revision = record.get("revision")
                    if type(record_revision) is not int or record_revision < 1:
                        errors.append("revision_history revision must be positive")
                        continue
                    history_revisions.append(record_revision)
                    if record.get("kind") not in REVISION_KINDS:
                        errors.append(f"revision_history {record_revision} has unsupported kind")
                    if not isinstance(record.get("changed_at"), str) or not record.get(
                        "changed_at"
                    ):
                        errors.append(f"revision_history {record_revision} requires changed_at")
                    if not isinstance(record.get("rationale"), str) or not record.get("rationale"):
                        errors.append(f"revision_history {record_revision} requires rationale")
                    record_confirmation = record.get("confirmation_id")
                    if (
                        record_confirmation is not None
                        and record_confirmation not in confirmation_ids
                    ):
                        errors.append(
                            f"revision_history {record_revision} names unknown confirmation"
                        )
                    evidence_manifest = record.get("evidence_manifest")
                    if evidence_manifest is not None and not valid_reference(evidence_manifest):
                        errors.append(
                            f"revision_history {record_revision} evidence_manifest must be typed"
                        )
                    revision_basis = record.get("decision_basis_sha256")
                    if revision_basis is not None and (
                        not isinstance(revision_basis, str)
                        or SHA256_RE.fullmatch(revision_basis) is None
                    ):
                        errors.append(
                            f"revision_history {record_revision} decision basis must be SHA256"
                        )
                if history_revisions != sorted(set(history_revisions)):
                    errors.append("revision_history revisions must be unique and increasing")
                elif history_revisions and history_revisions[-1] != revision:
                    errors.append("revision_history must end at the current revision")
                latest_history = history[-1] if history else None
                if (
                    isinstance(latest_history, dict)
                    and latest_history.get("decision_basis_sha256") is not None
                    and latest_history.get("decision_basis_sha256")
                    != decision_basis_sha256(frontmatter)
                ):
                    errors.append("current revision decision basis binding is stale")
            if intake_state(frontmatter) == "CURRENT_BASIS":
                latest = intake_records(frontmatter)[-1]
                try:
                    validate_intake_decision(
                        frontmatter,
                        decision=str(latest.get("decision")),
                        targets=cast(list[str], latest.get("targets", [])),
                        current_unknown_id=(
                            str(latest["current_unknown_id"])
                            if isinstance(latest.get("current_unknown_id"), str)
                            else None
                        ),
                    )
                except WorkctlError as exc:
                    errors.append(f"current intake decision invalid: {exc}")
    return errors


def validate_plan(
    root: Path,
    *,
    ignore_journal: Path | None = None,
    reject_blocking_artifacts: bool = True,
    require_governed: bool = True,
) -> list[str]:
    """Validate Plan structure and optionally require governed authority."""
    if not index_path(root).is_file():
        report = inspect_authority(root, ignore_journal=ignore_journal)
        errors: list[str] = []
        if report.state != "UNMANAGED_EMPTY":
            errors.append(f"authority state is {report.state}")
            errors.extend(report.blockers)
            return errors
        if plan_dir(root).is_dir():
            for path in sorted(plan_dir(root).glob("PLAN-*.md")):
                text = path.read_text(encoding="utf-8", errors="replace")
                if POINTER_MARKER in text:
                    continue
                try:
                    historical = load_plan(path)
                except WorkctlError as exc:
                    errors.append(str(exc))
                    continue
                if historical.frontmatter.get("status") not in {"complete", "retired"}:
                    errors.append(
                        f"unindexed Plan must be complete or retired: "
                        f"{relative_project_path(root, path)}"
                    )
                errors.extend(
                    f"{relative_project_path(root, path)}: {error}"
                    for error in validate_frontmatter(
                        historical.frontmatter,
                        reject_blocking_artifacts=False,
                    )
                )
                if not historical.body.strip():
                    errors.append(
                        f"{relative_project_path(root, path)}: Plan body must not be empty"
                    )
        return errors
    try:
        index = load_yaml_file(index_path(root))
        doc = load_plan(active_plan_path(root))
    except WorkctlError as exc:
        return [str(exc)]
    errors = validate_frontmatter(
        doc.frontmatter,
        reject_blocking_artifacts=reject_blocking_artifacts,
    )
    if doc.frontmatter.get("schema_version") == 5:
        errors.extend(validate_v5_runtime_bundle(root, doc.frontmatter))
    if index.get("schema_version") != 1:
        errors.append("index schema_version must be 1")
    if index.get("active_plan_id") != doc.frontmatter.get("plan_id"):
        errors.append("index active_plan_id must match active Plan")
    if not doc.body.strip():
        errors.append("Plan body must not be empty")
    plans = index.get("plans")
    if not isinstance(plans, list):
        errors.append("index plans must be a list")
        return errors
    index_item = next(
        (
            item
            for item in plans
            if isinstance(item, dict) and item.get("id") == doc.frontmatter.get("plan_id")
        ),
        None,
    )
    if index_item is None:
        errors.append("active plan must be listed in index")
    else:
        if index_item.get("path") != doc.path.name:
            errors.append("index path must match active Plan file")
        if {"status", "updated_at"} & set(index_item):
            errors.append("index must not duplicate mutable Plan fields")
    if require_governed:
        report = inspect_authority(root, ignore_journal=ignore_journal)
        if report.state != "GOVERNED_ACTIVE":
            errors.append(f"authority state is {report.state}")
            errors.extend(report.blockers)
    return errors


def layout_report_payload(root: Path, report: LayoutReport) -> dict[str, object]:
    """Build stable JSON for the layout and Plan-authority axes."""
    authority_state = "NOT_INSPECTED"
    authority_blockers: list[str] = []
    if report.state == "LAYOUT_READY":
        authority = inspect_authority(root)
        authority_state = authority.state
        authority_blockers = authority.blockers
    return {
        "layout_state": report.state,
        "layout_blocking_reasons": report.blockers,
        "legacy": {
            "classification": report.legacy.classification,
            "blocking_reasons": report.legacy.blockers,
            "active_plan_id": report.legacy.active_plan_id,
            "active_plan_path": report.legacy.active_plan_path,
            "manifest_sha256": report.legacy.manifest_sha256,
        },
        "plan_authority_state": authority_state,
        "plan_authority_blocking_reasons": authority_blockers,
        "allowed_commands": report.allowed_commands,
    }


def layout_version_payload(
    *,
    migration_status: str,
    transaction_id: str,
    legacy_manifest_sha256: str,
    new_layout_baseline_sha256: str,
    completed_at: str,
    completion_kind: str,
    completion_path: str,
    completion_sha256: str,
) -> dict[str, object]:
    """Build the exact versioned layout commitment."""
    return {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "layout_version": LAYOUT_VERSION,
        "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
        "plugin_compatibility": PLUGIN_COMPATIBILITY,
        "legacy_migration_action_revision": LEGACY_MIGRATION_ACTION_REVISION,
        "migration": {
            "status": migration_status,
            "transaction_id": transaction_id,
            "legacy_manifest_sha256": legacy_manifest_sha256,
            "new_layout_baseline_sha256": new_layout_baseline_sha256,
            "completion_evidence": {
                "kind": completion_kind,
                "path": completion_path,
                "sha256": completion_sha256,
                "completed_at": completed_at,
            },
        },
    }


def commit_not_applicable_layout(root: Path) -> None:
    """Commit layout 1 without creating a Plan when no legacy authority exists."""
    governance = governance_root(root)
    if governance.is_symlink():
        raise WorkctlError(f"LAYOUT_PATH_SYMLINK: {governance}")
    governance.mkdir(parents=True, exist_ok=True)
    ensure_layout_gitignore(root)
    completed_at = utc_now()
    receipt = {
        "action": "layout-not-applicable",
        "completed_at": completed_at,
        "legacy_classification": "NOT_APPLICABLE",
    }
    journal_digest = sha256_bytes(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    )
    baseline_digest = sha256_bytes(
        json.dumps(
            {
                "layout_version": LAYOUT_VERSION,
                "versioned_paths": [".gitignore", "version.yaml"],
                "plan_created": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    payload = layout_version_payload(
        migration_status="not_applicable",
        transaction_id="not-applicable",
        legacy_manifest_sha256=manifest_sha256([]),
        new_layout_baseline_sha256=baseline_digest,
        completed_at=completed_at,
        completion_kind="not-applicable-receipt",
        completion_path="not-applicable",
        completion_sha256=journal_digest,
    )
    write_atomic(version_path(root), yaml.safe_dump(payload, sort_keys=False))


def cmd_layout_adopt(args: argparse.Namespace) -> None:
    """Bind one reviewed legacy snapshot to the current physical worktree."""
    root = project_root()
    if not valid_reference(args.ref):
        raise WorkctlError("LEGACY_ADOPTION_REF_INVALID")
    if SHA256_RE.fullmatch(args.expected_manifest_sha256) is None:
        raise WorkctlError("LEGACY_ADOPTION_MANIFEST_INVALID")
    if PLAN_ID_RE.fullmatch(args.expected_active_plan_id) is None:
        raise WorkctlError("LEGACY_ADOPTION_PLAN_ID_INVALID")
    with lock(root):
        if version_path(root).is_file():
            raise WorkctlError("LEGACY_ADOPTION_NOT_REQUIRED: layout is already committed")
        control_errors = layout_control_path_errors(root)
        if control_errors:
            raise WorkctlError("LEGACY_ADOPTION_ENVIRONMENT_BLOCKED: " + "; ".join(control_errors))
        legacy = classify_legacy_layout(root, require_adoption=False)
        if legacy.classification == "NOT_APPLICABLE":
            raise WorkctlError("LEGACY_ADOPTION_NOT_REQUIRED")
        if legacy.classification != "MIGRATABLE":
            details = "; ".join(legacy.blockers)
            suffix = f": {details}" if details else ""
            raise WorkctlError(f"LEGACY_ADOPTION_BLOCKED: {legacy.classification}{suffix}")
        if (
            legacy.manifest_sha256 != args.expected_manifest_sha256
            or legacy.active_plan_id != args.expected_active_plan_id
            or legacy.active_plan_path is None
        ):
            raise WorkctlError("LEGACY_ADOPTION_EXPECTATION_DRIFT")
        ensure_layout_gitignore(root)
        receipt = legacy_adoption_path(root)
        if receipt.is_symlink() or (receipt.exists() and not receipt.is_file()):
            raise WorkctlError("LEGACY_ADOPTION_RECEIPT_CONFLICT")
        payload = {
            "schema_version": 1,
            "kind": "work-governance-legacy-adoption",
            "action_revision": LEGACY_MIGRATION_ACTION_REVISION,
            "project_root": root.resolve().as_posix(),
            "worktree_identity": git_worktree_identity(root),
            "active_plan_id": legacy.active_plan_id,
            "active_plan_path": legacy.active_plan_path,
            "legacy_manifest_sha256": legacy.manifest_sha256,
            "controller_sha256": sha256_file(Path(__file__).resolve()),
            "confirmation_ref": args.ref,
            "created_at": utc_now(),
        }
        write_atomic(receipt, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        adopted = classify_legacy_layout(root)
        if adopted.classification != "MIGRATABLE":
            raise WorkctlError(
                "LEGACY_ADOPTION_COMMITTED_BUT_INVALID: " + "; ".join(adopted.blockers)
            )
        print(
            json.dumps(
                {
                    "status": "LEGACY_ADOPTED",
                    "project_root": root.resolve().as_posix(),
                    "active_plan_id": adopted.active_plan_id,
                    "legacy_manifest_sha256": adopted.manifest_sha256,
                    "receipt": relative_project_path(root, receipt),
                    "receipt_sha256": sha256_file(receipt),
                },
                indent=2,
                sort_keys=True,
            )
        )


def cmd_layout_status(_args: argparse.Namespace) -> None:
    """Print deterministic layout and Plan-authority axes."""
    root = project_root()
    report = inspect_layout(root)
    print(json.dumps(layout_report_payload(root, report), indent=2, sort_keys=True))


def cmd_layout_validate(_args: argparse.Namespace) -> None:
    """Validate committed layout without promoting active Plan parse failures."""
    root = project_root()
    report = inspect_layout(root)
    if report.state != "LAYOUT_READY":
        details = "; ".join(report.blockers)
        suffix = f": {details}" if details else ""
        raise WorkctlError(f"LAYOUT_INVALID: {report.state}{suffix}")
    errors = layout_version_errors(root)
    if errors:
        raise WorkctlError("LAYOUT_INVALID: " + "; ".join(errors))
    print("LAYOUT_VALID")


def cmd_intake_status(args: argparse.Namespace) -> None:
    """Validate the exact session receipt before classifying Plan intake."""
    root = project_root()
    receipt = validate_current_ready_receipt(
        root,
        args.receipt_sha256,
        require_current_controller=True,
    )
    layout = inspect_layout(root)
    authority_state = "NOT_INSPECTED"
    plan_contract_state = "NO_ACTIVE_PLAN"
    plan_id: object = None
    if layout.state == "LAYOUT_READY":
        authority = inspect_authority(root)
        authority_state = authority.state
        if authority.state in {"GOVERNED_ACTIVE", "PLAN_SCHEMA_REFRESH_REQUIRED"}:
            doc = load_plan(active_plan_path(root))
            plan_contract_state = contract_state(doc.frontmatter)
            plan_id = doc.frontmatter.get("plan_id")
    intake_state = (
        "INTAKE_READY"
        if layout.state == "LAYOUT_READY"
        and authority_state in {"UNMANAGED_EMPTY", "GOVERNED_ACTIVE"}
        and plan_contract_state
        in {"NO_ACTIVE_PLAN", "PLAN_CONTRACT_READY", "PLAN_CONTRACT_LEGACY_READABLE"}
        else plan_contract_state
        if plan_contract_state == "PLAN_SCHEMA_REFRESH_REQUIRED"
        else "INTAKE_BLOCKED"
    )
    print(
        json.dumps(
            {
                "intake_state": intake_state,
                "layout_state": layout.state,
                "authority_state": authority_state,
                "contract_state": plan_contract_state,
                "plan_id": plan_id,
                "receipt_schema_version": receipt["schema_version"],
                "session_id": receipt["session_id"],
                "controller_ref": receipt["controller_ref"],
                "controller_sha256": receipt["controller_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )


def current_turn_receipt_path(root: Path, session_id: str | None = None) -> Path:
    """Return the newest turn receipt for one session or the legacy location."""
    if session_id is None:
        return runtime_dir(root) / "current-turn-receipt.json"
    return session_state_dir(root, session_id) / "current-turn-receipt.json"


def current_turn_receipt_paths(root: Path) -> list[Path]:
    """Return legacy plus all session-scoped current-turn receipt candidates."""
    return [
        current_turn_receipt_path(root),
        *scoped_session_paths(root, "current-turn-receipt.json"),
    ]


def turn_receipt_digest(payload: Mapping[str, object]) -> str:
    """Hash the canonical current-turn receipt projection without its self digest."""
    projection = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    return sha256_bytes(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def controller_receipt_digest(payload: Mapping[str, object]) -> str:
    """Hash one READY receipt using the hook's exact durable JSON encoding."""
    return sha256_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def session_receipt_for_turn(
    root: Path,
    supplied_turn_sha256: str,
    *,
    require_current_controller: bool,
) -> dict[str, Any]:
    """Resolve the session receipt bound to an exact current-turn digest."""
    if SHA256_RE.fullmatch(supplied_turn_sha256) is None:
        raise WorkctlError("TURN_RECEIPT_INVALID")
    raw: object | None = None
    for path in current_turn_receipt_paths(root):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            candidate: object = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(candidate, dict) and candidate.get("receipt_sha256") == supplied_turn_sha256:
            raw = candidate
            break
    if raw is None and any(
        not path.is_symlink() and path.is_file() for path in current_turn_receipt_paths(root)
    ):
        raise WorkctlError("TURN_RECEIPT_SUPERSEDED")
    if not isinstance(raw, dict) or not isinstance(raw.get("session_id"), str):
        raise WorkctlError("TURN_RECEIPT_INVALID")
    session_id = str(raw["session_id"])
    scoped = session_receipt_path(root, session_id)
    legacy = bootstrap_state_path(root)
    receipt_path = scoped if scoped.is_file() and not scoped.is_symlink() else legacy
    return validate_current_ready_receipt(
        root,
        sha256_file(receipt_path),
        require_current_controller=require_current_controller,
    )


def load_current_turn_receipt(
    root: Path,
    *,
    supplied_sha256: str,
    session_receipt: Mapping[str, object],
) -> dict[str, object]:
    """Validate and return the current UserPromptSubmit receipt."""
    session_id_value = session_receipt.get("session_id")
    if not isinstance(session_id_value, str):
        raise WorkctlError("TURN_RECEIPT_INVALID")
    scoped = current_turn_receipt_path(root, session_id_value)
    legacy = current_turn_receipt_path(root)
    path = scoped if scoped.is_file() and not scoped.is_symlink() else legacy
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("TURN_RECEIPT_REQUIRED")
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WorkctlError("TURN_RECEIPT_INVALID") from exc
    if not isinstance(raw, dict):
        raise WorkctlError("TURN_RECEIPT_INVALID")
    receipt = cast(dict[str, object], raw)
    required = {
        "schema_version",
        "kind",
        "plugin_build",
        "session_start_receipt_sha256",
        "session_id",
        "turn_id",
        "prompt_sha256",
        "request_ref",
        "project_root",
        "issued_at",
        "receipt_sha256",
    }
    prompt_sha256 = receipt.get("prompt_sha256")
    receipt_sha256 = receipt.get("receipt_sha256")
    session_id = receipt.get("session_id")
    turn_id = receipt.get("turn_id")
    expected_request_ref = f"user:session/{session_id}/turn/{turn_id}/sha256/{prompt_sha256}"
    if (
        set(receipt) != required
        or receipt.get("schema_version") != 1
        or receipt.get("kind") != "work-governance-current-turn-receipt"
        or receipt.get("plugin_build") != session_receipt.get("plugin_build")
        or receipt.get("session_start_receipt_sha256") != controller_receipt_digest(session_receipt)
        or session_id != session_receipt.get("session_id")
        or not isinstance(session_id, str)
        or not session_id
        or not isinstance(turn_id, str)
        or not turn_id
        or not isinstance(prompt_sha256, str)
        or SHA256_RE.fullmatch(prompt_sha256) is None
        or receipt.get("request_ref") != expected_request_ref
        or receipt.get("project_root") != root.resolve().as_posix()
        or not isinstance(receipt.get("issued_at"), str)
        or not isinstance(receipt_sha256, str)
        or SHA256_RE.fullmatch(receipt_sha256) is None
        or turn_receipt_digest(receipt) != receipt_sha256
    ):
        raise WorkctlError("TURN_RECEIPT_INVALID")
    if SHA256_RE.fullmatch(supplied_sha256) is None:
        raise WorkctlError("TURN_RECEIPT_REQUIRED")
    if supplied_sha256 != receipt_sha256:
        raise WorkctlError("TURN_RECEIPT_SUPERSEDED")
    return receipt


def valid_target_ref(value: object) -> bool:
    """Return whether *value* belongs to the shared advancement target namespace."""
    return isinstance(value, str) and TARGET_REF_RE.fullmatch(value) is not None


def exact_activation_target_from_placeholder(
    current_target: object,
    requested_target: object,
) -> str:
    """Bind one exact Codex build only to its matching plugin placeholder."""
    if not isinstance(current_target, str):
        raise WorkctlError("ACTIVATION_TARGET_NOT_PLACEHOLDER")
    placeholder = ACTIVATION_TARGET_PLACEHOLDER_RE.fullmatch(current_target)
    if placeholder is None:
        raise WorkctlError("ACTIVATION_TARGET_NOT_PLACEHOLDER")
    if (
        not isinstance(requested_target, str)
        or requested_target != requested_target.strip()
        or any(character.isspace() for character in requested_target)
    ):
        raise WorkctlError("ACTIVATION_TARGET_EXACT_REF_REQUIRED")
    prefix = placeholder.group(1)
    if not requested_target.startswith(prefix):
        raise WorkctlError("ACTIVATION_TARGET_EXACT_REF_REQUIRED")
    cachebuster = requested_target[len(prefix) :]
    if cachebuster == "pending" or ACTIVATION_CACHEBUSTER_RE.fullmatch(cachebuster) is None:
        raise WorkctlError("ACTIVATION_TARGET_EXACT_REF_REQUIRED")
    return requested_target


def exact_activation_repair_target(
    current_target: object,
    requested_target: object,
) -> str:
    """Validate one exact replacement for the bounded legacy target defect."""
    if not isinstance(current_target, str):
        raise WorkctlError("ACTIVATION_REPAIR_LEGACY_TARGET_REQUIRED")
    legacy = LEGACY_ACTIVATION_TARGET_PLACEHOLDER_RE.fullmatch(current_target)
    if legacy is None:
        raise WorkctlError("ACTIVATION_REPAIR_LEGACY_TARGET_REQUIRED")
    if not isinstance(requested_target, str):
        raise WorkctlError("ACTIVATION_REPAIR_EXACT_TARGET_REQUIRED")
    exact = EXACT_ACTIVATION_TARGET_RE.fullmatch(requested_target)
    if exact is None or exact.group("plugin") != legacy.group("plugin"):
        raise WorkctlError("ACTIVATION_REPAIR_EXACT_TARGET_REQUIRED")
    cachebuster = exact.group("cachebuster")
    if cachebuster == "pending" or ACTIVATION_CACHEBUSTER_RE.fullmatch(cachebuster) is None:
        raise WorkctlError("ACTIVATION_REPAIR_EXACT_TARGET_REQUIRED")
    return requested_target


def decision_basis_projection(frontmatter: Mapping[str, Any]) -> dict[str, object]:
    """Project only contract and execution-structure fields that invalidate intake."""

    def collection_projection(
        field: str,
        *,
        excluded: set[str],
    ) -> list[dict[str, object]]:
        """Project one ordered Plan collection without volatile fields."""
        raw = frontmatter.get(field, [])
        if not isinstance(raw, list):
            return []
        projected: list[dict[str, object]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            projected.append(
                {
                    str(key): cast(object, value)
                    for key, value in item.items()
                    if key not in excluded
                }
            )
        return projected

    contract = frontmatter.get("contract", {})
    contract_revision = contract.get("revision") if isinstance(contract, dict) else None
    route = frontmatter.get("route", {})
    route_projection = (
        {
            str(key): cast(object, value)
            for key, value in route.items()
            if key not in {"slice_status"}
        }
        if isinstance(route, dict)
        else {}
    )
    return {
        "contract_revision": contract_revision,
        "goal": cast(object, frontmatter.get("goal", {})),
        "scope": cast(object, frontmatter.get("scope", {})),
        "obligations": collection_projection(
            "obligations",
            excluded={
                "status",
                "evidence_ref",
                "evidence_sha256",
                "verified_at",
                "note",
            },
        ),
        "unknowns": collection_projection(
            "unknowns",
            excluded={"resolved_at", "evidence_manifest"},
        ),
        "tasks": collection_projection(
            "tasks",
            excluded={
                "status",
                "note",
                "started_at",
                "verified_at",
                "skipped_at",
            },
        ),
        "route": route_projection,
    }


def decision_basis_sha256(frontmatter: Mapping[str, Any]) -> str:
    """Hash the normalized intake decision basis for one Plan state."""
    return sha256_bytes(
        json.dumps(
            decision_basis_projection(frontmatter),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def legacy_unknown_ids(frontmatter: Mapping[str, Any]) -> list[str]:
    """Return unknown IDs that lack the strict clarification metadata contract."""
    result: list[str] = []
    raw_unknowns = frontmatter.get("unknowns", [])
    if not isinstance(raw_unknowns, list):
        return ["unknowns:invalid"]
    for item in raw_unknowns:
        if not isinstance(item, dict):
            result.append("unknown:invalid")
            continue
        unknown_id = str(item.get("id", "unknown:invalid"))
        blocks = item.get("blocks")
        if (
            item.get("owner") not in UNKNOWN_OWNERS
            or item.get("impact") not in UNKNOWN_IMPACTS
            or not isinstance(blocks, list)
            or not all(valid_target_ref(target) for target in blocks)
            or not isinstance(item.get("expected_evidence"), str)
            or not item.get("expected_evidence")
        ):
            result.append(unknown_id)
    return result


def unknowns_by_id(frontmatter: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Index well-shaped Plan unknown mappings by ID."""
    result: dict[str, dict[str, Any]] = {}
    raw_unknowns = frontmatter.get("unknowns", [])
    if not isinstance(raw_unknowns, list):
        return result
    for item in raw_unknowns:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            result[str(item["id"])] = item
    return result


def target_covers(record_target: str, command_target: str) -> bool:
    """Return whether one intake target authorizes one command target."""
    return record_target == "route" or record_target == command_target


def unknown_blocks_target(unknown: Mapping[str, Any], target: str) -> bool:
    """Return whether one open strict unknown blocks *target*."""
    if unknown.get("status") != "open":
        return False
    raw_blocks = unknown.get("blocks", [])
    if not isinstance(raw_blocks, list):
        return False
    return any(isinstance(block, str) and target_covers(block, target) for block in raw_blocks)


def open_blockers_for_targets(
    frontmatter: Mapping[str, Any],
    targets: list[str],
) -> list[dict[str, Any]]:
    """Return every open strict unknown blocking any requested target."""
    blockers: list[dict[str, Any]] = []
    for unknown in unknowns_by_id(frontmatter).values():
        if any(unknown_blocks_target(unknown, target) for target in targets):
            blockers.append(unknown)
    return blockers


def validate_intake_decision(
    frontmatter: Mapping[str, Any],
    *,
    decision: str,
    targets: list[str],
    current_unknown_id: str | None,
) -> None:
    """Enforce proceed, explore, and ask semantics against current unknowns."""
    if not targets or any(not valid_target_ref(target) for target in targets):
        raise WorkctlError("INTAKE_TARGET_INVALID")
    blockers = open_blockers_for_targets(frontmatter, targets)
    if decision == "proceed":
        if current_unknown_id is not None:
            raise WorkctlError("INTAKE_PROCEED_UNKNOWN_CONFLICT")
        if blockers:
            raise WorkctlError(f"INTAKE_BLOCKED_BY_UNKNOWN: {blockers[0].get('id')}")
        return
    if current_unknown_id is None:
        raise WorkctlError("INTAKE_CURRENT_UNKNOWN_REQUIRED")
    current = unknowns_by_id(frontmatter).get(current_unknown_id)
    expected_owner = "user" if decision == "ask" else "agent"
    if (
        current is None
        or current.get("status") != "open"
        or current.get("owner") != expected_owner
        or current not in blockers
    ):
        raise WorkctlError(f"INTAKE_{decision.upper()}_UNKNOWN_INVALID")


def intake_proposal_digest(payload: Mapping[str, object]) -> str:
    """Hash one normalized intake proposal without its self digest."""
    projection = {key: value for key, value in payload.items() if key != "intake_sha256"}
    return sha256_bytes(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def intake_record_digest(payload: Mapping[str, object]) -> str:
    """Hash one append-only intake record without its self digest."""
    projection = {key: value for key, value in payload.items() if key != "record_sha256"}
    return sha256_bytes(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def intake_records(frontmatter: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the legacy chain or the bounded protocol-v2 current record."""
    intake = frontmatter.get("intake", {})
    if isinstance(intake, dict) and intake.get("protocol_version") == 2:
        current = intake.get("current")
        return [cast(dict[str, Any], current)] if isinstance(current, dict) else []
    records = intake.get("records", []) if isinstance(intake, dict) else []
    return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []


def intake_contract_errors(frontmatter: Mapping[str, Any]) -> list[str]:
    """Validate an optional schema-v4 intake protocol and its hash chain."""
    intake = frontmatter.get("intake")
    if intake is None:
        return []
    if not isinstance(intake, dict) or intake.get("protocol_version") not in {1, 2}:
        return ["intake.protocol_version must equal 1 or 2"]
    protocol_version = intake["protocol_version"]
    if protocol_version == 1:
        raw_records = intake.get("records")
        if not isinstance(raw_records, list) or not raw_records:
            return ["intake.records must be a non-empty list"]
    else:
        if set(intake) != {"protocol_version", "current", "history"}:
            return ["intake protocol 2 fields are invalid"]
        current = intake.get("current")
        history = intake.get("history")
        if not isinstance(current, dict):
            return ["intake.current must be a mapping"]
        if (
            not isinstance(history, dict)
            or set(history) != {"storage", "head_sha256", "record_count"}
            or history.get("storage") != "project-local-immutable"
            or history.get("head_sha256") != current.get("record_sha256")
            or not isinstance(history.get("record_count"), int)
            or cast(int, history["record_count"]) < 1
        ):
            return ["intake.history anchor is invalid"]
        raw_records = [current]
    errors: list[str] = []
    previous: str | None = None
    request_refs: set[str] = set()
    for index, item in enumerate(raw_records):
        label = f"intake.records[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be a mapping")
            continue
        required = {
            "request_ref",
            "request_sha256",
            "classification",
            "targets",
            "decision",
            "rationale",
            "decision_basis_sha256",
            "previous_record_sha256",
            "recorded_at",
            "record_sha256",
        }
        allowed = required | {"current_unknown_id", "supersedes_record_sha256"}
        request_ref = item.get("request_ref")
        request_sha256 = item.get("request_sha256")
        record_sha256 = item.get("record_sha256")
        targets = item.get("targets")
        if not required.issubset(item) or not set(item).issubset(allowed):
            errors.append(f"{label} has invalid fields")
        if (
            not isinstance(request_ref, str)
            or not isinstance(request_sha256, str)
            or SHA256_RE.fullmatch(request_sha256) is None
            or not request_ref.endswith(f"/sha256/{request_sha256}")
        ):
            errors.append(f"{label} request identity is invalid")
        elif protocol_version == 1 and request_ref in request_refs:
            errors.append(f"{label} request_ref must be unique")
        else:
            request_refs.add(request_ref)
        if item.get("classification") != "plan_controlled":
            errors.append(f"{label} classification must be plan_controlled")
        if (
            not isinstance(targets, list)
            or not targets
            or not all(valid_target_ref(target) for target in targets)
            or len(targets) != len(set(cast(list[str], targets)))
        ):
            errors.append(f"{label} targets are invalid")
        if item.get("decision") not in INTAKE_DECISIONS:
            errors.append(f"{label} decision is invalid")
        if not isinstance(item.get("rationale"), str) or not item.get("rationale"):
            errors.append(f"{label} rationale is required")
        basis = item.get("decision_basis_sha256")
        if not isinstance(basis, str) or SHA256_RE.fullmatch(basis) is None:
            errors.append(f"{label} decision_basis_sha256 is invalid")
        prior_digest = item.get("previous_record_sha256")
        if protocol_version == 1 and prior_digest != previous:
            errors.append(f"{label} previous_record_sha256 breaks the chain")
        if (
            protocol_version == 2
            and prior_digest is not None
            and (not isinstance(prior_digest, str) or SHA256_RE.fullmatch(prior_digest) is None)
        ):
            errors.append(f"{label} previous_record_sha256 is invalid")
        if not isinstance(item.get("recorded_at"), str) or not item.get("recorded_at"):
            errors.append(f"{label} recorded_at is required")
        if (
            not isinstance(record_sha256, str)
            or SHA256_RE.fullmatch(record_sha256) is None
            or intake_record_digest(cast(Mapping[str, object], item)) != record_sha256
        ):
            errors.append(f"{label} record_sha256 is invalid")
        if item.get("decision") == "proceed" and "current_unknown_id" in item:
            errors.append(f"{label} proceed cannot name current_unknown_id")
        if item.get("decision") in {"ask", "explore"} and not isinstance(
            item.get("current_unknown_id"), str
        ):
            errors.append(f"{label} {item.get('decision')} requires current_unknown_id")
        supersedes = item.get("supersedes_record_sha256")
        if "supersedes_record_sha256" in item and (
            not isinstance(supersedes, str) or SHA256_RE.fullmatch(supersedes) is None
        ):
            errors.append(f"{label} supersedes_record_sha256 is invalid")
        previous = record_sha256 if isinstance(record_sha256, str) else None
    return errors


def intake_history_dir(root: Path, plan_id: str) -> Path:
    """Return the ignored immutable history directory for one canonical Plan."""
    if PLAN_ID_RE.fullmatch(plan_id) is None:
        raise WorkctlError("INTAKE_HISTORY_PLAN_ID_INVALID")
    return runtime_dir(root) / "intake-history" / plan_id


def persist_intake_history_record(
    root: Path,
    plan_id: str,
    record: Mapping[str, object],
) -> None:
    """Create one content-addressed intake history record without overwriting bytes."""
    record_sha256 = record.get("record_sha256")
    if (
        not isinstance(record_sha256, str)
        or SHA256_RE.fullmatch(record_sha256) is None
        or intake_record_digest(record) != record_sha256
    ):
        raise WorkctlError("INTAKE_HISTORY_RECORD_INVALID")
    history = intake_history_dir(root, plan_id)
    reject_symlink_components(root, history)
    history.mkdir(parents=True, exist_ok=True)
    target = history / f"{record_sha256}.json"
    content = (json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != content:
            raise WorkctlError("INTAKE_HISTORY_RECORD_CONFLICT")
        return
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            target.unlink()
        raise
    fsync_directory(history)


def intake_state(frontmatter: Mapping[str, Any]) -> str:
    """Return the current Plan-basis state of the latest intake record."""
    errors = intake_contract_errors(frontmatter)
    if errors:
        return "INVALID"
    records = intake_records(frontmatter)
    if not records:
        return "MISSING"
    if records[-1].get("decision_basis_sha256") != decision_basis_sha256(frontmatter):
        return "STALE_BASIS"
    return "CURRENT_BASIS"


def require_current_intake(
    root: Path,
    frontmatter: Mapping[str, Any],
    *,
    turn_receipt_sha256: str | None,
    expected_intake_sha256: str | None,
    targets: list[str],
) -> None:
    """Require a current-turn, current-basis intake record covering all targets."""
    if frontmatter.get("schema_version") != 4:
        return
    if turn_receipt_sha256 is None or expected_intake_sha256 is None:
        raise WorkctlError("TURN_RECEIPT_REQUIRED")
    session_receipt = session_receipt_for_turn(
        root,
        turn_receipt_sha256,
        require_current_controller=True,
    )
    turn_receipt = load_current_turn_receipt(
        root,
        supplied_sha256=turn_receipt_sha256,
        session_receipt=cast(Mapping[str, object], session_receipt),
    )
    if legacy_unknown_ids(frontmatter):
        raise WorkctlError("UNKNOWN_CONTRACT_REQUIRED")
    records = intake_records(frontmatter)
    if not records:
        raise WorkctlError("INTAKE_RECORD_REQUIRED")
    latest = records[-1]
    if latest.get("record_sha256") != expected_intake_sha256:
        raise WorkctlError("INTAKE_RECORD_MISMATCH")
    if latest.get("request_ref") != turn_receipt.get("request_ref"):
        raise WorkctlError("INTAKE_REQUEST_MISMATCH")
    if latest.get("decision_basis_sha256") != decision_basis_sha256(frontmatter):
        raise WorkctlError("INTAKE_BASIS_STALE")
    if latest.get("decision") != "proceed":
        raise WorkctlError(f"INTAKE_DECISION_NOT_PROCEED: {latest.get('decision')}")
    record_targets = latest.get("targets")
    if not isinstance(record_targets, list) or any(
        not any(
            isinstance(record_target, str) and target_covers(record_target, command_target)
            for record_target in record_targets
        )
        for command_target in targets
    ):
        raise WorkctlError("INTAKE_TARGET_MISMATCH")
    validate_intake_decision(
        frontmatter,
        decision=str(latest.get("decision")),
        targets=targets,
        current_unknown_id=(
            str(latest["current_unknown_id"])
            if isinstance(latest.get("current_unknown_id"), str)
            else None
        ),
    )


def cmd_intake_receipt(args: argparse.Namespace) -> None:
    """Generate one normalized, turn-bound intake proposal without writing state."""
    root = project_root()
    session_receipt = validate_current_ready_receipt(
        root,
        args.receipt_sha256,
        require_current_controller=True,
    )
    turn_receipt = load_current_turn_receipt(
        root,
        supplied_sha256=args.turn_receipt_sha256,
        session_receipt=cast(Mapping[str, object], session_receipt),
    )
    rationale = str(args.rationale).strip()
    targets = list(dict.fromkeys(str(target).strip() for target in args.targets))
    if not rationale:
        raise WorkctlError("INTAKE_RATIONALE_REQUIRED")
    if not targets or any(not valid_target_ref(target) for target in targets):
        raise WorkctlError("INTAKE_TARGET_INVALID")
    if args.classification == "no_plan":
        if args.decision != "proceed" or args.current_unknown_id is not None:
            raise WorkctlError("NO_PLAN_INTAKE_MUST_PROCEED")
        decision_basis: str | None = None
    else:
        report = inspect_authority(root)
        if args.candidate_plan is not None:
            plan = load_plan(Path(args.candidate_plan).resolve())
        elif report.state == "GOVERNED_ACTIVE":
            plan = load_plan(active_plan_path(root))
        else:
            raise WorkctlError("PLAN_INTAKE_CANDIDATE_REQUIRED")
        plan_schema_version = plan.frontmatter.get("schema_version")
        if plan_schema_version != 4:
            if plan_schema_version == CURRENT_PLAN_SCHEMA_VERSION:
                raise WorkctlError("PLAN_INTAKE_NOT_REQUIRED_FOR_CURRENT_SCHEMA")
            raise WorkctlError("PLAN_SCHEMA_REFRESH_REQUIRED")
        if legacy_unknown_ids(plan.frontmatter):
            raise WorkctlError("UNKNOWN_CONTRACT_REQUIRED")
        validate_intake_decision(
            plan.frontmatter,
            decision=args.decision,
            targets=targets,
            current_unknown_id=args.current_unknown_id,
        )
        decision_basis = decision_basis_sha256(plan.frontmatter)
    proposal: dict[str, object] = {
        "schema_version": 1,
        "kind": "work-governance-intake-proposal",
        "request_ref": turn_receipt["request_ref"],
        "request_sha256": turn_receipt["prompt_sha256"],
        "turn_receipt_sha256": turn_receipt["receipt_sha256"],
        "classification": args.classification,
        "decision": args.decision,
        "rationale": rationale,
        "targets": targets,
        "created_at": turn_receipt["issued_at"],
    }
    if decision_basis is not None:
        proposal["decision_basis_sha256"] = decision_basis
    if args.current_unknown_id is not None:
        proposal["current_unknown_id"] = args.current_unknown_id
    if args.candidate_plan is not None:
        proposal["candidate_plan"] = args.candidate_plan
    proposal["intake_sha256"] = sha256_bytes(
        json.dumps(
            proposal,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    print(json.dumps(proposal, indent=2, sort_keys=True, ensure_ascii=False))


def validate_intake_proposal_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and return one normalized intake proposal mapping."""
    proposal = dict(payload)
    base_fields = {
        "schema_version",
        "kind",
        "request_ref",
        "request_sha256",
        "turn_receipt_sha256",
        "classification",
        "decision",
        "rationale",
        "targets",
        "created_at",
        "intake_sha256",
    }
    optional_fields = {
        "current_unknown_id",
        "candidate_plan",
        "decision_basis_sha256",
    }
    request_sha256 = proposal.get("request_sha256")
    turn_receipt_sha256 = proposal.get("turn_receipt_sha256")
    intake_sha256 = proposal.get("intake_sha256")
    targets = proposal.get("targets")
    if (
        not base_fields.issubset(proposal)
        or not set(proposal).issubset(base_fields | optional_fields)
        or proposal.get("schema_version") != 1
        or proposal.get("kind") != "work-governance-intake-proposal"
        or not isinstance(proposal.get("request_ref"), str)
        or not isinstance(request_sha256, str)
        or SHA256_RE.fullmatch(request_sha256) is None
        or not str(proposal["request_ref"]).endswith(f"/sha256/{request_sha256}")
        or not isinstance(turn_receipt_sha256, str)
        or SHA256_RE.fullmatch(turn_receipt_sha256) is None
        or proposal.get("classification") not in INTAKE_CLASSIFICATIONS
        or proposal.get("decision") not in INTAKE_DECISIONS
        or not isinstance(proposal.get("rationale"), str)
        or not proposal.get("rationale")
        or not isinstance(targets, list)
        or not targets
        or not all(valid_target_ref(target) for target in targets)
        or len(targets) != len(set(cast(list[str], targets)))
        or not isinstance(proposal.get("created_at"), str)
        or not proposal.get("created_at")
        or not isinstance(intake_sha256, str)
        or SHA256_RE.fullmatch(intake_sha256) is None
        or intake_proposal_digest(cast(Mapping[str, object], proposal)) != intake_sha256
    ):
        raise WorkctlError("INTAKE_MANIFEST_INVALID")
    return proposal


def load_intake_proposal(path: Path) -> dict[str, Any]:
    """Load and structurally validate one normalized intake proposal."""
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("INTAKE_MANIFEST_MISSING")
    return validate_intake_proposal_payload(load_yaml_file(path))


def embedded_initial_intake(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the strict, embedded initial intake proposal from a transaction."""
    value = manifest.get("intake")
    if not isinstance(value, dict):
        raise WorkctlError("INITIAL_INTAKE_REQUIRED")
    proposal = validate_intake_proposal_payload(cast(Mapping[str, Any], value))
    if proposal.get("classification") != "plan_controlled":
        raise WorkctlError("PLAN_INTAKE_CLASSIFICATION_REQUIRED")
    return proposal


def validate_current_intake_proposal(
    root: Path,
    frontmatter: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    session_receipt: Mapping[str, object],
) -> None:
    """Validate one proposal against current turn identity and target Plan basis."""
    turn_receipt = load_current_turn_receipt(
        root,
        supplied_sha256=str(proposal["turn_receipt_sha256"]),
        session_receipt=session_receipt,
    )
    if proposal.get("request_ref") != turn_receipt.get("request_ref") or proposal.get(
        "request_sha256"
    ) != turn_receipt.get("prompt_sha256"):
        raise WorkctlError("INTAKE_REQUEST_MISMATCH")
    if legacy_unknown_ids(frontmatter):
        raise WorkctlError("UNKNOWN_CONTRACT_REQUIRED")
    basis = decision_basis_sha256(frontmatter)
    if proposal.get("decision_basis_sha256") != basis:
        raise WorkctlError("INTAKE_BASIS_STALE")
    targets = cast(list[str], proposal["targets"])
    current_unknown_id = (
        str(proposal["current_unknown_id"])
        if isinstance(proposal.get("current_unknown_id"), str)
        else None
    )
    validate_intake_decision(
        frontmatter,
        decision=str(proposal["decision"]),
        targets=targets,
        current_unknown_id=current_unknown_id,
    )


def intake_record_from_proposal(
    frontmatter: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    previous_record_sha256: str | None,
) -> dict[str, object]:
    """Build one canonical append-only record from a validated proposal."""
    record: dict[str, object] = {
        "request_ref": proposal["request_ref"],
        "request_sha256": proposal["request_sha256"],
        "classification": "plan_controlled",
        "targets": proposal["targets"],
        "decision": proposal["decision"],
        "rationale": proposal["rationale"],
        "decision_basis_sha256": decision_basis_sha256(frontmatter),
        "previous_record_sha256": previous_record_sha256,
        "recorded_at": proposal["created_at"],
    }
    if isinstance(proposal.get("current_unknown_id"), str):
        record["current_unknown_id"] = proposal["current_unknown_id"]
    record["record_sha256"] = intake_record_digest(record)
    return record


def inject_initial_intake(
    frontmatter: dict[str, Any],
    proposal: Mapping[str, Any],
) -> dict[str, object]:
    """Inject the first intake record into a not-yet-active strict Plan."""
    if frontmatter.get("intake") is not None:
        raise WorkctlError("INITIAL_INTAKE_ALREADY_PRESENT")
    record = intake_record_from_proposal(
        frontmatter,
        proposal,
        previous_record_sha256=None,
    )
    frontmatter["intake"] = {"protocol_version": 1, "records": [record]}
    return record


def initial_intake_binding(
    proposal: Mapping[str, Any],
    record: Mapping[str, object],
) -> dict[str, object]:
    """Return the transaction fields that bind request, turn, basis and record."""
    return {
        "request_ref": proposal["request_ref"],
        "request_sha256": proposal["request_sha256"],
        "turn_receipt_sha256": proposal["turn_receipt_sha256"],
        "decision_basis_sha256": proposal["decision_basis_sha256"],
        "intake_proposal_sha256": proposal["intake_sha256"],
        "intake_record_sha256": record["record_sha256"],
    }


def transaction_binding_digest(
    *,
    transaction_kind: str,
    transaction_id: str,
    plan_id: str,
    prepared_plan_sha256: str,
    target_plan_sha256: str,
    intake_binding: Mapping[str, object],
) -> str:
    """Hash the exact strict transaction inputs and staged target bytes."""
    payload = {
        "transaction_kind": transaction_kind,
        "transaction_id": transaction_id,
        "plan_id": plan_id,
        "prepared_plan_sha256": prepared_plan_sha256,
        "target_plan_sha256": target_plan_sha256,
        "intake_binding": intake_binding,
    }
    return sha256_bytes(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def current_revision_binds_decision_basis(
    frontmatter: Mapping[str, Any],
    basis: str,
) -> bool:
    """Require the current basis to come from the latest controller revision."""
    history = frontmatter.get("revision_history", [])
    latest = history[-1] if isinstance(history, list) and history else None
    return bool(
        isinstance(latest, dict)
        and latest.get("revision") == frontmatter.get("revision")
        and latest.get("kind") != "intake-recorded"
        and latest.get("decision_basis_sha256") == basis
    )


def refresh_intake_for_atomic_controller_transition(
    frontmatter: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    """Refresh one trusted proceed after an in-memory atomic structural change."""
    prior_records = intake_records(frontmatter)
    if not prior_records:
        raise WorkctlError("INTAKE_RECORD_REQUIRED")
    existing = prior_records[-1]
    if existing.get("decision") != "proceed":
        raise WorkctlError("INTAKE_DECISION_NOT_PROCEED")
    record: dict[str, object] = {
        "request_ref": existing["request_ref"],
        "request_sha256": existing["request_sha256"],
        "classification": "plan_controlled",
        "targets": existing["targets"],
        "decision": "proceed",
        "rationale": existing["rationale"],
        "decision_basis_sha256": decision_basis_sha256(frontmatter),
        "previous_record_sha256": existing["record_sha256"],
        "recorded_at": utc_now(),
        "supersedes_record_sha256": existing["record_sha256"],
    }
    if isinstance(existing.get("current_unknown_id"), str):
        record["current_unknown_id"] = existing["current_unknown_id"]
    record["record_sha256"] = intake_record_digest(record)
    intake = frontmatter.get("intake")
    prior_count = (
        cast(int, cast(dict[str, object], intake["history"])["record_count"])
        if isinstance(intake, dict)
        and intake.get("protocol_version") == 2
        and isinstance(intake.get("history"), dict)
        and isinstance(cast(dict[str, object], intake["history"]).get("record_count"), int)
        else len(prior_records)
    )
    frontmatter["intake"] = {
        "protocol_version": 2,
        "current": record,
        "history": {
            "storage": "project-local-immutable",
            "head_sha256": record["record_sha256"],
            "record_count": prior_count + 1,
        },
    }
    return prior_records, record


def cmd_plan_intake_record(args: argparse.Namespace) -> None:
    """Append one current-turn intake record, with idempotent exact replay."""
    root = project_root()
    manifest = load_intake_proposal(Path(args.manifest).resolve())
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        if manifest.get("classification") != "plan_controlled":
            raise WorkctlError("PLAN_INTAKE_CLASSIFICATION_REQUIRED")
        session_receipt = validate_current_ready_receipt(
            root,
            args.receipt_sha256,
            require_current_controller=True,
        )
        turn_receipt = load_current_turn_receipt(
            root,
            supplied_sha256=str(manifest["turn_receipt_sha256"]),
            session_receipt=cast(Mapping[str, object], session_receipt),
        )
        if manifest.get("request_ref") != turn_receipt.get("request_ref") or manifest.get(
            "request_sha256"
        ) != turn_receipt.get("prompt_sha256"):
            raise WorkctlError("INTAKE_REQUEST_MISMATCH")
        basis = decision_basis_sha256(doc.frontmatter)
        if manifest.get("decision_basis_sha256") != basis:
            raise WorkctlError("INTAKE_BASIS_STALE")
        targets = cast(list[str], manifest["targets"])
        current_unknown_id = (
            str(manifest["current_unknown_id"])
            if isinstance(manifest.get("current_unknown_id"), str)
            else None
        )
        validate_intake_decision(
            doc.frontmatter,
            decision=str(manifest["decision"]),
            targets=targets,
            current_unknown_id=current_unknown_id,
        )
        record_core: dict[str, object] = {
            "request_ref": manifest["request_ref"],
            "request_sha256": manifest["request_sha256"],
            "classification": "plan_controlled",
            "targets": targets,
            "decision": manifest["decision"],
            "rationale": manifest["rationale"],
            "decision_basis_sha256": basis,
        }
        if current_unknown_id is not None:
            record_core["current_unknown_id"] = current_unknown_id
        prior_records = intake_records(doc.frontmatter)
        existing = next(
            (
                record
                for record in reversed(prior_records)
                if record.get("request_ref") == manifest["request_ref"]
            ),
            None,
        )
        transitioned = False
        refreshed = False
        if existing is not None:
            existing_core = {
                key: cast(object, existing[key]) for key in record_core if key in existing
            }
            if existing_core == record_core:
                print(
                    "PLAN_INTAKE_REPLAY "
                    f"record_sha256={existing.get('record_sha256')} "
                    f"revision={doc.frontmatter['revision']}"
                )
                return
            transitioned = bool(
                existing.get("decision") in {"ask", "explore"}
                and manifest.get("decision") == "proceed"
                and existing.get("decision_basis_sha256") != basis
                and existing.get("targets") == targets
                and existing.get("request_sha256") == manifest.get("request_sha256")
            )
            refreshed = bool(
                existing.get("decision") == "proceed"
                and manifest.get("decision") == "proceed"
                and existing.get("decision_basis_sha256") != basis
                and existing.get("targets") == targets
                and existing.get("request_sha256") == manifest.get("request_sha256")
                and existing.get("rationale") == manifest.get("rationale")
                and existing.get("current_unknown_id") == current_unknown_id
                and current_revision_binds_decision_basis(doc.frontmatter, basis)
            )
            if not transitioned and not refreshed:
                raise WorkctlError("INTAKE_REQUEST_CONFLICT")
        require_expected_revision(doc.frontmatter, args.expected_revision)
        intake = doc.frontmatter.get("intake")
        if not isinstance(intake, dict) or intake.get("protocol_version") not in {1, 2}:
            raise WorkctlError("INTAKE_CONTRACT_INVALID")
        previous = prior_records[-1].get("record_sha256") if prior_records else None
        record: dict[str, object] = {
            **record_core,
            "previous_record_sha256": previous,
            "recorded_at": manifest["created_at"],
        }
        if (transitioned or refreshed) and existing is not None:
            record["supersedes_record_sha256"] = existing["record_sha256"]
        record["record_sha256"] = intake_record_digest(record)
        plan_id = str(doc.frontmatter["plan_id"])
        for prior in prior_records:
            persist_intake_history_record(root, plan_id, prior)
        persist_intake_history_record(root, plan_id, record)
        prior_count = (
            cast(int, cast(dict[str, object], intake["history"])["record_count"])
            if intake.get("protocol_version") == 2
            and isinstance(intake.get("history"), dict)
            and isinstance(cast(dict[str, object], intake["history"]).get("record_count"), int)
            else len(prior_records)
        )
        doc.frontmatter["intake"] = {
            "protocol_version": 2,
            "current": record,
            "history": {
                "storage": "project-local-immutable",
                "head_sha256": record["record_sha256"],
                "record_count": prior_count + 1,
            },
        }
        bump_revision(
            doc.frontmatter,
            kind="intake-recorded",
            rationale=(
                f"Transition intake for {manifest['request_ref']}."
                if transitioned
                else (
                    f"Refresh intake for {manifest['request_ref']}."
                    if refreshed
                    else f"Record intake for {manifest['request_ref']}."
                )
            ),
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        result_kind = (
            "PLAN_INTAKE_TRANSITIONED"
            if transitioned
            else "PLAN_INTAKE_REFRESHED"
            if refreshed
            else "PLAN_INTAKE_RECORDED"
        )
        print(
            f"{result_kind} record_sha256={record['record_sha256']} "
            f"revision={doc.frontmatter['revision']}"
        )


@contextlib.contextmanager
def legacy_layout_lock(root: Path) -> Iterator[None]:
    """Acquire the old controller lock after the stable layout-1 lock."""
    legacy = legacy_plan_dir(root)
    if legacy.is_symlink() or not legacy.is_dir():
        raise WorkctlError("LEGACY_LOCK_UNAVAILABLE")
    path = legacy / ".workctl.lock"
    if path.is_symlink():
        raise WorkctlError("LEGACY_LOCK_SYMLINK")
    with path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def current_layout_git_baseline(root: Path) -> dict[str, object]:
    """Return a stable Git baseline excluding transaction-owned new-root files."""
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return {"repository": False}
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    filtered = sorted(line for line in status if f"{GOVERNANCE_DIR_NAME}/" not in line)
    return {
        "repository": True,
        "head": head,
        "status_sha256": sha256_bytes("\n".join(filtered).encode()),
    }


def layout_transaction_paths(
    root: Path, transaction_id: str
) -> tuple[Path, Path, Path, Path, Path, Path]:
    """Return runtime, journal, staging, backup, evidence, and guard paths."""
    if LAYOUT_TRANSACTION_RE.fullmatch(transaction_id) is None:
        raise WorkctlError("INVALID_LAYOUT_TRANSACTION_ID")
    transaction = runtime_dir(root) / transaction_id
    journal = transaction / "journal.json"
    staging = transaction / "staging"
    backup = transaction / "backup"
    evidence = evidence_dir(root) / "layout-migrations" / transaction_id
    guard = legacy_plan_dir(root)
    for path in (transaction, journal, staging, backup, evidence):
        reject_symlink_components(root, path)
    return transaction, journal, staging, backup, evidence, guard


def new_layout_transaction_id(legacy_manifest_sha256: str) -> str:
    """Return a collision-resistant transaction ID independent of PID reuse."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"LAY-{stamp}-{legacy_manifest_sha256[:8]}-{secrets.token_hex(16)}"


def write_layout_journal(path: Path, journal: dict[str, Any]) -> None:
    """Durably replace one JSON transaction journal."""
    journal["updated_at"] = utc_now()
    write_atomic(path, json.dumps(journal, indent=2, sort_keys=True) + "\n")


def load_layout_journal(path: Path) -> dict[str, Any]:
    """Load and minimally authenticate a layout transaction journal."""
    if not path.is_file() or path.is_symlink():
        raise WorkctlError(f"INVALID_LAYOUT_JOURNAL: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkctlError(f"INVALID_LAYOUT_JOURNAL: {path}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("kind") not in {"layout-migration", "layout-action-upgrade"}
        or not isinstance(payload.get("transaction_id"), str)
        or LAYOUT_TRANSACTION_RE.fullmatch(str(payload.get("transaction_id"))) is None
    ):
        raise WorkctlError(f"INVALID_LAYOUT_JOURNAL: {path}")
    if payload.get("kind") == "layout-migration":
        allowed_statuses = {
            "preparing",
            "staged",
            "activating",
            "legacy-backed-up",
            "plan-activated",
            "version-pending",
            "committed",
            "aborted",
        }
    else:
        allowed_statuses = {
            "preparing",
            "staged",
            "plan-activated",
            "proof-installed",
            "version-pending",
            "committed",
            "aborted",
        }
    if payload.get("status") not in allowed_statuses:
        raise WorkctlError(f"INVALID_LAYOUT_JOURNAL: {path}")
    return payload


def validate_preparing_layout_payload(root: Path, journal: dict[str, Any]) -> None:
    """Validate every durable field that can cross a preparing recovery boundary."""
    transaction_id = journal.get("transaction_id")
    if (
        not isinstance(transaction_id, str)
        or LAYOUT_TRANSACTION_RE.fullmatch(transaction_id) is None
    ):
        raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    _transaction, _journal, staging, backup, evidence, _guard = layout_transaction_paths(
        root, transaction_id
    )
    expected_paths = {
        "staged_plan": (staging / PLAN_DIR_NAME).as_posix(),
        "staged_proposals": (staging / "proposals").as_posix(),
        "target_proposals": proposals_dir(root).as_posix(),
        "backup_plan": (backup / PLAN_DIR_NAME).as_posix(),
        "original_evidence": (evidence / f"legacy-{PLAN_DIR_NAME}").as_posix(),
    }
    legacy_manifest = journal.get("legacy_manifest")
    if (
        set(journal) != PREPARING_LAYOUT_JOURNAL_KEYS
        or journal.get("schema_version") != 1
        or journal.get("kind") != "layout-migration"
        or journal.get("status") != "preparing"
        or journal.get("completed_operations") != ["snapshot"]
        or not isinstance(journal.get("created_at"), str)
        or not journal.get("created_at")
        or not isinstance(journal.get("updated_at"), str)
        or not journal.get("updated_at")
        or not isinstance(journal.get("active_plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(journal.get("active_plan_id"))) is None
        or not isinstance(journal.get("active_plan_path"), str)
        or Path(str(journal.get("active_plan_path"))).name != journal.get("active_plan_path")
        or Path(str(journal.get("active_plan_path"))).stem != journal.get("active_plan_id")
        or not isinstance(legacy_manifest, list)
        or not isinstance(journal.get("git_baseline"), dict)
        or journal.get("paths") != expected_paths
    ):
        raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    seen_manifest_paths: set[str] = set()
    for entry in legacy_manifest:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
        raw_path = str(entry["path"])
        if (
            Path(raw_path).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(raw_path).parts)
            or raw_path in seen_manifest_paths
        ):
            raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
        seen_manifest_paths.add(raw_path)
        if entry.get("kind") == "directory":
            if set(entry) != {"path", "kind"}:
                raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
        elif entry.get("kind") == "file":
            if (
                set(entry) != {"path", "kind", "size", "sha256"}
                or not isinstance(entry.get("size"), int)
                or int(entry["size"]) < 0
                or SHA256_RE.fullmatch(str(entry.get("sha256"))) is None
            ):
                raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
        else:
            raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    if manifest_sha256(legacy_manifest) != journal.get("legacy_manifest_sha256"):
        raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    legacy_proposals_manifest = journal.get("legacy_proposals_manifest")
    legacy_proposals_sha256 = journal.get("legacy_proposals_sha256")
    if (
        not isinstance(legacy_proposals_manifest, list)
        or not isinstance(legacy_proposals_sha256, str)
        or SHA256_RE.fullmatch(legacy_proposals_sha256) is None
        or manifest_sha256(legacy_proposals_manifest) != legacy_proposals_sha256
        or proposal_manifest_from_plan_manifest(cast(list[dict[str, object]], legacy_manifest))
        != legacy_proposals_manifest
    ):
        raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    adoption_sha256 = journal.get("legacy_adoption_sha256")
    if not isinstance(adoption_sha256, str) or SHA256_RE.fullmatch(adoption_sha256) is None:
        raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    planned_logs = journal.get("planned_log_files")
    if not isinstance(planned_logs, list):
        raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    seen_log_paths: set[str] = set()
    for entry in planned_logs:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256"}
            or not isinstance(entry.get("path"), str)
            or Path(str(entry["path"])).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(str(entry["path"])).parts)
            or str(entry["path"]) in seen_log_paths
            or SHA256_RE.fullmatch(str(entry.get("sha256"))) is None
        ):
            raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
        seen_log_paths.add(str(entry["path"]))


def validate_aborted_layout_journal(
    root: Path, journal_path: Path, journal: dict[str, Any]
) -> None:
    """Authenticate an ignored aborted journal against its parent and exact transition."""
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise WorkctlError("INVALID_ABORTED_LAYOUT_JOURNAL")
    transaction, expected_journal, _staging, _backup, _evidence, _guard = layout_transaction_paths(
        root, transaction_id
    )
    preparing_path = transaction / "preparing-journal.json"
    if (
        journal_path.parent.name != transaction_id
        or journal_path != expected_journal
        or set(journal) != ABORTED_LAYOUT_JOURNAL_KEYS
        or journal.get("status") != "aborted"
        or journal.get("completed_operations") != ["snapshot", "preparation-preserved"]
        or SHA256_RE.fullmatch(str(journal.get("preparing_journal_sha256"))) is None
        or preparing_path.is_symlink()
        or not preparing_path.is_file()
        or sha256_file(preparing_path) != journal.get("preparing_journal_sha256")
    ):
        raise WorkctlError("INVALID_ABORTED_LAYOUT_JOURNAL")
    preparing = load_layout_journal(preparing_path)
    validate_preparing_layout_payload(root, preparing)
    stable_fields = PREPARING_LAYOUT_JOURNAL_KEYS - {
        "status",
        "updated_at",
        "completed_operations",
    }
    if any(journal.get(field) != preparing.get(field) for field in stable_fields):
        raise WorkctlError("INVALID_ABORTED_LAYOUT_JOURNAL")


def layout_test_interrupt(phase: str) -> None:
    """Raise only when a test explicitly requests one transaction interruption."""
    if os.environ.get("WORKCTL_TEST_LAYOUT_INTERRUPT_AFTER") == phase:
        raise WorkctlError(f"LAYOUT_TEST_INTERRUPTED: {phase}")


def rewrite_legacy_plan_path(value: str) -> str:
    """Translate one exact legacy Plan prefix to the canonical root."""
    if value == PLAN_DIR_NAME:
        return plan_relative_path()
    prefix = f"{PLAN_DIR_NAME}/"
    if value.startswith(prefix):
        return f"{plan_relative_path()}/{value.removeprefix(prefix)}"
    return value


def rewrite_legacy_scope_root(value: str) -> str:
    """Translate only an exact legacy governance-root scope entry."""
    if value == PLAN_DIR_NAME:
        return plan_relative_path()
    if value == f"{PLAN_DIR_NAME}/":
        return f"{plan_relative_path()}/"
    return value


def convert_active_scope_paths(frontmatter: dict[str, Any]) -> None:
    """Convert exact active scope roots without absorbing project-owned child paths."""
    scope = frontmatter.get("scope")
    if not isinstance(scope, dict):
        return
    for field in ("include", "exclude"):
        entries = scope.get(field)
        if isinstance(entries, list):
            scope[field] = [
                rewrite_legacy_scope_root(entry) if isinstance(entry, str) else entry
                for entry in entries
            ]


def rewrite_evidence_reference(value: str, mapping: dict[str, str]) -> str:
    """Translate only a legacy reference bound to a staged governance target."""
    return mapping.get(value, value)


def convert_authority_mapping(value: object) -> object:
    """Convert the allowlisted operational paths inside authority metadata."""
    if isinstance(value, list):
        return [convert_authority_mapping(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, object] = {}
    for key, item in value.items():
        if key in {"path", "archive_path"} and isinstance(item, str):
            result[str(key)] = rewrite_legacy_plan_path(item)
        else:
            result[str(key)] = convert_authority_mapping(item)
    return result


def convert_evidence_references(value: object, mapping: dict[str, str]) -> object:
    """Convert operational evidence-reference fields without broad text replacement."""
    if isinstance(value, list):
        return [convert_evidence_references(item, mapping) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, object] = {}
    for key, item in value.items():
        if key in EVIDENCE_REFERENCE_FIELDS and isinstance(item, str):
            result[str(key)] = rewrite_evidence_reference(item, mapping)
        else:
            result[str(key)] = convert_evidence_references(item, mapping)
    return result


def converted_plan_frontmatter(
    frontmatter: dict[str, Any],
    *,
    active: bool,
    predecessor_sha256: str | None,
    evidence_mapping: dict[str, str],
) -> dict[str, Any]:
    """Convert one lineage Plan and bump only the active Plan revision."""
    converted = copy.deepcopy(frontmatter)
    authority = converted.get("authority")
    if isinstance(authority, dict):
        converted_authority = convert_authority_mapping(authority)
        assert isinstance(converted_authority, dict)
        converted["authority"] = converted_authority
        predecessor = converted_authority.get("predecessor")
        if isinstance(predecessor, dict) and predecessor_sha256 is not None:
            predecessor["sha256"] = predecessor_sha256
    evidence_converted = convert_evidence_references(converted, evidence_mapping)
    assert isinstance(evidence_converted, dict)
    converted = evidence_converted
    if active:
        convert_active_scope_paths(converted)
        bump_revision(converted)
    return converted


def action_upgrade_transaction_paths(
    root: Path,
    transaction_id: str,
) -> tuple[Path, Path, Path, Path]:
    """Return runtime, journal, staging, and local evidence paths for one action upgrade."""
    if LAYOUT_TRANSACTION_RE.fullmatch(transaction_id) is None:
        raise WorkctlError("INVALID_LAYOUT_TRANSACTION_ID")
    transaction = runtime_dir(root) / transaction_id
    journal = transaction / "journal.json"
    staging = transaction / "staging"
    evidence = evidence_dir(root) / "layout-action-upgrades" / transaction_id
    for path in (transaction, journal, staging, evidence):
        reject_symlink_components(root, path)
    return transaction, journal, staging, evidence


def action_upgrade_expected_paths(
    root: Path,
    transaction_id: str,
    active_path: Path | None,
) -> dict[str, object]:
    """Build the exact transaction-owned and activation paths."""
    _transaction, _journal, staging, evidence = action_upgrade_transaction_paths(
        root, transaction_id
    )
    proof = (
        plan_dir(root) / ".migrations" / f"{transaction_id}.yaml"
        if active_path is not None
        else None
    )
    return {
        "staged_plan": (staging / "active-plan.md").as_posix(),
        "staged_version": (staging / "version.yaml").as_posix(),
        "staged_proof": (staging / "proof.yaml").as_posix(),
        "original_plan": (evidence / "active-plan.before.md").as_posix(),
        "original_version": (evidence / "version.before.yaml").as_posix(),
        "target_plan": active_path.as_posix() if active_path is not None else None,
        "target_proof": proof.as_posix() if proof is not None else None,
    }


def action_upgrade_plan_metadata(
    root: Path,
) -> tuple[Path | None, str | None, int | None, str | None, str | None]:
    """Return a validated active Plan snapshot, or an explicit No-Plan snapshot."""
    canonical = plan_dir(root)
    if not canonical.exists() and not canonical.is_symlink():
        return None, None, None, None, None
    if canonical.is_symlink() or not canonical.is_dir():
        raise WorkctlError("ACTION_UPGRADE_PLAN_ROOT_INVALID")
    index = index_path(root)
    reject_symlink_components(root, index)
    if index.is_symlink() or not index.is_file():
        raise WorkctlError("ACTION_UPGRADE_INDEX_INVALID")
    errors = validate_plan(
        root,
        reject_blocking_artifacts=False,
        require_governed=False,
    )
    if errors:
        raise WorkctlError("ACTION_UPGRADE_PLAN_INVALID: " + "; ".join(errors))
    active = active_plan_path(root)
    reject_symlink_components(root, active)
    if active.is_symlink() or not active.is_file() or active.parent != canonical:
        raise WorkctlError("ACTION_UPGRADE_ACTIVE_PLAN_INVALID")
    document = load_plan(active)
    plan_id = document.frontmatter.get("plan_id")
    revision = document.frontmatter.get("revision")
    if (
        not isinstance(plan_id, str)
        or PLAN_ID_RE.fullmatch(plan_id) is None
        or not isinstance(revision, int)
        or revision < 1
    ):
        raise WorkctlError("ACTION_UPGRADE_ACTIVE_PLAN_INVALID")
    return active, plan_id, revision, sha256_file(active), sha256_file(index)


def validate_action_upgrade_journal(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
) -> None:
    """Authenticate every stable field of one committed-layout action upgrade."""
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise WorkctlError("INVALID_ACTION_UPGRADE_JOURNAL")
    _transaction, expected_journal, _staging, _evidence = action_upgrade_transaction_paths(
        root, transaction_id
    )
    active_path_raw = journal.get("active_plan_path")
    active_relative = Path(active_path_raw) if isinstance(active_path_raw, str) else None
    active_path = root / active_relative if active_relative is not None else None
    expected_paths = action_upgrade_expected_paths(root, transaction_id, active_path)
    conversion_table = journal.get("conversion_table")
    plan_fields = (
        journal.get("active_plan_id"),
        journal.get("active_plan_path"),
        journal.get("active_plan_before_sha256"),
        journal.get("active_plan_after_sha256"),
        journal.get("active_plan_revision_before"),
        journal.get("active_plan_revision_after"),
        journal.get("index_sha256"),
        journal.get("proof_relative_path"),
        journal.get("proof_sha256"),
    )
    if (
        journal_path != expected_journal
        or set(journal) != ACTION_UPGRADE_JOURNAL_KEYS
        or journal.get("schema_version") != 1
        or journal.get("kind") != "layout-action-upgrade"
        or journal.get("status")
        not in {
            "preparing",
            "staged",
            "plan-activated",
            "proof-installed",
            "version-pending",
            "committed",
            "aborted",
        }
        or not isinstance(journal.get("created_at"), str)
        or not journal.get("created_at")
        or not isinstance(journal.get("updated_at"), str)
        or not journal.get("updated_at")
        or journal.get("from_action_revision")
        not in (SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS - {LEGACY_MIGRATION_ACTION_REVISION})
        or journal.get("to_action_revision") != LEGACY_MIGRATION_ACTION_REVISION
        or SHA256_RE.fullmatch(str(journal.get("version_before_sha256"))) is None
        or SHA256_RE.fullmatch(str(journal.get("version_after_sha256"))) is None
        or not isinstance(journal.get("git_baseline"), dict)
        or not isinstance(conversion_table, list)
        or sha256_bytes(
            json.dumps(conversion_table, sort_keys=True, separators=(",", ":")).encode()
        )
        != journal.get("conversion_table_sha256")
        or journal.get("paths") != expected_paths
        or not isinstance(journal.get("completed_operations"), list)
    ):
        raise WorkctlError("INVALID_ACTION_UPGRADE_JOURNAL")
    if active_path is None:
        if any(value is not None for value in plan_fields):
            raise WorkctlError("INVALID_ACTION_UPGRADE_JOURNAL")
        if conversion_table:
            raise WorkctlError("INVALID_ACTION_UPGRADE_JOURNAL")
        return
    expected_proof = plan_relative_path(".migrations", f"{transaction_id}.yaml")
    if (
        active_relative is None
        or active_relative.is_absolute()
        or any(part in {"", ".", ".."} for part in active_relative.parts)
        or active_relative.parent != Path(GOVERNANCE_DIR_NAME, PLAN_DIR_NAME)
        or active_path.parent != plan_dir(root)
        or journal.get("active_plan_id") != active_relative.stem
        or PLAN_ID_RE.fullmatch(str(journal.get("active_plan_id"))) is None
        or SHA256_RE.fullmatch(str(journal.get("active_plan_before_sha256"))) is None
        or SHA256_RE.fullmatch(str(journal.get("active_plan_after_sha256"))) is None
        or not isinstance(journal.get("active_plan_revision_before"), int)
        or not isinstance(journal.get("active_plan_revision_after"), int)
        or SHA256_RE.fullmatch(str(journal.get("index_sha256"))) is None
        or journal.get("proof_relative_path") != expected_proof
        or SHA256_RE.fullmatch(str(journal.get("proof_sha256"))) is None
    ):
        raise WorkctlError("INVALID_ACTION_UPGRADE_JOURNAL")
    before_revision = cast(int, journal["active_plan_revision_before"])
    after_revision = cast(int, journal["active_plan_revision_after"])
    before_digest = str(journal["active_plan_before_sha256"])
    after_digest = str(journal["active_plan_after_sha256"])
    if conversion_table:
        expected_conversion = [
            {
                "path": relative_project_path(root, active_path),
                "kind": "active-plan-scope-root",
                "before_sha256": before_digest,
                "after_sha256": after_digest,
            }
        ]
        if (
            conversion_table != expected_conversion
            or after_revision != before_revision + 1
            or after_digest == before_digest
        ):
            raise WorkctlError("INVALID_ACTION_UPGRADE_JOURNAL")
    elif after_revision != before_revision or after_digest != before_digest:
        raise WorkctlError("INVALID_ACTION_UPGRADE_JOURNAL")


def validate_aborted_action_upgrade_journal(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
) -> None:
    """Validate an ignored pre-activation action-upgrade receipt."""
    validate_action_upgrade_journal(root, journal_path, journal)
    if journal.get("status") != "aborted" or journal.get("completed_operations") != [
        "snapshot",
        "preparation-preserved",
    ]:
        raise WorkctlError("INVALID_ABORTED_ACTION_UPGRADE_JOURNAL")


def action_upgrade_proof_payload(
    journal: dict[str, Any],
) -> dict[str, object]:
    """Build the versioned proof for one Plan-bearing action correction."""
    return {
        "schema_version": 1,
        "kind": "layout-action-upgrade-proof",
        "transaction_id": journal["transaction_id"],
        "status": "prepared",
        "from_action_revision": journal["from_action_revision"],
        "to_action_revision": journal["to_action_revision"],
        "active_plan_id": journal["active_plan_id"],
        "active_plan_path": journal["active_plan_path"],
        "active_plan_before_sha256": journal["active_plan_before_sha256"],
        "active_plan_after_sha256": journal["active_plan_after_sha256"],
        "active_plan_revision_before": journal["active_plan_revision_before"],
        "active_plan_revision_after": journal["active_plan_revision_after"],
        "version_before_sha256": journal["version_before_sha256"],
        "version_after_sha256": journal["version_after_sha256"],
        "conversion_table_sha256": journal["conversion_table_sha256"],
        "created_at": journal["created_at"],
    }


def validate_action_upgrade_proof(path: Path, journal: dict[str, Any]) -> None:
    """Bind one staged or installed proof to its transaction journal."""
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("ACTION_UPGRADE_PROOF_MISSING")
    try:
        proof = load_yaml_file(path)
    except (WorkctlError, yaml.YAMLError) as exc:
        raise WorkctlError("ACTION_UPGRADE_PROOF_INVALID") from exc
    if (
        set(proof) != ACTION_UPGRADE_PROOF_KEYS
        or proof != action_upgrade_proof_payload(journal)
        or sha256_file(path) != journal.get("proof_sha256")
    ):
        raise WorkctlError("ACTION_UPGRADE_PROOF_INVALID")


def verify_action_upgrade_staging(root: Path, journal: dict[str, Any]) -> None:
    """Verify staged bytes, original evidence, and current non-governance inputs."""
    transaction_id = str(journal["transaction_id"])
    _transaction, _journal, staging, evidence = action_upgrade_transaction_paths(
        root, transaction_id
    )
    paths = cast(dict[str, object], journal["paths"])
    staged_version = Path(str(paths["staged_version"]))
    original_version = Path(str(paths["original_version"]))
    if (
        staged_version != staging / "version.yaml"
        or staged_version.is_symlink()
        or not staged_version.is_file()
        or sha256_file(staged_version) != journal.get("version_after_sha256")
        or original_version != evidence / "version.before.yaml"
        or original_version.is_symlink()
        or not original_version.is_file()
        or sha256_file(original_version) != journal.get("version_before_sha256")
        or current_layout_git_baseline(root) != journal.get("git_baseline")
    ):
        raise WorkctlError("ACTION_UPGRADE_STAGING_DRIFT")
    try:
        original_version_payload = load_yaml_file(original_version)
        staged_version_payload = load_yaml_file(staged_version)
    except (WorkctlError, yaml.YAMLError) as exc:
        raise WorkctlError("ACTION_UPGRADE_STAGING_DRIFT") from exc
    expected_version_payload = copy.deepcopy(original_version_payload)
    expected_version_payload["legacy_migration_action_revision"] = LEGACY_MIGRATION_ACTION_REVISION
    if (
        original_version_payload.get("legacy_migration_action_revision")
        != journal.get("from_action_revision")
        or staged_version_payload != expected_version_payload
        or staged_version_payload.get("legacy_migration_action_revision")
        != journal.get("to_action_revision")
    ):
        raise WorkctlError("ACTION_UPGRADE_STAGING_DRIFT")
    active_path_raw = journal.get("active_plan_path")
    if active_path_raw is None:
        return
    staged_plan = Path(str(paths["staged_plan"]))
    original_plan = Path(str(paths["original_plan"]))
    staged_proof = Path(str(paths["staged_proof"]))
    if (
        staged_plan != staging / "active-plan.md"
        or staged_plan.is_symlink()
        or not staged_plan.is_file()
        or sha256_file(staged_plan) != journal.get("active_plan_after_sha256")
        or original_plan != evidence / "active-plan.before.md"
        or original_plan.is_symlink()
        or not original_plan.is_file()
        or sha256_file(original_plan) != journal.get("active_plan_before_sha256")
        or staged_proof != staging / "proof.yaml"
        or index_path(root).is_symlink()
        or not index_path(root).is_file()
        or sha256_file(index_path(root)) != journal.get("index_sha256")
    ):
        raise WorkctlError("ACTION_UPGRADE_STAGING_DRIFT")
    original_document = load_plan(original_plan)
    expected_frontmatter = copy.deepcopy(original_document.frontmatter)
    convert_active_scope_paths(expected_frontmatter)
    if expected_frontmatter != original_document.frontmatter:
        expected_frontmatter["revision"] = journal["active_plan_revision_after"]
        expected_frontmatter["updated_at"] = journal["created_at"]
        expected_plan_bytes = dump_plan(
            PlanDocument(original_plan, expected_frontmatter, original_document.body)
        ).encode()
    else:
        expected_plan_bytes = original_plan.read_bytes()
    if staged_plan.read_bytes() != expected_plan_bytes:
        raise WorkctlError("ACTION_UPGRADE_STAGING_DRIFT")
    validate_action_upgrade_proof(staged_proof, journal)


def verify_action_upgrade_target_plan(
    root: Path,
    journal: dict[str, Any],
    *,
    allow_before: bool,
) -> str:
    """Return before/after for the bound active Plan and reject every other byte state."""
    active_path_raw = journal.get("active_plan_path")
    if active_path_raw is None:
        if plan_dir(root).exists() or plan_dir(root).is_symlink():
            raise WorkctlError("ACTION_UPGRADE_PLAN_APPEARED")
        return "after"
    active = root / str(active_path_raw)
    reject_symlink_components(root, active)
    if active.is_symlink() or not active.is_file():
        raise WorkctlError("ACTION_UPGRADE_ACTIVE_PLAN_MISSING")
    digest = sha256_file(active)
    if digest == journal.get("active_plan_after_sha256"):
        return "after"
    if allow_before and digest == journal.get("active_plan_before_sha256"):
        return "before"
    raise WorkctlError("ACTION_UPGRADE_ACTIVE_PLAN_DRIFT")


def prepare_action_upgrade_transaction(
    root: Path,
) -> tuple[Path, dict[str, Any]]:
    """Snapshot and stage one correction from a supported committed action revision."""
    version = version_path(root)
    errors = layout_version_errors(root)
    if errors:
        raise WorkctlError("ACTION_UPGRADE_VERSION_INVALID: " + "; ".join(errors))
    version_payload = load_yaml_file(version)
    from_revision = version_payload.get("legacy_migration_action_revision")
    if from_revision == LEGACY_MIGRATION_ACTION_REVISION:
        raise WorkctlError("ACTION_UPGRADE_NOT_REQUIRED")
    if from_revision not in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS:
        raise WorkctlError("ACTION_UPGRADE_REVISION_UNSUPPORTED")
    created_at = utc_now()
    version_before_bytes = version.read_bytes()
    version_before_sha256 = sha256_bytes(version_before_bytes)
    version_after_payload = copy.deepcopy(version_payload)
    version_after_payload["legacy_migration_action_revision"] = LEGACY_MIGRATION_ACTION_REVISION
    if {
        key: value
        for key, value in version_after_payload.items()
        if key != "legacy_migration_action_revision"
    } != {
        key: value
        for key, value in version_payload.items()
        if key != "legacy_migration_action_revision"
    }:
        raise WorkctlError("ACTION_UPGRADE_VERSION_TRANSFORM_INVALID")
    version_after_bytes = yaml.safe_dump(version_after_payload, sort_keys=False).encode()
    version_after_sha256 = sha256_bytes(version_after_bytes)
    active, plan_id, plan_revision, plan_before_sha256, index_sha256 = action_upgrade_plan_metadata(
        root
    )
    conversion_table: list[dict[str, object]] = []
    active_after_bytes: bytes | None = None
    active_after_sha256: str | None = None
    active_revision_after: int | None = None
    if active is not None:
        document = load_plan(active)
        converted = copy.deepcopy(document.frontmatter)
        convert_active_scope_paths(converted)
        if converted != document.frontmatter:
            converted["revision"] = cast(int, plan_revision) + 1
            converted["updated_at"] = created_at
            active_after_bytes = dump_plan(PlanDocument(active, converted, document.body)).encode()
            active_revision_after = cast(int, converted["revision"])
        else:
            active_after_bytes = active.read_bytes()
            active_revision_after = plan_revision
        active_after_sha256 = sha256_bytes(active_after_bytes)
        if active_after_sha256 != plan_before_sha256:
            conversion_table.append(
                {
                    "path": relative_project_path(root, active),
                    "kind": "active-plan-scope-root",
                    "before_sha256": plan_before_sha256,
                    "after_sha256": active_after_sha256,
                }
            )
    conversion_digest = sha256_bytes(
        json.dumps(conversion_table, sort_keys=True, separators=(",", ":")).encode()
    )
    transaction_id = new_layout_transaction_id(version_before_sha256)
    transaction, journal_path, staging, evidence = action_upgrade_transaction_paths(
        root, transaction_id
    )
    if transaction.exists() or evidence.exists():
        raise WorkctlError(f"LAYOUT_TRANSACTION_EXISTS: {transaction_id}")
    proof_relative = (
        plan_relative_path(".migrations", f"{transaction_id}.yaml") if active is not None else None
    )
    journal: dict[str, Any] = {
        "schema_version": 1,
        "kind": "layout-action-upgrade",
        "transaction_id": transaction_id,
        "status": "preparing",
        "created_at": created_at,
        "updated_at": created_at,
        "from_action_revision": from_revision,
        "to_action_revision": LEGACY_MIGRATION_ACTION_REVISION,
        "version_before_sha256": version_before_sha256,
        "version_after_sha256": version_after_sha256,
        "git_baseline": current_layout_git_baseline(root),
        "active_plan_id": plan_id,
        "active_plan_path": (relative_project_path(root, active) if active is not None else None),
        "active_plan_before_sha256": plan_before_sha256,
        "active_plan_after_sha256": active_after_sha256,
        "active_plan_revision_before": plan_revision,
        "active_plan_revision_after": active_revision_after,
        "index_sha256": index_sha256,
        "conversion_table": conversion_table,
        "conversion_table_sha256": conversion_digest,
        "proof_relative_path": proof_relative,
        "proof_sha256": None,
        "paths": action_upgrade_expected_paths(root, transaction_id, active),
        "completed_operations": ["snapshot"],
    }
    if active is not None:
        proof_bytes = yaml.safe_dump(
            action_upgrade_proof_payload(journal),
            sort_keys=False,
        ).encode()
        journal["proof_sha256"] = sha256_bytes(proof_bytes)
    else:
        proof_bytes = None
    ensure_directory_durable(transaction)
    write_layout_journal(journal_path, journal)
    validate_action_upgrade_journal(root, journal_path, journal)
    layout_test_interrupt("action-upgrade-preparing")
    ensure_directory_durable(staging)
    ensure_directory_durable(evidence)
    write_atomic_bytes(evidence / "version.before.yaml", version_before_bytes)
    write_atomic_bytes(staging / "version.yaml", version_after_bytes)
    if active is not None and active_after_bytes is not None and proof_bytes is not None:
        write_atomic_bytes(evidence / "active-plan.before.md", active.read_bytes())
        write_atomic_bytes(staging / "active-plan.md", active_after_bytes)
        write_atomic_bytes(staging / "proof.yaml", proof_bytes)
        staged_document = load_plan(staging / "active-plan.md")
        staged_errors = validate_frontmatter(
            staged_document.frontmatter,
            reject_blocking_artifacts=False,
        )
        if not staged_document.body.strip():
            staged_errors.append("Plan body must not be empty")
        if staged_errors:
            raise WorkctlError("ACTION_UPGRADE_STAGED_PLAN_INVALID: " + "; ".join(staged_errors))
    fsync_tree(staging)
    fsync_tree(evidence)
    journal["status"] = "staged"
    journal["completed_operations"] = [
        "snapshot",
        "staging",
        "conversion",
        "staged-validation",
    ]
    write_layout_journal(journal_path, journal)
    validate_action_upgrade_journal(root, journal_path, journal)
    verify_action_upgrade_staging(root, journal)
    return journal_path, journal


def abandon_action_upgrade_preparation(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
) -> None:
    """Preserve a pre-activation interruption and release the next retry."""
    validate_action_upgrade_journal(root, journal_path, journal)
    if journal.get("status") != "preparing":
        raise WorkctlError("ACTION_UPGRADE_PREPARATION_NOT_ABORTABLE")
    if sha256_file(version_path(root)) != journal.get(
        "version_before_sha256"
    ) or current_layout_git_baseline(root) != journal.get("git_baseline"):
        raise WorkctlError("ACTION_UPGRADE_INPUT_DRIFT")
    active_path_raw = journal.get("active_plan_path")
    if active_path_raw is not None:
        active = root / str(active_path_raw)
        if (
            active.is_symlink()
            or not active.is_file()
            or sha256_file(active) != journal.get("active_plan_before_sha256")
        ):
            raise WorkctlError("ACTION_UPGRADE_INPUT_DRIFT")
    elif plan_dir(root).exists() or plan_dir(root).is_symlink():
        raise WorkctlError("ACTION_UPGRADE_INPUT_DRIFT")
    journal["status"] = "aborted"
    journal["completed_operations"] = ["snapshot", "preparation-preserved"]
    write_layout_journal(journal_path, journal)
    validate_aborted_action_upgrade_journal(root, journal_path, journal)
    print(f"LAYOUT_ACTION_UPGRADE_PREPARATION_PRESERVED {journal['transaction_id']}")


def resume_action_upgrade_transaction(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
) -> None:
    """Deterministically forward one staged action correction to version-last commit."""
    validate_action_upgrade_journal(root, journal_path, journal)
    if journal.get("status") == "committed":
        print(f"LAYOUT_ACTION_UPGRADE_ALREADY_COMMITTED {journal['transaction_id']}")
        return
    if journal.get("status") in {"preparing", "aborted"}:
        raise WorkctlError("ACTION_UPGRADE_TRANSACTION_NOT_RESUMABLE")
    verify_action_upgrade_staging(root, journal)
    paths = cast(dict[str, object], journal["paths"])
    version_digest = sha256_file(version_path(root))
    if version_digest not in {
        journal.get("version_before_sha256"),
        journal.get("version_after_sha256"),
    }:
        raise WorkctlError("ACTION_UPGRADE_VERSION_DRIFT")
    status = str(journal["status"])
    if status == "staged":
        if version_digest != journal.get("version_before_sha256"):
            raise WorkctlError("ACTION_UPGRADE_VERSION_ACTIVATED_EARLY")
        plan_state = verify_action_upgrade_target_plan(root, journal, allow_before=True)
        if plan_state == "before" and journal.get("active_plan_path") is not None:
            write_atomic_bytes(
                root / str(journal["active_plan_path"]),
                Path(str(paths["staged_plan"])).read_bytes(),
            )
            layout_test_interrupt("action-upgrade-plan")
        journal["status"] = "plan-activated"
        journal["completed_operations"] = [
            *journal["completed_operations"],
            "plan-activation",
        ]
        write_layout_journal(journal_path, journal)
    status = str(journal["status"])
    if status == "plan-activated":
        verify_action_upgrade_target_plan(root, journal, allow_before=False)
        proof_relative = journal.get("proof_relative_path")
        if proof_relative is not None:
            proof_target = root / str(proof_relative)
            reject_symlink_components(root, proof_target)
            if proof_target.exists() or proof_target.is_symlink():
                if (
                    proof_target.is_symlink()
                    or not proof_target.is_file()
                    or sha256_file(proof_target) != journal.get("proof_sha256")
                ):
                    raise WorkctlError("ACTION_UPGRADE_PROOF_CONFLICT")
            else:
                write_atomic_bytes(
                    proof_target,
                    Path(str(paths["staged_proof"])).read_bytes(),
                )
                layout_test_interrupt("action-upgrade-proof")
            validate_action_upgrade_proof(proof_target, journal)
        journal["status"] = "proof-installed"
        journal["completed_operations"] = [
            *journal["completed_operations"],
            "proof-install",
        ]
        write_layout_journal(journal_path, journal)
    status = str(journal["status"])
    if status == "proof-installed":
        verify_action_upgrade_target_plan(root, journal, allow_before=False)
        if index_path(root).exists():
            errors = validate_plan(
                root,
                reject_blocking_artifacts=False,
                require_governed=False,
            )
            if errors:
                raise WorkctlError("ACTION_UPGRADE_ACTIVATED_PLAN_INVALID: " + "; ".join(errors))
        journal["status"] = "version-pending"
        journal["completed_operations"] = [
            *journal["completed_operations"],
            "final-validation",
        ]
        write_layout_journal(journal_path, journal)
    if str(journal["status"]) == "version-pending":
        verify_action_upgrade_target_plan(root, journal, allow_before=False)
        version_digest = sha256_file(version_path(root))
        if version_digest == journal.get("version_before_sha256"):
            write_atomic_bytes(
                version_path(root),
                Path(str(paths["staged_version"])).read_bytes(),
            )
            layout_test_interrupt("action-upgrade-version")
        elif version_digest != journal.get("version_after_sha256"):
            raise WorkctlError("ACTION_UPGRADE_VERSION_DRIFT")
        version_errors = layout_version_errors(root)
        if version_errors:
            raise WorkctlError("ACTION_UPGRADE_VERSION_INVALID: " + "; ".join(version_errors))
        journal["status"] = "committed"
        journal["completed_operations"] = [
            *journal["completed_operations"],
            "version-commit",
        ]
        write_layout_journal(journal_path, journal)
    final = inspect_layout(root)
    if final.state != "LAYOUT_READY":
        raise WorkctlError(
            f"ACTION_UPGRADE_COMMITTED_BUT_INVALID: {final.state}; " + "; ".join(final.blockers)
        )
    print(f"LAYOUT_ACTION_UPGRADED {journal['transaction_id']}")


def migrate_layout_action_upgrade(root: Path) -> None:
    """Execute the required committed-layout action correction."""
    journal_path, journal = prepare_action_upgrade_transaction(root)
    layout_test_interrupt("action-upgrade-staged")
    resume_action_upgrade_transaction(root, journal_path, journal)


def lineage_plan_paths(staged_plan: Path, active_name: str) -> list[Path]:
    """Return predecessor lineage from oldest to active within a staged tree."""
    chain: list[Path] = []
    seen: set[Path] = set()
    current = staged_plan / active_name
    while True:
        resolved = current.resolve()
        if resolved in seen:
            raise WorkctlError("LAYOUT_LINEAGE_CYCLE")
        try:
            resolved.relative_to(staged_plan.resolve())
        except ValueError as exc:
            raise WorkctlError("LAYOUT_LINEAGE_ESCAPES_STAGING") from exc
        if not current.is_file() or current.is_symlink():
            raise WorkctlError(f"LAYOUT_LINEAGE_MISSING: {current.name}")
        seen.add(resolved)
        chain.append(current)
        doc = load_plan(current)
        authority = doc.frontmatter.get("authority")
        predecessor = authority.get("predecessor") if isinstance(authority, dict) else None
        raw_path = predecessor.get("path") if isinstance(predecessor, dict) else None
        if not isinstance(raw_path, str):
            break
        raw_predecessor = Path(raw_path)
        predecessor_name = raw_predecessor.name
        allowed_paths = {
            predecessor_name,
            (Path(PLAN_DIR_NAME) / predecessor_name).as_posix(),
            (Path(GOVERNANCE_DIR_NAME) / PLAN_DIR_NAME / predecessor_name).as_posix(),
        }
        if (
            raw_predecessor.is_absolute()
            or raw_path not in allowed_paths
            or PLAN_ID_RE.fullmatch(Path(predecessor_name).stem) is None
        ):
            raise WorkctlError("LAYOUT_LINEAGE_PATH_UNSUPPORTED")
        current = staged_plan / predecessor_name
    chain.reverse()
    return chain


def record_conversion(
    conversions: list[dict[str, object]],
    *,
    path: str,
    kind: str,
    before_sha256: str,
    after_sha256: str,
) -> None:
    """Append one exact byte conversion record when content changed."""
    if before_sha256 != after_sha256:
        conversions.append(
            {
                "path": path,
                "kind": kind,
                "before_sha256": before_sha256,
                "after_sha256": after_sha256,
            }
        )


def convert_lineage_plans(
    staged_plan: Path,
    active_name: str,
    conversions: list[dict[str, object]],
    evidence_mapping: dict[str, str],
) -> None:
    """Convert current lineage paths and update recursive predecessor hashes."""
    predecessor_sha256: str | None = None
    lineage = lineage_plan_paths(staged_plan, active_name)
    for path in lineage:
        before = sha256_file(path)
        doc = load_plan(path)
        converted = converted_plan_frontmatter(
            doc.frontmatter,
            active=path.name == active_name,
            predecessor_sha256=predecessor_sha256,
            evidence_mapping=evidence_mapping,
        )
        write_atomic(path, dump_plan(PlanDocument(path, converted, doc.body)))
        after = sha256_file(path)
        record_conversion(
            conversions,
            path=path.relative_to(staged_plan).as_posix(),
            kind="active-plan" if path.name == active_name else "lineage-plan",
            before_sha256=before,
            after_sha256=after,
        )
        predecessor_sha256 = after


JOURNAL_PATH_FIELDS = {
    "path",
    "archive_path",
    "target_path",
    "pointer_path",
    "canonical_path",
    "staged_prepared_plan",
    "staged_plan",
    "staged_path",
    "staged_index",
}


def convert_operational_journal_value(
    value: object,
    evidence_mapping: dict[str, str],
    key: str | None = None,
) -> object:
    """Convert allowlisted fields in current migration and rollover journals."""
    if isinstance(value, list):
        return [convert_operational_journal_value(item, evidence_mapping) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): convert_operational_journal_value(item, evidence_mapping, str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, str) and key in JOURNAL_PATH_FIELDS:
        return rewrite_legacy_plan_path(value)
    if isinstance(value, str) and key == "evidence_ref":
        return rewrite_evidence_reference(value, evidence_mapping)
    return value


def convert_operational_journals(
    staged_plan: Path,
    conversions: list[dict[str, object]],
    evidence_mapping: dict[str, str],
) -> None:
    """Convert completed operational journal fields while preserving source evidence."""
    for directory_name, pattern in ((".migrations", "MIG-*.yaml"), (".rollovers", "ROL-*.yaml")):
        directory = staged_plan / directory_name
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in sorted(directory.glob(pattern)):
            before = sha256_file(path)
            payload = load_yaml_file(path)
            converted = convert_operational_journal_value(payload, evidence_mapping)
            assert isinstance(converted, dict)
            write_atomic(path, yaml.safe_dump(converted, sort_keys=False))
            record_conversion(
                conversions,
                path=path.relative_to(staged_plan).as_posix(),
                kind="operational-journal",
                before_sha256=before,
                after_sha256=sha256_file(path),
            )


def collect_evidence_references(value: object) -> set[str]:
    """Collect exact operational evidence references from Plan frontmatter."""
    found: set[str] = set()
    if isinstance(value, list):
        for item in value:
            found.update(collect_evidence_references(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in EVIDENCE_REFERENCE_FIELDS and isinstance(item, str):
                found.add(item)
            else:
                found.update(collect_evidence_references(item))
    return found


def convertible_evidence_references(staged_plan: Path, active_name: str) -> set[str]:
    """Collect references from exactly the lineage and journals being converted."""
    references: set[str] = set()
    for path in lineage_plan_paths(staged_plan, active_name):
        references.update(collect_evidence_references(load_plan(path).frontmatter))
    for directory_name, pattern in ((".migrations", "MIG-*.yaml"), (".rollovers", "ROL-*.yaml")):
        directory = staged_plan / directory_name
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in sorted(directory.glob(pattern)):
            references.update(collect_evidence_references(load_yaml_file(path)))
    return references


def legacy_evidence_reference_mapping(
    root: Path, staged_plan: Path, active_name: str
) -> tuple[dict[str, str], set[Path]]:
    """Bind converted legacy references to exact staged Plan or source-log targets."""
    legacy_logs = legacy_logs_dir(root)
    mapping: dict[str, str] = {}
    referenced_files: set[Path] = set()
    for reference in sorted(convertible_evidence_references(staged_plan, active_name)):
        if reference == "project:_Plan" or reference.startswith("project:_Plan/"):
            relative_text = reference.removeprefix("project:_Plan").removeprefix("/")
            relative = Path(relative_text)
            if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
                raise WorkctlError(f"LAYOUT_PROJECT_REFERENCE_INVALID: {reference}")
            candidate = staged_plan.joinpath(*relative.parts)
            reject_symlink_components(staged_plan, candidate)
            try:
                candidate.resolve().relative_to(staged_plan.resolve())
            except ValueError as exc:
                raise WorkctlError(f"LAYOUT_PROJECT_REFERENCE_INVALID: {reference}") from exc
            if candidate.is_symlink() or not candidate.exists():
                raise WorkctlError(f"LAYOUT_PROJECT_REFERENCE_MISSING: {reference}")
            mapping[reference] = "project:" + plan_relative_path(*relative.parts)
            continue
        if not reference.startswith("evidence:.logs/"):
            continue
        relative_text = reference.removeprefix("evidence:.logs/")
        relative = Path(relative_text)
        if not relative_text or relative.is_absolute():
            raise WorkctlError(f"LAYOUT_EVIDENCE_REFERENCE_INVALID: {reference}")
        candidate = legacy_logs / relative
        reject_symlink_components(root, candidate)
        try:
            resolved = candidate.resolve()
            resolved.relative_to(legacy_logs.resolve())
        except ValueError as exc:
            raise WorkctlError(f"LAYOUT_EVIDENCE_REFERENCE_INVALID: {reference}") from exc
        if (
            not legacy_logs.is_dir()
            or legacy_logs.is_symlink()
            or not candidate.is_file()
            or candidate.is_symlink()
        ):
            raise WorkctlError(f"LAYOUT_EVIDENCE_REFERENCE_MISSING: {reference}")
        mapping[reference] = "evidence:.work-governance/logs/" + relative.as_posix()
        referenced_files.add(resolved)
    return mapping, referenced_files


def jsonl_belongs_to_plan(path: Path, plan_ids: set[str]) -> bool:
    """Return whether every non-empty JSONL record names a registered Plan."""
    saw_record = False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict) or payload.get("plan_id") not in plan_ids:
                return False
            saw_record = True
    except (OSError, json.JSONDecodeError):
        return False
    return saw_record


def proven_log_files(root: Path, staged_plan: Path, referenced_files: set[Path]) -> list[Path]:
    """Return only legacy log files with deterministic Work Governance ownership."""
    legacy_logs = legacy_logs_dir(root)
    if not legacy_logs.is_dir() or legacy_logs.is_symlink():
        return []
    index = load_yaml_file(staged_plan / "index.yaml")
    plan_ids = {
        str(item["id"])
        for item in index.get("plans", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    proven = set(referenced_files)
    for candidate in sorted(legacy_logs.rglob("*")):
        if not candidate.is_file() or candidate.is_symlink():
            continue
        relative = candidate.relative_to(legacy_logs)
        if (relative.parts and relative.parts[0] in plan_ids) or (
            candidate.suffix == ".jsonl" and jsonl_belongs_to_plan(candidate, plan_ids)
        ):
            proven.add(candidate.resolve())
        elif candidate.suffix == ".json":
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("plan_id") in plan_ids
                and isinstance(payload.get("schema_version"), int)
            ):
                proven.add(candidate.resolve())
    return sorted(proven)


def stage_proven_logs(
    root: Path, proven_sources: list[Path], staging: Path
) -> list[dict[str, object]]:
    """Stage only proven governance log files and record exact source hashes."""
    records: list[dict[str, object]] = []
    target_root = staging / "logs"
    legacy_logs = legacy_logs_dir(root)
    for source in proven_sources:
        relative = source.relative_to(legacy_logs.resolve())
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append(
            {
                "source": (Path(".logs") / relative).as_posix(),
                "target": (Path(GOVERNANCE_DIR_NAME) / "logs" / relative).as_posix(),
                "sha256": sha256_file(source),
                "staged_path": target.as_posix(),
            }
        )
    return records


def proposal_tree_manifest(legacy_plan: Path) -> list[dict[str, object]]:
    """Return the exact legacy proposal side-tree manifest, or an empty manifest."""
    proposals = legacy_plan / "proposals"
    if not proposals.exists() and not proposals.is_symlink():
        return []
    return tree_manifest(proposals)


def staged_proposal_records(staged_proposals: Path) -> list[dict[str, object]]:
    """Describe each staged reconciliation proposal for idempotent activation."""
    if not staged_proposals.exists() and not staged_proposals.is_symlink():
        return []
    if staged_proposals.is_symlink() or not staged_proposals.is_dir():
        raise WorkctlError("STAGED_LAYOUT_PROPOSALS_INVALID")
    records: list[dict[str, object]] = []
    for proposal in sorted(staged_proposals.iterdir(), key=lambda item: item.name):
        if (
            proposal.is_symlink()
            or not proposal.is_dir()
            or MIGRATION_ID_RE.fullmatch(proposal.name) is None
        ):
            raise WorkctlError("STAGED_LAYOUT_PROPOSALS_INVALID")
        manifest = tree_manifest(proposal)
        records.append(
            {
                "migration_id": proposal.name,
                "manifest": manifest,
                "manifest_sha256": manifest_sha256(manifest),
                "staged_path": proposal.as_posix(),
                "target": (Path(GOVERNANCE_DIR_NAME) / "proposals" / proposal.name).as_posix(),
            }
        )
    return records


def validate_staged_plan(staged_plan: Path, active_name: str) -> None:
    """Validate staged schema, index, and recursive predecessor hashes before activation."""
    index = load_yaml_file(staged_plan / "index.yaml")
    doc = load_plan(staged_plan / active_name)
    errors = validate_frontmatter(doc.frontmatter, reject_blocking_artifacts=True)
    if index.get("active_plan_id") != doc.frontmatter.get("plan_id"):
        errors.append("staged index and active Plan IDs differ")
    lineage = lineage_plan_paths(staged_plan, active_name)
    for child_path in lineage[1:]:
        child = load_plan(child_path)
        authority = child.frontmatter.get("authority")
        predecessor = authority.get("predecessor") if isinstance(authority, dict) else None
        raw_path = predecessor.get("path") if isinstance(predecessor, dict) else None
        expected_sha = predecessor.get("sha256") if isinstance(predecessor, dict) else None
        if not isinstance(raw_path, str):
            errors.append(f"staged predecessor path missing: {child_path.name}")
            continue
        parent = staged_plan / Path(raw_path).name
        if not parent.is_file() or sha256_file(parent) != expected_sha:
            errors.append(f"staged predecessor hash mismatch: {child_path.name}")
    if errors:
        raise WorkctlError("STAGED_LAYOUT_INVALID: " + "; ".join(errors))


def prepare_layout_transaction(
    root: Path, legacy: LegacyLayoutReport
) -> tuple[Path, dict[str, Any]]:
    """Snapshot, copy, convert, and validate a durable layout transaction."""
    if legacy.manifest_sha256 is None or legacy.active_plan_path is None:
        raise WorkctlError("LEGACY_LAYOUT_SNAPSHOT_INCOMPLETE")
    transaction_id = new_layout_transaction_id(legacy.manifest_sha256)
    transaction, journal_path, staging, backup, evidence, _guard = layout_transaction_paths(
        root, transaction_id
    )
    if transaction.exists() or evidence.exists():
        raise WorkctlError(f"LAYOUT_TRANSACTION_EXISTS: {transaction_id}")
    ensure_layout_gitignore(root)
    source_manifest = tree_manifest(legacy_plan_dir(root), exclude_names={".workctl.lock"})
    source_digest = manifest_sha256(source_manifest)
    if source_digest != legacy.manifest_sha256:
        raise WorkctlError("LEGACY_LAYOUT_INPUT_DRIFT")
    legacy_proposals_manifest = proposal_manifest_from_plan_manifest(source_manifest)
    if proposal_tree_manifest(legacy_plan_dir(root)) != legacy_proposals_manifest:
        raise WorkctlError("LEGACY_PROPOSALS_INPUT_DRIFT")
    legacy_proposals_digest = manifest_sha256(legacy_proposals_manifest)
    git_baseline = current_layout_git_baseline(root)
    evidence_mapping, referenced_logs = legacy_evidence_reference_mapping(
        root, legacy_plan_dir(root), legacy.active_plan_path
    )
    proven_logs = proven_log_files(root, legacy_plan_dir(root), referenced_logs)
    planned_logs = [
        {
            "path": source.relative_to(legacy_logs_dir(root).resolve()).as_posix(),
            "sha256": sha256_file(source),
        }
        for source in proven_logs
    ]
    adoption = legacy_adoption_path(root)
    if adoption.is_symlink() or not adoption.is_file():
        raise WorkctlError("LEGACY_ADOPTION_RECEIPT_MISSING")
    adoption_sha256 = sha256_file(adoption)
    ensure_directory_durable(transaction)
    staged_plan = staging / PLAN_DIR_NAME
    staged_proposals = staging / "proposals"
    original_plan = evidence / f"legacy-{PLAN_DIR_NAME}"
    journal: dict[str, Any] = {
        "schema_version": 1,
        "kind": "layout-migration",
        "transaction_id": transaction_id,
        "status": "preparing",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "active_plan_id": legacy.active_plan_id,
        "active_plan_path": legacy.active_plan_path,
        "legacy_manifest": source_manifest,
        "legacy_manifest_sha256": source_digest,
        "legacy_proposals_manifest": legacy_proposals_manifest,
        "legacy_proposals_sha256": legacy_proposals_digest,
        "legacy_adoption_sha256": adoption_sha256,
        "git_baseline": git_baseline,
        "planned_log_files": planned_logs,
        "paths": {
            "staged_plan": staged_plan.as_posix(),
            "staged_proposals": staged_proposals.as_posix(),
            "target_proposals": proposals_dir(root).as_posix(),
            "backup_plan": (backup / PLAN_DIR_NAME).as_posix(),
            "original_evidence": original_plan.as_posix(),
        },
        "completed_operations": ["snapshot"],
    }
    write_layout_journal(journal_path, journal)
    layout_test_interrupt("preparing")
    ensure_directory_durable(staging)
    ensure_directory_durable(backup)
    ensure_directory_durable(evidence.parent)
    shutil.copytree(
        legacy_plan_dir(root),
        staged_plan,
        ignore=shutil.ignore_patterns(".workctl.lock"),
    )
    layout_test_interrupt("legacy-plan-staging")
    shutil.copytree(
        legacy_plan_dir(root),
        original_plan,
        ignore=shutil.ignore_patterns(".workctl.lock"),
    )
    staged_plan_proposals = staged_plan / "proposals"
    if staged_plan_proposals.exists() or staged_plan_proposals.is_symlink():
        if staged_plan_proposals.is_symlink() or not staged_plan_proposals.is_dir():
            raise WorkctlError("STAGED_LAYOUT_PROPOSALS_INVALID")
        durable_replace(staged_plan_proposals, staged_proposals)
        layout_test_interrupt("proposal-staging")
    proposal_records = staged_proposal_records(staged_proposals)
    if manifest_sha256(proposal_tree_manifest(staging)) != legacy_proposals_digest:
        raise WorkctlError("STAGED_LAYOUT_PROPOSALS_MANIFEST_MISMATCH")
    conversions: list[dict[str, object]] = []
    convert_lineage_plans(
        staged_plan,
        legacy.active_plan_path,
        conversions,
        evidence_mapping,
    )
    convert_operational_journals(staged_plan, conversions, evidence_mapping)
    log_files = stage_proven_logs(root, proven_logs, staging)
    proof_dir = staged_plan / ".migrations"
    proof_dir.mkdir(parents=True, exist_ok=True)
    conversion_digest = sha256_bytes(
        json.dumps(conversions, sort_keys=True, separators=(",", ":")).encode()
    )
    proof = {
        "schema_version": 1,
        "kind": "layout-migration-proof",
        "transaction_id": transaction_id,
        "status": "prepared",
        "legacy_manifest_sha256": source_digest,
        "legacy_adoption_sha256": adoption_sha256,
        "conversion_table_sha256": conversion_digest,
        "legacy_proposals_sha256": legacy_proposals_digest,
        "new_proposals_baseline_sha256": legacy_proposals_digest,
        "created_at": utc_now(),
    }
    write_atomic(
        proof_dir / f"{transaction_id}.yaml",
        yaml.safe_dump(proof, sort_keys=False),
    )
    validate_staged_plan(staged_plan, legacy.active_plan_path)
    target_manifest = tree_manifest(staged_plan, exclude_names={".workctl.lock"})
    target_digest = manifest_sha256(target_manifest)
    fsync_tree(staging)
    fsync_directory(staging.parent)
    fsync_tree(evidence)
    fsync_directory(evidence.parent)
    journal.pop("planned_log_files")
    journal.update(
        {
            "status": "staged",
            "new_layout_manifest": target_manifest,
            "new_layout_baseline_sha256": target_digest,
            "conversion_table": conversions,
            "conversion_table_sha256": conversion_digest,
            "log_files": log_files,
            "proposal_trees": proposal_records,
            "new_proposals_baseline_sha256": legacy_proposals_digest,
            "completed_operations": ["snapshot", "staging", "conversion", "staged-validation"],
        }
    )
    write_layout_journal(journal_path, journal)
    return journal_path, journal


def verify_layout_inputs(root: Path, journal: dict[str, Any]) -> None:
    """Reject every source, adoption, log, or Git drift before activation."""
    legacy = legacy_plan_dir(root)
    if not legacy.is_dir() or legacy.is_symlink():
        raise WorkctlError("LEGACY_LAYOUT_INPUT_MISSING")
    actual_manifest = tree_manifest(legacy, exclude_names={".workctl.lock"})
    if manifest_sha256(actual_manifest) != journal.get("legacy_manifest_sha256"):
        raise WorkctlError("LEGACY_LAYOUT_INPUT_DRIFT")
    if manifest_sha256(proposal_tree_manifest(legacy)) != journal.get("legacy_proposals_sha256"):
        raise WorkctlError("LEGACY_PROPOSALS_INPUT_DRIFT")
    if current_layout_git_baseline(root) != journal.get("git_baseline"):
        raise WorkctlError("LAYOUT_GIT_BASELINE_DRIFT")
    adoption = legacy_adoption_path(root)
    if (
        adoption.is_symlink()
        or not adoption.is_file()
        or sha256_file(adoption) != journal.get("legacy_adoption_sha256")
    ):
        raise WorkctlError("LEGACY_ADOPTION_RECEIPT_DRIFT")
    for record in journal.get("log_files", []):
        if not isinstance(record, dict):
            raise WorkctlError("INVALID_LAYOUT_JOURNAL")
        source = root / str(record.get("source"))
        if (
            source.is_symlink()
            or not source.is_file()
            or sha256_file(source) != record.get("sha256")
        ):
            raise WorkctlError(f"LAYOUT_LOG_INPUT_DRIFT: {record.get('source')}")


def layout_proposal_records(
    root: Path,
    journal: dict[str, Any],
) -> list[dict[str, object]]:
    """Validate and return proposal activation records from a layout journal."""
    raw_records = journal.get("proposal_trees")
    if not isinstance(raw_records, list):
        raise WorkctlError("INVALID_LAYOUT_PROPOSAL_JOURNAL")
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise WorkctlError("INVALID_LAYOUT_PROPOSAL_JOURNAL")
    _transaction, _journal, staging, _backup, _evidence, _guard = layout_transaction_paths(
        root,
        transaction_id,
    )
    seen: set[str] = set()
    records: list[dict[str, object]] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict) or set(raw_record) != {
            "migration_id",
            "manifest",
            "manifest_sha256",
            "staged_path",
            "target",
        }:
            raise WorkctlError("INVALID_LAYOUT_PROPOSAL_JOURNAL")
        migration_id = raw_record.get("migration_id")
        manifest = raw_record.get("manifest")
        manifest_digest = raw_record.get("manifest_sha256")
        if (
            not isinstance(migration_id, str)
            or MIGRATION_ID_RE.fullmatch(migration_id) is None
            or migration_id in seen
            or not isinstance(manifest, list)
            or not isinstance(manifest_digest, str)
            or SHA256_RE.fullmatch(manifest_digest) is None
            or manifest_sha256(manifest) != manifest_digest
            or raw_record.get("staged_path") != (staging / "proposals" / migration_id).as_posix()
            or raw_record.get("target")
            != (Path(GOVERNANCE_DIR_NAME) / "proposals" / migration_id).as_posix()
        ):
            raise WorkctlError("INVALID_LAYOUT_PROPOSAL_JOURNAL")
        seen.add(migration_id)
        records.append(cast(dict[str, object], raw_record))
    return records


def validate_active_layout_journal_artifacts(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
) -> None:
    """Bind an active journal to the exact controller artifacts already on disk."""
    transaction_id = journal.get("transaction_id")
    status = journal.get("status")
    if not isinstance(transaction_id, str) or status not in {
        "plan-activated",
        "version-pending",
    }:
        raise WorkctlError("INVALID_ACTIVE_LAYOUT_JOURNAL")
    transaction, expected_journal, staging, backup, evidence, guard = layout_transaction_paths(
        root,
        transaction_id,
    )
    active_plan_id = journal.get("active_plan_id")
    expected_operations = [
        "snapshot",
        "staging",
        "conversion",
        "staged-validation",
        "legacy-backup",
        "plan-activation",
    ]
    if status == "version-pending":
        expected_operations.extend(["side-files", "final-validation"])
    legacy_manifest = journal.get("legacy_manifest")
    legacy_proposals_manifest = journal.get("legacy_proposals_manifest")
    new_layout_manifest = journal.get("new_layout_manifest")
    conversion_table = journal.get("conversion_table")
    expected_paths = {
        "staged_plan": (staging / PLAN_DIR_NAME).as_posix(),
        "staged_proposals": (staging / "proposals").as_posix(),
        "target_proposals": proposals_dir(root).as_posix(),
        "backup_plan": (backup / PLAN_DIR_NAME).as_posix(),
        "original_evidence": (evidence / f"legacy-{PLAN_DIR_NAME}").as_posix(),
    }
    if (
        journal_path != expected_journal
        or journal_path.parent != transaction
        or set(journal) != ACTIVE_LAYOUT_JOURNAL_KEYS
        or journal.get("schema_version") != 1
        or journal.get("kind") != "layout-migration"
        or journal_path.parent.name != transaction_id
        or not isinstance(active_plan_id, str)
        or PLAN_ID_RE.fullmatch(active_plan_id) is None
        or journal.get("active_plan_path") != f"{active_plan_id}.md"
        or not isinstance(journal.get("created_at"), str)
        or not journal.get("created_at")
        or not isinstance(journal.get("updated_at"), str)
        or not journal.get("updated_at")
        or not isinstance(journal.get("git_baseline"), dict)
        or journal.get("paths") != expected_paths
        or journal.get("completed_operations") != expected_operations
        or not isinstance(journal.get("log_files"), list)
        or not isinstance(legacy_manifest, list)
        or manifest_sha256(cast(list[dict[str, object]], legacy_manifest))
        != journal.get("legacy_manifest_sha256")
        or not isinstance(legacy_proposals_manifest, list)
        or manifest_sha256(cast(list[dict[str, object]], legacy_proposals_manifest))
        != journal.get("legacy_proposals_sha256")
        or proposal_manifest_from_plan_manifest(cast(list[dict[str, object]], legacy_manifest))
        != legacy_proposals_manifest
        or not isinstance(new_layout_manifest, list)
        or manifest_sha256(cast(list[dict[str, object]], new_layout_manifest))
        != journal.get("new_layout_baseline_sha256")
        or not isinstance(conversion_table, list)
        or manifest_sha256(cast(list[dict[str, object]], conversion_table))
        != journal.get("conversion_table_sha256")
        or journal.get("new_proposals_baseline_sha256") != journal.get("legacy_proposals_sha256")
    ):
        raise WorkctlError("INVALID_ACTIVE_LAYOUT_JOURNAL")
    records = layout_proposal_records(root, journal)
    combined_manifest: list[dict[str, object]] = []
    for record in records:
        migration_id = str(record["migration_id"])
        combined_manifest.append({"path": migration_id, "kind": "directory"})
        for entry in cast(list[dict[str, object]], record["manifest"]):
            combined_manifest.append(
                {
                    **entry,
                    "path": f"{migration_id}/{entry['path']}",
                }
            )
    combined_manifest.sort(key=lambda entry: str(entry["path"]))
    canonical_plan = plan_dir(root)
    backup_plan = backup / PLAN_DIR_NAME
    original_evidence = evidence / f"legacy-{PLAN_DIR_NAME}"
    adoption = legacy_adoption_path(root)
    proof_relative = (Path(".migrations") / f"{transaction_id}.yaml").as_posix()
    proof = canonical_plan / proof_relative
    try:
        adoption_payload = json.loads(adoption.read_text(encoding="utf-8"))
        proof_payload = load_yaml_file(proof)
        identity = git_worktree_identity(root)
    except (OSError, json.JSONDecodeError, WorkctlError, yaml.YAMLError) as exc:
        raise WorkctlError("INVALID_ACTIVE_LAYOUT_JOURNAL") from exc
    expected_adoption = {
        "schema_version": 1,
        "kind": "work-governance-legacy-adoption",
        "project_root": root.resolve().as_posix(),
        "worktree_identity": identity,
        "active_plan_id": active_plan_id,
        "active_plan_path": journal.get("active_plan_path"),
        "legacy_manifest_sha256": journal.get("legacy_manifest_sha256"),
    }
    expected_proof = {
        "schema_version": 1,
        "kind": "layout-migration-proof",
        "transaction_id": transaction_id,
        "status": "prepared",
        "legacy_manifest_sha256": journal.get("legacy_manifest_sha256"),
        "legacy_adoption_sha256": journal.get("legacy_adoption_sha256"),
        "conversion_table_sha256": journal.get("conversion_table_sha256"),
        "legacy_proposals_sha256": journal.get("legacy_proposals_sha256"),
        "new_proposals_baseline_sha256": journal.get("new_proposals_baseline_sha256"),
    }
    expected_proposals = {
        str(record["migration_id"]): cast(
            list[dict[str, object]],
            record["manifest"],
        )
        for record in records
    }
    target_root = proposals_dir(root)
    staged_root = staging / "proposals"
    if target_root.is_symlink() or (target_root.exists() and not target_root.is_dir()):
        raise WorkctlError("INVALID_ACTIVE_LAYOUT_JOURNAL")
    if staged_root.is_symlink() or (staged_root.exists() and not staged_root.is_dir()):
        raise WorkctlError("INVALID_ACTIVE_LAYOUT_JOURNAL")
    actual_names = (
        {child.name for child in target_root.iterdir()} if target_root.is_dir() else set()
    )
    staged_names = (
        {child.name for child in staged_root.iterdir()} if staged_root.is_dir() else set()
    )
    if (
        combined_manifest != legacy_proposals_manifest
        or tree_manifest(canonical_plan) != new_layout_manifest
        or tree_manifest(backup_plan, exclude_names={".workctl.lock"}) != legacy_manifest
        or tree_manifest(original_evidence) != legacy_manifest
        or adoption.is_symlink()
        or not adoption.is_file()
        or sha256_file(adoption) != journal.get("legacy_adoption_sha256")
        or proof.is_symlink()
        or not proof.is_file()
        or not any(
            entry.get("path") == proof_relative and entry.get("kind") == "file"
            for entry in cast(list[dict[str, object]], new_layout_manifest)
        )
        or not isinstance(adoption_payload, dict)
        or set(adoption_payload) != LEGACY_ADOPTION_KEYS
        or any(adoption_payload.get(field) != value for field, value in expected_adoption.items())
        or adoption_payload.get("action_revision")
        not in SUPPORTED_LEGACY_MIGRATION_ACTION_REVISIONS
        or SHA256_RE.fullmatch(str(adoption_payload.get("controller_sha256"))) is None
        or not valid_reference(adoption_payload.get("confirmation_ref"))
        or not isinstance(adoption_payload.get("created_at"), str)
        or not adoption_payload.get("created_at")
        or set(proof_payload) != LAYOUT_PROPOSAL_PROOF_KEYS
        or any(proof_payload.get(field) != value for field, value in expected_proof.items())
        or not isinstance(proof_payload.get("created_at"), str)
        or not proof_payload.get("created_at")
        or not actual_names.issubset(expected_proposals)
        or not staged_names.issubset(expected_proposals)
        or actual_names & staged_names
        or actual_names | staged_names != set(expected_proposals)
        or (status == "version-pending" and staged_names)
        or any(
            tree_manifest(target_root / name) != expected_proposals[name] for name in actual_names
        )
        or any(
            tree_manifest(staged_root / name) != expected_proposals[name] for name in staged_names
        )
        or (staging / PLAN_DIR_NAME).exists()
        or (staging / PLAN_DIR_NAME).is_symlink()
        or (
            status == "plan-activated"
            and (
                guard.is_symlink()
                or not guard.is_file()
                or guard.read_text(encoding="utf-8") != "WORK_GOVERNANCE_LAYOUT_ACTIVATION_GUARD\n"
            )
        )
        or (status == "version-pending" and (guard.exists() or guard.is_symlink()))
    ):
        raise WorkctlError("INVALID_ACTIVE_LAYOUT_JOURNAL")


def install_staged_proposals(root: Path, journal: dict[str, Any]) -> None:
    """Install each validated proposal tree idempotently under the canonical side root."""
    target_root = proposals_dir(root)
    reject_symlink_components(root, target_root)
    if target_root.is_symlink() or (target_root.exists() and not target_root.is_dir()):
        raise WorkctlError("LAYOUT_PROPOSALS_TARGET_INVALID")
    ensure_directory_durable(target_root)
    for record in layout_proposal_records(root, journal):
        migration_id = str(record["migration_id"])
        expected_manifest = cast(list[dict[str, object]], record["manifest"])
        source = Path(str(record["staged_path"]))
        target = root / str(record["target"])
        reject_symlink_components(root, target)
        if target.exists() or target.is_symlink():
            if (
                target.is_symlink()
                or not target.is_dir()
                or tree_manifest(target) != expected_manifest
            ):
                raise WorkctlError(f"LAYOUT_PROPOSAL_TARGET_CONFLICT: {migration_id}")
            if source.exists() or source.is_symlink():
                raise WorkctlError(f"LAYOUT_PROPOSAL_DUPLICATED: {migration_id}")
            continue
        if source.is_symlink() or not source.is_dir() or tree_manifest(source) != expected_manifest:
            raise WorkctlError(f"STAGED_LAYOUT_PROPOSAL_MISMATCH: {migration_id}")
        durable_replace(source, target)
        layout_test_interrupt(f"proposal-activation-{migration_id}")
    actual_digest = manifest_sha256(tree_manifest(target_root))
    if actual_digest != journal.get("new_proposals_baseline_sha256"):
        raise WorkctlError("LAYOUT_PROPOSALS_BASELINE_MISMATCH")


def install_staged_side_files(root: Path, journal: dict[str, Any]) -> None:
    """Install validated proposals and proven governance logs idempotently."""
    install_staged_proposals(root, journal)
    for record in journal.get("log_files", []):
        if not isinstance(record, dict):
            raise WorkctlError("INVALID_LAYOUT_JOURNAL")
        source = root / str(record.get("source"))
        target = root / str(record.get("target"))
        staged = Path(str(record.get("staged_path")))
        reject_symlink_components(root, target)
        expected = str(record.get("sha256"))
        if not staged.is_file() or sha256_file(staged) != expected:
            raise WorkctlError("STAGED_LAYOUT_LOG_HASH_MISMATCH")
        if target.exists() and (not target.is_file() or sha256_file(target) != expected):
            raise WorkctlError(f"LAYOUT_LOG_TARGET_CONFLICT: {target}")
        if not target.exists():
            durable_copy_file(staged, target)
        if source.is_file() and sha256_file(source) == expected:
            durable_unlink(source)


def commit_layout_version(root: Path, journal_path: Path, journal: dict[str, Any]) -> None:
    """Write version.yaml last, then mark the runtime journal committed."""
    transaction_id = str(journal["transaction_id"])
    proof_relative = plan_relative_path(".migrations", f"{transaction_id}.yaml")
    proof_path = root / proof_relative
    if not proof_path.is_file() or proof_path.is_symlink():
        raise WorkctlError("LAYOUT_MIGRATION_PROOF_MISSING")
    proof = load_yaml_file(proof_path)
    if (
        proof.get("status") != "prepared"
        or proof.get("transaction_id") != transaction_id
        or proof.get("legacy_adoption_sha256") != journal.get("legacy_adoption_sha256")
    ):
        raise WorkctlError("LAYOUT_MIGRATION_PROOF_INVALID")
    journal["status"] = "version-pending"
    journal["completed_operations"] = [
        *journal.get("completed_operations", []),
        "side-files",
        "final-validation",
    ]
    write_layout_journal(journal_path, journal)
    validate_active_layout_journal_artifacts(root, journal_path, journal)
    completed_at = utc_now()
    payload = layout_version_payload(
        migration_status="migrated",
        transaction_id=transaction_id,
        legacy_manifest_sha256=str(journal["legacy_manifest_sha256"]),
        new_layout_baseline_sha256=str(journal["new_layout_baseline_sha256"]),
        completed_at=completed_at,
        completion_kind="migration-proof",
        completion_path=proof_relative,
        completion_sha256=sha256_file(proof_path),
    )
    write_atomic(version_path(root), yaml.safe_dump(payload, sort_keys=False))
    layout_test_interrupt("version")
    journal["status"] = "committed"
    journal["completed_operations"] = [
        *journal.get("completed_operations", []),
        "version-commit",
    ]
    write_layout_journal(journal_path, journal)


def resume_layout_transaction(root: Path, journal_path: Path, journal: dict[str, Any]) -> None:
    """Forward one staged or activated transaction to version commitment."""
    transaction_id = str(journal["transaction_id"])
    _transaction, expected_journal, staging, backup, evidence, guard = layout_transaction_paths(
        root, transaction_id
    )
    if expected_journal != journal_path:
        raise WorkctlError("LAYOUT_JOURNAL_PATH_MISMATCH")
    staged_plan = staging / PLAN_DIR_NAME
    backup_plan = backup / PLAN_DIR_NAME
    target_plan = plan_dir(root)
    status = str(journal["status"])
    if status in {"staged", "activating", "legacy-backed-up"}:
        legacy_manifest = journal.get("legacy_manifest")
        original_evidence = evidence / f"legacy-{PLAN_DIR_NAME}"
        if (
            not isinstance(legacy_manifest, list)
            or tree_manifest(original_evidence) != legacy_manifest
        ):
            raise WorkctlError("LAYOUT_ORIGINAL_EVIDENCE_MANIFEST_MISMATCH")
    if status in {"plan-activated", "version-pending"}:
        validate_active_layout_journal_artifacts(root, journal_path, journal)
    if status == "committed":
        print(f"LAYOUT_ALREADY_COMMITTED {transaction_id}")
        return
    if status == "staged":
        verify_layout_inputs(root, journal)
        if not staged_plan.is_dir() or (
            manifest_sha256(tree_manifest(staged_plan, exclude_names={".workctl.lock"}))
            != journal.get("new_layout_baseline_sha256")
        ):
            raise WorkctlError("STAGED_LAYOUT_MANIFEST_MISMATCH")
        if manifest_sha256(proposal_tree_manifest(staging)) != journal.get(
            "new_proposals_baseline_sha256"
        ):
            raise WorkctlError("STAGED_LAYOUT_PROPOSALS_MANIFEST_MISMATCH")
        journal["status"] = "activating"
        write_layout_journal(journal_path, journal)
    status = str(journal["status"])
    if status == "activating":
        if backup_plan.exists():
            if (
                backup_plan.is_symlink()
                or not backup_plan.is_dir()
                or manifest_sha256(tree_manifest(backup_plan, exclude_names={".workctl.lock"}))
                != journal.get("legacy_manifest_sha256")
            ):
                raise WorkctlError("LAYOUT_LEGACY_BACKUP_MANIFEST_MISMATCH")
            if not guard.exists() and not guard.is_symlink():
                if target_plan.exists() or target_plan.is_symlink():
                    raise WorkctlError("LAYOUT_TARGET_CONFLICT")
                write_atomic(guard, "WORK_GOVERNANCE_LAYOUT_ACTIVATION_GUARD\n")
            elif not guard.is_file():
                raise WorkctlError("LAYOUT_ACTIVATION_MARKER_MISMATCH")
        else:
            verify_layout_inputs(root, journal)
            if not guard.is_dir() or guard.is_symlink():
                raise WorkctlError("LEGACY_LAYOUT_INPUT_MISSING")
            durable_replace(guard, backup_plan)
            layout_test_interrupt("legacy-rename")
            write_atomic(guard, "WORK_GOVERNANCE_LAYOUT_ACTIVATION_GUARD\n")
        journal["status"] = "legacy-backed-up"
        journal["completed_operations"] = [
            *journal.get("completed_operations", []),
            "legacy-backup",
        ]
        write_layout_journal(journal_path, journal)
        layout_test_interrupt("legacy-backup")
    status = str(journal["status"])
    if status == "legacy-backed-up":
        if target_plan.exists():
            if not target_plan.is_dir() or manifest_sha256(
                tree_manifest(target_plan, exclude_names={".workctl.lock"})
            ) != journal.get("new_layout_baseline_sha256"):
                raise WorkctlError("LAYOUT_TARGET_CONFLICT")
        else:
            if not staged_plan.is_dir():
                raise WorkctlError("STAGED_LAYOUT_MISSING")
            durable_replace(staged_plan, target_plan)
        journal["status"] = "plan-activated"
        journal["completed_operations"] = [
            *journal.get("completed_operations", []),
            "plan-activation",
        ]
        write_layout_journal(journal_path, journal)
        layout_test_interrupt("plan-activation")
    if str(journal["status"]) in {"plan-activated", "version-pending"}:
        install_staged_side_files(root, journal)
        layout_test_interrupt("proposal-activation")
        if guard.exists() and (
            not guard.is_file()
            or guard.read_text(encoding="utf-8") != "WORK_GOVERNANCE_LAYOUT_ACTIVATION_GUARD\n"
        ):
            raise WorkctlError("LAYOUT_ACTIVATION_GUARD_DRIFT")
        validation_errors = validate_plan(root, require_governed=False)
        if validation_errors:
            raise WorkctlError("LAYOUT_ACTIVATED_BUT_INVALID: " + "; ".join(validation_errors))
        if guard.exists():
            durable_unlink(guard)
        if legacy_plan_dir(root).exists() or legacy_plan_dir(root).is_symlink():
            raise WorkctlError("LEGACY_ROOT_REAPPEARED")
        if str(journal["status"]) == "version-pending" and version_path(root).is_file():
            version_errors = layout_version_errors(root)
            if version_errors:
                raise WorkctlError("LAYOUT_VERSION_INVALID: " + "; ".join(version_errors))
            journal["status"] = "committed"
            write_layout_journal(journal_path, journal)
        else:
            commit_layout_version(root, journal_path, journal)
    final = inspect_layout(root)
    if final.state != "LAYOUT_READY":
        raise WorkctlError(
            f"LAYOUT_COMMITTED_BUT_INVALID: {final.state}; {'; '.join(final.blockers)}"
        )
    print(f"LAYOUT_COMMITTED {transaction_id}")


def migrate_legacy_layout(root: Path, legacy: LegacyLayoutReport) -> None:
    """Execute a strict, recoverable legacy layout transaction."""
    with legacy_layout_lock(root):
        fresh = classify_legacy_layout(root)
        if fresh.classification != "MIGRATABLE" or fresh.manifest_sha256 != legacy.manifest_sha256:
            raise WorkctlError("LEGACY_LAYOUT_INPUT_DRIFT")
        journal_path, journal = prepare_layout_transaction(root, fresh)
        layout_test_interrupt("staged")
        resume_layout_transaction(root, journal_path, journal)


def abandon_layout_preparation(root: Path, journal_path: Path, journal: dict[str, Any]) -> None:
    """Discard a journaled pre-activation preparation without touching legacy inputs."""
    transaction_id = str(journal["transaction_id"])
    transaction, expected_journal, staging, backup, evidence, guard = layout_transaction_paths(
        root, transaction_id
    )
    expected_paths = {
        "staged_plan": (staging / PLAN_DIR_NAME).as_posix(),
        "staged_proposals": (staging / "proposals").as_posix(),
        "target_proposals": proposals_dir(root).as_posix(),
        "backup_plan": (backup / PLAN_DIR_NAME).as_posix(),
        "original_evidence": (evidence / f"legacy-{PLAN_DIR_NAME}").as_posix(),
    }
    validate_preparing_layout_payload(root, journal)
    legacy_manifest = journal.get("legacy_manifest")
    planned_logs = journal.get("planned_log_files")
    if (
        expected_journal != journal_path
        or journal.get("status") != "preparing"
        or set(journal) != PREPARING_LAYOUT_JOURNAL_KEYS
        or not isinstance(journal.get("created_at"), str)
        or not isinstance(journal.get("updated_at"), str)
        or not isinstance(journal.get("active_plan_id"), str)
        or not isinstance(journal.get("active_plan_path"), str)
        or not isinstance(legacy_manifest, list)
        or manifest_sha256(legacy_manifest) != journal.get("legacy_manifest_sha256")
        or not isinstance(journal.get("git_baseline"), dict)
        or not isinstance(planned_logs, list)
        or journal.get("paths") != expected_paths
        or journal.get("completed_operations") != ["snapshot"]
    ):
        raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
    source_paths: set[str] = set()
    source_file_hashes: dict[str, str] = {}
    proposal_source_hashes: dict[str, str] = {}
    for entry in legacy_manifest:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or entry.get("kind") not in {"directory", "file"}
        ):
            raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
        raw_source_path = str(entry["path"])
        source_paths.add(raw_source_path)
        if entry.get("kind") == "file":
            source_file_hashes[raw_source_path] = str(entry["sha256"])
            if raw_source_path.startswith("proposals/"):
                proposal_source_hashes[raw_source_path] = str(entry["sha256"])
    planned_log_hashes: dict[str, str] = {}
    for entry in planned_logs:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256"}
            or not isinstance(entry.get("path"), str)
            or Path(str(entry["path"])).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(str(entry["path"])).parts)
            or SHA256_RE.fullmatch(str(entry.get("sha256"))) is None
        ):
            raise WorkctlError("INVALID_PREPARING_LAYOUT_JOURNAL")
        planned_log_hashes[str(entry["path"])] = str(entry["sha256"])
    fresh = classify_legacy_layout(root)
    if (
        fresh.classification != "MIGRATABLE"
        or fresh.active_plan_id != journal.get("active_plan_id")
        or fresh.active_plan_path != journal.get("active_plan_path")
        or fresh.manifest_sha256 != journal.get("legacy_manifest_sha256")
    ):
        raise WorkctlError("LEGACY_LAYOUT_INPUT_DRIFT")
    if current_layout_git_baseline(root) != journal.get("git_baseline"):
        raise WorkctlError("LAYOUT_GIT_BASELINE_DRIFT")
    adoption = legacy_adoption_path(root)
    if (
        adoption.is_symlink()
        or not adoption.is_file()
        or sha256_file(adoption) != journal.get("legacy_adoption_sha256")
    ):
        raise WorkctlError("LEGACY_ADOPTION_RECEIPT_DRIFT")
    for raw_path, expected_hash in planned_log_hashes.items():
        source = legacy_logs_dir(root) / raw_path
        if source.is_symlink() or not source.is_file() or sha256_file(source) != expected_hash:
            raise WorkctlError(f"LAYOUT_LOG_INPUT_DRIFT: {(Path('.logs') / raw_path).as_posix()}")
    if (
        not guard.is_dir()
        or guard.is_symlink()
        or plan_dir(root).exists()
        or plan_dir(root).is_symlink()
        or version_path(root).exists()
        or version_path(root).is_symlink()
        or (backup / PLAN_DIR_NAME).exists()
        or (backup / PLAN_DIR_NAME).is_symlink()
    ):
        raise WorkctlError("LAYOUT_PREPARATION_ABANDON_UNSAFE")
    expected_transaction_children = {
        "journal.json",
        "preparing-journal.json",
        "staging",
        "backup",
    }
    transaction_children = list(transaction.iterdir())
    unexpected_transaction_children = [
        child
        for child in transaction_children
        if child.name not in expected_transaction_children
        and not (
            child.name.startswith((".preparing-journal.json.", ".journal.json."))
            and not child.is_symlink()
            and child.is_file()
        )
    ]
    actual_transaction_children = {child.name for child in transaction_children}
    if (
        unexpected_transaction_children
        or "journal.json" not in actual_transaction_children
        or (
            staging.exists()
            and (
                staging.is_symlink()
                or not staging.is_dir()
                or not {child.name for child in staging.iterdir()}.issubset(
                    {PLAN_DIR_NAME, "logs", "proposals"}
                )
            )
        )
        or (
            backup.exists()
            and (backup.is_symlink() or not backup.is_dir() or any(backup.iterdir()))
        )
        or (
            evidence.exists()
            and (
                evidence.is_symlink()
                or not evidence.is_dir()
                or not {child.name for child in evidence.iterdir()}.issubset(
                    {f"legacy-{PLAN_DIR_NAME}"}
                )
            )
        )
    ):
        raise WorkctlError("LAYOUT_PREPARATION_INVENTORY_INVALID")
    staged_plan = staging / PLAN_DIR_NAME
    staged_proposals = staging / "proposals"
    legacy_proposals_manifest = cast(
        list[dict[str, object]],
        journal["legacy_proposals_manifest"],
    )
    allowed_proposal_paths: set[str] = set()
    expected_proposal_hashes: dict[str, str] = {}
    for entry in legacy_proposals_manifest:
        raw_path = str(entry["path"])
        allowed_proposal_paths.add(raw_path)
        if entry.get("kind") == "file":
            expected_proposal_hashes[raw_path] = str(entry["sha256"])
    proof_relative = (Path(".migrations") / f"{transaction_id}.yaml").as_posix()
    allowed_staged_plan_paths = {
        *source_paths,
        ".migrations",
        proof_relative,
    }
    original_plan = evidence / f"legacy-{PLAN_DIR_NAME}"
    staged_logs = staging / "logs"
    allowed_log_paths = set(planned_log_hashes)
    for raw_path in planned_log_hashes:
        allowed_log_paths.update(
            parent.as_posix() for parent in Path(raw_path).parents if parent != Path(".")
        )
    if (
        (
            staged_plan.exists()
            and (
                staged_plan.is_symlink()
                or not staged_plan.is_dir()
                or not manifest_matches_allowed_subset(
                    staged_plan,
                    allowed_staged_plan_paths,
                    proposal_source_hashes,
                )
            )
        )
        or (
            original_plan.exists()
            and (
                original_plan.is_symlink()
                or not original_plan.is_dir()
                or not manifest_matches_allowed_subset(
                    original_plan,
                    source_paths,
                    source_file_hashes,
                )
            )
        )
        or (
            staged_logs.exists()
            and (
                staged_logs.is_symlink()
                or not staged_logs.is_dir()
                or not manifest_matches_allowed_subset(
                    staged_logs,
                    allowed_log_paths,
                    planned_log_hashes,
                )
            )
        )
        or (
            staged_proposals.exists()
            and (
                staged_proposals.is_symlink()
                or not staged_proposals.is_dir()
                or not manifest_matches_allowed_subset(
                    staged_proposals,
                    allowed_proposal_paths,
                    expected_proposal_hashes,
                )
            )
        )
    ):
        raise WorkctlError("LAYOUT_PREPARATION_INVENTORY_INVALID")
    preparing_path = transaction / "preparing-journal.json"
    if preparing_path.exists() or preparing_path.is_symlink():
        if (
            preparing_path.is_symlink()
            or not preparing_path.is_file()
            or sha256_file(preparing_path) != sha256_file(journal_path)
        ):
            raise WorkctlError("LAYOUT_PREPARING_RECEIPT_DRIFT")
    else:
        durable_copy_file(journal_path, preparing_path)
    layout_test_interrupt("preparing-receipt")
    journal["preparing_journal_sha256"] = sha256_file(preparing_path)
    journal["status"] = "aborted"
    journal["completed_operations"] = [
        *journal.get("completed_operations", []),
        "preparation-preserved",
    ]
    write_layout_journal(journal_path, journal)
    print(f"LAYOUT_PREPARATION_PRESERVED {transaction_id}")


def recover_layout_transaction(root: Path) -> None:
    """Recover the sole incomplete layout transaction by deterministic forward progress."""
    journals = layout_journal_paths(root)
    if not journals:
        raise WorkctlError("NO_INCOMPLETE_LAYOUT_MIGRATION")
    if len(journals) != 1:
        raise WorkctlError("LAYOUT_TRANSACTION_ID_REQUIRED")
    journal_path = journals[0]
    journal = load_layout_journal(journal_path)
    if journal.get("kind") == "layout-action-upgrade":
        if journal.get("status") == "preparing":
            abandon_action_upgrade_preparation(root, journal_path, journal)
        else:
            resume_action_upgrade_transaction(root, journal_path, journal)
        return
    if journal.get("status") == "preparing":
        with legacy_layout_lock(root):
            abandon_layout_preparation(root, journal_path, journal)
        return
    if journal.get("status") == "staged" or (
        journal.get("status") == "activating" and legacy_plan_dir(root).is_dir()
    ):
        with legacy_layout_lock(root):
            resume_layout_transaction(root, journal_path, journal)
    else:
        resume_layout_transaction(root, journal_path, journal)


def cmd_layout_migrate(_args: argparse.Namespace) -> None:
    """Commit a not-applicable layout or execute one safe legacy transaction."""
    root = project_root()
    with lock(root):
        report = inspect_layout(root)
        if report.state == "LAYOUT_READY":
            print("LAYOUT_ALREADY_READY")
            return
        if report.state != "LAYOUT_MIGRATION_REQUIRED":
            details = "; ".join(report.blockers)
            suffix = f": {details}" if details else ""
            raise WorkctlError(f"LAYOUT_MIGRATION_BLOCKED: {report.state}{suffix}")
        if version_path(root).is_file():
            migrate_layout_action_upgrade(root)
            return
        if report.legacy.classification == "NOT_APPLICABLE":
            commit_not_applicable_layout(root)
            print("LAYOUT_COMMITTED not_applicable")
            return
        if report.legacy.classification != "MIGRATABLE":
            raise WorkctlError(f"LAYOUT_MIGRATION_BLOCKED: {report.legacy.classification}")
        migrate_legacy_layout(root, report.legacy)


def cmd_layout_recover(_args: argparse.Namespace) -> None:
    """Resume the sole incomplete layout transaction deterministically."""
    root = project_root()
    with lock(root):
        recover_layout_transaction(root)


def require_valid_candidate(doc: PlanDocument) -> None:
    errors = validate_frontmatter(doc.frontmatter, reject_blocking_artifacts=False)
    if not doc.body.strip():
        errors.append("Plan body must not be empty")
    if errors:
        raise WorkctlError(f"INVALID_PLAN: {'; '.join(errors)}")


def admission_transaction_dir(root: Path, transaction_id: str) -> Path:
    """Return one ignored, durable Plan-admission transaction directory."""
    return governance_root(root) / "runtime" / "plan-admissions" / transaction_id


def write_transaction_journal(path: Path, payload: Mapping[str, Any]) -> None:
    """Write one durable JSON transaction journal."""
    write_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def validate_partial_transaction_directory(
    transaction: Path,
    expected_files: set[str],
    *,
    error: str,
) -> None:
    """Require an existing partial staging tree to contain only expected entries."""
    if not transaction.exists() and not transaction.is_symlink():
        return
    if transaction.is_symlink() or not transaction.is_dir():
        raise WorkctlError(error)
    expected_directories: set[str] = set()
    for relative_file in expected_files:
        parent = Path(relative_file).parent
        while parent != Path("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    for candidate in transaction.rglob("*"):
        relative = candidate.relative_to(transaction).as_posix()
        if candidate.is_symlink():
            raise WorkctlError(error)
        if candidate.is_dir():
            if relative not in expected_directories:
                raise WorkctlError(error)
        elif candidate.is_file():
            if relative not in expected_files:
                raise WorkctlError(error)
        else:
            raise WorkctlError(error)


def write_or_validate_staged_bytes(
    path: Path,
    content: bytes,
    *,
    error: str,
) -> None:
    """Write a missing staged file or require exact existing ordinary-file bytes."""
    if path.is_symlink():
        raise WorkctlError(error)
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise WorkctlError(error)
        return
    write_atomic_bytes(path, content)


def maybe_interrupt_before_transaction_journal(kind: str) -> None:
    """Inject a deterministic test-only interruption before journal publication."""
    if os.environ.get("WORKCTL_TEST_STAGE_INTERRUPT_BEFORE_JOURNAL") == kind:
        raise WorkctlError(f"TRANSACTION_STAGE_TEST_INTERRUPTED: {kind}")


def load_admission_manifest(path: Path) -> dict[str, Any]:
    """Validate the closed public Plan-admission manifest."""
    manifest = load_yaml_file(path)
    required_fields = {
        "schema_version",
        "kind",
        "transaction_id",
        "prepared_plan",
        "plan_id",
        "plan_sha256",
        "confirmation_id",
        "confirmation_ref",
    }
    if STRICT_INITIAL_INTAKE_REQUIRED:
        required_fields.add("intake")
    if set(manifest) != required_fields:
        raise WorkctlError("INVALID_PLAN_ADMISSION_MANIFEST_FIELDS")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "plan-admission":
        raise WorkctlError("INVALID_PLAN_ADMISSION_MANIFEST_SCHEMA")
    transaction_id = manifest.get("transaction_id")
    plan_id = manifest.get("plan_id")
    if not isinstance(transaction_id, str) or ADMISSION_ID_RE.fullmatch(transaction_id) is None:
        raise WorkctlError("INVALID_PLAN_ADMISSION_TRANSACTION_ID")
    if not isinstance(plan_id, str) or PLAN_ID_RE.fullmatch(plan_id) is None:
        raise WorkctlError("INVALID_PLAN_ADMISSION_PLAN_ID")
    if (
        not isinstance(manifest.get("plan_sha256"), str)
        or SHA256_RE.fullmatch(str(manifest["plan_sha256"])) is None
    ):
        raise WorkctlError("INVALID_PLAN_ADMISSION_SHA256")
    if not isinstance(manifest.get("confirmation_id"), str) or not str(
        manifest["confirmation_id"]
    ).startswith("C-"):
        raise WorkctlError("INVALID_PLAN_ADMISSION_CONFIRMATION")
    if not valid_reference(manifest.get("confirmation_ref")):
        raise WorkctlError("INVALID_PLAN_ADMISSION_CONFIRMATION_REF")
    prepared_plan = manifest.get("prepared_plan")
    if (
        not isinstance(prepared_plan, str)
        or not prepared_plan
        or Path(prepared_plan).is_absolute()
        or ".." in Path(prepared_plan).parts
    ):
        raise WorkctlError("INVALID_PLAN_ADMISSION_PREPARED_PATH")
    if STRICT_INITIAL_INTAKE_REQUIRED:
        embedded_initial_intake(manifest)
    return manifest


def resume_plan_admission(root: Path, journal_path: Path) -> None:
    """Deterministically roll one staged Plan admission forward, index last."""
    reject_symlink_components(root, journal_path)
    if journal_path.is_symlink() or not journal_path.is_file():
        raise WorkctlError("INVALID_PLAN_ADMISSION_JOURNAL")
    journal = load_yaml_file(journal_path)
    expected_keys = {
        "schema_version",
        "kind",
        "transaction_id",
        "status",
        "created_at",
        "updated_at",
        "plan_id",
        "plan_sha256",
        "manifest_sha256",
        "staged_path",
        "target_path",
    }
    if STRICT_INITIAL_INTAKE_REQUIRED:
        expected_keys.update(
            {
                "prepared_plan_sha256",
                "intake_binding",
                "transaction_binding_sha256",
            }
        )
    transaction_id = journal.get("transaction_id")
    plan_id = journal.get("plan_id")
    if (
        set(journal) != expected_keys
        or journal.get("kind") != "plan-admission"
        or journal.get("schema_version") != 1
        or journal.get("status") not in {"prepared", "plan-installed", "committed"}
        or not isinstance(transaction_id, str)
        or ADMISSION_ID_RE.fullmatch(transaction_id) is None
        or not isinstance(plan_id, str)
        or PLAN_ID_RE.fullmatch(plan_id) is None
        or journal_path != admission_transaction_dir(root, transaction_id) / "journal.json"
    ):
        raise WorkctlError("INVALID_PLAN_ADMISSION_JOURNAL")
    if journal.get("status") == "committed":
        print(f"PLAN_ADMISSION_ALREADY_COMMITTED {transaction_id}")
        return
    target = checked_project_path(root, str(journal.get("target_path")))
    staged = checked_project_path(root, str(journal.get("staged_path")))
    expected_transaction = admission_transaction_dir(root, transaction_id)
    expected_target = plan_dir(root) / f"{plan_id}.md"
    expected_staged = expected_transaction / "staging" / f"{plan_id}.md"
    expected_sha256 = str(journal.get("plan_sha256"))
    if (
        target != expected_target
        or staged != expected_staged
        or SHA256_RE.fullmatch(expected_sha256) is None
        or SHA256_RE.fullmatch(str(journal.get("manifest_sha256"))) is None
        or staged.is_symlink()
        or not staged.is_file()
        or sha256_file(staged) != expected_sha256
    ):
        raise WorkctlError("INVALID_PLAN_ADMISSION_JOURNAL")
    reject_symlink_components(root, target)
    staged_doc = load_plan(staged)
    require_valid_candidate(staged_doc)
    require_strict_intervention_contract(staged_doc.frontmatter)
    require_new_plan_reviews_pending(staged_doc.frontmatter)
    if (
        staged_doc.frontmatter.get("schema_version") != 4
        or staged_doc.frontmatter.get("plan_id") != plan_id
    ):
        raise WorkctlError("PLAN_ADMISSION_PLAN_ID_MISMATCH")
    if STRICT_INITIAL_INTAKE_REQUIRED:
        binding = journal.get("intake_binding")
        prepared_sha256 = journal.get("prepared_plan_sha256")
        transaction_binding_sha256 = journal.get("transaction_binding_sha256")
        records = intake_records(staged_doc.frontmatter)
        if (
            not isinstance(binding, dict)
            or not isinstance(prepared_sha256, str)
            or SHA256_RE.fullmatch(prepared_sha256) is None
            or not isinstance(transaction_binding_sha256, str)
            or SHA256_RE.fullmatch(transaction_binding_sha256) is None
            or len(records) != 1
            or records[0].get("record_sha256") != binding.get("intake_record_sha256")
            or records[0].get("request_ref") != binding.get("request_ref")
            or records[0].get("decision_basis_sha256") != binding.get("decision_basis_sha256")
            or transaction_binding_digest(
                transaction_kind="plan-admission",
                transaction_id=transaction_id,
                plan_id=plan_id,
                prepared_plan_sha256=prepared_sha256,
                target_plan_sha256=expected_sha256,
                intake_binding=cast(Mapping[str, object], binding),
            )
            != transaction_binding_sha256
        ):
            raise WorkctlError("INVALID_PLAN_ADMISSION_JOURNAL")
    if target.exists():
        if target.is_symlink() or not target.is_file() or sha256_file(target) != expected_sha256:
            raise WorkctlError("PLAN_ADMISSION_TARGET_CONFLICT")
    else:
        write_atomic_bytes(target, staged.read_bytes())
    journal["status"] = "plan-installed"
    journal["updated_at"] = utc_now()
    write_transaction_journal(journal_path, journal)
    if os.environ.get("WORKCTL_TEST_ADMISSION_INTERRUPT_AFTER") == "plan-installed":
        raise WorkctlError("PLAN_ADMISSION_TEST_INTERRUPTED: plan-installed")
    index = {
        "schema_version": 1,
        "active_plan_id": plan_id,
        "plans": [
            {
                "id": plan_id,
                "path": target.name,
                "title": staged_doc.frontmatter["title"],
                "created_at": staged_doc.frontmatter["created_at"],
            }
        ],
    }
    write_atomic(index_path(root), yaml.safe_dump(index, sort_keys=False))
    report = inspect_authority(root)
    if report.state != "GOVERNED_ACTIVE":
        raise WorkctlError(
            f"PLAN_ADMISSION_ACTIVATED_BUT_INVALID: {report.state}; {'; '.join(report.blockers)}"
        )
    errors = validate_plan(root)
    if errors:
        raise WorkctlError(f"PLAN_ADMISSION_ACTIVATED_BUT_INVALID: {'; '.join(errors)}")
    journal["status"] = "committed"
    journal["updated_at"] = utc_now()
    write_transaction_journal(journal_path, journal)
    print(f"PLAN_ADMISSION_COMMITTED {journal['transaction_id']} plan={plan_id}")


def cmd_plan_admit_apply(args: argparse.Namespace) -> None:
    """Stage, validate, journal and activate one exact confirmed Plan."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    manifest = load_admission_manifest(manifest_path)
    with lock(root):
        report = inspect_authority(root)
        if report.state != "UNMANAGED_EMPTY":
            raise WorkctlError(f"PLAN_ADMISSION_BLOCKED: {report.state}")
        transaction_id = str(manifest["transaction_id"])
        transaction = admission_transaction_dir(root, transaction_id)
        journal_path = transaction / "journal.json"
        if journal_path.exists():
            resume_plan_admission(root, journal_path)
            return
        if transaction.exists():
            raise WorkctlError("PLAN_ADMISSION_TRANSACTION_CONFLICT")
        prepared = manifest_input_path(manifest_path, str(manifest["prepared_plan"]))
        if prepared.is_symlink() or not prepared.is_file():
            raise WorkctlError("PLAN_ADMISSION_PREPARED_PLAN_MISSING")
        if sha256_file(prepared) != manifest["plan_sha256"]:
            raise WorkctlError("PLAN_ADMISSION_INPUT_DRIFT")
        candidate = load_plan(prepared)
        require_valid_candidate(candidate)
        require_strict_intervention_contract(candidate.frontmatter)
        require_new_plan_reviews_pending(candidate.frontmatter)
        plan_id = str(manifest["plan_id"])
        if (
            candidate.frontmatter.get("schema_version") != 4
            or candidate.frontmatter.get("plan_id") != plan_id
            or candidate.path.name == "index.yaml"
        ):
            raise WorkctlError("PLAN_ADMISSION_CANDIDATE_INVALID")
        decision = confirmations(candidate.frontmatter).get(str(manifest["confirmation_id"]))
        if (
            decision is None
            or decision.get("status") != "accepted"
            or decision.get("ref") != manifest["confirmation_ref"]
            or candidate.frontmatter.get("contract", {}).get("confirmation_id")
            != manifest["confirmation_id"]
        ):
            raise WorkctlError("PLAN_ADMISSION_CONFIRMATION_MISMATCH")
        intake_binding: dict[str, object] | None = None
        prepared_sha256 = str(manifest["plan_sha256"])
        if STRICT_INITIAL_INTAKE_REQUIRED:
            session_receipt = validate_current_ready_receipt(
                root,
                args.receipt_sha256,
                require_current_controller=True,
            )
            proposal = embedded_initial_intake(manifest)
            validate_current_intake_proposal(
                root,
                candidate.frontmatter,
                proposal,
                session_receipt=cast(Mapping[str, object], session_receipt),
            )
            record = inject_initial_intake(candidate.frontmatter, proposal)
            intake_binding = initial_intake_binding(proposal, record)
            require_valid_candidate(candidate)
            require_strict_intervention_contract(candidate.frontmatter)
            require_new_plan_reviews_pending(candidate.frontmatter)
        staged = transaction / "staging" / f"{plan_id}.md"
        if STRICT_INITIAL_INTAKE_REQUIRED:
            write_atomic(staged, dump_plan(candidate))
        else:
            durable_copy_file(prepared, staged)
        target_sha256 = sha256_file(staged)
        journal = {
            "schema_version": 1,
            "kind": "plan-admission",
            "transaction_id": transaction_id,
            "status": "prepared",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "plan_id": plan_id,
            "plan_sha256": target_sha256,
            "manifest_sha256": sha256_file(manifest_path),
            "staged_path": relative_project_path(root, staged),
            "target_path": plan_relative_path(f"{plan_id}.md"),
        }
        if STRICT_INITIAL_INTAKE_REQUIRED:
            assert intake_binding is not None
            journal["prepared_plan_sha256"] = prepared_sha256
            journal["intake_binding"] = intake_binding
            journal["transaction_binding_sha256"] = transaction_binding_digest(
                transaction_kind="plan-admission",
                transaction_id=transaction_id,
                plan_id=plan_id,
                prepared_plan_sha256=prepared_sha256,
                target_plan_sha256=target_sha256,
                intake_binding=intake_binding,
            )
        write_transaction_journal(journal_path, journal)
        resume_plan_admission(root, journal_path)


def cmd_plan_admit_recover(args: argparse.Namespace) -> None:
    """Recover the sole or named incomplete Plan-admission transaction."""
    root = project_root()
    with lock(root):
        base = governance_root(root) / "runtime" / "plan-admissions"
        if args.transaction_id:
            journal = admission_transaction_dir(root, args.transaction_id) / "journal.json"
            if not journal.is_file():
                raise WorkctlError("PLAN_ADMISSION_JOURNAL_NOT_FOUND")
        else:
            journals = sorted(base.glob("*/journal.json")) if base.is_dir() else []
            incomplete = [
                path for path in journals if load_yaml_file(path).get("status") != "committed"
            ]
            if len(incomplete) != 1:
                raise WorkctlError(
                    "PLAN_ADMISSION_RECOVERY_AMBIGUOUS"
                    if incomplete
                    else "PLAN_ADMISSION_RECOVERY_NOT_REQUIRED"
                )
            journal = incomplete[0]
        resume_plan_admission(root, journal)


def contract_upgrade_transaction_dir(root: Path, transaction_id: str) -> Path:
    """Return one ignored contract-upgrade transaction directory."""
    return governance_root(root) / "runtime" / "contract-upgrades" / transaction_id


def load_contract_upgrade_manifest(path: Path) -> dict[str, Any]:
    """Validate one schema-v3-to-v4 upgrade manifest."""
    manifest = load_yaml_file(path)
    required_fields = {
        "schema_version",
        "kind",
        "transaction_id",
        "plan_id",
        "expected_revision",
        "plan_sha256",
        "confirmation_id",
        "confirmation_ref",
        "evidence_manifest",
        "goal",
        "unknowns",
        "task_metadata",
        "validation_provenance",
    }
    if STRICT_INITIAL_INTAKE_REQUIRED:
        required_fields.add("intake")
    if set(manifest) != required_fields:
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_MANIFEST_FIELDS")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "plan-contract-upgrade":
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_MANIFEST_SCHEMA")
    transaction_id = manifest.get("transaction_id")
    if (
        not isinstance(transaction_id, str)
        or CONTRACT_UPGRADE_ID_RE.fullmatch(transaction_id) is None
        or not isinstance(manifest.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(manifest["plan_id"])) is None
        or type(manifest.get("expected_revision")) is not int
        or not isinstance(manifest.get("plan_sha256"), str)
        or SHA256_RE.fullmatch(str(manifest["plan_sha256"])) is None
        or not isinstance(manifest.get("confirmation_id"), str)
        or not str(manifest["confirmation_id"]).startswith("C-")
        or not valid_reference(manifest.get("confirmation_ref"))
        or not isinstance(manifest.get("evidence_manifest"), str)
        or not isinstance(manifest.get("goal"), dict)
        or not isinstance(manifest.get("unknowns"), list)
        or not isinstance(manifest.get("task_metadata"), dict)
        or not isinstance(manifest.get("validation_provenance"), dict)
    ):
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_MANIFEST")
    if STRICT_INITIAL_INTAKE_REQUIRED:
        embedded_initial_intake(manifest)
    return manifest


def prepare_contract_upgrade(
    root: Path,
    manifest_path: Path,
    source: PlanDocument,
    *,
    source_sha256: str,
    session_receipt: Mapping[str, object] | None,
) -> ContractUpgradePreparation:
    """Authenticate and build one schema-v4 child target without writing it."""
    manifest = load_contract_upgrade_manifest(manifest_path)
    if contract_state(source.frontmatter) != "PLAN_CONTRACT_UPGRADE_REQUIRED":
        raise WorkctlError("PLAN_CONTRACT_UPGRADE_NOT_REQUIRED")
    if (
        source.frontmatter.get("plan_id") != manifest["plan_id"]
        or source.frontmatter.get("revision") != manifest["expected_revision"]
        or source_sha256 != manifest["plan_sha256"]
    ):
        raise WorkctlError("PLAN_CONTRACT_UPGRADE_INPUT_DRIFT")
    confirmation_id = str(manifest["confirmation_id"])
    decision = confirmations(source.frontmatter).get(confirmation_id)
    if (
        decision is None
        or decision.get("status") != "accepted"
        or decision.get("ref") != manifest["confirmation_ref"]
    ):
        raise WorkctlError("PLAN_CONTRACT_UPGRADE_CONFIRMATION_MISMATCH")
    evidence_ref, _ = verify_evidence_manifest(
        root,
        str(manifest["evidence_manifest"]),
        plan_id=str(source.frontmatter["plan_id"]),
        subject="contract-upgrade",
    )
    upgraded = PlanDocument(
        path=source.path,
        frontmatter=copy.deepcopy(source.frontmatter),
        body=source.body,
    )
    upgraded.frontmatter["schema_version"] = 4
    upgraded.frontmatter["goal"] = manifest["goal"]
    upgraded.frontmatter["contract"] = {
        "revision": 1,
        "confirmation_id": confirmation_id,
        "confirmed_ref": decision["ref"],
    }
    upgraded.frontmatter["unknowns"] = manifest["unknowns"]
    task_metadata = cast(dict[str, Any], manifest["task_metadata"])
    for task in upgraded.frontmatter.get("tasks", []):
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        metadata = task_metadata.get(task["id"])
        if not isinstance(metadata, dict) or set(metadata) != {
            "unknowns",
            "expected_evidence_delta",
        }:
            raise WorkctlError(f"CONTRACT_UPGRADE_TASK_METADATA_MISSING: {task['id']}")
        task.update(metadata)
    if set(task_metadata) != {
        str(task["id"])
        for task in upgraded.frontmatter.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }:
        raise WorkctlError("CONTRACT_UPGRADE_TASK_METADATA_UNKNOWN")
    validation_provenance = cast(dict[str, Any], manifest["validation_provenance"])
    for validation in upgraded.frontmatter.get("validations", []):
        if not isinstance(validation, dict) or not isinstance(validation.get("id"), str):
            continue
        provenance = validation_provenance.get(validation["id"])
        if not isinstance(provenance, dict):
            raise WorkctlError(
                f"CONTRACT_UPGRADE_VALIDATION_PROVENANCE_MISSING: {validation['id']}"
            )
        validation["provenance"] = provenance
    if set(validation_provenance) != {
        str(validation["id"])
        for validation in upgraded.frontmatter.get("validations", [])
        if isinstance(validation, dict) and isinstance(validation.get("id"), str)
    }:
        raise WorkctlError("CONTRACT_UPGRADE_VALIDATION_PROVENANCE_UNKNOWN")
    next_revision = int(upgraded.frontmatter["revision"]) + 1
    changed_at = decision.get("accepted_at") or decision.get("decided_at")
    if not isinstance(changed_at, str) or not changed_at:
        raise WorkctlError("PLAN_CONTRACT_UPGRADE_CONFIRMATION_MISMATCH")
    upgraded.frontmatter["revision"] = next_revision
    upgraded.frontmatter["updated_at"] = changed_at
    upgraded.frontmatter["revision_history"] = [
        {
            "revision": next_revision,
            "kind": "contract-upgrade",
            "changed_at": changed_at,
            "rationale": "Upgrade the active legacy contract without trusting log hashes.",
            "confirmation_id": confirmation_id,
            "evidence_manifest": evidence_ref,
        }
    ]
    intake_binding: dict[str, object] | None = None
    if STRICT_INITIAL_INTAKE_REQUIRED:
        if session_receipt is None:
            raise WorkctlError("BOOTSTRAP_RECEIPT_REQUIRED")
        proposal = embedded_initial_intake(manifest)
        validate_current_intake_proposal(
            root,
            upgraded.frontmatter,
            proposal,
            session_receipt=session_receipt,
        )
        record = inject_initial_intake(upgraded.frontmatter, proposal)
        intake_binding = initial_intake_binding(proposal, record)
    require_valid_candidate(upgraded)
    require_strict_intervention_contract(upgraded.frontmatter)
    require_new_plan_reviews_pending(upgraded.frontmatter)
    return ContractUpgradePreparation(
        manifest=manifest,
        upgraded=upgraded,
        source_sha256=source_sha256,
        intake_binding=intake_binding,
    )


def stage_contract_upgrade(
    root: Path,
    manifest_path: Path,
    preparation: ContractUpgradePreparation,
) -> Path:
    """Stage one independently recoverable contract-upgrade child transaction."""
    manifest = preparation.manifest
    upgraded = preparation.upgraded
    transaction_id = str(manifest["transaction_id"])
    transaction = contract_upgrade_transaction_dir(root, transaction_id)
    journal_path = transaction / "journal.json"
    if journal_path.exists():
        return journal_path
    staged = transaction / "staging" / upgraded.path.name
    staged_bytes = dump_plan(upgraded).encode("utf-8")
    conflict_error = "CONTRACT_UPGRADE_TRANSACTION_CONFLICT"
    validate_partial_transaction_directory(
        transaction,
        {relative_project_path(transaction, staged)},
        error=conflict_error,
    )
    write_or_validate_staged_bytes(staged, staged_bytes, error=conflict_error)
    journal: dict[str, Any] = {
        "schema_version": 1,
        "kind": "plan-contract-upgrade",
        "transaction_id": transaction_id,
        "status": "prepared",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "plan_id": upgraded.frontmatter["plan_id"],
        "source_sha256": preparation.source_sha256,
        "target_sha256": sha256_bytes(staged_bytes),
        "manifest_sha256": sha256_file(manifest_path),
        "staged_path": relative_project_path(root, staged),
        "target_path": relative_project_path(root, upgraded.path),
    }
    if STRICT_INITIAL_INTAKE_REQUIRED:
        intake_binding = preparation.intake_binding
        if intake_binding is None:
            raise WorkctlError("INITIAL_INTAKE_REQUIRED")
        journal["intake_binding"] = intake_binding
        journal["transaction_binding_sha256"] = transaction_binding_digest(
            transaction_kind="plan-contract-upgrade",
            transaction_id=transaction_id,
            plan_id=str(upgraded.frontmatter["plan_id"]),
            prepared_plan_sha256=preparation.source_sha256,
            target_plan_sha256=str(journal["target_sha256"]),
            intake_binding=intake_binding,
        )
    maybe_interrupt_before_transaction_journal("contract-upgrade")
    write_transaction_journal(journal_path, journal)
    return journal_path


def resume_contract_upgrade(root: Path, journal_path: Path) -> None:
    """Roll one staged active-Plan contract upgrade forward."""
    reject_symlink_components(root, journal_path)
    if journal_path.is_symlink() or not journal_path.is_file():
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_JOURNAL")
    journal = load_yaml_file(journal_path)
    expected_keys = {
        "schema_version",
        "kind",
        "transaction_id",
        "status",
        "created_at",
        "updated_at",
        "plan_id",
        "source_sha256",
        "target_sha256",
        "manifest_sha256",
        "staged_path",
        "target_path",
    }
    if STRICT_INITIAL_INTAKE_REQUIRED:
        expected_keys.update({"intake_binding", "transaction_binding_sha256"})
    transaction_id = journal.get("transaction_id")
    plan_id = journal.get("plan_id")
    if (
        set(journal) != expected_keys
        or journal.get("kind") != "plan-contract-upgrade"
        or journal.get("schema_version") != 1
        or journal.get("status") not in {"prepared", "plan-replaced", "committed"}
        or not isinstance(transaction_id, str)
        or CONTRACT_UPGRADE_ID_RE.fullmatch(transaction_id) is None
        or not isinstance(plan_id, str)
        or PLAN_ID_RE.fullmatch(plan_id) is None
        or journal_path != contract_upgrade_transaction_dir(root, transaction_id) / "journal.json"
    ):
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_JOURNAL")
    target = checked_project_path(root, str(journal.get("target_path")))
    staged = checked_project_path(root, str(journal.get("staged_path")))
    expected_transaction = contract_upgrade_transaction_dir(root, transaction_id)
    expected_target = plan_dir(root) / f"{plan_id}.md"
    expected_staged = expected_transaction / "staging" / f"{plan_id}.md"
    source_sha256 = str(journal.get("source_sha256"))
    target_sha256 = str(journal.get("target_sha256"))
    if (
        target != expected_target
        or staged != expected_staged
        or target.is_symlink()
        or not target.is_file()
        or staged.is_symlink()
        or not staged.is_file()
        or SHA256_RE.fullmatch(source_sha256) is None
        or SHA256_RE.fullmatch(target_sha256) is None
        or SHA256_RE.fullmatch(str(journal.get("manifest_sha256"))) is None
        or sha256_file(staged) != target_sha256
    ):
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_JOURNAL")
    reject_symlink_components(root, target)
    staged_doc = load_plan(staged)
    require_valid_candidate(staged_doc)
    if (
        staged_doc.frontmatter.get("schema_version") != 4
        or staged_doc.frontmatter.get("plan_id") != plan_id
    ):
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_JOURNAL")
    if STRICT_INITIAL_INTAKE_REQUIRED:
        binding = journal.get("intake_binding")
        transaction_binding_sha256 = journal.get("transaction_binding_sha256")
        records = intake_records(staged_doc.frontmatter)
        if (
            not isinstance(binding, dict)
            or not isinstance(transaction_binding_sha256, str)
            or SHA256_RE.fullmatch(transaction_binding_sha256) is None
            or len(records) != 1
            or records[0].get("record_sha256") != binding.get("intake_record_sha256")
            or records[0].get("request_ref") != binding.get("request_ref")
            or records[0].get("decision_basis_sha256") != binding.get("decision_basis_sha256")
            or transaction_binding_digest(
                transaction_kind="plan-contract-upgrade",
                transaction_id=transaction_id,
                plan_id=plan_id,
                prepared_plan_sha256=source_sha256,
                target_plan_sha256=target_sha256,
                intake_binding=cast(Mapping[str, object], binding),
            )
            != transaction_binding_sha256
        ):
            raise WorkctlError("INVALID_CONTRACT_UPGRADE_JOURNAL")
    index = load_yaml_file(index_path(root))
    if index.get("active_plan_id") != plan_id:
        raise WorkctlError("CONTRACT_UPGRADE_ACTIVE_PLAN_DRIFT")
    current_sha256 = sha256_file(target)
    if journal.get("status") == "committed":
        if current_sha256 != target_sha256:
            raise WorkctlError("CONTRACT_UPGRADE_COMMITTED_STATE_DRIFT")
        doc = load_plan(target)
        require_valid_candidate(doc)
        errors = validate_plan(root, ignore_journal=journal_path)
        if errors:
            raise WorkctlError(f"PLAN_CONTRACT_UPGRADE_INVALID: {'; '.join(errors)}")
        print(f"PLAN_CONTRACT_UPGRADE_ALREADY_COMMITTED {transaction_id}")
        return
    if current_sha256 == source_sha256:
        write_atomic_bytes(target, staged.read_bytes())
    elif current_sha256 != target_sha256:
        raise WorkctlError("CONTRACT_UPGRADE_TARGET_DRIFT")
    journal["status"] = "plan-replaced"
    journal["updated_at"] = utc_now()
    write_transaction_journal(journal_path, journal)
    if os.environ.get("WORKCTL_TEST_UPGRADE_INTERRUPT_AFTER") == "plan-replaced":
        raise WorkctlError("PLAN_CONTRACT_UPGRADE_TEST_INTERRUPTED: plan-replaced")
    doc = load_plan(target)
    require_valid_candidate(doc)
    errors = validate_plan(root, ignore_journal=journal_path)
    if errors:
        raise WorkctlError(f"PLAN_CONTRACT_UPGRADE_INVALID: {'; '.join(errors)}")
    journal["status"] = "committed"
    journal["updated_at"] = utc_now()
    write_transaction_journal(journal_path, journal)
    print(f"PLAN_CONTRACT_UPGRADE_COMMITTED {journal['transaction_id']} plan={journal['plan_id']}")


def cmd_plan_contract_upgrade_status(_args: argparse.Namespace) -> None:
    """Report the independent Plan-contract cutover state."""
    root = project_root()
    report = inspect_authority(root)
    payload: dict[str, Any] = {
        "authority_state": report.state,
        "contract_state": "NO_ACTIVE_PLAN",
        "plan_id": None,
        "schema_version": None,
    }
    if report.state in {"GOVERNED_ACTIVE", "PLAN_SCHEMA_REFRESH_REQUIRED"}:
        doc = load_plan(active_plan_path(root))
        payload.update(
            {
                "contract_state": contract_state(doc.frontmatter),
                "plan_id": doc.frontmatter.get("plan_id"),
                "schema_version": doc.frontmatter.get("schema_version"),
            }
        )
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_plan_contract_upgrade_apply(args: argparse.Namespace) -> None:
    """Stage and activate one exact active schema-v3-to-v4 contract upgrade."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    with lock(root):
        require_governed_authority(root)
        source = load_plan(active_plan_path(root))
        session_receipt: Mapping[str, object] | None = None
        if STRICT_INITIAL_INTAKE_REQUIRED:
            session_receipt = cast(
                Mapping[str, object],
                validate_current_ready_receipt(
                    root,
                    args.receipt_sha256,
                    require_current_controller=True,
                ),
            )
        preparation = prepare_contract_upgrade(
            root,
            manifest_path,
            source,
            source_sha256=sha256_file(source.path),
            session_receipt=session_receipt,
        )
        journal_path = stage_contract_upgrade(root, manifest_path, preparation)
        resume_contract_upgrade(root, journal_path)


def cmd_plan_contract_upgrade_recover(args: argparse.Namespace) -> None:
    """Recover the sole or named incomplete contract upgrade."""
    root = project_root()
    with lock(root):
        base = governance_root(root) / "runtime" / "contract-upgrades"
        if args.transaction_id:
            journal = contract_upgrade_transaction_dir(root, args.transaction_id) / "journal.json"
            if not journal.is_file():
                raise WorkctlError("CONTRACT_UPGRADE_JOURNAL_NOT_FOUND")
        else:
            journals = sorted(base.glob("*/journal.json")) if base.is_dir() else []
            incomplete = [
                path for path in journals if load_yaml_file(path).get("status") != "committed"
            ]
            if len(incomplete) != 1:
                raise WorkctlError(
                    "CONTRACT_UPGRADE_RECOVERY_AMBIGUOUS"
                    if incomplete
                    else "CONTRACT_UPGRADE_RECOVERY_NOT_REQUIRED"
                )
            journal = incomplete[0]
        resume_contract_upgrade(root, journal)


STRUCTURAL_REBASE_CHANGE_FIELDS = {
    "goal",
    "scope",
    "obligations",
    "tasks",
    "validations",
    "route",
    "handoff",
    "confirmations",
    "independent_validation",
}


@dataclass(frozen=True)
class StructuralRebasePreparation:
    """Bind a staged same-Plan structural rebase to its immutable inputs."""

    manifest: dict[str, Any]
    target: PlanDocument
    source_sha256: str
    index_sha256: str


def structural_rebase_transaction_dir(root: Path, transaction_id: str) -> Path:
    """Return one ignored structural-rebase transaction directory."""
    return governance_root(root) / "runtime" / "structural-rebases" / transaction_id


def load_structural_rebase_manifest(path: Path) -> dict[str, Any]:
    """Load the closed envelope for one authenticated Plan structure rebase."""
    manifest = load_yaml_file(path)
    required = {
        "schema_version",
        "kind",
        "transaction_id",
        "plan_id",
        "expected_revision",
        "plan_sha256",
        "index_sha256",
        "authorization",
        "rationale",
        "changes",
        "confirmation_rebindings",
    }
    if set(manifest) != required:
        raise WorkctlError("INVALID_STRUCTURAL_REBASE_MANIFEST_FIELDS")
    authorization = manifest.get("authorization")
    changes = manifest.get("changes")
    rebindings = manifest.get("confirmation_rebindings")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "plan-structural-rebase"
        or not isinstance(manifest.get("transaction_id"), str)
        or STRUCTURAL_REBASE_ID_RE.fullmatch(str(manifest["transaction_id"])) is None
        or not isinstance(manifest.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(manifest["plan_id"])) is None
        or type(manifest.get("expected_revision")) is not int
        or not isinstance(manifest.get("plan_sha256"), str)
        or SHA256_RE.fullmatch(str(manifest["plan_sha256"])) is None
        or not isinstance(manifest.get("index_sha256"), str)
        or SHA256_RE.fullmatch(str(manifest["index_sha256"])) is None
        or not isinstance(manifest.get("rationale"), str)
        or not manifest["rationale"].strip()
        or not isinstance(changes, dict)
        or not changes
        or not set(changes).issubset(STRUCTURAL_REBASE_CHANGE_FIELDS)
        or not isinstance(rebindings, list)
        or not all(isinstance(item, str) and item.startswith("C-") for item in rebindings)
        or len(rebindings) != len(set(rebindings))
        or not isinstance(authorization, dict)
        or set(authorization) != {"id", "ref", "accepted_at", "basis_sha256"}
        or not isinstance(authorization.get("id"), str)
        or not str(authorization["id"]).startswith("C-")
        or not valid_reference(authorization.get("ref"))
        or not isinstance(authorization.get("accepted_at"), str)
        or not authorization["accepted_at"]
        or not isinstance(authorization.get("basis_sha256"), str)
        or SHA256_RE.fullmatch(str(authorization["basis_sha256"])) is None
    ):
        raise WorkctlError("INVALID_STRUCTURAL_REBASE_MANIFEST")
    return manifest


def rebase_authorization_confirmation(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Build the audit-only accepted confirmation derived from the manifest."""
    authorization = cast(dict[str, Any], manifest["authorization"])
    return {
        "id": authorization["id"],
        "description": "Record the exact authority for this recoverable Plan structural rebase.",
        "status": "accepted",
        "ref": authorization["ref"],
        "accepted_at": authorization["accepted_at"],
        "evidence_sha256": authorization["basis_sha256"],
        "intervention": {
            "kind": "plan_contract",
            "blocks": ["route"],
            "basis_ref": authorization["ref"],
            "basis_sha256": authorization["basis_sha256"],
        },
    }


def validate_structural_rebase_transition(
    source: Mapping[str, Any], target: Mapping[str, Any], manifest: Mapping[str, Any]
) -> None:
    """Reject a rebase that changes status, completed facts, or review evidence."""
    for field in (
        "plan_id",
        "title",
        "status",
        "mode",
        "created_at",
        "authority",
        "unknowns",
        "artifacts",
        "delivery",
        "activation",
    ):
        if source.get(field) != target.get(field):
            raise WorkctlError(f"STRUCTURAL_REBASE_IMMUTABLE_FIELD: {field}")
    for field in ("obligations", "validations"):
        before = entries_by_id(cast(dict[str, Any], source), field)
        after = entries_by_id(cast(dict[str, Any], target), field)
        if set(before) - set(after):
            raise WorkctlError(f"STRUCTURAL_REBASE_{field.upper()}_REMOVAL")
        for entry_id, item in before.items():
            if after[entry_id].get("status") != item.get("status"):
                raise WorkctlError(f"STRUCTURAL_REBASE_STATUS_IMMUTABLE: {entry_id}")
        for entry_id in set(after) - set(before):
            if after[entry_id].get("status") != "pending":
                raise WorkctlError(f"STRUCTURAL_REBASE_NEW_ENTRY_MUST_BE_PENDING: {entry_id}")
    before_tasks = tasks_by_id(cast(dict[str, Any], source))
    after_tasks = tasks_by_id(cast(dict[str, Any], target))
    if set(before_tasks) - set(after_tasks):
        raise WorkctlError("STRUCTURAL_REBASE_TASK_REMOVAL")
    for task_id, task in before_tasks.items():
        candidate = after_tasks[task_id]
        if candidate.get("status") != task.get("status"):
            raise WorkctlError(f"STRUCTURAL_REBASE_STATUS_IMMUTABLE: {task_id}")
        if candidate.get("requires_confirmation") != task.get("requires_confirmation"):
            raise WorkctlError(f"STRUCTURAL_REBASE_TASK_GATE_IMMUTABLE: {task_id}")
    for task_id in set(after_tasks) - set(before_tasks):
        if after_tasks[task_id].get("status") != "pending":
            raise WorkctlError(f"STRUCTURAL_REBASE_NEW_TASK_MUST_BE_PENDING: {task_id}")
    before_confirmations = confirmations(cast(dict[str, Any], source))
    after_confirmations = confirmations(cast(dict[str, Any], target))
    authorization_id = str(cast(dict[str, Any], manifest["authorization"])["id"])
    rebindings = set(cast(list[str], manifest["confirmation_rebindings"]))
    if authorization_id in before_confirmations or authorization_id not in after_confirmations:
        raise WorkctlError("STRUCTURAL_REBASE_AUTHORIZATION_CONFIRMATION_INVALID")
    for confirmation_id, item in before_confirmations.items():
        candidate_confirmation = after_confirmations.get(confirmation_id)
        if candidate_confirmation is None:
            raise WorkctlError(f"STRUCTURAL_REBASE_CONFIRMATION_REMOVAL: {confirmation_id}")
        if item.get("status") != "pending" and candidate_confirmation != item:
            raise WorkctlError(
                f"STRUCTURAL_REBASE_DECIDED_CONFIRMATION_IMMUTABLE: {confirmation_id}"
            )
        if item.get("status") == "pending" and candidate_confirmation != item:
            if (
                confirmation_id not in rebindings
                or candidate_confirmation.get("status") != "pending"
            ):
                raise WorkctlError(f"STRUCTURAL_REBASE_REBINDING_FORBIDDEN: {confirmation_id}")
            if any(
                key in candidate_confirmation
                for key in ("ref", "accepted_at", "decided_at", "evidence_sha256")
            ):
                raise WorkctlError(
                    f"STRUCTURAL_REBASE_PENDING_CONFIRMATION_INVALID: {confirmation_id}"
                )
    for confirmation_id in rebindings:
        if confirmation_id not in before_confirmations or before_confirmations[
            confirmation_id
        ] == after_confirmations.get(confirmation_id):
            raise WorkctlError(f"STRUCTURAL_REBASE_REBINDING_UNUSED: {confirmation_id}")
    for confirmation_id, item in after_confirmations.items():
        if (
            confirmation_id not in before_confirmations
            and confirmation_id != authorization_id
            and (
                item.get("status") != "pending"
                or any(
                    key in item for key in ("ref", "accepted_at", "decided_at", "evidence_sha256")
                )
            )
        ):
            raise WorkctlError(f"STRUCTURAL_REBASE_NEW_CONFIRMATION_INVALID: {confirmation_id}")
    before_review = source.get("independent_validation")
    after_review = target.get("independent_validation")
    if before_review != after_review:
        if not isinstance(before_review, dict) or not isinstance(after_review, dict):
            raise WorkctlError("STRUCTURAL_REBASE_REVIEW_CONTRACT_IMMUTABLE")
        if {key: value for key, value in before_review.items() if key != "reviews"} != {
            key: value for key, value in after_review.items() if key != "reviews"
        }:
            raise WorkctlError("STRUCTURAL_REBASE_REVIEW_CONTRACT_IMMUTABLE")
        before_by_mode = {
            str(item.get("mode")): item
            for item in before_review.get("reviews", [])
            if isinstance(item, dict)
        }
        after_by_mode = {
            str(item.get("mode")): item
            for item in after_review.get("reviews", [])
            if isinstance(item, dict)
        }
        if set(before_by_mode) != set(after_by_mode):
            raise WorkctlError("STRUCTURAL_REBASE_REVIEW_MODE_IMMUTABLE")
        for mode, review in before_by_mode.items():
            candidate = after_by_mode[mode]
            if review.get("state") != "pending" or candidate.get("state") != "pending":
                raise WorkctlError("STRUCTURAL_REBASE_RECORDED_REVIEW_IMMUTABLE")
            if {key: value for key, value in review.items() if key != "blocks"} != {
                key: value for key, value in candidate.items() if key != "blocks"
            }:
                raise WorkctlError("STRUCTURAL_REBASE_REVIEW_EVIDENCE_IMMUTABLE")


def prepare_structural_rebase(
    root: Path,
    manifest_path: Path,
    source: PlanDocument,
    *,
    dry_run: bool = False,
) -> StructuralRebasePreparation:
    """Build the exact same-Plan target before publishing a transaction journal."""
    manifest = load_structural_rebase_manifest(manifest_path)
    source_sha256 = sha256_file(source.path)
    current_index_sha256 = sha256_file(index_path(root))
    if (
        source.frontmatter.get("schema_version") != 4
        or source.frontmatter.get("plan_id") != manifest["plan_id"]
        or source.frontmatter.get("revision") != manifest["expected_revision"]
        or source_sha256 != manifest["plan_sha256"]
        or current_index_sha256 != manifest["index_sha256"]
    ):
        raise WorkctlError("STRUCTURAL_REBASE_INPUT_DRIFT")
    target = PlanDocument(source.path, copy.deepcopy(source.frontmatter), source.body)
    changes = cast(dict[str, Any], manifest["changes"])
    for field, value in changes.items():
        target.frontmatter[field] = copy.deepcopy(value)
    raw_confirmations = target.frontmatter.get("confirmations")
    if not isinstance(raw_confirmations, dict) or not isinstance(
        raw_confirmations.get("required"), list
    ):
        raise WorkctlError("STRUCTURAL_REBASE_CONFIRMATIONS_INVALID")
    authorization = rebase_authorization_confirmation(manifest)
    raw_confirmations["required"].append(authorization)
    contract = target.frontmatter.get("contract")
    if not isinstance(contract, dict) or type(contract.get("revision")) is not int:
        raise WorkctlError("STRUCTURAL_REBASE_CONTRACT_INVALID")
    contract["revision"] = int(contract["revision"]) + 1
    contract["confirmation_id"] = authorization["id"]
    contract["confirmed_ref"] = authorization["ref"]
    validate_structural_rebase_transition(source.frontmatter, target.frontmatter, manifest)
    bump_revision(
        target.frontmatter,
        kind="structural-rebase",
        rationale=str(manifest["rationale"]),
        confirmation_id=str(authorization["id"]),
        timestamp=source.frontmatter.get("updated_at") if dry_run else None,
    )
    require_valid_candidate(target)
    require_strict_intervention_contract(target.frontmatter)
    return StructuralRebasePreparation(manifest, target, source_sha256, current_index_sha256)


def structural_rebase_proposal(preparation: StructuralRebasePreparation) -> dict[str, Any]:
    """Return the stable dry-run digest payload for one prepared rebase."""
    manifest = preparation.manifest
    return {
        "transaction_id": manifest["transaction_id"],
        "plan_id": manifest["plan_id"],
        "source_plan_sha256": preparation.source_sha256,
        "index_sha256": preparation.index_sha256,
        "target_plan_sha256": sha256_bytes(dump_plan(preparation.target).encode()),
        "authorization_id": manifest["authorization"]["id"],
        "changed_fields": sorted(manifest["changes"]),
    }


def stage_structural_rebase(
    root: Path, manifest_path: Path, preparation: StructuralRebasePreparation
) -> Path:
    """Durably stage the target Plan before publishing the recovery journal."""
    transaction_id = str(preparation.manifest["transaction_id"])
    transaction = structural_rebase_transaction_dir(root, transaction_id)
    journal_path = transaction / "journal.json"
    if journal_path.exists():
        return journal_path
    staged = transaction / "staging" / preparation.target.path.name
    target_bytes = dump_plan(preparation.target).encode()
    validate_partial_transaction_directory(
        transaction,
        {relative_project_path(transaction, staged)},
        error="STRUCTURAL_REBASE_TRANSACTION_CONFLICT",
    )
    write_or_validate_staged_bytes(
        staged, target_bytes, error="STRUCTURAL_REBASE_TRANSACTION_CONFLICT"
    )
    journal: dict[str, Any] = {
        "schema_version": 1,
        "kind": "plan-structural-rebase",
        "transaction_id": transaction_id,
        "status": "prepared",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "plan_id": preparation.manifest["plan_id"],
        "source_sha256": preparation.source_sha256,
        "target_sha256": sha256_bytes(target_bytes),
        "index_sha256": preparation.index_sha256,
        "manifest_sha256": sha256_file(manifest_path),
        "staged_path": relative_project_path(root, staged),
        "target_path": relative_project_path(root, preparation.target.path),
    }
    maybe_interrupt_before_transaction_journal("structural-rebase")
    write_transaction_journal(journal_path, journal)
    return journal_path


def resume_structural_rebase(root: Path, journal_path: Path) -> None:
    """Idempotently replace one active Plan only when both source and index match."""
    journal = load_yaml_file(journal_path)
    expected = {
        "schema_version",
        "kind",
        "transaction_id",
        "status",
        "created_at",
        "updated_at",
        "plan_id",
        "source_sha256",
        "target_sha256",
        "index_sha256",
        "manifest_sha256",
        "staged_path",
        "target_path",
    }
    transaction_id = journal.get("transaction_id")
    plan_id = journal.get("plan_id")
    if (
        set(journal) != expected
        or journal.get("schema_version") != 1
        or journal.get("kind") != "plan-structural-rebase"
        or journal.get("status") not in {"prepared", "plan-replaced", "committed"}
        or not isinstance(transaction_id, str)
        or STRUCTURAL_REBASE_ID_RE.fullmatch(transaction_id) is None
        or not isinstance(plan_id, str)
        or PLAN_ID_RE.fullmatch(plan_id) is None
        or journal_path != structural_rebase_transaction_dir(root, transaction_id) / "journal.json"
    ):
        raise WorkctlError("INVALID_STRUCTURAL_REBASE_JOURNAL")
    target = checked_project_path(root, str(journal["target_path"]))
    staged = checked_project_path(root, str(journal["staged_path"]))
    if (
        target != plan_dir(root) / f"{plan_id}.md"
        or staged
        != structural_rebase_transaction_dir(root, transaction_id) / "staging" / f"{plan_id}.md"
        or not target.is_file()
        or not staged.is_file()
        or target.is_symlink()
        or staged.is_symlink()
        or any(
            SHA256_RE.fullmatch(str(journal[field])) is None
            for field in ("source_sha256", "target_sha256", "index_sha256", "manifest_sha256")
        )
        or sha256_file(staged) != journal["target_sha256"]
        or sha256_file(index_path(root)) != journal["index_sha256"]
    ):
        raise WorkctlError("STRUCTURAL_REBASE_RECOVERY_DRIFT")
    current_sha256 = sha256_file(target)
    if journal["status"] == "committed":
        if current_sha256 != journal["target_sha256"]:
            raise WorkctlError("STRUCTURAL_REBASE_COMMITTED_STATE_DRIFT")
        print(f"STRUCTURAL_REBASE_ALREADY_COMMITTED {transaction_id}")
        return
    if current_sha256 == journal["source_sha256"]:
        write_atomic_bytes(target, staged.read_bytes())
    elif current_sha256 != journal["target_sha256"]:
        raise WorkctlError("STRUCTURAL_REBASE_TARGET_DRIFT")
    journal["status"] = "plan-replaced"
    journal["updated_at"] = utc_now()
    write_transaction_journal(journal_path, journal)
    if os.environ.get("WORKCTL_TEST_STRUCTURAL_REBASE_INTERRUPT_AFTER") == "plan-replaced":
        raise WorkctlError("STRUCTURAL_REBASE_TEST_INTERRUPTED: plan-replaced")
    target_doc = load_plan(target)
    require_valid_candidate(target_doc)
    errors = validate_plan(root, ignore_journal=journal_path)
    if errors:
        raise WorkctlError(f"STRUCTURAL_REBASE_APPLIED_BUT_INVALID: {'; '.join(errors)}")
    journal["status"] = "committed"
    journal["updated_at"] = utc_now()
    write_transaction_journal(journal_path, journal)
    print(f"STRUCTURAL_REBASE_COMMITTED {transaction_id} plan={plan_id}")


def cmd_plan_structural_rebase_apply(args: argparse.Namespace) -> None:
    """Dry-run or apply an exact, confirmation-bound active Plan structural rebase."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    if args.dry_run:
        require_governed_authority(root)
        preparation = prepare_structural_rebase(
            root,
            manifest_path,
            load_plan(active_plan_path(root)),
            dry_run=True,
        )
        proposal = structural_rebase_proposal(preparation)
        proposal["proposal_sha256"] = sha256_bytes(
            json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode()
        )
        print(json.dumps(proposal, indent=2, sort_keys=True))
        return
    with lock(root):
        require_governed_authority(root)
        preparation = prepare_structural_rebase(
            root, manifest_path, load_plan(active_plan_path(root))
        )
        resume_structural_rebase(root, stage_structural_rebase(root, manifest_path, preparation))


def cmd_plan_structural_rebase_recover(args: argparse.Namespace) -> None:
    """Recover one named interrupted structural rebase without accepting new input."""
    root = project_root()
    transaction_id = args.transaction_id
    if STRUCTURAL_REBASE_ID_RE.fullmatch(transaction_id) is None:
        raise WorkctlError("INVALID_STRUCTURAL_REBASE_ID")
    with lock(root):
        journal = structural_rebase_transaction_dir(root, transaction_id) / "journal.json"
        if not journal.is_file():
            raise WorkctlError("STRUCTURAL_REBASE_JOURNAL_NOT_FOUND")
        resume_structural_rebase(root, journal)


def reconcile_upgrade_transaction_dir(root: Path, workflow_id: str) -> Path:
    """Return one ignored parent workflow transaction directory."""
    return governance_root(root) / "runtime" / "reconcile-upgrades" / workflow_id


def load_reconcile_upgrade_manifest(root: Path, path: Path) -> dict[str, Any]:
    """Validate and normalize one composed reconciliation-upgrade manifest."""
    manifest = load_yaml_file(path)
    required_fields = {
        "schema_version",
        "kind",
        "workflow_id",
        "reconciliation_manifest",
        "reconciliation_manifest_sha256",
        "contract_upgrade_manifest",
        "contract_upgrade_manifest_sha256",
    }
    if set(manifest) != required_fields:
        raise WorkctlError("INVALID_RECONCILE_UPGRADE_MANIFEST_FIELDS")
    workflow_id = manifest.get("workflow_id")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "plan-reconcile-upgrade"
        or not isinstance(workflow_id, str)
        or RECONCILE_UPGRADE_ID_RE.fullmatch(workflow_id) is None
    ):
        raise WorkctlError("INVALID_RECONCILE_UPGRADE_MANIFEST")
    normalized = copy.deepcopy(manifest)
    for field in ("reconciliation_manifest", "contract_upgrade_manifest"):
        raw_path = manifest.get(field)
        expected_sha256 = manifest.get(f"{field}_sha256")
        if (
            not isinstance(raw_path, str)
            or not isinstance(expected_sha256, str)
            or SHA256_RE.fullmatch(expected_sha256) is None
        ):
            raise WorkctlError("INVALID_RECONCILE_UPGRADE_MANIFEST")
        child_path = manifest_input_path(path, raw_path)
        child_relative = relative_project_path(root, child_path)
        reject_symlink_components(root, child_path)
        if child_path.is_symlink() or not child_path.is_file():
            raise WorkctlError(f"RECONCILE_UPGRADE_CHILD_MANIFEST_MISSING: {field}")
        if sha256_file(child_path) != expected_sha256:
            raise WorkctlError(f"RECONCILE_UPGRADE_CHILD_MANIFEST_DRIFT: {field}")
        normalized[field] = child_relative
    return normalized


def reconcile_upgrade_binding_digest(journal: Mapping[str, Any]) -> str:
    """Hash every field that fixes the parent workflow and its child order."""
    payload = {
        "workflow_id": journal["workflow_id"],
        "manifest_sha256": journal["manifest_sha256"],
        "reconciliation_manifest": journal["reconciliation_manifest"],
        "reconciliation_manifest_sha256": journal["reconciliation_manifest_sha256"],
        "migration_id": journal["migration_id"],
        "migration_journal": journal["migration_journal"],
        "schema3_plan_id": journal["schema3_plan_id"],
        "schema3_target_path": journal["schema3_target_path"],
        "schema3_plan_sha256": journal["schema3_plan_sha256"],
        "schema3_staged_path": journal["schema3_staged_path"],
        "contract_upgrade_manifest": journal["contract_upgrade_manifest"],
        "contract_upgrade_manifest_sha256": journal["contract_upgrade_manifest_sha256"],
        "contract_upgrade_id": journal["contract_upgrade_id"],
        "contract_upgrade_journal": journal["contract_upgrade_journal"],
        "schema4_plan_sha256": journal["schema4_plan_sha256"],
        "schema4_staged_path": journal["schema4_staged_path"],
        "intake_binding": journal["intake_binding"],
        "child_order": ["reconciliation", "contract-upgrade"],
    }
    return sha256_bytes(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def stage_reconcile_upgrade(
    root: Path,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    target_doc: PlanDocument,
    upgrade: ContractUpgradePreparation,
) -> Path:
    """Persist immutable parent bytes before either child mutates authority."""
    workflow_id = str(manifest["workflow_id"])
    transaction = reconcile_upgrade_transaction_dir(root, workflow_id)
    journal_path = transaction / "journal.json"
    if journal_path.exists():
        return journal_path
    staging = transaction / "staging"
    schema3_staged = staging / "schema3-plan.md"
    schema4_staged = staging / "schema4-plan.md"
    schema3_bytes = dump_plan(target_doc).encode("utf-8")
    schema4_bytes = dump_plan(upgrade.upgraded).encode("utf-8")
    conflict_error = "RECONCILE_UPGRADE_TRANSACTION_CONFLICT"
    validate_partial_transaction_directory(
        transaction,
        {
            relative_project_path(transaction, schema3_staged),
            relative_project_path(transaction, schema4_staged),
        },
        error=conflict_error,
    )
    write_or_validate_staged_bytes(
        schema3_staged,
        schema3_bytes,
        error=conflict_error,
    )
    write_or_validate_staged_bytes(
        schema4_staged,
        schema4_bytes,
        error=conflict_error,
    )
    migration_id = str(reconciliation["migration_id"])
    contract_upgrade_id = str(upgrade.manifest["transaction_id"])
    journal: dict[str, Any] = {
        "schema_version": 1,
        "kind": "plan-reconcile-upgrade",
        "workflow_id": workflow_id,
        "status": "prepared",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "manifest_sha256": sha256_file(manifest_path),
        "reconciliation_manifest": manifest["reconciliation_manifest"],
        "reconciliation_manifest_sha256": manifest["reconciliation_manifest_sha256"],
        "migration_id": migration_id,
        "migration_journal": plan_relative_path(".migrations", f"{migration_id}.yaml"),
        "schema3_plan_id": target_doc.frontmatter["plan_id"],
        "schema3_target_path": relative_project_path(root, target_doc.path),
        "schema3_plan_sha256": sha256_bytes(schema3_bytes),
        "schema3_staged_path": relative_project_path(root, schema3_staged),
        "contract_upgrade_manifest": manifest["contract_upgrade_manifest"],
        "contract_upgrade_manifest_sha256": manifest["contract_upgrade_manifest_sha256"],
        "contract_upgrade_id": contract_upgrade_id,
        "contract_upgrade_journal": relative_project_path(
            root,
            contract_upgrade_transaction_dir(root, contract_upgrade_id) / "journal.json",
        ),
        "schema4_plan_sha256": sha256_bytes(schema4_bytes),
        "schema4_staged_path": relative_project_path(root, schema4_staged),
        "intake_binding": upgrade.intake_binding,
    }
    journal["workflow_binding_sha256"] = reconcile_upgrade_binding_digest(journal)
    maybe_interrupt_before_transaction_journal("parent")
    write_transaction_journal(journal_path, journal)
    return journal_path


def load_reconcile_upgrade_journal(root: Path, journal_path: Path) -> dict[str, Any]:
    """Authenticate a parent journal and both immutable prepared Plan states."""
    reject_symlink_components(root, journal_path)
    if journal_path.is_symlink() or not journal_path.is_file():
        raise WorkctlError("INVALID_RECONCILE_UPGRADE_JOURNAL")
    journal = load_yaml_file(journal_path)
    expected_keys = {
        "schema_version",
        "kind",
        "workflow_id",
        "status",
        "created_at",
        "updated_at",
        "manifest_sha256",
        "reconciliation_manifest",
        "reconciliation_manifest_sha256",
        "migration_id",
        "migration_journal",
        "schema3_plan_id",
        "schema3_target_path",
        "schema3_plan_sha256",
        "schema3_staged_path",
        "contract_upgrade_manifest",
        "contract_upgrade_manifest_sha256",
        "contract_upgrade_id",
        "contract_upgrade_journal",
        "schema4_plan_sha256",
        "schema4_staged_path",
        "intake_binding",
        "workflow_binding_sha256",
    }
    workflow_id = journal.get("workflow_id")
    migration_id = journal.get("migration_id")
    contract_upgrade_id = journal.get("contract_upgrade_id")
    plan_id = journal.get("schema3_plan_id")
    if (
        set(journal) != expected_keys
        or journal.get("schema_version") != 1
        or journal.get("kind") != "plan-reconcile-upgrade"
        or journal.get("status")
        not in {"prepared", "children-staged", "reconciliation-committed", "committed"}
        or not isinstance(workflow_id, str)
        or RECONCILE_UPGRADE_ID_RE.fullmatch(workflow_id) is None
        or journal_path != reconcile_upgrade_transaction_dir(root, workflow_id) / "journal.json"
        or not isinstance(migration_id, str)
        or MIGRATION_ID_RE.fullmatch(migration_id) is None
        or not isinstance(contract_upgrade_id, str)
        or CONTRACT_UPGRADE_ID_RE.fullmatch(contract_upgrade_id) is None
        or not isinstance(plan_id, str)
        or PLAN_ID_RE.fullmatch(plan_id) is None
    ):
        raise WorkctlError("INVALID_RECONCILE_UPGRADE_JOURNAL")
    for field in (
        "manifest_sha256",
        "reconciliation_manifest_sha256",
        "schema3_plan_sha256",
        "contract_upgrade_manifest_sha256",
        "schema4_plan_sha256",
        "workflow_binding_sha256",
    ):
        if (
            not isinstance(journal.get(field), str)
            or SHA256_RE.fullmatch(str(journal[field])) is None
        ):
            raise WorkctlError("INVALID_RECONCILE_UPGRADE_JOURNAL")
    transaction = reconcile_upgrade_transaction_dir(root, workflow_id)
    expected_schema3_staged = transaction / "staging" / "schema3-plan.md"
    expected_schema4_staged = transaction / "staging" / "schema4-plan.md"
    schema3_staged = checked_project_path(root, str(journal.get("schema3_staged_path")))
    schema4_staged = checked_project_path(root, str(journal.get("schema4_staged_path")))
    schema3_target = checked_project_path(root, str(journal.get("schema3_target_path")))
    reconciliation_manifest = checked_project_path(
        root,
        str(journal.get("reconciliation_manifest")),
    )
    contract_upgrade_manifest = checked_project_path(
        root,
        str(journal.get("contract_upgrade_manifest")),
    )
    migration_journal = checked_project_path(root, str(journal.get("migration_journal")))
    contract_upgrade_journal = checked_project_path(
        root,
        str(journal.get("contract_upgrade_journal")),
    )
    for path in (
        schema3_staged,
        schema4_staged,
        schema3_target,
        reconciliation_manifest,
        contract_upgrade_manifest,
        migration_journal,
        contract_upgrade_journal,
    ):
        reject_symlink_components(root, path)
    if (
        schema3_staged != expected_schema3_staged
        or schema4_staged != expected_schema4_staged
        or schema3_target != plan_dir(root) / f"{plan_id}.md"
        or migration_journal != plan_dir(root) / ".migrations" / f"{migration_id}.yaml"
        or contract_upgrade_journal
        != contract_upgrade_transaction_dir(root, contract_upgrade_id) / "journal.json"
        or sha256_file(schema3_staged) != journal["schema3_plan_sha256"]
        or sha256_file(schema4_staged) != journal["schema4_plan_sha256"]
        or sha256_file(reconciliation_manifest) != journal["reconciliation_manifest_sha256"]
        or sha256_file(contract_upgrade_manifest) != journal["contract_upgrade_manifest_sha256"]
        or reconcile_upgrade_binding_digest(journal) != journal["workflow_binding_sha256"]
    ):
        raise WorkctlError("RECONCILE_UPGRADE_BINDING_DRIFT")
    schema3_doc = load_plan(schema3_staged)
    schema4_doc = load_plan(schema4_staged)
    require_valid_candidate(schema3_doc)
    require_valid_candidate(schema4_doc)
    require_strict_intervention_contract(schema4_doc.frontmatter)
    require_new_plan_reviews_pending(schema4_doc.frontmatter)
    if (
        schema3_doc.frontmatter.get("schema_version") != 3
        or schema4_doc.frontmatter.get("schema_version") != 4
        or schema3_doc.frontmatter.get("plan_id") != plan_id
        or schema4_doc.frontmatter.get("plan_id") != plan_id
    ):
        raise WorkctlError("INVALID_RECONCILE_UPGRADE_JOURNAL")
    return journal


def write_reconcile_upgrade_journal(
    journal_path: Path,
    journal: dict[str, Any],
    status: str,
) -> None:
    """Advance one authenticated parent state after a child boundary."""
    journal["status"] = status
    journal["updated_at"] = utc_now()
    write_transaction_journal(journal_path, journal)


def resume_reconcile_upgrade(root: Path, journal_path: Path) -> None:
    """Recover the only legal next child without collapsing child journals."""
    journal = load_reconcile_upgrade_journal(root, journal_path)
    reconciliation_manifest_path = checked_project_path(
        root,
        str(journal["reconciliation_manifest"]),
    )
    migration_journal_path = checked_project_path(root, str(journal["migration_journal"]))
    contract_upgrade_journal_path = checked_project_path(
        root,
        str(journal["contract_upgrade_journal"]),
    )
    if journal["status"] == "committed":
        contract_upgrade_journal = load_yaml_file(contract_upgrade_journal_path)
        if contract_upgrade_journal.get("status") != "committed":
            raise WorkctlError("RECONCILE_UPGRADE_COMMITTED_STATE_INVALID")
        validate_committed_migration(root, migration_journal_path)
        resume_contract_upgrade(root, contract_upgrade_journal_path)
        active = load_plan(active_plan_path(root))
        if (
            active.frontmatter.get("plan_id") != journal["schema3_plan_id"]
            or sha256_file(active.path) != journal["schema4_plan_sha256"]
            or active.frontmatter.get("schema_version") != 4
        ):
            raise WorkctlError("RECONCILE_UPGRADE_COMMITTED_STATE_INVALID")
        print(f"RECONCILE_UPGRADE_ALREADY_COMMITTED {journal['workflow_id']}")
        return
    if not migration_journal_path.is_file():
        reconciliation, target_doc, _ = prepare_reconciliation(
            root,
            reconciliation_manifest_path,
            require_confirmations=True,
        )
        if (
            reconciliation["migration_id"] != journal["migration_id"]
            or target_doc.frontmatter.get("plan_id") != journal["schema3_plan_id"]
            or sha256_bytes(dump_plan(target_doc).encode("utf-8")) != journal["schema3_plan_sha256"]
        ):
            raise WorkctlError("RECONCILE_UPGRADE_RECONCILIATION_DRIFT")
        staged_journal = stage_reconciliation(root, reconciliation, target_doc)
        if staged_journal != migration_journal_path:
            raise WorkctlError("INVALID_RECONCILE_UPGRADE_JOURNAL")
    contract_upgrade_manifest_path = checked_project_path(
        root,
        str(journal["contract_upgrade_manifest"]),
    )
    if not contract_upgrade_journal_path.is_file():
        manifest = load_contract_upgrade_manifest(contract_upgrade_manifest_path)
        schema4_staged = load_plan(checked_project_path(root, str(journal["schema4_staged_path"])))
        upgraded = PlanDocument(
            path=checked_project_path(root, str(journal["schema3_target_path"])),
            frontmatter=schema4_staged.frontmatter,
            body=schema4_staged.body,
        )
        intake_binding = journal["intake_binding"]
        if STRICT_INITIAL_INTAKE_REQUIRED and not isinstance(intake_binding, dict):
            raise WorkctlError("INVALID_RECONCILE_UPGRADE_JOURNAL")
        preparation = ContractUpgradePreparation(
            manifest=manifest,
            upgraded=upgraded,
            source_sha256=str(journal["schema3_plan_sha256"]),
            intake_binding=(
                cast(dict[str, object], intake_binding)
                if isinstance(intake_binding, dict)
                else None
            ),
        )
        staged_journal = stage_contract_upgrade(
            root,
            contract_upgrade_manifest_path,
            preparation,
        )
        if staged_journal != contract_upgrade_journal_path:
            raise WorkctlError("INVALID_RECONCILE_UPGRADE_JOURNAL")
    write_reconcile_upgrade_journal(journal_path, journal, "children-staged")
    resume_migration(root, migration_journal_path)
    validate_committed_migration(root, migration_journal_path)
    write_reconcile_upgrade_journal(journal_path, journal, "reconciliation-committed")
    if os.environ.get("WORKCTL_TEST_RECONCILE_UPGRADE_INTERRUPT_AFTER") == (
        "reconciliation-committed"
    ):
        raise WorkctlError("RECONCILE_UPGRADE_TEST_INTERRUPTED: reconciliation-committed")
    contract_upgrade_journal = load_yaml_file(contract_upgrade_journal_path)
    contract_upgrade_status = contract_upgrade_journal.get("status")
    if contract_upgrade_status not in {"prepared", "plan-replaced", "committed"}:
        raise WorkctlError("INVALID_CONTRACT_UPGRADE_JOURNAL")
    if contract_upgrade_status in {"prepared", "plan-replaced"}:
        active = load_plan(active_plan_path(root))
        expected_active_sha256 = (
            journal["schema3_plan_sha256"]
            if contract_upgrade_status == "prepared"
            else journal["schema4_plan_sha256"]
        )
        expected_schema_version = 3 if contract_upgrade_status == "prepared" else 4
        if (
            active.frontmatter.get("plan_id") != journal["schema3_plan_id"]
            or sha256_file(active.path) != expected_active_sha256
            or active.frontmatter.get("schema_version") != expected_schema_version
        ):
            raise WorkctlError("RECONCILE_UPGRADE_CHILD_ORDER_VIOLATION")
    resume_contract_upgrade(root, contract_upgrade_journal_path)
    active = load_plan(active_plan_path(root))
    if (
        active.frontmatter.get("plan_id") != journal["schema3_plan_id"]
        or sha256_file(active.path) != journal["schema4_plan_sha256"]
        or active.frontmatter.get("schema_version") != 4
    ):
        raise WorkctlError("RECONCILE_UPGRADE_FINAL_STATE_DRIFT")
    write_reconcile_upgrade_journal(journal_path, journal, "committed")
    print(
        "RECONCILE_UPGRADE_COMMITTED "
        f"{journal['workflow_id']} migration={journal['migration_id']} "
        f"upgrade={journal['contract_upgrade_id']}"
    )


def cmd_plan_reconcile_upgrade_apply(args: argparse.Namespace) -> None:
    """Validate, stage, and execute the fixed two-child workflow."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    manifest = load_reconcile_upgrade_manifest(root, manifest_path)
    workflow_id = str(manifest["workflow_id"])
    with lock(root):
        journal_path = reconcile_upgrade_transaction_dir(root, workflow_id) / "journal.json"
        if journal_path.is_file():
            journal = load_reconcile_upgrade_journal(root, journal_path)
            if journal["manifest_sha256"] != sha256_file(manifest_path):
                raise WorkctlError("RECONCILE_UPGRADE_MANIFEST_DRIFT")
            resume_reconcile_upgrade(root, journal_path)
            return
        if (
            incomplete_migration_journals(root)
            or incomplete_rollover_journals(root)
            or incomplete_retirement_journals(root)
            or incomplete_contract_upgrade_journals(root)
            or incomplete_reconcile_upgrade_journals(root)
        ):
            raise WorkctlError("MIGRATION_RECOVERY_REQUIRED")
        reconciliation_manifest_path = checked_project_path(
            root,
            str(manifest["reconciliation_manifest"]),
        )
        reconciliation, target_doc, _ = prepare_reconciliation(
            root,
            reconciliation_manifest_path,
            require_confirmations=True,
        )
        report = inspect_authority(root)
        if report.state == "GOVERNED_ACTIVE":
            raise WorkctlError("RECONCILIATION_NOT_REQUIRED")
        session_receipt: Mapping[str, object] | None = None
        if STRICT_INITIAL_INTAKE_REQUIRED:
            session_receipt = cast(
                Mapping[str, object],
                validate_current_ready_receipt(
                    root,
                    args.receipt_sha256,
                    require_current_controller=True,
                ),
            )
        contract_upgrade_manifest_path = checked_project_path(
            root,
            str(manifest["contract_upgrade_manifest"]),
        )
        source_sha256 = sha256_bytes(dump_plan(target_doc).encode("utf-8"))
        upgrade = prepare_contract_upgrade(
            root,
            contract_upgrade_manifest_path,
            target_doc,
            source_sha256=source_sha256,
            session_receipt=session_receipt,
        )
        journal_path = stage_reconcile_upgrade(
            root,
            manifest_path,
            manifest,
            reconciliation,
            target_doc,
            upgrade,
        )
        resume_reconcile_upgrade(root, journal_path)


def cmd_plan_reconcile_upgrade_recover(args: argparse.Namespace) -> None:
    """Recover one named or the sole incomplete composed workflow."""
    root = project_root()
    with lock(root):
        base = governance_root(root) / "runtime" / "reconcile-upgrades"
        if args.workflow_id:
            journal = reconcile_upgrade_transaction_dir(root, args.workflow_id) / "journal.json"
            if not journal.is_file():
                raise WorkctlError("RECONCILE_UPGRADE_JOURNAL_NOT_FOUND")
        else:
            journals = sorted(base.glob("*/journal.json")) if base.is_dir() else []
            incomplete = [
                path for path in journals if load_yaml_file(path).get("status") != "committed"
            ]
            if len(incomplete) != 1:
                raise WorkctlError(
                    "RECONCILE_UPGRADE_RECOVERY_AMBIGUOUS"
                    if incomplete
                    else "RECONCILE_UPGRADE_RECOVERY_NOT_REQUIRED"
                )
            journal = incomplete[0]
        resume_reconcile_upgrade(root, journal)


def read_workflow_input_bytes(
    args: argparse.Namespace,
    *,
    stdin_attr: str,
    file_attr: str,
    required: bool,
    max_bytes: int = EVIDENCE_MANIFEST_MAX_BYTES,
) -> bytes | None:
    """Read one bounded high-level workflow input from stdin or a file."""
    use_stdin = bool(getattr(args, stdin_attr, False))
    raw_path = getattr(args, file_attr, None)
    if module_read_workflow_input_bytes is None:
        raise WorkctlError("WORKFLOW_INPUT_MODULE_UNAVAILABLE: read_workflow_input_bytes")
    try:
        return module_read_workflow_input_bytes(
            use_stdin=use_stdin,
            raw_path=raw_path,
            required=required,
            max_bytes=max_bytes,
            stdin_reader=sys.stdin.buffer.read,
        )
    except ModuleWorkflowInputError as exc:
        raise WorkctlError(str(exc)) from exc


def parse_workflow_mapping(content: bytes, *, error_prefix: str) -> dict[str, Any]:
    """Parse a bounded JSON/YAML workflow mapping."""
    if module_parse_workflow_mapping is None:
        raise WorkctlError("WORKFLOW_CONTRACT_MODULE_UNAVAILABLE: parse_workflow_mapping")
    try:
        return cast(
            dict[str, Any],
            module_parse_workflow_mapping(content, error_prefix=error_prefix),
        )
    except ModuleWorkflowContractError as exc:
        raise WorkctlError(str(exc)) from exc


def non_empty_string(value: object, *, field: str) -> str:
    """Return a non-empty string field or raise a workflow contract error."""
    if module_non_empty_string is None:
        raise WorkctlError("WORKFLOW_CONTRACT_MODULE_UNAVAILABLE: non_empty_string")
    try:
        return module_non_empty_string(value, field=field)
    except ModuleWorkflowContractError as exc:
        raise WorkctlError(str(exc)) from exc


def workflow_string_list(value: object, *, field: str) -> list[str]:
    """Validate one non-empty list of strings for high-level contracts."""
    if module_workflow_string_list is None:
        raise WorkctlError("WORKFLOW_CONTRACT_MODULE_UNAVAILABLE: workflow_string_list")
    try:
        return module_workflow_string_list(value, field=field)
    except ModuleWorkflowContractError as exc:
        raise WorkctlError(str(exc)) from exc


def next_available_plan_id(root: Path) -> str:
    """Allocate the next date-scoped Plan ID without reading historical schema strictly."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    highest = 0
    if plan_dir(root).is_dir():
        for path in plan_dir(root).glob(f"PLAN-{today}-*.md"):
            match = PLAN_ID_RE.fullmatch(path.stem)
            if match is not None:
                highest = max(highest, int(path.stem.rsplit("-", 1)[1]))
    if index_path(root).is_file():
        try:
            index = load_yaml_file(index_path(root))
        except WorkctlError:
            index = {}
        plans = index.get("plans", []) if isinstance(index, dict) else []
        for item in plans if isinstance(plans, list) else []:
            plan_id = item.get("id") if isinstance(item, dict) else None
            if isinstance(plan_id, str) and plan_id.startswith(f"PLAN-{today}-"):
                highest = max(highest, int(plan_id.rsplit("-", 1)[1]))
    return f"PLAN-{today}-{highest + 1:03d}"


def normalize_goal_tasks(raw_tasks: object) -> list[dict[str, Any]]:
    """Normalize a minimal task list into v5 contract task mappings."""
    if module_normalize_goal_tasks is None:
        raise WorkctlError("WORKFLOW_CONTRACT_MODULE_UNAVAILABLE: normalize_goal_tasks")
    try:
        return cast(
            list[dict[str, Any]],
            module_normalize_goal_tasks(
                raw_tasks,
                task_id_pattern=ENTRY_ID_PATTERNS["tasks"],
            ),
        )
    except ModuleWorkflowContractError as exc:
        raise WorkctlError(str(exc)) from exc


def normalize_goal_confirmations(raw_confirmations: object) -> dict[str, list[dict[str, Any]]]:
    """Normalize the optional minimal confirmation mapping."""
    if module_normalize_goal_confirmations is None:
        raise WorkctlError("WORKFLOW_CONTRACT_MODULE_UNAVAILABLE: normalize_goal_confirmations")
    try:
        return cast(
            dict[str, list[dict[str, Any]]],
            module_normalize_goal_confirmations(raw_confirmations),
        )
    except ModuleWorkflowContractError as exc:
        raise WorkctlError(str(exc)) from exc


def build_goal_init_document(
    root: Path,
    contract: Mapping[str, Any],
    *,
    plan_id_arg: str | None,
    title_arg: str | None,
) -> PlanDocument:
    """Build one canonical minimal schema-v5 Plan document from a goal contract."""
    now = utc_now()
    plan_id = plan_id_arg or contract.get("plan_id") or next_available_plan_id(root)
    if not isinstance(plan_id, str) or PLAN_ID_RE.fullmatch(plan_id) is None:
        raise WorkctlError("GOAL_PLAN_ID_INVALID")
    title = title_arg or non_empty_string(contract.get("title"), field="GOAL_TITLE")
    goal = contract.get("goal")
    if isinstance(goal, dict):
        goal_statement = non_empty_string(goal.get("statement"), field="GOAL_STATEMENT")
        success_value = contract.get("success_conditions", goal.get("success_conditions"))
    else:
        goal_statement = non_empty_string(goal, field="GOAL_STATEMENT")
        success_value = contract.get("success_conditions")
    success_conditions = workflow_string_list(
        success_value,
        field="GOAL_SUCCESS_CONDITIONS",
    )
    tasks = normalize_goal_tasks(contract.get("tasks"))
    confirmations_value = normalize_goal_confirmations(contract.get("confirmations"))
    contract_revision = contract.get("contract_revision", 1)
    if type(contract_revision) is not int or contract_revision < 1:
        raise WorkctlError("GOAL_CONTRACT_REVISION_INVALID")
    frontmatter: dict[str, Any] = {
        "schema_version": 5,
        "plan_id": plan_id,
        "title": title,
        "status": contract.get("status", "active"),
        "contract_revision": contract_revision,
        "created_at": now,
        "updated_at": now,
        "goal": goal_statement,
        "success_conditions": success_conditions,
        "tasks": tasks,
        "confirmations": confirmations_value,
        "truth_refs": copy.deepcopy(contract.get("truth_refs", [])),
        "state_ref": f"runtime:{GOVERNANCE_DIR_NAME}/runtime/plans/{plan_id}/state.json",
        "event_ref": f"runtime:{GOVERNANCE_DIR_NAME}/runtime/plans/{plan_id}/events.jsonl",
        "evidence_store_ref": f"evidence:{GOVERNANCE_DIR_NAME}/evidence",
    }
    body = "# " + title + "\n\n"
    body += "Goal: " + goal_statement + "\n\n"
    body += "## Success Conditions\n"
    body += "".join(f"- {item}\n" for item in success_conditions)
    body += "\n## Tasks\n"
    body += "".join(f"- {task['id']}: {task['description']}\n" for task in tasks)
    return PlanDocument(
        path=plan_dir(root) / f"{plan_id}.md",
        frontmatter=frontmatter,
        body=body,
    )


def write_initial_v5_runtime(root: Path, doc: PlanDocument) -> None:
    """Create the initial runtime state and event ledger for a minimal v5 Plan."""
    plan_id = str(doc.frontmatter["plan_id"])
    state = v5_state_defaults(doc.frontmatter)
    state["event_sequence"] = 1
    state["updated_at"] = doc.frontmatter["updated_at"]
    event = {
        "schema_version": 1,
        "kind": "work-governance-plan-event",
        "plan_id": plan_id,
        "event_sequence": 1,
        "state_sequence": 0,
        "event": "plan.initialized",
        "subject": f"plan:{plan_id}",
        "payload": {
            "contract_revision": doc.frontmatter["contract_revision"],
            "title": doc.frontmatter["title"],
        },
        "recorded_at": doc.frontmatter["created_at"],
    }
    write_atomic(v5_event_path(root, plan_id), "")
    v5_append_event(root, plan_id, event)
    write_atomic(v5_state_path(root, plan_id), json.dumps(state, indent=2, sort_keys=True) + "\n")


def cmd_goal_init(args: argparse.Namespace) -> None:
    """Admit a minimal schema-v5 Plan from a high-level goal contract."""
    root = project_root()
    content = read_workflow_input_bytes(
        args,
        stdin_attr="stdin",
        file_attr="from_file",
        required=True,
    )
    assert content is not None
    contract = parse_workflow_mapping(content, error_prefix="GOAL_CONTRACT")
    with lock(root):
        report = inspect_authority(root)
        if report.state != "UNMANAGED_EMPTY":
            raise WorkctlError(f"GOAL_INIT_AUTHORITY_BLOCKED: {report.state}")
        doc = build_goal_init_document(
            root,
            contract,
            plan_id_arg=args.plan_id,
            title_arg=args.title,
        )
        if doc.path.exists() or doc.path.is_symlink():
            raise WorkctlError("GOAL_PLAN_ALREADY_EXISTS")
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        write_initial_v5_runtime(root, doc)
        write_atomic(index_path(root), yaml.safe_dump(activated_index(root, doc), sort_keys=False))
        errors = validate_plan(root)
        if errors:
            raise WorkctlError("GOAL_INIT_VALIDATION_FAILED: " + "; ".join(errors))
        print(
            json.dumps(
                {
                    "status": "GOAL_INITIALIZED",
                    "plan_id": doc.frontmatter["plan_id"],
                    "schema_version": 5,
                    "contract_revision": doc.frontmatter["contract_revision"],
                    "state_sequence": 0,
                    "event_sequence": 1,
                    "plan_path": relative_project_path(root, doc.path),
                },
                indent=2,
                sort_keys=True,
            )
        )


def persist_direct_evidence_bytes(
    root: Path,
    *,
    plan_id: str,
    task_id: str | None,
    kind: str,
    summary: str,
    raw_content: bytes,
    source_type: str,
    source_ref: str | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    """Persist direct evidence bytes and return the ledger-compatible record."""
    try:
        return cast(
            dict[str, Any],
            capture_module_call("persist_direct_evidence_bytes")(
                root,
                plan_id=plan_id,
                task_id=task_id,
                kind=kind,
                summary=summary,
                raw_content=raw_content,
                source_type=source_type,
                source_ref=source_ref,
                idempotency_key=idempotency_key,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def canonical_workflow_evidence(
    root: Path,
    *,
    plan_id: str,
    subject: str,
    producer_ref: str,
    direct_record: Mapping[str, Any],
) -> tuple[str, str]:
    """Create a canonical Plan evidence record from a direct evidence capture."""
    try:
        payload = cast(
            dict[str, Any],
            capture_module_call("workflow_evidence_payload")(
                plan_id=plan_id,
                subject=subject,
                producer_ref=producer_ref,
                direct_record=direct_record,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc
    return record_evidence_payload(root, plan_id=plan_id, payload=payload, expected_subject=subject)


def read_task_done_source(root: Path, args: argparse.Namespace) -> tuple[bytes, str, str | None]:
    """Read high-level task completion evidence bytes."""
    if bool(args.evidence_stdin) and isinstance(args.evidence_from_file, str):
        raise WorkctlError("TASK_DONE_EVIDENCE_SOURCE_CONFLICT")
    if args.evidence_stdin:
        content = sys.stdin.buffer.read(EVIDENCE_CAPTURE_MAX_BYTES + 1)
        if len(content) > EVIDENCE_CAPTURE_MAX_BYTES:
            raise WorkctlError("EVIDENCE_CAPTURE_TOO_LARGE")
        return content, "stdin", None
    if not isinstance(args.evidence_from_file, str):
        raise WorkctlError("TASK_DONE_EVIDENCE_REQUIRED")
    source = Path(args.evidence_from_file)
    candidate = source if source.is_absolute() else root / source
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkctlError(f"PATH_OUTSIDE_PROJECT: {args.evidence_from_file}") from exc
    reject_symlink_components(root, candidate)
    if candidate.is_symlink() or not candidate.is_file():
        raise WorkctlError("TASK_DONE_EVIDENCE_MISSING")
    content = candidate.read_bytes()
    if len(content) > EVIDENCE_CAPTURE_MAX_BYTES:
        raise WorkctlError("EVIDENCE_CAPTURE_TOO_LARGE")
    return content, "file", relative_project_path(root, candidate)


def verify_task_done_v5(
    root: Path,
    doc: PlanDocument,
    *,
    task_id: str,
    note: str | None,
    expected_state_sequence: int | None,
    evidence_ref: str,
    evidence_sha256: str,
    direct_record: Mapping[str, Any],
) -> int:
    """Complete a v5 task with a workflow-generated evidence pointer."""
    v5_recover_pending_event(root, doc.frontmatter)
    state = load_v5_state(root, doc.frontmatter)
    if expected_state_sequence is not None and state["state_sequence"] != expected_state_sequence:
        raise WorkctlError(
            "STATE_SEQUENCE_MISMATCH: "
            f"expected {expected_state_sequence}, found {state['state_sequence']}"
        )
    runtime = v5_runtime_frontmatter(root, doc.frontmatter, state)
    runtime_task = task_for(runtime, task_id)
    contract_task = task_for(doc.frontmatter, task_id)
    state_task = state["tasks"].get(task_id)
    if not isinstance(state_task, dict):
        raise WorkctlError("SCHEMA_V5_STATE_TASK_MISSING")
    current_status = str(state_task.get("status"))
    if current_status not in {"pending", "in_progress"}:
        raise WorkctlError(f"INVALID_TASK_DONE_TRANSITION: {task_id} {current_status} -> verified")
    require_no_blocking_artifacts(doc.frontmatter, contract_task)
    require_dependencies_verified(runtime, runtime_task)
    require_independent_target(root, doc.frontmatter, f"task:{task_id}")
    require_task_confirmation(doc.frontmatter, contract_task, "verified")
    state_task["status"] = "verified"
    if note:
        state_task["note"] = redacted_runtime_copy(note)
    state_task["evidence_ref"] = evidence_ref
    state_task["evidence_sha256"] = evidence_sha256
    state_task["verified_at"] = utc_now()
    state["current_task"] = None
    v5_persist_state_transition(
        root,
        doc.frontmatter,
        state,
        event="task.verified",
        subject=f"task:{task_id}",
        payload={
            "status": "verified",
            "evidence_ref": evidence_ref,
            "evidence_sha256": evidence_sha256,
            "direct_evidence_ref": direct_record.get("evidence_ref"),
            "direct_evidence_sha256": direct_record.get("evidence_sha256"),
            "note": note,
        },
    )
    return int(state["state_sequence"])


def preflight_task_done_v5(
    root: Path,
    doc: PlanDocument,
    *,
    task_id: str,
    expected_state_sequence: int | None,
) -> None:
    """Validate v5 task completion gates before raw evidence is persisted."""
    v5_recover_pending_event(root, doc.frontmatter)
    state = load_v5_state(root, doc.frontmatter)
    if expected_state_sequence is not None and state["state_sequence"] != expected_state_sequence:
        raise WorkctlError(
            "STATE_SEQUENCE_MISMATCH: "
            f"expected {expected_state_sequence}, found {state['state_sequence']}"
        )
    runtime = v5_runtime_frontmatter(root, doc.frontmatter, state)
    runtime_task = task_for(runtime, task_id)
    contract_task = task_for(doc.frontmatter, task_id)
    state_task = state["tasks"].get(task_id)
    if not isinstance(state_task, dict):
        raise WorkctlError("SCHEMA_V5_STATE_TASK_MISSING")
    current_status = str(state_task.get("status"))
    if current_status not in {"pending", "in_progress"}:
        raise WorkctlError(f"INVALID_TASK_DONE_TRANSITION: {task_id} {current_status} -> verified")
    require_no_blocking_artifacts(doc.frontmatter, contract_task)
    require_dependencies_verified(runtime, runtime_task)
    require_independent_target(root, doc.frontmatter, f"task:{task_id}")
    require_task_confirmation(doc.frontmatter, contract_task, "verified")


def verify_task_done_v4(
    root: Path,
    doc: PlanDocument,
    args: argparse.Namespace,
    *,
    evidence_ref: str,
    evidence_sha256: str,
) -> int:
    """Complete a v4 task with one revision while preserving existing guards."""
    require_expected_revision(doc.frontmatter, args.expected_revision)
    task = task_for(doc.frontmatter, args.task_id)
    require_current_intake(
        root,
        doc.frontmatter,
        turn_receipt_sha256=args.turn_receipt_sha256,
        expected_intake_sha256=args.expected_intake_sha256,
        targets=[f"task:{args.task_id}"],
    )
    current_status = task.get("status")
    if current_status not in {"pending", "in_progress"}:
        raise WorkctlError(
            f"INVALID_TASK_DONE_TRANSITION: {args.task_id} {current_status} -> verified"
        )
    require_no_blocking_artifacts(doc.frontmatter, task)
    require_dependencies_verified(doc.frontmatter, task)
    require_independent_target(root, doc.frontmatter, f"task:{args.task_id}")
    require_task_confirmation(doc.frontmatter, task, "verified")
    task["status"] = "verified"
    if args.note:
        task["note"] = args.note
    task["evidence_ref"] = evidence_ref
    task["evidence_sha256"] = evidence_sha256
    task["verified_at"] = utc_now()
    bump_revision(
        doc.frontmatter,
        kind="controlled-transition",
        rationale=f"Complete {args.task_id} through task done.",
        evidence_manifest=evidence_ref,
    )
    require_valid_candidate(doc)
    write_atomic(doc.path, dump_plan(doc))
    return int(doc.frontmatter["revision"])


def preflight_task_done_v4(root: Path, doc: PlanDocument, args: argparse.Namespace) -> None:
    """Validate v4 task completion gates before raw evidence is persisted."""
    require_expected_revision(doc.frontmatter, args.expected_revision)
    task = task_for(doc.frontmatter, args.task_id)
    require_current_intake(
        root,
        doc.frontmatter,
        turn_receipt_sha256=args.turn_receipt_sha256,
        expected_intake_sha256=args.expected_intake_sha256,
        targets=[f"task:{args.task_id}"],
    )
    current_status = task.get("status")
    if current_status not in {"pending", "in_progress"}:
        raise WorkctlError(
            f"INVALID_TASK_DONE_TRANSITION: {args.task_id} {current_status} -> verified"
        )
    require_no_blocking_artifacts(doc.frontmatter, task)
    require_dependencies_verified(doc.frontmatter, task)
    require_independent_target(root, doc.frontmatter, f"task:{args.task_id}")
    require_task_confirmation(doc.frontmatter, task, "verified")


def cmd_task_done(args: argparse.Namespace) -> None:
    """Capture raw evidence and verify one task through a single workflow command."""
    root = project_root()
    raw_content, source_type, source_ref = read_task_done_source(root, args)
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        plan_id = str(doc.frontmatter["plan_id"])
        task_for(doc.frontmatter, args.task_id)
        if doc.frontmatter.get("schema_version") == 5:
            preflight_task_done_v5(
                root,
                doc,
                task_id=args.task_id,
                expected_state_sequence=args.expected_state_sequence,
            )
        else:
            preflight_task_done_v4(root, doc, args)
        direct_record = persist_direct_evidence_bytes(
            root,
            plan_id=plan_id,
            task_id=args.task_id,
            kind=args.kind,
            summary=args.summary or f"Complete {args.task_id}.",
            raw_content=raw_content,
            source_type=source_type,
            source_ref=source_ref,
            idempotency_key=args.idempotency_key,
        )
        evidence_ref, evidence_sha256 = canonical_workflow_evidence(
            root,
            plan_id=plan_id,
            subject=f"task:{args.task_id}",
            producer_ref="runtime:workctl/task-done",
            direct_record=direct_record,
        )
        if doc.frontmatter.get("schema_version") == 5:
            sequence = verify_task_done_v5(
                root,
                doc,
                task_id=args.task_id,
                note=args.note,
                expected_state_sequence=args.expected_state_sequence,
                evidence_ref=evidence_ref,
                evidence_sha256=evidence_sha256,
                direct_record=direct_record,
            )
            payload: dict[str, Any] = {
                "status": "TASK_DONE",
                "plan_id": plan_id,
                "task_id": args.task_id,
                "state_sequence": sequence,
            }
        else:
            revision = verify_task_done_v4(
                root,
                doc,
                args,
                evidence_ref=evidence_ref,
                evidence_sha256=evidence_sha256,
            )
            payload = {
                "status": "TASK_DONE",
                "plan_id": plan_id,
                "task_id": args.task_id,
                "revision": revision,
            }
        payload.update(
            {
                "direct_evidence_ref": direct_record["evidence_ref"],
                "direct_evidence_sha256": direct_record["evidence_sha256"],
                "evidence_ref": evidence_ref,
                "evidence_sha256": evidence_sha256,
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_plan_adapt_intent(args: argparse.Namespace) -> None:
    """Record a high-level adaptation intent without requiring a strict manifest."""
    root = project_root()
    content = read_workflow_input_bytes(
        args,
        stdin_attr="intent_stdin",
        file_attr="intent_from_file",
        required=True,
    )
    assert content is not None
    summary = args.summary or "Record plan adaptation intent."
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        plan_id = str(doc.frontmatter["plan_id"])
        if doc.frontmatter.get("schema_version") != 5:
            require_expected_revision(doc.frontmatter, args.expected_revision)
            require_current_intake(
                root,
                doc.frontmatter,
                turn_receipt_sha256=args.turn_receipt_sha256,
                expected_intake_sha256=args.expected_intake_sha256,
                targets=["route"],
            )
        direct_record = persist_direct_evidence_bytes(
            root,
            plan_id=plan_id,
            task_id=None,
            kind="adaptation-intent",
            summary=summary,
            raw_content=content,
            source_type="stdin" if args.intent_stdin else "file",
            source_ref=args.intent_from_file,
            idempotency_key=args.idempotency_key,
        )
        if doc.frontmatter.get("schema_version") == 5:
            evidence_subject = f"adaptation:intent-{direct_record['id']}"
            evidence_ref, evidence_sha256 = canonical_workflow_evidence(
                root,
                plan_id=plan_id,
                subject=evidence_subject,
                producer_ref="runtime:workctl/plan-adapt",
                direct_record=direct_record,
            )
            v5_recover_pending_event(root, doc.frontmatter)
            state = load_v5_state(root, doc.frontmatter)
            v5_persist_state_transition(
                root,
                doc.frontmatter,
                state,
                event="plan.adapted",
                subject="route",
                payload={
                    "summary": summary,
                    "evidence_ref": evidence_ref,
                    "evidence_sha256": evidence_sha256,
                    "direct_evidence_ref": direct_record.get("evidence_ref"),
                    "direct_evidence_sha256": direct_record.get("evidence_sha256"),
                    "controller_decision": "recorded_intent_only",
                },
            )
            output = {
                "status": "PLAN_ADAPT_INTENT_RECORDED",
                "plan_id": plan_id,
                "state_sequence": state["state_sequence"],
                "evidence_ref": evidence_ref,
                "evidence_sha256": evidence_sha256,
                "direct_evidence_ref": direct_record["evidence_ref"],
                "direct_evidence_sha256": direct_record["evidence_sha256"],
            }
            print(json.dumps(output, indent=2, sort_keys=True))
            return
        next_revision = int(doc.frontmatter["revision"]) + 1
        evidence_ref, evidence_sha256 = canonical_workflow_evidence(
            root,
            plan_id=plan_id,
            subject=f"adaptation:{next_revision}",
            producer_ref="runtime:workctl/plan-adapt",
            direct_record=direct_record,
        )
        bump_revision(
            doc.frontmatter,
            kind="adaptation",
            rationale=summary,
            evidence_manifest=evidence_ref,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(
            json.dumps(
                {
                    "status": "PLAN_ADAPT_INTENT_RECORDED",
                    "plan_id": plan_id,
                    "revision": doc.frontmatter["revision"],
                    "evidence_ref": evidence_ref,
                    "evidence_sha256": evidence_sha256,
                    "direct_evidence_ref": direct_record["evidence_ref"],
                    "direct_evidence_sha256": direct_record["evidence_sha256"],
                },
                indent=2,
                sort_keys=True,
            )
        )


def tolerant_plan_history_summary(root: Path, path: Path) -> dict[str, Any]:
    """Read historical Plan metadata without enforcing the active schema."""
    if module_tolerant_plan_history_summary is None:
        raise WorkctlError("PLAN_HISTORY_MODULE_UNAVAILABLE")
    try:
        return dict(
            module_tolerant_plan_history_summary(
                path=path,
                relative_path=relative_project_path(root, path),
                file_sha256=sha256_file(path),
                body_sha256=sha256_bytes,
            )
        )
    except ModulePlanHistoryError as exc:
        raise WorkctlError(str(exc)) from exc


def cmd_plan_history(args: argparse.Namespace) -> None:
    """Read historical Plans without applying active schema validation."""
    root = project_root()
    base = plan_dir(root)
    summaries = (
        [tolerant_plan_history_summary(root, path) for path in sorted(base.glob("PLAN-*.md"))]
        if base.is_dir()
        else []
    )
    if args.history_action == "list":
        print(json.dumps({"plans": summaries}, indent=2, sort_keys=True))
        return
    target: dict[str, Any] | None = None
    if args.path:
        path = checked_project_path(root, args.path)
        target = tolerant_plan_history_summary(root, path)
    elif args.plan_id:
        if module_find_plan_history_target is None:
            raise WorkctlError("PLAN_HISTORY_MODULE_UNAVAILABLE")
        target_item = module_find_plan_history_target(summaries, str(args.plan_id))
        target = dict(target_item) if target_item is not None else None
    else:
        raise WorkctlError("PLAN_HISTORY_TARGET_REQUIRED")
    if target is None:
        raise WorkctlError("PLAN_HISTORY_NOT_FOUND")
    if target.get("parse_state") == "ok":
        path = checked_project_path(root, str(target["path"]))
        doc = load_plan(path)
        target["tasks"] = doc.frontmatter.get("tasks", [])
        target["confirmations"] = doc.frontmatter.get("confirmations", {})
        target["goal"] = doc.frontmatter.get("goal")
        target["success_conditions"] = doc.frontmatter.get("success_conditions")
    print(json.dumps(target, indent=2, sort_keys=True))


def risk_factors_for_action(action_kind: str) -> list[str]:
    """Return factual risk categories for one proposed action kind."""
    if module_risk_factors_for_action is None:
        raise WorkctlError("RISK_MODULE_UNAVAILABLE")
    return module_risk_factors_for_action(action_kind, HIGH_IMPACT_ACTION_KINDS)


def action_reversibility(action_kind: str) -> str:
    """Classify reversibility facts without making a confirmation decision."""
    if module_action_reversibility is None:
        raise WorkctlError("RISK_MODULE_UNAVAILABLE")
    return module_action_reversibility(action_kind)


def cmd_risk_inspect(args: argparse.Namespace) -> None:
    """Return read-only risk facts while leaving confirmation judgment to the model."""
    if module_risk_inspection_payload is None:
        raise WorkctlError("RISK_MODULE_UNAVAILABLE")
    content = read_workflow_input_bytes(
        args,
        stdin_attr="action_stdin",
        file_attr="action_from_file",
        required=False,
    )
    action_sha256: str | None = None
    action_size: int | None = None
    if content is not None:
        action_sha256 = sha256_bytes(content)
        action_size = len(content)
    output = module_risk_inspection_payload(
        action_kind=str(args.action_kind),
        target_ref=str(args.target_ref),
        high_impact_action_kinds=HIGH_IMPACT_ACTION_KINDS,
        action_sha256=action_sha256,
        action_size=action_size,
    )
    print(json.dumps(output, indent=2, sort_keys=True))


def worktree_ledger_path(root: Path, worktree_id: str) -> Path:
    """Return the non-authoritative worktree ledger path for one sub-execution."""
    if module_worktree_ledger_path is None:
        raise WorkctlError("WORKTREE_MODULE_UNAVAILABLE")
    try:
        path = module_worktree_ledger_path(
            runtime_dir(root),
            worktree_id,
            WORKTREE_LEDGER_ID_RE,
        )
    except ModuleWorktreeLedgerError as exc:
        raise WorkctlError(str(exc)) from exc
    reject_symlink_components(root, path)
    return path


def load_worktree_ledger(root: Path, worktree_id: str) -> dict[str, Any]:
    """Load one non-authoritative worktree ledger."""
    if module_load_worktree_ledger is None:
        raise WorkctlError("WORKTREE_MODULE_UNAVAILABLE")
    path = worktree_ledger_path(root, worktree_id)
    try:
        return module_load_worktree_ledger(path, worktree_id)
    except ModuleWorktreeLedgerError as exc:
        raise WorkctlError(str(exc)) from exc


def write_worktree_ledger(root: Path, worktree_id: str, payload: Mapping[str, Any]) -> None:
    """Persist one non-authoritative worktree ledger."""
    if module_encode_worktree_ledger is None:
        raise WorkctlError("WORKTREE_MODULE_UNAVAILABLE")
    write_atomic(worktree_ledger_path(root, worktree_id), module_encode_worktree_ledger(payload))


def worktree_parent_fork_base(root: Path, *, captured_at: str) -> dict[str, Any]:
    """Project the current active parent Plan state for a worktree fork."""
    doc = load_plan(active_plan_path(root))
    frontmatter = doc.frontmatter
    plan_id = frontmatter.get("plan_id")
    if not isinstance(plan_id, str):
        raise WorkctlError("INVALID_PLAN: plan_id must be a string")
    base: dict[str, Any] = {
        "authority": "PARENT_PLAN_BASE",
        "captured_at": captured_at,
        "plan_id": plan_id,
        "plan_path": relative_project_path(root, doc.path),
        "plan_sha256": sha256_file(doc.path),
        "contract_state": contract_state(frontmatter),
    }
    schema_version = frontmatter.get("schema_version")
    if isinstance(schema_version, int):
        base["schema_version"] = schema_version
    status = frontmatter.get("status")
    if isinstance(status, str):
        base["status"] = status
    revision = frontmatter.get("revision")
    if isinstance(revision, int):
        base["revision"] = revision
    contract_revision = frontmatter.get("contract_revision")
    if not isinstance(contract_revision, int):
        contract = frontmatter.get("contract")
        if isinstance(contract, dict) and isinstance(contract.get("revision"), int):
            contract_revision = contract["revision"]
    if isinstance(contract_revision, int):
        base["contract_revision"] = contract_revision
    current_task = frontmatter.get("current_task")
    if isinstance(current_task, str):
        base["current_task"] = current_task
    if schema_version == 5:
        state = load_v5_state(root, frontmatter)
        base["state_sequence"] = state["state_sequence"]
        base["event_sequence"] = state["event_sequence"]
    git_head = current_git_baseline(root)
    if git_head is not None:
        base["git_head"] = git_head
    return base


def worktree_parent_drift_reasons(
    fork_base: object,
    current_parent: Mapping[str, Any],
) -> list[str]:
    """Compare one worktree fork basis with the current active parent Plan."""
    if not isinstance(fork_base, dict):
        return ["fork_base_missing"]
    compare_fields = (
        "plan_id",
        "plan_sha256",
        "schema_version",
        "revision",
        "contract_revision",
        "state_sequence",
        "event_sequence",
        "git_head",
    )
    reason_names = {
        "plan_id": "parent_plan_id_changed",
        "plan_sha256": "parent_plan_sha_changed",
        "schema_version": "parent_schema_version_changed",
        "revision": "parent_plan_revision_changed",
        "contract_revision": "parent_contract_revision_changed",
        "state_sequence": "parent_state_sequence_changed",
        "event_sequence": "parent_event_sequence_changed",
        "git_head": "parent_git_head_changed",
    }
    reasons: list[str] = []
    for field in compare_fields:
        fork_value = fork_base.get(field)
        current_value = current_parent.get(field)
        if fork_value != current_value:
            reasons.append(reason_names[field])
    return reasons


def worktree_merge_suggested_actions(*, drift_detected: bool, closed: bool) -> list[str]:
    """Return model-facing next steps for non-authoritative worktree absorption."""
    if not closed:
        return [
            "Close the worktree ledger before parent Plan evidence absorption.",
            "Keep the ledger NON_AUTHORITY; do not treat it as a second Plan.",
        ]
    if drift_detected:
        return [
            "Review fork_base, current_parent, close_summary, and worktree events together.",
            (
                "Decide whether the parent Plan needs plan adapt, task done, "
                "or a confirmation gate before absorbing evidence."
            ),
            (
                "Reference only reviewed close_summary/evidence in the parent Plan; "
                "never promote the ledger as authority."
            ),
        ]
    return [
        "Review close_summary and cited evidence.",
        (
            "Record the parent Plan evidence or task completion explicitly with "
            "task done or evidence capture."
        ),
        "Keep the worktree ledger as NON_AUTHORITY runtime history.",
    ]


def worktree_event(args: argparse.Namespace, *, event_name: str | None = None) -> dict[str, Any]:
    """Build one bounded worktree ledger event."""
    if module_build_worktree_event is None:
        raise WorkctlError("WORKTREE_MODULE_UNAVAILABLE")
    try:
        return module_build_worktree_event(
            event=str(event_name if event_name is not None else args.event),
            summary=str(args.summary),
            recorded_at=utc_now(),
            evidence_ref=args.evidence_ref,
            evidence_sha256=args.evidence_sha256,
            valid_reference=valid_reference,
            sha256_pattern=SHA256_RE,
        )
    except ModuleWorktreeLedgerError as exc:
        raise WorkctlError(str(exc)) from exc


def cmd_worktree_begin(args: argparse.Namespace) -> None:
    """Begin a non-authoritative worktree execution ledger."""
    root = project_root()
    ledger_id = str(vars(args)["worktree_id"])
    with lock(root):
        if module_open_worktree_ledger is None:
            raise WorkctlError("WORKTREE_MODULE_UNAVAILABLE")
        path = worktree_ledger_path(root, ledger_id)
        if path.exists() or path.is_symlink():
            raise WorkctlError("WORKTREE_LEDGER_ALREADY_EXISTS")
        now = utc_now()
        fork_base = worktree_parent_fork_base(root, captured_at=now)
        payload = module_open_worktree_ledger(
            worktree_id=ledger_id,
            path=str(args.path),
            branch=str(args.branch),
            summary=str(args.summary),
            opened_at=now,
            fork_base=fork_base,
        )
        write_worktree_ledger(root, ledger_id, payload)
        print(
            json.dumps(
                {
                    "status": "WORKTREE_LEDGER_OPENED",
                    "authority": "NON_AUTHORITY",
                    "worktree_id": ledger_id,
                    "path": relative_project_path(root, path),
                    "fork_base": fork_base,
                },
                indent=2,
                sort_keys=True,
            )
        )


def cmd_worktree_record(args: argparse.Namespace) -> None:
    """Append one event to a non-authoritative worktree ledger."""
    root = project_root()
    ledger_id = str(vars(args)["worktree_id"])
    with lock(root):
        if module_append_worktree_event is None:
            raise WorkctlError("WORKTREE_MODULE_UNAVAILABLE")
        payload = load_worktree_ledger(root, ledger_id)
        try:
            event_count = module_append_worktree_event(payload, worktree_event(args))
        except ModuleWorktreeLedgerError as exc:
            raise WorkctlError(str(exc)) from exc
        payload["updated_at"] = utc_now()
        write_worktree_ledger(root, ledger_id, payload)
        print(
            json.dumps(
                {
                    "status": "WORKTREE_LEDGER_RECORDED",
                    "authority": "NON_AUTHORITY",
                    "worktree_id": ledger_id,
                    "event_count": event_count,
                },
                indent=2,
                sort_keys=True,
            )
        )


def cmd_worktree_close(args: argparse.Namespace) -> None:
    """Close a non-authoritative worktree ledger and emit its handoff summary."""
    root = project_root()
    ledger_id = str(vars(args)["worktree_id"])
    with lock(root):
        if module_close_worktree_ledger is None:
            raise WorkctlError("WORKTREE_MODULE_UNAVAILABLE")
        payload = load_worktree_ledger(root, ledger_id)
        now = utc_now()
        try:
            close_summary = module_close_worktree_ledger(
                payload,
                worktree_event(args, event_name="close"),
                summary=str(args.summary),
                closed_at=now,
            )
        except ModuleWorktreeLedgerError as exc:
            raise WorkctlError(str(exc)) from exc
        write_worktree_ledger(root, ledger_id, payload)
        print(
            json.dumps(
                {
                    "status": "WORKTREE_LEDGER_CLOSED",
                    "authority": "NON_AUTHORITY",
                    "worktree_id": ledger_id,
                    "close_summary": close_summary,
                },
                indent=2,
                sort_keys=True,
            )
        )


def cmd_worktree_merge_inspect(args: argparse.Namespace) -> None:
    """Inspect whether one closed worktree summary can be reviewed without drift."""
    root = project_root()
    ledger_id = str(vars(args)["worktree_id"])
    payload = load_worktree_ledger(root, ledger_id)
    current_parent = worktree_parent_fork_base(root, captured_at=utc_now())
    drift_reasons = worktree_parent_drift_reasons(payload.get("fork_base"), current_parent)
    closed = payload.get("status") == "closed"
    if drift_reasons:
        merge_state = "MERGE_REVIEW_REQUIRED"
    elif closed:
        merge_state = "READY_FOR_PARENT_REVIEW"
    else:
        merge_state = "WORKTREE_NOT_CLOSED"
    output = {
        "status": "WORKTREE_MERGE_INSPECTED",
        "authority": "NON_AUTHORITY",
        "controller_decision": "inspect_only",
        "decision_owner": "model",
        "parent_mutated": False,
        "worktree_id": ledger_id,
        "worktree_status": payload.get("status"),
        "merge_state": merge_state,
        "drift_detected": bool(drift_reasons),
        "drift_reasons": drift_reasons,
        "fork_base": payload.get("fork_base"),
        "current_parent": current_parent,
        "close_summary": payload.get("close_summary"),
        "suggested_parent_actions": worktree_merge_suggested_actions(
            drift_detected=bool(drift_reasons),
            closed=closed,
        ),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


def cmd_plan_init(args: argparse.Namespace) -> None:
    del args
    raise WorkctlError("PLAN_ADMISSION_REQUIRED: use plan admit apply --manifest")


def intake_blockers(frontmatter: Mapping[str, Any]) -> list[str]:
    """Return repair or refresh work blocking current intake use."""
    blockers: list[str] = []
    state = intake_state(frontmatter)
    if state == "MISSING":
        blockers.append("intake record missing")
    elif state == "STALE_BASIS":
        blockers.append("latest intake decision basis is stale")
    elif state == "INVALID":
        blockers.append("intake contract is invalid")
    for unknown_id in legacy_unknown_ids(frontmatter):
        blockers.append(f"legacy unknown contract: {unknown_id}")
    return blockers


def current_request_matches(
    root: Path,
    frontmatter: Mapping[str, Any],
    expected_intake_sha256: str,
) -> bool:
    """Compare one expected intake hash with the trusted current runtime turn."""
    records = intake_records(frontmatter)
    if not records or records[-1].get("record_sha256") != expected_intake_sha256:
        return False
    for path in current_turn_receipt_paths(root):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("receipt_sha256"), str):
            continue
        if records[-1].get("request_ref") != raw.get("request_ref"):
            continue
        try:
            session_receipt = session_receipt_for_turn(
                root,
                str(raw["receipt_sha256"]),
                require_current_controller=False,
            )
            turn = load_current_turn_receipt(
                root,
                supplied_sha256=str(raw["receipt_sha256"]),
                session_receipt=cast(Mapping[str, object], session_receipt),
            )
        except WorkctlError:
            continue
        if records[-1].get("request_ref") == turn.get("request_ref") and records[-1].get(
            "decision_basis_sha256"
        ) == decision_basis_sha256(frontmatter):
            return True
    return False


def require_confirmation_turn_ref(
    root: Path,
    *,
    ref: str,
    turn_receipt_sha256: str | None,
) -> dict[str, object]:
    """Bind a high-impact decision to the trusted current user turn."""
    if not isinstance(turn_receipt_sha256, str):
        raise WorkctlError("TURN_RECEIPT_REQUIRED")
    session_receipt = session_receipt_for_turn(
        root,
        turn_receipt_sha256,
        require_current_controller=True,
    )
    turn = load_current_turn_receipt(
        root,
        supplied_sha256=turn_receipt_sha256,
        session_receipt=cast(Mapping[str, object], session_receipt),
    )
    if ref != turn.get("request_ref"):
        raise WorkctlError("CONFIRMATION_REF_CURRENT_TURN_REQUIRED")
    return turn


def action_authorization_directory(root: Path) -> Path:
    """Return the private runtime directory for one-shot action authority."""
    path = governance_root(root) / "runtime" / "action-authorizations"
    reject_symlink_components(root, path)
    return path


def action_authority_lease_directory(root: Path) -> Path:
    """Return the private runtime directory for bounded route action leases."""
    path = governance_root(root) / "runtime" / "action-authority-leases"
    reject_symlink_components(root, path)
    return path


def action_authorization_path(root: Path, authorization_id: str) -> Path:
    """Resolve one action authorization after validating its content-derived ID."""
    if ACTION_AUTHORIZATION_ID_RE.fullmatch(authorization_id) is None:
        raise WorkctlError("ACTION_AUTHORIZATION_ID_INVALID")
    path = action_authorization_directory(root) / f"{authorization_id}.json"
    reject_symlink_components(root, path)
    return path


def action_authority_lease_path(root: Path, lease_id: str) -> Path:
    """Resolve one route authority lease after validating its content-derived ID."""
    if ACTION_AUTHORITY_LEASE_ID_RE.fullmatch(lease_id) is None:
        raise WorkctlError("ACTION_LEASE_ID_INVALID")
    path = action_authority_lease_directory(root) / f"{lease_id}.json"
    reject_symlink_components(root, path)
    return path


def action_authorization_digest(record: Mapping[str, object]) -> str:
    """Hash an action authorization without its self-authenticating digest."""
    projection = {key: value for key, value in record.items() if key != "record_sha256"}
    return sha256_bytes(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def action_authority_lease_digest(record: Mapping[str, object]) -> str:
    """Hash a route authority lease without its self-authenticating digest."""
    projection = {key: value for key, value in record.items() if key != "record_sha256"}
    return sha256_bytes(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def parse_authorization_time(value: object) -> datetime:
    """Parse one timezone-aware authorization timestamp."""
    if not isinstance(value, str):
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID") from exc
    if parsed.tzinfo is None:
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    return parsed.astimezone(UTC)


def load_action_authorization(root: Path, authorization_id: str) -> dict[str, object]:
    """Load and fully validate one persisted action authorization."""
    path = action_authorization_path(root, authorization_id)
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("ACTION_AUTHORIZATION_NOT_FOUND")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID") from exc
    required = {
        "schema_version",
        "kind",
        "authorization_id",
        "plan_id",
        "contract_revision",
        "contract_sha256",
        "confirmation_id",
        "action_kind",
        "target_ref",
        "action_sha256",
        "request_ref",
        "turn_receipt_sha256",
        "session_id",
        "session_start_receipt_sha256",
        "issued_at",
        "expires_at",
        "state",
        "consumed_at",
        "consumer_ref",
        "record_sha256",
    }
    if not isinstance(payload, dict):
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    record = cast(dict[str, object], payload)
    schema_version = record.get("schema_version")
    lease_fields = {
        "authority_source",
        "lease_id",
        "lease_basis_sha256",
        "lease_authorization_index",
        "idempotency_key",
    }
    required_fields = required if schema_version == 1 else required | lease_fields
    if set(record) != required_fields:
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    if (
        schema_version not in {1, 2}
        or record.get("kind") != "work-governance-action-authorization"
        or record.get("authorization_id") != authorization_id
        or not isinstance(record.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(record["plan_id"])) is None
        or type(record.get("contract_revision")) is not int
        or int(cast(int, record["contract_revision"])) < 1
        or not isinstance(record.get("contract_sha256"), str)
        or SHA256_RE.fullmatch(str(record["contract_sha256"])) is None
        or not isinstance(record.get("confirmation_id"), str)
        or not str(record["confirmation_id"]).startswith("C-")
        or record.get("action_kind") not in HIGH_IMPACT_ACTION_KINDS
        or not valid_reference(record.get("target_ref"))
        or not isinstance(record.get("action_sha256"), str)
        or SHA256_RE.fullmatch(str(record["action_sha256"])) is None
        or not valid_reference(record.get("request_ref"))
        or not isinstance(record.get("turn_receipt_sha256"), str)
        or SHA256_RE.fullmatch(str(record["turn_receipt_sha256"])) is None
        or not isinstance(record.get("session_id"), str)
        or SESSION_ID_RE.fullmatch(str(record["session_id"])) is None
        or not isinstance(record.get("session_start_receipt_sha256"), str)
        or SHA256_RE.fullmatch(str(record["session_start_receipt_sha256"])) is None
        or record.get("state") not in {"authorized", "consumed"}
        or not isinstance(record.get("record_sha256"), str)
        or SHA256_RE.fullmatch(str(record["record_sha256"])) is None
        or action_authorization_digest(record) != record.get("record_sha256")
    ):
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    if schema_version == 2 and (
        record.get("authority_source") != "lease"
        or not isinstance(record.get("lease_id"), str)
        or ACTION_AUTHORITY_LEASE_ID_RE.fullmatch(str(record["lease_id"])) is None
        or not isinstance(record.get("lease_basis_sha256"), str)
        or SHA256_RE.fullmatch(str(record["lease_basis_sha256"])) is None
        or type(record.get("lease_authorization_index")) is not int
        or int(cast(int, record["lease_authorization_index"])) < 1
        or not isinstance(record.get("idempotency_key"), str)
        or EVIDENCE_CAPTURE_IDEMPOTENCY_RE.fullmatch(str(record["idempotency_key"])) is None
    ):
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    issued_at = parse_authorization_time(record.get("issued_at"))
    expires_at = parse_authorization_time(record.get("expires_at"))
    if expires_at <= issued_at or expires_at - issued_at > timedelta(
        seconds=MAX_ACTION_AUTHORIZATION_TTL_SECONDS
    ):
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    consumed_at = record.get("consumed_at")
    consumer_ref = record.get("consumer_ref")
    if record["state"] == "authorized":
        if consumed_at is not None or consumer_ref is not None:
            raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    elif parse_authorization_time(consumed_at) < issued_at or not valid_reference(consumer_ref):
        raise WorkctlError("ACTION_AUTHORIZATION_INVALID")
    return record


def action_authorization_binding(
    *,
    turn_receipt_sha256: str,
    confirmation_id: str,
    action_kind: str,
    target_ref: str,
    action_sha256: str,
) -> dict[str, str]:
    """Return the immutable fields that define one exact high-impact action."""
    return {
        "turn_receipt_sha256": turn_receipt_sha256,
        "confirmation_id": confirmation_id,
        "action_kind": action_kind,
        "target_ref": target_ref,
        "action_sha256": action_sha256,
    }


def action_authorization_id(binding: Mapping[str, str]) -> str:
    """Derive an idempotent ID so one user turn cannot mint replay aliases."""
    digest = sha256_bytes(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"AUTH-{digest[:32]}"


def action_lease_authorization_binding(
    *,
    lease_id: str,
    action_kind: str,
    target_ref: str,
    action_sha256: str,
    idempotency_key: str,
) -> dict[str, str]:
    """Return the immutable fields for one lease-derived action capability."""
    return {
        "lease_id": lease_id,
        "action_kind": action_kind,
        "target_ref": target_ref,
        "action_sha256": action_sha256,
        "idempotency_key": idempotency_key,
    }


def action_lease_authorization_id(binding: Mapping[str, str]) -> str:
    """Derive an idempotent ID so a lease cannot mint replay aliases."""
    digest = sha256_bytes(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"AUTH-{digest[:32]}"


def action_lease_basis_ref(basis_sha256: str) -> str:
    """Return the typed confirmation basis reference for one lease scope digest."""
    if SHA256_RE.fullmatch(basis_sha256) is None:
        raise WorkctlError("ACTION_LEASE_BASIS_SHA256_INVALID")
    return f"runtime:action-lease/{basis_sha256}"


def valid_target_prefix(value: object) -> bool:
    """Return whether a route lease target prefix is typed and path-bounded."""
    if not isinstance(value, str) or REFERENCE_RE.fullmatch(value) is None:
        return False
    if "*" in value or not value.endswith("/"):
        return False
    _scheme, rest = value.split(":", 1)
    return bool(rest.strip("/"))


def normalize_unique_strings(values: Sequence[str], *, field: str) -> list[str]:
    """Return sorted unique strings or raise a field-specific validation error."""
    if any(not isinstance(value, str) for value in values):
        raise WorkctlError(f"{field}_INVALID")
    result = sorted(set(values))
    if len(result) != len(values):
        raise WorkctlError(f"{field}_DUPLICATE")
    return result


def action_lease_scope_from_args(args: argparse.Namespace) -> dict[str, object]:
    """Build the canonical, confirmed scope payload for a route authority lease."""
    target_refs = normalize_unique_strings(args.target_ref or [], field="ACTION_LEASE_TARGET_REF")
    target_prefixes = normalize_unique_strings(
        args.target_prefix or [],
        field="ACTION_LEASE_TARGET_PREFIX",
    )
    allowed_digests = normalize_unique_strings(
        args.allowed_action_sha256 or [],
        field="ACTION_LEASE_ALLOWED_ACTION_SHA256",
    )
    blocks = normalize_unique_strings(args.blocks or ["route"], field="ACTION_LEASE_BLOCKS")
    if args.action_kind not in HIGH_IMPACT_ACTION_KINDS:
        raise WorkctlError("ACTION_KIND_INVALID")
    if not target_refs and not target_prefixes:
        raise WorkctlError("ACTION_LEASE_TARGET_SCOPE_REQUIRED")
    for target_ref in target_refs:
        if not valid_reference(target_ref):
            raise WorkctlError("ACTION_LEASE_TARGET_REF_INVALID")
    for prefix in target_prefixes:
        if not valid_target_prefix(prefix):
            raise WorkctlError("ACTION_LEASE_TARGET_PREFIX_INVALID")
    for digest in allowed_digests:
        if SHA256_RE.fullmatch(digest) is None:
            raise WorkctlError("ACTION_LEASE_ALLOWED_ACTION_SHA256_INVALID")
    if args.action_digest_policy not in ACTION_DIGEST_POLICIES:
        raise WorkctlError("ACTION_LEASE_DIGEST_POLICY_INVALID")
    if args.action_digest_policy == "exact-list" and not allowed_digests:
        raise WorkctlError("ACTION_LEASE_ALLOWED_ACTION_SHA256_REQUIRED")
    if not 1 <= args.lease_ttl_seconds <= MAX_ACTION_LEASE_TTL_SECONDS:
        raise WorkctlError("ACTION_LEASE_TTL_INVALID")
    if not 1 <= args.authorization_ttl_seconds <= MAX_ACTION_AUTHORIZATION_TTL_SECONDS:
        raise WorkctlError("ACTION_AUTHORIZATION_TTL_INVALID")
    if not 1 <= args.max_authorizations <= MAX_ACTION_LEASE_AUTHORIZATIONS:
        raise WorkctlError("ACTION_LEASE_MAX_AUTHORIZATIONS_INVALID")
    for block in blocks:
        if not valid_target_ref(block):
            raise WorkctlError("ACTION_LEASE_BLOCK_TARGET_INVALID")
    pilot_evidence_ref = args.pilot_evidence_ref
    if pilot_evidence_ref is not None and not valid_reference(pilot_evidence_ref):
        raise WorkctlError("ACTION_LEASE_PILOT_EVIDENCE_REF_INVALID")
    return {
        "schema_version": 1,
        "kind": "work-governance-action-lease-basis",
        "action_kind": args.action_kind,
        "target_refs": target_refs,
        "target_prefixes": target_prefixes,
        "action_digest_policy": args.action_digest_policy,
        "allowed_action_sha256s": allowed_digests,
        "blocks": blocks,
        "lease_ttl_seconds": args.lease_ttl_seconds,
        "authorization_ttl_seconds": args.authorization_ttl_seconds,
        "max_authorizations": args.max_authorizations,
        "freeze_on_review_blocker": bool(args.freeze_on_review_blocker),
        "pilot_evidence_ref": pilot_evidence_ref,
    }


def action_lease_basis_sha256(scope: Mapping[str, object]) -> str:
    """Hash a canonical route authority lease scope."""
    return sha256_bytes(
        json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )


def target_ref_allowed_by_lease(lease: Mapping[str, object], target_ref: str) -> bool:
    """Return whether a concrete action target falls within a confirmed lease scope."""
    target_refs = lease.get("target_refs", [])
    if isinstance(target_refs, list) and target_ref in target_refs:
        return True
    target_prefixes = lease.get("target_prefixes", [])
    return isinstance(target_prefixes, list) and any(
        isinstance(prefix, str) and target_ref.startswith(prefix) for prefix in target_prefixes
    )


def load_action_authority_lease(root: Path, lease_id: str) -> dict[str, object]:
    """Load and fully validate one persisted route authority lease."""
    path = action_authority_lease_path(root, lease_id)
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("ACTION_LEASE_NOT_FOUND")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkctlError("ACTION_LEASE_INVALID") from exc
    if not isinstance(payload, dict):
        raise WorkctlError("ACTION_LEASE_INVALID")
    lease = cast(dict[str, object], payload)
    required = {
        "schema_version",
        "kind",
        "lease_id",
        "plan_id",
        "contract_revision",
        "contract_sha256",
        "confirmation_id",
        "action_kind",
        "target_refs",
        "target_prefixes",
        "action_digest_policy",
        "allowed_action_sha256s",
        "blocks",
        "basis_ref",
        "basis_sha256",
        "request_ref",
        "turn_receipt_sha256",
        "session_id",
        "session_start_receipt_sha256",
        "issued_at",
        "expires_at",
        "authorization_ttl_seconds",
        "max_authorizations",
        "freeze_on_review_blocker",
        "pilot_evidence_ref",
        "state",
        "issued_authorizations",
        "frozen_at",
        "freeze_reason",
        "revoked_at",
        "revoke_ref",
        "record_sha256",
    }
    target_refs = lease.get("target_refs")
    target_prefixes = lease.get("target_prefixes")
    allowed_digests = lease.get("allowed_action_sha256s")
    blocks = lease.get("blocks")
    issued = lease.get("issued_authorizations")
    invalid = (
        set(lease) != required
        or lease.get("schema_version") != 1
        or lease.get("kind") != "work-governance-action-authority-lease"
        or lease.get("lease_id") != lease_id
        or not isinstance(lease.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(lease["plan_id"])) is None
        or type(lease.get("contract_revision")) is not int
        or int(cast(int, lease["contract_revision"])) < 1
        or not isinstance(lease.get("contract_sha256"), str)
        or SHA256_RE.fullmatch(str(lease["contract_sha256"])) is None
        or not isinstance(lease.get("confirmation_id"), str)
        or not str(lease["confirmation_id"]).startswith("C-")
        or lease.get("action_kind") not in HIGH_IMPACT_ACTION_KINDS
        or not isinstance(target_refs, list)
        or (not target_refs and not target_prefixes)
        or not isinstance(target_prefixes, list)
        or not isinstance(allowed_digests, list)
        or lease.get("action_digest_policy") not in ACTION_DIGEST_POLICIES
        or (lease.get("action_digest_policy") == "exact-list" and not allowed_digests)
        or not isinstance(blocks, list)
        or not isinstance(lease.get("basis_ref"), str)
        or not valid_reference(lease.get("basis_ref"))
        or not isinstance(lease.get("basis_sha256"), str)
        or SHA256_RE.fullmatch(str(lease["basis_sha256"])) is None
        or lease.get("basis_ref") != action_lease_basis_ref(str(lease["basis_sha256"]))
        or not valid_reference(lease.get("request_ref"))
        or not isinstance(lease.get("turn_receipt_sha256"), str)
        or SHA256_RE.fullmatch(str(lease["turn_receipt_sha256"])) is None
        or not isinstance(lease.get("session_id"), str)
        or SESSION_ID_RE.fullmatch(str(lease["session_id"])) is None
        or not isinstance(lease.get("session_start_receipt_sha256"), str)
        or SHA256_RE.fullmatch(str(lease["session_start_receipt_sha256"])) is None
        or type(lease.get("authorization_ttl_seconds")) is not int
        or not (
            1
            <= int(cast(int, lease["authorization_ttl_seconds"]))
            <= MAX_ACTION_AUTHORIZATION_TTL_SECONDS
        )
        or type(lease.get("max_authorizations")) is not int
        or not (1 <= int(cast(int, lease["max_authorizations"])) <= MAX_ACTION_LEASE_AUTHORIZATIONS)
        or type(lease.get("freeze_on_review_blocker")) is not bool
        or (
            lease.get("pilot_evidence_ref") is not None
            and not valid_reference(lease.get("pilot_evidence_ref"))
        )
        or lease.get("state") not in {"active", "frozen", "revoked"}
        or not isinstance(issued, list)
        or len(issued) > int(cast(int, lease["max_authorizations"]))
        or not isinstance(lease.get("record_sha256"), str)
        or SHA256_RE.fullmatch(str(lease["record_sha256"])) is None
        or action_authority_lease_digest(lease) != lease.get("record_sha256")
    )
    if invalid:
        raise WorkctlError("ACTION_LEASE_INVALID")
    target_ref_values = cast(list[object], target_refs)
    target_prefix_values = cast(list[object], target_prefixes)
    allowed_digest_values = cast(list[object], allowed_digests)
    block_values = cast(list[object], blocks)
    issued_values = cast(list[object], issued)
    if any(not isinstance(item, str) or not valid_reference(item) for item in target_ref_values):
        raise WorkctlError("ACTION_LEASE_INVALID")
    if any(
        not isinstance(item, str) or not valid_target_prefix(item) for item in target_prefix_values
    ):
        raise WorkctlError("ACTION_LEASE_INVALID")
    if any(
        not isinstance(item, str) or SHA256_RE.fullmatch(item) is None
        for item in allowed_digest_values
    ):
        raise WorkctlError("ACTION_LEASE_INVALID")
    if any(not isinstance(item, str) or not valid_target_ref(item) for item in block_values):
        raise WorkctlError("ACTION_LEASE_INVALID")
    seen_authorizations: set[str] = set()
    for index, item in enumerate(issued_values, start=1):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("authorization_id"), str)
            or ACTION_AUTHORIZATION_ID_RE.fullmatch(str(item["authorization_id"])) is None
            or item["authorization_id"] in seen_authorizations
            or not isinstance(item.get("target_ref"), str)
            or not valid_reference(item.get("target_ref"))
            or not isinstance(item.get("action_sha256"), str)
            or SHA256_RE.fullmatch(str(item["action_sha256"])) is None
            or not isinstance(item.get("idempotency_key"), str)
            or EVIDENCE_CAPTURE_IDEMPOTENCY_RE.fullmatch(str(item["idempotency_key"])) is None
            or type(item.get("index")) is not int
            or item.get("index") != index
            or not isinstance(item.get("authorized_at"), str)
        ):
            raise WorkctlError("ACTION_LEASE_INVALID")
        parse_authorization_time(item["authorized_at"])
        seen_authorizations.add(str(item["authorization_id"]))
    issued_at = parse_authorization_time(lease.get("issued_at"))
    expires_at = parse_authorization_time(lease.get("expires_at"))
    if expires_at <= issued_at or expires_at - issued_at > timedelta(
        seconds=MAX_ACTION_LEASE_TTL_SECONDS
    ):
        raise WorkctlError("ACTION_LEASE_INVALID")
    if lease["state"] == "active":
        if lease.get("frozen_at") is not None or lease.get("freeze_reason") is not None:
            raise WorkctlError("ACTION_LEASE_INVALID")
        if lease.get("revoked_at") is not None or lease.get("revoke_ref") is not None:
            raise WorkctlError("ACTION_LEASE_INVALID")
    elif lease["state"] == "frozen":
        if not isinstance(lease.get("freeze_reason"), str) or not lease["freeze_reason"]:
            raise WorkctlError("ACTION_LEASE_INVALID")
        parse_authorization_time(lease.get("frozen_at"))
        if lease.get("revoked_at") is not None or lease.get("revoke_ref") is not None:
            raise WorkctlError("ACTION_LEASE_INVALID")
    elif (
        parse_authorization_time(lease.get("revoked_at")) < issued_at
        or not valid_reference(lease.get("revoke_ref"))
    ):
        raise WorkctlError("ACTION_LEASE_INVALID")
    return lease


def action_authority_lease_id(binding: Mapping[str, object]) -> str:
    """Derive an idempotent lease ID from the confirmed turn and scope."""
    digest = sha256_bytes(
        json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )
    return f"LEASE-{digest[:32]}"


def write_action_authority_lease(root: Path, lease: dict[str, object]) -> None:
    """Persist one validated lease record with a fresh self digest."""
    lease["record_sha256"] = action_authority_lease_digest(lease)
    write_atomic(
        action_authority_lease_path(root, str(lease["lease_id"])),
        json.dumps(lease, indent=2, sort_keys=True) + "\n",
    )


def freeze_action_authority_lease(
    root: Path,
    lease: dict[str, object],
    reason: str,
) -> None:
    """Fail closed by freezing a lease that no longer matches its route guard."""
    if lease.get("state") == "active":
        lease["state"] = "frozen"
        lease["frozen_at"] = utc_now()
        lease["freeze_reason"] = reason
        write_action_authority_lease(root, lease)


def validate_action_binding(args: argparse.Namespace) -> None:
    """Validate caller-supplied action metadata without reading action payload bytes."""
    if args.action_kind not in HIGH_IMPACT_ACTION_KINDS:
        raise WorkctlError("ACTION_KIND_INVALID")
    if not valid_reference(args.target_ref):
        raise WorkctlError("ACTION_TARGET_REF_INVALID")
    if SHA256_RE.fullmatch(args.action_sha256) is None:
        raise WorkctlError("ACTION_SHA256_INVALID")


def require_action_confirmation(
    root: Path,
    *,
    confirmation_id: str,
    action_kind: str,
    target_ref: str,
    action_sha256: str,
    turn: Mapping[str, object],
) -> tuple[str, int, str]:
    """Require one same-turn Plan gate bound to the exact external action."""
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    require_plan_contract_ready(doc.frontmatter)
    decision = confirmations(doc.frontmatter).get(confirmation_id)
    if not isinstance(decision, dict) or decision.get("status") != "accepted":
        raise WorkctlError("ACTION_CONFIRMATION_NOT_ACCEPTED")
    intervention = decision.get("intervention")
    expected_intervention = (
        "deviation_recovery" if action_kind == "substantive_rollback" else "external_authority"
    )
    if (
        decision.get("ref") != turn.get("request_ref")
        or decision.get("evidence_sha256") != action_sha256
        or not isinstance(intervention, dict)
        or intervention.get("kind") != expected_intervention
        or intervention.get("action_kind") != action_kind
        or intervention.get("basis_ref") != target_ref
        or intervention.get("basis_sha256") != action_sha256
    ):
        raise WorkctlError("ACTION_CONFIRMATION_BINDING_MISMATCH")
    revision = doc.frontmatter.get("contract_revision", doc.frontmatter.get("revision"))
    plan_id = doc.frontmatter.get("plan_id")
    if not isinstance(plan_id, str) or type(revision) is not int:
        raise WorkctlError("ACTION_CONFIRMATION_BINDING_MISMATCH")
    return plan_id, revision, sha256_file(doc.path)


def require_action_lease_confirmation(
    root: Path,
    *,
    confirmation_id: str,
    action_kind: str,
    basis_sha256: str,
    turn: Mapping[str, object],
) -> tuple[str, int, str]:
    """Require one same-turn Plan gate bound to a route authority lease scope."""
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    require_plan_contract_ready(doc.frontmatter)
    decision = confirmations(doc.frontmatter).get(confirmation_id)
    basis_ref = action_lease_basis_ref(basis_sha256)
    if not isinstance(decision, dict) or decision.get("status") != "accepted":
        raise WorkctlError("ACTION_LEASE_CONFIRMATION_NOT_ACCEPTED")
    intervention = decision.get("intervention")
    if (
        decision.get("ref") != turn.get("request_ref")
        or decision.get("evidence_sha256") != basis_sha256
        or not isinstance(intervention, dict)
        or intervention.get("kind") != "external_authority"
        or intervention.get("action_kind") != action_kind
        or intervention.get("basis_ref") != basis_ref
        or intervention.get("basis_sha256") != basis_sha256
    ):
        raise WorkctlError("ACTION_LEASE_CONFIRMATION_BINDING_MISMATCH")
    revision = doc.frontmatter.get("contract_revision", doc.frontmatter.get("revision"))
    plan_id = doc.frontmatter.get("plan_id")
    if not isinstance(plan_id, str) or type(revision) is not int:
        raise WorkctlError("ACTION_LEASE_CONFIRMATION_BINDING_MISMATCH")
    return plan_id, revision, sha256_file(doc.path)


def cmd_action_lease_prepare(args: argparse.Namespace) -> None:
    """Print the exact route authority lease basis to confirm through Plan gates."""
    scope = action_lease_scope_from_args(args)
    basis_sha256 = action_lease_basis_sha256(scope)
    basis_ref = action_lease_basis_ref(basis_sha256)
    payload = {
        "basis_ref": basis_ref,
        "basis_sha256": basis_sha256,
        "scope": scope,
        "confirmation": {
            "intervention_kind": "external_authority",
            "action_kind": args.action_kind,
            "basis_ref": basis_ref,
            "basis_sha256": basis_sha256,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_action_lease_issue(args: argparse.Namespace) -> None:
    """Create one bounded route-level authority lease after same-turn confirmation."""
    root = project_root()
    scope = action_lease_scope_from_args(args)
    basis_sha256 = action_lease_basis_sha256(scope)
    if args.basis_sha256 != basis_sha256:
        raise WorkctlError("ACTION_LEASE_BASIS_SHA256_MISMATCH")
    with lock(root):
        turn = require_confirmation_turn_ref(
            root,
            ref=args.ref,
            turn_receipt_sha256=args.turn_receipt_sha256,
        )
        plan_id, contract_revision, contract_sha256 = require_action_lease_confirmation(
            root,
            confirmation_id=args.confirmation_id,
            action_kind=args.action_kind,
            basis_sha256=basis_sha256,
            turn=turn,
        )
        issued_at = parse_authorization_time(turn.get("issued_at"))
        expires_at = issued_at + timedelta(seconds=args.lease_ttl_seconds)
        if datetime.now(UTC) >= expires_at:
            raise WorkctlError("ACTION_LEASE_EXPIRED")
        session_id = turn.get("session_id")
        session_start_digest = turn.get("session_start_receipt_sha256")
        if not isinstance(session_id, str) or not isinstance(session_start_digest, str):
            raise WorkctlError("TURN_RECEIPT_INVALID")
        binding = {
            "turn_receipt_sha256": args.turn_receipt_sha256,
            "confirmation_id": args.confirmation_id,
            "basis_sha256": basis_sha256,
        }
        lease_id = action_authority_lease_id(binding)
        path = action_authority_lease_path(root, lease_id)
        if path.exists() or path.is_symlink():
            existing = load_action_authority_lease(root, lease_id)
            if (
                existing.get("plan_id") != plan_id
                or existing.get("contract_revision") != contract_revision
                or existing.get("contract_sha256") != contract_sha256
            ):
                raise WorkctlError("ACTION_LEASE_CONTRACT_DRIFT")
            print(json.dumps(existing, indent=2, sort_keys=True))
            return
        lease: dict[str, object] = {
            "schema_version": 1,
            "kind": "work-governance-action-authority-lease",
            "lease_id": lease_id,
            "plan_id": plan_id,
            "contract_revision": contract_revision,
            "contract_sha256": contract_sha256,
            "confirmation_id": args.confirmation_id,
            "action_kind": args.action_kind,
            "target_refs": scope["target_refs"],
            "target_prefixes": scope["target_prefixes"],
            "action_digest_policy": scope["action_digest_policy"],
            "allowed_action_sha256s": scope["allowed_action_sha256s"],
            "blocks": scope["blocks"],
            "basis_ref": action_lease_basis_ref(basis_sha256),
            "basis_sha256": basis_sha256,
            "request_ref": args.ref,
            "turn_receipt_sha256": args.turn_receipt_sha256,
            "session_id": session_id,
            "session_start_receipt_sha256": session_start_digest,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "authorization_ttl_seconds": scope["authorization_ttl_seconds"],
            "max_authorizations": scope["max_authorizations"],
            "freeze_on_review_blocker": scope["freeze_on_review_blocker"],
            "pilot_evidence_ref": scope["pilot_evidence_ref"],
            "state": "active",
            "issued_authorizations": [],
            "frozen_at": None,
            "freeze_reason": None,
            "revoked_at": None,
            "revoke_ref": None,
        }
        write_action_authority_lease(root, lease)
        print(json.dumps(lease, indent=2, sort_keys=True))


def require_lease_route_still_clear(
    root: Path,
    lease: dict[str, object],
    doc: PlanDocument,
) -> None:
    """Freeze a lease when route-level blockers appear after it was issued."""
    if (
        lease.get("plan_id") != doc.frontmatter.get("plan_id")
        or lease.get("contract_revision")
        != doc.frontmatter.get("contract_revision", doc.frontmatter.get("revision"))
        or lease.get("contract_sha256") != sha256_file(doc.path)
    ):
        freeze_action_authority_lease(root, lease, "contract-drift")
        raise WorkctlError("ACTION_LEASE_CONTRACT_DRIFT")
    if lease.get("freeze_on_review_blocker") is not True:
        return
    try:
        require_no_blocking_artifacts(doc.frontmatter)
        blocks = lease.get("blocks", [])
        for target in blocks if isinstance(blocks, list) else []:
            require_independent_target(root, doc.frontmatter, str(target))
    except WorkctlError as exc:
        freeze_action_authority_lease(root, lease, str(exc).split(":", 1)[0])
        raise


def cmd_action_lease_authorize(args: argparse.Namespace) -> None:
    """Mint one single-use action capability from an active route authority lease."""
    root = project_root()
    validate_action_binding(args)
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        lease = load_action_authority_lease(root, args.lease_id)
        if lease.get("state") != "active":
            raise WorkctlError("ACTION_LEASE_NOT_ACTIVE")
        if datetime.now(UTC) >= parse_authorization_time(lease.get("expires_at")):
            freeze_action_authority_lease(root, lease, "expired")
            raise WorkctlError("ACTION_LEASE_EXPIRED")
        if lease.get("action_kind") != args.action_kind:
            raise WorkctlError("ACTION_LEASE_ACTION_KIND_MISMATCH")
        if not target_ref_allowed_by_lease(lease, args.target_ref):
            raise WorkctlError("ACTION_LEASE_TARGET_MISMATCH")
        allowed_digests = lease.get("allowed_action_sha256s", [])
        if lease.get("action_digest_policy") == "exact-list" and (
            not isinstance(allowed_digests, list) or args.action_sha256 not in allowed_digests
        ):
            raise WorkctlError("ACTION_LEASE_ACTION_SHA256_NOT_ALLOWED")
        require_lease_route_still_clear(root, lease, doc)
        issued = lease.get("issued_authorizations")
        if not isinstance(issued, list):
            raise WorkctlError("ACTION_LEASE_INVALID")
        idempotency_key = args.idempotency_key or "default"
        if EVIDENCE_CAPTURE_IDEMPOTENCY_RE.fullmatch(idempotency_key) is None:
            raise WorkctlError("ACTION_LEASE_IDEMPOTENCY_KEY_INVALID")
        binding = action_lease_authorization_binding(
            lease_id=args.lease_id,
            action_kind=args.action_kind,
            target_ref=args.target_ref,
            action_sha256=args.action_sha256,
            idempotency_key=idempotency_key,
        )
        authorization_id = action_lease_authorization_id(binding)
        path = action_authorization_path(root, authorization_id)
        if path.exists() or path.is_symlink():
            existing = load_action_authorization(root, authorization_id)
            if existing.get("state") == "consumed":
                raise WorkctlError("ACTION_AUTHORIZATION_REPLAYED")
            if datetime.now(UTC) >= parse_authorization_time(existing.get("expires_at")):
                raise WorkctlError("ACTION_AUTHORIZATION_EXPIRED")
            print(json.dumps(existing, indent=2, sort_keys=True))
            return
        if len(issued) >= int(cast(int, lease["max_authorizations"])):
            raise WorkctlError("ACTION_LEASE_EXHAUSTED")
        issued_at = datetime.now(UTC).replace(microsecond=0)
        requested_ttl = args.ttl_seconds or int(cast(int, lease["authorization_ttl_seconds"]))
        if not 1 <= requested_ttl <= int(cast(int, lease["authorization_ttl_seconds"])):
            raise WorkctlError("ACTION_AUTHORIZATION_TTL_INVALID")
        expires_at = issued_at + timedelta(seconds=requested_ttl)
        lease_expires_at = parse_authorization_time(lease.get("expires_at"))
        if expires_at > lease_expires_at:
            expires_at = lease_expires_at
        if datetime.now(UTC) >= expires_at:
            raise WorkctlError("ACTION_AUTHORIZATION_EXPIRED")
        lease_index = len(issued) + 1
        record: dict[str, object] = {
            "schema_version": 2,
            "kind": "work-governance-action-authorization",
            "authorization_id": authorization_id,
            "plan_id": lease["plan_id"],
            "contract_revision": lease["contract_revision"],
            "contract_sha256": lease["contract_sha256"],
            "confirmation_id": lease["confirmation_id"],
            "action_kind": args.action_kind,
            "target_ref": args.target_ref,
            "action_sha256": args.action_sha256,
            "request_ref": lease["request_ref"],
            "turn_receipt_sha256": lease["turn_receipt_sha256"],
            "session_id": lease["session_id"],
            "session_start_receipt_sha256": lease["session_start_receipt_sha256"],
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "state": "authorized",
            "consumed_at": None,
            "consumer_ref": None,
            "authority_source": "lease",
            "lease_id": args.lease_id,
            "lease_basis_sha256": lease["basis_sha256"],
            "lease_authorization_index": lease_index,
            "idempotency_key": idempotency_key,
        }
        record["record_sha256"] = action_authorization_digest(record)
        issued.append(
            {
                "index": lease_index,
                "authorization_id": authorization_id,
                "target_ref": args.target_ref,
                "action_sha256": args.action_sha256,
                "idempotency_key": idempotency_key,
                "authorized_at": issued_at.isoformat(),
            }
        )
        write_action_authority_lease(root, lease)
        write_atomic(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps(record, indent=2, sort_keys=True))


def cmd_action_lease_status(args: argparse.Namespace) -> None:
    """Show one route authority lease plus its effective state."""
    lease = load_action_authority_lease(project_root(), args.lease_id)
    payload = dict(lease)
    if lease.get("state") == "active" and datetime.now(UTC) >= parse_authorization_time(
        lease.get("expires_at")
    ):
        payload["effective_state"] = "expired"
    else:
        payload["effective_state"] = lease.get("state")
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_action_lease_revoke(args: argparse.Namespace) -> None:
    """Revoke one route authority lease without touching already consumed evidence."""
    if not valid_reference(args.ref):
        raise WorkctlError("ACTION_LEASE_REVOKE_REF_INVALID")
    root = project_root()
    with lock(root):
        lease = load_action_authority_lease(root, args.lease_id)
        if lease.get("state") != "revoked":
            lease["state"] = "revoked"
            lease["revoked_at"] = utc_now()
            lease["revoke_ref"] = args.ref
            if lease.get("frozen_at") is not None:
                lease["frozen_at"] = None
                lease["freeze_reason"] = None
            write_action_authority_lease(root, lease)
        print(json.dumps(lease, indent=2, sort_keys=True))


def cmd_action_authorize(args: argparse.Namespace) -> None:
    """Create one short-lived, target-bound, current-turn action capability."""
    root = project_root()
    validate_action_binding(args)
    if not 1 <= args.ttl_seconds <= MAX_ACTION_AUTHORIZATION_TTL_SECONDS:
        raise WorkctlError("ACTION_AUTHORIZATION_TTL_INVALID")
    with lock(root):
        turn = require_confirmation_turn_ref(
            root,
            ref=args.ref,
            turn_receipt_sha256=args.turn_receipt_sha256,
        )
        plan_id, contract_revision, contract_sha256 = require_action_confirmation(
            root,
            confirmation_id=args.confirmation_id,
            action_kind=args.action_kind,
            target_ref=args.target_ref,
            action_sha256=args.action_sha256,
            turn=turn,
        )
        issued_at = parse_authorization_time(turn.get("issued_at"))
        expires_at = issued_at + timedelta(seconds=args.ttl_seconds)
        if datetime.now(UTC) >= expires_at:
            raise WorkctlError("ACTION_AUTHORIZATION_EXPIRED")
        binding = action_authorization_binding(
            turn_receipt_sha256=args.turn_receipt_sha256,
            confirmation_id=args.confirmation_id,
            action_kind=args.action_kind,
            target_ref=args.target_ref,
            action_sha256=args.action_sha256,
        )
        authorization_id = action_authorization_id(binding)
        path = action_authorization_path(root, authorization_id)
        if path.exists() or path.is_symlink():
            existing = load_action_authorization(root, authorization_id)
            if (
                existing.get("plan_id") != plan_id
                or existing.get("contract_revision") != contract_revision
                or existing.get("contract_sha256") != contract_sha256
            ):
                raise WorkctlError("ACTION_AUTHORIZATION_CONTRACT_DRIFT")
            if existing.get("state") == "consumed":
                raise WorkctlError("ACTION_AUTHORIZATION_REPLAYED")
            if datetime.now(UTC) >= parse_authorization_time(existing.get("expires_at")):
                raise WorkctlError("ACTION_AUTHORIZATION_EXPIRED")
            print(json.dumps(existing, indent=2, sort_keys=True))
            return
        session_id = turn.get("session_id")
        session_start_digest = turn.get("session_start_receipt_sha256")
        if not isinstance(session_id, str) or not isinstance(session_start_digest, str):
            raise WorkctlError("TURN_RECEIPT_INVALID")
        record: dict[str, object] = {
            "schema_version": 1,
            "kind": "work-governance-action-authorization",
            "authorization_id": authorization_id,
            "plan_id": plan_id,
            "contract_revision": contract_revision,
            "contract_sha256": contract_sha256,
            "confirmation_id": args.confirmation_id,
            "action_kind": args.action_kind,
            "target_ref": args.target_ref,
            "action_sha256": args.action_sha256,
            "request_ref": args.ref,
            "turn_receipt_sha256": args.turn_receipt_sha256,
            "session_id": session_id,
            "session_start_receipt_sha256": session_start_digest,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "state": "authorized",
            "consumed_at": None,
            "consumer_ref": None,
        }
        record["record_sha256"] = action_authorization_digest(record)
        write_atomic(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps(record, indent=2, sort_keys=True))


def cmd_action_consume(args: argparse.Namespace) -> None:
    """Consume one exact action capability atomically and reject every replay."""
    root = project_root()
    validate_action_binding(args)
    with lock(root):
        record = load_action_authorization(root, args.authorization_id)
        if record.get("state") != "authorized":
            raise WorkctlError("ACTION_AUTHORIZATION_REPLAYED")
        if datetime.now(UTC) >= parse_authorization_time(record.get("expires_at")):
            raise WorkctlError("ACTION_AUTHORIZATION_EXPIRED")
        if record.get("schema_version") == 2:
            lease = load_action_authority_lease(root, str(record["lease_id"]))
            if lease.get("state") != "active":
                raise WorkctlError("ACTION_LEASE_NOT_ACTIVE")
            if datetime.now(UTC) >= parse_authorization_time(lease.get("expires_at")):
                freeze_action_authority_lease(root, lease, "expired")
                raise WorkctlError("ACTION_LEASE_EXPIRED")
            if (
                record.get("action_kind") != args.action_kind
                or record.get("target_ref") != args.target_ref
                or record.get("action_sha256") != args.action_sha256
                or record.get("lease_basis_sha256") != lease.get("basis_sha256")
                or record.get("confirmation_id") != lease.get("confirmation_id")
            ):
                raise WorkctlError("ACTION_AUTHORIZATION_TARGET_MISMATCH")
            doc = load_plan(active_plan_path(root))
            require_plan_contract_ready(doc.frontmatter)
            require_lease_route_still_clear(root, lease, doc)
            if (
                record.get("plan_id") != lease.get("plan_id")
                or record.get("contract_revision") != lease.get("contract_revision")
                or record.get("contract_sha256") != lease.get("contract_sha256")
            ):
                raise WorkctlError("ACTION_AUTHORIZATION_CONTRACT_DRIFT")
        else:
            if args.turn_receipt_sha256 is None:
                raise WorkctlError("TURN_RECEIPT_REQUIRED")
            session_receipt = session_receipt_for_turn(
                root,
                args.turn_receipt_sha256,
                require_current_controller=True,
            )
            turn = load_current_turn_receipt(
                root,
                supplied_sha256=args.turn_receipt_sha256,
                session_receipt=cast(Mapping[str, object], session_receipt),
            )
            expected = action_authorization_binding(
                turn_receipt_sha256=args.turn_receipt_sha256,
                confirmation_id=str(record["confirmation_id"]),
                action_kind=args.action_kind,
                target_ref=args.target_ref,
                action_sha256=args.action_sha256,
            )
            if any(record.get(key) != value for key, value in expected.items()):
                raise WorkctlError("ACTION_AUTHORIZATION_TARGET_MISMATCH")
            plan_id, contract_revision, contract_sha256 = require_action_confirmation(
                root,
                confirmation_id=str(record["confirmation_id"]),
                action_kind=args.action_kind,
                target_ref=args.target_ref,
                action_sha256=args.action_sha256,
                turn=turn,
            )
            if (
                record.get("plan_id") != plan_id
                or record.get("contract_revision") != contract_revision
                or record.get("contract_sha256") != contract_sha256
            ):
                raise WorkctlError("ACTION_AUTHORIZATION_CONTRACT_DRIFT")
            if (
                record.get("request_ref") != turn.get("request_ref")
                or record.get("session_id") != session_receipt.get("session_id")
                or record.get("session_start_receipt_sha256")
                != controller_receipt_digest(session_receipt)
            ):
                raise WorkctlError("ACTION_AUTHORIZATION_TURN_MISMATCH")
        if not valid_reference(args.consumer_ref):
            raise WorkctlError("ACTION_CONSUMER_REF_INVALID")
        record["state"] = "consumed"
        record["consumed_at"] = utc_now()
        record["consumer_ref"] = args.consumer_ref
        record["record_sha256"] = action_authorization_digest(record)
        write_atomic(
            action_authorization_path(root, args.authorization_id),
            json.dumps(record, indent=2, sort_keys=True) + "\n",
        )
        print(json.dumps(record, indent=2, sort_keys=True))


def cmd_action_status(args: argparse.Namespace) -> None:
    """Show one authorization plus its effective expiry state without mutation."""
    record = load_action_authorization(project_root(), args.authorization_id)
    payload = dict(record)
    if record.get("state") == "authorized" and datetime.now(UTC) >= parse_authorization_time(
        record.get("expires_at")
    ):
        payload["effective_state"] = "expired"
    else:
        payload["effective_state"] = record.get("state")
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_plan_status(args: argparse.Namespace) -> None:
    root = project_root()
    report = inspect_authority(root)
    try:
        doc = load_plan(active_plan_path(root))
    except WorkctlError:
        if not args.full:
            print(
                json.dumps(
                    {
                        "plan_id": None,
                        "goal": {},
                        "current_task": None,
                        "ready": [],
                        "blocked": [],
                        "blocked_details": [],
                        "parallel_ready": [],
                        "confirmation_gates": [],
                        "next_suggestion": (
                            "Admit a Plan only when durable execution state is needed."
                        ),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return
        summary: dict[str, Any] = {
            "authority_state": report.state,
            "contract_state": "NO_ACTIVE_PLAN",
            "intake_state": "NO_ACTIVE_PLAN",
            "unknown_contract_state": "NO_ACTIVE_PLAN",
            "intervention_contract_state": "NO_ACTIVE_PLAN",
            "user_intervention": {
                "state": "NOT_REQUIRED",
                "current_targets": [],
                "blocks": [],
                "unknown_id": None,
                "confirmation_id": None,
                "basis_ref": None,
            },
            "legacy_unknown_ids": [],
            "intake_blockers": ["no active Plan"],
            "authority_candidates": [candidate_to_dict(item) for item in report.candidates],
            "blocking_reasons": report.blockers,
            "allowed_commands": report.allowed_commands,
            "closeout_readiness": {"ready": False, "blockers": ["no active Plan"]},
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    if contract_state(doc.frontmatter) == "PLAN_SCHEMA_REFRESH_REQUIRED":
        print(
            json.dumps(
                current_schema_refresh_status(root, doc.frontmatter, report, full=args.full),
                indent=None if not args.full else 2,
                separators=(",", ":") if not args.full else None,
                sort_keys=True,
            )
        )
        return
    runtime_doc = doc.frontmatter
    v5_state: dict[str, Any] | None = None
    if doc.frontmatter.get("schema_version") == 5:
        v5_state = load_v5_state(root, doc.frontmatter)
        runtime_doc = v5_runtime_frontmatter(root, doc.frontmatter, v5_state)
    readiness = closeout_readiness(runtime_doc, report, validate_plan(root))
    legacy_ids = legacy_unknown_ids(doc.frontmatter)
    if not args.full:
        scheduler = (
            v5_state
            if v5_state is not None
            else load_scheduler_state(root, str(doc.frontmatter["plan_id"]))
        )
        print(
            json.dumps(
                compact_plan_status(root, runtime_doc, scheduler=scheduler),
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return
    scheduler = (
        v5_state
        if v5_state is not None
        else load_scheduler_state(root, str(doc.frontmatter["plan_id"]))
    )
    compact = compact_plan_status(root, runtime_doc, scheduler=scheduler)
    summary = {
        "authority_state": report.state,
        "authority_candidates": [candidate_to_dict(item) for item in report.candidates],
        "blocking_reasons": report.blockers,
        "allowed_commands": report.allowed_commands,
        "plan_id": doc.frontmatter.get("plan_id"),
        "status": doc.frontmatter.get("status"),
        "mode": doc.frontmatter.get("mode"),
        "revision": doc.frontmatter.get("revision"),
        "contract_revision": doc.frontmatter.get("contract_revision"),
        "state_sequence": v5_state.get("state_sequence") if v5_state else None,
        "contract_state": contract_state(doc.frontmatter),
        "intake_state": intake_state(doc.frontmatter),
        "unknown_contract_state": ("LEGACY_REPAIR_REQUIRED" if legacy_ids else "STRICT_READY"),
        "intervention_contract_state": intervention_contract_state(doc.frontmatter),
        "user_intervention": user_intervention_projection(doc.frontmatter),
        "legacy_unknown_ids": legacy_ids,
        "intake_blockers": intake_blockers(doc.frontmatter),
        "goal": doc.frontmatter.get("goal", {}),
        "scheduler": {
            "current_task": compact["current_task"],
            "ready": compact["ready"],
            "parallel_ready": compact["parallel_ready"],
            "blocked": compact["blocked"],
            "blocked_details": compact["blocked_details"],
            "confirmation_gates": compact["confirmation_gates"],
            "next_suggestion": compact["next_suggestion"],
        },
        "contract": doc.frontmatter.get("contract", {}),
        "unknowns": doc.frontmatter.get("unknowns", []),
        "revision_history": doc.frontmatter.get("revision_history", []),
        "obligations": doc.frontmatter.get("obligations", []),
        "tasks": runtime_doc.get("tasks", []),
        "validations": doc.frontmatter.get("validations", []),
        "confirmations": doc.frontmatter.get("confirmations", {}),
        "independent_validation": doc.frontmatter.get("independent_validation"),
        "artifacts": doc.frontmatter.get("artifacts", []),
        "scope": doc.frontmatter.get("scope", {}),
        "delivery": doc.frontmatter.get("delivery", {}),
        "activation": doc.frontmatter.get("activation", {}),
        "handoff": doc.frontmatter.get("handoff", {}),
        "route": doc.frontmatter.get("route", {}),
        "closeout_readiness": readiness,
        "completion_claims": completion_claims(runtime_doc, readiness),
    }
    if v5_state is not None:
        summary["events"] = v5_read_events(root, str(doc.frontmatter["plan_id"]))
    legacy_refresh = legacy_refresh_projection(root, doc.frontmatter)
    if legacy_refresh is not None:
        summary["legacy_refresh"] = legacy_refresh
    if args.expected_intake_sha256 is not None:
        summary["current_request_match"] = current_request_matches(
            root,
            doc.frontmatter,
            args.expected_intake_sha256,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


def cmd_plan_queue(args: argparse.Namespace) -> None:
    """Expose ready, blocked, and next scheduler projections as read-only commands."""
    root = project_root()
    doc = load_plan(active_plan_path(root))
    if doc.frontmatter.get("schema_version") == 5:
        state = load_v5_state(root, doc.frontmatter)
        runtime = v5_runtime_frontmatter(root, doc.frontmatter, state)
        compact = compact_plan_status(root, runtime, scheduler=state)
    else:
        scheduler = load_scheduler_state(root, str(doc.frontmatter["plan_id"]))
        compact = compact_plan_status(root, doc.frontmatter, scheduler=scheduler)
    if module_queue_projection is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: queue_projection")
    payload = module_queue_projection(compact, str(args.queue_action))
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def cmd_task_reprioritize(args: argparse.Namespace) -> None:
    """Change runtime task priority with a state-sequence guard."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        task_for(doc.frontmatter, args.task_id)
        if doc.frontmatter.get("schema_version") == 5:
            v5_recover_pending_event(root, doc.frontmatter)
            state = load_v5_state(root, doc.frontmatter)
            if state["state_sequence"] != args.expected_state_sequence:
                raise WorkctlError(
                    "STATE_SEQUENCE_MISMATCH: "
                    f"expected {args.expected_state_sequence}, found {state['state_sequence']}"
                )
            state["priorities"][args.task_id] = args.priority
            v5_persist_state_transition(
                root,
                doc.frontmatter,
                state,
                event="task.reprioritized",
                subject=f"task:{args.task_id}",
                payload={"priority": args.priority},
            )
            print(
                f"TASK_REPRIORITIZED {args.task_id} priority={args.priority} "
                f"state_sequence={state['state_sequence']}"
            )
            return
        state = load_scheduler_state(root, str(doc.frontmatter["plan_id"]))
        expected = args.expected_state_sequence
        if state["state_sequence"] != expected:
            raise WorkctlError(
                f"STATE_SEQUENCE_MISMATCH: expected {expected}, found {state['state_sequence']}"
            )
        priorities = cast(dict[str, int], state["priorities"])
        priorities[args.task_id] = args.priority
        state["state_sequence"] += 1
        write_atomic(
            scheduler_state_path(root, str(doc.frontmatter["plan_id"])),
            dump_scheduler_state(state),
        )
    print(
        f"TASK_REPRIORITIZED {args.task_id} priority={args.priority} "
        f"state_sequence={state['state_sequence']}"
    )


def cmd_workflow_help(args: argparse.Namespace) -> None:
    """Print the stable public workflow command surface."""
    workflows = MODULE_WORKFLOW_HELP
    workflow_aliases = MODULE_WORKFLOW_HELP_ALIASES
    workflow = args.workflow or "plan"
    workflow = workflow_aliases.get(workflow, workflow)
    if workflow not in workflows:
        raise WorkctlError(f"UNKNOWN_WORKFLOW: {workflow}")
    print(json.dumps(workflows[workflow], indent=2, sort_keys=True))


def cmd_goal_show(_args: argparse.Namespace) -> None:
    """Show the active Goal Contract projection."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    contract = doc.frontmatter.get("contract", {})
    goal = doc.frontmatter.get("goal")
    payload = {
        "plan_id": doc.frontmatter.get("plan_id"),
        "schema_version": doc.frontmatter.get("schema_version"),
        "goal": goal,
        "success_criteria": doc.frontmatter.get(
            "success_criteria",
            goal.get("success_conditions", []) if isinstance(goal, dict) else [],
        ),
        "contract_revision": doc.frontmatter.get(
            "contract_revision",
            contract.get("revision") if isinstance(contract, dict) else None,
        ),
        "truth_refs": doc.frontmatter.get("truth_refs", []),
        "confirmation_gates": [
            item.get("id")
            for item in confirmations(doc.frontmatter).values()
            if item.get("status") == "pending"
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_gate_list(_args: argparse.Namespace) -> None:
    """List the active Plan's confirmation gates."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    payload = {
        "plan_id": doc.frontmatter.get("plan_id"),
        "gates": list(confirmations(doc.frontmatter).values()),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_gate_check(args: argparse.Namespace) -> None:
    """Show one confirmation gate by ID."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    gate = confirmations(doc.frontmatter).get(args.gate_id)
    if gate is None:
        raise WorkctlError(f"UNKNOWN_GATE: {args.gate_id}")
    print(json.dumps(gate, indent=2, sort_keys=True))


def cmd_gate_satisfy(args: argparse.Namespace) -> None:
    """Resolve one gate as accepted through the existing confirmation command."""
    args.decision = "accepted"
    cmd_plan_confirm(args)


def cmd_gate_waive(args: argparse.Namespace) -> None:
    """Resolve one gate as declined through the existing confirmation command."""
    args.decision = "declined"
    cmd_plan_confirm(args)


def cmd_truth_list(_args: argparse.Namespace) -> None:
    """List durable truth references recorded in the active contract."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    truth_refs = doc.frontmatter.get("truth_refs", [])
    print(
        json.dumps(
            {
                "plan_id": doc.frontmatter.get("plan_id"),
                "truth_refs": truth_refs if isinstance(truth_refs, list) else [],
            },
            indent=2,
            sort_keys=True,
        )
    )


def cmd_truth_conflicts(_args: argparse.Namespace) -> None:
    """Report duplicate truth references for the active contract."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    truth_refs = doc.frontmatter.get("truth_refs", [])
    values = (
        [item for item in truth_refs if isinstance(item, str)]
        if isinstance(truth_refs, list)
        else []
    )
    counts = {item: values.count(item) for item in values}
    print(
        json.dumps(
            {
                "plan_id": doc.frontmatter.get("plan_id"),
                "conflicts": sorted(item for item, count in counts.items() if count > 1),
            },
            indent=2,
            sort_keys=True,
        )
    )


def reviewer_acquisition_directory(root: Path) -> Path:
    """Return the runtime cache for reviewer-acquisition attempts."""
    path = runtime_dir(root) / "reviewer-acquisition"
    reject_symlink_components(root, path)
    return path


def reviewer_acquisition_id(
    *,
    plan_id: str,
    target_ref: str,
    mechanism: str,
    review_input_sha256: str,
) -> str:
    """Derive the stable cache key for one reviewer acquisition route."""
    binding = {
        "plan_id": plan_id,
        "target_ref": target_ref,
        "mechanism": mechanism,
        "review_input_sha256": review_input_sha256,
    }
    digest = sha256_bytes(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"RA-{digest[:32]}"


def reviewer_acquisition_path(root: Path, acquisition_id: str) -> Path:
    """Return the runtime record path for one acquisition cache entry."""
    if REVIEWER_ACQUISITION_ID_RE.fullmatch(acquisition_id) is None:
        raise WorkctlError("REVIEWER_ACQUISITION_ID_INVALID")
    path = reviewer_acquisition_directory(root) / f"{acquisition_id}.json"
    reject_symlink_components(root, path)
    return path


def reviewer_acquisition_digest(record: Mapping[str, object]) -> str:
    """Hash a reviewer-acquisition record without its self-authenticating digest."""
    projection = {key: value for key, value in record.items() if key != "record_sha256"}
    return sha256_bytes(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def validate_reviewer_acquisition_scope(args: argparse.Namespace, plan_id: str) -> str:
    """Validate and return the stable reviewer-acquisition runtime key."""
    if not valid_target_ref(args.target_ref):
        raise WorkctlError("REVIEWER_ACQUISITION_TARGET_INVALID")
    if REVIEWER_ACQUISITION_MECHANISM_RE.fullmatch(args.mechanism) is None:
        raise WorkctlError("REVIEWER_ACQUISITION_MECHANISM_INVALID")
    if SHA256_RE.fullmatch(args.review_input_sha256) is None:
        raise WorkctlError("REVIEWER_ACQUISITION_INPUT_SHA256_INVALID")
    return reviewer_acquisition_id(
        plan_id=plan_id,
        target_ref=args.target_ref,
        mechanism=args.mechanism,
        review_input_sha256=args.review_input_sha256,
    )


def load_reviewer_acquisition_record(root: Path, acquisition_id: str) -> dict[str, Any]:
    """Load and validate one reviewer-acquisition runtime record."""
    path = reviewer_acquisition_path(root, acquisition_id)
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("REVIEWER_ACQUISITION_NOT_FOUND")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkctlError("REVIEWER_ACQUISITION_INVALID") from exc
    if not isinstance(payload, dict):
        raise WorkctlError("REVIEWER_ACQUISITION_INVALID")
    record = cast(dict[str, Any], payload)
    required = {
        "schema_version",
        "kind",
        "acquisition_id",
        "plan_id",
        "target_ref",
        "mechanism",
        "review_input_sha256",
        "state",
        "created_at",
        "updated_at",
        "cooldown_until",
        "latest_attempt_index",
        "attempts",
        "record_sha256",
    }
    attempts = record.get("attempts")
    invalid = (
        set(record) != required
        or record.get("schema_version") != 1
        or record.get("kind") != "work-governance-reviewer-acquisition"
        or record.get("acquisition_id") != acquisition_id
        or not isinstance(record.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(record["plan_id"])) is None
        or not valid_target_ref(record.get("target_ref"))
        or not isinstance(record.get("mechanism"), str)
        or REVIEWER_ACQUISITION_MECHANISM_RE.fullmatch(str(record["mechanism"])) is None
        or not isinstance(record.get("review_input_sha256"), str)
        or SHA256_RE.fullmatch(str(record["review_input_sha256"])) is None
        or record.get("state") != "validator_unavailable"
        or not isinstance(record.get("cooldown_until"), str)
        or type(record.get("latest_attempt_index")) is not int
        or not isinstance(attempts, list)
        or not attempts
        or len(attempts) > REVIEWER_ACQUISITION_MAX_ATTEMPTS
        or not isinstance(record.get("record_sha256"), str)
        or SHA256_RE.fullmatch(str(record["record_sha256"])) is None
        or reviewer_acquisition_digest(record) != record.get("record_sha256")
    )
    if invalid:
        raise WorkctlError("REVIEWER_ACQUISITION_INVALID")
    parse_authorization_time(record["created_at"])
    parse_authorization_time(record["updated_at"])
    parse_authorization_time(record["cooldown_until"])
    attempt_values = cast(list[object], attempts)
    seen_keys: set[str] = set()
    for index, item in enumerate(attempt_values, start=1):
        if (
            not isinstance(item, dict)
            or type(item.get("index")) is not int
            or item.get("index") != index
            or not valid_reference(item.get("attempt_ref"))
            or not isinstance(item.get("idempotency_key"), str)
            or EVIDENCE_CAPTURE_IDEMPOTENCY_RE.fullmatch(str(item["idempotency_key"])) is None
            or item["idempotency_key"] in seen_keys
            or item.get("outcome") != "failed"
            or item.get("failure_class") not in REVIEWER_FAILURE_CLASSES
            or not isinstance(item.get("failure_fingerprint"), str)
            or SHA256_RE.fullmatch(str(item["failure_fingerprint"])) is None
            or not isinstance(item.get("failure_summary"), str)
            or not item["failure_summary"]
            or not isinstance(item.get("redacted_excerpt"), str)
            or not isinstance(item.get("output_sha256"), str)
            or SHA256_RE.fullmatch(str(item["output_sha256"])) is None
            or type(item.get("output_size")) is not int
            or int(cast(int, item["output_size"])) < 0
            or type(item.get("exit_code")) is not int
            or type(item.get("cooldown_seconds")) is not int
            or not (
                1
                <= int(cast(int, item["cooldown_seconds"]))
                <= REVIEWER_ACQUISITION_MAX_COOLDOWN_SECONDS
            )
            or not isinstance(item.get("cooldown_until"), str)
            or not isinstance(item.get("recorded_at"), str)
        ):
            raise WorkctlError("REVIEWER_ACQUISITION_INVALID")
        parse_authorization_time(item["cooldown_until"])
        parse_authorization_time(item["recorded_at"])
        seen_keys.add(str(item["idempotency_key"]))
    latest_index = int(cast(int, record["latest_attempt_index"]))
    if latest_index != len(attempt_values):
        raise WorkctlError("REVIEWER_ACQUISITION_INVALID")
    return record


def try_load_reviewer_acquisition_record(
    root: Path,
    acquisition_id: str,
) -> dict[str, Any] | None:
    """Return a reviewer-acquisition record when it exists."""
    path = reviewer_acquisition_path(root, acquisition_id)
    if not path.exists() and not path.is_symlink():
        return None
    return load_reviewer_acquisition_record(root, acquisition_id)


def load_reviewer_acquisition_records(root: Path, plan_id: str) -> list[dict[str, Any]]:
    """Load every reviewer-acquisition record for one Plan."""
    directory = reviewer_acquisition_directory(root)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise WorkctlError("REVIEWER_ACQUISITION_DIRECTORY_INVALID")
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("RA-*.json")):
        record = load_reviewer_acquisition_record(root, path.stem)
        if record.get("plan_id") == plan_id:
            records.append(record)
    return records


def write_reviewer_acquisition_record(root: Path, record: dict[str, Any]) -> None:
    """Persist one reviewer-acquisition runtime record with a fresh self digest."""
    record["record_sha256"] = reviewer_acquisition_digest(record)
    write_atomic(
        reviewer_acquisition_path(root, str(record["acquisition_id"])),
        json.dumps(record, indent=2, sort_keys=True) + "\n",
    )


def read_reviewer_failure_bytes(root: Path, args: argparse.Namespace) -> bytes:
    """Read reviewer failure output from stdin or one project-local file."""
    if args.failure_stdin and args.failure_from_file is not None:
        raise WorkctlError("REVIEWER_ACQUISITION_FAILURE_SOURCE_CONFLICT")
    if isinstance(args.failure_from_file, str):
        input_path = checked_project_path(root, args.failure_from_file)
        reject_symlink_components(root, input_path)
        if input_path.is_symlink() or not input_path.is_file():
            raise WorkctlError("REVIEWER_ACQUISITION_FAILURE_SOURCE_MISSING")
        content = input_path.read_bytes()
    else:
        content = sys.stdin.buffer.read()
    if len(content) > REVIEWER_ACQUISITION_MAX_BYTES:
        raise WorkctlError("REVIEWER_ACQUISITION_FAILURE_TOO_LARGE")
    return content


def reviewer_failure_signals(text: str) -> list[str]:
    """Extract stable, non-secret signals from reviewer acquisition failure text."""
    lowered = text.lower()
    signals: list[str] = []
    if "proxy connection failed" in lowered or "http connect failed with status 403" in lowered:
        signals.append("proxy-connect-403")
    if "backend-api/codex/responses" in lowered:
        signals.append("codex-responses-api")
    if "backend-api/codex/models" in lowered:
        signals.append("codex-models-api")
    if "authentication" in lowered or "unauthorized" in lowered or "status 401" in lowered:
        signals.append("auth-unavailable")
    if "command not found" in lowered or "no such file or directory" in lowered:
        signals.append("command-missing")
    if "timed out" in lowered or "timeout" in lowered:
        signals.append("timeout")
    if "trusted_attestation" in lowered or "attestor" in lowered:
        signals.append("attestor-untrusted")
    if signals:
        return sorted(set(signals))
    normalized: list[str] = []
    for line in text.splitlines():
        stripped = re.sub(r"\d{4}-\d{2}-\d{2}T\S+", "<timestamp>", line.strip())
        stripped = re.sub(r"[0-9a-f]{32,64}", "<hex>", stripped)
        if stripped:
            normalized.append(stripped[:160])
        if len(normalized) >= 6:
            break
    return normalized or ["empty-output"]


def classify_reviewer_failure(text: str, exit_code: int, requested: str) -> str:
    """Classify a reviewer acquisition failure into a stable governance category."""
    if requested != "auto":
        if requested not in REVIEWER_FAILURE_CLASSES:
            raise WorkctlError("REVIEWER_ACQUISITION_FAILURE_CLASS_INVALID")
        return requested
    lowered = text.lower()
    if "proxy connection failed" in lowered or "http connect failed with status 403" in lowered:
        return "network_proxy_blocked"
    if "authentication" in lowered or "unauthorized" in lowered or "status 401" in lowered:
        return "auth_unavailable"
    if "command not found" in lowered or "no such file or directory" in lowered:
        return "command_missing"
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout"
    if "trusted_attestation" in lowered or "attestor" in lowered:
        return "attestor_untrusted"
    if exit_code == 124:
        return "timeout"
    return "unknown_failure"


def reviewer_failure_fingerprint(
    *,
    mechanism: str,
    failure_class: str,
    signals: Sequence[str],
) -> str:
    """Hash the stable failure classification and signals for cooldown matching."""
    payload = {
        "mechanism": mechanism,
        "failure_class": failure_class,
        "signals": list(signals),
    }
    return sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def reviewer_failure_summary(text: str, explicit_summary: str | None, failure_class: str) -> str:
    """Return a redacted, bounded failure summary for the runtime record."""
    if isinstance(explicit_summary, str) and explicit_summary.strip():
        summary = redact_capture_text(explicit_summary.strip())
    else:
        summary = next((line.strip() for line in text.splitlines() if line.strip()), failure_class)
    summary = summary[:512]
    return summary or failure_class


def reviewer_failure_components(root: Path, args: argparse.Namespace) -> dict[str, object]:
    """Read and classify one reviewer-acquisition failure payload."""
    raw_failure = read_reviewer_failure_bytes(root, args)
    redacted_failure, _text_source = redact_capture_bytes(raw_failure)
    text = redacted_failure.decode("utf-8")
    summary = reviewer_failure_summary(text, args.summary, args.failure_class)
    if not text.strip() and not summary.strip():
        raise WorkctlError("REVIEWER_ACQUISITION_FAILURE_REQUIRED")
    classification_text = f"{summary}\n{text}"
    failure_class = classify_reviewer_failure(
        classification_text,
        args.exit_code,
        args.failure_class,
    )
    signals = reviewer_failure_signals(classification_text)
    return {
        "text": text,
        "summary": summary,
        "failure_class": failure_class,
        "failure_fingerprint": reviewer_failure_fingerprint(
            mechanism=args.mechanism,
            failure_class=failure_class,
            signals=signals,
        ),
        "output_sha256": sha256_bytes(redacted_failure),
        "output_size": len(redacted_failure),
    }


def reviewer_acquisition_latest(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the latest attempt from a validated reviewer-acquisition record."""
    attempts = cast(list[dict[str, Any]], record["attempts"])
    return attempts[int(cast(int, record["latest_attempt_index"])) - 1]


def reviewer_acquisition_cooldown_active(record: Mapping[str, Any]) -> bool:
    """Return whether a reviewer-acquisition cooldown is still active."""
    return datetime.now(UTC) < parse_authorization_time(record["cooldown_until"])


def reviewer_acquisition_mechanism_cache(
    root: Path,
    plan_id: str,
    mechanism: str,
    *,
    exclude_acquisition_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the active mechanism-scoped cache entry for a reviewer route."""
    candidates: list[dict[str, Any]] = []
    for record in load_reviewer_acquisition_records(root, plan_id):
        if record["acquisition_id"] == exclude_acquisition_id:
            continue
        if record["mechanism"] != mechanism:
            continue
        latest = reviewer_acquisition_latest(record)
        if latest["failure_class"] not in MECHANISM_SCOPED_REVIEWER_FAILURE_CLASSES:
            continue
        if reviewer_acquisition_cooldown_active(record):
            candidates.append(record)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda record: (
            parse_authorization_time(record["cooldown_until"]),
            str(record["acquisition_id"]),
        ),
    )


def reviewer_acquisition_projection(
    record: Mapping[str, Any],
    *,
    cache_scope: str | None = None,
    requested_acquisition_id: str | None = None,
) -> dict[str, Any]:
    """Project a reviewer-acquisition record into a compact status payload."""
    latest = reviewer_acquisition_latest(record)
    cached = reviewer_acquisition_cooldown_active(record)
    payload = {
        "acquisition_id": record["acquisition_id"],
        "plan_id": record["plan_id"],
        "target_ref": record["target_ref"],
        "mechanism": record["mechanism"],
        "review_input_sha256": record["review_input_sha256"],
        "attempt_allowed": not cached,
        "state": "VALIDATOR_UNAVAILABLE_CACHED" if cached else "cooldown_expired",
        "failure_class": latest["failure_class"],
        "failure_fingerprint": latest["failure_fingerprint"],
        "failure_summary": latest["failure_summary"],
        "attempt_count": len(cast(list[object], record["attempts"])),
        "cooldown_until": record["cooldown_until"],
        "latest_attempt_ref": latest["attempt_ref"],
        "latest_recorded_at": latest["recorded_at"],
        "fallback_boundary": (
            "deterministic_self_challenge_for_reversible_local_only; "
            "high_impact_targets_remain_fail_closed"
        ),
    }
    if cache_scope is not None:
        payload["cache_scope"] = cache_scope
    if requested_acquisition_id is not None:
        payload["requested_acquisition_id"] = requested_acquisition_id
    return payload


def cmd_review_acquisition_check(args: argparse.Namespace) -> None:
    """Tell the caller whether a reviewer acquisition attempt should run."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    plan_id = str(doc.frontmatter["plan_id"])
    acquisition_id = validate_reviewer_acquisition_scope(args, plan_id)
    record = try_load_reviewer_acquisition_record(root, acquisition_id)
    if record is not None:
        payload = reviewer_acquisition_projection(record, cache_scope="exact")
        if payload["attempt_allowed"]:
            mechanism_cache = reviewer_acquisition_mechanism_cache(
                root,
                plan_id,
                args.mechanism,
                exclude_acquisition_id=acquisition_id,
            )
            if mechanism_cache is not None:
                payload = reviewer_acquisition_projection(
                    mechanism_cache,
                    cache_scope="mechanism",
                    requested_acquisition_id=acquisition_id,
                )
                payload["requested_target_ref"] = args.target_ref
                payload["requested_review_input_sha256"] = args.review_input_sha256
    else:
        mechanism_cache = reviewer_acquisition_mechanism_cache(root, plan_id, args.mechanism)
        if mechanism_cache is not None:
            payload = reviewer_acquisition_projection(
                mechanism_cache,
                cache_scope="mechanism",
                requested_acquisition_id=acquisition_id,
            )
            payload["requested_target_ref"] = args.target_ref
            payload["requested_review_input_sha256"] = args.review_input_sha256
        else:
            payload = {
                "plan_id": plan_id,
                "target_ref": args.target_ref,
                "mechanism": args.mechanism,
                "review_input_sha256": args.review_input_sha256,
                "acquisition_id": acquisition_id,
                "attempt_allowed": True,
                "state": "attempt_allowed",
                "cache_scope": "none",
            }
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_review_acquisition_status(args: argparse.Namespace) -> None:
    """Show reviewer-acquisition failure caches for the active Plan."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    plan_id = str(doc.frontmatter["plan_id"])
    records = load_reviewer_acquisition_records(root, plan_id)
    projections = [reviewer_acquisition_projection(record) for record in records]
    if args.target_ref is not None:
        if not valid_target_ref(args.target_ref):
            raise WorkctlError("REVIEWER_ACQUISITION_TARGET_INVALID")
        projections = [item for item in projections if item["target_ref"] == args.target_ref]
    if args.mechanism is not None:
        if REVIEWER_ACQUISITION_MECHANISM_RE.fullmatch(args.mechanism) is None:
            raise WorkctlError("REVIEWER_ACQUISITION_MECHANISM_INVALID")
        projections = [item for item in projections if item["mechanism"] == args.mechanism]
    print(
        json.dumps(
            {
                "plan_id": plan_id,
                "reviewer_acquisition": projections,
            },
            indent=2,
            sort_keys=True,
        )
    )


def cmd_review_acquisition_record_failure(args: argparse.Namespace) -> None:
    """Record a failed reviewer acquisition and install a bounded cooldown."""
    root = project_root()
    if args.exit_code < -9999 or args.exit_code > 9999:
        raise WorkctlError("REVIEWER_ACQUISITION_EXIT_CODE_INVALID")
    if not 1 <= args.cooldown_seconds <= REVIEWER_ACQUISITION_MAX_COOLDOWN_SECONDS:
        raise WorkctlError("REVIEWER_ACQUISITION_COOLDOWN_INVALID")
    if not valid_reference(args.attempt_ref):
        raise WorkctlError("REVIEWER_ACQUISITION_ATTEMPT_REF_INVALID")
    idempotency_key = args.idempotency_key or "default"
    if EVIDENCE_CAPTURE_IDEMPOTENCY_RE.fullmatch(idempotency_key) is None:
        raise WorkctlError("REVIEWER_ACQUISITION_IDEMPOTENCY_KEY_INVALID")
    failure = reviewer_failure_components(root, args)
    if args.dry_run:
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        plan_id = str(doc.frontmatter["plan_id"])
        acquisition_id = validate_reviewer_acquisition_scope(args, plan_id)
        existing = try_load_reviewer_acquisition_record(root, acquisition_id)
        if existing is not None and reviewer_acquisition_cooldown_active(existing):
            payload = reviewer_acquisition_projection(existing, cache_scope="exact")
            payload.update(
                {
                    "state": "would_reject_failure_record",
                    "reason": "REVIEWER_ACQUISITION_COOLDOWN_ACTIVE",
                    "proposed_failure_class": failure["failure_class"],
                    "proposed_failure_fingerprint": failure["failure_fingerprint"],
                    "proposed_failure_summary": failure["summary"],
                    "write": False,
                }
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        mechanism_cache = reviewer_acquisition_mechanism_cache(
            root,
            plan_id,
            args.mechanism,
            exclude_acquisition_id=acquisition_id,
        )
        if mechanism_cache is not None:
            payload = reviewer_acquisition_projection(
                mechanism_cache,
                cache_scope="mechanism",
                requested_acquisition_id=acquisition_id,
            )
            payload["requested_target_ref"] = args.target_ref
            payload["requested_review_input_sha256"] = args.review_input_sha256
            payload.update(
                {
                    "state": "would_reject_failure_record",
                    "reason": "REVIEWER_ACQUISITION_MECHANISM_COOLDOWN_ACTIVE",
                    "proposed_failure_class": failure["failure_class"],
                    "proposed_failure_fingerprint": failure["failure_fingerprint"],
                    "proposed_failure_summary": failure["summary"],
                    "write": False,
                }
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        recorded_at = utc_now()
        cooldown_until = (
            parse_authorization_time(recorded_at) + timedelta(seconds=args.cooldown_seconds)
        ).isoformat()
        payload = {
            "plan_id": plan_id,
            "target_ref": args.target_ref,
            "mechanism": args.mechanism,
            "review_input_sha256": args.review_input_sha256,
            "acquisition_id": acquisition_id,
            "attempt_allowed": False,
            "state": "would_record_failure",
            "failure_class": failure["failure_class"],
            "failure_fingerprint": failure["failure_fingerprint"],
            "failure_summary": failure["summary"],
            "cooldown_until": cooldown_until,
            "write": False,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        plan_id = str(doc.frontmatter["plan_id"])
        acquisition_id = validate_reviewer_acquisition_scope(args, plan_id)
        failure_class = str(failure["failure_class"])
        failure_fingerprint = str(failure["failure_fingerprint"])
        output_sha256 = str(failure["output_sha256"])
        existing = try_load_reviewer_acquisition_record(root, acquisition_id)
        if existing is not None:
            attempts = cast(list[dict[str, Any]], existing["attempts"])
            prior = next(
                (
                    attempt
                    for attempt in attempts
                    if attempt.get("idempotency_key") == idempotency_key
                ),
                None,
            )
            if prior is not None:
                if (
                    prior.get("attempt_ref") != args.attempt_ref
                    or prior.get("failure_class") != failure_class
                    or prior.get("failure_fingerprint") != failure_fingerprint
                    or prior.get("output_sha256") != output_sha256
                    or prior.get("exit_code") != args.exit_code
                    or prior.get("cooldown_seconds") != args.cooldown_seconds
                ):
                    raise WorkctlError("REVIEWER_ACQUISITION_IDEMPOTENCY_CONFLICT")
                payload = reviewer_acquisition_projection(existing)
                payload["idempotent"] = True
                payload["write"] = False
                print(json.dumps(payload, indent=2, sort_keys=True))
                return
            if reviewer_acquisition_cooldown_active(existing):
                raise WorkctlError("REVIEWER_ACQUISITION_COOLDOWN_ACTIVE")
            if len(attempts) >= REVIEWER_ACQUISITION_MAX_ATTEMPTS:
                raise WorkctlError("REVIEWER_ACQUISITION_ATTEMPTS_EXHAUSTED")
        mechanism_cache = reviewer_acquisition_mechanism_cache(
            root,
            plan_id,
            args.mechanism,
            exclude_acquisition_id=acquisition_id,
        )
        if mechanism_cache is not None:
            raise WorkctlError(
                "REVIEWER_ACQUISITION_MECHANISM_COOLDOWN_ACTIVE: "
                f"{mechanism_cache['acquisition_id']}"
            )
        if existing is not None:
            attempts = cast(list[dict[str, Any]], existing["attempts"])
            record = existing
            created_at = str(existing["created_at"])
            attempt_index = len(attempts) + 1
        else:
            record = {
                "schema_version": 1,
                "kind": "work-governance-reviewer-acquisition",
                "acquisition_id": acquisition_id,
                "plan_id": plan_id,
                "target_ref": args.target_ref,
                "mechanism": args.mechanism,
                "review_input_sha256": args.review_input_sha256,
                "state": "validator_unavailable",
                "attempts": [],
            }
            created_at = utc_now()
            attempt_index = 1
        recorded_at = utc_now()
        cooldown_until = (
            parse_authorization_time(recorded_at) + timedelta(seconds=args.cooldown_seconds)
        ).isoformat()
        attempt = {
            "index": attempt_index,
            "attempt_ref": args.attempt_ref,
            "idempotency_key": idempotency_key,
            "outcome": "failed",
            "failure_class": failure_class,
            "failure_fingerprint": failure_fingerprint,
            "failure_summary": failure["summary"],
            "redacted_excerpt": str(failure["text"])[:2048],
            "output_sha256": output_sha256,
            "output_size": failure["output_size"],
            "exit_code": args.exit_code,
            "cooldown_seconds": args.cooldown_seconds,
            "cooldown_until": cooldown_until,
            "recorded_at": recorded_at,
        }
        attempts = cast(list[dict[str, Any]], record["attempts"])
        attempts.append(attempt)
        record["created_at"] = created_at
        record["updated_at"] = recorded_at
        record["cooldown_until"] = cooldown_until
        record["latest_attempt_index"] = attempt_index
        write_reviewer_acquisition_record(root, record)
        payload = reviewer_acquisition_projection(record)
        payload["idempotent"] = False
        payload["write"] = True
        print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_review_status(_args: argparse.Namespace) -> None:
    """Show active independent-validation records."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    plan_id = str(doc.frontmatter["plan_id"])
    print(
        json.dumps(
            {
                "plan_id": plan_id,
                "independent_validation": doc.frontmatter.get("independent_validation", {}),
                "reviewer_acquisition": [
                    reviewer_acquisition_projection(record)
                    for record in load_reviewer_acquisition_records(root, plan_id)
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def cmd_review_request(_args: argparse.Namespace) -> None:
    """Print the review modes expected by Work Governance."""
    print(
        json.dumps(
            {
                "review_modes": [
                    "plan_challenge",
                    "artifact_review",
                    "evidence_audit",
                ],
                "record_command": "review attach --manifest PATH",
                "acquisition_commands": [
                    "review acquisition check",
                    "review acquisition record-failure",
                    "review acquisition status",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def cmd_migrate_inspect(_args: argparse.Namespace) -> None:
    """Report the current-schema refresh boundary without writing any state."""
    root = project_root()
    report = inspect_authority(root)
    payload: dict[str, Any] = {
        "authority_state": report.state,
        "plan_id": None,
        "from_schema_version": None,
        "to_schema_version": CURRENT_PLAN_SCHEMA_VERSION,
        "write": False,
    }
    if report.state in {"GOVERNED_ACTIVE", "PLAN_SCHEMA_REFRESH_REQUIRED"}:
        doc = load_plan(active_plan_path(root))
        payload["plan_id"] = doc.frontmatter.get("plan_id")
        payload["from_schema_version"] = doc.frontmatter.get("schema_version")
        if migration_projection is None:
            raise WorkctlError("MIGRATION_MODULE_UNAVAILABLE: migration_projection")
        payload.update(migration_projection(doc.frontmatter))
    print(json.dumps(payload, indent=2, sort_keys=True))


def v5_migration_base(root: Path) -> Path:
    """Return the ignored parent for current-schema refresh transactions."""
    path = governance_root(root) / "runtime" / "migrations-v5"
    reject_symlink_components(root, path)
    return path


def next_v5_migration_id(root: Path) -> str:
    date_part = datetime.now(UTC).strftime("%Y%m%d")
    base = v5_migration_base(root)
    existing = (
        {
            path.name
            for path in base.iterdir()
            if base.is_dir() and path.is_dir() and MIGRATION_ID_RE.fullmatch(path.name)
        }
        if base.exists()
        else set()
    )
    for number in range(1, 1000):
        candidate = f"MIG-{date_part}-{number:03d}"
        if candidate not in existing:
            return candidate
    raise WorkctlError("SCHEMA_V5_MIGRATION_ID_EXHAUSTED")


def v5_migration_paths(root: Path, migration_id: str) -> dict[str, Path]:
    if MIGRATION_ID_RE.fullmatch(migration_id) is None:
        raise WorkctlError("SCHEMA_V5_MIGRATION_ID_INVALID")
    transaction = v5_migration_base(root) / migration_id
    return {
        "transaction": transaction,
        "journal": transaction / "journal.json",
        "staging": transaction / "staging" / "plan.md",
        "backup": transaction / "backup" / "plan.md",
        "state_staging": transaction / "staging" / "state.json",
        "events_staging": transaction / "staging" / "events.jsonl",
    }


def v5_legacy_archive_path(root: Path, migration_id: str, source_name: str) -> Path:
    """Return the versioned archive target for one legacy active Plan."""
    if MIGRATION_ID_RE.fullmatch(migration_id) is None:
        raise WorkctlError("SCHEMA_V5_MIGRATION_ID_INVALID")
    if Path(source_name).name != source_name:
        raise WorkctlError("SCHEMA_V5_MIGRATION_SOURCE_NAME_INVALID")
    path = checked_project_path(root, plan_relative_path("archive", migration_id, source_name))
    reject_symlink_components(root, path)
    return path


def current_schema_refresh_body(contract: Mapping[str, Any]) -> str:
    """Build a fresh active Plan body that points to the archived legacy source."""
    title = str(contract.get("title") or contract.get("plan_id") or "Current Plan")
    goal = contract.get("goal")
    success_conditions = contract.get("success_conditions", [])
    tasks = contract.get("tasks", [])
    archive = contract.get("legacy_archive")
    archive_path = archive.get("path") if isinstance(archive, dict) else None
    lines = [
        f"# {title}",
        "",
        "## Goal",
        str(goal) if isinstance(goal, str) and goal else "See frontmatter goal.",
        "",
        "## Success Conditions",
    ]
    if isinstance(success_conditions, list) and success_conditions:
        lines.extend(
            f"- {item}" for item in success_conditions if isinstance(item, str) and item
        )
    else:
        lines.append("- See frontmatter success_conditions.")
    lines.extend(["", "## Tasks"])
    if isinstance(tasks, list) and tasks:
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = task.get("id")
            description = task.get("description")
            if isinstance(task_id, str) and isinstance(description, str):
                lines.append(f"- {task_id}: {description}")
    else:
        lines.append("- See frontmatter tasks.")
    lines.extend(
        [
            "",
            "## Legacy Archive",
            (
                f"Legacy Plan bytes are archived at `{archive_path}`."
                if isinstance(archive_path, str) and archive_path
                else "Legacy Plan bytes are archived in the schema refresh journal."
            ),
            (
                "Legacy runtime state was not migrated; review `plan status` "
                "legacy_refresh before selecting the next task."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def prepare_v5_migration(
    root: Path,
    source: PlanDocument,
    *,
    migration_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes]:
    """Prepare current-schema contract, state, event, and journal bytes."""
    from_schema_version = source.frontmatter.get("schema_version")
    if from_schema_version == CURRENT_PLAN_SCHEMA_VERSION:
        raise WorkctlError("CURRENT_PLAN_SCHEMA_REFRESH_NOT_REQUIRED")
    if not isinstance(from_schema_version, int) or from_schema_version < 1:
        raise WorkctlError("SCHEMA_V5_MIGRATION_SOURCE_UNSUPPORTED")
    if build_v5_contract is None or build_v5_state is None:
        raise WorkctlError("SCHEMA_V5_MIGRATION_MODULE_UNAVAILABLE")
    timestamp = utc_now()
    source_bytes = source.path.read_bytes()
    source_sha256 = sha256_bytes(source_bytes)
    archive_path = v5_legacy_archive_path(root, migration_id, source.path.name)
    archive_relative = relative_project_path(root, archive_path)
    summary = (
        legacy_plan_summary(source.frontmatter)
        if callable(legacy_plan_summary)
        else {
            "authority": "NON_AUTHORITY",
            "schema_version": from_schema_version,
            "not_migrated": list(REFRESH_NOT_MIGRATED),
        }
    )
    contract = build_v5_contract(source.frontmatter)
    contract["legacy_archive"] = {
        "path": archive_relative,
        "sha256": source_sha256,
        "from_schema_version": from_schema_version,
        "mode": "archive_legacy_and_rebuild_current_plan",
        "runtime_state": "fresh",
        "state_reset": True,
        "legacy_state_migrated": False,
        "not_migrated": list(REFRESH_NOT_MIGRATED),
        "next_model_action": REFRESH_NEXT_MODEL_ACTION,
    }
    contract = cast(dict[str, Any], redacted_runtime_copy(contract))
    state = build_v5_state(
        source.frontmatter,
        updated_at=timestamp,
    )
    state = cast(dict[str, Any], redacted_runtime_copy(state))
    plan_doc = PlanDocument(source.path, contract, current_schema_refresh_body(contract))
    target_bytes = dump_plan(plan_doc).encode("utf-8")
    target_sha256 = sha256_bytes(target_bytes)
    plan_id = str(source.frontmatter["plan_id"])
    event = {
        "schema_version": 1,
        "kind": "work-governance-plan-event",
        "plan_id": plan_id,
        "event_sequence": 1,
        "state_sequence": 0,
        "event": "contract.rebuilt_from_legacy_archive",
        "subject": f"plan:{plan_id}",
        "payload": {
            "from_schema_version": from_schema_version,
            "to_schema_version": CURRENT_PLAN_SCHEMA_VERSION,
            "migration_mode": "archive_legacy_and_rebuild_current_plan",
            "source_sha256": source_sha256,
            "archive_path": archive_relative,
            "archive_sha256": source_sha256,
            "state_mapping": "not_performed",
            "legacy_summary": summary,
            "legacy_state_migrated": False,
            "not_migrated": list(REFRESH_NOT_MIGRATED),
            "next_model_action": REFRESH_NEXT_MODEL_ACTION,
        },
        "recorded_at": timestamp,
    }
    event = cast(dict[str, Any], redacted_runtime_copy(event))
    state["event_sequence"] = 1
    event_bytes = canonical_event_payload_bytes(event)
    journal = {
        "schema_version": 1,
        "kind": "current-plan-schema-refresh",
        "migration_id": migration_id,
        "status": "prepared",
        "plan_id": plan_id,
        "from_schema_version": from_schema_version,
        "to_schema_version": CURRENT_PLAN_SCHEMA_VERSION,
        "migration_mode": "archive_legacy_and_rebuild_current_plan",
        "source_path": relative_project_path(root, source.path),
        "source_sha256": source_sha256,
        "archive_path": archive_relative,
        "archive_sha256": source_sha256,
        "target_sha256": target_sha256,
        "state_sha256": sha256_bytes(
            json.dumps(state, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        ),
        "events_sha256": sha256_bytes(event_bytes),
        "contract_revision": contract.get("contract_revision"),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    return journal, state, event, target_bytes


def write_v5_migration_staging(
    root: Path,
    paths: Mapping[str, Path],
    source_bytes: bytes,
    target_bytes: bytes,
    state: Mapping[str, Any],
    event_bytes: bytes,
) -> None:
    """Write the complete backup and staging set before the Plan replacement."""
    write_atomic_bytes(paths["backup"], source_bytes)
    write_atomic_bytes(paths["staging"], target_bytes)
    write_atomic(
        paths["state_staging"],
        json.dumps(state, indent=2, sort_keys=True) + "\n",
    )
    write_atomic_bytes(paths["events_staging"], event_bytes)


def finish_v5_migration(root: Path, journal_path: Path) -> None:
    """Complete one prepared current-schema refresh after an interruption."""
    journal = load_yaml_file(journal_path)
    migration_id = journal.get("migration_id")
    if not isinstance(migration_id, str):
        raise WorkctlError("SCHEMA_V5_MIGRATION_JOURNAL_INVALID")
    paths = v5_migration_paths(root, migration_id)
    if journal_path.resolve() != paths["journal"].resolve():
        raise WorkctlError("SCHEMA_V5_MIGRATION_JOURNAL_INVALID")
    required = {
        "schema_version",
        "kind",
        "migration_id",
        "status",
        "plan_id",
        "from_schema_version",
        "to_schema_version",
        "migration_mode",
        "source_path",
        "source_sha256",
        "archive_path",
        "archive_sha256",
        "target_sha256",
        "state_sha256",
        "events_sha256",
        "contract_revision",
        "created_at",
        "updated_at",
    }
    if (
        set(journal) != required
        or journal.get("schema_version") != 1
        or journal.get("kind") != "current-plan-schema-refresh"
        or journal.get("to_schema_version") != CURRENT_PLAN_SCHEMA_VERSION
        or journal.get("migration_mode") != "archive_legacy_and_rebuild_current_plan"
        or journal.get("status") not in {"prepared", "plan-replaced", "committed"}
    ):
        raise WorkctlError("SCHEMA_V5_MIGRATION_JOURNAL_INVALID")
    source = checked_project_path(root, str(journal["source_path"]))
    archive = checked_project_path(root, str(journal["archive_path"]))
    reject_symlink_components(root, archive)
    plan_id = str(journal["plan_id"])
    runtime = v5_runtime_dir(root, plan_id)
    state_target = runtime / "state.json"
    event_target = runtime / "events.jsonl"
    if (
        not paths["backup"].is_file()
        or sha256_file(paths["backup"]) != journal["source_sha256"]
        or not paths["staging"].is_file()
        or sha256_file(paths["staging"]) != journal["target_sha256"]
        or not paths["state_staging"].is_file()
        or sha256_file(paths["state_staging"]) != journal["state_sha256"]
        or not paths["events_staging"].is_file()
        or sha256_file(paths["events_staging"]) != journal["events_sha256"]
    ):
        raise WorkctlError("SCHEMA_V5_MIGRATION_STAGING_INVALID")
    if journal["archive_sha256"] != journal["source_sha256"]:
        raise WorkctlError("SCHEMA_V5_MIGRATION_JOURNAL_INVALID")
    if archive.exists() and (
        not archive.is_file() or sha256_file(archive) != journal["archive_sha256"]
    ):
        raise WorkctlError("SCHEMA_V5_MIGRATION_ARCHIVE_DRIFT")
    if journal["status"] == "committed":
        if not source.is_file() or sha256_file(source) != journal["target_sha256"]:
            raise WorkctlError("SCHEMA_V5_MIGRATION_COMMITTED_DRIFT")
        if not archive.is_file() or sha256_file(archive) != journal["archive_sha256"]:
            raise WorkctlError("SCHEMA_V5_MIGRATION_COMMITTED_DRIFT")
        return
    if not source.is_file():
        raise WorkctlError("SCHEMA_V5_MIGRATION_SOURCE_MISSING")
    current_sha256 = sha256_file(source)
    if current_sha256 == journal["source_sha256"]:
        write_atomic_bytes(archive, paths["backup"].read_bytes())
        write_atomic_bytes(state_target, paths["state_staging"].read_bytes())
        write_atomic_bytes(event_target, paths["events_staging"].read_bytes())
        write_atomic_bytes(source, paths["staging"].read_bytes())
    elif current_sha256 != journal["target_sha256"]:
        raise WorkctlError("SCHEMA_V5_MIGRATION_SOURCE_DRIFT")
    else:
        if not archive.is_file():
            write_atomic_bytes(archive, paths["backup"].read_bytes())
        write_atomic_bytes(state_target, paths["state_staging"].read_bytes())
        write_atomic_bytes(event_target, paths["events_staging"].read_bytes())
    journal["status"] = "plan-replaced"
    journal["updated_at"] = utc_now()
    write_atomic(journal_path, json.dumps(journal, indent=2, sort_keys=True) + "\n")
    if os.environ.get("WORKCTL_TEST_V5_MIGRATION_INTERRUPT") == "1":
        raise WorkctlError("SCHEMA_V5_TEST_INTERRUPTED_AFTER_REPLACE")
    errors = validate_plan(root, require_governed=False)
    if errors:
        raise WorkctlError("SCHEMA_V5_MIGRATION_APPLIED_BUT_INVALID: " + "; ".join(errors))
    journal["status"] = "committed"
    journal["updated_at"] = utc_now()
    write_atomic(journal_path, json.dumps(journal, indent=2, sort_keys=True) + "\n")


def cmd_migrate_apply(args: argparse.Namespace) -> None:
    """Archive an outdated active Plan and rebuild the current-schema contract."""
    root = project_root()
    if args.dry_run:
        require_current_schema_refresh_authority(root)
        source = load_plan(active_plan_path(root))
        if source.frontmatter.get("schema_version") == CURRENT_PLAN_SCHEMA_VERSION:
            print(
                json.dumps(
                    {
                        "status": "already_current",
                        "plan_id": source.frontmatter.get("plan_id"),
                        "schema_version": CURRENT_PLAN_SCHEMA_VERSION,
                    },
                    sort_keys=True,
                )
            )
            return
        contract = source.frontmatter.get("contract")
        current_revision = (
            contract.get("revision")
            if isinstance(contract, dict)
            else source.frontmatter.get("revision")
        )
        if (
            args.expected_contract_revision is not None
            and current_revision != args.expected_contract_revision
        ):
            raise WorkctlError(
                "CONTRACT_REVISION_MISMATCH: "
                f"expected {args.expected_contract_revision}, found {current_revision}"
            )
        preview_migration_id = next_v5_migration_id(root)
        journal, state, _event, target_bytes = prepare_v5_migration(
            root,
            source,
            migration_id=preview_migration_id,
        )
        target_sha256 = sha256_bytes(target_bytes)
        if isinstance(args.confirmation, str) and not args.confirmation.startswith("C-"):
            raise WorkctlError("INVALID_CONFIRMATION_ID")
        payload = migration_projection(source.frontmatter) if callable(migration_projection) else {}
        payload.update(
            {
                "status": "dry_run",
                "plan_id": source.frontmatter.get("plan_id"),
                "source_sha256": sha256_file(source.path),
                "archive_path": journal.get("archive_path"),
                "archive_sha256": journal.get("archive_sha256"),
                "target_sha256": target_sha256,
                "state_sequence": state.get("state_sequence"),
                "contract_revision": journal.get("contract_revision"),
                "confirmation_ref": None,
                "confirmation_deprecated": bool(args.confirmation),
                "confirmations_required": [],
                "writes": [],
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    with lock(root):
        require_current_schema_refresh_authority(root)
        source = load_plan(active_plan_path(root))
        if source.frontmatter.get("schema_version") == CURRENT_PLAN_SCHEMA_VERSION:
            print(
                json.dumps(
                    {
                        "status": "already_current",
                        "plan_id": source.frontmatter.get("plan_id"),
                        "schema_version": CURRENT_PLAN_SCHEMA_VERSION,
                    },
                    sort_keys=True,
                )
            )
            return
        if isinstance(args.confirmation, str) and not args.confirmation.startswith("C-"):
            raise WorkctlError("INVALID_CONFIRMATION_ID")
        expected = args.expected_contract_revision
        contract = source.frontmatter.get("contract")
        current_revision = (
            contract.get("revision")
            if isinstance(contract, dict)
            else source.frontmatter.get("revision")
        )
        if expected is None:
            raise WorkctlError("EXPECTED_CONTRACT_REVISION_REQUIRED")
        if current_revision != expected:
            raise WorkctlError(
                f"CONTRACT_REVISION_MISMATCH: expected {expected}, found {current_revision}"
            )
        migration_id = next_v5_migration_id(root)
        journal, state, event, target_bytes = prepare_v5_migration(
            root,
            source,
            migration_id=migration_id,
        )
        paths = v5_migration_paths(root, migration_id)
        source_bytes = source.path.read_bytes()
        event_bytes = canonical_event_payload_bytes(event)
        write_v5_migration_staging(root, paths, source_bytes, target_bytes, state, event_bytes)
        write_atomic(paths["journal"], json.dumps(journal, indent=2, sort_keys=True) + "\n")
        finish_v5_migration(root, paths["journal"])
    payload = {
        "status": "CURRENT_PLAN_SCHEMA_REFRESH_COMMITTED",
        "migration_id": migration_id,
        "plan_id": source.frontmatter["plan_id"],
        "archive_path": journal.get("archive_path"),
        "archive_sha256": journal.get("archive_sha256"),
        "state_reset": True,
        "legacy_state_migrated": False,
        "not_migrated": list(REFRESH_NOT_MIGRATED),
        "next_model_action": REFRESH_NEXT_MODEL_ACTION,
        "legacy_summary": legacy_plan_summary(source.frontmatter)
        if callable(legacy_plan_summary)
        else None,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def migration_rollback_entry(root: Path, journal_path: Path) -> dict[str, Any]:
    """Build a read-only rollback/recovery entry from one schema refresh journal."""
    journal = load_yaml_file(journal_path)
    migration_id = journal.get("migration_id")
    if not isinstance(migration_id, str):
        raise WorkctlError("SCHEMA_V5_MIGRATION_JOURNAL_INVALID")
    paths = v5_migration_paths(root, migration_id)
    backup_sha256 = sha256_file(paths["backup"]) if paths["backup"].is_file() else None
    staging_sha256 = sha256_file(paths["staging"]) if paths["staging"].is_file() else None
    archive_path = (
        checked_project_path(root, str(journal["archive_path"]))
        if isinstance(journal.get("archive_path"), str)
        else None
    )
    archive_sha256 = (
        sha256_file(archive_path)
        if isinstance(archive_path, Path) and archive_path.is_file()
        else None
    )
    return {
        "migration_id": migration_id,
        "status": journal.get("status"),
        "plan_id": journal.get("plan_id"),
        "from_schema_version": journal.get("from_schema_version"),
        "to_schema_version": journal.get("to_schema_version"),
        "migration_mode": journal.get("migration_mode"),
        "source_path": journal.get("source_path"),
        "source_sha256": journal.get("source_sha256"),
        "target_sha256": journal.get("target_sha256"),
        "archive_path": journal.get("archive_path"),
        "archive_sha256": archive_sha256,
        "expected_archive_sha256": journal.get("archive_sha256"),
        "backup_path": (
            relative_project_path(root, paths["backup"]) if paths["backup"].exists() else None
        ),
        "backup_sha256": backup_sha256,
        "staging_path": (
            relative_project_path(root, paths["staging"]) if paths["staging"].exists() else None
        ),
        "staging_sha256": staging_sha256,
        "recovery_command": f"migrate recover --migration-id {migration_id}",
        "rollback_boundary": (
            "No automatic rollback command is exposed. The legacy Plan is preserved "
            "in archive_path for audit and manually confirmed recovery planning."
        ),
    }


def migration_rollback_report_entry(root: Path, journal_path: Path) -> dict[str, Any]:
    """Build a doctor-safe schema refresh journal report entry."""
    try:
        return migration_rollback_entry(root, journal_path)
    except WorkctlError as exc:
        return {
            "journal_path": relative_project_path(root, journal_path),
            "status": "invalid",
            "error": str(exc),
            "recovery_command": None,
            "rollback_boundary": (
                "Invalid schema refresh journal was preserved for investigation; "
                "doctor does not delete schema refresh bundles."
            ),
        }


def cmd_migrate_rollback_info(args: argparse.Namespace) -> None:
    """Show schema refresh archive, backup, and recovery information."""
    root = project_root()
    base = v5_migration_base(root)
    if args.migration_id:
        journals = [v5_migration_paths(root, args.migration_id)["journal"]]
    elif base.is_dir():
        journals = sorted(base.glob("MIG-*/journal.json"))
    else:
        journals = []
    entries = [migration_rollback_entry(root, journal) for journal in journals if journal.is_file()]
    if args.migration_id and not entries:
        raise WorkctlError(f"SCHEMA_V5_MIGRATION_NOT_FOUND: {args.migration_id}")
    print(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "current-plan-schema-refresh-rollback-info",
                "write": False,
                "entries": entries,
            },
            indent=2,
            sort_keys=True,
        )
    )


def runtime_transactions_root(root: Path) -> Path:
    """Return the generic ignored transaction directory used by doctor."""
    path = governance_root(root) / "runtime" / "transactions"
    reject_symlink_components(root, path)
    return path


def stale_runtime_transaction_entries(
    root: Path,
    *,
    older_than_hours: int,
) -> list[dict[str, Any]]:
    """Return generic runtime transaction directories old enough for operator review."""
    transaction_root = runtime_transactions_root(root)
    if not transaction_root.exists():
        return []
    if transaction_root.is_symlink() or not transaction_root.is_dir():
        raise WorkctlError("RUNTIME_TRANSACTIONS_INVALID")
    threshold = time.time() - older_than_hours * 3600
    entries: list[dict[str, Any]] = []
    for path in sorted(transaction_root.iterdir()):
        if path.is_symlink() or not path.is_dir():
            entries.append(
                {
                    "path": relative_project_path(root, path),
                    "state": "invalid",
                    "reason": "transaction entry is not a plain directory",
                    "cleanable": False,
                }
            )
            continue
        modified_at = path.stat().st_mtime
        journal_paths = [path / "journal.json", path / "journal.yaml", path / "journal.yml"]
        has_journal = any(candidate.is_file() for candidate in journal_paths)
        stale = modified_at < threshold
        entries.append(
            {
                "path": relative_project_path(root, path),
                "state": "stale" if stale else "recent",
                "reason": "missing journal" if not has_journal else "journal present",
                "cleanable": bool(stale and not has_journal),
                "age_seconds": int(max(0.0, time.time() - modified_at)),
            }
        )
    return entries


def clean_stale_runtime_transactions(root: Path, entries: Sequence[Mapping[str, Any]]) -> list[str]:
    """Remove only stale generic transaction directories that have no journal."""
    cleaned: list[str] = []
    transaction_root = runtime_transactions_root(root).resolve()
    for entry in entries:
        if entry.get("cleanable") is not True:
            continue
        relative = entry.get("path")
        if not isinstance(relative, str):
            continue
        path = checked_project_path(root, relative)
        if path.is_symlink() or not path.is_dir() or path.parent.resolve() != transaction_root:
            raise WorkctlError("RUNTIME_TRANSACTION_CLEANUP_UNSAFE")
        if any((path / name).is_file() for name in ("journal.json", "journal.yaml", "journal.yml")):
            raise WorkctlError("RUNTIME_TRANSACTION_CLEANUP_JOURNAL_PRESENT")
        shutil.rmtree(path)
        cleaned.append(relative)
    return cleaned


def cmd_doctor(args: argparse.Namespace) -> None:
    """Inspect or safely clean local runtime transaction health."""
    root = project_root()
    if args.older_than_hours < 1:
        raise WorkctlError("DOCTOR_OLDER_THAN_HOURS_INVALID")
    stale_entries = stale_runtime_transaction_entries(
        root,
        older_than_hours=args.older_than_hours,
    )
    cleaned: list[str] = []
    if args.clean_stale_transactions:
        with lock(root):
            stale_entries = stale_runtime_transaction_entries(
                root,
                older_than_hours=args.older_than_hours,
            )
            cleaned = clean_stale_runtime_transactions(root, stale_entries)
            stale_entries = stale_runtime_transaction_entries(
                root,
                older_than_hours=args.older_than_hours,
            )
    report = inspect_authority(root)
    migration_base = v5_migration_base(root)
    migration_journals = (
        [
            migration_rollback_report_entry(root, path)
            for path in sorted(migration_base.glob("MIG-*/journal.json"))
        ]
        if migration_base.is_dir()
        else []
    )
    print(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "work-governance-doctor-report",
                "write": bool(args.clean_stale_transactions),
                "layout_state": inspect_layout(root).state,
                "authority_state": report.state,
                "blocking_reasons": report.blockers,
                "schema_v5_migrations": migration_journals,
                "runtime_transactions": stale_entries,
                "cleaned": cleaned,
                "next_action": (
                    "Run migrate recover for incomplete current-schema refresh journals "
                    "before ordinary work."
                    if any(entry.get("status") != "committed" for entry in migration_journals)
                    else "No current-schema refresh recovery action is required."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


def cmd_migrate_recover(args: argparse.Namespace) -> None:
    """Recover one named or the only incomplete current-schema refresh."""
    root = project_root()
    base = v5_migration_base(root)
    candidates = []
    for path in sorted(base.glob("MIG-*/journal.json")) if base.is_dir() else []:
        try:
            if load_yaml_file(path).get("status") != "committed":
                candidates.append(path)
        except WorkctlError:
            candidates.append(path)
    if args.migration_id:
        candidates = [v5_migration_paths(root, args.migration_id)["journal"]]
    if len(candidates) != 1:
        raise WorkctlError(
            "SCHEMA_V5_MIGRATION_RECOVERY_AMBIGUOUS"
            if candidates
            else "SCHEMA_V5_MIGRATION_RECOVERY_NOT_REQUIRED"
        )
    with lock(root):
        finish_v5_migration(root, candidates[0])
    print(f"CURRENT_PLAN_SCHEMA_REFRESH_RECOVERED {candidates[0].parent.name}")


def cmd_plan_validate(args: argparse.Namespace) -> None:
    root = project_root()
    errors = validate_plan(root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
    if args.evidence_manifest:
        doc = load_plan(active_plan_path(root))
        verify_evidence_manifest(
            root,
            args.evidence_manifest,
            plan_id=str(doc.frontmatter["plan_id"]),
            subject="plan-validation",
        )
    print("PLAN_VALID")


def require_matching_decision(
    frontmatter: dict[str, Any],
    confirmation_id: object,
    supplied_confirmation: str | None,
    allowed_decisions: set[str],
) -> dict[str, Any]:
    """Require a field transition to use its own resolved confirmation."""
    if not isinstance(confirmation_id, str) or confirmation_id != supplied_confirmation:
        raise WorkctlError("CONFIRMATION_BINDING_MISMATCH")
    item = confirmations(frontmatter).get(confirmation_id)
    if item is None or item.get("status") not in allowed_decisions or not item.get("ref"):
        raise WorkctlError(f"CONFIRMATION_REQUIRED: {confirmation_id}")
    return item


def exclusions_by_description(frontmatter: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index structured exclusions by their stable description."""
    scope = frontmatter.get("scope", {})
    values = scope.get("exclude", []) if isinstance(scope, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict) and isinstance(value.get("description"), str):
            result[value["description"]] = value
    return result


def require_slice_revision_confirmation(
    before: dict[str, Any],
    supplied_confirmation: str | None,
    allowed_decisions: set[str],
) -> dict[str, Any]:
    """Bind closeout-affecting structural changes to the current slice gate."""
    route = before.get("route", {})
    route_gate = route.get("confirmation_gate") if isinstance(route, dict) else None
    if isinstance(route_gate, str) and route_gate.startswith("C-"):
        return require_matching_decision(
            before,
            route_gate,
            supplied_confirmation,
            allowed_decisions,
        )
    if not isinstance(supplied_confirmation, str):
        raise WorkctlError("SLICE_REVISION_CONFIRMATION_REQUIRED")
    decision = confirmations(before).get(supplied_confirmation)
    if decision is None or not decision.get("ref"):
        raise WorkctlError(f"CONFIRMATION_REQUIRED: {supplied_confirmation}")
    if decision.get("status") in allowed_decisions:
        return decision
    activation = before.get("activation", {})
    declined_activation_resolution = (
        "declined" in allowed_decisions
        and isinstance(activation, dict)
        and activation.get("confirmation_id") == supplied_confirmation
        and decision.get("status") == "declined"
    )
    if not declined_activation_resolution:
        raise WorkctlError(f"CONFIRMATION_REQUIRED: {supplied_confirmation}")
    return decision


def validate_authorized_plan_patch(
    before: dict[str, Any],
    after: dict[str, Any],
    patch: dict[str, Any],
    supplied_confirmation: str | None,
) -> None:
    """Bind activation, exclusion, and terminal transitions to their own gate."""
    evidence_bound_change = any(
        before.get(field) != after.get(field)
        for field in ("obligations", "validations", "artifacts", "delivery")
    )
    slice_bound_change = any(
        before.get(field) != after.get(field) for field in ("route", "handoff")
    )
    old_scope = before.get("scope", {})
    new_scope = after.get("scope", {})
    if (
        isinstance(old_scope, dict)
        and isinstance(new_scope, dict)
        and old_scope.get("include") != new_scope.get("include")
    ):
        slice_bound_change = True
    old_activation = before.get("activation")
    new_activation = after.get("activation")
    if old_activation != new_activation and isinstance(new_activation, dict):
        old_status = old_activation.get("status") if isinstance(old_activation, dict) else None
        new_status = new_activation.get("status")
        activation_confirmation = new_activation.get("confirmation_id")
        old_activation_confirmation = (
            old_activation.get("confirmation_id") if isinstance(old_activation, dict) else None
        )
        if (
            isinstance(old_activation_confirmation, str)
            and activation_confirmation != old_activation_confirmation
        ):
            raise WorkctlError("ACTIVATION_CONFIRMATION_ID_IMMUTABLE")
        if new_status in {"in_progress", "active"} and old_status != new_status:
            require_matching_decision(
                after,
                activation_confirmation,
                supplied_confirmation,
                {"accepted"},
            )
        if new_status == "declined" and old_status != new_status:
            require_matching_decision(
                after,
                activation_confirmation,
                supplied_confirmation,
                {"declined"},
            )
        if new_status == "not_required" and old_status in BLOCKING_ACTIVATION_STATES:
            require_matching_decision(
                after,
                activation_confirmation,
                supplied_confirmation,
                {"accepted", "declined"},
            )
        sensitive_transition = (
            new_status in {"in_progress", "active", "declined", "not_required"}
            and old_status != new_status
        )
        current_changed = isinstance(old_activation, dict) and old_activation.get(
            "current_ref"
        ) != new_activation.get("current_ref")
        target_changed = isinstance(old_activation, dict) and old_activation.get(
            "target_ref"
        ) != new_activation.get("target_ref")
        evidence_changed = isinstance(old_activation, dict) and old_activation.get(
            "evidence"
        ) != new_activation.get("evidence")
        if target_changed:
            raise WorkctlError("ACTIVATION_TARGET_REQUIRES_DEDICATED_COMMAND")
        if isinstance(old_activation_confirmation, str) and (current_changed or evidence_changed):
            require_matching_decision(
                after,
                old_activation_confirmation,
                supplied_confirmation,
                {"accepted"},
            )
        elif not sensitive_transition:
            slice_bound_change = True

    old_exclusions = exclusions_by_description(before)
    new_exclusions = exclusions_by_description(after)
    for description, old_exclusion in old_exclusions.items():
        new_exclusion = new_exclusions.get(description)
        if new_exclusion is None:
            raise WorkctlError(f"SCOPE_EXCLUSION_REMOVAL_FORBIDDEN: {description}")
        if old_exclusion == new_exclusion:
            continue
        confirmation_id = old_exclusion.get("confirmation_id")
        if old_exclusion.get("disposition") != "pending_confirmation":
            raise WorkctlError(f"RESOLVED_EXCLUSION_IMMUTABLE: {description}")
        new_disposition = new_exclusion.get("disposition")
        if new_disposition == "pending_confirmation":
            raise WorkctlError(f"PENDING_EXCLUSION_MUTATION_FORBIDDEN: {description}")
        allowed_decisions = (
            {"accepted"}
            if new_disposition in {"completed", "transferred"}
            else {"accepted", "declined"}
        )
        decision = require_matching_decision(
            after,
            confirmation_id,
            supplied_confirmation,
            allowed_decisions,
        )
        if new_exclusion.get("resolution_ref") != decision.get("ref"):
            raise WorkctlError(f"EXCLUSION_RESOLUTION_REF_MISMATCH: {description}")
    for description in sorted(set(new_exclusions) - set(old_exclusions)):
        new_exclusion = new_exclusions[description]
        if new_exclusion.get("disposition") in BLOCKING_EXCLUSION_DISPOSITIONS:
            slice_bound_change = True
            continue
        decision = require_matching_decision(
            after,
            new_exclusion.get("confirmation_id"),
            supplied_confirmation,
            {"accepted", "declined"},
        )
        if new_exclusion.get("resolution_ref") != decision.get("ref"):
            raise WorkctlError(f"EXCLUSION_RESOLUTION_REF_MISMATCH: {description}")

    old_route = before.get("route")
    new_route = after.get("route")
    old_route_status = old_route.get("route_status") if isinstance(old_route, dict) else None
    new_route_status = new_route.get("route_status") if isinstance(new_route, dict) else None
    if old_route_status != "terminal" and new_route_status == "terminal":
        activation = after.get("activation", {})
        if isinstance(activation, dict) and activation.get("confirmation_id"):
            activation_status = activation.get("status")
            allowed_decisions = {"declined"} if activation_status == "declined" else {"accepted"}
            require_matching_decision(
                after,
                activation.get("confirmation_id"),
                supplied_confirmation,
                allowed_decisions,
            )

    if "confirmations" in patch:
        raise WorkctlError("CONFIRMATIONS_REQUIRE_DEDICATED_COMMAND")

    for field in ("obligations", "validations", "artifacts"):
        if field not in patch:
            continue
        old_entries = entries_by_id(before, field)
        new_entries = entries_by_id(after, field)
        removed = sorted(set(old_entries) - set(new_entries))
        if removed:
            raise WorkctlError(f"{field.upper()}_REMOVAL_FORBIDDEN: {removed[0]}")
        for entry_id, old_entry in old_entries.items():
            new_entry = new_entries[entry_id]
            if field == "artifacts" and new_entry != old_entry:
                raise WorkctlError(f"ARTIFACT_ENTRY_REQUIRES_DEDICATED_COMMAND: {entry_id}")
            if new_entry.get("status") != old_entry.get("status"):
                raise WorkctlError(f"{field.upper()}_STATUS_REQUIRES_DEDICATED_COMMAND: {entry_id}")
            terminal_status = "final" if field == "artifacts" else "verified"
            if old_entry.get("status") == terminal_status and new_entry != old_entry:
                raise WorkctlError(f"{field.upper()}_VERIFIED_ENTRY_IMMUTABLE: {entry_id}")
        for entry_id in sorted(set(new_entries) - set(old_entries)):
            if new_entries[entry_id].get("status") != "pending":
                raise WorkctlError(f"NEW_{field.upper()}_ENTRY_MUST_BE_PENDING: {entry_id}")

    if "delivery" in patch:
        old_delivery = before.get("delivery", {})
        new_delivery = after.get("delivery", {})
        if isinstance(old_delivery, dict) and isinstance(new_delivery, dict):
            old_delivery_status = old_delivery.get("status")
            new_delivery_status = new_delivery.get("status")
            if new_delivery_status == "complete" and old_delivery_status != "complete":
                raise WorkctlError("DELIVERY_COMPLETE_REQUIRES_DEDICATED_COMMAND")
            if old_delivery_status == "complete" and old_delivery != new_delivery:
                raise WorkctlError("COMPLETED_DELIVERY_IMMUTABLE")

    if "tasks" in patch:
        old_tasks = tasks_by_id(before)
        new_tasks = tasks_by_id(after)
        removed = sorted(set(old_tasks) - set(new_tasks))
        if removed:
            raise WorkctlError(f"TASK_REMOVAL_FORBIDDEN: {removed[0]}")
        for task_id, old_task in old_tasks.items():
            new_task = new_tasks[task_id]
            if new_task.get("status") != old_task.get("status"):
                raise WorkctlError(f"TASK_STATUS_REQUIRES_DEDICATED_COMMAND: {task_id}")
            if new_task.get("requires_confirmation") != old_task.get("requires_confirmation"):
                raise WorkctlError(f"TASK_CONFIRMATION_ID_IMMUTABLE: {task_id}")
            if any(
                new_task.get(field, []) != old_task.get(field, [])
                for field in ("depends_on", "completion_scope", "resolves_artifacts")
            ):
                slice_bound_change = True
        for task_id in sorted(set(new_tasks) - set(old_tasks)):
            if new_tasks[task_id].get("status") != "pending":
                raise WorkctlError(f"NEW_TASK_MUST_BE_PENDING: {task_id}")
            slice_bound_change = True

    if evidence_bound_change:
        require_slice_revision_confirmation(before, supplied_confirmation, {"accepted"})
    if slice_bound_change:
        require_slice_revision_confirmation(
            before,
            supplied_confirmation,
            {"accepted", "declined"},
        )


def cmd_plan_revise(args: argparse.Namespace) -> None:
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        if doc.frontmatter.get("schema_version") == 5:
            v5_recover_pending_event(root, doc.frontmatter)
            doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        if doc.frontmatter.get("schema_version") == 4:
            raise WorkctlError("PLAN_ADAPT_REQUIRED: use plan adapt --manifest")
        before_frontmatter = copy.deepcopy(doc.frontmatter)
        if args.status == "complete":
            raise WorkctlError("PLAN_COMPLETE_REQUIRES_CLOSEOUT_COMMAND")
        structural_change = bool(
            args.include
            or args.remove_exclude
            or args.patch_file
            or args.body_file
            or args.mode
            or args.status
        )
        if structural_change and not args.confirmation:
            raise WorkctlError("CONFIRMATION_REQUIRED: structural plan revision")
        if args.confirmation:
            confirmation = confirmations(doc.frontmatter).get(args.confirmation)
            if (
                confirmation is None
                or confirmation.get("status") not in {"accepted", "declined"}
                or not confirmation.get("ref")
            ):
                raise WorkctlError(f"CONFIRMATION_REQUIRED: {args.confirmation}")
            if confirmation.get("status") == "declined" and not args.patch_file:
                raise WorkctlError("DECLINED_CONFIRMATION_ONLY_AUTHORIZES_BOUND_STATE_RESOLUTION")
        if args.patch_file:
            patch = load_yaml_file(Path(args.patch_file))
            unsupported = sorted(set(patch) - PATCHABLE_PLAN_FIELDS)
            if unsupported:
                fields = ", ".join(unsupported)
                raise WorkctlError(f"UNSUPPORTED_PLAN_PATCH_FIELDS: {fields}")
            for field, value in patch.items():
                doc.frontmatter[field] = value
        scope = doc.frontmatter.setdefault("scope", {})
        if not isinstance(scope, dict):
            raise WorkctlError("INVALID_PLAN: scope must be a mapping")
        include = scope.setdefault("include", [])
        exclude = scope.setdefault("exclude", [])
        if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
            raise WorkctlError("INVALID_PLAN: scope.include must be a list of strings")
        if not isinstance(exclude, list):
            raise WorkctlError("INVALID_PLAN: scope.exclude must be a list")
        schema_version = doc.frontmatter.get("schema_version")
        if schema_version == 3:
            if not all(isinstance(item, dict) for item in exclude):
                raise WorkctlError("INVALID_PLAN: schema-v3 scope.exclude entries must be mappings")
        elif not all(isinstance(item, str) for item in exclude):
            raise WorkctlError("INVALID_PLAN: scope.exclude must be a list of strings")
        for item in args.include:
            if item not in include:
                include.append(item)
        for item in args.remove_exclude:
            matching_exclusion = next(
                (
                    exclusion
                    for exclusion in exclude
                    if exclusion == item
                    or (isinstance(exclusion, dict) and exclusion.get("description") == item)
                ),
                None,
            )
            if matching_exclusion is None:
                raise WorkctlError(f"SCOPE_EXCLUSION_NOT_FOUND: {item}")
            exclude.remove(matching_exclusion)
        if args.status:
            doc.frontmatter["status"] = args.status
        if args.mode:
            doc.frontmatter["mode"] = args.mode
        if args.body_file:
            body_path = Path(args.body_file)
            if not body_path.is_file():
                raise WorkctlError(f"MISSING_FILE: {body_path}")
            doc = PlanDocument(doc.path, doc.frontmatter, body_path.read_text(encoding="utf-8"))
        if structural_change:
            validate_authorized_plan_patch(
                before_frontmatter,
                doc.frontmatter,
                patch if args.patch_file else {},
                args.confirmation,
            )
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_REVISED revision={doc.frontmatter['revision']}")


def cmd_plan_confirmation_add(args: argparse.Namespace) -> None:
    """Create one explicit pending or already-authorized confirmation."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        if not args.confirmation_id.startswith("C-"):
            raise WorkctlError("INVALID_CONFIRMATION_ID")
        if not args.description:
            raise WorkctlError("INVALID_CONFIRMATION_DESCRIPTION")
        raw = doc.frontmatter.setdefault("confirmations", {})
        required = raw.setdefault("required", [])
        if not isinstance(required, list):
            raise WorkctlError("INVALID_PLAN: confirmations.required must be a list")
        if args.confirmation_id in confirmations(doc.frontmatter):
            raise WorkctlError(f"CONFIRMATION_EXISTS: {args.confirmation_id}")
        if doc.frontmatter.get("schema_version") in {4, 5} and args.status == "accepted":
            raise WorkctlError("CONFIRMATION_ACCEPTED_REQUIRES_PLAN_CONFIRM")
        item: dict[str, Any] = {
            "id": args.confirmation_id,
            "description": args.description,
            "status": args.status,
            "intervention": {
                "kind": args.intervention_kind,
                "blocks": list(dict.fromkeys(args.blocks)),
                "basis_ref": args.basis_ref,
            },
        }
        if args.basis_sha256 is not None:
            item["intervention"]["basis_sha256"] = args.basis_sha256
        if args.action_kind is not None:
            item["intervention"]["action_kind"] = args.action_kind
        errors = intervention_errors(doc.frontmatter, item)
        if errors:
            raise WorkctlError(f"INVALID_INTERVENTION_CONTRACT: {'; '.join(errors)}")
        if args.status == "accepted":
            if not isinstance(args.ref, str) or not valid_reference(args.ref):
                raise WorkctlError("CONFIRMATION_REF_REQUIRED")
            item["ref"] = args.ref
            item["accepted_at"] = utc_now()
        elif args.ref is not None:
            raise WorkctlError("PENDING_CONFIRMATION_CANNOT_HAVE_REF")
        required.append(item)
        bump_revision(
            doc.frontmatter,
            kind="confirmation-added",
            rationale=f"Create explicit confirmation {args.confirmation_id}.",
            confirmation_id=args.confirmation_id if args.status == "accepted" else None,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(
            f"CONFIRMATION_ADDED {args.confirmation_id} {args.status} "
            f"revision={doc.frontmatter['revision']}"
        )


def load_confirmation_classification_manifest(path: Path) -> dict[str, Any]:
    """Load one closed legacy-confirmation intervention classification."""
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("CONFIRMATION_CLASSIFICATION_MANIFEST_MISSING")
    manifest = load_yaml_file(path)
    required = {
        "schema_version",
        "kind",
        "plan_id",
        "confirmation_id",
        "intervention",
    }
    optional = {"supersedes_basis_sha256"}
    if not required.issubset(manifest) or set(manifest) - required - optional:
        raise WorkctlError("CONFIRMATION_CLASSIFICATION_MANIFEST_INVALID")
    intervention = manifest.get("intervention")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "confirmation-intervention-classification"
        or not isinstance(manifest.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(manifest["plan_id"])) is None
        or not isinstance(manifest.get("confirmation_id"), str)
        or not str(manifest["confirmation_id"]).startswith("C-")
        or not isinstance(intervention, dict)
        or set(intervention) - {"kind", "blocks", "basis_ref", "basis_sha256", "action_kind"}
        or (
            "supersedes_basis_sha256" in manifest
            and (
                not isinstance(manifest["supersedes_basis_sha256"], str)
                or SHA256_RE.fullmatch(str(manifest["supersedes_basis_sha256"])) is None
            )
        )
    ):
        raise WorkctlError("CONFIRMATION_CLASSIFICATION_MANIFEST_INVALID")
    return manifest


def cmd_plan_confirmation_classify(args: argparse.Namespace) -> None:
    """Classify a legacy gate or rebind one undecided external basis exactly."""
    root = project_root()
    manifest = load_confirmation_classification_manifest(Path(args.manifest).resolve())
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        require_expected_revision(doc.frontmatter, args.expected_revision)
        if manifest["plan_id"] != doc.frontmatter.get("plan_id"):
            raise WorkctlError("CONFIRMATION_CLASSIFICATION_PLAN_MISMATCH")
        confirmation_id = str(manifest["confirmation_id"])
        target = confirmations(doc.frontmatter).get(confirmation_id)
        if target is None:
            raise WorkctlError(f"UNKNOWN_CONFIRMATION: {confirmation_id}")
        status = target.get("status")
        existing = target.get("intervention")
        replacement = cast(dict[str, Any], manifest["intervention"])
        candidate = dict(target)
        candidate["intervention"] = replacement
        errors = intervention_errors(doc.frontmatter, candidate)
        if errors:
            raise WorkctlError(f"INVALID_INTERVENTION_CONTRACT: {'; '.join(errors)}")
        rebound = False
        if status == "pending":
            if existing is not None and not intervention_placeholder(target):
                supersedes_basis_sha256 = manifest.get("supersedes_basis_sha256")
                if (
                    existing.get("kind") != "external_authority"
                    or replacement.get("kind") != existing.get("kind")
                    or replacement.get("action_kind") != existing.get("action_kind")
                    or replacement.get("blocks") != existing.get("blocks")
                    or not isinstance(supersedes_basis_sha256, str)
                    or supersedes_basis_sha256 != existing.get("basis_sha256")
                ):
                    raise WorkctlError("CONFIRMATION_STRICT_REBIND_MISMATCH")
                new_basis_sha256 = replacement.get("basis_sha256")
                if (
                    not isinstance(new_basis_sha256, str)
                    or new_basis_sha256 == supersedes_basis_sha256
                    or replacement.get("basis_ref") == existing.get("basis_ref")
                ):
                    raise WorkctlError("CONFIRMATION_STRICT_REBIND_NO_CHANGE")
                rebound = True
        elif status == "accepted" and intervention_placeholder(target):
            if replacement.get("kind") != "external_authority" or target.get(
                "evidence_sha256"
            ) != replacement.get("basis_sha256"):
                raise WorkctlError("ACCEPTED_PLACEHOLDER_BASIS_MISMATCH")
        else:
            raise WorkctlError("CONFIRMATION_CLASSIFICATION_PENDING_REQUIRED")
        target["intervention"] = replacement
        bump_revision(
            doc.frontmatter,
            kind="confirmation-classified",
            rationale=f"Classify intervention contract for {confirmation_id}.",
            confirmation_id=confirmation_id if status == "accepted" else None,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        event = "CONFIRMATION_REBOUND" if rebound else "CONFIRMATION_CLASSIFIED"
        print(f"{event} {confirmation_id} revision={doc.frontmatter['revision']}")


def cmd_plan_confirm(args: argparse.Namespace) -> None:
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        if doc.frontmatter.get("schema_version") == 5:
            v5_recover_pending_event(root, doc.frontmatter)
            doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        raw = doc.frontmatter.setdefault("confirmations", {})
        required = raw.setdefault("required", [])
        target = None
        for item in required:
            if isinstance(item, dict) and item.get("id") == args.confirmation_id:
                target = item
                break
        if target is None:
            raise WorkctlError(f"UNKNOWN_CONFIRMATION: {args.confirmation_id}")
        if target.get("status") != "pending":
            raise WorkctlError(
                f"INVALID_CONFIRMATION_TRANSITION: {args.confirmation_id} "
                f"{target.get('status')} -> {args.decision}"
            )
        intervention = target.get("intervention")
        schema_version = doc.frontmatter.get("schema_version")
        if schema_version in {4, 5}:
            if not isinstance(intervention, dict):
                raise WorkctlError("CONFIRMATION_CLASSIFICATION_REQUIRED")
            if intervention_placeholder(target):
                raise WorkctlError("CONFIRMATION_BASIS_CLASSIFICATION_REQUIRED")
            blocks = intervention.get("blocks", [])
            if not isinstance(blocks, list):
                raise WorkctlError("INVALID_INTERVENTION_CONTRACT")
            if schema_version == 4:
                require_current_intake(
                    root,
                    doc.frontmatter,
                    turn_receipt_sha256=args.turn_receipt_sha256,
                    expected_intake_sha256=args.expected_intake_sha256,
                    targets=blocks,
                )
            require_confirmation_turn_ref(
                root,
                ref=args.ref,
                turn_receipt_sha256=args.turn_receipt_sha256,
            )
            basis_sha256 = intervention.get("basis_sha256")
            if basis_sha256 is not None and args.evidence_sha256 != basis_sha256:
                raise WorkctlError("CONFIRMATION_EVIDENCE_BASIS_MISMATCH")
            if args.decision == "accepted" and not confirmation_accepts_degraded_review(
                doc.frontmatter,
                target,
            ):
                for current_target in current_advancement_targets(doc.frontmatter):
                    if current_target in blocks:
                        require_independent_target(root, doc.frontmatter, current_target)
        if schema_version in {3, 4, 5} and not valid_reference(args.ref):
            raise WorkctlError("INVALID_CONFIRMATION_REF")
        target["status"] = args.decision
        target["ref"] = args.ref
        if args.decision == "accepted":
            target["accepted_at"] = utc_now()
        else:
            target["decided_at"] = utc_now()
        if args.evidence_sha256:
            if SHA256_RE.fullmatch(args.evidence_sha256) is None:
                raise WorkctlError("INVALID_CONFIRMATION_EVIDENCE_SHA256")
            target["evidence_sha256"] = args.evidence_sha256
        bump_revision(
            doc.frontmatter,
            kind="confirmation-decided",
            rationale=f"Record the explicit decision for {args.confirmation_id}.",
            confirmation_id=args.confirmation_id,
        )
        require_valid_candidate(doc)
        if schema_version == 5:
            v5_persist_contract_transition(
                root,
                doc,
                event="confirmation.decided",
                subject=f"confirmation:{args.confirmation_id}",
                payload={
                    "decision": args.decision,
                    "ref": args.ref,
                    "evidence_sha256": args.evidence_sha256,
                },
            )
        else:
            write_atomic(doc.path, dump_plan(doc))
        print(
            f"CONFIRMATION_DECIDED {args.confirmation_id} {args.decision} "
            f"revision={doc.frontmatter['revision']}"
        )


def load_independent_review_manifest(path: Path) -> dict[str, Any]:
    """Load one closed independent-review recording manifest."""
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("INDEPENDENT_REVIEW_MANIFEST_MISSING")
    manifest = load_yaml_file(path)
    required = {
        "schema_version",
        "kind",
        "plan_id",
        "mode",
        "state",
        "implementation_context_ref",
        "review_context_ref",
        "reviewed_contract",
        "reviewed_artifacts",
        "findings",
        "evidence_manifest",
        "isolation_attestation",
        "bootstrap_evidence",
    }
    optional = {"risk_acceptance_confirmation_id"}
    if (
        set(manifest) - optional != required
        or manifest.get("schema_version") != 1
        or manifest.get("kind") != "independent-review"
        or not isinstance(manifest.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(manifest["plan_id"])) is None
        or manifest.get("mode") not in INDEPENDENT_REVIEW_MODES
        or manifest.get("state") not in {"verified", "degraded"}
        or not valid_reference(manifest.get("implementation_context_ref"))
        or not valid_reference(manifest.get("review_context_ref"))
        or not isinstance(manifest.get("evidence_manifest"), str)
        or (
            manifest.get("isolation_attestation") is not None
            and not isinstance(manifest.get("isolation_attestation"), str)
        )
    ):
        raise WorkctlError("INDEPENDENT_REVIEW_MANIFEST_INVALID")
    reviewed_contract = manifest.get("reviewed_contract")
    if (
        not isinstance(reviewed_contract, dict)
        or set(reviewed_contract) != {"ref", "sha256"}
        or not valid_reference(reviewed_contract.get("ref"))
        or not isinstance(reviewed_contract.get("sha256"), str)
        or SHA256_RE.fullmatch(str(reviewed_contract["sha256"])) is None
    ):
        raise WorkctlError("INDEPENDENT_REVIEW_CONTRACT_INVALID")
    reviewed_artifacts = manifest.get("reviewed_artifacts")
    if not isinstance(reviewed_artifacts, list) or not reviewed_artifacts:
        raise WorkctlError("INDEPENDENT_REVIEW_ARTIFACTS_REQUIRED")
    for artifact in reviewed_artifacts:
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"ref", "sha256"}
            or not valid_reference(artifact.get("ref"))
            or not isinstance(artifact.get("sha256"), str)
            or SHA256_RE.fullmatch(str(artifact["sha256"])) is None
        ):
            raise WorkctlError("INDEPENDENT_REVIEW_ARTIFACT_INVALID")
    findings = manifest.get("findings")
    if not isinstance(findings, list):
        raise WorkctlError("INDEPENDENT_REVIEW_FINDINGS_INVALID")
    finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) not in (
            {"id", "severity", "status", "description"},
            {"id", "severity", "status", "description", "evidence_ref"},
        ):
            raise WorkctlError("INDEPENDENT_REVIEW_FINDING_INVALID")
        finding_id = finding.get("id")
        if (
            not isinstance(finding_id, str)
            or not finding_id
            or finding_id in finding_ids
            or finding.get("severity") not in INDEPENDENT_FINDING_SEVERITIES
            or finding.get("status") not in INDEPENDENT_FINDING_STATES
            or not isinstance(finding.get("description"), str)
            or not finding.get("description")
            or (
                finding.get("evidence_ref") is not None
                and not valid_reference(finding.get("evidence_ref"))
            )
        ):
            raise WorkctlError("INDEPENDENT_REVIEW_FINDING_INVALID")
        finding_ids.add(finding_id)
    bootstrap_evidence = manifest.get("bootstrap_evidence")
    if not isinstance(bootstrap_evidence, list):
        raise WorkctlError("INDEPENDENT_REVIEW_BOOTSTRAP_EVIDENCE_INVALID")
    for item in bootstrap_evidence:
        if (
            not isinstance(item, dict)
            or set(item) != {"target_ref", "evidence_ref", "evidence_sha256"}
            or not valid_target_ref(item.get("target_ref"))
            or not valid_reference(item.get("evidence_ref"))
            or not isinstance(item.get("evidence_sha256"), str)
            or SHA256_RE.fullmatch(str(item["evidence_sha256"])) is None
        ):
            raise WorkctlError("INDEPENDENT_REVIEW_BOOTSTRAP_EVIDENCE_INVALID")
    risk_confirmation = manifest.get("risk_acceptance_confirmation_id")
    if risk_confirmation is not None and (
        not isinstance(risk_confirmation, str) or not risk_confirmation.startswith("C-")
    ):
        raise WorkctlError("INDEPENDENT_REVIEW_RISK_CONFIRMATION_INVALID")
    if manifest["state"] == "degraded" and risk_confirmation is None:
        raise WorkctlError("DEGRADED_REVIEW_RISK_CONFIRMATION_ID_REQUIRED")
    if manifest["state"] == "verified" and risk_confirmation is not None:
        raise WorkctlError("VERIFIED_REVIEW_CANNOT_CARRY_RISK_CONFIRMATION")
    return manifest


def bootstrap_entry_evidence(
    frontmatter: Mapping[str, Any],
    target: str,
) -> tuple[object, object]:
    """Project the evidence pointer currently carried by one bootstrap-mapped entry."""
    kind, entry_id = target.split(":", 1)
    field = {
        "task": "tasks",
        "obligation": "obligations",
        "validation": "validations",
        "artifact": "artifacts",
    }.get(kind)
    values = frontmatter.get(field, []) if field else []
    entry = (
        next(
            (item for item in values if isinstance(item, dict) and item.get("id") == entry_id),
            None,
        )
        if isinstance(values, list)
        else None
    )
    if not isinstance(entry, dict):
        return None, None
    if field != "tasks":
        return entry.get("evidence_ref"), entry.get("evidence_sha256")
    note = entry.get("note")
    match = (
        re.search(r"evidence:(?P<path>\S+/(?P<sha>[0-9a-f]{64})\.json)", note)
        if isinstance(note, str)
        else None
    )
    if match is None:
        return None, None
    return f"evidence:{match.group('path')}", match.group("sha")


def cmd_plan_independent_review_record(args: argparse.Namespace) -> None:
    """Record one isolated review; this is the sole bootstrap-blocked migration write."""
    root = project_root()
    manifest = load_independent_review_manifest(Path(args.manifest).resolve())
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=current_advancement_targets(doc.frontmatter),
        )
        if manifest["plan_id"] != doc.frontmatter.get("plan_id"):
            raise WorkctlError("INDEPENDENT_REVIEW_PLAN_MISMATCH")
        contract = doc.frontmatter.get("independent_validation")
        if not isinstance(contract, dict) or contract.get("required") is not True:
            raise WorkctlError("INDEPENDENT_REVIEW_NOT_REQUIRED")
        implementation_context = str(manifest["implementation_context_ref"])
        review_context = str(manifest["review_context_ref"])
        if manifest["state"] == "verified" and implementation_context == review_context:
            raise WorkctlError("INDEPENDENT_REVIEW_CONTEXT_NOT_ISOLATED")
        if manifest["state"] == "verified":
            raise WorkctlError("INDEPENDENT_REVIEW_TRUSTED_ATTESTATION_UNAVAILABLE")
        configured_implementation = contract.get("implementation_context_ref")
        if configured_implementation not in {
            implementation_context,
            "context:pending-implementation",
        }:
            raise WorkctlError("INDEPENDENT_REVIEW_IMPLEMENTATION_CONTEXT_MISMATCH")
        reviews = contract.get("reviews", [])
        review = (
            next(
                (
                    item
                    for item in reviews
                    if isinstance(item, dict) and item.get("mode") == manifest["mode"]
                ),
                None,
            )
            if isinstance(reviews, list)
            else None
        )
        if review is None:
            raise WorkctlError("INDEPENDENT_REVIEW_MODE_NOT_CONFIGURED")
        if review.get("state") != "pending":
            raise WorkctlError("INDEPENDENT_REVIEW_ALREADY_RECORDED")
        if manifest["state"] == "verified" and unresolved_blocking_findings(manifest):
            raise WorkctlError("INDEPENDENT_REVIEW_BLOCKING_FINDINGS_OPEN")
        evidence_ref, evidence_sha256 = verify_evidence_manifest(
            root,
            str(manifest["evidence_manifest"]),
            plan_id=str(doc.frontmatter["plan_id"]),
            subject=f"independent-review:{manifest['mode']}",
        )
        evidence_path = checked_project_path(root, evidence_ref.removeprefix("evidence:"))
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence_payload.get("producer_ref") != review_context:
            raise WorkctlError("INDEPENDENT_REVIEW_PRODUCER_CONTEXT_MISMATCH")
        expected_bindings = {
            (
                str(cast(dict[str, Any], manifest["reviewed_contract"])["ref"]),
                str(cast(dict[str, Any], manifest["reviewed_contract"])["sha256"]),
            ),
            *{
                (str(item["ref"]), str(item["sha256"]))
                for item in cast(list[dict[str, Any]], manifest["reviewed_artifacts"])
            },
        }
        evidence_bindings = {
            (str(item["ref"]), str(item["sha256"]))
            for item in evidence_payload.get("items", [])
            if isinstance(item, dict)
        }
        if not expected_bindings.issubset(evidence_bindings):
            raise WorkctlError("INDEPENDENT_REVIEW_EVIDENCE_BINDING_MISMATCH")
        bootstrap = review.get("bootstrap_release")
        supplied_bootstrap = cast(list[dict[str, Any]], manifest["bootstrap_evidence"])
        if isinstance(bootstrap, dict):
            activation = doc.frontmatter.get("activation", {})
            if not isinstance(activation, dict) or activation.get("current_ref") != bootstrap.get(
                "controller_build"
            ):
                raise WorkctlError("INDEPENDENT_REVIEW_BOOTSTRAP_CONTROLLER_MISMATCH")
            expected_targets = bootstrap.get("evidence_mapping", [])
            if not isinstance(expected_targets, list) or {
                item["target_ref"] for item in supplied_bootstrap
            } != set(expected_targets):
                raise WorkctlError("INDEPENDENT_REVIEW_BOOTSTRAP_MAPPING_MISMATCH")
            for item in supplied_bootstrap:
                target = str(item["target_ref"])
                if not bootstrap_mapping_verified(root, doc.frontmatter, target):
                    raise WorkctlError("INDEPENDENT_REVIEW_BOOTSTRAP_EVIDENCE_INVALID")
                current_ref, current_sha = bootstrap_entry_evidence(doc.frontmatter, target)
                if item["evidence_ref"] != current_ref or item["evidence_sha256"] != current_sha:
                    raise WorkctlError("INDEPENDENT_REVIEW_BOOTSTRAP_EVIDENCE_MISMATCH")
        elif supplied_bootstrap:
            raise WorkctlError("INDEPENDENT_REVIEW_BOOTSTRAP_EVIDENCE_UNEXPECTED")
        risk_confirmation = manifest.get("risk_acceptance_confirmation_id")
        if isinstance(risk_confirmation, str):
            existing_risk = confirmations(doc.frontmatter).get(risk_confirmation)
            if existing_risk is not None:
                raise WorkctlError("DEGRADED_REVIEW_PREEXISTING_RISK_FORBIDDEN")
        raw_isolation = manifest["isolation_attestation"]
        if raw_isolation is not None:
            raise WorkctlError("DEGRADED_REVIEW_CANNOT_CLAIM_ISOLATION")
        contract["implementation_context_ref"] = implementation_context
        review["state"] = manifest["state"]
        review["review_context_ref"] = review_context
        reviewed_contract = cast(dict[str, Any], manifest["reviewed_contract"])
        review["reviewed_contract_ref"] = reviewed_contract["ref"]
        review["reviewed_contract_sha256"] = reviewed_contract["sha256"]
        review["reviewed_artifacts"] = manifest["reviewed_artifacts"]
        review["findings"] = manifest["findings"]
        review["evidence_ref"] = evidence_ref
        review["evidence_sha256"] = evidence_sha256
        if risk_confirmation is not None:
            review["risk_acceptance_confirmation_id"] = risk_confirmation
        review["recorded_at"] = utc_now()
        contract["state"] = aggregate_independent_review_state(contract)
        bump_revision(
            doc.frontmatter,
            kind="independent-review-recorded",
            rationale=f"Record independent {manifest['mode']} review.",
            evidence_manifest=evidence_ref,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(
            f"INDEPENDENT_REVIEW_RECORDED {manifest['mode']} {manifest['state']} "
            f"revision={doc.frontmatter['revision']}"
        )


def load_plan_change_manifest(
    path: Path,
    *,
    kind: str,
    allowed_change_fields: set[str],
) -> dict[str, Any]:
    """Validate the common closed envelope for evidence-backed Plan changes."""
    manifest = load_yaml_file(path)
    if set(manifest) != {
        "schema_version",
        "kind",
        "plan_id",
        "expected_revision",
        "confirmation_id",
        "rationale",
        "evidence_manifest",
        "changes",
    }:
        raise WorkctlError("INVALID_PLAN_CHANGE_MANIFEST_FIELDS")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != kind:
        raise WorkctlError("INVALID_PLAN_CHANGE_MANIFEST_SCHEMA")
    if (
        not isinstance(manifest.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(manifest["plan_id"])) is None
        or type(manifest.get("expected_revision")) is not int
        or not isinstance(manifest.get("confirmation_id"), str)
        or not str(manifest["confirmation_id"]).startswith("C-")
        or not isinstance(manifest.get("rationale"), str)
        or not manifest.get("rationale")
        or not isinstance(manifest.get("evidence_manifest"), str)
    ):
        raise WorkctlError("INVALID_PLAN_CHANGE_MANIFEST")
    changes = manifest.get("changes")
    if (
        not isinstance(changes, dict)
        or not changes
        or not set(changes).issubset(allowed_change_fields)
    ):
        raise WorkctlError("INVALID_PLAN_CHANGE_FIELDS")
    return manifest


def cmd_plan_adapt(args: argparse.Namespace) -> None:
    """Adapt only the execution path while preserving the confirmed contract."""
    if getattr(args, "manifest", None) is None:
        cmd_plan_adapt_intent(args)
        return
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    manifest = load_plan_change_manifest(
        manifest_path,
        kind="plan-adaptation",
        allowed_change_fields={"tasks", "validations", "route", "handoff"},
    )
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        if manifest["plan_id"] != doc.frontmatter.get("plan_id"):
            raise WorkctlError("PLAN_ADAPTATION_PLAN_MISMATCH")
        require_expected_revision(doc.frontmatter, int(manifest["expected_revision"]))
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=["route"],
        )
        confirmation_id = str(manifest["confirmation_id"])
        require_matching_decision(
            doc.frontmatter,
            confirmation_id,
            confirmation_id,
            {"accepted"},
        )
        next_revision = int(doc.frontmatter["revision"]) + 1
        evidence_ref, _ = verify_evidence_manifest(
            root,
            str(manifest["evidence_manifest"]),
            plan_id=str(doc.frontmatter["plan_id"]),
            subject=f"adaptation:{next_revision}",
        )
        before = copy.deepcopy(doc.frontmatter)
        changes = cast(dict[str, Any], manifest["changes"])
        for field, value in changes.items():
            doc.frontmatter[field] = value
        validate_authorized_plan_patch(
            before,
            doc.frontmatter,
            changes,
            confirmation_id,
        )
        if before.get("goal") != doc.frontmatter.get("goal") or before.get(
            "contract"
        ) != doc.frontmatter.get("contract"):
            raise WorkctlError("PLAN_ADAPTATION_CONTRACT_IMMUTABLE")
        bump_revision(
            doc.frontmatter,
            kind="adaptation",
            rationale=str(manifest["rationale"]),
            confirmation_id=confirmation_id,
            evidence_manifest=evidence_ref,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_ADAPTED revision={doc.frontmatter['revision']}")


def cmd_plan_contract_revise(args: argparse.Namespace) -> None:
    """Revise goal/contract only through an accepted, evidence-bound decision."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    manifest = load_plan_change_manifest(
        manifest_path,
        kind="plan-contract-revision",
        allowed_change_fields={"goal", "scope", "obligations"},
    )
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        if manifest["plan_id"] != doc.frontmatter.get("plan_id"):
            raise WorkctlError("PLAN_CONTRACT_REVISION_PLAN_MISMATCH")
        require_expected_revision(doc.frontmatter, int(manifest["expected_revision"]))
        confirmation_id = str(manifest["confirmation_id"])
        decision = require_matching_decision(
            doc.frontmatter,
            confirmation_id,
            confirmation_id,
            {"accepted"},
        )
        contract = doc.frontmatter.get("contract")
        if not isinstance(contract, dict) or type(contract.get("revision")) is not int:
            raise WorkctlError("INVALID_PLAN_CONTRACT")
        next_contract_revision = int(contract["revision"]) + 1
        evidence_ref, _ = verify_evidence_manifest(
            root,
            str(manifest["evidence_manifest"]),
            plan_id=str(doc.frontmatter["plan_id"]),
            subject=f"contract-revision:{next_contract_revision}",
        )
        before = copy.deepcopy(doc.frontmatter)
        changes = cast(dict[str, Any], manifest["changes"])
        for field, value in changes.items():
            doc.frontmatter[field] = value
        contract["revision"] = next_contract_revision
        contract["confirmation_id"] = confirmation_id
        contract["confirmed_ref"] = decision["ref"]
        validate_authorized_plan_patch(
            before,
            doc.frontmatter,
            changes,
            confirmation_id,
        )
        bump_revision(
            doc.frontmatter,
            kind="contract-revision",
            rationale=str(manifest["rationale"]),
            confirmation_id=confirmation_id,
            evidence_manifest=evidence_ref,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(
            f"PLAN_CONTRACT_REVISED contract_revision={next_contract_revision} "
            f"revision={doc.frontmatter['revision']}"
        )


def require_target_exists(frontmatter: Mapping[str, Any], target: str) -> None:
    """Require a non-route target to name an existing Plan entry."""
    if target in {"route", "delivery", "activation"}:
        return
    kind, entry_id = target.split(":", 1)
    field = {
        "task": "tasks",
        "obligation": "obligations",
        "validation": "validations",
        "artifact": "artifacts",
    }[kind]
    values = frontmatter.get(field, [])
    if not isinstance(values, list) or not any(
        isinstance(item, dict) and item.get("id") == entry_id for item in values
    ):
        raise WorkctlError(f"UNKNOWN_TARGET_REF: {target}")


def canonical_evidence_pointer(
    root: Path,
    frontmatter: Mapping[str, Any],
    evidence_ref: object,
    evidence_sha256: object,
    *,
    expected_subject: str | None = None,
) -> bool:
    """Return whether a Plan pointer names exact canonical evidence bytes."""
    if (
        not isinstance(evidence_ref, str)
        or not evidence_ref.startswith("evidence:")
        or not isinstance(evidence_sha256, str)
        or SHA256_RE.fullmatch(evidence_sha256) is None
    ):
        return False
    relative = evidence_ref.removeprefix("evidence:")
    if Path(relative).stem != evidence_sha256:
        return False
    try:
        path = checked_project_path(root, relative)
    except WorkctlError:
        return False
    if path.is_symlink() or not path.is_file():
        return False
    content = path.read_bytes()
    if sha256_bytes(content) != evidence_sha256:
        return False
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("plan_id") == frontmatter.get("plan_id")
        and (expected_subject is None or payload.get("subject") == expected_subject)
        and canonical_evidence_bytes(payload) == content
    )


def bootstrap_mapping_verified(
    root: Path,
    frontmatter: Mapping[str, Any],
    target: str,
) -> bool:
    """Check the canonical V/T evidence mapping used only by the migration bridge."""
    kind, entry_id = target.split(":", 1)
    field = {
        "task": "tasks",
        "obligation": "obligations",
        "validation": "validations",
        "artifact": "artifacts",
    }.get(kind)
    if field is None:
        return False
    values = frontmatter.get(field, [])
    entry = (
        next(
            (item for item in values if isinstance(item, dict) and item.get("id") == entry_id),
            None,
        )
        if isinstance(values, list)
        else None
    )
    if entry is None:
        return False
    expected_state = "final" if field == "artifacts" else "verified"
    if entry.get("status") != expected_state:
        return False
    if field != "tasks":
        return canonical_evidence_pointer(
            root,
            frontmatter,
            entry.get("evidence_ref"),
            entry.get("evidence_sha256"),
            expected_subject=target,
        )
    note = entry.get("note")
    if not isinstance(note, str):
        return False
    match = re.search(
        r"evidence:(?P<path>\S+/(?P<sha>[0-9a-f]{64})\.json)",
        note,
    )
    return bool(
        match
        and canonical_evidence_pointer(
            root,
            frontmatter,
            f"evidence:{match.group('path')}",
            match.group("sha"),
            expected_subject=target,
        )
    )


def unresolved_blocking_findings(review: Mapping[str, Any]) -> list[str]:
    """Return unresolved blocker/high finding IDs from one review."""
    findings = review.get("findings", [])
    if not isinstance(findings, list):
        return ["invalid"]
    return [
        str(finding.get("id", "unknown"))
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("severity") in INDEPENDENT_BLOCKING_SEVERITIES
        and finding.get("status") == "open"
    ]


def recorded_review_integrity_valid(
    root: Path,
    frontmatter: Mapping[str, Any],
    review: Mapping[str, Any],
) -> bool:
    """Revalidate canonical review and isolation bytes before releasing a target."""
    mode = review.get("mode")
    state = review.get("state")
    evidence_ref = review.get("evidence_ref")
    evidence_sha256 = review.get("evidence_sha256")
    review_context_ref = review.get("review_context_ref")
    if (
        mode not in INDEPENDENT_REVIEW_MODES
        or state not in {"verified", "degraded"}
        or not valid_reference(review_context_ref)
        or not canonical_evidence_pointer(
            root,
            frontmatter,
            evidence_ref,
            evidence_sha256,
            expected_subject=f"independent-review:{mode}",
        )
    ):
        return False
    if state == "verified":
        return False
    try:
        evidence_path = checked_project_path(
            root,
            str(evidence_ref).removeprefix("evidence:"),
        )
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (WorkctlError, json.JSONDecodeError, OSError):
        return False
    if (
        not isinstance(evidence_payload, dict)
        or evidence_payload.get("producer_ref") != review_context_ref
    ):
        return False
    contract_ref = review.get("reviewed_contract_ref")
    contract_sha256 = review.get("reviewed_contract_sha256")
    reviewed_artifacts = review.get("reviewed_artifacts")
    contract = frontmatter.get("independent_validation")
    if (
        not valid_reference(contract_ref)
        or not isinstance(contract_sha256, str)
        or SHA256_RE.fullmatch(contract_sha256) is None
        or not isinstance(reviewed_artifacts, list)
        or not reviewed_artifacts
        or any(
            not isinstance(item, dict)
            or set(item) != {"ref", "sha256"}
            or not valid_reference(item.get("ref"))
            or not isinstance(item.get("sha256"), str)
            or SHA256_RE.fullmatch(str(item.get("sha256"))) is None
            for item in reviewed_artifacts
        )
        or not isinstance(contract, dict)
        or not valid_reference(contract.get("implementation_context_ref"))
    ):
        return False
    expected_bindings = {
        (str(contract_ref), contract_sha256),
        *{
            (str(item.get("ref")), str(item.get("sha256")))
            for item in reviewed_artifacts
            if isinstance(item, dict)
        },
    }
    evidence_bindings = {
        (str(item.get("ref")), str(item.get("sha256")))
        for item in evidence_payload.get("items", [])
        if isinstance(item, dict)
    }
    if not expected_bindings.issubset(evidence_bindings):
        return False
    return bool(
        review.get("isolation_attestation_ref") is None
        and review.get("isolation_attestation_sha256") is None
    )


def risk_confirmation_matches_review(
    confirmation: Mapping[str, Any],
    review: Mapping[str, Any],
) -> bool:
    """Return whether one accepted authority exactly covers one degraded review."""
    intervention = confirmation.get("intervention")
    review_blocks = review.get("blocks", [])
    confirmation_blocks = intervention.get("blocks", []) if isinstance(intervention, dict) else []
    return bool(
        confirmation.get("status") == "accepted"
        and confirmation.get("ref")
        and isinstance(intervention, dict)
        and intervention.get("kind") == "external_authority"
        and intervention.get("basis_ref") == review.get("evidence_ref")
        and intervention.get("basis_sha256") == review.get("evidence_sha256")
        and isinstance(review_blocks, list)
        and isinstance(confirmation_blocks, list)
        and set(review_blocks).issubset(confirmation_blocks)
    )


def confirmation_accepts_degraded_review(
    frontmatter: Mapping[str, Any],
    confirmation: Mapping[str, Any],
) -> bool:
    """Allow the exact risk decision itself while its reviewed targets are blocked."""
    contract = frontmatter.get("independent_validation")
    reviews = contract.get("reviews", []) if isinstance(contract, dict) else []
    return bool(
        isinstance(reviews, list)
        and any(
            isinstance(review, dict)
            and review.get("state") == "degraded"
            and review.get("risk_acceptance_confirmation_id") == confirmation.get("id")
            and risk_confirmation_matches_review(
                {**confirmation, "status": "accepted", "ref": "pending-current-turn"},
                review,
            )
            for review in reviews
        )
    )


def review_has_risk_acceptance(
    frontmatter: Mapping[str, Any],
    review: Mapping[str, Any],
) -> bool:
    """Require a separate exact external-authority decision for degraded evidence."""
    raw_confirmations = confirmations(cast(dict[str, Any], frontmatter))
    confirmation_id = review.get("risk_acceptance_confirmation_id")
    if not isinstance(confirmation_id, str):
        return False
    confirmation = raw_confirmations.get(confirmation_id)
    return bool(
        isinstance(confirmation, dict) and risk_confirmation_matches_review(confirmation, review)
    )


def pending_plan_challenge_is_advisory(
    frontmatter: Mapping[str, Any],
    review: Mapping[str, Any],
    target: str,
) -> bool:
    """Release only an ordinary local task from an unfinished Plan challenge."""
    if review.get("mode") != "plan_challenge" or review.get("state") != "pending":
        return False
    if not target.startswith("task:"):
        return False
    task_id = target.removeprefix("task:")
    raw_tasks = frontmatter.get("tasks", [])
    task = (
        next(
            (item for item in raw_tasks if isinstance(item, dict) and item.get("id") == task_id),
            None,
        )
        if isinstance(raw_tasks, list)
        else None
    )
    return bool(
        isinstance(task, dict)
        and task.get("completion_scope", "local") == "local"
        and not task.get("requires_confirmation")
    )


def review_releases_target(
    root: Path,
    frontmatter: Mapping[str, Any],
    review: Mapping[str, Any],
    target: str,
) -> bool:
    """Return whether one strict review or exact bootstrap bridge releases a target."""
    if unresolved_blocking_findings(review):
        return False
    state = review.get("state")
    if pending_plan_challenge_is_advisory(frontmatter, review, target):
        return True
    if state in {"verified", "degraded"} and not recorded_review_integrity_valid(
        root,
        frontmatter,
        review,
    ):
        return False
    if state == "verified":
        return True
    if state == "degraded" and review_has_risk_acceptance(frontmatter, review):
        return True
    bootstrap = review.get("bootstrap_release")
    activation = frontmatter.get("activation", {})
    if not isinstance(bootstrap, dict) or not isinstance(activation, dict):
        return False
    if activation.get("current_ref") != bootstrap.get("controller_build"):
        return False
    releases = bootstrap.get("releases", [])
    mapping = bootstrap.get("evidence_mapping", [])
    return bool(
        isinstance(releases, list)
        and target in releases
        and isinstance(mapping, list)
        and mapping
        and all(
            isinstance(mapped_target, str)
            and bootstrap_mapping_verified(root, frontmatter, mapped_target)
            for mapped_target in mapping
        )
    )


def independent_review_blockers(
    root: Path,
    frontmatter: Mapping[str, Any],
    target: str,
) -> list[str]:
    """Return review modes that still block one exact advancement target."""
    contract = frontmatter.get("independent_validation")
    if not isinstance(contract, dict) or contract.get("required") is not True:
        return []
    reviews = contract.get("reviews", [])
    if not isinstance(reviews, list):
        return ["invalid"]
    blockers: list[str] = []
    for review in reviews:
        if not isinstance(review, dict):
            blockers.append("invalid")
            continue
        blocks = review.get("blocks", [])
        if (
            isinstance(blocks, list)
            and target in blocks
            and not review_releases_target(root, frontmatter, review, target)
        ):
            blockers.append(str(review.get("mode", "invalid")))
    return blockers


def require_independent_target(
    root: Path,
    frontmatter: Mapping[str, Any],
    target: str,
) -> None:
    """Fail closed when a required independent review still blocks a target."""
    blockers = independent_review_blockers(root, frontmatter, target)
    if blockers:
        raise WorkctlError(f"INDEPENDENT_REVIEW_REQUIRED: {target} blocked by {','.join(blockers)}")


def aggregate_independent_review_state(contract: Mapping[str, Any]) -> str:
    """Derive the Plan-level state from the required review records."""
    reviews = contract.get("reviews", [])
    states = (
        {review.get("state") for review in reviews if isinstance(review, dict)}
        if isinstance(reviews, list)
        else set()
    )
    if states and states.issubset({"verified"}):
        return "verified"
    if states and states.issubset({"verified", "degraded"}) and "degraded" in states:
        return "degraded"
    return "pending"


def require_new_plan_reviews_pending(frontmatter: Mapping[str, Any]) -> None:
    """Reject pre-certified reviews when admitting or switching to new authority."""
    contract = frontmatter.get("independent_validation")
    if not isinstance(contract, dict):
        return
    reviews = contract.get("reviews", [])
    if (
        contract.get("state") != "pending"
        or not isinstance(reviews, list)
        or any(
            not isinstance(review, dict) or review.get("state") != "pending" for review in reviews
        )
    ):
        raise WorkctlError("NEW_PLAN_INDEPENDENT_REVIEW_MUST_BE_PENDING")


def validate_unknown_classification(
    frontmatter: Mapping[str, Any],
    *,
    owner: str,
    impact: str,
    blocks: list[str],
    expected_evidence: str,
) -> None:
    """Validate strict unknown metadata and its referenced targets."""
    if owner not in UNKNOWN_OWNERS:
        raise WorkctlError("UNKNOWN_OWNER_INVALID")
    if impact not in UNKNOWN_IMPACTS:
        raise WorkctlError("UNKNOWN_IMPACT_INVALID")
    if not expected_evidence.strip():
        raise WorkctlError("UNKNOWN_EXPECTED_EVIDENCE_REQUIRED")
    if any(not valid_target_ref(target) for target in blocks):
        raise WorkctlError("UNKNOWN_BLOCK_TARGET_INVALID")
    if len(blocks) != len(set(blocks)):
        raise WorkctlError("UNKNOWN_BLOCK_TARGET_DUPLICATE")
    if (impact == "blocking") != bool(blocks):
        raise WorkctlError("UNKNOWN_IMPACT_BLOCKS_CONFLICT")
    for target in blocks:
        require_target_exists(frontmatter, target)


def project_unknown_to_tasks(
    frontmatter: dict[str, Any],
    *,
    unknown_id: str,
    blocks: list[str],
) -> None:
    """Synchronize the compatibility task.unknowns projection from blocks."""
    raw_tasks = frontmatter.get("tasks", [])
    if not isinstance(raw_tasks, list):
        raise WorkctlError("INVALID_PLAN: tasks must be a list")
    exact_task_targets = {
        target.removeprefix("task:") for target in blocks if target.startswith("task:")
    }
    for task in raw_tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        linked = task.get("unknowns")
        if not isinstance(linked, list) or not all(isinstance(item, str) for item in linked):
            raise WorkctlError(f"INVALID_PLAN: {task.get('id')} unknowns must be ids")
        retained = [item for item in linked if item != unknown_id]
        if task["id"] in exact_task_targets:
            retained.append(unknown_id)
        task["unknowns"] = retained


def cmd_plan_unknown_add(args: argparse.Namespace) -> None:
    """Add one explicit unknown without changing the confirmed goal."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        require_expected_revision(doc.frontmatter, args.expected_revision)
        if UNKNOWN_ID_RE.fullmatch(args.unknown_id) is None:
            raise WorkctlError("INVALID_UNKNOWN_ID")
        unknowns = doc.frontmatter.setdefault("unknowns", [])
        if not isinstance(unknowns, list):
            raise WorkctlError("INVALID_PLAN: unknowns must be a list")
        if any(isinstance(item, dict) and item.get("id") == args.unknown_id for item in unknowns):
            raise WorkctlError(f"UNKNOWN_EXISTS: {args.unknown_id}")
        blocks = list(dict.fromkeys(args.blocks))
        validate_unknown_classification(
            doc.frontmatter,
            owner=args.owner,
            impact=args.impact,
            blocks=blocks,
            expected_evidence=args.expected_evidence,
        )
        unknowns.append(
            {
                "id": args.unknown_id,
                "question": args.question,
                "status": "open",
                "owner": args.owner,
                "impact": args.impact,
                "blocks": blocks,
                "expected_evidence": args.expected_evidence,
            }
        )
        project_unknown_to_tasks(
            doc.frontmatter,
            unknown_id=args.unknown_id,
            blocks=blocks,
        )
        bump_revision(
            doc.frontmatter,
            kind="unknown-added",
            rationale=f"Track explicit unknown {args.unknown_id}.",
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_UNKNOWN_ADDED {args.unknown_id} revision={doc.frontmatter['revision']}")


def load_unknown_classification_manifest(path: Path) -> dict[str, Any]:
    """Load one exact legacy-unknown classification manifest."""
    if path.is_symlink() or not path.is_file():
        raise WorkctlError("UNKNOWN_CLASSIFICATION_MANIFEST_MISSING")
    manifest = load_yaml_file(path)
    required = {
        "schema_version",
        "kind",
        "plan_id",
        "unknown_id",
        "owner",
        "impact",
        "blocks",
        "expected_evidence",
    }
    if (
        set(manifest) != required
        or manifest.get("schema_version") != 1
        or manifest.get("kind") != "plan-unknown-classification"
        or not isinstance(manifest.get("plan_id"), str)
        or PLAN_ID_RE.fullmatch(str(manifest["plan_id"])) is None
        or not isinstance(manifest.get("unknown_id"), str)
        or UNKNOWN_ID_RE.fullmatch(str(manifest["unknown_id"])) is None
        or manifest.get("owner") not in UNKNOWN_OWNERS
        or manifest.get("impact") not in UNKNOWN_IMPACTS
        or not isinstance(manifest.get("blocks"), list)
        or not all(isinstance(item, str) for item in manifest["blocks"])
        or not isinstance(manifest.get("expected_evidence"), str)
        or not manifest.get("expected_evidence")
    ):
        raise WorkctlError("UNKNOWN_CLASSIFICATION_MANIFEST_INVALID")
    return manifest


def cmd_plan_unknown_classify(args: argparse.Namespace) -> None:
    """Repair one legacy unknown into the strict target-blocker contract."""
    root = project_root()
    manifest = load_unknown_classification_manifest(Path(args.manifest).resolve())
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        require_expected_revision(doc.frontmatter, args.expected_revision)
        if manifest["plan_id"] != doc.frontmatter.get("plan_id"):
            raise WorkctlError("UNKNOWN_CLASSIFICATION_PLAN_MISMATCH")
        unknown_id = str(manifest["unknown_id"])
        target = unknowns_by_id(doc.frontmatter).get(unknown_id)
        if target is None:
            raise WorkctlError(f"UNKNOWN_UNKNOWN: {unknown_id}")
        blocks = cast(list[str], manifest["blocks"])
        validate_unknown_classification(
            doc.frontmatter,
            owner=str(manifest["owner"]),
            impact=str(manifest["impact"]),
            blocks=blocks,
            expected_evidence=str(manifest["expected_evidence"]),
        )
        target["owner"] = manifest["owner"]
        target["impact"] = manifest["impact"]
        target["blocks"] = blocks
        target["expected_evidence"] = manifest["expected_evidence"]
        project_unknown_to_tasks(
            doc.frontmatter,
            unknown_id=unknown_id,
            blocks=blocks,
        )
        bump_revision(
            doc.frontmatter,
            kind="unknown-classified",
            rationale=f"Classify legacy unknown {unknown_id}.",
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_UNKNOWN_CLASSIFIED {unknown_id} revision={doc.frontmatter['revision']}")


def cmd_plan_unknown_resolve(args: argparse.Namespace) -> None:
    """Resolve one unknown only with immutable evidence."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_plan_contract_ready(doc.frontmatter)
        require_expected_revision(doc.frontmatter, args.expected_revision)
        unknowns = doc.frontmatter.get("unknowns")
        target = (
            next(
                (
                    item
                    for item in unknowns
                    if isinstance(item, dict) and item.get("id") == args.unknown_id
                ),
                None,
            )
            if isinstance(unknowns, list)
            else None
        )
        if target is None:
            raise WorkctlError(f"UNKNOWN_UNKNOWN: {args.unknown_id}")
        if target.get("status") != "open":
            raise WorkctlError(f"INVALID_UNKNOWN_TRANSITION: {args.unknown_id}")
        evidence_ref, _ = verify_evidence_manifest(
            root,
            args.evidence_manifest,
            plan_id=str(doc.frontmatter["plan_id"]),
            subject=f"unknown:{args.unknown_id}",
        )
        target["status"] = "resolved"
        target["resolution"] = args.resolution
        target["evidence_manifest"] = evidence_ref
        target["resolved_at"] = utc_now()
        bump_revision(
            doc.frontmatter,
            kind="unknown-resolved",
            rationale=f"Resolve explicit unknown {args.unknown_id}.",
            evidence_manifest=evidence_ref,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_UNKNOWN_RESOLVED {args.unknown_id} revision={doc.frontmatter['revision']}")


def require_evidence_args(evidence_ref: str, evidence_sha256: str) -> None:
    """Validate immutable evidence pointers used by dedicated transitions."""
    if not valid_reference(evidence_ref):
        raise WorkctlError("INVALID_EVIDENCE_REF")
    if SHA256_RE.fullmatch(evidence_sha256) is None:
        raise WorkctlError("INVALID_EVIDENCE_SHA256")


def canonical_evidence_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the only accepted immutable evidence record encoding."""
    if MODULE_CANONICAL_EVIDENCE_BYTES is None:
        raise WorkctlError("EVIDENCE_MODULE_UNAVAILABLE: canonical_evidence_bytes")
    return MODULE_CANONICAL_EVIDENCE_BYTES(payload)


def validate_evidence_payload(
    payload: Mapping[str, Any],
    *,
    expected_plan_id: str,
    expected_subject: str | None = None,
) -> None:
    """Validate bounded evidence metadata without accepting process output blobs."""
    if module_evidence is None:
        raise WorkctlError("EVIDENCE_MODULE_UNAVAILABLE: validate_evidence_payload")
    try:
        module_evidence.validate_evidence_payload(
            payload,
            expected_plan_id=expected_plan_id,
            expected_subject=expected_subject,
            valid_reference=valid_reference,
            sha256_pattern=SHA256_RE,
            max_items=EVIDENCE_MANIFEST_MAX_ITEMS,
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def evidence_relative_path(plan_id: str, digest: str) -> str:
    """Return the canonical versioned evidence path for one Plan."""
    return plan_relative_path(f".evidence/{plan_id}/{digest}.json")


def parse_evidence_content(content: bytes) -> dict[str, Any]:
    """Parse one bounded JSON or YAML evidence object from trusted input bytes."""
    try:
        if MODULE_PARSE_EVIDENCE_BYTES is None:
            raise WorkctlError("EVIDENCE_MODULE_UNAVAILABLE: parse_evidence_bytes")
        return cast(
            dict[str, Any],
            MODULE_PARSE_EVIDENCE_BYTES(content, EVIDENCE_MANIFEST_MAX_BYTES),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def evidence_payload_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    """Read an optional evidence object from a manifest path or standard input."""
    if getattr(args, "evidence_stdin", False) or getattr(args, "stdin", False):
        return parse_evidence_content(sys.stdin.buffer.read())
    input_path_value = getattr(args, "evidence_manifest", None)
    if not isinstance(input_path_value, str):
        input_path_value = getattr(args, "manifest", None)
    if not isinstance(input_path_value, str):
        return None
    input_path = Path(input_path_value)
    if input_path.is_symlink() or not input_path.is_file():
        raise WorkctlError("EVIDENCE_INPUT_MISSING")
    return parse_evidence_content(input_path.read_bytes())


def capture_module_call(name: str) -> Any:
    """Return one extracted evidence capture helper or fail with a stable code."""
    if module_evidence is None:
        raise WorkctlError(f"EVIDENCE_CAPTURE_MODULE_UNAVAILABLE: {name}")
    try:
        return getattr(module_evidence, name)
    except AttributeError as exc:
        raise WorkctlError(f"EVIDENCE_CAPTURE_MODULE_UNAVAILABLE: {name}") from exc


def evidence_capture_root(root: Path) -> Path:
    """Return the project-local direct evidence store root."""
    try:
        return cast(
            Path,
            capture_module_call("evidence_capture_root")(
                root,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def evidence_capture_blob_path(root: Path, digest: str) -> Path:
    """Return the content-addressed blob path for direct evidence capture."""
    try:
        return cast(
            Path,
            capture_module_call("evidence_capture_blob_path")(
                root,
                digest,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def evidence_capture_record_path(root: Path, digest: str) -> Path:
    """Return the content-addressed metadata record path for direct evidence capture."""
    try:
        helper = capture_module_call("evidence_capture_record_path")
        return cast(Path, helper(root, digest, governance_dir_name=GOVERNANCE_DIR_NAME))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def evidence_capture_ledger_path(root: Path) -> Path:
    """Return the append-only direct evidence ledger path."""
    try:
        helper = capture_module_call("evidence_capture_ledger_path")
        return cast(Path, helper(root, governance_dir_name=GOVERNANCE_DIR_NAME))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def normalize_capture_task(task_value: str | None) -> str | None:
    """Normalize an optional task reference to a task ID."""
    try:
        return cast(str | None, capture_module_call("normalize_capture_task")(task_value))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def redact_capture_text(value: str) -> str:
    """Apply conservative text redaction before evidence bytes are persisted."""
    try:
        return cast(str, capture_module_call("redact_capture_text")(value))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def redact_capture_bytes(content: bytes) -> tuple[bytes, bool]:
    """Return persistable evidence bytes and whether the source was textual."""
    try:
        return cast(tuple[bytes, bool], capture_module_call("redact_capture_bytes")(content))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def read_capture_source(root: Path, args: argparse.Namespace) -> tuple[bytes, str, str | None]:
    """Read direct evidence bytes from stdin or a project-local explicit file."""
    try:
        return cast(
            tuple[bytes, str, str | None],
            capture_module_call("read_capture_source")(root, args),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def capture_record_id(created_at: str) -> str:
    """Create a collision-resistant evidence ID from time and a random suffix."""
    try:
        return cast(str, capture_module_call("capture_record_id")(created_at))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def load_capture_records(root: Path) -> list[dict[str, Any]]:
    """Load the direct evidence ledger for idempotency checks."""
    try:
        return cast(
            list[dict[str, Any]],
            capture_module_call("load_capture_records")(
                root,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def append_capture_record(root: Path, record: Mapping[str, Any]) -> None:
    """Append one canonical direct evidence record to the ledger."""
    try:
        capture_module_call("append_capture_record")(
            root,
            record,
            governance_dir_name=GOVERNANCE_DIR_NAME,
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def verify_capture_record_file(root: Path, record: Mapping[str, Any]) -> tuple[str, str]:
    """Verify the content-addressed metadata file named by a ledger record."""
    try:
        return cast(
            tuple[str, str],
            capture_module_call("verify_capture_record_file")(
                root,
                record,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def find_capture_record_by_idempotency_key(
    root: Path,
    *,
    plan_id: str,
    key: str,
) -> dict[str, Any] | None:
    """Return the existing record for one idempotency key, if any."""
    try:
        return cast(
            dict[str, Any] | None,
            capture_module_call("find_capture_record_by_idempotency_key")(
                root,
                plan_id=plan_id,
                key=key,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def validate_capture_args(args: argparse.Namespace) -> str | None:
    """Validate direct evidence capture arguments and return the normalized task."""
    try:
        return cast(str | None, capture_module_call("validate_capture_args")(args))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def persist_capture_blob(root: Path, content: bytes) -> tuple[str, str, int]:
    """Persist redacted direct evidence bytes as a content-addressed blob."""
    try:
        return cast(
            tuple[str, str, int],
            capture_module_call("persist_capture_blob")(
                root,
                content,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def persist_capture_metadata(root: Path, record: Mapping[str, Any]) -> tuple[str, str]:
    """Persist direct evidence metadata as a content-addressed record."""
    try:
        return cast(
            tuple[str, str],
            capture_module_call("persist_capture_metadata")(
                root,
                record,
                governance_dir_name=GOVERNANCE_DIR_NAME,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def preflight_v5_capture_binding(
    root: Path,
    doc: PlanDocument,
    *,
    task_id: str,
    expected_state_sequence: int | None,
) -> None:
    """Validate v5 task binding guards before durable evidence is written."""
    v5_recover_pending_event(root, doc.frontmatter)
    state = load_v5_state(root, doc.frontmatter)
    if expected_state_sequence is not None and state["state_sequence"] != expected_state_sequence:
        raise WorkctlError(
            "STATE_SEQUENCE_MISMATCH: "
            f"expected {expected_state_sequence}, found {state['state_sequence']}"
        )
    task_for(v5_runtime_frontmatter(root, doc.frontmatter, state), task_id)
    state_tasks = state.get("tasks")
    if not isinstance(state_tasks, dict):
        raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    if not isinstance(state_tasks.get(task_id), dict):
        raise WorkctlError("SCHEMA_V5_STATE_TASK_MISSING")


def bind_v5_capture_record(
    root: Path,
    doc: PlanDocument,
    *,
    task_id: str,
    record_ref: str,
    record_id: str,
    record_sha256: str,
    blob_ref: str,
    expected_state_sequence: int | None,
) -> int:
    """Bind direct evidence to a v5 task runtime state without touching the contract."""
    v5_recover_pending_event(root, doc.frontmatter)
    state = load_v5_state(root, doc.frontmatter)
    if expected_state_sequence is not None and state["state_sequence"] != expected_state_sequence:
        raise WorkctlError(
            "STATE_SEQUENCE_MISMATCH: "
            f"expected {expected_state_sequence}, found {state['state_sequence']}"
        )
    task_for(v5_runtime_frontmatter(root, doc.frontmatter, state), task_id)
    state_tasks = state.get("tasks")
    if not isinstance(state_tasks, dict):
        raise WorkctlError("SCHEMA_V5_STATE_INVALID")
    state_task = state_tasks.get(task_id)
    if not isinstance(state_task, dict):
        raise WorkctlError("SCHEMA_V5_STATE_TASK_MISSING")
    evidence_refs = state_task.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not all(
        isinstance(item, str) for item in evidence_refs
    ):
        evidence_refs = []
        state_task["evidence_refs"] = evidence_refs
    if record_ref in evidence_refs:
        return int(state["state_sequence"])
    evidence_sha256s = state_task.get("evidence_sha256s")
    if not isinstance(evidence_sha256s, list) or not all(
        isinstance(item, str) and SHA256_RE.fullmatch(item) is not None for item in evidence_sha256s
    ):
        evidence_sha256s = []
        state_task["evidence_sha256s"] = evidence_sha256s
    evidence_refs.append(record_ref)
    evidence_sha256s.append(record_sha256)
    v5_persist_state_transition(
        root,
        doc.frontmatter,
        state,
        event="evidence.captured",
        subject=f"task:{task_id}",
        payload={
            "evidence_record_id": record_id,
            "evidence_ref": record_ref,
            "evidence_sha256": record_sha256,
            "blob_ref": blob_ref,
        },
    )
    return int(state["state_sequence"])


def cmd_evidence_capture(args: argparse.Namespace) -> None:
    """Directly capture command output or a project file into the evidence store."""
    root = project_root()
    task_id = validate_capture_args(args)
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        plan_id = str(doc.frontmatter["plan_id"])
        if task_id is not None:
            if doc.frontmatter.get("schema_version") == 5:
                preflight_v5_capture_binding(
                    root,
                    doc,
                    task_id=task_id,
                    expected_state_sequence=args.expected_state_sequence,
                )
            else:
                task_for(doc.frontmatter, task_id)
        raw_content, source_type, source_ref = read_capture_source(root, args)
        redacted_content, text_source = redact_capture_bytes(raw_content)
        source_digest = sha256_bytes(redacted_content)
        idempotency_key = getattr(args, "idempotency_key", None)
        existing = (
            find_capture_record_by_idempotency_key(
                root,
                plan_id=plan_id,
                key=idempotency_key,
            )
            if isinstance(idempotency_key, str)
            else None
        )
        state_sequence: int | None = None
        if existing is not None:
            if (
                existing.get("source_digest") != source_digest
                or existing.get("evidence_kind") != args.kind
                or existing.get("summary") != redact_capture_text(args.summary.strip())
                or existing.get("redaction_policy") != args.redaction_policy
                or existing.get("task_ref") != (f"task:{task_id}" if task_id is not None else None)
            ):
                raise WorkctlError("EVIDENCE_CAPTURE_IDEMPOTENCY_CONFLICT")
            existing_record = existing
            record_ref, record_sha256 = verify_capture_record_file(root, existing_record)
            if doc.frontmatter.get("schema_version") == 5 and task_id is not None:
                state_sequence = bind_v5_capture_record(
                    root,
                    doc,
                    task_id=task_id,
                    record_ref=record_ref,
                    record_id=str(existing_record["id"]),
                    record_sha256=record_sha256,
                    blob_ref=str(existing_record["blob_ref"]),
                    expected_state_sequence=args.expected_state_sequence,
                )
            output = {
                "id": existing_record["id"],
                "evidence_ref": record_ref,
                "evidence_sha256": record_sha256,
                "blob_ref": existing_record["blob_ref"],
                "source_digest": existing_record["source_digest"],
                "plan_id": plan_id,
                "idempotent": True,
            }
            if state_sequence is not None:
                output["state_sequence"] = state_sequence
            print(json.dumps(output, sort_keys=True))
            return
        blob_ref, blob_sha256, blob_size = persist_capture_blob(root, redacted_content)
        created_at = utc_now()
        record_id = capture_record_id(created_at)
        if EVIDENCE_CAPTURE_ID_RE.fullmatch(record_id) is None:
            raise WorkctlError("EVIDENCE_CAPTURE_ID_INVALID")
        task_ref = f"task:{task_id}" if task_id is not None else None
        new_record: dict[str, Any] = {
            "schema_version": 1,
            "kind": "work-governance-evidence-record",
            "id": record_id,
            "plan_id": plan_id,
            "goal_ref": f"plan:{plan_id}",
            "task_ref": task_ref,
            "evidence_kind": args.kind,
            "summary": redact_capture_text(args.summary.strip()),
            "source_type": source_type,
            "source_ref": source_ref,
            "source_digest": source_digest,
            "source_size": len(redacted_content),
            "text_source": text_source,
            "redaction_policy": args.redaction_policy,
            "blob_ref": blob_ref,
            "blob_sha256": blob_sha256,
            "blob_size": blob_size,
            "validator": "workctl:evidence.capture",
            "result": "captured",
            "created_at": created_at,
        }
        if isinstance(idempotency_key, str):
            new_record["idempotency_key"] = idempotency_key
        record_ref, record_sha256 = persist_capture_metadata(root, new_record)
        ledger_record = {**new_record, "evidence_ref": record_ref, "evidence_sha256": record_sha256}
        append_capture_record(root, ledger_record)
        if doc.frontmatter.get("schema_version") == 5 and task_id is not None:
            state_sequence = bind_v5_capture_record(
                root,
                doc,
                task_id=task_id,
                record_ref=record_ref,
                record_id=record_id,
                record_sha256=record_sha256,
                blob_ref=blob_ref,
                expected_state_sequence=args.expected_state_sequence,
            )
        output = {
            "id": record_id,
            "evidence_ref": record_ref,
            "evidence_sha256": record_sha256,
            "blob_ref": blob_ref,
            "source_digest": source_digest,
            "plan_id": plan_id,
            "idempotent": False,
        }
        if state_sequence is not None:
            output["state_sequence"] = state_sequence
        print(json.dumps(output, sort_keys=True))


def record_evidence_payload(
    root: Path,
    *,
    plan_id: str,
    payload: Mapping[str, Any],
    expected_subject: str | None = None,
) -> tuple[str, str]:
    """Validate and atomically install one canonical evidence payload."""
    validate_evidence_payload(
        payload,
        expected_plan_id=plan_id,
        expected_subject=expected_subject,
    )
    canonical = canonical_evidence_bytes(payload)
    digest = sha256_bytes(canonical)
    relative = evidence_relative_path(plan_id, digest)
    target = checked_project_path(root, relative)
    if target.exists():
        if target.is_symlink() or target.read_bytes() != canonical:
            raise WorkctlError("EVIDENCE_MANIFEST_CONFLICT")
    else:
        write_atomic_bytes(target, canonical)
    return f"evidence:{relative}", digest


def verify_evidence_manifest(
    root: Path,
    raw_path: str,
    *,
    plan_id: str,
    subject: str,
    expected_observed_ref: str | None = None,
) -> tuple[str, str]:
    """Verify canonical path, digest, payload and subject for one evidence record."""
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkctlError("EVIDENCE_MANIFEST_PATH_INVALID")
    candidate = checked_project_path(root, relative.as_posix())
    reject_legacy_plan_authority_path(root, relative.as_posix(), candidate)
    expected_parent = plan_dir(root) / ".evidence" / plan_id
    if candidate.parent != expected_parent or candidate.suffix != ".json":
        raise WorkctlError("EVIDENCE_MANIFEST_PATH_INVALID")
    if candidate.is_symlink() or not candidate.is_file():
        raise WorkctlError("EVIDENCE_MANIFEST_MISSING")
    content = candidate.read_bytes()
    if len(content) > EVIDENCE_MANIFEST_MAX_BYTES:
        raise WorkctlError("EVIDENCE_MANIFEST_TOO_LARGE")
    digest = sha256_bytes(content)
    if candidate.stem != digest:
        raise WorkctlError("EVIDENCE_MANIFEST_HASH_MISMATCH")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise WorkctlError("EVIDENCE_MANIFEST_INVALID_JSON") from exc
    if not isinstance(payload, dict):
        raise WorkctlError("EVIDENCE_MANIFEST_INVALID_JSON")
    validate_evidence_payload(payload, expected_plan_id=plan_id, expected_subject=subject)
    if expected_observed_ref is not None and payload.get("observed_ref") != expected_observed_ref:
        raise WorkctlError("EVIDENCE_MANIFEST_OBSERVED_REF_MISMATCH")
    if canonical_evidence_bytes(payload) != content:
        raise WorkctlError("EVIDENCE_MANIFEST_NON_CANONICAL")
    return f"evidence:{relative.as_posix()}", digest


def transition_evidence(
    root: Path,
    doc: PlanDocument,
    *,
    evidence_manifest: str | None,
    evidence_ref: str | None,
    evidence_sha256: str | None,
    subject: str,
    expected_observed_ref: str | None = None,
) -> tuple[str, str]:
    """Use immutable schema-v4 evidence and retain schema-v3 compatibility."""
    if doc.frontmatter.get("schema_version") == 4:
        if not isinstance(evidence_manifest, str):
            raise WorkctlError("EVIDENCE_MANIFEST_REQUIRED")
        return verify_evidence_manifest(
            root,
            evidence_manifest,
            plan_id=str(doc.frontmatter["plan_id"]),
            subject=subject,
            expected_observed_ref=expected_observed_ref,
        )
    if not isinstance(evidence_ref, str) or not isinstance(evidence_sha256, str):
        raise WorkctlError("EVIDENCE_REFERENCE_REQUIRED")
    require_evidence_args(evidence_ref, evidence_sha256)
    return evidence_ref, evidence_sha256


def cmd_plan_evidence_record(args: argparse.Namespace) -> None:
    """Install one canonical, content-addressed, versionable evidence record."""
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    payload = evidence_payload_from_args(args)
    if payload is None:
        raise WorkctlError("EVIDENCE_INPUT_REQUIRED")
    if doc.frontmatter.get("schema_version") == 5:
        payload = v5_redact_evidence_payload(payload)
    plan_id = str(doc.frontmatter["plan_id"])
    with lock(root):
        evidence_ref, digest = record_evidence_payload(
            root,
            plan_id=plan_id,
            payload=payload,
        )
    relative = evidence_ref.removeprefix("evidence:")
    print(json.dumps({"path": relative, "sha256": digest}, sort_keys=True))


def cmd_plan_verify_entry(args: argparse.Namespace) -> None:
    """Verify one obligation or validation through an evidence-bound command."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        singular = "obligation" if args.field == "obligations" else "validation"
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=[f"{singular}:{args.entry_id}"],
        )
        require_slice_revision_confirmation(
            doc.frontmatter,
            args.confirmation,
            {"accepted"},
        )
        require_independent_target(
            root,
            doc.frontmatter,
            f"{singular}:{args.entry_id}",
        )
        entries = entries_by_id(doc.frontmatter, args.field)
        entry = entries.get(args.entry_id)
        if entry is None:
            raise WorkctlError(f"UNKNOWN_{args.field.upper()}_ENTRY: {args.entry_id}")
        evidence_ref, evidence_sha256 = transition_evidence(
            root,
            doc,
            evidence_manifest=args.evidence_manifest,
            evidence_ref=args.evidence_ref,
            evidence_sha256=args.evidence_sha256,
            subject=f"{singular}:{args.entry_id}",
        )
        if entry.get("status") in VERIFIED_TASK_STATES:
            raise WorkctlError(
                f"INVALID_{args.field.upper()}_TRANSITION: "
                f"{args.entry_id} {entry.get('status')} -> verified"
            )
        entry["status"] = "verified"
        entry["evidence_ref"] = evidence_ref
        entry["evidence_sha256"] = evidence_sha256
        entry["verified_at"] = utc_now()
        bump_revision(
            doc.frontmatter,
            confirmation_id=args.confirmation,
            evidence_manifest=evidence_ref if doc.frontmatter.get("schema_version") == 4 else None,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(
            f"PLAN_ENTRY_VERIFIED {args.field} {args.entry_id} "
            f"revision={doc.frontmatter['revision']}"
        )


def cmd_plan_finalize_artifact(args: argparse.Namespace) -> None:
    """Finalize one artifact with an evidence reference and digest."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=[
                f"artifact:{args.artifact_id}",
                f"task:{args.task_id}",
            ],
        )
        require_slice_revision_confirmation(
            doc.frontmatter,
            args.confirmation,
            {"accepted"},
        )
        require_independent_target(
            root,
            doc.frontmatter,
            f"artifact:{args.artifact_id}",
        )
        require_independent_target(
            root,
            doc.frontmatter,
            f"task:{args.task_id}",
        )
        artifact = entries_by_id(doc.frontmatter, "artifacts").get(args.artifact_id)
        if artifact is None:
            raise WorkctlError(f"UNKNOWN_ARTIFACT: {args.artifact_id}")
        evidence_ref, evidence_sha256 = transition_evidence(
            root,
            doc,
            evidence_manifest=args.evidence_manifest,
            evidence_ref=args.evidence_ref,
            evidence_sha256=args.evidence_sha256,
            subject=f"artifact:{args.artifact_id}",
        )
        task = task_for(doc.frontmatter, args.task_id)
        if task.get("status") != "in_progress":
            raise WorkctlError(f"ARTIFACT_TASK_NOT_IN_PROGRESS: {args.task_id}")
        current_status = artifact.get("status")
        if current_status not in {"pending", "suspect"}:
            raise WorkctlError(
                f"INVALID_ARTIFACT_TRANSITION: {args.artifact_id} {current_status} -> final"
            )
        if current_status == "suspect":
            resolves = task.get("resolves_artifacts", [])
            if not isinstance(resolves, list) or args.artifact_id not in resolves:
                raise WorkctlError(
                    f"ARTIFACT_RECOVERY_OWNERSHIP_REQUIRED: "
                    f"{args.task_id} must resolve {args.artifact_id}"
                )
        state_confirmation_id = artifact.get("state_confirmation_id")
        if isinstance(state_confirmation_id, str):
            require_matching_decision(
                doc.frontmatter,
                state_confirmation_id,
                args.confirmation,
                {"accepted"},
            )
        artifact["status"] = "final"
        artifact["evidence_ref"] = evidence_ref
        artifact["evidence_sha256"] = evidence_sha256
        artifact["finalized_at"] = utc_now()
        artifact.pop("state_confirmation_id", None)
        bump_revision(
            doc.frontmatter,
            confirmation_id=args.confirmation,
            evidence_manifest=evidence_ref if doc.frontmatter.get("schema_version") == 4 else None,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"ARTIFACT_FINALIZED {args.artifact_id} revision={doc.frontmatter['revision']}")


def cmd_plan_artifact_state(args: argparse.Namespace) -> None:
    """Move an artifact through fail-safe deviation and recovery states."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        artifact = entries_by_id(doc.frontmatter, "artifacts").get(args.artifact_id)
        if artifact is None:
            raise WorkctlError(f"UNKNOWN_ARTIFACT: {args.artifact_id}")
        evidence_ref, evidence_sha256 = transition_evidence(
            root,
            doc,
            evidence_manifest=args.evidence_manifest,
            evidence_ref=args.evidence_ref,
            evidence_sha256=args.evidence_sha256,
            subject=f"artifact-state:{args.artifact_id}",
        )
        current_status = artifact.get("status")
        target_status = args.state
        if current_status == target_status:
            raise WorkctlError(
                f"INVALID_ARTIFACT_TRANSITION: {args.artifact_id} "
                f"{current_status} -> {target_status}"
            )
        stronger_states = {"quarantined", "rollback-pending"}
        if target_status == "suspect" and current_status in {"pending", "final"}:
            pass
        elif target_status in stronger_states and current_status == "suspect":
            require_slice_revision_confirmation(
                doc.frontmatter,
                args.confirmation,
                {"accepted"},
            )
            artifact["state_confirmation_id"] = args.confirmation
        elif target_status == "suspect" and current_status in stronger_states:
            state_confirmation_id = artifact.get("state_confirmation_id")
            require_matching_decision(
                doc.frontmatter,
                state_confirmation_id,
                args.confirmation,
                {"accepted"},
            )
        else:
            raise WorkctlError(
                f"INVALID_ARTIFACT_TRANSITION: {args.artifact_id} "
                f"{current_status} -> {target_status}"
            )
        artifact["status"] = target_status
        artifact["state_evidence_ref"] = evidence_ref
        artifact["state_evidence_sha256"] = evidence_sha256
        artifact["state_changed_at"] = utc_now()
        bump_revision(
            doc.frontmatter,
            confirmation_id=args.confirmation,
            evidence_manifest=evidence_ref if doc.frontmatter.get("schema_version") == 4 else None,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(
            f"ARTIFACT_STATE_UPDATED {args.artifact_id} {target_status} "
            f"revision={doc.frontmatter['revision']}"
        )


def cmd_plan_delivery_complete(args: argparse.Namespace) -> None:
    """Complete local delivery only through an evidence-bound transition."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=["delivery"],
        )
        require_slice_revision_confirmation(
            doc.frontmatter,
            args.confirmation,
            {"accepted"},
        )
        require_independent_target(root, doc.frontmatter, "delivery")
        delivery = doc.frontmatter.get("delivery")
        if not isinstance(delivery, dict):
            raise WorkctlError("INVALID_DELIVERY")
        evidence_ref, evidence_sha256 = transition_evidence(
            root,
            doc,
            evidence_manifest=args.evidence_manifest,
            evidence_ref=args.evidence_ref,
            evidence_sha256=args.evidence_sha256,
            subject="delivery",
        )
        if delivery.get("status") == "complete":
            raise WorkctlError("INVALID_DELIVERY_TRANSITION: complete -> complete")
        if delivery.get("boundary") in {None, "", "undetermined"}:
            raise WorkctlError("DELIVERY_BOUNDARY_REQUIRED")
        delivery["status"] = "complete"
        delivery["evidence_ref"] = evidence_ref
        delivery["evidence_sha256"] = evidence_sha256
        delivery["completed_at"] = utc_now()
        bump_revision(
            doc.frontmatter,
            confirmation_id=args.confirmation,
            evidence_manifest=evidence_ref if doc.frontmatter.get("schema_version") == 4 else None,
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"DELIVERY_COMPLETED revision={doc.frontmatter['revision']}")


def activation_exclusions_to_resolve(
    frontmatter: dict[str, Any],
    activation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve an explicit binding or one unambiguous legacy live exclusion."""
    confirmation_id = activation.get("confirmation_id")
    explicit = activation.get("resolves_exclusions")
    exclusions = exclusions_by_description(frontmatter)
    if explicit is None:
        legacy_matches = [
            exclusion
            for exclusion in exclusions.values()
            if exclusion.get("confirmation_id") == confirmation_id
            and exclusion.get("disposition") == "pending_confirmation"
        ]
        if len(legacy_matches) > 1:
            raise WorkctlError("ACTIVATION_EXCLUSION_BINDING_REQUIRED")
        return legacy_matches
    if (
        not isinstance(explicit, list)
        or not explicit
        or not all(isinstance(description, str) and description for description in explicit)
        or len(explicit) != len(set(explicit))
    ):
        raise WorkctlError("INVALID_ACTIVATION_EXCLUSION_BINDING")
    result: list[dict[str, Any]] = []
    for description in explicit:
        exclusion = exclusions.get(description)
        if (
            exclusion is None
            or exclusion.get("confirmation_id") != confirmation_id
            or exclusion.get("disposition") != "pending_confirmation"
        ):
            raise WorkctlError(f"ACTIVATION_EXCLUSION_BINDING_MISMATCH: {description}")
        result.append(exclusion)
    return result


def require_activation_repair_confirmation(
    frontmatter: dict[str, Any],
    *,
    confirmation_id: str,
    task_id: str,
    target_ref: str,
) -> dict[str, Any]:
    """Require one exact accepted gate for the repaired live target contract."""
    decision = require_matching_decision(
        frontmatter,
        confirmation_id,
        confirmation_id,
        {"accepted"},
    )
    intervention = decision.get("intervention")
    expected_blocks = {f"task:{task_id}", "activation", "route"}
    blocks = intervention.get("blocks") if isinstance(intervention, dict) else None
    if (
        not isinstance(intervention, dict)
        or intervention.get("kind") != "external_authority"
        or not isinstance(blocks, list)
        or set(blocks) != expected_blocks
        or len(blocks) != len(expected_blocks)
        or intervention.get("basis_ref") != target_ref
        or intervention.get("basis_sha256") != decision.get("evidence_sha256")
        or not isinstance(decision.get("evidence_sha256"), str)
        or SHA256_RE.fullmatch(str(decision["evidence_sha256"])) is None
    ):
        raise WorkctlError("ACTIVATION_REPAIR_CONFIRMATION_MISMATCH")
    return decision


def cmd_plan_activation_repair(args: argparse.Namespace) -> None:
    """Atomically repair one accepted schema-v4 legacy activation contract."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        if doc.frontmatter.get("schema_version") != 4:
            raise WorkctlError("ACTIVATION_REPAIR_REQUIRES_SCHEMA_V4")
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=[f"task:{args.task_id}", "activation", "route"],
        )
        activation = doc.frontmatter.get("activation")
        if not isinstance(activation, dict) or activation.get("status") != "pending_confirmation":
            raise WorkctlError("ACTIVATION_REPAIR_PENDING_STATE_REQUIRED")
        old_confirmation_id = activation.get("confirmation_id")
        if not isinstance(old_confirmation_id, str):
            raise WorkctlError("ACTIVATION_REPAIR_OLD_CONFIRMATION_REQUIRED")
        if args.confirmation == old_confirmation_id:
            raise WorkctlError("ACTIVATION_REPAIR_NEW_CONFIRMATION_REQUIRED")
        require_matching_decision(
            doc.frontmatter,
            old_confirmation_id,
            old_confirmation_id,
            {"accepted"},
        )
        exact_target = exact_activation_repair_target(
            activation.get("target_ref"),
            args.target_ref,
        )
        session_receipt = session_receipt_for_turn(
            root,
            args.turn_receipt_sha256,
            require_current_controller=True,
        )
        exact_match = EXACT_ACTIVATION_TARGET_RE.fullmatch(exact_target)
        expected_target = (
            f"plugin:{exact_match.group('plugin')}@{session_receipt.get('plugin_build')}"
            if exact_match is not None
            else None
        )
        if exact_target != expected_target:
            raise WorkctlError("ACTIVATION_REPAIR_CONTROLLER_BUILD_MISMATCH")
        decision = require_activation_repair_confirmation(
            doc.frontmatter,
            confirmation_id=args.confirmation,
            task_id=args.task_id,
            target_ref=exact_target,
        )
        task = task_for(doc.frontmatter, args.task_id)
        if task.get("status") != "blocked":
            raise WorkctlError("ACTIVATION_REPAIR_BLOCKED_TASK_REQUIRED")
        if task.get("requires_confirmation") != old_confirmation_id:
            raise WorkctlError("ACTIVATION_REPAIR_TASK_GATE_MISMATCH")
        if task.get("completion_scope", "local") != "route":
            raise WorkctlError("ACTIVATION_REPAIR_ROUTE_TASK_REQUIRED")
        raw_tasks = doc.frontmatter.get("tasks")
        route_gate_tasks = (
            [
                candidate
                for candidate in raw_tasks
                if isinstance(candidate, dict)
                and candidate.get("completion_scope", "local") == "route"
                and candidate.get("requires_confirmation") == old_confirmation_id
            ]
            if isinstance(raw_tasks, list)
            else []
        )
        if len(route_gate_tasks) != 1 or route_gate_tasks[0].get("id") != args.task_id:
            raise WorkctlError("ACTIVATION_REPAIR_ROUTE_TASK_AMBIGUOUS")
        route = doc.frontmatter.get("route")
        if (
            not isinstance(route, dict)
            or route.get("route_status") != "active"
            or route.get("confirmation_gate") != old_confirmation_id
        ):
            raise WorkctlError("ACTIVATION_REPAIR_ROUTE_GATE_MISMATCH")
        exclusions = activation_exclusions_to_resolve(doc.frontmatter, activation)
        for exclusion in exclusions:
            exclusion["confirmation_id"] = args.confirmation
        activation["target_ref"] = exact_target
        activation["confirmation_id"] = args.confirmation
        task["requires_confirmation"] = args.confirmation
        route["confirmation_gate"] = args.confirmation
        contract = doc.frontmatter.get("contract")
        if not isinstance(contract, dict) or type(contract.get("revision")) is not int:
            raise WorkctlError("INVALID_PLAN_CONTRACT")
        contract["revision"] = int(contract["revision"]) + 1
        contract["confirmation_id"] = args.confirmation
        contract["confirmed_ref"] = decision["ref"]
        bump_revision(
            doc.frontmatter,
            kind="activation-contract-repaired",
            rationale=(
                f"Repair the legacy activation contract for {args.task_id} "
                f"and freeze {exact_target}."
            ),
            confirmation_id=args.confirmation,
        )
        require_valid_candidate(doc)
        require_strict_intervention_contract(doc.frontmatter)
        if os.environ.get("WORKCTL_TEST_ACTIVATION_REPAIR_INTERRUPT") == "before-plan-write":
            raise WorkctlError("ACTIVATION_REPAIR_TEST_INTERRUPTED_BEFORE_PLAN_WRITE")
        write_atomic(doc.path, dump_plan(doc))
        print(
            f"ACTIVATION_CONTRACT_REPAIRED task={args.task_id} "
            f"target={exact_target} revision={doc.frontmatter['revision']}"
        )


def cmd_plan_activation_promote(args: argparse.Namespace) -> None:
    """Promote activation through intake- and confirmation-bound states."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=["activation"],
        )
        activation = doc.frontmatter.get("activation")
        if not isinstance(activation, dict):
            raise WorkctlError("INVALID_ACTIVATION")
        require_independent_target(root, doc.frontmatter, "activation")
        decision = require_matching_decision(
            doc.frontmatter,
            activation.get("confirmation_id"),
            args.confirmation,
            {"accepted"},
        )
        target_ref = args.target_ref
        current = activation.get("status")
        if args.state == "in_progress":
            if current not in {"pending_confirmation", "deferred"}:
                raise WorkctlError(f"INVALID_ACTIVATION_TRANSITION: {current} -> in_progress")
            if target_ref is not None:
                if doc.frontmatter.get("schema_version") != 4:
                    raise WorkctlError("ACTIVATION_TARGET_REQUIRES_SCHEMA_V4")
                activation["target_ref"] = exact_activation_target_from_placeholder(
                    activation.get("target_ref"),
                    target_ref,
                )
            activation["status"] = "in_progress"
        else:
            if target_ref is not None:
                raise WorkctlError("ACTIVATION_TARGET_REBIND_INVALID_STATE")
            if current != "in_progress":
                raise WorkctlError(f"INVALID_ACTIVATION_TRANSITION: {current} -> active")
            frozen_target = activation.get("target_ref")
            if not isinstance(frozen_target, str) or not frozen_target:
                raise WorkctlError("INVALID_ACTIVATION_TARGET")
            evidence_ref, evidence_sha256 = transition_evidence(
                root,
                doc,
                evidence_manifest=args.evidence_manifest,
                evidence_ref=args.evidence_ref,
                evidence_sha256=args.evidence_sha256,
                subject="activation",
                expected_observed_ref=(
                    frozen_target if doc.frontmatter.get("schema_version") == 4 else None
                ),
            )
            activation["status"] = "active"
            activation["current_ref"] = frozen_target
            activation["evidence"] = {
                "observed_ref": frozen_target,
                "source_ref": evidence_ref,
                "checked_at": utc_now(),
                "sha256": evidence_sha256,
            }
            for exclusion in activation_exclusions_to_resolve(
                doc.frontmatter,
                activation,
            ):
                exclusion["disposition"] = "completed"
                exclusion["resolution_ref"] = decision["ref"]
        bump_revision(
            doc.frontmatter,
            confirmation_id=args.confirmation,
            evidence_manifest=(
                activation.get("evidence", {}).get("source_ref")
                if isinstance(activation.get("evidence"), dict)
                else None
            ),
            rationale=f"Promote activation to {args.state}.",
        )
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"ACTIVATION_PROMOTED {args.state} revision={doc.frontmatter['revision']}")


def cmd_log_append(args: argparse.Namespace) -> None:
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    require_expected_revision(doc.frontmatter, args.expected_revision)
    local_logs_dir = logs_dir(root)
    local_logs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "time": utc_now(),
        "plan_id": doc.frontmatter.get("plan_id"),
        "revision": doc.frontmatter.get("revision"),
        "kind": args.kind,
        "message": args.message,
    }
    path = local_logs_dir / f"{doc.frontmatter['plan_id']}.jsonl"
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    fd = os.open(path, flags, 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(f"LOG_APPENDED {path}")


def candidate_to_dict(candidate: AuthorityCandidate) -> dict[str, Any]:
    """Convert a candidate into stable JSON output."""
    if module_candidate_to_dict is None:
        raise WorkctlError("AUTHORITY_MODULE_UNAVAILABLE: candidate_to_dict")
    return cast(dict[str, Any], module_candidate_to_dict(candidate))


def parse_candidate_specs(values: list[str]) -> dict[str, str]:
    """Parse repeatable ``PATH=CLASSIFICATION`` semantic inputs."""
    if module_parse_candidate_specs is None:
        raise WorkctlError("AUTHORITY_MODULE_UNAVAILABLE: parse_candidate_specs")
    try:
        return module_parse_candidate_specs(values, AUTHORITY_CLASSIFICATIONS)
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def cmd_plan_authority_inspect(args: argparse.Namespace) -> None:
    """Print authority candidates, signals, hashes, state, and allowed commands."""
    explicit = parse_candidate_specs(args.candidate)
    report = inspect_authority(project_root(), explicit)
    payload = {
        "authority_state": report.state,
        "candidates": [candidate_to_dict(candidate) for candidate in report.candidates],
        "blocking_reasons": report.blockers,
        "allowed_commands": report.allowed_commands,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_plan_authority_check(args: argparse.Namespace) -> None:
    """Print the current deterministic authority state."""
    explicit = parse_candidate_specs(args.candidate)
    report = inspect_authority(project_root(), explicit)
    print(
        json.dumps(
            {
                "authority_state": report.state,
                "blocking_reasons": report.blockers,
                "allowed_commands": report.allowed_commands,
            },
            indent=2,
            sort_keys=True,
        )
    )


def cmd_plan_schema_validate(args: argparse.Namespace) -> None:
    """Validate one Plan document without checking project authority."""
    root = project_root()
    path = Path(args.plan).resolve() if args.plan else active_plan_path(root)
    doc = load_plan(path)
    errors = validate_frontmatter(doc.frontmatter, reject_blocking_artifacts=False)
    if not doc.body.strip():
        errors.append("Plan body must not be empty")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
    print(f"PLAN_SCHEMA_VALID {path}")


def incomplete_entries(frontmatter: dict[str, Any], field: str) -> list[str]:
    """Return IDs for work entries that are not verified or skipped."""
    return module_incomplete_entries(frontmatter, field, VERIFIED_TASK_STATES)


def unresolved_exclusions(frontmatter: dict[str, Any]) -> list[str]:
    """Return schema-v3 exclusions that still require route disposition."""
    return module_unresolved_exclusions(frontmatter, BLOCKING_EXCLUSION_DISPOSITIONS)


def completion_claims(
    frontmatter: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    """Describe which completion claims current evidence permits."""
    if module_completion_claims is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: completion_claims")

    def incomplete_ids(document: Mapping[str, object], field: str) -> Sequence[str]:
        return incomplete_entries(cast(dict[str, Any], document), field)

    def confirmation_lookup(
        document: Mapping[str, object],
    ) -> Mapping[str, Mapping[str, object]]:
        return cast(
            Mapping[str, Mapping[str, object]],
            confirmations(cast(dict[str, Any], document)),
        )

    return cast(
        dict[str, Any],
        module_completion_claims(
            frontmatter,
            readiness,
            incomplete_entry_ids=incomplete_ids,
            confirmations_by_id=confirmation_lookup,
            verified_task_states=VERIFIED_TASK_STATES,
        ),
    )


def closeout_readiness(
    frontmatter: dict[str, Any],
    report: AuthorityReport,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Compute complete-route readiness without mutating the Plan."""
    blockers: list[str] = []
    blockers.extend(f"plan validation: {error}" for error in (validation_errors or []))
    if report.state != "GOVERNED_ACTIVE":
        blockers.append(f"authority state is {report.state}")
    for field in ("obligations", "tasks", "validations"):
        for entry_id in incomplete_entries(frontmatter, field):
            blockers.append(f"{field} not complete: {entry_id}")
    raw_unknowns = frontmatter.get("unknowns", [])
    if not isinstance(raw_unknowns, list):
        blockers.append("unknowns is invalid")
    else:
        for unknown in raw_unknowns:
            if isinstance(unknown, dict) and unknown.get("status") == "open":
                blockers.append(f"unknown remains open: {unknown.get('id', 'unknown')}")
    artifacts = frontmatter.get("artifacts", [])
    if not isinstance(artifacts, list):
        blockers.append("artifacts is invalid")
    else:
        for artifact in artifacts:
            if not isinstance(artifact, dict) or artifact.get("status") != "final":
                artifact_id = (
                    artifact.get("id", "unknown") if isinstance(artifact, dict) else "invalid"
                )
                blockers.append(f"artifact not final: {artifact_id}")
    if frontmatter.get("schema_version") in {3, 4}:
        delivery = frontmatter.get("delivery", {})
        if not isinstance(delivery, dict) or delivery.get("status") != "complete":
            blockers.append("delivery is not complete")
        activation = frontmatter.get("activation", {})
        if isinstance(activation, dict) and activation.get("status") in BLOCKING_ACTIVATION_STATES:
            blockers.append(f"activation is {activation.get('status')}")
        for description in unresolved_exclusions(frontmatter):
            blockers.append(f"scope exclusion is unresolved: {description}")
    if frontmatter.get("schema_version") == 4:
        if STRICT_INITIAL_INTAKE_REQUIRED:
            current_intake_state = intake_state(frontmatter)
            if current_intake_state != "CURRENT_BASIS":
                blockers.append(f"intake is {current_intake_state}")
        for unknown_id in legacy_unknown_ids(frontmatter):
            blockers.append(f"legacy unknown contract: {unknown_id}")
        intervention_state = intervention_contract_state(frontmatter)
        if intervention_state != "STRICT_READY":
            blockers.append(f"intervention contract is {intervention_state}")
    for mode in independent_review_blockers(project_root(), frontmatter, "route"):
        blockers.append(f"independent review blocks route: {mode}")
    raw_confirmations = frontmatter.get("confirmations", {})
    if not isinstance(raw_confirmations, dict):
        blockers.append("confirmations is invalid")
    else:
        for item in raw_confirmations.get("required", []):
            if not isinstance(item, dict) or not confirmation_resolved_for_closeout(
                frontmatter, item
            ):
                confirmation_id = item.get("id", "unknown") if isinstance(item, dict) else "invalid"
                blockers.append(f"confirmation unresolved: {confirmation_id}")
    route = frontmatter.get("route", {})
    if not isinstance(route, dict):
        blockers.append("route is invalid")
    else:
        if route.get("route_status") != "terminal":
            blockers.append("route_status is not terminal")
        if route.get("next_phase") not in {"", "none"}:
            blockers.append("next_phase remains")
        if route.get("confirmation_gate") not in {"", "none"}:
            blockers.append("confirmation_gate remains")
    handoff = frontmatter.get("handoff", {})
    if not isinstance(handoff, dict):
        blockers.append("handoff is invalid")
    else:
        if handoff.get("route_status") != "terminal":
            blockers.append("handoff route_status is not terminal")
        if handoff.get("next_step") not in {"", "none"}:
            blockers.append("handoff next_step remains")
    return {"ready": not blockers, "blockers": blockers}


def cmd_plan_closeout_check(args: argparse.Namespace) -> None:
    """Print closeout readiness and fail when obligations remain."""
    root = project_root()
    report = inspect_authority(root)
    doc = load_plan(active_plan_path(root))
    readiness = closeout_readiness(doc.frontmatter, report, validate_plan(root))
    if doc.frontmatter.get("schema_version") == 4:
        if not args.evidence_manifest:
            readiness["ready"] = False
            readiness["blockers"].append("closeout evidence manifest required")
        else:
            try:
                verify_evidence_manifest(
                    root,
                    args.evidence_manifest,
                    plan_id=str(doc.frontmatter["plan_id"]),
                    subject="closeout",
                )
            except WorkctlError as exc:
                readiness["ready"] = False
                readiness["blockers"].append(str(exc))
    print(json.dumps(readiness, indent=2, sort_keys=True))
    if not readiness["ready"]:
        raise SystemExit(1)


def cmd_plan_complete(args: argparse.Namespace) -> None:
    """Mark a Plan complete, optionally finalizing a ready route atomically."""
    root = project_root()
    with lock(root):
        report = require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=["route"],
        )
        evidence_ref: str | None = None
        evidence_sha256: str | None = None
        if doc.frontmatter.get("schema_version") == 4:
            if not args.evidence_manifest:
                raise WorkctlError("EVIDENCE_MANIFEST_REQUIRED")
            evidence_ref, evidence_sha256 = verify_evidence_manifest(
                root,
                args.evidence_manifest,
                plan_id=str(doc.frontmatter["plan_id"]),
                subject="closeout",
            )
        require_independent_target(root, doc.frontmatter, "route")
        if args.confirmation and not args.finalize_route:
            raise WorkctlError("FINALIZE_ROUTE_REQUIRED_FOR_CONFIRMATION")
        finalized_atomically = False
        atomic_intake_history: tuple[list[dict[str, Any]], dict[str, object]] | None = None
        if args.finalize_route:
            require_slice_revision_confirmation(
                doc.frontmatter,
                args.confirmation,
                {"accepted", "declined"},
            )
            route = doc.frontmatter.get("route")
            handoff = doc.frontmatter.get("handoff")
            if not isinstance(route, dict) or not isinstance(handoff, dict):
                raise WorkctlError("INVALID_TERMINAL_ROUTE")
            route["route_status"] = "terminal"
            route["slice_status"] = "complete"
            route["next_phase"] = "none"
            route["confirmation_gate"] = "none"
            handoff["route_status"] = "terminal"
            handoff["next_step"] = "none"
            if STRICT_INITIAL_INTAKE_REQUIRED:
                atomic_intake_history = refresh_intake_for_atomic_controller_transition(
                    doc.frontmatter
                )
            doc.frontmatter["status"] = "complete"
            if evidence_ref is not None and evidence_sha256 is not None:
                doc.frontmatter["completion_evidence"] = {
                    "ref": evidence_ref,
                    "sha256": evidence_sha256,
                    "completed_at": utc_now(),
                }
            bump_revision(
                doc.frontmatter,
                confirmation_id=args.confirmation,
                evidence_manifest=evidence_ref,
                rationale="Atomically finalize the route and complete the Plan.",
            )
            finalized_atomically = True
            validation_errors = validate_frontmatter(
                doc.frontmatter,
                reject_blocking_artifacts=True,
            )
        else:
            validation_errors = validate_plan(root)
        readiness = closeout_readiness(doc.frontmatter, report, validation_errors)
        if not readiness["ready"]:
            raise WorkctlError(
                f"CLOSEOUT_BLOCKED: {'; '.join(str(item) for item in readiness['blockers'])}"
            )
        if not finalized_atomically:
            doc.frontmatter["status"] = "complete"
            if evidence_ref is not None and evidence_sha256 is not None:
                doc.frontmatter["completion_evidence"] = {
                    "ref": evidence_ref,
                    "sha256": evidence_sha256,
                    "completed_at": utc_now(),
                }
            bump_revision(
                doc.frontmatter,
                evidence_manifest=evidence_ref,
                rationale="Complete the Plan after evidence-bound closeout.",
            )
        if atomic_intake_history is not None:
            prior_records, refreshed_record = atomic_intake_history
            plan_id = str(doc.frontmatter["plan_id"])
            for prior in prior_records:
                persist_intake_history_record(root, plan_id, prior)
            persist_intake_history_record(root, plan_id, refreshed_record)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_COMPLETED revision={doc.frontmatter['revision']}")


def confirmation_module_call(name: str) -> Any:
    """Return one extracted confirmation helper or fail with a stable code."""
    if module_confirmation is None:
        raise WorkctlError(f"CONFIRMATION_MODULE_UNAVAILABLE: {name}")
    try:
        return getattr(module_confirmation, name)
    except AttributeError as exc:
        raise WorkctlError(f"CONFIRMATION_MODULE_UNAVAILABLE: {name}") from exc


def manifest_input_path(manifest_path: Path, raw_path: str) -> Path:
    """Resolve a read-only manifest input relative to the manifest directory."""
    try:
        return cast(Path, confirmation_module_call("manifest_input_path")(manifest_path, raw_path))
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def confirmation_from_manifest(
    confirmations_value: dict[str, Any],
    key: str,
    *,
    required: bool,
) -> tuple[str, str, str, str] | None:
    """Read one accepted confirmation reference from a reconciliation manifest."""
    try:
        return cast(
            tuple[str, str, str, str] | None,
            confirmation_module_call("confirmation_from_manifest")(
                confirmations_value,
                key,
                required=required,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def accepted_confirmation(
    confirmation_id: str,
    ref: str,
    accepted_at: str,
    evidence_sha256: str,
    description: str,
    *,
    intervention_kind: str = "plan_contract",
) -> dict[str, Any]:
    """Build a confirmed or dry-run-pending entry for the canonical Plan."""
    try:
        return cast(
            dict[str, Any],
            confirmation_module_call("accepted_confirmation")(
                confirmation_id,
                ref,
                accepted_at,
                evidence_sha256,
                description,
                intervention_kind=intervention_kind,
            ),
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def archive_path_for_source(migration_id: str, source_path: str) -> str:
    """Return the deterministic archive location for a migration source."""
    if module_archive_path_for_source is None:
        raise WorkctlError("MIGRATION_MODULE_UNAVAILABLE: archive_path_for_source")
    try:
        return module_archive_path_for_source(
            migration_id,
            source_path,
            governance_dir_name=GOVERNANCE_DIR_NAME,
            plan_dir_name=PLAN_DIR_NAME,
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def pointer_text(
    *,
    source_path: str,
    canonical_path: str,
    migration_id: str,
    archive_path: str,
) -> str:
    """Build the non-authoritative pointer that replaces a migrated source."""
    if module_pointer_text is None:
        raise WorkctlError("MIGRATION_MODULE_UNAVAILABLE: pointer_text")
    try:
        return module_pointer_text(
            source_path=source_path,
            canonical_path=canonical_path,
            migration_id=migration_id,
            archive_path=archive_path,
            pointer_marker=POINTER_MARKER,
        )
    except ValueError as exc:
        raise WorkctlError(str(exc)) from exc


def current_git_baseline(root: Path) -> str | None:
    """Return HEAD for Git projects, otherwise ``None``."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def add_or_replace_confirmation(
    frontmatter: dict[str, Any],
    confirmation: dict[str, Any],
) -> None:
    """Insert one accepted confirmation without duplicating its ID."""
    raw_confirmations = frontmatter.setdefault("confirmations", {})
    if not isinstance(raw_confirmations, dict):
        raise WorkctlError("INVALID_PLAN: confirmations must be a mapping")
    required = raw_confirmations.setdefault("required", [])
    if not isinstance(required, list):
        raise WorkctlError("INVALID_PLAN: confirmations.required must be a list")
    confirmation_id = confirmation["id"]
    required[:] = [
        item for item in required if not isinstance(item, dict) or item.get("id") != confirmation_id
    ]
    required.append(confirmation)


def upgrade_reconciled_plan_to_schema3(
    frontmatter: dict[str, Any],
    migration_id: str,
) -> None:
    """Preserve schema v3 or safely upgrade a legacy prepared target."""
    if frontmatter.get("schema_version") == 3:
        return
    if frontmatter.get("schema_version") not in {1, 2}:
        raise WorkctlError("UNSUPPORTED_PREPARED_PLAN_SCHEMA")
    scope = frontmatter.get("scope")
    if not isinstance(scope, dict):
        raise WorkctlError("INVALID_PREPARED_PLAN_SCOPE")
    exclusions = scope.get("exclude", [])
    if not isinstance(exclusions, list):
        raise WorkctlError("INVALID_PREPARED_PLAN_EXCLUSIONS")
    scope["exclude"] = [
        (
            {
                "description": exclusion,
                "disposition": "deferred",
            }
            if isinstance(exclusion, str)
            else exclusion
        )
        for exclusion in exclusions
    ]
    frontmatter["schema_version"] = 3
    frontmatter.setdefault(
        "delivery",
        {
            "status": "pending",
            "boundary": "reconciled-plan",
            "evidence_ref": f"project:{migration_id}",
        },
    )
    frontmatter.setdefault(
        "activation",
        {
            "status": "deferred",
            "current_ref": "undetermined",
            "target_ref": "undetermined",
        },
    )
    route = frontmatter.get("route")
    if not isinstance(route, dict):
        raise WorkctlError("INVALID_PREPARED_PLAN_ROUTE")
    if route.get("route_status") == "terminal":
        route["route_status"] = "active"
        route["next_phase"] = "Resolve delivery and activation after reconciliation."
        route["confirmation_gate"] = "none"
    handoff = frontmatter.get("handoff")
    if not isinstance(handoff, dict):
        raise WorkctlError("INVALID_PREPARED_PLAN_HANDOFF")
    handoff["route_status"] = route.get("route_status")
    if handoff.get("route_status") != "terminal" and handoff.get("next_step") in {
        "",
        "none",
    }:
        handoff["next_step"] = "Resolve delivery and activation after reconciliation."


def prepare_reconciliation(
    root: Path,
    manifest_path: Path,
    *,
    require_confirmations: bool,
) -> tuple[dict[str, Any], PlanDocument, str | None]:
    """Validate a reconciliation manifest and build its canonical Plan."""
    manifest = load_yaml_file(manifest_path)
    migration_id = manifest.get("migration_id")
    if not isinstance(migration_id, str) or MIGRATION_ID_RE.fullmatch(migration_id) is None:
        raise WorkctlError("INVALID_MIGRATION_ID")
    target_value = manifest.get("target_plan")
    if not isinstance(target_value, dict):
        raise WorkctlError("MANIFEST_TARGET_PLAN_REQUIRED")
    prepared_file = target_value.get("prepared_file")
    if not isinstance(prepared_file, str):
        raise WorkctlError("MANIFEST_TARGET_PREPARED_FILE_REQUIRED")
    prepared_path = manifest_input_path(manifest_path, prepared_file)
    prepared_doc = load_plan(prepared_path)
    plan_id = prepared_doc.frontmatter.get("plan_id")
    if not isinstance(plan_id, str) or PLAN_ID_RE.fullmatch(plan_id) is None:
        raise WorkctlError("INVALID_TARGET_PLAN_ID")
    target_relative = plan_relative_path(f"{plan_id}.md")
    target_path = checked_project_path(root, target_relative)
    if target_path.exists():
        raise WorkctlError(f"TARGET_PLAN_MUST_BE_NEW: {target_relative}")
    if prepared_doc.frontmatter.get("status") != "active":
        raise WorkctlError("TARGET_PLAN_MUST_BE_ACTIVE")

    expected_git_baseline = manifest.get("git_baseline")
    if expected_git_baseline is not None:
        if not isinstance(expected_git_baseline, str) or not expected_git_baseline:
            raise WorkctlError("INVALID_GIT_BASELINE")
        actual_git_baseline = current_git_baseline(root)
        if actual_git_baseline != expected_git_baseline:
            raise WorkctlError(
                "GIT_BASELINE_MISMATCH: "
                f"expected {expected_git_baseline}, found {actual_git_baseline}"
            )

    agents_value = manifest.get("agents_rewrite")

    sources_value = manifest.get("sources", [])
    if not isinstance(sources_value, list):
        raise WorkctlError("MANIFEST_SOURCES_MUST_BE_LIST")
    sources: list[dict[str, Any]] = []
    source_paths: set[str] = set()
    for raw_source in sources_value:
        if not isinstance(raw_source, dict):
            raise WorkctlError("MANIFEST_SOURCE_MUST_BE_MAPPING")
        source_path = raw_source.get("path")
        role = raw_source.get("role")
        expected_hash = raw_source.get("sha256")
        classification = raw_source.get("classification")
        if not isinstance(source_path, str):
            raise WorkctlError("MANIFEST_SOURCE_PATH_REQUIRED")
        if source_path in source_paths:
            raise WorkctlError(f"DUPLICATE_MIGRATION_SOURCE: {source_path}")
        source_paths.add(source_path)
        if source_path.startswith(
            (
                plan_relative_path("archive") + "/",
                plan_relative_path(".migrations") + "/",
            )
        ):
            raise WorkctlError(f"INVALID_MIGRATION_SOURCE: {source_path}")
        if source_path == target_relative:
            raise WorkctlError("TARGET_PLAN_MUST_BE_NEW")
        if role not in SOURCE_ROLES:
            raise WorkctlError(f"INVALID_SOURCE_ROLE: {source_path}")
        if classification != "CONFIRMED_AUTHORITY":
            raise WorkctlError(f"SOURCE_CLASSIFICATION_REQUIRED: {source_path}")
        if not isinstance(expected_hash, str) or SHA256_RE.fullmatch(expected_hash) is None:
            raise WorkctlError(f"INVALID_SOURCE_HASH: {source_path}")
        source = checked_project_path(root, source_path)
        reject_legacy_plan_authority_path(root, source_path, source)
        actual_hash = sha256_file(source)
        if actual_hash != expected_hash:
            raise WorkctlError(
                f"SOURCE_DRIFT: {source_path} expected {expected_hash}, found {actual_hash}"
            )
        expected_revision = raw_source.get("revision")
        _, actual_revision, _ = optional_plan_metadata(source)
        if expected_revision is not None and expected_revision != actual_revision:
            raise WorkctlError(
                f"SOURCE_REVISION_DRIFT: {source_path} expected {expected_revision}, "
                f"found {actual_revision}"
            )
        archive_relative = archive_path_for_source(migration_id, source_path)
        archive_path = checked_project_path(root, archive_relative)
        if archive_path.exists() and sha256_file(archive_path) != expected_hash:
            raise WorkctlError(f"ARCHIVE_HASH_MISMATCH: {archive_relative}")
        sources.append(
            {
                "path": source_path,
                "role": role,
                "sha256": expected_hash,
                "revision": expected_revision,
                "archive_path": archive_relative,
                "classification": classification,
            }
        )

    explicit_classifications = {
        str(source["path"]): str(source["classification"]) for source in sources
    }
    authority_report = inspect_authority(root, explicit_classifications)
    required_source_paths = {
        candidate.path
        for candidate in authority_report.candidates
        if candidate.classification == "CONFIRMED_AUTHORITY"
        and (
            "migration-pointer" not in candidate.signals
            or "project-rule-explicit" in candidate.signals
        )
    }
    missing_sources = sorted(required_source_paths - source_paths)
    if missing_sources:
        raise WorkctlError(f"MISSING_MIGRATION_SOURCES: {','.join(missing_sources)}")
    unresolved_likely = sorted(
        candidate.path
        for candidate in authority_report.candidates
        if candidate.classification == "LIKELY_AUTHORITY"
        and "migration-pointer" not in candidate.signals
    )
    if unresolved_likely:
        raise WorkctlError(f"UNRESOLVED_AUTHORITY_CANDIDATES: {','.join(unresolved_likely)}")

    agents_record: dict[str, Any] | None = None
    diff_text: str | None = None
    if agents_value is not None:
        if not isinstance(agents_value, dict):
            raise WorkctlError("MANIFEST_AGENTS_REWRITE_MUST_BE_MAPPING")
        agents_path_value = agents_value.get("path")
        expected_hash = agents_value.get("sha256")
        replacement_file = agents_value.get("replacement_file")
        if not all(
            isinstance(value, str) for value in (agents_path_value, expected_hash, replacement_file)
        ):
            raise WorkctlError("INVALID_AGENTS_REWRITE")
        assert isinstance(agents_path_value, str)
        assert isinstance(expected_hash, str)
        assert isinstance(replacement_file, str)
        agents_path = checked_project_path(root, agents_path_value)
        reject_legacy_plan_authority_path(root, agents_path_value, agents_path)
        if agents_path_value != "AGENTS.md":
            raise WorkctlError("INVALID_AGENTS_REWRITE_PATH")
        if SHA256_RE.fullmatch(expected_hash) is None:
            raise WorkctlError("INVALID_AGENTS_REWRITE_HASH")
        if sha256_file(agents_path) != expected_hash:
            raise WorkctlError(f"SOURCE_DRIFT: {agents_path_value}")
        replacement_path = manifest_input_path(manifest_path, replacement_file)
        if not replacement_path.is_file():
            raise WorkctlError(f"MISSING_FILE: {replacement_path}")
        original_text = agents_path.read_text(encoding="utf-8")
        replacement_text = replacement_path.read_text(encoding="utf-8")
        if original_text == replacement_text:
            raise WorkctlError("AGENTS_REWRITE_HAS_NO_DIFF")
        diff_text = "".join(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                replacement_text.splitlines(keepends=True),
                fromfile=agents_path_value,
                tofile=f"{agents_path_value}.proposed",
            )
        )
        agents_record = {
            "path": agents_path_value,
            "sha256": expected_hash,
            "replacement_file": str(replacement_path),
            "replacement_sha256": sha256_file(replacement_path),
        }

    prepared_sha256 = sha256_file(prepared_path)
    agents_diff_sha256 = sha256_bytes(diff_text.encode()) if diff_text is not None else None
    proposal_payload = {
        "migration_id": migration_id,
        "target_path": target_relative,
        "prepared_plan_sha256": prepared_sha256,
        "git_baseline": expected_git_baseline,
        "sources": sources,
        "agents_rewrite": (
            {
                "path": agents_record["path"],
                "sha256": agents_record["sha256"],
                "replacement_sha256": agents_record["replacement_sha256"],
                "diff_sha256": agents_diff_sha256,
            }
            if agents_record is not None
            else None
        ),
    }
    proposal_sha256 = sha256_bytes(
        json.dumps(proposal_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    confirmations_value = manifest.get("confirmations")
    if not isinstance(confirmations_value, dict):
        if require_confirmations:
            raise WorkctlError("MANIFEST_CONFIRMATIONS_REQUIRED")
        confirmations_value = {}
    baseline_confirmation = confirmation_from_manifest(
        confirmations_value,
        "baseline",
        required=require_confirmations,
    )
    if baseline_confirmation is None:
        baseline_confirmation = (
            "C-MIGRATION-BASELINE",
            "PENDING",
            "PENDING",
            proposal_sha256,
        )
    agents_confirmation = confirmation_from_manifest(
        confirmations_value,
        "agents_rewrite",
        required=agents_value is not None and require_confirmations,
    )
    if agents_value is not None and agents_confirmation is None:
        assert agents_diff_sha256 is not None
        agents_confirmation = (
            "C-AGENTS-REWRITE",
            "PENDING",
            "PENDING",
            agents_diff_sha256,
        )
    baseline_id, baseline_ref, baseline_accepted_at, baseline_evidence = baseline_confirmation
    if require_confirmations and baseline_evidence != proposal_sha256:
        raise WorkctlError(f"CONFIRMATION_EVIDENCE_MISMATCH: baseline expected {proposal_sha256}")
    add_or_replace_confirmation(
        prepared_doc.frontmatter,
        accepted_confirmation(
            baseline_id,
            baseline_ref,
            baseline_accepted_at,
            baseline_evidence,
            "Approve the migration baseline, classifications, hashes, and merged Plan.",
        ),
    )
    authority_confirmations: dict[str, str] = {"baseline": baseline_id}
    if agents_confirmation is not None:
        agents_id, agents_ref, agents_accepted_at, agents_evidence = agents_confirmation
        assert agents_diff_sha256 is not None
        if require_confirmations and agents_evidence != agents_diff_sha256:
            raise WorkctlError(
                f"CONFIRMATION_EVIDENCE_MISMATCH: agents_rewrite expected {agents_diff_sha256}"
            )
        add_or_replace_confirmation(
            prepared_doc.frontmatter,
            accepted_confirmation(
                agents_id,
                agents_ref,
                agents_accepted_at,
                agents_evidence,
                "Approve the exact project AGENTS.md Plan-routing rewrite.",
            ),
        )
        authority_confirmations["agents_rewrite"] = agents_id
    upgrade_reconciled_plan_to_schema3(prepared_doc.frontmatter, migration_id)
    prepared_doc.frontmatter["authority"] = {
        "model": AUTHORITY_MODEL,
        "state": AUTHORITY_STATE,
        "canonical_plan_id": plan_id,
        "migration_id": migration_id,
        "sources": sources,
        "confirmations": authority_confirmations,
    }
    target_doc = PlanDocument(
        target_path,
        prepared_doc.frontmatter,
        prepared_doc.body,
    )
    require_valid_candidate(target_doc)
    require_strict_intervention_contract(target_doc.frontmatter)
    require_new_plan_reviews_pending(target_doc.frontmatter)
    manifest["migration_id"] = migration_id
    manifest["target_relative"] = target_relative
    manifest["sources"] = sources
    manifest["agents_record"] = agents_record
    manifest["prepared_plan_sha256"] = prepared_sha256
    manifest["proposal_sha256"] = proposal_sha256
    manifest["agents_diff_sha256"] = agents_diff_sha256
    return manifest, target_doc, diff_text


def stage_reconciliation(
    root: Path,
    manifest: dict[str, Any],
    target_doc: PlanDocument,
) -> Path:
    """Stage immutable migration inputs and create the recovery journal."""
    migration_id = str(manifest["migration_id"])
    migration_dir, staging_dir, journal_path = reconciliation_transaction_paths(
        root,
        migration_id,
    )
    if journal_path.exists():
        raise WorkctlError(f"MIGRATION_JOURNAL_EXISTS: {migration_id}")

    staged_plan = staging_dir / "target-plan.md"
    reject_symlink_components(root, staged_plan)
    staged_plan_text = dump_plan(target_doc)
    staged_plan_bytes = staged_plan_text.encode("utf-8")
    staged_sources: list[dict[str, Any]] = []
    staged_source_bytes: list[tuple[Path, bytes]] = []
    for source in manifest["sources"]:
        assert isinstance(source, dict)
        source_path_value = str(source["path"])
        source_path = checked_project_path(root, source_path_value)
        reject_legacy_plan_authority_path(root, source_path_value, source_path)
        staged_path = staging_dir / "sources" / source_path_value
        reject_symlink_components(root, staged_path)
        source_bytes = source_path.read_bytes()
        if sha256_bytes(source_bytes) != source["sha256"]:
            raise WorkctlError(f"SOURCE_DRIFT: {source_path_value}")
        staged_source_bytes.append((staged_path, source_bytes))
        staged_sources.append({**source, "staged_path": relative_project_path(root, staged_path)})

    agents_record = manifest.get("agents_record")
    staged_agents: dict[str, Any] | None = None
    staged_agents_write: tuple[Path, bytes] | None = None
    if isinstance(agents_record, dict):
        replacement_file = Path(str(agents_record["replacement_file"]))
        staged_agents_path = staging_dir / "agents-replacement.md"
        reject_symlink_components(root, staged_agents_path)
        replacement_bytes = replacement_file.read_bytes()
        if sha256_bytes(replacement_bytes) != agents_record["replacement_sha256"]:
            raise WorkctlError("AGENTS_REWRITE_DRIFT")
        staged_agents_write = (staged_agents_path, replacement_bytes)
        staged_agents = {
            **agents_record,
            "staged_path": relative_project_path(root, staged_agents_path),
        }

    expected_files = {
        relative_project_path(migration_dir, staged_plan),
        *(
            relative_project_path(migration_dir, staged_path)
            for staged_path, _ in staged_source_bytes
        ),
    }
    if staged_agents_write is not None:
        expected_files.add(relative_project_path(migration_dir, staged_agents_write[0]))
    conflict_error = f"MIGRATION_STAGING_EXISTS: {migration_id}"
    validate_partial_transaction_directory(
        migration_dir,
        expected_files,
        error=conflict_error,
    )
    write_or_validate_staged_bytes(
        staged_plan,
        staged_plan_bytes,
        error=conflict_error,
    )
    for staged_path, source_bytes in staged_source_bytes:
        write_or_validate_staged_bytes(
            staged_path,
            source_bytes,
            error=conflict_error,
        )
    if staged_agents_write is not None:
        write_or_validate_staged_bytes(
            staged_agents_write[0],
            staged_agents_write[1],
            error=conflict_error,
        )

    journal = {
        "schema_version": 1,
        "migration_id": migration_id,
        "status": "staged",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "target_plan_id": target_doc.frontmatter["plan_id"],
        "target_path": relative_project_path(root, target_doc.path),
        "staged_plan": relative_project_path(root, staged_plan),
        "target_sha256": sha256_bytes(staged_plan_bytes),
        "prepared_plan_sha256": manifest["prepared_plan_sha256"],
        "proposal_sha256": manifest["proposal_sha256"],
        "agents_diff_sha256": manifest["agents_diff_sha256"],
        "sources": staged_sources,
        "agents_rewrite": staged_agents,
        "git_baseline": manifest.get("git_baseline"),
        "completed_operations": [],
    }
    maybe_interrupt_before_transaction_journal("reconciliation")
    write_atomic(journal_path, yaml.safe_dump(journal, sort_keys=False))
    return journal_path


def write_journal(journal_path: Path, journal: dict[str, Any]) -> None:
    """Persist a migration journal after one idempotent operation."""
    journal["updated_at"] = utc_now()
    write_atomic(journal_path, yaml.safe_dump(journal, sort_keys=False))


def maybe_interrupt(operation: str) -> None:
    """Inject a deterministic test-only migration interruption."""
    if os.environ.get("WORKCTL_TEST_INTERRUPT_AFTER") == operation:
        raise WorkctlError(f"SIMULATED_MIGRATION_INTERRUPT: {operation}")


def record_operation(
    journal_path: Path,
    journal: dict[str, Any],
    operation: str,
) -> None:
    """Record one completed migration operation and honor test interruption."""
    completed = journal.setdefault("completed_operations", [])
    if not isinstance(completed, list):
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    if operation not in completed:
        completed.append(operation)
    journal["status"] = "applying"
    write_journal(journal_path, journal)
    maybe_interrupt(operation)


def preflight_reconciliation_recovery_inventory(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
) -> ReconciliationRecoveryInventory:
    """Authenticate every recovery path before the transaction can write."""
    migration_id = journal.get("migration_id")
    if not isinstance(migration_id, str) or MIGRATION_ID_RE.fullmatch(migration_id) is None:
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    _, staging_dir, expected_journal = reconciliation_transaction_paths(root, migration_id)
    if journal_path.resolve() != expected_journal.resolve():
        raise WorkctlError("INVALID_MIGRATION_JOURNAL_PATH")

    target_plan_id = journal.get("target_plan_id")
    if not isinstance(target_plan_id, str) or PLAN_ID_RE.fullmatch(target_plan_id) is None:
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    target_path_value = journal.get("target_path")
    if not isinstance(target_path_value, str):
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    target = checked_project_path(root, target_path_value)
    reject_legacy_plan_authority_path(root, target_path_value, target)
    if target_path_value != plan_relative_path(f"{target_plan_id}.md"):
        raise WorkctlError("INVALID_MIGRATION_TARGET_PATH")

    staged_plan_value = journal.get("staged_plan")
    if not isinstance(staged_plan_value, str):
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    staged_plan = checked_project_path(root, staged_plan_value)
    reject_legacy_plan_authority_path(root, staged_plan_value, staged_plan)
    expected_staged_plan = relative_project_path(root, staging_dir / "target-plan.md")
    if staged_plan_value != expected_staged_plan:
        raise WorkctlError("INVALID_MIGRATION_STAGED_PLAN_PATH")

    target_sha256 = journal.get("target_sha256")
    if not isinstance(target_sha256, str) or SHA256_RE.fullmatch(target_sha256) is None:
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    completed_operations = journal.get("completed_operations")
    if not isinstance(completed_operations, list) or not all(
        isinstance(operation, str) for operation in completed_operations
    ):
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")

    sources_value = journal.get("sources")
    if not isinstance(sources_value, list):
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    sources: list[dict[str, Any]] = []
    for source in sources_value:
        if not isinstance(source, dict):
            raise WorkctlError("INVALID_MIGRATION_JOURNAL")
        source_path_value = source.get("path")
        archive_path_value = source.get("archive_path")
        staged_path_value = source.get("staged_path")
        source_sha256 = source.get("sha256")
        if not all(
            isinstance(value, str)
            for value in (
                source_path_value,
                archive_path_value,
                staged_path_value,
                source_sha256,
            )
        ):
            raise WorkctlError("INVALID_MIGRATION_JOURNAL")
        assert isinstance(source_path_value, str)
        assert isinstance(archive_path_value, str)
        assert isinstance(staged_path_value, str)
        assert isinstance(source_sha256, str)
        if SHA256_RE.fullmatch(source_sha256) is None:
            raise WorkctlError("INVALID_MIGRATION_JOURNAL")

        source_path = checked_project_path(root, source_path_value)
        reject_legacy_plan_authority_path(root, source_path_value, source_path)
        archive_path = checked_project_path(root, archive_path_value)
        reject_legacy_plan_authority_path(root, archive_path_value, archive_path)
        if archive_path_value != archive_path_for_source(migration_id, source_path_value):
            raise WorkctlError(f"INVALID_MIGRATION_ARCHIVE_PATH: {source_path_value}")
        staged_path = checked_project_path(root, staged_path_value)
        reject_legacy_plan_authority_path(root, staged_path_value, staged_path)
        expected_staged_path = relative_project_path(
            root,
            staging_dir / "sources" / source_path_value,
        )
        if staged_path_value != expected_staged_path:
            raise WorkctlError(f"INVALID_MIGRATION_STAGED_SOURCE_PATH: {source_path_value}")
        sources.append(source)

    agents_value = journal.get("agents_rewrite")
    agents_record: dict[str, Any] | None = None
    if agents_value is not None:
        if not isinstance(agents_value, dict):
            raise WorkctlError("INVALID_MIGRATION_JOURNAL")
        agents_path_value = agents_value.get("path")
        staged_agents_value = agents_value.get("staged_path")
        original_sha256 = agents_value.get("sha256")
        replacement_sha256 = agents_value.get("replacement_sha256")
        if not all(
            isinstance(value, str)
            for value in (
                agents_path_value,
                staged_agents_value,
                original_sha256,
                replacement_sha256,
            )
        ):
            raise WorkctlError("INVALID_MIGRATION_JOURNAL")
        assert isinstance(agents_path_value, str)
        assert isinstance(staged_agents_value, str)
        assert isinstance(original_sha256, str)
        assert isinstance(replacement_sha256, str)
        agents_path = checked_project_path(root, agents_path_value)
        reject_legacy_plan_authority_path(root, agents_path_value, agents_path)
        if agents_path_value != "AGENTS.md":
            raise WorkctlError("INVALID_AGENTS_REWRITE_PATH")
        staged_agents = checked_project_path(root, staged_agents_value)
        reject_legacy_plan_authority_path(root, staged_agents_value, staged_agents)
        expected_staged_agents = relative_project_path(
            root,
            staging_dir / "agents-replacement.md",
        )
        if staged_agents_value != expected_staged_agents:
            raise WorkctlError("INVALID_STAGED_AGENTS_REWRITE_PATH")
        if (
            SHA256_RE.fullmatch(original_sha256) is None
            or SHA256_RE.fullmatch(replacement_sha256) is None
        ):
            raise WorkctlError("INVALID_MIGRATION_JOURNAL")
        agents_record = agents_value

    return ReconciliationRecoveryInventory(
        staged_plan=staged_plan,
        target=target,
        sources=sources,
        agents_record=agents_record,
    )


def preflight_reconciliation_recovery_content(
    root: Path,
    journal: dict[str, Any],
    inventory: ReconciliationRecoveryInventory,
    *,
    repair_committed: bool,
) -> None:
    """Check all recovery bytes before the first archive or pointer write."""
    target_sha256 = str(journal["target_sha256"])
    if sha256_file(inventory.staged_plan) != target_sha256:
        raise WorkctlError("STAGED_PLAN_HASH_MISMATCH")
    if inventory.target.exists() and sha256_file(inventory.target) != target_sha256:
        raise WorkctlError(f"TARGET_PLAN_CONFLICT: {journal['target_path']}")

    for source in inventory.sources:
        source_path_value = str(source["path"])
        expected_sha256 = str(source["sha256"])
        staged = checked_project_path(root, str(source["staged_path"]))
        if sha256_file(staged) != expected_sha256:
            raise WorkctlError(f"STAGED_SOURCE_HASH_MISMATCH: {source_path_value}")
        archive = checked_project_path(root, str(source["archive_path"]))
        if archive.exists() and sha256_file(archive) != expected_sha256 and not repair_committed:
            raise WorkctlError(f"ARCHIVE_HASH_MISMATCH: {source['archive_path']}")
        original = checked_project_path(root, source_path_value)
        pointer = pointer_text(
            source_path=source_path_value,
            canonical_path=str(journal["target_path"]),
            migration_id=str(journal["migration_id"]),
            archive_path=str(source["archive_path"]),
        )
        current_hash = sha256_file(original)
        if current_hash not in {
            expected_sha256,
            sha256_bytes(pointer.encode()),
        }:
            raise WorkctlError(f"SOURCE_DRIFT: {source_path_value}")

    agents_record = inventory.agents_record
    if agents_record is not None:
        staged_agents = checked_project_path(root, str(agents_record["staged_path"]))
        if sha256_file(staged_agents) != agents_record["replacement_sha256"]:
            raise WorkctlError("STAGED_AGENTS_REWRITE_HASH_MISMATCH")
        agents_path = checked_project_path(root, str(agents_record["path"]))
        if sha256_file(agents_path) not in {
            agents_record["sha256"],
            agents_record["replacement_sha256"],
        }:
            raise WorkctlError(f"SOURCE_DRIFT: {agents_record['path']}")


def ensure_archive(
    root: Path,
    source: dict[str, Any],
    *,
    repair: bool,
) -> None:
    """Create or verify one immutable source archive."""
    archive_path_value = str(source["archive_path"])
    archive = checked_project_path(root, archive_path_value)
    reject_legacy_plan_authority_path(root, archive_path_value, archive)
    staged_path_value = str(source["staged_path"])
    staged = checked_project_path(root, staged_path_value)
    reject_legacy_plan_authority_path(root, staged_path_value, staged)
    expected_hash = str(source["sha256"])
    if archive.exists():
        if sha256_file(archive) == expected_hash:
            return
        if not repair:
            raise WorkctlError(f"ARCHIVE_HASH_MISMATCH: {source['archive_path']}")
    if sha256_file(staged) != expected_hash:
        raise WorkctlError(f"STAGED_SOURCE_HASH_MISMATCH: {source['path']}")
    write_atomic_bytes(archive, staged.read_bytes())
    if sha256_file(archive) != expected_hash:
        raise WorkctlError(f"ARCHIVE_HASH_MISMATCH: {source['archive_path']}")


def ensure_pointer(root: Path, journal: dict[str, Any], source: dict[str, Any]) -> None:
    """Replace or verify one historical authority path as a pointer."""
    source_path_value = str(source["path"])
    original = checked_project_path(root, source_path_value)
    reject_legacy_plan_authority_path(root, source_path_value, original)
    pointer = pointer_text(
        source_path=source_path_value,
        canonical_path=str(journal["target_path"]),
        migration_id=str(journal["migration_id"]),
        archive_path=str(source["archive_path"]),
    )
    pointer_hash = sha256_bytes(pointer.encode())
    current_hash = sha256_file(original)
    if current_hash == pointer_hash:
        return
    if current_hash != source["sha256"]:
        raise WorkctlError(f"SOURCE_DRIFT: {source['path']}")
    write_atomic(original, pointer)


def ensure_agents_rewrite(root: Path, agents_record: dict[str, Any]) -> None:
    """Apply or verify the separately confirmed AGENTS.md rewrite."""
    target_path_value = str(agents_record["path"])
    target = checked_project_path(root, target_path_value)
    reject_legacy_plan_authority_path(root, target_path_value, target)
    if target_path_value != "AGENTS.md":
        raise WorkctlError("INVALID_AGENTS_REWRITE_PATH")
    staged_path_value = str(agents_record["staged_path"])
    staged = checked_project_path(root, staged_path_value)
    reject_legacy_plan_authority_path(root, staged_path_value, staged)
    if sha256_file(staged) != agents_record["replacement_sha256"]:
        raise WorkctlError("STAGED_AGENTS_REWRITE_HASH_MISMATCH")
    current_hash = sha256_file(target)
    if current_hash == agents_record["replacement_sha256"]:
        return
    if current_hash != agents_record["sha256"]:
        raise WorkctlError(f"SOURCE_DRIFT: {agents_record['path']}")
    write_atomic_bytes(target, staged.read_bytes())


def activated_index(root: Path, target_doc: PlanDocument) -> dict[str, Any]:
    """Build an index that activates the canonical Plan last."""
    plans: list[dict[str, Any]] = []
    if index_path(root).is_file():
        existing = load_yaml_file(index_path(root)).get("plans", [])
        if isinstance(existing, list):
            plans.extend(item for item in existing if isinstance(item, dict))
    plan_id = str(target_doc.frontmatter["plan_id"])
    plans = [item for item in plans if item.get("id") != plan_id]
    plans.append(
        {
            "id": plan_id,
            "path": target_doc.path.name,
            "title": target_doc.frontmatter["title"],
            "created_at": target_doc.frontmatter["created_at"],
        }
    )
    return {"schema_version": 1, "active_plan_id": plan_id, "plans": plans}


def validate_committed_migration(root: Path, journal_path: Path) -> None:
    """Authenticate a committed reconciliation without requiring schema-v3 bytes."""
    journal = load_yaml_file(journal_path)
    expected_keys = {
        "schema_version",
        "migration_id",
        "status",
        "created_at",
        "updated_at",
        "target_plan_id",
        "target_path",
        "staged_plan",
        "target_sha256",
        "prepared_plan_sha256",
        "proposal_sha256",
        "agents_diff_sha256",
        "sources",
        "agents_rewrite",
        "git_baseline",
        "completed_operations",
    }
    if (
        set(journal) != expected_keys
        or journal.get("schema_version") != 1
        or journal.get("status") != "committed"
        or not isinstance(journal.get("prepared_plan_sha256"), str)
        or SHA256_RE.fullmatch(str(journal["prepared_plan_sha256"])) is None
        or not isinstance(journal.get("proposal_sha256"), str)
        or SHA256_RE.fullmatch(str(journal["proposal_sha256"])) is None
        or (
            journal.get("git_baseline") is not None
            and not isinstance(journal.get("git_baseline"), str)
        )
    ):
        raise WorkctlError("MIGRATION_COMMITTED_STATE_INVALID")
    inventory = preflight_reconciliation_recovery_inventory(root, journal_path, journal)
    if sha256_file(inventory.staged_plan) != journal["target_sha256"]:
        raise WorkctlError("STAGED_PLAN_HASH_MISMATCH")
    staged_doc = load_plan(inventory.staged_plan)
    require_valid_candidate(staged_doc)
    authority = staged_doc.frontmatter.get("authority")
    if not isinstance(authority, dict):
        raise WorkctlError("MIGRATION_COMMITTED_BINDING_DRIFT")

    expected_operations: list[str] = []
    proposal_sources: list[dict[str, Any]] = []
    for source in inventory.sources:
        source_path_value = str(source["path"])
        expected_sha256 = str(source["sha256"])
        staged = checked_project_path(root, str(source["staged_path"]))
        archive = checked_project_path(root, str(source["archive_path"]))
        original = checked_project_path(root, source_path_value)
        pointer = pointer_text(
            source_path=source_path_value,
            canonical_path=str(journal["target_path"]),
            migration_id=str(journal["migration_id"]),
            archive_path=str(source["archive_path"]),
        )
        if sha256_file(staged) != expected_sha256:
            raise WorkctlError(f"STAGED_SOURCE_HASH_MISMATCH: {source_path_value}")
        if sha256_file(archive) != expected_sha256:
            raise WorkctlError(f"ARCHIVE_HASH_MISMATCH: {source['archive_path']}")
        if sha256_file(original) != sha256_bytes(pointer.encode()):
            raise WorkctlError(f"SOURCE_DRIFT: {source_path_value}")
        proposal_sources.append(
            {key: value for key, value in source.items() if key != "staged_path"}
        )
        expected_operations.extend([f"archive:{source_path_value}", f"pointer:{source_path_value}"])
    if authority.get("sources") != proposal_sources:
        raise WorkctlError("MIGRATION_COMMITTED_BINDING_DRIFT")

    agents_record = inventory.agents_record
    agents_proposal: dict[str, Any] | None = None
    if agents_record is not None:
        if set(agents_record) != {
            "path",
            "sha256",
            "replacement_file",
            "replacement_sha256",
            "staged_path",
        }:
            raise WorkctlError("MIGRATION_COMMITTED_STATE_INVALID")
        agents_diff_sha256 = journal.get("agents_diff_sha256")
        if (
            not isinstance(agents_diff_sha256, str)
            or SHA256_RE.fullmatch(agents_diff_sha256) is None
        ):
            raise WorkctlError("MIGRATION_COMMITTED_STATE_INVALID")
        staged_agents = checked_project_path(root, str(agents_record["staged_path"]))
        agents_path = checked_project_path(root, str(agents_record["path"]))
        replacement_sha256 = str(agents_record["replacement_sha256"])
        if sha256_file(staged_agents) != replacement_sha256:
            raise WorkctlError("STAGED_AGENTS_REWRITE_HASH_MISMATCH")
        if sha256_file(agents_path) != replacement_sha256:
            raise WorkctlError(f"SOURCE_DRIFT: {agents_record['path']}")
        agents_proposal = {
            "path": agents_record["path"],
            "sha256": agents_record["sha256"],
            "replacement_sha256": replacement_sha256,
            "diff_sha256": agents_diff_sha256,
        }
        expected_operations.append("agents-rewrite")
    elif journal.get("agents_diff_sha256") is not None:
        raise WorkctlError("MIGRATION_COMMITTED_STATE_INVALID")

    proposal_payload = {
        "migration_id": journal["migration_id"],
        "target_path": journal["target_path"],
        "prepared_plan_sha256": journal["prepared_plan_sha256"],
        "git_baseline": journal["git_baseline"],
        "sources": proposal_sources,
        "agents_rewrite": agents_proposal,
    }
    proposal_sha256 = sha256_bytes(
        json.dumps(proposal_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    authority_confirmations = authority.get("confirmations")
    if not isinstance(authority_confirmations, dict):
        raise WorkctlError("MIGRATION_COMMITTED_BINDING_DRIFT")
    staged_confirmations = confirmations(staged_doc.frontmatter)
    baseline_id = authority_confirmations.get("baseline")
    baseline_confirmation = (
        staged_confirmations.get(baseline_id) if isinstance(baseline_id, str) else None
    )
    if (
        proposal_sha256 != journal["proposal_sha256"]
        or baseline_confirmation is None
        or baseline_confirmation.get("status") != "accepted"
        or baseline_confirmation.get("evidence_sha256") != proposal_sha256
    ):
        raise WorkctlError("MIGRATION_COMMITTED_BINDING_DRIFT")
    if agents_record is not None:
        agents_id = authority_confirmations.get("agents_rewrite")
        agents_confirmation = (
            staged_confirmations.get(agents_id) if isinstance(agents_id, str) else None
        )
        if (
            agents_confirmation is None
            or agents_confirmation.get("status") != "accepted"
            or agents_confirmation.get("evidence_sha256") != journal["agents_diff_sha256"]
        ):
            raise WorkctlError("MIGRATION_COMMITTED_BINDING_DRIFT")

    expected_operations.extend(["target-plan", "index-activation"])
    if journal.get("completed_operations") != expected_operations:
        raise WorkctlError("MIGRATION_COMMITTED_OPERATIONS_INVALID")

    index = load_yaml_file(index_path(root))
    if index.get("active_plan_id") != journal["target_plan_id"]:
        raise WorkctlError("MIGRATION_COMMITTED_INDEX_DRIFT")
    target = inventory.target
    if target.is_symlink() or not target.is_file():
        raise WorkctlError("MIGRATION_COMMITTED_TARGET_MISSING")
    canonical_doc = load_plan(target)
    require_valid_candidate(canonical_doc)
    if canonical_doc.frontmatter.get("plan_id") != journal["target_plan_id"]:
        raise WorkctlError("MIGRATION_COMMITTED_TARGET_DRIFT")
    metadata_errors = authority_metadata_errors(root, canonical_doc)
    if metadata_errors:
        raise WorkctlError(f"INVALID_MIGRATION_LINEAGE: {'; '.join(metadata_errors)}")
    report = inspect_authority(root, ignore_journal=journal_path)
    if report.state != "GOVERNED_ACTIVE":
        raise WorkctlError(
            f"MIGRATION_COMMITTED_STATE_INVALID: {report.state}; {'; '.join(report.blockers)}"
        )


def resume_migration(
    root: Path,
    journal_path: Path,
    *,
    repair_committed: bool = False,
) -> None:
    """Idempotently roll a staged migration forward to index activation."""
    journal = load_yaml_file(journal_path)
    if journal.get("status") == "committed" and not repair_committed:
        validate_committed_migration(root, journal_path)
        print(f"MIGRATION_ALREADY_COMMITTED {journal['migration_id']}")
        return
    expected_git_baseline = journal.get("git_baseline")
    if not repair_committed and expected_git_baseline is not None:
        actual_git_baseline = current_git_baseline(root)
        if actual_git_baseline != expected_git_baseline:
            raise WorkctlError(
                "GIT_BASELINE_MISMATCH: "
                f"expected {expected_git_baseline}, found {actual_git_baseline}"
            )
    inventory = preflight_reconciliation_recovery_inventory(root, journal_path, journal)
    preflight_reconciliation_recovery_content(
        root,
        journal,
        inventory,
        repair_committed=repair_committed,
    )
    for source in inventory.sources:
        archive_operation = f"archive:{source['path']}"
        ensure_archive(root, source, repair=repair_committed)
        record_operation(journal_path, journal, archive_operation)
        pointer_operation = f"pointer:{source['path']}"
        ensure_pointer(root, journal, source)
        record_operation(journal_path, journal, pointer_operation)
    agents_record = inventory.agents_record
    if agents_record is not None:
        ensure_agents_rewrite(root, agents_record)
        record_operation(journal_path, journal, "agents-rewrite")
    staged_plan = inventory.staged_plan
    target = inventory.target
    reject_legacy_plan_authority_path(root, str(journal["target_path"]), target)
    if target.exists() and sha256_file(target) != journal["target_sha256"]:
        raise WorkctlError(f"TARGET_PLAN_CONFLICT: {journal['target_path']}")
    if not target.exists():
        write_atomic_bytes(target, staged_plan.read_bytes())
    record_operation(journal_path, journal, "target-plan")
    canonical_doc = load_plan(target)
    metadata_errors = authority_metadata_errors(root, canonical_doc)
    if metadata_errors:
        raise WorkctlError(f"INVALID_MIGRATION_LINEAGE: {'; '.join(metadata_errors)}")
    write_atomic(
        index_path(root),
        yaml.safe_dump(activated_index(root, canonical_doc), sort_keys=False),
    )
    record_operation(journal_path, journal, "index-activation")
    report = inspect_authority(root, ignore_journal=journal_path)
    if report.state != "GOVERNED_ACTIVE":
        raise WorkctlError(
            f"MIGRATION_ACTIVATED_BUT_INVALID: {report.state}; {'; '.join(report.blockers)}"
        )
    journal["status"] = "committed"
    write_journal(journal_path, journal)
    print(f"MIGRATION_COMMITTED {journal['migration_id']} plan={journal['target_plan_id']}")


def retirement_requirements(
    frontmatter: dict[str, Any],
) -> tuple[dict[str, set[str]], set[str]]:
    """Return every unfinished collection item and singleton retirement blocker."""
    collections: dict[str, set[str]] = {}
    terminal_statuses = {
        "obligations": {"verified", "skipped"},
        "tasks": VERIFIED_TASK_STATES,
        "validations": {"verified", "skipped"},
        "artifacts": {"final"},
        "unknowns": {"resolved"},
    }
    for field, terminal in terminal_statuses.items():
        collections[field] = {
            str(item["id"])
            for item in frontmatter.get(field, [])
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("status") not in terminal
        }
    scope = frontmatter.get("scope", {})
    exclusions = scope.get("exclude", []) if isinstance(scope, dict) else []
    collections["exclusions"] = {
        str(item["description"])
        for item in exclusions
        if isinstance(item, dict)
        and isinstance(item.get("description"), str)
        and item.get("disposition") in BLOCKING_EXCLUSION_DISPOSITIONS
    }
    collections["confirmations"] = {
        str(item["id"])
        for item in confirmations(frontmatter).values()
        if item.get("status") == "pending"
    }

    singletons: set[str] = set()
    delivery = frontmatter.get("delivery")
    if not isinstance(delivery, dict) or delivery.get("status") != "complete":
        singletons.add("delivery")
    activation = frontmatter.get("activation")
    if not isinstance(activation, dict) or activation.get("status") not in {
        "not_required",
        "declined",
    }:
        singletons.add("activation")
    for field in ("route", "handoff"):
        value = frontmatter.get(field)
        if not isinstance(value, dict) or value.get("route_status") != "terminal":
            singletons.add(field)
    return collections, singletons


def validate_retirement_disposition(
    record: object,
    *,
    label: str,
    confirmation_ref: str | None,
) -> dict[str, Any]:
    """Validate one explicit retirement disposition and its authority reference."""
    if not isinstance(record, dict):
        raise WorkctlError(f"INVALID_RETIREMENT_DISPOSITION: {label}")
    disposition = record.get("disposition")
    reason = record.get("reason")
    resolution_ref = record.get("resolution_ref")
    if disposition not in RETIREMENT_DISPOSITIONS:
        raise WorkctlError(f"INVALID_RETIREMENT_DISPOSITION: {label}")
    if not isinstance(reason, str) or not reason:
        raise WorkctlError(f"RETIREMENT_DISPOSITION_REASON_REQUIRED: {label}")
    if not valid_reference(resolution_ref):
        raise WorkctlError(f"RETIREMENT_DISPOSITION_REF_REQUIRED: {label}")
    if confirmation_ref is not None and resolution_ref != confirmation_ref:
        raise WorkctlError(f"RETIREMENT_DISPOSITION_REF_MISMATCH: {label}")
    return copy.deepcopy(record)


def normalize_retirement_dispositions(
    frontmatter: dict[str, Any],
    raw_dispositions: object,
    *,
    confirmation_ref: str | None,
) -> dict[str, Any]:
    """Require an exact disposition for every unfinished Plan surface."""
    if not isinstance(raw_dispositions, dict):
        raise WorkctlError("RETIREMENT_DISPOSITIONS_REQUIRED")
    collection_requirements, singleton_requirements = retirement_requirements(frontmatter)
    normalized: dict[str, Any] = {}
    identity_fields = {
        "exclusions": "description",
        "obligations": "id",
        "tasks": "id",
        "validations": "id",
        "artifacts": "id",
        "unknowns": "id",
        "confirmations": "id",
    }
    for field, identity_field in identity_fields.items():
        raw_records = raw_dispositions.get(field, [])
        if not isinstance(raw_records, list):
            raise WorkctlError(f"INVALID_RETIREMENT_DISPOSITIONS: {field}")
        by_identity: dict[str, dict[str, Any]] = {}
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                raise WorkctlError(f"INVALID_RETIREMENT_DISPOSITION: {field}")
            identity = raw_record.get(identity_field)
            if not isinstance(identity, str) or not identity:
                raise WorkctlError(f"RETIREMENT_DISPOSITION_ID_REQUIRED: {field} {identity_field}")
            if identity in by_identity:
                raise WorkctlError(f"RETIREMENT_DISPOSITION_DUPLICATE: {field} {identity}")
            by_identity[identity] = validate_retirement_disposition(
                raw_record,
                label=f"{field} {identity}",
                confirmation_ref=confirmation_ref,
            )
        required = collection_requirements[field]
        missing = sorted(required - set(by_identity))
        unexpected = sorted(set(by_identity) - required)
        if missing:
            raise WorkctlError(f"RETIREMENT_DISPOSITION_MISSING: {field} {missing[0]}")
        if unexpected:
            raise WorkctlError(f"RETIREMENT_DISPOSITION_UNEXPECTED: {field} {unexpected[0]}")
        if by_identity:
            normalized[field] = [by_identity[key] for key in sorted(by_identity)]

    for field in ("delivery", "activation", "route", "handoff"):
        raw_record = raw_dispositions.get(field)
        if field in singleton_requirements:
            if raw_record is None:
                raise WorkctlError(f"RETIREMENT_DISPOSITION_MISSING: {field}")
            normalized[field] = validate_retirement_disposition(
                raw_record,
                label=field,
                confirmation_ref=confirmation_ref,
            )
        elif raw_record is not None:
            raise WorkctlError(f"RETIREMENT_DISPOSITION_UNEXPECTED: {field}")
    return normalized


def retirement_proposal_payload(
    retirement_id: str,
    source_plan: dict[str, Any],
    index_baseline: dict[str, Any],
    *,
    reason: str,
    dispositions: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical payload authorized by ``C-PLAN-RETIREMENT``."""
    return {
        "retirement_id": retirement_id,
        "source_plan": source_plan,
        "index_baseline": index_baseline,
        "reason": reason,
        "dispositions": dispositions,
        "index_outcome": "NO_PLAN",
    }


def prepare_retirement(
    root: Path,
    manifest_path: Path,
    *,
    require_confirmations: bool,
) -> dict[str, Any]:
    """Validate an active Plan retirement manifest and bind its exact proposal."""
    manifest = load_yaml_file(manifest_path)
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "plan-retirement":
        raise WorkctlError("INVALID_RETIREMENT_MANIFEST_SCHEMA")
    retirement_id = manifest.get("retirement_id")
    if not isinstance(retirement_id, str) or RETIREMENT_ID_RE.fullmatch(retirement_id) is None:
        raise WorkctlError("INVALID_RETIREMENT_ID")
    reason = manifest.get("reason")
    if not isinstance(reason, str) or not reason:
        raise WorkctlError("RETIREMENT_REASON_REQUIRED")

    report = inspect_authority(root)
    if report.state != "GOVERNED_ACTIVE":
        raise WorkctlError(
            f"AUTHORITY_BLOCKED: {report.state}; allowed={','.join(report.allowed_commands)}"
        )
    source_doc = load_plan(active_plan_path(root))
    if source_doc.frontmatter.get("schema_version") != 4:
        raise WorkctlError("RETIREMENT_SOURCE_MUST_USE_SCHEMA_VERSION_4")
    if source_doc.frontmatter.get("status") != "active":
        raise WorkctlError("RETIREMENT_SOURCE_NOT_ACTIVE")
    source_relative = relative_project_path(root, source_doc.path)
    source_candidate = next(
        (candidate for candidate in report.candidates if candidate.path == source_relative),
        None,
    )
    if source_candidate is not None and "project-rule-explicit" in source_candidate.signals:
        raise WorkctlError(f"RETIREMENT_PROJECT_RULE_REWRITE_REQUIRED: {source_relative}")

    source_value = manifest.get("source_plan")
    if not isinstance(source_value, dict):
        raise WorkctlError("MANIFEST_SOURCE_PLAN_REQUIRED")
    if source_value.get("path") != source_relative:
        raise WorkctlError(
            f"RETIREMENT_SOURCE_PATH_MISMATCH: expected {source_relative}, "
            f"found {source_value.get('path')}"
        )
    if source_value.get("plan_id") != source_doc.frontmatter.get("plan_id"):
        raise WorkctlError("RETIREMENT_SOURCE_ID_MISMATCH")
    if source_value.get("revision") != source_doc.frontmatter.get("revision"):
        raise WorkctlError("RETIREMENT_SOURCE_REVISION_MISMATCH")
    actual_source_sha256 = sha256_file(source_doc.path)
    if source_value.get("sha256") != actual_source_sha256:
        raise WorkctlError(
            "RETIREMENT_SOURCE_HASH_MISMATCH: "
            f"expected {actual_source_sha256}, found {source_value.get('sha256')}"
        )
    source_record = {
        "path": source_relative,
        "plan_id": str(source_doc.frontmatter["plan_id"]),
        "revision": source_doc.frontmatter["revision"],
        "sha256": actual_source_sha256,
    }

    index_value = manifest.get("index_baseline")
    if not isinstance(index_value, dict):
        raise WorkctlError("MANIFEST_INDEX_BASELINE_REQUIRED")
    if index_value.get("active_plan_id") != source_doc.frontmatter.get("plan_id"):
        raise WorkctlError("INDEX_ACTIVE_PLAN_MISMATCH")
    actual_index_sha256 = sha256_file(index_path(root))
    if index_value.get("sha256") != actual_index_sha256:
        raise WorkctlError(
            f"INDEX_BASELINE_DRIFT: expected {actual_index_sha256}, "
            f"found {index_value.get('sha256')}"
        )
    index_baseline = {
        "active_plan_id": str(source_doc.frontmatter["plan_id"]),
        "sha256": actual_index_sha256,
    }

    confirmations_value = manifest.get("confirmations")
    if not isinstance(confirmations_value, dict):
        if require_confirmations:
            raise WorkctlError("MANIFEST_CONFIRMATIONS_REQUIRED")
        confirmations_value = {}
    retirement_confirmation = confirmation_from_manifest(
        confirmations_value,
        "retirement",
        required=require_confirmations,
    )
    confirmation_ref = retirement_confirmation[1] if retirement_confirmation else None
    dispositions = normalize_retirement_dispositions(
        source_doc.frontmatter,
        manifest.get("dispositions"),
        confirmation_ref=confirmation_ref,
    )
    proposal_payload = retirement_proposal_payload(
        retirement_id,
        source_record,
        index_baseline,
        reason=reason,
        dispositions=dispositions,
    )
    proposal_sha256 = sha256_bytes(
        json.dumps(proposal_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    if retirement_confirmation is None:
        retirement_confirmation = (
            "C-PLAN-RETIREMENT",
            "PENDING",
            "PENDING",
            proposal_sha256,
        )
    confirmation_id, confirmation_ref, accepted_at, evidence_sha256 = retirement_confirmation
    if confirmation_id != "C-PLAN-RETIREMENT":
        raise WorkctlError("RETIREMENT_CONFIRMATION_ID_MUST_BE_C-PLAN-RETIREMENT")
    if require_confirmations and evidence_sha256 != proposal_sha256:
        raise WorkctlError(f"CONFIRMATION_EVIDENCE_MISMATCH: retirement expected {proposal_sha256}")

    manifest["retirement_id"] = retirement_id
    manifest["source_plan"] = source_record
    manifest["index_baseline"] = index_baseline
    manifest["reason"] = reason
    manifest["dispositions"] = dispositions
    manifest["proposal_sha256"] = proposal_sha256
    manifest["retirement_confirmation"] = accepted_confirmation(
        confirmation_id,
        confirmation_ref,
        accepted_at,
        evidence_sha256,
        "Approve retirement of the exact obsolete Plan without claiming completion.",
        intervention_kind="external_authority",
    )
    return manifest


def retired_plan_document(
    root: Path,
    source_doc: PlanDocument,
    manifest: dict[str, Any],
    archive_path: Path,
) -> PlanDocument:
    """Build the immutable, non-authoritative retired Plan representation."""
    frontmatter = copy.deepcopy(source_doc.frontmatter)
    confirmation = manifest.get("retirement_confirmation")
    if not isinstance(confirmation, dict) or confirmation.get("status") != "accepted":
        raise WorkctlError("RETIREMENT_CONFIRMATION_REQUIRED")
    add_or_replace_confirmation(frontmatter, confirmation)
    frontmatter["status"] = "retired"
    frontmatter["retirement"] = {
        "retirement_id": manifest["retirement_id"],
        "reason": manifest["reason"],
        "retired_at": confirmation["accepted_at"],
        "proposal_sha256": manifest["proposal_sha256"],
        "original_path": relative_project_path(root, archive_path),
        "original_sha256": manifest["source_plan"]["sha256"],
        "confirmation": {
            "id": confirmation["id"],
            "ref": confirmation["ref"],
            "evidence_sha256": confirmation["evidence_sha256"],
        },
        "dispositions": copy.deepcopy(manifest["dispositions"]),
    }
    bump_revision(
        frontmatter,
        kind="retirement",
        rationale=str(manifest["reason"]),
        confirmation_id="C-PLAN-RETIREMENT",
    )
    retired = PlanDocument(source_doc.path, frontmatter, source_doc.body)
    require_valid_candidate(retired)
    return retired


def stage_retirement(
    root: Path,
    manifest: dict[str, Any],
) -> Path:
    """Stage original and retired bytes, then create a recovery journal."""
    retirement_id = str(manifest["retirement_id"])
    _retirement_dir, staging_dir, archive_path, journal_path = retirement_transaction_paths(
        root, retirement_id
    )
    if journal_path.exists():
        raise WorkctlError(f"RETIREMENT_JOURNAL_EXISTS: {retirement_id}")
    source = cast(dict[str, Any], manifest["source_plan"])
    source_path = checked_project_path(root, str(source["path"]))
    if sha256_file(source_path) != source["sha256"]:
        raise WorkctlError(f"RETIREMENT_SOURCE_DRIFT: {source['path']}")
    index_baseline = cast(dict[str, Any], manifest["index_baseline"])
    if sha256_file(index_path(root)) != index_baseline["sha256"]:
        raise WorkctlError("INDEX_BASELINE_DRIFT")

    ensure_directory_durable(staging_dir)
    write_atomic_bytes(archive_path, source_path.read_bytes())
    source_doc = load_plan(source_path)
    retired_doc = retired_plan_document(root, source_doc, manifest, archive_path)
    staged_plan = staging_dir / "retired-plan.md"
    write_atomic_bytes(staged_plan, dump_plan(retired_doc).encode())
    journal = {
        "schema_version": 1,
        "kind": "plan-retirement-journal",
        "retirement_id": retirement_id,
        "status": "staged",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "source_plan": source,
        "index_baseline": index_baseline,
        "reason": manifest["reason"],
        "dispositions": manifest["dispositions"],
        "proposal_sha256": manifest["proposal_sha256"],
        "retirement_confirmation": manifest["retirement_confirmation"],
        "archive_path": relative_project_path(root, archive_path),
        "staged_plan": relative_project_path(root, staged_plan),
        "retired_plan_sha256": sha256_file(staged_plan),
        "completed_operations": [],
    }
    write_atomic(journal_path, yaml.safe_dump(journal, sort_keys=False))
    return journal_path


def validate_retirement_journal(
    root: Path,
    journal_path: Path,
) -> tuple[dict[str, Any], PlanDocument]:
    """Authenticate every retirement recovery input before writing."""
    journal = load_yaml_file(journal_path)
    retirement_id = journal.get("retirement_id")
    if (
        journal.get("schema_version") != 1
        or journal.get("kind") != "plan-retirement-journal"
        or not isinstance(retirement_id, str)
        or RETIREMENT_ID_RE.fullmatch(retirement_id) is None
    ):
        raise WorkctlError("INVALID_RETIREMENT_JOURNAL")
    expected_keys = {
        "schema_version",
        "kind",
        "retirement_id",
        "status",
        "created_at",
        "updated_at",
        "source_plan",
        "index_baseline",
        "reason",
        "dispositions",
        "proposal_sha256",
        "retirement_confirmation",
        "archive_path",
        "staged_plan",
        "retired_plan_sha256",
        "completed_operations",
    }
    if (
        set(journal) != expected_keys
        or journal.get("status") not in {"staged", "applying", "committed"}
        or not isinstance(journal.get("completed_operations"), list)
        or len(journal["completed_operations"]) != len(set(journal["completed_operations"]))
        or not set(journal["completed_operations"])
        <= {"retirement-source-plan", "retirement-index-removal"}
    ):
        raise WorkctlError("INVALID_RETIREMENT_JOURNAL")
    _retirement_dir, staging_dir, archive_path, expected_journal_path = (
        retirement_transaction_paths(root, retirement_id)
    )
    if journal_path.resolve() != expected_journal_path.resolve() or journal.get(
        "archive_path"
    ) != relative_project_path(root, archive_path):
        raise WorkctlError("INVALID_RETIREMENT_JOURNAL")
    source = journal.get("source_plan")
    index_baseline = journal.get("index_baseline")
    dispositions = journal.get("dispositions")
    confirmation = journal.get("retirement_confirmation")
    if (
        not isinstance(source, dict)
        or not isinstance(index_baseline, dict)
        or not isinstance(dispositions, dict)
        or not isinstance(confirmation, dict)
    ):
        raise WorkctlError("INVALID_RETIREMENT_JOURNAL")
    if sha256_file(archive_path) != source.get("sha256"):
        raise WorkctlError("RETIREMENT_ARCHIVE_HASH_MISMATCH")
    staged_plan = checked_project_path(root, str(journal.get("staged_plan")))
    if staged_plan != staging_dir / "retired-plan.md":
        raise WorkctlError("INVALID_RETIREMENT_JOURNAL")
    if sha256_file(staged_plan) != journal.get("retired_plan_sha256"):
        raise WorkctlError("STAGED_RETIREMENT_PLAN_HASH_MISMATCH")
    retired_doc = load_plan(staged_plan)
    retirement = retired_doc.frontmatter.get("retirement")
    retired_confirmation = retirement.get("confirmation") if isinstance(retirement, dict) else None
    if (
        retired_doc.frontmatter.get("status") != "retired"
        or not isinstance(retirement, dict)
        or not isinstance(retired_confirmation, dict)
        or retirement.get("retirement_id") != retirement_id
        or retirement.get("proposal_sha256") != journal.get("proposal_sha256")
        or retirement.get("dispositions") != dispositions
    ):
        raise WorkctlError("INVALID_RETIREMENT_JOURNAL")
    if (
        retired_confirmation.get("id") != confirmation.get("id")
        or retired_confirmation.get("ref") != confirmation.get("ref")
        or retired_confirmation.get("evidence_sha256") != confirmation.get("evidence_sha256")
        or retirement.get("retired_at") != confirmation.get("accepted_at")
    ):
        raise WorkctlError("RETIREMENT_CONFIRMATION_MISMATCH")
    proposal = retirement_proposal_payload(
        retirement_id,
        source,
        index_baseline,
        reason=str(journal.get("reason")),
        dispositions=dispositions,
    )
    proposal_sha256 = sha256_bytes(
        json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode()
    )
    if (
        proposal_sha256 != journal.get("proposal_sha256")
        or confirmation.get("id") != "C-PLAN-RETIREMENT"
        or confirmation.get("status") != "accepted"
        or confirmation.get("evidence_sha256") != proposal_sha256
    ):
        raise WorkctlError("RETIREMENT_PROPOSAL_HASH_MISMATCH")
    require_valid_candidate(retired_doc)
    return journal, retired_doc


def resume_retirement(root: Path, journal_path: Path) -> None:
    """Idempotently retire the source and remove its index authority last."""
    journal, retired_doc = validate_retirement_journal(root, journal_path)
    retirement_id = str(journal["retirement_id"])
    if journal.get("status") == "committed":
        print(f"PLAN_RETIREMENT_ALREADY_COMMITTED {retirement_id}")
        return
    source = cast(dict[str, Any], journal["source_plan"])
    index_baseline = cast(dict[str, Any], journal["index_baseline"])
    source_path = checked_project_path(root, str(source["path"]))
    current_source_sha256 = sha256_file(source_path)
    retired_sha256 = str(journal["retired_plan_sha256"])
    if current_source_sha256 not in {source["sha256"], retired_sha256}:
        raise WorkctlError(f"RETIREMENT_SOURCE_DRIFT: {source['path']}")
    if index_path(root).is_file():
        if sha256_file(index_path(root)) != index_baseline["sha256"]:
            raise WorkctlError("INDEX_BASELINE_DRIFT")
    elif current_source_sha256 != retired_sha256:
        raise WorkctlError("RETIREMENT_INDEX_REMOVED_BEFORE_SOURCE")

    if current_source_sha256 == source["sha256"]:
        write_atomic_bytes(source_path, retired_doc.path.read_bytes())
    record_operation(journal_path, journal, "retirement-source-plan")

    if index_path(root).is_file():
        durable_unlink(index_path(root))
    record_operation(journal_path, journal, "retirement-index-removal")

    report = inspect_authority(root, ignore_journal=journal_path)
    validation_errors = validate_plan(root, ignore_journal=journal_path)
    if report.state != "UNMANAGED_EMPTY" or validation_errors:
        details = [*report.blockers, *validation_errors]
        raise WorkctlError(f"RETIREMENT_APPLIED_BUT_INVALID: {report.state}; {'; '.join(details)}")
    journal["status"] = "committed"
    write_journal(journal_path, journal)
    print(f"PLAN_RETIREMENT_COMMITTED {retirement_id} plan={source['plan_id']}")


def cmd_plan_retire_apply(args: argparse.Namespace) -> None:
    """Dry-run or apply a confirmed active Plan retirement."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    if args.dry_run:
        manifest = prepare_retirement(
            root,
            manifest_path,
            require_confirmations=False,
        )
        payload = {
            "retirement_id": manifest["retirement_id"],
            "source_plan": manifest["source_plan"],
            "index_baseline": manifest["index_baseline"],
            "index_outcome": "NO_PLAN",
            "dispositions": manifest["dispositions"],
            "proposal_sha256": manifest["proposal_sha256"],
            "confirmations_required": ["C-PLAN-RETIREMENT"],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    with lock(root):
        if (
            incomplete_migration_journals(root)
            or incomplete_rollover_journals(root)
            or incomplete_retirement_journals(root)
            or incomplete_contract_upgrade_journals(root)
            or incomplete_reconcile_upgrade_journals(root)
        ):
            raise WorkctlError("MIGRATION_RECOVERY_REQUIRED")
        manifest = prepare_retirement(
            root,
            manifest_path,
            require_confirmations=True,
        )
        journal_path = stage_retirement(root, manifest)
        resume_retirement(root, journal_path)


def cmd_plan_retire_recover(args: argparse.Namespace) -> None:
    """Recover one named retirement transaction idempotently."""
    root = project_root()
    retirement_id = args.retirement_id
    if RETIREMENT_ID_RE.fullmatch(retirement_id) is None:
        raise WorkctlError("INVALID_RETIREMENT_ID")
    with lock(root):
        if incomplete_migration_journals(root) or incomplete_rollover_journals(root):
            raise WorkctlError("MIGRATION_RECOVERY_REQUIRED")
        _retirement_dir, _staging_dir, _archive_path, journal_path = retirement_transaction_paths(
            root, retirement_id
        )
        if not journal_path.is_file():
            raise WorkctlError(f"RETIREMENT_JOURNAL_NOT_FOUND: {retirement_id}")
        resume_retirement(root, journal_path)


def require_terminal_rollover_source(
    root: Path,
    source_doc: PlanDocument,
    report: AuthorityReport | None = None,
) -> None:
    """Require a complete, terminal, closeout-ready rollover predecessor."""
    if source_doc.frontmatter.get("status") != "complete":
        raise WorkctlError("ROLLOVER_SOURCE_NOT_COMPLETE")
    route = source_doc.frontmatter.get("route")
    if not isinstance(route, dict) or route.get("route_status") != "terminal":
        raise WorkctlError("ROLLOVER_SOURCE_NOT_TERMINAL")
    if report is not None:
        validation_errors = validate_plan(root)
        readiness_report = report
    else:
        validation_errors = validate_frontmatter(
            source_doc.frontmatter,
            reject_blocking_artifacts=True,
        )
        validation_errors.extend(authority_metadata_errors(root, source_doc))
        readiness_report = AuthorityReport(
            "GOVERNED_ACTIVE",
            [],
            [],
            allowed_commands_for_state("GOVERNED_ACTIVE"),
        )
    readiness = closeout_readiness(
        source_doc.frontmatter,
        readiness_report,
        validation_errors,
    )
    if source_doc.frontmatter.get("schema_version") == 4:
        readiness["blockers"] = [
            blocker
            for blocker in readiness["blockers"]
            if not str(blocker).startswith("intake is ")
            and not str(blocker).startswith("legacy unknown contract:")
        ]
        readiness["ready"] = not readiness["blockers"]
    if not readiness["ready"]:
        raise WorkctlError(
            "ROLLOVER_SOURCE_NOT_CLOSEOUT_READY: "
            + "; ".join(str(blocker) for blocker in readiness["blockers"])
        )


def rollover_proposal_payload(
    rollover_id: str,
    source_plan: dict[str, Any],
    index_baseline: dict[str, Any],
    *,
    target_path: str,
    target_plan_id: str,
    target_revision: object,
    prepared_plan_sha256: str,
) -> dict[str, Any]:
    """Build the stable successor contract authorized by ``C-PLAN-ROLLOVER``."""
    return {
        "rollover_id": rollover_id,
        "source_plan": source_plan,
        "index_baseline": index_baseline,
        "target_plan": {
            "path": target_path,
            "plan_id": target_plan_id,
            "revision": target_revision,
            "prepared_plan_sha256": prepared_plan_sha256,
        },
    }


def prepare_rollover(
    root: Path,
    manifest_path: Path,
    *,
    require_confirmations: bool,
) -> tuple[dict[str, Any], PlanDocument]:
    """Validate a terminal rollover manifest and build the successor Plan."""
    manifest = load_yaml_file(manifest_path)
    if manifest.get("schema_version") != 1:
        raise WorkctlError("INVALID_ROLLOVER_MANIFEST_SCHEMA")
    rollover_id = manifest.get("rollover_id")
    if not isinstance(rollover_id, str) or ROLLOVER_ID_RE.fullmatch(rollover_id) is None:
        raise WorkctlError("INVALID_ROLLOVER_ID")

    report = inspect_authority(root)
    if report.state != "GOVERNED_ACTIVE":
        raise WorkctlError(
            f"AUTHORITY_BLOCKED: {report.state}; allowed={','.join(report.allowed_commands)}"
        )
    source_doc = load_plan(active_plan_path(root))
    require_terminal_rollover_source(root, source_doc, report)
    source_relative = relative_project_path(root, source_doc.path)
    source_candidate = next(
        (candidate for candidate in report.candidates if candidate.path == source_relative),
        None,
    )
    if source_candidate is not None and "project-rule-explicit" in source_candidate.signals:
        raise WorkctlError(f"ROLLOVER_PROJECT_RULE_REWRITE_REQUIRED: {source_relative}")

    source_value = manifest.get("source_plan")
    if not isinstance(source_value, dict):
        raise WorkctlError("MANIFEST_SOURCE_PLAN_REQUIRED")
    expected_source_path = source_value.get("path")
    expected_source_id = source_value.get("plan_id")
    expected_source_revision = source_value.get("revision")
    expected_source_sha256 = source_value.get("sha256")
    if expected_source_path != source_relative:
        raise WorkctlError(
            f"ROLLOVER_SOURCE_PATH_MISMATCH: expected {source_relative}, "
            f"found {expected_source_path}"
        )
    if expected_source_id != source_doc.frontmatter.get("plan_id"):
        raise WorkctlError(
            "ROLLOVER_SOURCE_ID_MISMATCH: "
            f"expected {source_doc.frontmatter.get('plan_id')}, found {expected_source_id}"
        )
    if expected_source_revision != source_doc.frontmatter.get("revision"):
        raise WorkctlError(
            "ROLLOVER_SOURCE_REVISION_MISMATCH: "
            f"expected {source_doc.frontmatter.get('revision')}, "
            f"found {expected_source_revision}"
        )
    actual_source_sha256 = sha256_file(source_doc.path)
    if expected_source_sha256 != actual_source_sha256:
        raise WorkctlError(
            "ROLLOVER_SOURCE_HASH_MISMATCH: "
            f"expected {actual_source_sha256}, found {expected_source_sha256}"
        )
    source_record = {
        "path": source_relative,
        "plan_id": str(expected_source_id),
        "revision": expected_source_revision,
        "sha256": actual_source_sha256,
    }

    index_value = manifest.get("index_baseline")
    if not isinstance(index_value, dict):
        raise WorkctlError("MANIFEST_INDEX_BASELINE_REQUIRED")
    expected_index_active = index_value.get("active_plan_id")
    expected_index_sha256 = index_value.get("sha256")
    source_plan_id = source_doc.frontmatter.get("plan_id")
    if expected_index_active != source_plan_id:
        raise WorkctlError(
            f"INDEX_ACTIVE_PLAN_MISMATCH: expected {source_plan_id}, found {expected_index_active}"
        )
    actual_index_sha256 = sha256_file(index_path(root))
    if expected_index_sha256 != actual_index_sha256:
        raise WorkctlError(
            f"INDEX_BASELINE_DRIFT: expected {expected_index_sha256}, found {actual_index_sha256}"
        )
    index_baseline = {
        "active_plan_id": str(source_plan_id),
        "sha256": actual_index_sha256,
    }

    target_value = manifest.get("target_plan")
    if not isinstance(target_value, dict):
        raise WorkctlError("MANIFEST_TARGET_PLAN_REQUIRED")
    prepared_file = target_value.get("prepared_file")
    if not isinstance(prepared_file, str):
        raise WorkctlError("MANIFEST_TARGET_PREPARED_FILE_REQUIRED")
    prepared_path = manifest_input_path(manifest_path, prepared_file)
    prepared_doc = load_plan(prepared_path)
    prepared_sha256 = sha256_file(prepared_path)
    target_plan_id = prepared_doc.frontmatter.get("plan_id")
    target_revision = prepared_doc.frontmatter.get("revision")
    if target_value.get("plan_id") != target_plan_id:
        raise WorkctlError("TARGET_PLAN_ID_DRIFT")
    if target_value.get("revision") != target_revision:
        raise WorkctlError("TARGET_PLAN_REVISION_DRIFT")
    if target_value.get("sha256") != prepared_sha256:
        raise WorkctlError("TARGET_PLAN_HASH_DRIFT")
    if not isinstance(target_plan_id, str) or PLAN_ID_RE.fullmatch(target_plan_id) is None:
        raise WorkctlError("INVALID_TARGET_PLAN_ID")
    if target_plan_id == source_plan_id:
        raise WorkctlError("TARGET_PLAN_MUST_BE_NEW")
    if prepared_doc.frontmatter.get("schema_version") != 4:
        raise WorkctlError("ROLLOVER_TARGET_MUST_USE_SCHEMA_VERSION_4")
    if prepared_doc.frontmatter.get("status") != "active":
        raise WorkctlError("TARGET_PLAN_MUST_BE_ACTIVE")
    target_relative = plan_relative_path(f"{target_plan_id}.md")
    target_path = checked_project_path(root, target_relative)
    if target_path.exists():
        raise WorkctlError(f"TARGET_PLAN_CONFLICT: {target_relative}")

    target_frontmatter = copy.deepcopy(prepared_doc.frontmatter)
    intake_binding: dict[str, object] | None = None
    target_contract_sha256: str | None = None
    if STRICT_INITIAL_INTAKE_REQUIRED:
        proposal = embedded_initial_intake(manifest)
        session_receipt = session_receipt_for_turn(
            root,
            str(proposal["turn_receipt_sha256"]),
            require_current_controller=True,
        )
        validate_current_intake_proposal(
            root,
            target_frontmatter,
            proposal,
            session_receipt=cast(Mapping[str, object], session_receipt),
        )
        record = inject_initial_intake(target_frontmatter, proposal)
        intake_binding = initial_intake_binding(proposal, record)
    target_frontmatter["authority"] = {
        "model": AUTHORITY_MODEL,
        "state": AUTHORITY_STATE,
        "canonical_plan_id": target_plan_id,
        "rollover_id": rollover_id,
        "predecessor": source_record,
        "sources": [],
        "confirmations": {"rollover": "C-PLAN-ROLLOVER"},
    }
    if STRICT_INITIAL_INTAKE_REQUIRED:
        unsigned_target = PlanDocument(
            target_path,
            copy.deepcopy(target_frontmatter),
            prepared_doc.body,
        )
        target_contract_sha256 = sha256_bytes(dump_plan(unsigned_target).encode())
    proposal_payload = rollover_proposal_payload(
        rollover_id,
        source_record,
        index_baseline,
        target_path=target_relative,
        target_plan_id=target_plan_id,
        target_revision=target_revision,
        prepared_plan_sha256=prepared_sha256,
    )
    proposal_sha256 = sha256_bytes(
        json.dumps(proposal_payload, sort_keys=True, separators=(",", ":")).encode()
    )

    confirmations_value = manifest.get("confirmations")
    if not isinstance(confirmations_value, dict):
        if require_confirmations:
            raise WorkctlError("MANIFEST_CONFIRMATIONS_REQUIRED")
        confirmations_value = {}
    rollover_confirmation = confirmation_from_manifest(
        confirmations_value,
        "rollover",
        required=require_confirmations,
    )
    if rollover_confirmation is None:
        rollover_confirmation = (
            "C-PLAN-ROLLOVER",
            "PENDING",
            "PENDING",
            proposal_sha256,
        )
    confirmation_id, confirmation_ref, accepted_at, evidence_sha256 = rollover_confirmation
    if confirmation_id != "C-PLAN-ROLLOVER":
        raise WorkctlError("ROLLOVER_CONFIRMATION_ID_MUST_BE_C-PLAN-ROLLOVER")
    if require_confirmations and evidence_sha256 != proposal_sha256:
        raise WorkctlError(f"CONFIRMATION_EVIDENCE_MISMATCH: rollover expected {proposal_sha256}")

    add_or_replace_confirmation(
        target_frontmatter,
        accepted_confirmation(
            confirmation_id,
            confirmation_ref,
            accepted_at,
            evidence_sha256,
            "Approve the terminal predecessor and exact successor Plan contract.",
        ),
    )
    cast(dict[str, str], target_frontmatter["authority"]["confirmations"])["rollover"] = (
        confirmation_id
    )
    target_doc = PlanDocument(target_path, target_frontmatter, prepared_doc.body)
    require_valid_candidate(target_doc)
    require_strict_intervention_contract(target_doc.frontmatter)
    require_new_plan_reviews_pending(target_doc.frontmatter)

    manifest["rollover_id"] = rollover_id
    manifest["source_plan"] = source_record
    manifest["index_baseline"] = index_baseline
    manifest["target_relative"] = target_relative
    manifest["prepared_path"] = str(prepared_path)
    manifest["prepared_plan_sha256"] = prepared_sha256
    manifest["proposal_sha256"] = proposal_sha256
    if STRICT_INITIAL_INTAKE_REQUIRED:
        assert intake_binding is not None
        assert target_contract_sha256 is not None
        manifest["intake_binding"] = intake_binding
        manifest["target_contract_sha256"] = target_contract_sha256
    return manifest, target_doc


def stage_rollover(
    root: Path,
    manifest: dict[str, Any],
    target_doc: PlanDocument,
) -> Path:
    """Stage immutable rollover inputs and create the recovery journal."""
    rollover_id = str(manifest["rollover_id"])
    _rollover_dir, staging_dir, journal_path = rollover_transaction_paths(
        root,
        rollover_id,
    )
    if journal_path.exists():
        raise WorkctlError(f"ROLLOVER_JOURNAL_EXISTS: {rollover_id}")

    source = manifest["source_plan"]
    assert isinstance(source, dict)
    source_path = checked_project_path(root, str(source["path"]))
    if sha256_file(source_path) != source["sha256"]:
        raise WorkctlError(f"ROLLOVER_SOURCE_DRIFT: {source['path']}")
    index_baseline = manifest["index_baseline"]
    assert isinstance(index_baseline, dict)
    if sha256_file(index_path(root)) != index_baseline["sha256"]:
        raise WorkctlError("INDEX_BASELINE_DRIFT")

    prepared_path = Path(str(manifest["prepared_path"]))
    if sha256_file(prepared_path) != manifest["prepared_plan_sha256"]:
        raise WorkctlError("TARGET_PLAN_HASH_DRIFT")
    staged_prepared_plan = staging_dir / "prepared-plan.md"
    write_atomic_bytes(staged_prepared_plan, prepared_path.read_bytes())
    staged_plan = staging_dir / "target-plan.md"
    write_atomic(staged_plan, dump_plan(target_doc))
    staged_index = staging_dir / "target-index.yaml"
    write_atomic(
        staged_index,
        yaml.safe_dump(activated_index(root, target_doc), sort_keys=False),
    )
    journal = {
        "schema_version": 1,
        "kind": "rollover",
        "rollover_id": rollover_id,
        "status": "staged",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "source_plan": source,
        "index_baseline": index_baseline,
        "target_plan_id": target_doc.frontmatter["plan_id"],
        "target_path": relative_project_path(root, target_doc.path),
        "staged_prepared_plan": relative_project_path(root, staged_prepared_plan),
        "staged_plan": relative_project_path(root, staged_plan),
        "target_sha256": sha256_file(staged_plan),
        "staged_index": relative_project_path(root, staged_index),
        "target_index_sha256": sha256_file(staged_index),
        "prepared_plan_sha256": manifest["prepared_plan_sha256"],
        "proposal_sha256": manifest["proposal_sha256"],
        "confirmation_payload_version": ROLLOVER_CONFIRMATION_PAYLOAD_VERSION,
        "rollover_confirmation": confirmations(target_doc.frontmatter)["C-PLAN-ROLLOVER"],
        "completed_operations": [],
    }
    if STRICT_INITIAL_INTAKE_REQUIRED:
        intake_binding = cast(dict[str, object], manifest["intake_binding"])
        journal["intake_binding"] = intake_binding
        journal["target_contract_sha256"] = manifest["target_contract_sha256"]
        journal["transaction_binding_sha256"] = transaction_binding_digest(
            transaction_kind="plan-rollover",
            transaction_id=rollover_id,
            plan_id=str(target_doc.frontmatter["plan_id"]),
            prepared_plan_sha256=str(manifest["prepared_plan_sha256"]),
            target_plan_sha256=str(journal["target_sha256"]),
            intake_binding=intake_binding,
        )
    write_atomic(journal_path, yaml.safe_dump(journal, sort_keys=False))
    return journal_path


def validate_rollover_journal(
    root: Path,
    journal_path: Path,
) -> tuple[dict[str, Any], PlanDocument]:
    """Validate a rollover journal and its staged authority contract."""
    journal = load_yaml_file(journal_path)
    rollover_id = journal.get("rollover_id")
    if (
        journal.get("schema_version") != 1
        or journal.get("kind") != "rollover"
        or journal.get("status") not in {"staged", "applying", "committed"}
        or not isinstance(rollover_id, str)
        or ROLLOVER_ID_RE.fullmatch(rollover_id) is None
        or journal_path.name != f"{rollover_id}.yaml"
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")

    source = journal.get("source_plan")
    index_baseline = journal.get("index_baseline")
    if not isinstance(source, dict) or not isinstance(index_baseline, dict):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    completed_operations = journal.get("completed_operations")
    if not isinstance(completed_operations, list) or not all(
        isinstance(operation, str) for operation in completed_operations
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    source_plan_id = source.get("plan_id")
    source_revision = source.get("revision")
    source_path_value = source.get("path")
    source_sha256 = source.get("sha256")
    if (
        not isinstance(source_plan_id, str)
        or PLAN_ID_RE.fullmatch(source_plan_id) is None
        or type(source_revision) is not int
        or source_revision < 1
        or not isinstance(source_path_value, str)
        or not isinstance(source_sha256, str)
        or SHA256_RE.fullmatch(source_sha256) is None
        or index_baseline.get("active_plan_id") != source_plan_id
        or not isinstance(index_baseline.get("sha256"), str)
        or SHA256_RE.fullmatch(str(index_baseline.get("sha256"))) is None
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")

    target_plan_id = journal.get("target_plan_id")
    target_path_value = journal.get("target_path")
    if (
        not isinstance(target_plan_id, str)
        or PLAN_ID_RE.fullmatch(target_plan_id) is None
        or target_path_value != plan_relative_path(f"{target_plan_id}.md")
        or target_plan_id == source_plan_id
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    expected_staging_root = plan_relative_path(".rollovers", rollover_id, "staging")
    if (
        journal.get("staged_prepared_plan") != f"{expected_staging_root}/prepared-plan.md"
        or journal.get("staged_plan") != f"{expected_staging_root}/target-plan.md"
        or journal.get("staged_index") != f"{expected_staging_root}/target-index.yaml"
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    for field in (
        "target_sha256",
        "target_index_sha256",
        "prepared_plan_sha256",
        "proposal_sha256",
    ):
        value = journal.get(field)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    confirmation_payload_version = journal.get("confirmation_payload_version", 1)
    if type(confirmation_payload_version) is not int or confirmation_payload_version not in {
        1,
        ROLLOVER_CONFIRMATION_PAYLOAD_VERSION,
    }:
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    intake_binding: dict[str, object] | None = None
    target_contract_sha256: str | None = None
    if STRICT_INITIAL_INTAKE_REQUIRED:
        binding_value = journal.get("intake_binding")
        target_contract_value = journal.get("target_contract_sha256")
        transaction_binding_value = journal.get("transaction_binding_sha256")
        if (
            not isinstance(binding_value, dict)
            or not isinstance(target_contract_value, str)
            or SHA256_RE.fullmatch(target_contract_value) is None
            or not isinstance(transaction_binding_value, str)
            or SHA256_RE.fullmatch(transaction_binding_value) is None
        ):
            raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
        intake_binding = cast(dict[str, object], binding_value)
        target_contract_sha256 = target_contract_value
        if (
            transaction_binding_digest(
                transaction_kind="plan-rollover",
                transaction_id=rollover_id,
                plan_id=target_plan_id,
                prepared_plan_sha256=str(journal["prepared_plan_sha256"]),
                target_plan_sha256=str(journal["target_sha256"]),
                intake_binding=intake_binding,
            )
            != transaction_binding_value
        ):
            raise WorkctlError("ROLLOVER_TRANSACTION_BINDING_MISMATCH")

    staged_prepared_plan = checked_project_path(
        root,
        str(journal["staged_prepared_plan"]),
    )
    staged_plan = checked_project_path(root, str(journal["staged_plan"]))
    staged_index = checked_project_path(root, str(journal["staged_index"]))
    if sha256_file(staged_prepared_plan) != journal["prepared_plan_sha256"]:
        raise WorkctlError("STAGED_PREPARED_PLAN_HASH_MISMATCH")
    if sha256_file(staged_plan) != journal["target_sha256"]:
        raise WorkctlError("STAGED_ROLLOVER_PLAN_HASH_MISMATCH")
    if sha256_file(staged_index) != journal["target_index_sha256"]:
        raise WorkctlError("STAGED_ROLLOVER_INDEX_HASH_MISMATCH")
    prepared_doc = load_plan(staged_prepared_plan)
    target_doc = load_plan(staged_plan)
    if prepared_doc.frontmatter.get("plan_id") != target_plan_id or prepared_doc.frontmatter.get(
        "revision"
    ) != target_doc.frontmatter.get("revision"):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    expected_proposal = rollover_proposal_payload(
        rollover_id,
        source,
        index_baseline,
        target_path=str(target_path_value),
        target_plan_id=target_plan_id,
        target_revision=prepared_doc.frontmatter.get("revision"),
        prepared_plan_sha256=str(journal["prepared_plan_sha256"]),
    )
    if confirmation_payload_version == 1:
        if intake_binding is None or target_contract_sha256 is None:
            raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
        expected_proposal["intake_binding"] = intake_binding
        cast(dict[str, Any], expected_proposal["target_plan"])["target_contract_sha256"] = (
            target_contract_sha256
        )
    expected_proposal_sha256 = sha256_bytes(
        json.dumps(expected_proposal, sort_keys=True, separators=(",", ":")).encode()
    )
    if expected_proposal_sha256 != journal["proposal_sha256"]:
        raise WorkctlError("ROLLOVER_PROPOSAL_HASH_MISMATCH")

    authority = target_doc.frontmatter.get("authority")
    if (
        target_doc.frontmatter.get("plan_id") != target_plan_id
        or not isinstance(authority, dict)
        or authority.get("rollover_id") != rollover_id
        or authority.get("predecessor") != source
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    authority_confirmations = authority.get("confirmations")
    confirmation_id = (
        authority_confirmations.get("rollover")
        if isinstance(authority_confirmations, dict)
        else None
    )
    confirmation = (
        confirmations(target_doc.frontmatter).get(confirmation_id)
        if isinstance(confirmation_id, str)
        else None
    )
    journal_confirmation = journal.get("rollover_confirmation")
    if (
        confirmation_id != "C-PLAN-ROLLOVER"
        or confirmation is None
        or not isinstance(journal_confirmation, dict)
        or confirmation != journal_confirmation
        or confirmation.get("status") != "accepted"
        or confirmation.get("evidence_sha256") != journal["proposal_sha256"]
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    if STRICT_INITIAL_INTAKE_REQUIRED:
        records = intake_records(target_doc.frontmatter)
        if (
            intake_binding is None
            or len(records) != 1
            or records[0].get("record_sha256") != intake_binding.get("intake_record_sha256")
            or records[0].get("request_ref") != intake_binding.get("request_ref")
            or records[0].get("decision_basis_sha256")
            != intake_binding.get("decision_basis_sha256")
        ):
            raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
        unsigned_frontmatter = copy.deepcopy(target_doc.frontmatter)
        unsigned_confirmations = unsigned_frontmatter.get("confirmations")
        if not isinstance(unsigned_confirmations, dict) or not isinstance(
            unsigned_confirmations.get("required"), list
        ):
            raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
        unsigned_confirmations["required"] = [
            item
            for item in unsigned_confirmations["required"]
            if not isinstance(item, dict) or item.get("id") != "C-PLAN-ROLLOVER"
        ]
        expected_unsigned_frontmatter = copy.deepcopy(prepared_doc.frontmatter)
        expected_unsigned_frontmatter["intake"] = copy.deepcopy(target_doc.frontmatter["intake"])
        expected_unsigned_frontmatter["authority"] = {
            "model": AUTHORITY_MODEL,
            "state": AUTHORITY_STATE,
            "canonical_plan_id": target_plan_id,
            "rollover_id": rollover_id,
            "predecessor": source,
            "sources": [],
            "confirmations": {"rollover": "C-PLAN-ROLLOVER"},
        }
        expected_unsigned_doc = PlanDocument(
            staged_plan,
            expected_unsigned_frontmatter,
            prepared_doc.body,
        )
        unsigned_contract_bytes_match = sha256_bytes(
            dump_plan(expected_unsigned_doc).encode()
        ) == target_contract_sha256
        legacy_unsigned_semantics_match = (
            confirmation_payload_version == 1
            and unsigned_frontmatter == expected_unsigned_frontmatter
            and target_doc.body == prepared_doc.body
        )
        if not unsigned_contract_bytes_match and not legacy_unsigned_semantics_match:
            raise WorkctlError("ROLLOVER_TARGET_CONTRACT_HASH_MISMATCH")
    expected_frontmatter = copy.deepcopy(prepared_doc.frontmatter)
    if STRICT_INITIAL_INTAKE_REQUIRED:
        expected_frontmatter["intake"] = copy.deepcopy(target_doc.frontmatter["intake"])
    add_or_replace_confirmation(expected_frontmatter, journal_confirmation)
    expected_frontmatter["authority"] = {
        "model": AUTHORITY_MODEL,
        "state": AUTHORITY_STATE,
        "canonical_plan_id": target_plan_id,
        "rollover_id": rollover_id,
        "predecessor": source,
        "sources": [],
        "confirmations": {"rollover": "C-PLAN-ROLLOVER"},
    }
    expected_target_doc = PlanDocument(
        staged_plan,
        expected_frontmatter,
        prepared_doc.body,
    )
    target_bytes_match = staged_plan.read_bytes() == dump_plan(expected_target_doc).encode()
    legacy_versionless_semantics_match = (
        confirmation_payload_version == 1
        and target_doc.frontmatter == expected_frontmatter
        and target_doc.body == prepared_doc.body
    )
    # Versionless rollover journals may carry bytes produced by the old dumper.
    # Their staged hash and transaction binding still protect the exact file.
    if not target_bytes_match and not legacy_versionless_semantics_match:
        raise WorkctlError("STAGED_ROLLOVER_TARGET_CONTRACT_MISMATCH")

    staged_index_value = load_yaml_file(staged_index)
    indexed_target = next(
        (
            item
            for item in staged_index_value.get("plans", [])
            if isinstance(item, dict) and item.get("id") == target_plan_id
        ),
        None,
    )
    if (
        staged_index_value.get("active_plan_id") != target_plan_id
        or not isinstance(indexed_target, dict)
        or indexed_target.get("path") != f"{target_plan_id}.md"
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    return journal, target_doc


def resume_rollover(root: Path, journal_path: Path) -> None:
    """Idempotently roll a staged successor forward to index-last activation."""
    journal, staged_target_doc = validate_rollover_journal(root, journal_path)
    if journal.get("status") == "committed":
        print(f"ROLLOVER_ALREADY_COMMITTED {journal['rollover_id']}")
        return
    rollover_id = str(journal["rollover_id"])

    source = journal.get("source_plan")
    index_baseline = journal.get("index_baseline")
    if not isinstance(source, dict) or not isinstance(index_baseline, dict):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    source_path = checked_project_path(root, str(source.get("path")))
    if sha256_file(source_path) != source.get("sha256"):
        raise WorkctlError(f"ROLLOVER_SOURCE_DRIFT: {source.get('path')}")
    source_doc = load_plan(source_path)
    if source_doc.frontmatter.get("plan_id") != source.get("plan_id") or source_doc.frontmatter.get(
        "revision"
    ) != source.get("revision"):
        raise WorkctlError("ROLLOVER_SOURCE_METADATA_DRIFT")
    require_terminal_rollover_source(root, source_doc)

    staged_plan = staged_target_doc.path
    staged_index = checked_project_path(root, str(journal["staged_index"]))

    current_index_sha256 = sha256_file(index_path(root))
    expected_index_sha256 = index_baseline.get("sha256")
    target_index_sha256 = journal.get("target_index_sha256")
    if current_index_sha256 not in {expected_index_sha256, target_index_sha256}:
        raise WorkctlError("INDEX_BASELINE_DRIFT")
    target = checked_project_path(root, str(journal.get("target_path")))
    if target.exists() and sha256_file(target) != journal.get("target_sha256"):
        raise WorkctlError(f"TARGET_PLAN_CONFLICT: {journal.get('target_path')}")
    if not target.exists():
        write_atomic_bytes(target, staged_plan.read_bytes())
    record_operation(journal_path, journal, "rollover-target-plan")

    if current_index_sha256 == expected_index_sha256:
        write_atomic_bytes(index_path(root), staged_index.read_bytes())
    record_operation(journal_path, journal, "rollover-index-activation")

    report = inspect_authority(root, ignore_journal=journal_path)
    validation_errors = validate_plan(root, ignore_journal=journal_path)
    if report.state != "GOVERNED_ACTIVE" or validation_errors:
        details = [*report.blockers, *validation_errors]
        raise WorkctlError(f"ROLLOVER_ACTIVATED_BUT_INVALID: {report.state}; {'; '.join(details)}")
    journal["status"] = "committed"
    write_journal(journal_path, journal)
    print(f"ROLLOVER_COMMITTED {rollover_id} plan={journal['target_plan_id']}")


def cmd_plan_rollover_apply(args: argparse.Namespace) -> None:
    """Dry-run or apply a confirmed terminal Plan rollover."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    if args.dry_run:
        manifest, target_doc = prepare_rollover(
            root,
            manifest_path,
            require_confirmations=False,
        )
        payload = {
            "rollover_id": manifest["rollover_id"],
            "source_plan": manifest["source_plan"],
            "index_baseline": manifest["index_baseline"],
            "target_plan": {
                "path": relative_project_path(root, target_doc.path),
                "plan_id": target_doc.frontmatter["plan_id"],
                "revision": target_doc.frontmatter["revision"],
                "prepared_plan_sha256": manifest["prepared_plan_sha256"],
            },
            "proposal_sha256": manifest["proposal_sha256"],
            "confirmations_required": ["C-PLAN-ROLLOVER"],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    with lock(root):
        if (
            incomplete_migration_journals(root)
            or incomplete_rollover_journals(root)
            or incomplete_retirement_journals(root)
            or incomplete_contract_upgrade_journals(root)
            or incomplete_reconcile_upgrade_journals(root)
        ):
            raise WorkctlError("MIGRATION_RECOVERY_REQUIRED")
        manifest, target_doc = prepare_rollover(
            root,
            manifest_path,
            require_confirmations=True,
        )
        journal_path = stage_rollover(root, manifest, target_doc)
        resume_rollover(root, journal_path)


def cmd_plan_rollover_recover(args: argparse.Namespace) -> None:
    """Recover one named rollover transaction idempotently."""
    root = project_root()
    rollover_id = args.rollover_id
    if ROLLOVER_ID_RE.fullmatch(rollover_id) is None:
        raise WorkctlError("INVALID_ROLLOVER_ID")
    with lock(root):
        if incomplete_retirement_journals(root):
            raise WorkctlError("RETIREMENT_RECOVERY_REQUIRED")
        if incomplete_migration_journals(root):
            raise WorkctlError("MIGRATION_RECOVERY_REQUIRED")
        _rollover_dir, _staging_dir, journal_path = rollover_transaction_paths(
            root,
            rollover_id,
        )
        if not journal_path.is_file():
            raise WorkctlError(f"ROLLOVER_JOURNAL_NOT_FOUND: {rollover_id}")
        resume_rollover(root, journal_path)


def cmd_plan_reconcile_apply(args: argparse.Namespace) -> None:
    """Apply a confirmed, prehashed reconciliation transaction."""
    root = project_root()
    manifest_path = Path(args.manifest).resolve()
    if args.dry_run:
        manifest, target_doc, diff_text = prepare_reconciliation(
            root,
            manifest_path,
            require_confirmations=False,
        )
        payload = {
            "migration_id": manifest["migration_id"],
            "target_plan": relative_project_path(root, target_doc.path),
            "prepared_plan_sha256": manifest["prepared_plan_sha256"],
            "proposal_sha256": manifest["proposal_sha256"],
            "sources": manifest["sources"],
            "git_baseline": manifest.get("git_baseline"),
            "agents_diff": diff_text,
            "agents_diff_sha256": manifest["agents_diff_sha256"],
            "confirmations_required": [
                "C-MIGRATION-BASELINE",
                *(["C-AGENTS-REWRITE"] if diff_text is not None else []),
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    with lock(root):
        if (
            incomplete_migration_journals(root)
            or incomplete_rollover_journals(root)
            or incomplete_retirement_journals(root)
            or incomplete_contract_upgrade_journals(root)
            or incomplete_reconcile_upgrade_journals(root)
        ):
            raise WorkctlError("MIGRATION_RECOVERY_REQUIRED")
        manifest, target_doc, _diff_text = prepare_reconciliation(
            root,
            manifest_path,
            require_confirmations=True,
        )
        report = inspect_authority(root)
        if report.state == "GOVERNED_ACTIVE":
            raise WorkctlError("RECONCILIATION_NOT_REQUIRED")
        journal_path = stage_reconciliation(root, manifest, target_doc)
        resume_migration(root, journal_path)


def cmd_plan_reconcile_recover(args: argparse.Namespace) -> None:
    """Recover the only incomplete migration or a named migration."""
    root = project_root()
    with lock(root):
        if incomplete_retirement_journals(root):
            raise WorkctlError("RETIREMENT_RECOVERY_REQUIRED")
        if incomplete_rollover_journals(root):
            raise WorkctlError("ROLLOVER_RECOVERY_REQUIRED")
        report = inspect_authority(root)
        journals = incomplete_migration_journals(root)
        if args.migration_id:
            candidate = plan_dir(root) / ".migrations" / f"{args.migration_id}.yaml"
            journals = [candidate] if candidate.is_file() else []
        elif not journals and report.state == "MIGRATION_RECOVERY_REQUIRED":
            try:
                active_doc = load_plan(active_plan_path(root))
            except WorkctlError:
                active_doc = None
            authority = active_doc.frontmatter.get("authority") if active_doc is not None else None
            migration_id = authority.get("migration_id") if isinstance(authority, dict) else None
            if isinstance(migration_id, str):
                candidate = plan_dir(root) / ".migrations" / f"{migration_id}.yaml"
                if candidate.is_file():
                    journals = [candidate]
        if not journals:
            raise WorkctlError("NO_INCOMPLETE_MIGRATION")
        if len(journals) != 1:
            raise WorkctlError("MIGRATION_ID_REQUIRED")
        journal = load_yaml_file(journals[0])
        repair_committed = journal.get("status") == "committed"
        if repair_committed and report.state != "MIGRATION_RECOVERY_REQUIRED":
            raise WorkctlError("COMMITTED_MIGRATION_REPAIR_NOT_REQUIRED")
        resume_migration(root, journals[0], repair_committed=repair_committed)


def add_current_intake_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared trusted-turn advancement arguments."""
    parser.add_argument("--turn-receipt-sha256")
    parser.add_argument("--expected-intake-sha256")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workctl")
    parser.add_argument(
        "--receipt-sha256",
        help="SHA256 of the exact current SessionStart READY receipt.",
    )
    sub = parser.add_subparsers(dest="domain", required=True)

    help_command = sub.add_parser("help")
    help_command.add_argument(
        "workflow",
        nargs="?",
        choices=[
            "plan",
            "task",
            "evidence",
            "action",
            "migrate",
            "migration",
            "goal",
            "gate",
            "truth",
            "review",
            "risk",
            "worktree",
            "doctor",
        ],
    )
    help_command.set_defaults(func=cmd_workflow_help)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--older-than-hours", type=int, default=24)
    doctor.add_argument("--clean-stale-transactions", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    goal_command = sub.add_parser("goal")
    goal_sub = goal_command.add_subparsers(dest="goal_action", required=True)
    goal_init = goal_sub.add_parser("init")
    goal_init.add_argument("--plan-id")
    goal_init.add_argument("--title")
    goal_init_source = goal_init.add_mutually_exclusive_group(required=True)
    goal_init_source.add_argument("--stdin", action="store_true")
    goal_init_source.add_argument("--from-file")
    goal_init.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    goal_init.set_defaults(func=cmd_goal_init)
    goal_show = goal_sub.add_parser("show")
    goal_show.set_defaults(func=cmd_goal_show)
    goal_revise = goal_sub.add_parser("revise")
    goal_revise.add_argument("--manifest", required=True)
    goal_revise.set_defaults(func=cmd_plan_contract_revise)
    goal_close = goal_sub.add_parser("close")
    goal_close.add_argument("--expected-revision", type=int, required=True)
    goal_close.add_argument("--evidence-manifest")
    goal_close.add_argument("--finalize-route", action="store_true")
    goal_close.add_argument("--confirmation")
    add_current_intake_args(goal_close)
    goal_close.set_defaults(func=cmd_plan_complete)

    gate_command = sub.add_parser("gate")
    gate_sub = gate_command.add_subparsers(dest="gate_action", required=True)
    gate_list = gate_sub.add_parser("list")
    gate_list.set_defaults(func=cmd_gate_list)
    gate_check = gate_sub.add_parser("check")
    gate_check.add_argument("--gate-id", required=True)
    gate_check.set_defaults(func=cmd_gate_check)
    gate_open = gate_sub.add_parser("open")
    gate_open.add_argument("--confirmation-id", required=True)
    gate_open.add_argument("--description", required=True)
    gate_open.add_argument("--status", default="pending")
    gate_open.add_argument("--ref")
    gate_open.add_argument("--intervention-kind", choices=sorted(INTERVENTION_KINDS), required=True)
    gate_open.add_argument("--blocks", action="append", required=True)
    gate_open.add_argument("--basis-ref", required=True)
    gate_open.add_argument("--basis-sha256")
    gate_open.add_argument("--action-kind", choices=sorted(HIGH_IMPACT_ACTION_KINDS))
    gate_open.add_argument("--expected-revision", type=int, required=True)
    gate_open.set_defaults(func=cmd_plan_confirmation_add)
    for gate_action, decision in (("satisfy", "accepted"), ("waive", "declined")):
        gate_decide = gate_sub.add_parser(gate_action)
        gate_decide.add_argument("--confirmation-id", required=True)
        gate_decide.add_argument("--ref", required=True)
        gate_decide.add_argument("--evidence-sha256")
        gate_decide.add_argument("--expected-revision", type=int, required=True)
        add_current_intake_args(gate_decide)
        gate_decide.set_defaults(
            func=cmd_gate_satisfy if decision == "accepted" else cmd_gate_waive
        )

    truth_command = sub.add_parser("truth")
    truth_sub = truth_command.add_subparsers(dest="truth_action", required=True)
    truth_list = truth_sub.add_parser("list")
    truth_list.set_defaults(func=cmd_truth_list)
    truth_conflicts = truth_sub.add_parser("conflicts")
    truth_conflicts.set_defaults(func=cmd_truth_conflicts)
    for truth_action in ("add", "resolve"):
        truth_edit = truth_sub.add_parser(truth_action)
        truth_edit.add_argument("--manifest", required=True)
        truth_edit.set_defaults(func=cmd_plan_contract_revise)

    review_command = sub.add_parser("review")
    review_sub = review_command.add_subparsers(dest="review_action", required=True)
    review_request = review_sub.add_parser("request")
    review_request.set_defaults(func=cmd_review_request)
    review_status = review_sub.add_parser("status")
    review_status.set_defaults(func=cmd_review_status)
    review_acquisition = review_sub.add_parser("acquisition")
    review_acquisition_sub = review_acquisition.add_subparsers(
        dest="review_acquisition_action",
        required=True,
    )

    def add_review_acquisition_scope_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--target-ref", required=True)
        parser.add_argument("--mechanism", required=True)
        parser.add_argument("--review-input-sha256", required=True)

    review_acquisition_check = review_acquisition_sub.add_parser("check")
    add_review_acquisition_scope_args(review_acquisition_check)
    review_acquisition_check.set_defaults(func=cmd_review_acquisition_check)
    review_acquisition_status = review_acquisition_sub.add_parser("status")
    review_acquisition_status.add_argument("--target-ref")
    review_acquisition_status.add_argument("--mechanism")
    review_acquisition_status.set_defaults(func=cmd_review_acquisition_status)
    review_acquisition_record = review_acquisition_sub.add_parser("record-failure")
    add_review_acquisition_scope_args(review_acquisition_record)
    review_acquisition_record.add_argument("--attempt-ref", required=True)
    review_acquisition_record.add_argument("--exit-code", type=int, required=True)
    review_acquisition_record.add_argument(
        "--failure-class",
        choices=["auto", *sorted(REVIEWER_FAILURE_CLASSES)],
        default="auto",
    )
    review_acquisition_record.add_argument("--summary")
    review_acquisition_record.add_argument("--failure-stdin", action="store_true")
    review_acquisition_record.add_argument("--failure-from-file")
    review_acquisition_record.add_argument("--cooldown-seconds", type=int, default=900)
    review_acquisition_record.add_argument("--idempotency-key")
    review_acquisition_record.add_argument("--dry-run", action="store_true")
    review_acquisition_record.set_defaults(func=cmd_review_acquisition_record_failure)
    review_attach = review_sub.add_parser("attach")
    review_attach.add_argument("--manifest", required=True)
    review_attach.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(review_attach)
    review_attach.set_defaults(func=cmd_plan_independent_review_record)

    evidence_command = sub.add_parser("evidence")
    evidence_sub = evidence_command.add_subparsers(dest="evidence_action", required=True)
    evidence_capture = evidence_sub.add_parser("capture")
    evidence_capture.add_argument("--task")
    evidence_capture.add_argument("--kind", required=True)
    evidence_capture.add_argument("--summary", required=True)
    evidence_capture.add_argument("--from-file")
    evidence_capture.add_argument(
        "--stdin",
        action="store_true",
        help="Read evidence bytes from standard input; stdin is also the default source.",
    )
    evidence_capture.add_argument(
        "--redaction-policy",
        default="default-secret-patterns-v1",
    )
    evidence_capture.add_argument("--idempotency-key")
    evidence_capture.add_argument("--expected-state-sequence", type=int)
    evidence_capture.set_defaults(func=cmd_evidence_capture)
    evidence_record = evidence_sub.add_parser("record")
    evidence_source = evidence_record.add_mutually_exclusive_group(required=True)
    evidence_source.add_argument("--manifest")
    evidence_source.add_argument("--stdin", action="store_true")
    evidence_record.set_defaults(func=cmd_plan_evidence_record)

    risk = sub.add_parser("risk")
    risk_sub = risk.add_subparsers(dest="risk_action", required=True)
    risk_inspect = risk_sub.add_parser("inspect")
    risk_inspect.add_argument(
        "--action-kind",
        choices=sorted(MODEL_RISK_ACTION_KINDS),
        required=True,
    )
    risk_inspect.add_argument("--target-ref", required=True)
    risk_source = risk_inspect.add_mutually_exclusive_group()
    risk_source.add_argument("--action-stdin", action="store_true")
    risk_source.add_argument("--action-from-file")
    risk_inspect.set_defaults(func=cmd_risk_inspect)

    action_command = sub.add_parser("action")
    action_sub = action_command.add_subparsers(
        dest="action_authorization_action",
        required=True,
    )
    action_authorize = action_sub.add_parser("authorize")
    action_authorize.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
        required=True,
    )
    action_authorize.add_argument("--target-ref", required=True)
    action_authorize.add_argument("--action-sha256", required=True)
    action_authorize.add_argument("--confirmation-id", required=True)
    action_authorize.add_argument("--ref", required=True)
    action_authorize.add_argument("--turn-receipt-sha256", required=True)
    action_authorize.add_argument("--ttl-seconds", type=int, default=300)
    action_authorize.set_defaults(func=cmd_action_authorize)
    action_consume = action_sub.add_parser("consume")
    action_consume.add_argument("--authorization-id", required=True)
    action_consume.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
        required=True,
    )
    action_consume.add_argument("--target-ref", required=True)
    action_consume.add_argument("--action-sha256", required=True)
    action_consume.add_argument("--turn-receipt-sha256")
    action_consume.add_argument("--consumer-ref", required=True)
    action_consume.set_defaults(func=cmd_action_consume)
    action_status = action_sub.add_parser("status")
    action_status.add_argument("--authorization-id", required=True)
    action_status.set_defaults(func=cmd_action_status)
    action_lease = action_sub.add_parser("lease")
    action_lease_sub = action_lease.add_subparsers(dest="action_lease_action", required=True)

    def add_action_lease_scope_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--action-kind",
            choices=sorted(HIGH_IMPACT_ACTION_KINDS),
            required=True,
        )
        parser.add_argument("--target-ref", action="append", default=[])
        parser.add_argument("--target-prefix", action="append", default=[])
        parser.add_argument(
            "--action-digest-policy",
            choices=sorted(ACTION_DIGEST_POLICIES),
            default="exact-list",
        )
        parser.add_argument("--allowed-action-sha256", action="append", default=[])
        parser.add_argument("--blocks", action="append", default=[])
        parser.add_argument("--lease-ttl-seconds", type=int, default=3600)
        parser.add_argument("--authorization-ttl-seconds", type=int, default=300)
        parser.add_argument("--max-authorizations", type=int, default=10)
        parser.add_argument(
            "--freeze-on-review-blocker",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        parser.add_argument("--pilot-evidence-ref")

    action_lease_prepare = action_lease_sub.add_parser("prepare")
    add_action_lease_scope_args(action_lease_prepare)
    action_lease_prepare.set_defaults(func=cmd_action_lease_prepare)
    action_lease_issue = action_lease_sub.add_parser("issue")
    add_action_lease_scope_args(action_lease_issue)
    action_lease_issue.add_argument("--confirmation-id", required=True)
    action_lease_issue.add_argument("--basis-sha256", required=True)
    action_lease_issue.add_argument("--ref", required=True)
    action_lease_issue.add_argument("--turn-receipt-sha256", required=True)
    action_lease_issue.set_defaults(func=cmd_action_lease_issue)
    action_lease_authorize = action_lease_sub.add_parser("authorize")
    action_lease_authorize.add_argument("--lease-id", required=True)
    action_lease_authorize.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
        required=True,
    )
    action_lease_authorize.add_argument("--target-ref", required=True)
    action_lease_authorize.add_argument("--action-sha256", required=True)
    action_lease_authorize.add_argument("--idempotency-key")
    action_lease_authorize.add_argument("--ttl-seconds", type=int)
    action_lease_authorize.set_defaults(func=cmd_action_lease_authorize)
    action_lease_status = action_lease_sub.add_parser("status")
    action_lease_status.add_argument("--lease-id", required=True)
    action_lease_status.set_defaults(func=cmd_action_lease_status)
    action_lease_revoke = action_lease_sub.add_parser("revoke")
    action_lease_revoke.add_argument("--lease-id", required=True)
    action_lease_revoke.add_argument("--ref", required=True)
    action_lease_revoke.set_defaults(func=cmd_action_lease_revoke)

    migrate = sub.add_parser(
        "migrate",
        description=(
            "Archive outdated active Plans and rebuild the plugin-declared current "
            "schema without adapting legacy runtime state."
        ),
    )
    migrate_sub = migrate.add_subparsers(dest="migration_action", required=True)
    migrate_inspect = migrate_sub.add_parser(
        "inspect",
        description=(
            "Read-only refresh boundary plus NON_AUTHORITY legacy_summary for an "
            "outdated active Plan."
        ),
    )
    migrate_inspect.set_defaults(func=cmd_migrate_inspect)
    migrate_apply = migrate_sub.add_parser(
        "apply",
        description=(
            "Preview or perform current-schema refresh. Output includes state_reset, "
            "legacy_state_migrated=false, not_migrated, and legacy_summary."
        ),
    )
    migrate_apply.add_argument(
        "--confirmation",
        help="Deprecated compatibility argument; current-schema refresh does not require it.",
    )
    migrate_apply.add_argument(
        "--expected-contract-revision",
        type=int,
        help="Required for durable refresh; guards the archived legacy source revision.",
    )
    migrate_apply.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the archive and rebuild boundary without writing project state.",
    )
    migrate_apply.set_defaults(func=cmd_migrate_apply)
    migrate_recover = migrate_sub.add_parser("recover")
    migrate_recover.add_argument("--migration-id")
    migrate_recover.set_defaults(func=cmd_migrate_recover)
    migrate_rollback = migrate_sub.add_parser("rollback-info")
    migrate_rollback.add_argument("--migration-id")
    migrate_rollback.set_defaults(func=cmd_migrate_rollback_info)

    intake = sub.add_parser("intake")
    intake_sub = intake.add_subparsers(dest="intake_action", required=True)
    intake_status = intake_sub.add_parser("status")
    intake_status.set_defaults(func=cmd_intake_status)
    intake_receipt = intake_sub.add_parser("receipt")
    intake_receipt.add_argument("--turn-receipt-sha256", required=True)
    intake_receipt.add_argument(
        "--classification",
        choices=["no_plan", "plan_controlled"],
        required=True,
    )
    intake_receipt.add_argument(
        "--decision",
        choices=["proceed", "explore", "ask"],
        required=True,
    )
    intake_receipt.add_argument("--rationale", required=True)
    intake_receipt.add_argument("--targets", action="append", required=True)
    intake_receipt.add_argument("--current-unknown-id")
    intake_receipt.add_argument("--candidate-plan")
    intake_receipt.set_defaults(func=cmd_intake_receipt)

    layout = sub.add_parser("layout")
    layout_sub = layout.add_subparsers(dest="action", required=True)
    layout_status = layout_sub.add_parser("status")
    layout_status.set_defaults(func=cmd_layout_status)
    layout_validate = layout_sub.add_parser("validate")
    layout_validate.set_defaults(func=cmd_layout_validate)
    layout_adopt = layout_sub.add_parser("adopt")
    layout_adopt.add_argument("--expected-manifest-sha256", required=True)
    layout_adopt.add_argument("--expected-active-plan-id", required=True)
    layout_adopt.add_argument("--ref", required=True)
    layout_adopt.set_defaults(func=cmd_layout_adopt)
    layout_migrate = layout_sub.add_parser("migrate")
    layout_migrate.set_defaults(func=cmd_layout_migrate)
    layout_recover = layout_sub.add_parser("recover")
    layout_recover.set_defaults(func=cmd_layout_recover)

    plan = sub.add_parser("plan")
    plan_sub = plan.add_subparsers(dest="action", required=True)
    init = plan_sub.add_parser("init")
    init.add_argument("--plan-id", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    init.set_defaults(func=cmd_plan_init)
    create = plan_sub.add_parser("create")
    create.add_argument("--plan-id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    create.set_defaults(func=cmd_plan_init)
    status = plan_sub.add_parser("status")
    status.add_argument("--expected-intake-sha256")
    status.add_argument(
        "--full",
        action="store_true",
        help="Include the complete authority, history, and closeout report.",
    )
    status.set_defaults(func=cmd_plan_status)
    show = plan_sub.add_parser("show")
    show.add_argument("--expected-intake-sha256")
    show.add_argument("--full", action="store_true")
    show.set_defaults(func=cmd_plan_status)
    history = plan_sub.add_parser("history")
    history_sub = history.add_subparsers(dest="history_action", required=True)
    history_list = history_sub.add_parser("list")
    history_list.set_defaults(func=cmd_plan_history)
    history_show = history_sub.add_parser("show")
    history_show.add_argument("--plan-id")
    history_show.add_argument("--path")
    history_show.set_defaults(func=cmd_plan_history)
    for queue_action in ("ready", "next", "blocked"):
        queue = plan_sub.add_parser(queue_action)
        queue.set_defaults(func=cmd_plan_queue, queue_action=queue_action)
    reorder = plan_sub.add_parser("reorder")
    reorder.add_argument("--task-id", required=True)
    reorder.add_argument("--priority", type=int, required=True)
    reorder.add_argument("--expected-state-sequence", type=int, required=True)
    reorder.set_defaults(func=cmd_task_reprioritize)
    plan_intake = plan_sub.add_parser("intake")
    plan_intake_sub = plan_intake.add_subparsers(
        dest="plan_intake_action",
        required=True,
    )
    plan_intake_record = plan_intake_sub.add_parser("record")
    plan_intake_record.add_argument("--manifest", required=True)
    plan_intake_record.add_argument("--expected-revision", type=int, required=True)
    plan_intake_record.set_defaults(func=cmd_plan_intake_record)
    admit = plan_sub.add_parser("admit")
    admit_sub = admit.add_subparsers(dest="admit_action", required=True)
    admit_apply = admit_sub.add_parser("apply")
    admit_apply.add_argument("--manifest", required=True)
    admit_apply.set_defaults(func=cmd_plan_admit_apply)
    admit_recover = admit_sub.add_parser("recover")
    admit_recover.add_argument("--transaction-id")
    admit_recover.set_defaults(func=cmd_plan_admit_recover)
    authority = plan_sub.add_parser("authority")
    authority_sub = authority.add_subparsers(dest="authority_action", required=True)
    authority_inspect = authority_sub.add_parser("inspect")
    authority_inspect.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Agent semantic input as PATH=CLASSIFICATION.",
    )
    authority_inspect.set_defaults(func=cmd_plan_authority_inspect)
    authority_check = authority_sub.add_parser("check")
    authority_check.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Agent semantic input as PATH=CLASSIFICATION.",
    )
    authority_check.set_defaults(func=cmd_plan_authority_check)
    schema_validate = plan_sub.add_parser("schema-validate")
    schema_validate.add_argument("--plan")
    schema_validate.set_defaults(func=cmd_plan_schema_validate)
    validate = plan_sub.add_parser("validate")
    validate.add_argument("--evidence-manifest")
    validate.set_defaults(func=cmd_plan_validate)
    adapt = plan_sub.add_parser("adapt")
    adapt_source = adapt.add_mutually_exclusive_group(required=True)
    adapt_source.add_argument("--manifest")
    adapt_source.add_argument("--intent-stdin", action="store_true")
    adapt_source.add_argument("--intent-from-file")
    adapt.add_argument("--summary")
    adapt.add_argument("--idempotency-key")
    adapt.add_argument(
        "--expected-revision",
        type=int,
        help="Required for schema-v4 high-level intent adaptation.",
    )
    add_current_intake_args(adapt)
    adapt.set_defaults(func=cmd_plan_adapt)
    contract = plan_sub.add_parser("contract")
    contract_sub = contract.add_subparsers(dest="contract_action", required=True)
    contract_revise = contract_sub.add_parser("revise")
    contract_revise.add_argument("--manifest", required=True)
    contract_revise.set_defaults(func=cmd_plan_contract_revise)
    contract_upgrade = contract_sub.add_parser(
        "upgrade",
        description=(
            "Historical schema-v3-to-v4 recovery/audit surface. New work uses "
            "`migrate apply` current-schema refresh."
        ),
    )
    contract_upgrade_sub = contract_upgrade.add_subparsers(
        dest="contract_upgrade_action",
        required=True,
    )
    contract_upgrade_status = contract_upgrade_sub.add_parser(
        "status",
        description=(
            "Historical schema-v3-to-v4 upgrade status. Current active Plans "
            "older than the plugin-declared schema use `migrate inspect`."
        ),
    )
    contract_upgrade_status.set_defaults(func=cmd_plan_contract_upgrade_status)
    contract_upgrade_apply = contract_upgrade_sub.add_parser(
        "apply",
        description=(
            "Historical schema-v3-to-v4 upgrade transaction. New work must "
            "archive and rebuild through `migrate apply` instead."
        ),
    )
    contract_upgrade_apply.add_argument("--manifest", required=True)
    contract_upgrade_apply.set_defaults(func=cmd_plan_contract_upgrade_apply)
    contract_upgrade_recover = contract_upgrade_sub.add_parser(
        "recover",
        description=(
            "Recover only an already staged historical schema-v3-to-v4 upgrade "
            "journal."
        ),
    )
    contract_upgrade_recover.add_argument("--transaction-id")
    contract_upgrade_recover.set_defaults(func=cmd_plan_contract_upgrade_recover)
    structural_rebase = plan_sub.add_parser("structural-rebase")
    structural_rebase_sub = structural_rebase.add_subparsers(
        dest="structural_rebase_action",
        required=True,
    )
    structural_rebase_apply = structural_rebase_sub.add_parser("apply")
    structural_rebase_apply.add_argument("--manifest", required=True)
    structural_rebase_apply.add_argument("--dry-run", action="store_true")
    structural_rebase_apply.set_defaults(func=cmd_plan_structural_rebase_apply)
    structural_rebase_recover = structural_rebase_sub.add_parser("recover")
    structural_rebase_recover.add_argument("--transaction-id", required=True)
    structural_rebase_recover.set_defaults(func=cmd_plan_structural_rebase_recover)
    unknown = plan_sub.add_parser("unknown")
    unknown_sub = unknown.add_subparsers(dest="unknown_action", required=True)
    unknown_add = unknown_sub.add_parser("add")
    unknown_add.add_argument("--unknown-id", required=True)
    unknown_add.add_argument("--question", required=True)
    unknown_add.add_argument("--owner", choices=sorted(UNKNOWN_OWNERS), required=True)
    unknown_add.add_argument("--impact", choices=sorted(UNKNOWN_IMPACTS), required=True)
    unknown_add.add_argument("--blocks", action="append", default=[])
    unknown_add.add_argument("--expected-evidence", required=True)
    unknown_add.add_argument("--expected-revision", type=int, required=True)
    unknown_add.set_defaults(func=cmd_plan_unknown_add)
    unknown_classify = unknown_sub.add_parser("classify")
    unknown_classify.add_argument("--manifest", required=True)
    unknown_classify.add_argument("--expected-revision", type=int, required=True)
    unknown_classify.set_defaults(func=cmd_plan_unknown_classify)
    unknown_resolve = unknown_sub.add_parser("resolve")
    unknown_resolve.add_argument("--unknown-id", required=True)
    unknown_resolve.add_argument("--resolution", required=True)
    unknown_resolve.add_argument("--evidence-manifest", required=True)
    unknown_resolve.add_argument("--expected-revision", type=int, required=True)
    unknown_resolve.set_defaults(func=cmd_plan_unknown_resolve)
    evidence = plan_sub.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_action", required=True)
    evidence_record = evidence_sub.add_parser("record")
    evidence_source = evidence_record.add_mutually_exclusive_group(required=True)
    evidence_source.add_argument("--manifest")
    evidence_source.add_argument(
        "--stdin",
        action="store_true",
        help="Read the bounded evidence object from standard input.",
    )
    evidence_record.set_defaults(func=cmd_plan_evidence_record)
    reconcile = plan_sub.add_parser("reconcile")
    reconcile_sub = reconcile.add_subparsers(dest="reconcile_action", required=True)
    reconcile_apply = reconcile_sub.add_parser("apply")
    reconcile_apply.add_argument("--manifest", required=True)
    reconcile_apply.add_argument("--dry-run", action="store_true")
    reconcile_apply.set_defaults(func=cmd_plan_reconcile_apply)
    reconcile_recover = reconcile_sub.add_parser("recover")
    reconcile_recover.add_argument("--migration-id")
    reconcile_recover.set_defaults(func=cmd_plan_reconcile_recover)
    reconcile_upgrade = plan_sub.add_parser(
        "reconcile-upgrade",
        description=(
            "Historical composed schema-v3 reconciliation plus schema-v4 upgrade "
            "surface. New work uses `migrate apply` current-schema refresh."
        ),
    )
    reconcile_upgrade_sub = reconcile_upgrade.add_subparsers(
        dest="reconcile_upgrade_action",
        required=True,
    )
    reconcile_upgrade_apply = reconcile_upgrade_sub.add_parser(
        "apply",
        description=(
            "Historical composed schema-v3/v4 transaction. Current active legacy "
            "Plans are archived and rebuilt through `migrate apply`."
        ),
    )
    reconcile_upgrade_apply.add_argument("--manifest", required=True)
    reconcile_upgrade_apply.set_defaults(func=cmd_plan_reconcile_upgrade_apply)
    reconcile_upgrade_recover = reconcile_upgrade_sub.add_parser(
        "recover",
        description=(
            "Recover only an already staged historical reconcile-upgrade "
            "workflow."
        ),
    )
    reconcile_upgrade_recover.add_argument("--workflow-id")
    reconcile_upgrade_recover.set_defaults(func=cmd_plan_reconcile_upgrade_recover)
    rollover = plan_sub.add_parser("rollover")
    rollover_sub = rollover.add_subparsers(dest="rollover_action", required=True)
    rollover_apply = rollover_sub.add_parser("apply")
    rollover_apply.add_argument("--manifest", required=True)
    rollover_apply.add_argument("--dry-run", action="store_true")
    rollover_apply.set_defaults(func=cmd_plan_rollover_apply)
    rollover_recover = rollover_sub.add_parser("recover")
    rollover_recover.add_argument("--rollover-id", required=True)
    rollover_recover.set_defaults(func=cmd_plan_rollover_recover)
    retire = plan_sub.add_parser("retire")
    retire_sub = retire.add_subparsers(dest="retire_action", required=True)
    retire_apply = retire_sub.add_parser("apply")
    retire_apply.add_argument("--manifest", required=True)
    retire_apply.add_argument("--dry-run", action="store_true")
    retire_apply.set_defaults(func=cmd_plan_retire_apply)
    retire_recover = retire_sub.add_parser("recover")
    retire_recover.add_argument("--retirement-id", required=True)
    retire_recover.set_defaults(func=cmd_plan_retire_recover)
    closeout_check = plan_sub.add_parser("closeout-check")
    closeout_check.add_argument("--evidence-manifest")
    closeout_check.set_defaults(func=cmd_plan_closeout_check)
    complete = plan_sub.add_parser("complete")
    complete.add_argument("--expected-revision", type=int, required=True)
    complete.add_argument("--evidence-manifest")
    complete.add_argument("--finalize-route", action="store_true")
    complete.add_argument("--confirmation")
    add_current_intake_args(complete)
    complete.set_defaults(func=cmd_plan_complete)
    revise = plan_sub.add_parser("revise")
    revise.add_argument("--expected-revision", type=int, required=True)
    revise.add_argument("--confirmation")
    revise.add_argument("--status")
    revise.add_argument("--mode", choices=["autonomous", "strict"])
    revise.add_argument("--include", action="append", default=[])
    revise.add_argument("--remove-exclude", action="append", default=[])
    revise.add_argument("--patch-file")
    revise.add_argument("--body-file")
    revise.set_defaults(func=cmd_plan_revise)
    edit = plan_sub.add_parser("edit")
    edit.add_argument("--expected-revision", type=int, required=True)
    edit.add_argument("--confirmation")
    edit.add_argument("--status")
    edit.add_argument("--mode", choices=["autonomous", "strict"])
    edit.add_argument("--include", action="append", default=[])
    edit.add_argument("--remove-exclude", action="append", default=[])
    edit.add_argument("--patch-file")
    edit.add_argument("--body-file")
    edit.set_defaults(func=cmd_plan_revise)
    confirm = plan_sub.add_parser("confirm")
    confirm.add_argument("--confirmation-id", required=True)
    confirm.add_argument("--decision", choices=["accepted", "declined"], default="accepted")
    confirm.add_argument("--ref", required=True)
    confirm.add_argument("--evidence-sha256")
    confirm.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(confirm)
    confirm.set_defaults(func=cmd_plan_confirm)
    confirmation = plan_sub.add_parser("confirmation")
    confirmation_sub = confirmation.add_subparsers(
        dest="confirmation_action",
        required=True,
    )
    confirmation_add = confirmation_sub.add_parser("add")
    confirmation_add.add_argument("--confirmation-id", required=True)
    confirmation_add.add_argument("--description", required=True)
    confirmation_add.add_argument(
        "--status",
        default="pending",
    )
    confirmation_add.add_argument("--ref")
    confirmation_add.add_argument(
        "--intervention-kind",
        choices=sorted(INTERVENTION_KINDS),
        required=True,
    )
    confirmation_add.add_argument("--blocks", action="append", required=True)
    confirmation_add.add_argument("--basis-ref", required=True)
    confirmation_add.add_argument("--basis-sha256")
    confirmation_add.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
    )
    confirmation_add.add_argument("--expected-revision", type=int, required=True)
    confirmation_add.set_defaults(func=cmd_plan_confirmation_add)
    confirmation_classify = confirmation_sub.add_parser("classify")
    confirmation_classify.add_argument("--manifest", required=True)
    confirmation_classify.add_argument("--expected-revision", type=int, required=True)
    confirmation_classify.set_defaults(func=cmd_plan_confirmation_classify)
    independent_review = plan_sub.add_parser("independent-review")
    independent_review_sub = independent_review.add_subparsers(
        dest="independent_review_action",
        required=True,
    )
    independent_review_record = independent_review_sub.add_parser("record")
    independent_review_record.add_argument("--manifest", required=True)
    independent_review_record.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(independent_review_record)
    independent_review_record.set_defaults(func=cmd_plan_independent_review_record)
    verify_entry = plan_sub.add_parser("verify-entry")
    verify_entry.add_argument("--field", choices=["obligations", "validations"], required=True)
    verify_entry.add_argument("--entry-id", required=True)
    verify_entry.add_argument("--confirmation", required=True)
    verify_entry.add_argument("--evidence-manifest")
    verify_entry.add_argument("--evidence-ref")
    verify_entry.add_argument("--evidence-sha256")
    verify_entry.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(verify_entry)
    verify_entry.set_defaults(func=cmd_plan_verify_entry)
    artifact_state = plan_sub.add_parser("artifact-state")
    artifact_state.add_argument("--artifact-id", required=True)
    artifact_state.add_argument(
        "--state",
        choices=["suspect", "quarantined", "rollback-pending"],
        required=True,
    )
    artifact_state.add_argument("--confirmation")
    artifact_state.add_argument("--evidence-manifest")
    artifact_state.add_argument("--evidence-ref")
    artifact_state.add_argument("--evidence-sha256")
    artifact_state.add_argument("--expected-revision", type=int, required=True)
    artifact_state.set_defaults(func=cmd_plan_artifact_state)
    finalize_artifact = plan_sub.add_parser("finalize-artifact")
    finalize_artifact.add_argument("--artifact-id", required=True)
    finalize_artifact.add_argument("--task-id", required=True)
    finalize_artifact.add_argument("--confirmation", required=True)
    finalize_artifact.add_argument("--evidence-manifest")
    finalize_artifact.add_argument("--evidence-ref")
    finalize_artifact.add_argument("--evidence-sha256")
    finalize_artifact.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(finalize_artifact)
    finalize_artifact.set_defaults(func=cmd_plan_finalize_artifact)
    delivery_complete = plan_sub.add_parser("delivery-complete")
    delivery_complete.add_argument("--confirmation", required=True)
    delivery_complete.add_argument("--evidence-manifest")
    delivery_complete.add_argument("--evidence-ref")
    delivery_complete.add_argument("--evidence-sha256")
    delivery_complete.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(delivery_complete)
    delivery_complete.set_defaults(func=cmd_plan_delivery_complete)
    activation_repair = plan_sub.add_parser("activation-repair")
    activation_repair.add_argument("--task-id", required=True)
    activation_repair.add_argument("--target-ref", required=True)
    activation_repair.add_argument("--confirmation", required=True)
    activation_repair.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(activation_repair)
    activation_repair.set_defaults(func=cmd_plan_activation_repair)
    activation_promote = plan_sub.add_parser("activation-promote")
    activation_promote.add_argument(
        "--state",
        choices=["in_progress", "active"],
        required=True,
    )
    activation_promote.add_argument("--target-ref")
    activation_promote.add_argument("--confirmation", required=True)
    activation_promote.add_argument("--evidence-manifest")
    activation_promote.add_argument("--evidence-ref")
    activation_promote.add_argument("--evidence-sha256")
    activation_promote.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(activation_promote)
    activation_promote.set_defaults(func=cmd_plan_activation_promote)

    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="action", required=True)
    for action, status_value in {
        "start": "in_progress",
        "block": "blocked",
        "unblock": "in_progress",
        "verify": "verified",
        "skip": "skipped",
    }.items():
        item = task_sub.add_parser(action)
        item.add_argument("--task-id", required=True)
        item.add_argument("--expected-revision", type=int)
        item.add_argument("--expected-state-sequence", type=int)
        item.add_argument("--note")
        if action == "verify":
            task_evidence = item.add_mutually_exclusive_group()
            task_evidence.add_argument("--evidence-manifest")
            task_evidence.add_argument(
                "--evidence-stdin",
                action="store_true",
                help="Record bounded evidence from standard input atomically with verification.",
            )
        if action != "block":
            add_current_intake_args(item)
        else:
            item.set_defaults(
                turn_receipt_sha256=None,
                expected_intake_sha256=None,
            )
        item.set_defaults(func=lambda args, value=status_value: set_task_status(args, value))
    done = task_sub.add_parser("done")
    done.add_argument("--task-id", required=True)
    done.add_argument("--expected-revision", type=int)
    done.add_argument("--expected-state-sequence", type=int)
    done.add_argument("--note")
    done.add_argument("--kind", default="task-done")
    done.add_argument("--summary")
    done.add_argument("--idempotency-key")
    done_source = done.add_mutually_exclusive_group(required=True)
    done_source.add_argument("--evidence-stdin", action="store_true")
    done_source.add_argument("--evidence-from-file", dest="evidence_from_file")
    done_source.add_argument("--from-file", dest="evidence_from_file")
    add_current_intake_args(done)
    done.set_defaults(func=cmd_task_done)
    reprioritize = task_sub.add_parser("reprioritize")
    reprioritize.add_argument("--task-id", required=True)
    reprioritize.add_argument("--priority", type=int, required=True)
    reprioritize.add_argument("--expected-state-sequence", type=int, required=True)
    reprioritize.set_defaults(func=cmd_task_reprioritize)

    worktree = sub.add_parser("worktree")
    worktree_sub = worktree.add_subparsers(dest="worktree_action", required=True)
    worktree_begin = worktree_sub.add_parser("begin")
    worktree_begin.add_argument("--worktree-id", required=True)
    worktree_begin.add_argument("--path", required=True)
    worktree_begin.add_argument("--branch", required=True)
    worktree_begin.add_argument("--summary", required=True)
    worktree_begin.set_defaults(func=cmd_worktree_begin)
    worktree_record = worktree_sub.add_parser("record")
    worktree_record.add_argument("--worktree-id", required=True)
    worktree_record.add_argument("--event", required=True)
    worktree_record.add_argument("--summary", required=True)
    worktree_record.add_argument("--evidence-ref")
    worktree_record.add_argument("--evidence-sha256")
    worktree_record.set_defaults(func=cmd_worktree_record)
    worktree_close = worktree_sub.add_parser("close")
    worktree_close.add_argument("--worktree-id", required=True)
    worktree_close.add_argument("--summary", required=True)
    worktree_close.add_argument("--evidence-ref")
    worktree_close.add_argument("--evidence-sha256")
    worktree_close.set_defaults(func=cmd_worktree_close)
    worktree_merge = worktree_sub.add_parser("merge")
    worktree_merge_sub = worktree_merge.add_subparsers(
        dest="worktree_merge_action",
        required=True,
    )
    worktree_merge_inspect = worktree_merge_sub.add_parser("inspect")
    worktree_merge_inspect.add_argument("--worktree-id", required=True)
    worktree_merge_inspect.set_defaults(func=cmd_worktree_merge_inspect)

    log = sub.add_parser("log")
    log_sub = log.add_subparsers(dest="action", required=True)
    append = log_sub.add_parser("append")
    append.add_argument("--kind", required=True)
    append.add_argument("--message", required=True)
    append.add_argument("--expected-revision", type=int, required=True)
    append.set_defaults(func=cmd_log_append)
    return parser


def command_mutates_state(args: argparse.Namespace) -> bool:
    """Classify commands that must be bound to the newest session receipt."""
    if args.domain in {"intake", "help", "risk"}:
        return False
    if args.domain == "evidence":
        return True
    if args.domain == "action":
        if args.action_authorization_action == "lease":
            return cast(str, args.action_lease_action) not in {"prepare", "status"}
        return cast(str, args.action_authorization_action) != "status"
    if args.domain == "migrate":
        return args.migration_action == "recover" or (
            args.migration_action == "apply" and not bool(args.dry_run)
        )
    if args.domain == "doctor":
        return bool(args.clean_stale_transactions)
    if args.domain == "layout":
        return args.action not in {"status", "validate"}
    if args.domain in {"task", "log"}:
        return True
    if args.domain == "worktree":
        if args.worktree_action == "merge":
            return cast(str, args.worktree_merge_action) != "inspect"
        return True
    if args.domain == "goal":
        return cast(str, args.goal_action) != "show"
    if args.domain == "gate":
        return cast(str, args.gate_action) not in {"list", "check"}
    if args.domain == "truth":
        return cast(str, args.truth_action) not in {"list", "conflicts"}
    if args.domain == "review":
        if args.review_action == "acquisition":
            if args.review_acquisition_action in {"check", "status"}:
                return False
            return not bool(args.dry_run)
        return cast(str, args.review_action) not in {"status", "request"}
    if args.domain != "plan":
        return False
    if args.action in {
        "status",
        "show",
        "ready",
        "next",
        "blocked",
        "authority",
        "history",
        "schema-validate",
        "validate",
        "closeout-check",
    }:
        return False
    if args.action == "contract" and args.contract_action == "upgrade":
        return cast(str, args.contract_upgrade_action) != "status"
    return True


def enforce_active_contract_gate(args: argparse.Namespace, root: Path) -> None:
    """Allow only current-schema refresh writes for an outdated active Plan."""
    if not command_mutates_state(args) or args.domain == "layout":
        return
    report = inspect_authority(root)
    if report.state == "PLAN_SCHEMA_REFRESH_REQUIRED":
        allowed = args.domain == "migrate" and args.migration_action in {"apply", "recover"}
        if allowed:
            return
        raise WorkctlError("PLAN_SCHEMA_REFRESH_REQUIRED")
    if report.state != "GOVERNED_ACTIVE":
        return
    doc = load_plan(active_plan_path(root))
    state = contract_state(doc.frontmatter)
    if state == "PLAN_CONTRACT_READY":
        return
    if state != "PLAN_SCHEMA_REFRESH_REQUIRED":
        raise WorkctlError(state)
    allowed = args.domain == "migrate" and args.migration_action in {"apply", "recover"}
    if not allowed:
        raise WorkctlError("PLAN_SCHEMA_REFRESH_REQUIRED")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = project_root()
        if args.domain not in {"layout", "help"}:
            require_layout_ready(root)
        if command_mutates_state(args):
            validate_current_ready_receipt(
                root,
                args.receipt_sha256,
                require_current_controller=True,
                allow_bootstrapping=args.domain == "layout",
            )
        enforce_active_contract_gate(args, root)
        args.func(args)
    except WorkctlError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
