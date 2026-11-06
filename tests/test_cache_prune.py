"""Exercise cache cleanup against isolated temporary directories."""

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prune-local-plugin-cache.sh"


def make_version(root: Path, version: str) -> Path:
    """Create a verified cache entry in the isolated test root."""
    target = root / version
    target.mkdir(parents=True)
    (target / "plugin.json").write_text(
        json.dumps({"name": "work-governance", "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def prune(root: Path, keep: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the actual cleanup command against the isolated test root."""
    return subprocess.run(
        ["bash", str(SCRIPT), "--cache-root", str(root), "--keep-version", keep, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_old_keep_refuses_before_any_deletion(tmp_path: Path) -> None:
    """A newer verified version blocks all deletion, including earlier candidates."""
    root = tmp_path / "work-governance"
    oldest = make_version(root, "2.9.0")
    keep = make_version(root, "3.0.0")
    newest = make_version(root, "3.1.0")
    result = prune(root, "3.0.0")
    assert result.returncode != 0
    assert "verified newer version exists" in result.stderr
    assert all(path.exists() for path in (oldest, keep, newest))


def test_current_keep_removes_only_verified_older_versions(tmp_path: Path) -> None:
    """Dry-run does not mutate; real execution removes a verified older entry only."""
    root = tmp_path / "work-governance"
    old = make_version(root, "3.0.0")
    keep = make_version(root, "3.1.0")
    invalid = root / "1.0.0"
    invalid.mkdir()
    result = prune(root, "3.1.0", "--dry-run")
    assert result.returncode == 0
    assert "would_remove=" in result.stdout
    assert old.exists() and keep.exists() and invalid.exists()
    result = prune(root, "3.1.0")
    assert result.returncode == 0
    assert not old.exists() and keep.exists() and invalid.exists()


def test_version_components_are_compared_numerically(tmp_path: Path) -> None:
    """Multi-digit semantic version components compare by value, not raw text."""
    root = tmp_path / "work-governance"
    old = make_version(root, "3.9.99")
    new = make_version(root, "3.10.0")
    assert prune(root, "3.9.99").returncode != 0
    assert old.exists() and new.exists()
    assert prune(root, "3.10.0").returncode == 0
    assert not old.exists() and new.exists()
