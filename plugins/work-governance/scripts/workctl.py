#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6.0.2"]
# ///
"""Deterministic controller for Work Governance Plan files."""

from __future__ import annotations

import argparse
import contextlib
import copy
import difflib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PLAN_ID_RE = re.compile(r"^PLAN-\d{8}-\d{3}$")
MIGRATION_ID_RE = re.compile(r"^MIG-\d{8}-\d{3}$")
ROLLOVER_ID_RE = re.compile(r"^ROL-\d{8}-\d{3}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REFERENCE_RE = re.compile(r"^(user|project|git|runtime|evidence|handoff|codex-plugin-list):\S+$")
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
    "plan rollover apply",
    "plan rollover recover",
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


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def valid_reference(value: object) -> bool:
    """Return whether a value is a typed, non-whitespace authority reference."""
    return isinstance(value, str) and REFERENCE_RE.fullmatch(value) is not None


def project_root() -> Path:
    return Path.cwd().resolve()


def plan_dir(root: Path) -> Path:
    return root / "_Plan"


def index_path(root: Path) -> Path:
    return plan_dir(root) / "index.yaml"


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA256 digest for *content*."""
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest for a regular file."""
    if not path.is_file():
        raise WorkctlError(f"MISSING_FILE: {path}")
    return sha256_bytes(path.read_bytes())


def relative_project_path(root: Path, path: Path) -> str:
    """Return a stable project-relative POSIX path."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise WorkctlError(f"PATH_OUTSIDE_PROJECT: {path}") from exc


def checked_project_path(root: Path, raw_path: str) -> Path:
    """Resolve a manifest path while preventing project-root escape."""
    if not raw_path or Path(raw_path).is_absolute():
        raise WorkctlError(f"INVALID_PROJECT_PATH: {raw_path}")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkctlError(f"PATH_OUTSIDE_PROJECT: {raw_path}") from exc
    return resolved


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
        r"(?:_Plan/[A-Za-z0-9._/-]+\.md|docs/[A-Za-z0-9._/-]*[Pp]lan\.md|[Pp]lan\.md)"
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
    if status == "complete":
        signals.append("completed-plan")
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
                add_candidate(path.resolve(), ("_Plan-file",))
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
        raise WorkctlError("ROLLOVER_PATH_SYMLINK: _Plan/.rollovers")
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
    rollover_dir = checked_project_path(root, f"_Plan/.rollovers/{rollover_id}")
    staging_dir = checked_project_path(
        root,
        f"_Plan/.rollovers/{rollover_id}/staging",
    )
    journal_path = checked_project_path(
        root,
        f"_Plan/.rollovers/{rollover_id}.yaml",
    )
    return rollover_dir, staging_dir, journal_path


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
    commands = list(AUTHORITY_BLOCKED_COMMANDS)
    if state == "UNMANAGED_EMPTY":
        commands.append("plan init")
    if state == "GOVERNED_ACTIVE":
        commands.extend(
            [
                "plan revise",
                "plan confirm",
                "plan closeout-check",
                "plan complete",
                "plan verify-entry",
                "plan artifact-state",
                "plan finalize-artifact",
                "plan delivery-complete",
                "task start|block|verify|skip",
                "log append",
            ]
        )
    return commands


def inspect_authority(
    root: Path,
    explicit_candidates: dict[str, str] | None = None,
    *,
    ignore_journal: Path | None = None,
) -> AuthorityReport:
    """Resolve the deterministic authority state for a project."""
    candidates = discover_authority_candidates(root, explicit_candidates)
    blockers: list[str] = []
    migration_journals = [
        journal
        for journal in incomplete_migration_journals(root)
        if ignore_journal is None or journal.resolve() != ignore_journal.resolve()
    ]
    rollover_journals = [
        journal
        for journal in incomplete_rollover_journals(root)
        if ignore_journal is None or journal.resolve() != ignore_journal.resolve()
    ]
    if migration_journals or rollover_journals:
        blockers.extend(
            f"incomplete migration journal: {relative_project_path(root, journal)}"
            for journal in migration_journals
        )
        blockers.extend(
            f"incomplete rollover journal: {relative_project_path(root, journal)}"
            for journal in rollover_journals
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

    lineage_errors = authority_metadata_errors(root, active_doc)
    has_authority_metadata = isinstance(active_doc.frontmatter.get("authority"), dict)
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
    elif not has_authority_metadata:
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


def active_plan_path(root: Path) -> Path:
    index = load_yaml_file(index_path(root))
    active = index.get("active_plan_id")
    if not isinstance(active, str) or not active:
        raise WorkctlError("NO_ACTIVE_PLAN: _Plan/index.yaml has no active_plan_id")
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
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise WorkctlError(f"INVALID_YAML: {path} must contain a mapping")
    return data


def load_plan(path: Path) -> PlanDocument:
    if not path.is_file():
        raise WorkctlError(f"MISSING_FILE: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise WorkctlError("INVALID_PLAN: plan must start with YAML frontmatter")
    try:
        _, raw_frontmatter, body = text.split("---\n", 2)
    except ValueError as exc:
        raise WorkctlError("INVALID_PLAN: plan frontmatter is not closed") from exc
    frontmatter = yaml.safe_load(raw_frontmatter)
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
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_directory_durable(path: Path) -> None:
    """Create a directory chain and synchronize each new parent entry."""
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    path.mkdir(parents=True, exist_ok=True)
    for directory in reversed(missing):
        fsync_directory(directory.parent)
        fsync_directory(directory)


def write_atomic_bytes(path: Path, content: bytes) -> None:
    """Atomically and durably replace a file with exact bytes."""
    ensure_directory_durable(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()


def write_atomic(path: Path, text: str) -> None:
    """Atomically replace a UTF-8 text file."""
    write_atomic_bytes(path, text.encode())


@contextlib.contextmanager
def lock(root: Path) -> Iterator[None]:
    lock_path = plan_dir(root) / ".workctl.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        attempt_path = os.environ.get("WORKCTL_TEST_LOCK_ATTEMPT_FILE")
        if attempt_path:
            Path(attempt_path).write_text("attempting\n", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def require_expected_revision(frontmatter: dict[str, Any], expected: int | None) -> None:
    if expected is None:
        raise WorkctlError("EXPECTED_REVISION_REQUIRED")
    current = frontmatter.get("revision")
    if current != expected:
        raise WorkctlError(f"REVISION_MISMATCH: expected {expected}, found {current}")


def bump_revision(frontmatter: dict[str, Any]) -> None:
    revision = frontmatter.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise WorkctlError("INVALID_PLAN: revision must be a positive integer")
    frontmatter["revision"] = revision + 1
    frontmatter["updated_at"] = utc_now()


def blocking_artifacts(frontmatter: dict[str, Any]) -> dict[str, str]:
    """Return blocking artifact IDs and states from a Plan."""
    result: dict[str, str] = {}
    for artifact in frontmatter.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("status") in BLOCKING_ARTIFACT_STATES:
            artifact_id = artifact.get("id")
            status = artifact.get("status")
            if isinstance(artifact_id, str) and isinstance(status, str):
                result[artifact_id] = status
    return result


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
    result: dict[str, dict[str, Any]] = {}
    raw = frontmatter.get("confirmations", {})
    for group in ("required", "accepted"):
        for item in raw.get(group, []) if isinstance(raw, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                result[item["id"]] = item
    return result


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
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        task = task_for(doc.frontmatter, args.task_id)
        if status != "blocked":
            require_no_blocking_artifacts(doc.frontmatter, task)
        current_status = task.get("status")
        allowed = TASK_TRANSITIONS.get(str(current_status), set())
        if status not in allowed:
            raise WorkctlError(
                f"INVALID_TASK_TRANSITION: {args.task_id} {current_status} -> {status}"
            )
        if status in {"in_progress", "verified", "skipped"}:
            require_dependencies_verified(doc.frontmatter, task)
            require_task_confirmation(doc.frontmatter, task, status)
        task["status"] = status
        if args.note:
            task["note"] = args.note
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"TASK_UPDATED {args.task_id} {status} revision={doc.frontmatter['revision']}")


def validate_frontmatter(
    frontmatter: dict[str, Any],
    *,
    reject_blocking_artifacts: bool,
) -> list[str]:
    errors: list[str] = []
    schema_version = frontmatter.get("schema_version")
    if schema_version not in {1, 2, 3}:
        errors.append("schema_version must be 1, 2, or 3")
    plan_id = frontmatter.get("plan_id")
    if not isinstance(plan_id, str) or PLAN_ID_RE.fullmatch(plan_id) is None:
        errors.append("plan_id must match PLAN-YYYYMMDD-NNN")
    revision = frontmatter.get("revision")
    if type(revision) is not int or revision < 1:
        errors.append("revision must be a positive integer")
    if frontmatter.get("status") not in PLAN_STATES:
        errors.append("status must be a supported Plan state")
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
        elif schema_version == 3:
            exclusion_descriptions: set[str] = set()
            for exclusion_number, exclusion in enumerate(exclude):
                prefix = f"scope.exclude[{exclusion_number}]"
                if not isinstance(exclusion, dict):
                    errors.append(f"{prefix} must be a mapping for schema_version 3")
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
                if confirmation_status in {"accepted", "declined"}:
                    if not item.get("ref"):
                        errors.append(f"{confirmation_id} resolved confirmation requires ref")
                    elif schema_version == 3 and not valid_reference(item.get("ref")):
                        errors.append(f"{confirmation_id} ref must be a typed authority reference")
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

    if schema_version in {2, 3}:
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
            allowed_route_states = ROUTE_STATES if schema_version == 3 else {"active", "terminal"}
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

        if schema_version == 3:
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
    return errors


def validate_plan(
    root: Path,
    *,
    ignore_journal: Path | None = None,
) -> list[str]:
    """Validate the active Plan, index, authority, and complete lineage."""
    try:
        index = load_yaml_file(index_path(root))
        doc = load_plan(active_plan_path(root))
    except WorkctlError as exc:
        return [str(exc)]
    errors = validate_frontmatter(doc.frontmatter, reject_blocking_artifacts=True)
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
    report = inspect_authority(root, ignore_journal=ignore_journal)
    if report.state != "GOVERNED_ACTIVE":
        errors.append(f"authority state is {report.state}")
        errors.extend(report.blockers)
    return errors


def require_valid_candidate(doc: PlanDocument) -> None:
    errors = validate_frontmatter(doc.frontmatter, reject_blocking_artifacts=False)
    if not doc.body.strip():
        errors.append("Plan body must not be empty")
    if errors:
        raise WorkctlError(f"INVALID_PLAN: {'; '.join(errors)}")


def cmd_plan_init(args: argparse.Namespace) -> None:
    root = project_root()
    plan_id = args.plan_id
    if PLAN_ID_RE.fullmatch(plan_id) is None:
        raise WorkctlError("INVALID_PLAN_ID")
    with lock(root):
        if index_path(root).exists():
            index = load_yaml_file(index_path(root))
            if index.get("active_plan_id"):
                raise WorkctlError("ACTIVE_PLAN_EXISTS")
        report = inspect_authority(root)
        if report.state != "UNMANAGED_EMPTY":
            raise WorkctlError(f"AUTHORITY_BLOCKED: {report.state}")
        now = utc_now()
        plan_dir(root).mkdir(parents=True, exist_ok=True)
        index = {
            "schema_version": 1,
            "active_plan_id": plan_id,
            "plans": [
                {
                    "id": plan_id,
                    "path": f"{plan_id}.md",
                    "title": args.title,
                    "created_at": now,
                }
            ],
        }
        fm = {
            "schema_version": 3,
            "plan_id": plan_id,
            "title": args.title,
            "status": "active",
            "mode": args.mode,
            "revision": 1,
            "created_at": now,
            "updated_at": now,
            "scope": {"include": [], "exclude": []},
            "confirmations": {"required": []},
            "obligations": [],
            "tasks": [],
            "validations": [],
            "artifacts": [],
            "authority": {
                "model": AUTHORITY_MODEL,
                "state": AUTHORITY_STATE,
                "canonical_plan_id": plan_id,
                "sources": [],
                "confirmations": {},
            },
            "delivery": {
                "status": "pending",
                "boundary": "undetermined",
                "evidence_ref": "project:not-yet-delivered",
            },
            "activation": {
                "status": "deferred",
                "current_ref": "undetermined",
                "target_ref": "undetermined",
            },
            "route": {
                "route_status": "active",
                "slice_status": "initialized",
                "next_phase": "Define the demand contract.",
                "validation_standard": "Every obligation has direct fresh evidence.",
                "confirmation_gate": "none",
            },
            "handoff": {
                "route_status": "active",
                "next_step": "Define the demand contract.",
            },
        }
        doc = PlanDocument(
            plan_dir(root) / f"{plan_id}.md",
            fm,
            "# Decision Summary\n\nInitialized.\n",
        )
        require_valid_candidate(doc)
        write_atomic(index_path(root), yaml.safe_dump(index, sort_keys=False))
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_INITIALIZED {plan_id} revision=1")


def cmd_plan_status(_args: argparse.Namespace) -> None:
    root = project_root()
    report = inspect_authority(root)
    try:
        doc = load_plan(active_plan_path(root))
    except WorkctlError:
        summary: dict[str, Any] = {
            "authority_state": report.state,
            "authority_candidates": [candidate_to_dict(item) for item in report.candidates],
            "blocking_reasons": report.blockers,
            "allowed_commands": report.allowed_commands,
            "closeout_readiness": {"ready": False, "blockers": ["no active Plan"]},
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    readiness = closeout_readiness(doc.frontmatter, report, validate_plan(root))
    summary = {
        "authority_state": report.state,
        "authority_candidates": [candidate_to_dict(item) for item in report.candidates],
        "blocking_reasons": report.blockers,
        "allowed_commands": report.allowed_commands,
        "plan_id": doc.frontmatter.get("plan_id"),
        "status": doc.frontmatter.get("status"),
        "mode": doc.frontmatter.get("mode"),
        "revision": doc.frontmatter.get("revision"),
        "obligations": doc.frontmatter.get("obligations", []),
        "tasks": doc.frontmatter.get("tasks", []),
        "validations": doc.frontmatter.get("validations", []),
        "confirmations": doc.frontmatter.get("confirmations", {}),
        "artifacts": doc.frontmatter.get("artifacts", []),
        "scope": doc.frontmatter.get("scope", {}),
        "delivery": doc.frontmatter.get("delivery", {}),
        "activation": doc.frontmatter.get("activation", {}),
        "handoff": doc.frontmatter.get("handoff", {}),
        "route": doc.frontmatter.get("route", {}),
        "closeout_readiness": readiness,
        "completion_claims": completion_claims(doc.frontmatter, readiness),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def cmd_plan_validate(_args: argparse.Namespace) -> None:
    errors = validate_plan(project_root())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
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
        activation_decision = (
            confirmations(before).get(old_activation_confirmation)
            if isinstance(old_activation_confirmation, str)
            else None
        )
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
        if isinstance(old_activation_confirmation, str) and (
            current_changed
            or evidence_changed
            or (
                target_changed
                and activation_decision is not None
                and activation_decision.get("status") != "pending"
            )
        ):
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
        require_expected_revision(doc.frontmatter, args.expected_revision)
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


def cmd_plan_confirm(args: argparse.Namespace) -> None:
    root = project_root()
    with lock(root):
        require_governed_authority(root)
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
        if doc.frontmatter.get("schema_version") == 3 and not valid_reference(args.ref):
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
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(
            f"CONFIRMATION_DECIDED {args.confirmation_id} {args.decision} "
            f"revision={doc.frontmatter['revision']}"
        )


def require_evidence_args(evidence_ref: str, evidence_sha256: str) -> None:
    """Validate immutable evidence pointers used by dedicated transitions."""
    if not valid_reference(evidence_ref):
        raise WorkctlError("INVALID_EVIDENCE_REF")
    if SHA256_RE.fullmatch(evidence_sha256) is None:
        raise WorkctlError("INVALID_EVIDENCE_SHA256")


def cmd_plan_verify_entry(args: argparse.Namespace) -> None:
    """Verify one obligation or validation through an evidence-bound command."""
    root = project_root()
    with lock(root):
        require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_slice_revision_confirmation(
            doc.frontmatter,
            args.confirmation,
            {"accepted"},
        )
        require_evidence_args(args.evidence_ref, args.evidence_sha256)
        entries = entries_by_id(doc.frontmatter, args.field)
        entry = entries.get(args.entry_id)
        if entry is None:
            raise WorkctlError(f"UNKNOWN_{args.field.upper()}_ENTRY: {args.entry_id}")
        if entry.get("status") in VERIFIED_TASK_STATES:
            raise WorkctlError(
                f"INVALID_{args.field.upper()}_TRANSITION: "
                f"{args.entry_id} {entry.get('status')} -> verified"
            )
        entry["status"] = "verified"
        entry["evidence_ref"] = args.evidence_ref
        entry["evidence_sha256"] = args.evidence_sha256
        entry["verified_at"] = utc_now()
        bump_revision(doc.frontmatter)
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
        require_slice_revision_confirmation(
            doc.frontmatter,
            args.confirmation,
            {"accepted"},
        )
        require_evidence_args(args.evidence_ref, args.evidence_sha256)
        artifact = entries_by_id(doc.frontmatter, "artifacts").get(args.artifact_id)
        if artifact is None:
            raise WorkctlError(f"UNKNOWN_ARTIFACT: {args.artifact_id}")
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
        artifact["evidence_ref"] = args.evidence_ref
        artifact["evidence_sha256"] = args.evidence_sha256
        artifact["finalized_at"] = utc_now()
        artifact.pop("state_confirmation_id", None)
        bump_revision(doc.frontmatter)
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
        require_evidence_args(args.evidence_ref, args.evidence_sha256)
        artifact = entries_by_id(doc.frontmatter, "artifacts").get(args.artifact_id)
        if artifact is None:
            raise WorkctlError(f"UNKNOWN_ARTIFACT: {args.artifact_id}")
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
        artifact["state_evidence_ref"] = args.evidence_ref
        artifact["state_evidence_sha256"] = args.evidence_sha256
        artifact["state_changed_at"] = utc_now()
        bump_revision(doc.frontmatter)
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
        require_slice_revision_confirmation(
            doc.frontmatter,
            args.confirmation,
            {"accepted"},
        )
        require_evidence_args(args.evidence_ref, args.evidence_sha256)
        delivery = doc.frontmatter.get("delivery")
        if not isinstance(delivery, dict):
            raise WorkctlError("INVALID_DELIVERY")
        if delivery.get("status") == "complete":
            raise WorkctlError("INVALID_DELIVERY_TRANSITION: complete -> complete")
        if delivery.get("boundary") in {None, "", "undetermined"}:
            raise WorkctlError("DELIVERY_BOUNDARY_REQUIRED")
        delivery["status"] = "complete"
        delivery["evidence_ref"] = args.evidence_ref
        delivery["evidence_sha256"] = args.evidence_sha256
        delivery["completed_at"] = utc_now()
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"DELIVERY_COMPLETED revision={doc.frontmatter['revision']}")


def cmd_log_append(args: argparse.Namespace) -> None:
    root = project_root()
    require_governed_authority(root)
    doc = load_plan(active_plan_path(root))
    require_expected_revision(doc.frontmatter, args.expected_revision)
    logs_dir = root / ".logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "time": utc_now(),
        "plan_id": doc.frontmatter.get("plan_id"),
        "revision": doc.frontmatter.get("revision"),
        "kind": args.kind,
        "message": args.message,
    }
    path = logs_dir / f"{doc.frontmatter['plan_id']}.jsonl"
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    fd = os.open(path, flags, 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(f"LOG_APPENDED {path}")


def candidate_to_dict(candidate: AuthorityCandidate) -> dict[str, Any]:
    """Convert a candidate into stable JSON output."""
    return {
        "path": candidate.path,
        "classification": candidate.classification,
        "origin": candidate.origin,
        "signals": candidate.signals,
        "sha256": candidate.sha256,
        "plan_id": candidate.plan_id,
        "revision": candidate.revision,
        "status": candidate.status,
    }


def parse_candidate_specs(values: list[str]) -> dict[str, str]:
    """Parse repeatable ``PATH=CLASSIFICATION`` semantic inputs."""
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise WorkctlError("INVALID_CANDIDATE: expected PATH=CLASSIFICATION")
        path, classification = value.rsplit("=", 1)
        if classification not in AUTHORITY_CLASSIFICATIONS:
            raise WorkctlError(f"INVALID_AUTHORITY_CLASSIFICATION: {classification}")
        if path in result and result[path] != classification:
            raise WorkctlError(f"CONFLICTING_CANDIDATE_CLASSIFICATION: {path}")
        result[path] = classification
    return result


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
    result: list[str] = []
    values = frontmatter.get(field, [])
    if not isinstance(values, list):
        return [f"{field}:invalid"]
    for item in values:
        if not isinstance(item, dict):
            result.append(f"{field}:invalid")
            continue
        if item.get("status") not in VERIFIED_TASK_STATES:
            result.append(str(item.get("id", f"{field}:unknown")))
    return result


def unresolved_exclusions(frontmatter: dict[str, Any]) -> list[str]:
    """Return schema-v3 exclusions that still require route disposition."""
    scope = frontmatter.get("scope", {})
    exclusions = scope.get("exclude", []) if isinstance(scope, dict) else []
    result: list[str] = []
    if not isinstance(exclusions, list):
        return result
    for exclusion in exclusions:
        if (
            isinstance(exclusion, dict)
            and exclusion.get("disposition") in BLOCKING_EXCLUSION_DISPOSITIONS
        ):
            description = exclusion.get("description", "<unknown>")
            result.append(str(description))
    return result


def completion_claims(
    frontmatter: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    """Describe which completion claims current evidence permits."""
    delivery = frontmatter.get("delivery", {})
    route = frontmatter.get("route", {})
    delivery_declared_complete = isinstance(delivery, dict) and delivery.get("status") == "complete"
    obligations_complete = not incomplete_entries(frontmatter, "obligations")
    validations_complete = not incomplete_entries(frontmatter, "validations")
    tasks = frontmatter.get("tasks", [])
    local_tasks_complete = isinstance(tasks, list) and all(
        isinstance(task, dict)
        and (
            task.get("completion_scope", "local") == "route"
            or task.get("status") in VERIFIED_TASK_STATES
        )
        for task in tasks
    )
    artifacts = frontmatter.get("artifacts", [])
    artifacts_final = isinstance(artifacts, list) and all(
        isinstance(artifact, dict) and artifact.get("status") == "final" for artifact in artifacts
    )
    local_delivery_complete = (
        delivery_declared_complete
        and obligations_complete
        and validations_complete
        and local_tasks_complete
        and artifacts_final
    )
    route_complete = bool(readiness.get("ready"))
    confirmation_gate = route.get("confirmation_gate") if isinstance(route, dict) else None
    slice_action_authorized = confirmation_gate in {None, "", "none"}
    if isinstance(confirmation_gate, str) and confirmation_gate.startswith("C-"):
        confirmation = confirmations(frontmatter).get(confirmation_gate)
        slice_action_authorized = bool(
            confirmation and confirmation.get("status") == "accepted" and confirmation.get("ref")
        )
    activation = frontmatter.get("activation", {})
    activation_confirmation = (
        activation.get("confirmation_id") if isinstance(activation, dict) else None
    )
    activation_decision = (
        confirmations(frontmatter).get(activation_confirmation)
        if isinstance(activation_confirmation, str)
        else None
    )
    activation_authorized = bool(
        activation_decision
        and activation_decision.get("status") == "accepted"
        and activation_decision.get("ref")
    )
    if route_complete:
        level = "route_complete"
    elif local_delivery_complete:
        level = "local_delivery_complete"
    else:
        level = "in_progress"
    return {
        "level": level,
        "slice_status": route.get("slice_status") if isinstance(route, dict) else None,
        "delivery_declared_complete": delivery_declared_complete,
        "local_delivery_complete": local_delivery_complete,
        "route_complete": route_complete,
        "no_required_next_step_allowed": route_complete,
        "slice_next_action_authorized": slice_action_authorized,
        "slice_confirmation_id": confirmation_gate,
        "activation_authorized": activation_authorized,
        "activation_confirmation_id": activation_confirmation,
    }


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
    if frontmatter.get("schema_version") == 3:
        delivery = frontmatter.get("delivery", {})
        if not isinstance(delivery, dict) or delivery.get("status") != "complete":
            blockers.append("delivery is not complete")
        activation = frontmatter.get("activation", {})
        if isinstance(activation, dict) and activation.get("status") in BLOCKING_ACTIVATION_STATES:
            blockers.append(f"activation is {activation.get('status')}")
        for description in unresolved_exclusions(frontmatter):
            blockers.append(f"scope exclusion is unresolved: {description}")
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


def cmd_plan_closeout_check(_args: argparse.Namespace) -> None:
    """Print closeout readiness and fail when obligations remain."""
    root = project_root()
    report = inspect_authority(root)
    doc = load_plan(active_plan_path(root))
    readiness = closeout_readiness(doc.frontmatter, report, validate_plan(root))
    print(json.dumps(readiness, indent=2, sort_keys=True))
    if not readiness["ready"]:
        raise SystemExit(1)


def cmd_plan_complete(args: argparse.Namespace) -> None:
    """Mark a Plan complete only after full route closeout."""
    root = project_root()
    with lock(root):
        report = require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        readiness = closeout_readiness(doc.frontmatter, report, validate_plan(root))
        if not readiness["ready"]:
            raise WorkctlError(
                f"CLOSEOUT_BLOCKED: {'; '.join(str(item) for item in readiness['blockers'])}"
            )
        doc.frontmatter["status"] = "complete"
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_COMPLETED revision={doc.frontmatter['revision']}")


def manifest_input_path(manifest_path: Path, raw_path: str) -> Path:
    """Resolve a read-only manifest input relative to the manifest directory."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def confirmation_from_manifest(
    confirmations_value: dict[str, Any],
    key: str,
    *,
    required: bool,
) -> tuple[str, str, str, str] | None:
    """Read one accepted confirmation reference from a reconciliation manifest."""
    raw = confirmations_value.get(key)
    if raw is None and not required:
        return None
    if not isinstance(raw, dict):
        raise WorkctlError(f"MANIFEST_CONFIRMATION_REQUIRED: {key}")
    confirmation_id = raw.get("id")
    ref = raw.get("ref")
    accepted_at = raw.get("accepted_at")
    evidence_sha256 = raw.get("evidence_sha256")
    if not isinstance(confirmation_id, str) or not confirmation_id.startswith("C-"):
        raise WorkctlError(f"INVALID_MANIFEST_CONFIRMATION_ID: {key}")
    if not isinstance(ref, str) or not ref:
        raise WorkctlError(f"MANIFEST_CONFIRMATION_REF_REQUIRED: {key}")
    if not isinstance(accepted_at, str) or not accepted_at:
        raise WorkctlError(f"MANIFEST_CONFIRMATION_ACCEPTED_AT_REQUIRED: {key}")
    if not isinstance(evidence_sha256, str) or SHA256_RE.fullmatch(evidence_sha256) is None:
        raise WorkctlError(f"MANIFEST_CONFIRMATION_EVIDENCE_REQUIRED: {key}")
    return confirmation_id, ref, accepted_at, evidence_sha256


def accepted_confirmation(
    confirmation_id: str,
    ref: str,
    accepted_at: str,
    evidence_sha256: str,
    description: str,
) -> dict[str, Any]:
    """Build a confirmed or dry-run-pending entry for the canonical Plan."""
    if ref == "PENDING":
        return {
            "id": confirmation_id,
            "description": description,
            "status": "pending",
            "evidence_sha256": evidence_sha256,
        }
    return {
        "id": confirmation_id,
        "description": description,
        "status": "accepted",
        "ref": ref,
        "accepted_at": accepted_at,
        "evidence_sha256": evidence_sha256,
    }


def archive_path_for_source(migration_id: str, source_path: str) -> str:
    """Return the deterministic archive location for a migration source."""
    if source_path.startswith("_Plan/"):
        suffix = source_path.removeprefix("_Plan/")
        return f"_Plan/archive/{migration_id}/unmerged/{suffix}"
    return f"_Plan/archive/{migration_id}/legacy/{source_path}"


def pointer_text(
    *,
    source_path: str,
    canonical_path: str,
    migration_id: str,
    archive_path: str,
) -> str:
    """Build the non-authoritative pointer that replaces a migrated source."""
    source_parent = Path(source_path).parent
    canonical_href = os.path.relpath(canonical_path, start=source_parent).replace(os.sep, "/")
    archive_href = os.path.relpath(archive_path, start=source_parent).replace(os.sep, "/")
    return (
        "# Non-authoritative migration pointer\n\n"
        "This path no longer controls current or future execution.\n\n"
        f"- Canonical Plan: [{canonical_path}]({canonical_href})\n"
        f"- Migration: `{migration_id}`\n"
        f"- Archived source: [{archive_path}]({archive_href})\n"
        f"- Marker: `{POINTER_MARKER}`\n"
    )


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
    target_relative = f"_Plan/{plan_id}.md"
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
        if source_path.startswith(("_Plan/archive/", "_Plan/.migrations/")):
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
        if SHA256_RE.fullmatch(expected_hash) is None:
            raise WorkctlError("INVALID_AGENTS_REWRITE_HASH")
        agents_path = checked_project_path(root, agents_path_value)
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
    migration_dir = plan_dir(root) / ".migrations" / migration_id
    staging_dir = migration_dir / "staging"
    journal_path = plan_dir(root) / ".migrations" / f"{migration_id}.yaml"
    if journal_path.exists():
        raise WorkctlError(f"MIGRATION_JOURNAL_EXISTS: {migration_id}")
    staged_plan = staging_dir / "target-plan.md"
    write_atomic(staged_plan, dump_plan(target_doc))
    staged_sources: list[dict[str, Any]] = []
    for source in manifest["sources"]:
        assert isinstance(source, dict)
        source_path_value = str(source["path"])
        source_path = checked_project_path(root, source_path_value)
        staged_path = staging_dir / "sources" / source_path_value
        source_bytes = source_path.read_bytes()
        if sha256_bytes(source_bytes) != source["sha256"]:
            raise WorkctlError(f"SOURCE_DRIFT: {source_path_value}")
        write_atomic_bytes(staged_path, source_bytes)
        staged_sources.append({**source, "staged_path": relative_project_path(root, staged_path)})
    agents_record = manifest.get("agents_record")
    staged_agents: dict[str, Any] | None = None
    if isinstance(agents_record, dict):
        replacement_file = Path(str(agents_record["replacement_file"]))
        staged_agents_path = staging_dir / "agents-replacement.md"
        replacement_bytes = replacement_file.read_bytes()
        if sha256_bytes(replacement_bytes) != agents_record["replacement_sha256"]:
            raise WorkctlError("AGENTS_REWRITE_DRIFT")
        write_atomic_bytes(staged_agents_path, replacement_bytes)
        staged_agents = {
            **agents_record,
            "staged_path": relative_project_path(root, staged_agents_path),
        }
    journal = {
        "schema_version": 1,
        "migration_id": migration_id,
        "status": "staged",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "target_plan_id": target_doc.frontmatter["plan_id"],
        "target_path": relative_project_path(root, target_doc.path),
        "staged_plan": relative_project_path(root, staged_plan),
        "target_sha256": sha256_file(staged_plan),
        "prepared_plan_sha256": manifest["prepared_plan_sha256"],
        "proposal_sha256": manifest["proposal_sha256"],
        "agents_diff_sha256": manifest["agents_diff_sha256"],
        "sources": staged_sources,
        "agents_rewrite": staged_agents,
        "git_baseline": manifest.get("git_baseline"),
        "completed_operations": [],
    }
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


def ensure_archive(
    root: Path,
    source: dict[str, Any],
    *,
    repair: bool,
) -> None:
    """Create or verify one immutable source archive."""
    archive = checked_project_path(root, str(source["archive_path"]))
    staged = checked_project_path(root, str(source["staged_path"]))
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
    original = checked_project_path(root, str(source["path"]))
    pointer = pointer_text(
        source_path=str(source["path"]),
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
    target = checked_project_path(root, str(agents_record["path"]))
    staged = checked_project_path(root, str(agents_record["staged_path"]))
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


def resume_migration(
    root: Path,
    journal_path: Path,
    *,
    repair_committed: bool = False,
) -> None:
    """Idempotently roll a staged migration forward to index activation."""
    journal = load_yaml_file(journal_path)
    if journal.get("status") == "committed" and not repair_committed:
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
    staged_plan = checked_project_path(root, str(journal["staged_plan"]))
    if sha256_file(staged_plan) != journal.get("target_sha256"):
        raise WorkctlError("STAGED_PLAN_HASH_MISMATCH")
    sources = journal.get("sources", [])
    if not isinstance(sources, list):
        raise WorkctlError("INVALID_MIGRATION_JOURNAL")
    for source in sources:
        if not isinstance(source, dict):
            raise WorkctlError("INVALID_MIGRATION_JOURNAL")
        archive_operation = f"archive:{source['path']}"
        ensure_archive(root, source, repair=repair_committed)
        record_operation(journal_path, journal, archive_operation)
        pointer_operation = f"pointer:{source['path']}"
        ensure_pointer(root, journal, source)
        record_operation(journal_path, journal, pointer_operation)
    agents_record = journal.get("agents_rewrite")
    if isinstance(agents_record, dict):
        ensure_agents_rewrite(root, agents_record)
        record_operation(journal_path, journal, "agents-rewrite")
    target = checked_project_path(root, str(journal["target_path"]))
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
    """Build the canonical payload authorized by ``C-PLAN-ROLLOVER``."""
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
    if prepared_doc.frontmatter.get("schema_version") != 3:
        raise WorkctlError("ROLLOVER_TARGET_MUST_USE_SCHEMA_VERSION_3")
    if prepared_doc.frontmatter.get("status") != "active":
        raise WorkctlError("TARGET_PLAN_MUST_BE_ACTIVE")
    target_relative = f"_Plan/{target_plan_id}.md"
    target_path = checked_project_path(root, target_relative)
    if target_path.exists():
        raise WorkctlError(f"TARGET_PLAN_CONFLICT: {target_relative}")

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

    target_frontmatter = copy.deepcopy(prepared_doc.frontmatter)
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
    target_frontmatter["authority"] = {
        "model": AUTHORITY_MODEL,
        "state": AUTHORITY_STATE,
        "canonical_plan_id": target_plan_id,
        "rollover_id": rollover_id,
        "predecessor": source_record,
        "sources": [],
        "confirmations": {"rollover": confirmation_id},
    }
    target_doc = PlanDocument(target_path, target_frontmatter, prepared_doc.body)
    require_valid_candidate(target_doc)

    manifest["rollover_id"] = rollover_id
    manifest["source_plan"] = source_record
    manifest["index_baseline"] = index_baseline
    manifest["target_relative"] = target_relative
    manifest["prepared_path"] = str(prepared_path)
    manifest["prepared_plan_sha256"] = prepared_sha256
    manifest["proposal_sha256"] = proposal_sha256
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
        "rollover_confirmation": confirmations(target_doc.frontmatter)["C-PLAN-ROLLOVER"],
        "completed_operations": [],
    }
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
        or target_path_value != f"_Plan/{target_plan_id}.md"
        or target_plan_id == source_plan_id
    ):
        raise WorkctlError("INVALID_ROLLOVER_JOURNAL")
    expected_staging_root = f"_Plan/.rollovers/{rollover_id}/staging"
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
    expected_frontmatter = copy.deepcopy(prepared_doc.frontmatter)
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
    if staged_plan.read_bytes() != dump_plan(expected_target_doc).encode():
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
        if incomplete_migration_journals(root) or incomplete_rollover_journals(root):
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
        if incomplete_migration_journals(root) or incomplete_rollover_journals(root):
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workctl")
    sub = parser.add_subparsers(dest="domain", required=True)

    plan = sub.add_parser("plan")
    plan_sub = plan.add_subparsers(dest="action", required=True)
    init = plan_sub.add_parser("init")
    init.add_argument("--plan-id", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    init.set_defaults(func=cmd_plan_init)
    status = plan_sub.add_parser("status")
    status.set_defaults(func=cmd_plan_status)
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
    validate.set_defaults(func=cmd_plan_validate)
    reconcile = plan_sub.add_parser("reconcile")
    reconcile_sub = reconcile.add_subparsers(dest="reconcile_action", required=True)
    reconcile_apply = reconcile_sub.add_parser("apply")
    reconcile_apply.add_argument("--manifest", required=True)
    reconcile_apply.add_argument("--dry-run", action="store_true")
    reconcile_apply.set_defaults(func=cmd_plan_reconcile_apply)
    reconcile_recover = reconcile_sub.add_parser("recover")
    reconcile_recover.add_argument("--migration-id")
    reconcile_recover.set_defaults(func=cmd_plan_reconcile_recover)
    rollover = plan_sub.add_parser("rollover")
    rollover_sub = rollover.add_subparsers(dest="rollover_action", required=True)
    rollover_apply = rollover_sub.add_parser("apply")
    rollover_apply.add_argument("--manifest", required=True)
    rollover_apply.add_argument("--dry-run", action="store_true")
    rollover_apply.set_defaults(func=cmd_plan_rollover_apply)
    rollover_recover = rollover_sub.add_parser("recover")
    rollover_recover.add_argument("--rollover-id", required=True)
    rollover_recover.set_defaults(func=cmd_plan_rollover_recover)
    closeout_check = plan_sub.add_parser("closeout-check")
    closeout_check.set_defaults(func=cmd_plan_closeout_check)
    complete = plan_sub.add_parser("complete")
    complete.add_argument("--expected-revision", type=int, required=True)
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
    confirm = plan_sub.add_parser("confirm")
    confirm.add_argument("--confirmation-id", required=True)
    confirm.add_argument("--decision", choices=["accepted", "declined"], default="accepted")
    confirm.add_argument("--ref", required=True)
    confirm.add_argument("--evidence-sha256")
    confirm.add_argument("--expected-revision", type=int, required=True)
    confirm.set_defaults(func=cmd_plan_confirm)
    verify_entry = plan_sub.add_parser("verify-entry")
    verify_entry.add_argument("--field", choices=["obligations", "validations"], required=True)
    verify_entry.add_argument("--entry-id", required=True)
    verify_entry.add_argument("--confirmation", required=True)
    verify_entry.add_argument("--evidence-ref", required=True)
    verify_entry.add_argument("--evidence-sha256", required=True)
    verify_entry.add_argument("--expected-revision", type=int, required=True)
    verify_entry.set_defaults(func=cmd_plan_verify_entry)
    artifact_state = plan_sub.add_parser("artifact-state")
    artifact_state.add_argument("--artifact-id", required=True)
    artifact_state.add_argument(
        "--state",
        choices=["suspect", "quarantined", "rollback-pending"],
        required=True,
    )
    artifact_state.add_argument("--confirmation")
    artifact_state.add_argument("--evidence-ref", required=True)
    artifact_state.add_argument("--evidence-sha256", required=True)
    artifact_state.add_argument("--expected-revision", type=int, required=True)
    artifact_state.set_defaults(func=cmd_plan_artifact_state)
    finalize_artifact = plan_sub.add_parser("finalize-artifact")
    finalize_artifact.add_argument("--artifact-id", required=True)
    finalize_artifact.add_argument("--task-id", required=True)
    finalize_artifact.add_argument("--confirmation", required=True)
    finalize_artifact.add_argument("--evidence-ref", required=True)
    finalize_artifact.add_argument("--evidence-sha256", required=True)
    finalize_artifact.add_argument("--expected-revision", type=int, required=True)
    finalize_artifact.set_defaults(func=cmd_plan_finalize_artifact)
    delivery_complete = plan_sub.add_parser("delivery-complete")
    delivery_complete.add_argument("--confirmation", required=True)
    delivery_complete.add_argument("--evidence-ref", required=True)
    delivery_complete.add_argument("--evidence-sha256", required=True)
    delivery_complete.add_argument("--expected-revision", type=int, required=True)
    delivery_complete.set_defaults(func=cmd_plan_delivery_complete)

    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="action", required=True)
    for action, status_value in {
        "start": "in_progress",
        "block": "blocked",
        "verify": "verified",
        "skip": "skipped",
    }.items():
        item = task_sub.add_parser(action)
        item.add_argument("--task-id", required=True)
        item.add_argument("--expected-revision", type=int, required=True)
        item.add_argument("--note")
        item.set_defaults(func=lambda args, value=status_value: set_task_status(args, value))

    log = sub.add_parser("log")
    log_sub = log.add_subparsers(dest="action", required=True)
    append = log_sub.add_parser("append")
    append.add_argument("--kind", required=True)
    append.add_argument("--message", required=True)
    append.add_argument("--expected-revision", type=int, required=True)
    append.set_defaults(func=cmd_log_append)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except WorkctlError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
