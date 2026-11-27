"""Plain data types shared by every AI module.

The AI package never imports the web framework or the database. The backend
converts database rows into these dataclasses, calls ``ai.pipeline.plan``,
and stores what comes back. This keeps every algorithm testable on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional

PRIORITY_WEIGHTS = {1: 1.0, 2: 2.0, 3: 3.0, 4: 5.0}  # Low, Medium, High, Critical
PRIORITY_NAMES = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}


@dataclass
class TaskIn:
    """A task as the scheduler sees it."""

    id: int
    title: str
    category: str
    priority: int  # 1 Low .. 4 Critical
    est_minutes: int
    mental_difficulty: int = 5  # 1-10
    physical_difficulty: int = 3  # 1-10
    mental_req: int = 5  # 1-10, mental energy required
    physical_req: int = 3  # 1-10, physical energy required
    deadline: Optional[datetime] = None
    depends_on: Optional[int] = None
    is_fixed: bool = False
    fixed_start: Optional[datetime] = None
    fixed_end: Optional[datetime] = None
    minutes_done: int = 0  # minutes already spent (partial outcomes carry over)
    not_before: Optional[datetime] = None  # release time, e.g. a repeating task's copy waits for its own day

    @property
    def weight(self) -> float:
        return PRIORITY_WEIGHTS.get(self.priority, 2.0)

    @property
    def mental_demand(self) -> float:
        """Combined mental demand on 1-10: 0.6 x requirement + 0.4 x difficulty."""
        return round(0.6 * self.mental_req + 0.4 * self.mental_difficulty, 1)

    @property
    def physical_demand(self) -> float:
        return round(0.6 * self.physical_req + 0.4 * self.physical_difficulty, 1)


@dataclass
class Commitment:
    """Time the scheduler must not use: a lecture, a meeting, sleep, travel."""

    start: datetime
    end: datetime
    label: str = "Busy"
    kind: str = "fixed"  # "fixed" or "unavailable"


@dataclass
class CheckIn:
    recorded_at: datetime
    mental: float
    physical: float
    focus: float
    stress: float


@dataclass
class Preferences:
    day_start: time = time(8, 0)
    day_end: time = time(22, 0)
    break_minutes: int = 10
    max_focus_block: int = 90
    no_work_after: time = time(21, 0)
    preset: str = "balanced"
    horizon_days: int = 3


@dataclass
class OutcomeContext:
    """What was known about a block when it was planned: the inputs of the completion model.

    Captured at planning time, so training never uses information from after the
    block's start (no leakage from the outcome itself or from later check-ins).
    """

    start: datetime
    mental_demand: float
    physical_demand: float
    expected_mental: float  # projected mental energy at the block's start, 0-10
    expected_physical: float
    focus: float
    stress: float


@dataclass
class Outcome:
    """A recorded result for one planned block.

    status: "done", "partial" or "skipped" are real outcomes. "unreached" means the
    block never got the chance to start (the day ran out first): it is censored, so
    it is left out of follow-through and completion learning.
    """

    category: str
    status: str
    est_minutes: int
    actual_minutes: Optional[int] = None
    context: Optional[OutcomeContext] = None


@dataclass
class PlanRequest:
    now: datetime
    tasks: list[TaskIn]
    commitments: list[Commitment] = field(default_factory=list)
    checkins: list[CheckIn] = field(default_factory=list)  # history, newest last
    outcomes: list[Outcome] = field(default_factory=list)
    prefs: Preferences = field(default_factory=Preferences)
    seed: int = 42
    locked: list[tuple[int, datetime]] = field(default_factory=list)  # (task_id, start) kept in place
    # Stability-aware replanning: the plan being replaced, as (task_id, start), and how strongly
    # to keep it (0 = free replan, 1 = moving a block costs about as much as dropping a priority task).
    previous: list[tuple[int, datetime]] = field(default_factory=list)
    stability: float = 0.0
    optimizer: str = "hybrid"  # "ga", "hybrid" or "cpsat" (see ai.pipeline.OPTIMIZERS)
    duration_version: Optional[str] = None  # "v1" or "v2"; None = the default model
    # How much time to reserve per block, as a quantile of the predicted duration
    # (0.8 = P80). Predicting a duration and deciding how long to reserve are separate choices.
    reserve_quantile: float = 0.8
    # Fraction of each day's free time kept empty at the end of the day as a shared buffer.
    day_buffer: float = 0.0
    # Ablation switches, used only by the evaluation lab: "no_context" (every slot of a task
    # gets the same completion probability), "fuzzy_reference" (slots ranked by the fuzzy
    # suitability score instead) and "no_probability" (blocks are the user's own estimate
    # instead of the learned duration).
    ablations: tuple[str, ...] = ()
    # Monte Carlo replays per plan: "quick" (30), "standard" (100), "research" (300) or
    # "adaptive" (30 upward until the estimate is precise enough; see ai.uncertainty).
    simulation: str = "standard"
    # Choose the main plan by simulated outcome (ai.selection). Off by default: in the
    # closed-loop evaluation it made no measurable difference and planning took about 4x longer.
    select_by_outcome: bool = False
