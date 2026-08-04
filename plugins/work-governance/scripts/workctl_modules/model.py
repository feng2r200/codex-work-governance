"""Small typed projections shared by controller boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskProjection:
    """Immutable task data needed by the scheduler."""

    task_id: str
    status: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class SchedulerProjection:
    """Bounded scheduler output independent from Plan serialization."""

    current_task: str | None
    ready: tuple[str, ...]
    blocked: tuple[str, ...]
    next_suggestion: str


@dataclass(frozen=True)
class V5ContractProjection:
    """Stable contract references for a schema-v5 Plan bundle."""

    plan_id: str
    contract_revision: int
    state_ref: str
    event_ref: str
    evidence_ref: str
    truth_refs: tuple[str, ...]


@dataclass(frozen=True)
class V5StateProjection:
    """Runtime state projection independent from the durable contract."""

    plan_id: str
    state_sequence: int
    event_sequence: int
    current_task: str | None
    tasks: dict[str, dict[str, Any]]
    priorities: dict[str, int]
