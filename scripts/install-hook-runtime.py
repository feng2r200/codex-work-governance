#!/usr/bin/python3 -I
"""Install and inspect the stable Work Governance hook runtime."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

CONTRACT = "wg-hook-v1"
ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "plugins" / "work-governance" / "runtime"
LAUNCHER_SOURCE = ROOT / "scripts" / "work-governance-hook"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _source_manifest() -> tuple[dict[str, Any], str]:
    manifest = json.loads((RUNTIME_ROOT / "package.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(_canonical(manifest)).hexdigest()
    if manifest.get("contract") != CONTRACT or manifest.get("schema_version") != 1:
        raise RuntimeError("source package manifest is incompatible")
    for entry in manifest.get("files", []):
        path = RUNTIME_ROOT / entry["path"]
        if path.name != entry["path"] or path.is_symlink() or not path.is_file():
            raise RuntimeError(f"source package file is unsafe: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"source package file digest mismatch: {path}")
    return manifest, digest


def _private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError(f"installation directory is unsafe: {path}")


def _safe_parent_dir(path: Path) -> None:
    """Create a parent directory without tightening unrelated existing modes."""
    path.mkdir(mode=0o755, parents=True, exist_ok=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"installation parent is not a real directory: {path}")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise RuntimeError(f"installation parent is not safely owner-controlled: {path}")


def _install_package(home: Path, expected: str | None) -> str:
    manifest, digest = _source_manifest()
    if expected is not None and expected != digest:
        raise RuntimeError(f"expected package digest {expected}, computed {digest}")
    root = home / ".local" / "libexec" / "work-governance"
    for path in (home / ".local", home / ".local" / "libexec"):
        _safe_parent_dir(path)
    _private_dir(root)
    destination = root / digest
    if destination.exists():
        _validate_installed_package(destination, manifest, digest)
        return digest
    temporary = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=root))
    try:
        temporary.chmod(0o700)
        for entry in manifest["files"]:
            target = temporary / entry["path"]
            target.write_bytes((RUNTIME_ROOT / entry["path"]).read_bytes())
            target.chmod(0o600)
        manifest_path = temporary / "package.json"
        manifest_path.write_bytes(_canonical(manifest) + b"\n")
        manifest_path.chmod(0o600)
        os.rename(temporary, destination)
    except OSError:
        if not destination.exists():
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        shutil.rmtree(temporary)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _validate_installed_package(destination, manifest, digest)
    return digest


def _validate_installed_package(
    destination: Path, manifest: dict[str, Any], expected_digest: str
) -> None:
    info = destination.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("installed package is not a real directory")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("installed package is not owner-private")
    installed_manifest = json.loads((destination / "package.json").read_text(encoding="utf-8"))
    if hashlib.sha256(_canonical(installed_manifest)).hexdigest() != expected_digest:
        raise RuntimeError("installed package manifest digest mismatch")
    if installed_manifest != manifest:
        raise RuntimeError("installed package manifest differs from the source manifest")
    expected_names = {"package.json"}
    for entry in manifest["files"]:
        expected_names.add(entry["path"])
        path = destination / entry["path"]
        file_info = path.lstat()
        if stat.S_ISLNK(file_info.st_mode) or not stat.S_ISREG(file_info.st_mode):
            raise RuntimeError(f"installed package file is unsafe: {path}")
        if file_info.st_uid != os.getuid() or stat.S_IMODE(file_info.st_mode) & 0o077:
            raise RuntimeError(f"installed package file is not owner-private: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"installed package file digest mismatch: {path}")
    if {path.name for path in destination.iterdir()} != expected_names:
        raise RuntimeError("installed package tree contains unexpected members")


def _install_launcher(home: Path, probe_digests: list[str], rollback_digest: str | None) -> None:
    bin_dir = home / ".local" / "bin"
    _safe_parent_dir(home / ".local")
    _safe_parent_dir(bin_dir)
    target = bin_dir / "work-governance-hook"
    lock_path = bin_dir / ".work-governance-hook.install.lock"
    lock_descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        lock_info = os.fstat(lock_descriptor)
        if lock_info.st_uid != os.getuid() or stat.S_IMODE(lock_info.st_mode) & 0o077:
            raise RuntimeError("launcher installation lock is not owner-private")
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        previous: bytes | None = None
        if target.exists() or target.is_symlink():
            target_info = target.lstat()
            if (
                stat.S_ISLNK(target_info.st_mode)
                or not stat.S_ISREG(target_info.st_mode)
                or target_info.st_uid != os.getuid()
                or stat.S_IMODE(target_info.st_mode) & 0o077
            ):
                raise RuntimeError("existing launcher is unsafe")
            previous = target.read_bytes()
        if previous is not None and rollback_digest is None:
            raise RuntimeError(
                "launcher upgrade requires --rollback-digest for the current package"
            )
        if previous is None and rollback_digest is not None:
            raise RuntimeError("fresh launcher installation cannot name a rollback digest")
        if rollback_digest is not None:
            if rollback_digest not in probe_digests:
                raise RuntimeError("rollback digest must also be included in --probe-digest")
            _probe(home, rollback_digest)
        _replace_launcher(target, LAUNCHER_SOURCE.read_bytes())
        try:
            for digest in probe_digests:
                _probe(home, digest)
        except Exception as candidate_error:
            if previous is None:
                target.unlink(missing_ok=True)
                raise RuntimeError(
                    f"candidate launcher probe failed; fresh launcher removed: {candidate_error}"
                ) from candidate_error
            try:
                _replace_launcher(target, previous)
            except Exception as restore_error:
                raise RuntimeError(
                    "candidate launcher probe failed and rollback launcher restore failed: "
                    f"candidate={candidate_error}; rollback={restore_error}"
                ) from restore_error
            try:
                _probe(home, rollback_digest)
            except Exception as rollback_error:
                raise RuntimeError(
                    "candidate launcher probe failed and rollback launcher probe failed: "
                    f"candidate={candidate_error}; rollback={rollback_error}"
                ) from rollback_error
            raise RuntimeError(
                "candidate launcher probe failed; rollback launcher restored and verified: "
                f"{candidate_error}"
            ) from candidate_error
    finally:
        os.close(lock_descriptor)


def _replace_launcher(target: Path, content: bytes) -> None:
    temporary = target.parent / (f".work-governance-hook.{os.getpid()}.{time.time_ns()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, target)


def _probe(home: Path, digest: str) -> dict[str, Any]:
    launcher = home / ".local" / "bin" / "work-governance-hook"
    process = subprocess.run(
        [
            str(launcher),
            "probe",
            "--contract",
            CONTRACT,
            "--package-digest",
            digest,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        timeout=10,
    )
    result = json.loads(process.stdout)
    if result != {"contract": CONTRACT, "package_digest": digest, "ok": True}:
        raise RuntimeError("launcher probe returned an unexpected result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path.home())
    subparsers = parser.add_subparsers(dest="command", required=True)
    package = subparsers.add_parser("package")
    package.add_argument("--expected-digest")
    launcher = subparsers.add_parser("launcher")
    launcher.add_argument("--probe-digest", action="append", required=True)
    launcher.add_argument("--rollback-digest")
    status = subparsers.add_parser("status")
    status.add_argument("--package-digest", required=True)
    args = parser.parse_args()
    home = args.home.resolve()
    if args.command == "package":
        digest = _install_package(home, args.expected_digest)
        print(json.dumps({"package_digest": digest, "package_installed": True}, sort_keys=True))
    elif args.command == "launcher":
        _install_launcher(home, args.probe_digest, args.rollback_digest)
        print(
            json.dumps(
                {
                    "launcher_installed": True,
                    "probed": args.probe_digest,
                    "rollback_digest": args.rollback_digest,
                },
                sort_keys=True,
            )
        )
    else:
        result = _probe(home, args.package_digest)
        print(json.dumps({"launcher": str(home / ".local/bin/work-governance-hook"), **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
