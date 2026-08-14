from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from workctl_modules import yaml_compat as yaml
from workctl_modules.filesystem import checked_project_path, relative_project_path, sha256_file
from workctl_modules.paths import index_path, legacy_plan_dir, plan_dir

POINTER_MARKER = "WORK_GOVERNANCE_NON_AUTHORITY_POINTER"


class PlanSourceError(Exception):
    """Raised when a plan source cannot be inspected safely."""


@dataclass(frozen=True)
class PlanSource:
    path: str
    classification: str
    origin: str
    signals: list[str]
    sha256: str
    plan_id: str | None = None
    revision: int | None = None
    status: str | None = None
    reason: str | None = None
    history_visible: bool = False


def _as_mapping(value: object) -> Mapping[object, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _read_index_payload(path: Path) -> Mapping[object, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return _as_mapping(cast(object, raw))


def _frontmatter_metadata(path: Path) -> Mapping[object, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanSourceError(f"failed to read Plan source {path}: {exc}") from exc
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    try:
        raw = yaml.safe_load(text[4:end].strip()) or {}
    except Exception:
        return {}
    return _as_mapping(cast(object, raw))


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return left.resolve() == right.resolve()


def _record_path(candidate_paths: dict[Path, set[str]], path: Path, origin: str) -> None:
    for existing_path, origins in candidate_paths.items():
        if _same_path(existing_path, path):
            origins.add(origin)
            return
    candidate_paths[path] = {origin}


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def is_legacy_plan_authority_path(
    root: Path,
    raw_path: str,
    path: Path,
    *,
    plan_dir_name: str,
) -> bool:
    normalized = Path(os.path.normpath(raw_path))
    lexical_legacy = bool(normalized.parts and normalized.parts[0] == plan_dir_name)
    legacy = legacy_plan_dir(root, plan_dir_name).resolve()
    resolved = path.resolve()
    physical_legacy = resolved == legacy or legacy in resolved.parents
    return lexical_legacy or physical_legacy


def _active_plan_path(root: Path, *, governance_dir_name: str, plan_dir_name: str) -> Path | None:
    idx = index_path(root, governance_dir_name, plan_dir_name)
    if not idx.is_file():
        return None
    payload = _read_index_payload(idx)
    active_id = payload.get("active_plan_id")
    plans_raw = payload.get("plans")
    if not isinstance(active_id, str) or not isinstance(plans_raw, list):
        return None
    for item_raw in plans_raw:
        item = _as_mapping(cast(object, item_raw))
        if item.get("id") != active_id:
            continue
        relative = item.get("path")
        if not isinstance(relative, str) or not relative:
            return None
        try:
            candidate = (plan_dir(root, governance_dir_name, plan_dir_name) / relative).resolve()
            candidate.relative_to(plan_dir(root, governance_dir_name, plan_dir_name).resolve())
            return candidate
        except Exception:
            return None
    return None


def optional_plan_metadata(path: Path) -> tuple[str | None, int | None, str | None]:
    metadata = _frontmatter_metadata(path)
    plan_id_raw = metadata.get("plan_id")
    revision_raw = metadata.get("revision")
    status_raw = metadata.get("status")
    plan_id = plan_id_raw if isinstance(plan_id_raw, str) else None
    revision = revision_raw if isinstance(revision_raw, int) else None
    status = status_raw if isinstance(status_raw, str) else None
    return plan_id, revision, status


def candidate_signals(path: Path, active: bool, rules_confirmed: bool) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PlanSourceError(f"failed to read Plan source {path}: {exc}") from exc
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
        r"\b(archive|evidence|log|technical design|phase design)\b|归档|证据|日志|技术方案",
        lowered,
    ):
        signals.append("non-authority-document")
    return signals


def project_rule_references(
    root: Path,
    *,
    governance_dir_name: str = ".work-governance",
    plan_dir_name: str = "_Plan",
) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    path_pattern = re.compile(
        r"(?<![A-Za-z0-9._/-])"
        rf"(?:{re.escape(governance_dir_name)}/{re.escape(plan_dir_name)}/[A-Za-z0-9._/-]+\.md"
        r"|docs/[A-Za-z0-9._/-]*[Pp]lan\.md|[Pp]lan\.md)"
        r"(?![A-Za-z0-9._/-])"
    )
    authority_pattern = re.compile(
        r"\b(authoritative|current|must\s+(?:read|update)|single\s+active)\b"
        r"|执行权威|当前.*计划|必须(?:读取|更新)|唯一.*计划",
        re.IGNORECASE,
    )
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            raise PlanSourceError(f"failed to read project rule file {name}: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if authority_pattern.search(line) is None:
                continue
            for match in path_pattern.finditer(line):
                raw_path = match.group(0)
                references.setdefault(raw_path, []).append(f"{name}:{line_number}")
    return references


def classify_candidate(
    path: Path,
    signals: Sequence[str],
    *,
    active: bool,
    rules_confirmed: bool,
    explicit_classification: str | None,
) -> tuple[str, str | None]:
    signal_set = set(signals)
    plan_id, _revision, status = optional_plan_metadata(path)
    if explicit_classification:
        if isinstance(signals, list):
            signals.append("agent-classification")
        return explicit_classification, None
    if active or rules_confirmed:
        return "CONFIRMED_AUTHORITY", None
    if "migration-pointer" in signal_set:
        return "NON_AUTHORITY", "migration_pointer"
    if plan_id and status == "complete":
        if isinstance(signals, list):
            signals.append("completed-plan")
        return "NON_AUTHORITY", "completed_plan_ignored"
    if plan_id and status == "retired":
        if isinstance(signals, list):
            signals.append("retired-plan")
        return "NON_AUTHORITY", "retired_plan_ignored"
    control_signals = {"controls-goal", "controls-phases", "controls-queue", "controls-gates"}
    if "self-claims-authority" in signal_set and len(signal_set & control_signals) >= 2:
        return "LIKELY_AUTHORITY", None
    return "NON_AUTHORITY", None


def _record_candidate(
    *,
    root: Path,
    candidate_paths: dict[Path, set[str]],
    raw_path: str,
    origin: str,
    governance_dir_name: str,
    plan_dir_name: str,
    reject_legacy: bool = False,
) -> None:
    path = checked_project_path(root, raw_path)
    if not path.exists() or not path.is_file():
        return
    if is_legacy_plan_authority_path(root, raw_path, path, plan_dir_name=plan_dir_name):
        if reject_legacy:
            raise PlanSourceError(f"LEGACY_ROOT_AUTHORITY_FORBIDDEN: {raw_path}")
        return
    _record_path(candidate_paths, path, origin)


def _history_visible(
    path: Path,
    origins: set[str],
    root: Path,
    *,
    governance_dir_name: str,
    plan_dir_name: str,
) -> bool:
    source_plan_dir = plan_dir(root, governance_dir_name, plan_dir_name)
    if _is_under(path, source_plan_dir) and path.name.startswith("PLAN-") and path.suffix == ".md":
        return True
    return "conventional-path" in origins


def discover_plan_sources(
    root: Path,
    *,
    explicit_candidates: Sequence[tuple[str, str | None]] | None = None,
    governance_dir_name: str = ".work-governance",
    plan_dir_name: str = "_Plan",
) -> list[PlanSource]:
    explicit_candidates = list(explicit_candidates or [])
    explicit_by_identity: dict[tuple[int, int], str] = {}
    candidate_paths: dict[Path, set[str]] = {}
    rules = project_rule_references(
        root,
        governance_dir_name=governance_dir_name,
        plan_dir_name=plan_dir_name,
    )
    active_path = _active_plan_path(
        root,
        governance_dir_name=governance_dir_name,
        plan_dir_name=plan_dir_name,
    )

    for raw, origins in rules.items():
        _record_candidate(
            root=root,
            candidate_paths=candidate_paths,
            raw_path=raw,
            origin=",".join(origins),
            governance_dir_name=governance_dir_name,
            plan_dir_name=plan_dir_name,
        )
    for raw in ("Plan.md", "plan.md", "docs/Plan.md", "docs/plan.md"):
        _record_candidate(
            root=root,
            candidate_paths=candidate_paths,
            raw_path=raw,
            origin="conventional-path",
            governance_dir_name=governance_dir_name,
            plan_dir_name=plan_dir_name,
        )
    for path in sorted(plan_dir(root, governance_dir_name, plan_dir_name).glob("*.md")):
        if path.is_file():
            _record_path(candidate_paths, path.resolve(), "governance-plan-file")
    for raw_path, classification in explicit_candidates:
        path = checked_project_path(root, raw_path)
        if not path.exists() or not path.is_file():
            raise PlanSourceError(f"explicit Plan candidate not found or not a file: {raw_path}")
        if is_legacy_plan_authority_path(root, raw_path, path, plan_dir_name=plan_dir_name):
            raise PlanSourceError(f"LEGACY_ROOT_AUTHORITY_FORBIDDEN: {raw_path}")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        explicit_classification = classification or "CONFIRMED_AUTHORITY"
        existing = explicit_by_identity.get(identity)
        if existing is not None and existing != explicit_classification:
            raise PlanSourceError(
                f"CONFLICTING_CANDIDATE_CLASSIFICATION: {relative_project_path(root, path)}"
            )
        _record_path(candidate_paths, path, "agent-input")
        explicit_by_identity[identity] = explicit_classification
    if active_path and active_path.exists():
        _record_path(candidate_paths, active_path, "index")

    sources: list[PlanSource] = []
    for path in sorted(candidate_paths, key=lambda item: relative_project_path(root, item)):
        origins = sorted(candidate_paths[path])
        origin = origins[0] if len(origins) == 1 else ",".join(origins)
        active = bool(active_path and _same_path(path, active_path))
        rules_confirmed = any(
            origin.startswith("AGENTS.md:") or origin.startswith("CLAUDE.md:")
            for origin in origins
        )
        explicit_classification = explicit_by_identity.get(
            (path.stat().st_dev, path.stat().st_ino)
        )
        signals = candidate_signals(path, active=active, rules_confirmed=rules_confirmed)
        classification, reason = classify_candidate(
            path,
            signals,
            active=active,
            rules_confirmed=rules_confirmed,
            explicit_classification=explicit_classification,
        )
        rel = relative_project_path(root, path)
        if reason is None and "conventional-path" in origins and classification == "NON_AUTHORITY":
            reason = "historical_conventional_plan_ignored"
        plan_id, revision, status = optional_plan_metadata(path)
        sources.append(
            PlanSource(
                path=rel,
                classification=classification,
                origin=origin,
                signals=signals,
                sha256=sha256_file(path),
                plan_id=plan_id,
                revision=revision,
                status=status,
                reason=reason,
                history_visible=_history_visible(
                    path,
                    set(origins),
                    root,
                    governance_dir_name=governance_dir_name,
                    plan_dir_name=plan_dir_name,
                ),
            )
        )
    return sources
