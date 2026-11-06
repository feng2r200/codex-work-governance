"""Exercise the version gate with an isolated, real Git repository."""

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(root: Path, *command: str) -> subprocess.CompletedProcess[str]:
    """Execute a command inside the isolated repository."""
    return subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)


def test_package_only_change_requires_version_bump(tmp_path: Path) -> None:
    """A package-only change is detected, and a coordinated bump is accepted."""
    root = tmp_path / "repo"
    root.mkdir()
    for relative in (
        "scripts/validate-version-bump.sh",
        "pyproject.toml",
        "package.json",
        "plugins/work-governance/plugin.json",
        "plugins/work-governance/.codex-plugin/plugin.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    assert run(root, "git", "init", "-q").returncode == 0
    assert run(root, "git", "add", ".").returncode == 0
    assert (
        run(
            root,
            "git",
            "-c",
            "user.name=probe",
            "-c",
            "user.email=probe@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ).returncode
        == 0
    )
    package = root / "package.json"
    package.write_text(package.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = run(root, "bash", "scripts/validate-version-bump.sh", "--base-ref", "HEAD")
    assert result.returncode != 0
    assert "require a semantic version bump" in result.stderr
    project = root / "pyproject.toml"
    project_text = project.read_text(encoding="utf-8")
    version = tomllib.loads(project_text)["project"]["version"]
    major, minor, patch = (int(part) for part in version.split("."))
    bumped = f"{major}.{minor}.{patch + 1}"
    project.write_text(
        project_text.replace(f'version = "{version}"', f'version = "{bumped}"', 1),
        encoding="utf-8",
    )
    manifests = (
        root / "plugins/work-governance/plugin.json",
        root / "plugins/work-governance/.codex-plugin/plugin.json",
    )
    for path in manifests:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = bumped
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    result = run(root, "bash", "scripts/validate-version-bump.sh", "--base-ref", "HEAD")
    assert result.returncode == 0, result.stderr
    assert "work_governance_version_bump_verified=true" in result.stdout
