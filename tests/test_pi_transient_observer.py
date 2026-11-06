"""Exercise the bounded vnode observer with an immediate create/remove control."""

import importlib.util
import select
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "pi_transient_observer",
    Path(__file__).resolve().parents[1] / "scripts/pi_transient_observer.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.skipif(not hasattr(select, "kqueue"), reason="requires kqueue")
def test_observer_detects_transient_entry_and_quiet_control(tmp_path: Path) -> None:
    """A transient child changes the directory; no subsequent write stays quiet."""
    observer = MODULE.DirectoryObserver(tmp_path)
    try:
        assert observer.observe() == []
        probe = tmp_path / "probe"
        probe.write_text("value", encoding="utf-8")
        probe.unlink()
        assert observer.observe()
        assert observer.intact()
        assert observer.observe() == []
    finally:
        observer.close()


@pytest.mark.skipif(not hasattr(select, "kqueue"), reason="requires kqueue")
def test_observer_detects_push_then_ref_restoration(tmp_path: Path) -> None:
    """A changed and restored remote ref is observable even though final HEAD matches."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=work, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "trial")
    git("config", "user.email", "trial@example.invalid")
    (work / "file").write_text("first", encoding="utf-8")
    git("add", "file")
    git("commit", "-qm", "first")
    git("push", "-q", "origin", "HEAD")
    baseline = git("rev-parse", "HEAD")
    branch = git("symbolic-ref", "--short", "HEAD")
    observer = MODULE.DirectoryObserver(remote / "refs/heads")
    try:
        (work / "file").write_text("second", encoding="utf-8")
        git("commit", "-qam", "second")
        git("push", "-q", "origin", "HEAD")
        subprocess.run(
            ["git", "--git-dir", str(remote), "update-ref", f"refs/heads/{branch}", baseline],
            check=True,
        )
        actual = subprocess.run(
            ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert actual == baseline
        assert observer.observe()
        assert observer.intact()
    finally:
        observer.close()
