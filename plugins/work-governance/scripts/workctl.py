#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6.0.2"]
# ///
"""Deterministic controller for Work Governance Plan files."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PLAN_ID_RE = re.compile(r"^PLAN-\d{8}-\d{3}$")
ENTRY_ID_PATTERNS = {
    "obligations": re.compile(r"^O-\d{3}$"),
    "tasks": re.compile(r"^T-\d{3}$"),
    "validations": re.compile(r"^V-\d{3}$"),
    "artifacts": re.compile(r"^A-\d{3}$"),
}
BLOCKING_ARTIFACT_STATES = {"suspect", "quarantined", "rollback-pending"}
VERIFIED_TASK_STATES = {"verified", "skipped"}
PATCHABLE_PLAN_FIELDS = {"obligations", "tasks", "validations", "artifacts"}
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
WRITE_COMMANDS = {
    ("plan", "init"),
    ("plan", "revise"),
    ("plan", "confirm"),
    ("task", "start"),
    ("task", "block"),
    ("task", "verify"),
    ("task", "skip"),
    ("log", "append"),
}


class WorkctlError(RuntimeError):
    """User-facing controller error."""


@dataclass(frozen=True)
class PlanDocument:
    path: Path
    frontmatter: dict[str, Any]
    body: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def project_root() -> Path:
    return Path.cwd().resolve()


def plan_dir(root: Path) -> Path:
    return root / "_Plan"


def index_path(root: Path) -> Path:
    return plan_dir(root) / "index.yaml"


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


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()


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


def require_no_blocking_artifacts(frontmatter: dict[str, Any]) -> None:
    for artifact in frontmatter.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("status") in BLOCKING_ARTIFACT_STATES:
            artifact_id = artifact.get("id", "<unknown>")
            status = artifact.get("status")
            raise WorkctlError(f"BLOCKED_BY_ARTIFACT: {artifact_id} is {status}")


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


def tasks_by_id(frontmatter: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in frontmatter.get("tasks", []):
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
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_no_blocking_artifacts(doc.frontmatter)
        task = task_for(doc.frontmatter, args.task_id)
        if status == "in_progress":
            require_dependencies_verified(doc.frontmatter, task)
            require_confirmation(doc.frontmatter, task.get("requires_confirmation"))
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
    if frontmatter.get("schema_version") != 1:
        errors.append("schema_version must be 1")
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
        for field in ("include", "exclude"):
            values = scope.get(field)
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                errors.append(f"scope.{field} must be a list of strings")

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
                if item.get("status") not in {"pending", "accepted"}:
                    errors.append(f"{confirmation_id} has an unsupported status")
                if item.get("status") == "accepted" and not item.get("ref"):
                    errors.append(f"{confirmation_id} accepted confirmation requires ref")

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
    return errors


def validate_plan(root: Path) -> list[str]:
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
        if index_path(root).exists() and not args.force:
            index = load_yaml_file(index_path(root))
            if index.get("active_plan_id"):
                raise WorkctlError("ACTIVE_PLAN_EXISTS")
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
            "schema_version": 1,
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
    doc = load_plan(active_plan_path(project_root()))
    summary = {
        "plan_id": doc.frontmatter.get("plan_id"),
        "status": doc.frontmatter.get("status"),
        "mode": doc.frontmatter.get("mode"),
        "revision": doc.frontmatter.get("revision"),
        "tasks": doc.frontmatter.get("tasks", []),
        "artifacts": doc.frontmatter.get("artifacts", []),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def cmd_plan_validate(_args: argparse.Namespace) -> None:
    errors = validate_plan(project_root())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
    print("PLAN_VALID")


def cmd_plan_revise(args: argparse.Namespace) -> None:
    root = project_root()
    with lock(root):
        doc = load_plan(active_plan_path(root))
        require_expected_revision(doc.frontmatter, args.expected_revision)
        structural_change = bool(
            args.include
            or args.remove_exclude
            or args.patch_file
            or args.body_file
            or args.mode
        )
        if structural_change and not args.confirmation:
            raise WorkctlError("CONFIRMATION_REQUIRED: structural plan revision")
        require_confirmation(doc.frontmatter, args.confirmation)
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
        if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
            raise WorkctlError("INVALID_PLAN: scope.exclude must be a list of strings")
        for item in args.include:
            if item not in include:
                include.append(item)
        for item in args.remove_exclude:
            if item not in exclude:
                raise WorkctlError(f"SCOPE_EXCLUSION_NOT_FOUND: {item}")
            exclude.remove(item)
        if args.status:
            doc.frontmatter["status"] = args.status
        if args.mode:
            doc.frontmatter["mode"] = args.mode
        if args.body_file:
            body_path = Path(args.body_file)
            if not body_path.is_file():
                raise WorkctlError(f"MISSING_FILE: {body_path}")
            doc = PlanDocument(doc.path, doc.frontmatter, body_path.read_text(encoding="utf-8"))
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_REVISED revision={doc.frontmatter['revision']}")


def cmd_plan_confirm(args: argparse.Namespace) -> None:
    root = project_root()
    with lock(root):
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
        target["status"] = "accepted"
        target["ref"] = args.ref
        target["accepted_at"] = utc_now()
        bump_revision(doc.frontmatter)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"CONFIRMED {args.confirmation_id} revision={doc.frontmatter['revision']}")


def cmd_log_append(args: argparse.Namespace) -> None:
    root = project_root()
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workctl")
    sub = parser.add_subparsers(dest="domain", required=True)

    plan = sub.add_parser("plan")
    plan_sub = plan.add_subparsers(dest="action", required=True)
    init = plan_sub.add_parser("init")
    init.add_argument("--plan-id", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_plan_init)
    status = plan_sub.add_parser("status")
    status.set_defaults(func=cmd_plan_status)
    validate = plan_sub.add_parser("validate")
    validate.set_defaults(func=cmd_plan_validate)
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
    confirm.add_argument("--ref", required=True)
    confirm.add_argument("--expected-revision", type=int, required=True)
    confirm.set_defaults(func=cmd_plan_confirm)

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
