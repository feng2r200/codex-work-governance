import concurrent.futures
import hashlib
import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-hook-runtime.py"
MANIFEST = ROOT / "plugins" / "work-governance" / "runtime" / "package.json"
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
