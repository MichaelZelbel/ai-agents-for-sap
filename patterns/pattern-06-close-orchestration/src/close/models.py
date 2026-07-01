"""Data models for close orchestration.

Money is always a Decimal, never a float. The plan and every task are frozen
dataclasses. A frozen plan cannot be edited in place. The only way to change
it is to build a new one, which keeps the "human approves any change" rule
honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional

Status = Literal["not_started", "in_progress", "done", "blocked"]

# The kind of mitigation the deterministic part proposes.
Action = Literal["remind", "resequence", "escalate"]


@dataclass(frozen=True)
class CloseTask:
    """One task in the month-end close.

    `depends_on` lists task ids that must finish first. `impact` is the money
    at stake if this task blocks the close (a proxy for how much it matters).
    The signals are plain booleans a real system would derive from history.
    """

    task_id: str
    name: str
    owner: str
    deadline: str  # ISO date, e.g. "2026-07-03"
    status: Status
    impact: Decimal
    depends_on: tuple[str, ...] = ()
    # Signals. These feed the scorer and the deterministic mitigation.
    late_last_period: bool = False
    queue_backed_up: bool = False
    owner_overloaded: bool = False


@dataclass(frozen=True)
class ClosePlan:
    """The whole close plan: an ordered, frozen set of tasks."""

    period: str  # e.g. "2026-06"
    tasks: tuple[CloseTask, ...]

    def get(self, task_id: str) -> CloseTask:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(task_id)


@dataclass(frozen=True)
class BlockerPrediction:
    """The agent's read on one task: how likely it is to block, and why."""

    task_id: str
    score: Decimal  # 0.00 to 1.00, higher means more likely to block
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Mitigation:
    """A proposed change to the plan. Deterministic, derived from a score."""

    task_id: str
    action: Action
    detail: str
    # The before/after preview. `after` is None for actions that do not move
    # a deadline (a plain reminder). A resequence sets a new deadline.
    before_deadline: Optional[str] = None
    after_deadline: Optional[str] = None


@dataclass(frozen=True)
class StagedIntervention:
    """A mitigation held for review. Nothing is applied until a human says yes."""

    staged_id: str
    prediction: BlockerPrediction
    mitigation: Mitigation


@dataclass(frozen=True)
class InterventionResult:
    """The outcome of one staged intervention."""

    staged_id: str
    outcome: str  # "applied" or "rejected_by_human"
    plan: ClosePlan
