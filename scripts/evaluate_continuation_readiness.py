#!/usr/bin/env python3
"""Exercise the native atomic readiness query against a temporary WorkVCS Store."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pwd
import sqlite3
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "plugins" / "work-governance" / "runtime" / "hook_runtime.py"
CONTRACT = "wg-hook-v1"
PROJECT_ID = "g-p-continuation-readiness-eval"
DIGEST_A = "1" * 64
DIGEST_B = "2" * 64


class RuntimeModule(Protocol):
    """Typed Hook consumer surface reused by the development-candidate probe."""

    def _continuation_readiness_response(
        self,
        snapshot: dict[str, object],
        scope_id: str,
        previous_digest: str | None,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class DevelopmentProvider:
    """Bind an explicit candidate binary to its source checkout and build identity."""

    executable: Path
    source_root: Path
    runtime_status: dict[str, object]
    binary_sha256: str


def parse_arguments() -> argparse.Namespace:
    """Parse either the stable consumer probe or an explicit development candidate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--development-workvcs",
        type=Path,
        help="Absolute candidate WorkVCS binary used only for isolated development evidence",
    )
    parser.add_argument(
        "--development-source-root",
        type=Path,
        help="Absolute source checkout containing the development WorkVCS binary",
    )
    arguments = parser.parse_args()
    if (arguments.development_workvcs is None) != (arguments.development_source_root is None):
        parser.error(
            "--development-workvcs and --development-source-root must be provided together"
        )
    return arguments


def load_runtime_module() -> RuntimeModule:
    """Load the exact Hook response implementation without changing stable CLI selection."""
    spec = importlib.util.spec_from_file_location("work_governance_readiness_eval", RUNTIME)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Hook runtime: {RUNTIME}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(RuntimeModule, module)


def stable_workvcs() -> Path:
    """Resolve the fixed owner-controlled WorkVCS executable."""
    path = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local" / "bin" / "workvcs"
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"stable WorkVCS entry is not a regular file: {path}")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise RuntimeError(f"stable WorkVCS entry is not owner-controlled: {path}")
    return path


def stable_hook() -> tuple[Path, str, Path]:
    """Select the installed launcher and source-matched immutable Hook package."""
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    launcher = home / ".local" / "bin" / "work-governance-hook"
    info = launcher.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) & 0o077
        or not os.access(launcher, os.X_OK)
    ):
        raise RuntimeError("stable Hook launcher is not an owner-private executable")
    manifest = parse_json_output(
        RUNTIME.with_name("package.json").read_text(encoding="utf-8"),
        "source Hook package manifest",
    )
    if manifest.get("schema_version") != 1 or manifest.get("contract") != CONTRACT:
        raise RuntimeError("source Hook package manifest has an incompatible contract")
    package_digest = json_sha256(manifest)
    installed_runtime = (
        home / ".local" / "libexec" / "work-governance" / package_digest / RUNTIME.name
    )
    if file_sha256(installed_runtime) != file_sha256(RUNTIME):
        raise RuntimeError("installed Hook runtime does not match the evaluated source")
    return launcher, package_digest, installed_runtime


def run(arguments: list[str], *, input_text: str | None = None, cwd: Path = Path("/")) -> str:
    """Run one bounded real command and return stdout."""
    completed = run_completed(arguments, input_text=input_text, cwd=cwd)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic"
        raise RuntimeError(f"command failed with exit {completed.returncode}: {detail}")
    return completed.stdout


def run_completed(
    arguments: list[str], *, input_text: str | None = None, cwd: Path = Path("/")
) -> subprocess.CompletedProcess[str]:
    """Run one bounded command while preserving a typed failure result."""
    return subprocess.run(
        arguments,
        input=input_text,
        capture_output=True,
        check=False,
        cwd=cwd,
        env={"HOME": pwd.getpwuid(os.getuid()).pw_dir, "PATH": "/usr/bin:/bin"},
        text=True,
        timeout=30,
    )


def parse_json_output(output: str, label: str) -> dict[str, object]:
    """Parse one command's top-level JSON object."""
    try:
        decoded: object = json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label} is not valid JSON") from error
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise RuntimeError(f"{label} is not a JSON object")
    return decoded


def development_provider(executable: Path, source_root: Path) -> DevelopmentProvider:
    """Validate an explicitly selected owner-controlled development binary."""
    if not executable.is_absolute() or not source_root.is_absolute():
        raise RuntimeError("development WorkVCS paths must be absolute")
    resolved_root = source_root.resolve(strict=True)
    root_info = resolved_root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid():
        raise RuntimeError("development source root must be an owner-controlled directory")
    resolved_executable = executable.resolve(strict=True)
    executable_info = executable.lstat()
    if (
        stat.S_ISLNK(executable_info.st_mode)
        or not stat.S_ISREG(executable_info.st_mode)
        or executable_info.st_uid != os.getuid()
        or stat.S_IMODE(executable_info.st_mode) & 0o022
        or not os.access(executable, os.X_OK)
    ):
        raise RuntimeError("development WorkVCS must be an owner-controlled executable file")
    if resolved_executable != executable or not resolved_executable.is_relative_to(resolved_root):
        raise RuntimeError("development WorkVCS must be a real file inside its source root")
    status = parse_json_output(
        run(
            [str(resolved_executable), "runtime", "status", "--format", "json"],
            cwd=resolved_root,
        ),
        "development WorkVCS runtime status",
    )
    binary_digest = status.get("binary_digest")
    if (
        status.get("read_only") is not True
        or status.get("executable_role") != "development_candidate"
        or status.get("stable_entry") is not False
        or status.get("executable_path") != str(resolved_executable)
        or status.get("binary_size_bytes") != executable_info.st_size
        or not isinstance(binary_digest, str)
        or not binary_digest.startswith("blake3-256:")
        or len(binary_digest.removeprefix("blake3-256:")) != 64
        or any(
            character not in "0123456789abcdef"
            for character in binary_digest.removeprefix("blake3-256:")
        )
    ):
        raise RuntimeError("development WorkVCS runtime identity did not match the selected binary")
    return DevelopmentProvider(
        executable=resolved_executable,
        source_root=resolved_root,
        runtime_status=status,
        binary_sha256=file_sha256(resolved_executable),
    )


def parse_records(output: str) -> dict[str, str]:
    """Parse setup-command key-value receipts without using them for readiness."""
    records: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in records:
            raise RuntimeError(f"duplicate output key: {key}")
        records[key] = value
    return records


def require(records: dict[str, str], field: str) -> str:
    """Return one required setup receipt field."""
    value = records.get(field)
    if value is None or not value:
        raise RuntimeError(f"command output is missing {field}")
    return value


def authority(actor_session_id: str, *, expected_revision: int, enabled: bool) -> str:
    """Build a deterministic local evaluation authority envelope."""
    return json.dumps(
        {
            "action": "enable" if enabled else "disable",
            "actor_session_id": actor_session_id,
            "authorization_envelope_kind": "trusted_product_control_plane",
            "authorized_at_us": 1,
            "expected_revision": expected_revision,
            "product_actor_id": "local-protocol-evaluation",
            "project_id": PROJECT_ID,
            "project_membership_receipt_digest": DIGEST_A,
            "schema_version": 1,
            "user_authorization_receipt_digest": DIGEST_B,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def readiness(
    event: dict[str, object], development: DevelopmentProvider | None
) -> dict[str, object]:
    """Invoke either the stable Hook or an explicit candidate plus the same consumer."""
    if development is not None:
        store = event.get("store_path")
        scope_id = event.get("scope_id")
        previous = event.get("previous_currentness_digest")
        if not isinstance(store, str) or not isinstance(scope_id, str):
            raise RuntimeError("development readiness event lacks Store or scope identity")
        if previous is not None and not isinstance(previous, str):
            raise RuntimeError("development readiness prior currentness digest is invalid")
        snapshot = parse_json_output(
            run(
                [
                    str(development.executable),
                    "continuation",
                    "readiness",
                    store,
                    "--scope-id",
                    scope_id,
                ],
                cwd=development.source_root,
            ),
            "development WorkVCS continuation readiness",
        )
        return load_runtime_module()._continuation_readiness_response(
            snapshot,
            scope_id,
            previous,
        )

    launcher, package_digest, _ = stable_hook()
    output = run(
        [
            str(launcher),
            "dispatch",
            "--contract",
            CONTRACT,
            "--package-digest",
            package_digest,
            "--handler",
            "continuation-readiness",
        ],
        input_text=json.dumps(event, sort_keys=True, separators=(",", ":")),
    )
    decoded: object = json.loads(output)
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise RuntimeError("continuation readiness output is not an object")
    return decoded


def required_bool(value: dict[str, object], field: str) -> bool:
    """Return one required boolean response field."""
    candidate = value.get(field)
    if not isinstance(candidate, bool):
        raise RuntimeError(f"readiness output.{field} is not boolean")
    return candidate


def required_string(value: dict[str, object], field: str) -> str:
    """Return one required non-empty string response field."""
    candidate = value.get(field)
    if not isinstance(candidate, str) or not candidate:
        raise RuntimeError(f"readiness output.{field} is not a string")
    return candidate


def required_object(value: dict[str, object], field: str) -> dict[str, object]:
    """Return one required object response field."""
    candidate = value.get(field)
    if not isinstance(candidate, dict) or not all(isinstance(key, str) for key in candidate):
        raise RuntimeError(f"readiness output.{field} is not an object")
    return candidate


def file_sha256(path: Path) -> str:
    """Hash one regular directory member."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(64 * 1024):
            digest.update(block)
    return digest.hexdigest()


def json_sha256(value: object) -> str:
    """Hash one canonical JSON-compatible evidence value."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def directory_snapshot(directory: Path) -> dict[str, dict[str, object]]:
    """Bind every Store-directory member, including SQLite WAL and SHM files."""
    snapshot: dict[str, dict[str, object]] = {}
    for path in sorted(directory.iterdir()):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"temporary Store directory contains a symlink: {path}")
        if stat.S_ISREG(info.st_mode):
            snapshot[path.name] = {
                "kind": "file",
                "size": info.st_size,
                "sha256": file_sha256(path),
            }
        elif stat.S_ISDIR(info.st_mode):
            snapshot[path.name] = {"kind": "directory"}
        else:
            snapshot[path.name] = {"kind": "other", "mode": stat.S_IFMT(info.st_mode)}
    return snapshot


def retain_wal_observation_connection(store: Path, branch_id: str) -> sqlite3.Connection:
    """Keep a real SQLite WAL connection open while observing all directory members."""
    connection = sqlite3.connect(store)
    journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
    if journal_mode != ("wal",):
        connection.close()
        raise RuntimeError("temporary WorkVCS Store did not enter SQLite WAL mode")
    branch_bytes = uuid.UUID(branch_id).bytes
    row = connection.execute(
        "SELECT lifecycle_state FROM branch WHERE branch_id = ?1",
        (branch_bytes,),
    ).fetchone()
    if row not in {("active",), ("closed",)}:
        connection.close()
        raise RuntimeError("temporary WorkVCS Branch has no valid lifecycle for sidecar setup")
    original_lifecycle = row[0]
    temporary_lifecycle = "closed" if row == ("active",) else "active"
    connection.execute(
        "UPDATE branch SET lifecycle_state = ?1 WHERE branch_id = ?2",
        (temporary_lifecycle, branch_bytes),
    )
    connection.execute(
        "UPDATE branch SET lifecycle_state = ?1 WHERE branch_id = ?2",
        (original_lifecycle, branch_bytes),
    )
    connection.commit()
    observed = connection.execute(
        "SELECT lifecycle_state FROM branch WHERE branch_id = ?1",
        (branch_bytes,),
    ).fetchone()
    if observed != (original_lifecycle,):
        connection.close()
        raise RuntimeError("temporary WorkVCS Branch lifecycle sidecar setup did not restore state")
    expected = {f"{store.name}-wal"}
    present = {path.name for path in store.parent.iterdir()}
    if not expected.issubset(present):
        connection.close()
        raise RuntimeError(
            "temporary WorkVCS Store did not retain its WAL member; present="
            + ",".join(sorted(present))
        )
    return connection


def set_fixture_branch_lifecycle(store: Path, branch_id: str, lifecycle: str) -> None:
    """Set one isolated fixture lifecycle through SQLite's mature typed adapter."""
    branch_bytes = uuid.UUID(branch_id).bytes
    with sqlite3.connect(store) as connection:
        cursor = connection.execute(
            "UPDATE branch SET lifecycle_state = ?1 WHERE branch_id = ?2",
            (lifecycle, branch_bytes),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("isolated fixture Branch lifecycle update did not affect one row")


def require_invalid_branch_lifecycle_error(
    workvcs: Path,
    command_cwd: Path,
    store: Path,
    scope_id: str,
) -> dict[str, object]:
    """Require native CLI typed failure without a readiness success envelope."""
    completed = run_completed(
        [
            str(workvcs),
            "--error-format",
            "json",
            "continuation",
            "readiness",
            str(store),
            "--scope-id",
            scope_id,
        ],
        cwd=command_cwd,
    )
    if completed.returncode == 0:
        raise RuntimeError("invalid Branch lifecycle unexpectedly returned exit zero")
    if completed.stdout.strip():
        raise RuntimeError("invalid Branch lifecycle unexpectedly returned readiness stdout")
    error = parse_json_output(completed.stderr, "invalid Branch lifecycle CLI error")
    message = error.get("message")
    if (
        error.get("error_code") != "continuation_invalid"
        or not isinstance(message, str)
        or "bogus_lifecycle" not in message
    ):
        raise RuntimeError("invalid Branch lifecycle did not return its typed native error")
    return error


def require_gap(response: dict[str, object], code: str) -> None:
    """Require one native provider gap code from the Hook response."""
    provider_gaps = response.get("provider_gaps")
    if not isinstance(provider_gaps, list):
        raise RuntimeError("readiness output.provider_gaps is not an array")
    codes = {
        item.get("code")
        for item in provider_gaps
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    if code not in codes:
        raise RuntimeError(f"readiness output is missing provider gap {code}")


def assert_readonly_query(
    directory: Path,
    event: dict[str, object],
    development: DevelopmentProvider | None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Prove persistent Store members unchanged while observing SQLite SHM coordination."""
    before = directory_snapshot(directory)
    response = readiness(event, development)
    after = directory_snapshot(directory)
    before_names = set(before)
    after_names = set(after)
    membership_changes = before_names.symmetric_difference(after_names)
    unexpected_membership_changes = {
        name for name in membership_changes if not name.endswith("-shm")
    }
    if unexpected_membership_changes:
        raise RuntimeError(
            "readiness inspection changed persistent Store directory membership: "
            + ", ".join(sorted(unexpected_membership_changes))
        )
    changed = sorted(
        name for name in before_names.intersection(after_names) if before[name] != after[name]
    )
    persistent_changed = [name for name in changed if not name.endswith("-shm")]
    if persistent_changed:
        raise RuntimeError(
            "readiness inspection changed persistent Store members: "
            + ", ".join(persistent_changed)
        )
    provider = required_object(response, "provider_snapshot")
    if provider.get("read_only") is not True or provider.get("store_opened_readonly") is not True:
        raise RuntimeError("native readiness did not prove a read-only Store open")
    return response, {
        "members_before": sorted(before_names),
        "members_after": sorted(after_names),
        "directory_snapshot_before_sha256": json_sha256(before),
        "directory_snapshot_after_sha256": json_sha256(after),
        "persistent_members_unchanged": True,
        "persistent_membership_unchanged": True,
        "sqlite_shm_changed": any(name.endswith("-shm") for name in changed)
        or any(name.endswith("-shm") for name in membership_changes),
        "sqlite_shm_membership_changed": any(name.endswith("-shm") for name in membership_changes),
        "changed_members": changed,
        "membership_changes": sorted(membership_changes),
        "sqlite_shm_before": {
            name: before[name] for name in sorted(before_names) if name.endswith("-shm")
        },
        "sqlite_shm_after": {
            name: after[name] for name in sorted(after_names) if name.endswith("-shm")
        },
    }


def require_sqlite_readonly_write_rejection(store: Path, branch_id: str) -> str:
    """Prove a mode=ro, query_only SQLite connection rejects an actual row write."""
    uri = f"file:{store}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        try:
            connection.execute(
                "UPDATE branch SET lifecycle_state = lifecycle_state WHERE branch_id = ?1",
                (uuid.UUID(branch_id).bytes,),
            )
        except sqlite3.OperationalError as error:
            message = str(error)
            if "readonly" not in message.lower():
                raise RuntimeError(
                    "SQLite readonly rejection had an unexpected diagnostic"
                ) from error
            return message
        raise RuntimeError("SQLite mode=ro query_only connection unexpectedly accepted a write")
    finally:
        connection.close()


def set_policy(
    workvcs: Path,
    store: Path,
    listener_session_id: str,
    *,
    expected_revision: int,
    enabled: bool,
    cwd: Path,
) -> None:
    """Apply one explicit temporary-Store policy transition."""
    run(
        [
            str(workvcs),
            "continuation",
            "project-policy-set",
            str(store),
            "--actor",
            listener_session_id,
            "--project-id",
            PROJECT_ID,
            "--expected-revision",
            str(expected_revision),
            "--enabled",
            "true" if enabled else "false",
            "--authority-json",
            authority(
                listener_session_id,
                expected_revision=expected_revision,
                enabled=enabled,
            ),
        ],
        cwd=cwd,
    )


def main() -> int:
    """Build a real scope and challenge native currentness and readonly guarantees."""
    arguments = parse_arguments()
    development = (
        development_provider(
            arguments.development_workvcs,
            arguments.development_source_root,
        )
        if arguments.development_workvcs is not None
        and arguments.development_source_root is not None
        else None
    )
    workvcs = development.executable if development is not None else stable_workvcs()
    command_cwd = development.source_root if development is not None else Path("/")
    status_command = [str(workvcs), "runtime", "status", "--format", "json"]
    source_paths = [Path(__file__).resolve(), RUNTIME, RUNTIME.with_name("package.json")]
    consumer: dict[str, object]
    if development is None:
        status_command.append("--require-stable")
        launcher, package_digest, installed_runtime = stable_hook()
        source_paths.extend(
            [launcher, installed_runtime, installed_runtime.with_name("package.json")]
        )
        consumer = {
            "kind": "installed_launcher_dispatch",
            "launcher_path": str(launcher),
            "package_digest": package_digest,
            "runtime_path": str(installed_runtime),
            "hook_event_execution_proven": False,
        }
    else:
        consumer = {"kind": "development_source_consumer", "runtime_path": str(RUNTIME)}
    runtime_status = parse_json_output(
        run(status_command, cwd=command_cwd), "evaluated WorkVCS runtime identity"
    )
    if runtime_status.get("executable_path") != str(workvcs):
        raise RuntimeError("evaluated WorkVCS runtime identity has a different executable path")
    binary_sha256 = file_sha256(workvcs)
    source_sha256 = {str(path): file_sha256(path) for path in source_paths}
    with tempfile.TemporaryDirectory(prefix="work-governance-continuation-readiness.") as name:
        directory = Path(name)
        store = directory / "workvcs.sqlite"
        run(
            [str(workvcs), "init", str(store), "--display-name", "readiness-eval"],
            cwd=command_cwd,
        )
        workspace = parse_records(
            run(
                [
                    str(workvcs),
                    "workspace",
                    "create",
                    str(store),
                    "--display-name",
                    "readiness-eval",
                    "--initial-branch-name",
                    "conversation-lane",
                ],
                cwd=command_cwd,
            )
        )
        workspace_id = require(workspace, "workspace_id")
        branch_id = require(workspace, "branch_id")
        task = parse_records(
            run(
                [
                    str(workvcs),
                    "task",
                    "create",
                    str(store),
                    "--branch",
                    branch_id,
                    "--head",
                    require(workspace, "genesis_commit_id"),
                    "--description",
                    "Validate continuation runtime readiness",
                ],
                cwd=command_cwd,
            )
        )
        task_entity_id = require(task, "task_entity_id")
        run(
            [
                str(workvcs),
                "projection",
                "refresh",
                str(store),
                "--branch",
                branch_id,
            ],
            cwd=command_cwd,
        )
        listener = parse_records(
            run(
                [
                    str(workvcs),
                    "session",
                    "start",
                    str(store),
                    "--workspace",
                    workspace_id,
                    "--branch",
                    branch_id,
                    "--metadata-json",
                    '{"thread_id":"eval-listener","workvcs_session_role":"listener"}',
                ],
                cwd=command_cwd,
            )
        )
        carrier = parse_records(
            run(
                [
                    str(workvcs),
                    "session",
                    "start",
                    str(store),
                    "--workspace",
                    workspace_id,
                    "--branch",
                    branch_id,
                    "--metadata-json",
                    '{"thread_id":"eval-work","workvcs_session_role":"work"}',
                ],
                cwd=command_cwd,
            )
        )
        listener_session_id = require(listener, "session_id")
        carrier_session_id = require(carrier, "session_id")
        claim = parse_records(
            run(
                [
                    str(workvcs),
                    "claim",
                    "task",
                    str(store),
                    "--session",
                    carrier_session_id,
                    "--task",
                    task_entity_id,
                ],
                cwd=command_cwd,
            )
        )
        set_policy(
            workvcs,
            store,
            listener_session_id,
            expected_revision=0,
            enabled=True,
            cwd=command_cwd,
        )
        scope = parse_records(
            run(
                [
                    str(workvcs),
                    "continuation",
                    "scope-bind",
                    str(store),
                    "--workspace",
                    workspace_id,
                    "--branch",
                    branch_id,
                    "--task",
                    task_entity_id,
                    "--listener",
                    listener_session_id,
                    "--carrier",
                    carrier_session_id,
                    "--claim",
                    require(claim, "claim_id"),
                    "--project-id",
                    PROJECT_ID,
                ],
                cwd=command_cwd,
            )
        )
        scope_id = require(scope, "scope.scope_id")
        if require(scope, "scope.project_id") != PROJECT_ID:
            raise RuntimeError("scope bind did not retain the exact Project id")
        if require(scope, "scope.project_binding_source") != "continuation.scope_bound":
            raise RuntimeError("scope bind did not retain native Project-binding provenance")
        query: dict[str, object] = {
            "schema_version": 1,
            "store_path": str(store),
            "scope_id": scope_id,
        }
        wal_connection = retain_wal_observation_connection(store, branch_id)

        readonly_write_error = require_sqlite_readonly_write_rejection(store, branch_id)
        directory_observations: list[dict[str, object]] = []
        baseline, baseline_observation = assert_readonly_query(directory, query, development)
        directory_observations.append(baseline_observation)
        if not required_bool(baseline, "provider_protocol_ready"):
            raise RuntimeError("provider protocol should be ready in the temporary Store")
        if required_bool(baseline, "automatic_rotation_ready"):
            raise RuntimeError("provider state alone must not prove automatic rotation readiness")
        if required_bool(baseline, "safe_to_dispatch_product_effect"):
            raise RuntimeError("readiness probe must not authorize a product effect")
        digest = required_string(baseline, "provider_snapshot_digest")

        unchanged_query = dict(query)
        unchanged_query["previous_currentness_digest"] = digest
        unchanged, unchanged_observation = assert_readonly_query(
            directory, unchanged_query, development
        )
        directory_observations.append(unchanged_observation)
        if required_object(unchanged, "meaning_change").get("status") != "unchanged":
            raise RuntimeError("unchanged provider state was not recognized")
        wal_connection.close()

        set_policy(
            workvcs,
            store,
            listener_session_id,
            expected_revision=1,
            enabled=False,
            cwd=command_cwd,
        )
        wal_connection = retain_wal_observation_connection(store, branch_id)
        revoked, revoked_observation = assert_readonly_query(
            directory, unchanged_query, development
        )
        directory_observations.append(revoked_observation)
        if required_object(revoked, "meaning_change").get("status") != "changed":
            raise RuntimeError("policy revocation was not recognized as a meaning change")
        if required_bool(revoked, "provider_protocol_ready"):
            raise RuntimeError("revoked Project policy must fail provider readiness")
        require_gap(revoked, "project_policy_disabled")
        wal_connection.close()

        set_policy(
            workvcs,
            store,
            listener_session_id,
            expected_revision=2,
            enabled=True,
            cwd=command_cwd,
        )
        set_fixture_branch_lifecycle(store, branch_id, "closed")
        wal_connection = retain_wal_observation_connection(store, branch_id)
        closed_warm = readiness(query, development)
        if required_bool(closed_warm, "provider_protocol_ready"):
            raise RuntimeError("a closed Branch must fail provider readiness")
        require_gap(closed_warm, "branch_not_active")
        closed_branch, closed_observation = assert_readonly_query(directory, query, development)
        directory_observations.append(closed_observation)
        if required_bool(closed_branch, "provider_protocol_ready"):
            raise RuntimeError("a closed Branch must fail provider readiness")
        require_gap(closed_branch, "branch_not_active")
        if required_string(closed_warm, "provider_snapshot_digest") != required_string(
            closed_branch, "provider_snapshot_digest"
        ):
            raise RuntimeError("closed Branch readiness was not stable across repeated reads")
        wal_connection.close()

        set_fixture_branch_lifecycle(store, branch_id, "bogus_lifecycle")
        invalid_branch_error = require_invalid_branch_lifecycle_error(
            workvcs,
            command_cwd,
            store,
            scope_id,
        )
        set_fixture_branch_lifecycle(store, branch_id, "active")
        run(
            [
                str(workvcs),
                "session",
                "end",
                str(store),
                "--session",
                listener_session_id,
                "--expected-session",
                listener_session_id,
                "--expected-lifecycle-state",
                "ended",
            ],
            cwd=command_cwd,
        )
        wal_connection = retain_wal_observation_connection(store, branch_id)
        stopped, stopped_observation = assert_readonly_query(directory, query, development)
        directory_observations.append(stopped_observation)
        wal_connection.close()
        if required_bool(stopped, "provider_protocol_ready"):
            raise RuntimeError("an ended listener must fail provider readiness")
        require_gap(stopped, "listener_not_active")
        observed_members: set[str] = set()
        for observation in directory_observations:
            for field in ("members_before", "members_after"):
                values = observation.get(field)
                if not isinstance(values, list) or not all(
                    isinstance(value, str) for value in values
                ):
                    raise RuntimeError("directory observation has invalid member evidence")
                observed_members.update(value for value in values if isinstance(value, str))

        if (
            parse_json_output(
                run(status_command, cwd=command_cwd), "final WorkVCS runtime identity"
            )
            != runtime_status
            or file_sha256(workvcs) != binary_sha256
        ):
            raise RuntimeError("evaluated WorkVCS identity changed during the probe")
        if {str(path): file_sha256(path) for path in source_paths} != source_sha256:
            raise RuntimeError("evaluated Hook or probe source changed during the probe")

        print(
            json.dumps(
                {
                    "schema_version": 3,
                    "evidence_kind": (
                        "development_candidate_native_plus_runtime_schema"
                        if development is not None
                        else "stable_hook_consumer"
                    ),
                    "requires_stable_rerun": development is not None,
                    "runtime_status": runtime_status,
                    "evaluated_binary_sha256": binary_sha256,
                    "source_sha256": source_sha256,
                    "identity_unchanged_during_evaluation": True,
                    "hook_consumer": consumer,
                    "native_command": "workvcs continuation readiness STORE --scope-id ID",
                    "temporary_store_protocol": "passed",
                    "readiness_persistent_members_unchanged": True,
                    "readiness_persistent_membership_unchanged": True,
                    "directory_members_bound": sorted(observed_members),
                    "directory_observations": directory_observations,
                    "sqlite_shm_coordination_observed": any(
                        observation["sqlite_shm_changed"] is True
                        for observation in directory_observations
                    ),
                    "sqlite_mode_ro_query_only_write_rejected": True,
                    "sqlite_readonly_write_error": readonly_write_error,
                    "provider_ready_before_revocation": True,
                    "provider_ready_after_revocation": False,
                    "stopped_listener_rejected": True,
                    "unchanged_currentness_detected": True,
                    "policy_revocation_detected": True,
                    "closed_branch_rejected": True,
                    "invalid_branch_lifecycle_typed_error": invalid_branch_error,
                    "automatic_rotation_ready": False,
                    "product_effects_performed": False,
                    "product_gap": "trusted_product_adapter_unavailable",
                    "baseline_currentness_digest": digest,
                    "revoked_currentness_digest": required_string(
                        revoked, "provider_snapshot_digest"
                    ),
                    "stopped_listener_currentness_digest": required_string(
                        stopped, "provider_snapshot_digest"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
