"""Current-schema refresh and runtime doctor commands."""

from __future__ import annotations

# Controller infrastructure is bound by name for each refresh/doctor command.
# ruff: noqa: F821
import argparse
import json
import shutil
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from workctl_modules.kernel.bindings import call_with_bound_globals


def call(bindings: Mapping[str, Any], function: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a legacy refresh helper with controller infrastructure bound."""
    return call_with_bound_globals(globals(), bindings, function, *args, **kwargs)


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
        lines.extend(f"- {item}" for item in success_conditions if isinstance(item, str) and item)
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
