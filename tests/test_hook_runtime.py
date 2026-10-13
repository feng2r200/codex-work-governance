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
