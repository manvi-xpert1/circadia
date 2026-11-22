"""Synthetic users with hidden ground truth (design: Evaluation plan).

Each synthetic user has parameters the planner never sees:
  - a true overrun ratio per category,
  - a true daily energy curve that differs from the planner's default profile,
  - a true follow-through rate.

The planner only sees noisy morning check-ins and the outcomes it observes.
How well a block really fits is judged by a simple ground-truth formula that is
deliberately NOT the planner's fuzzy model, so the evaluation is not circular:

    true_fit = exp(-(mental deficit)^2 / 10 - (physical deficit)^2 / 12)

where a deficit is how far the task's demand exceeds the user's true energy at
that moment (0 if energy is enough).

SYNTHETIC DATA: everything here is made up for testing and is never stored as
a user record.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from ..types import CheckIn, Commitment, TaskIn

CATEGORIES = ["Study", "Work", "Errand", "Health", "Admin"]
BANDS = [(0, 9), (9, 12), (12, 13), (13, 15), (15, 18), (18, 21), (21, 24)]
DAY_START, DAY_END = time(8, 0), time(22, 0)


def _band(t: datetime) -> int:
    h = t.hour + t.minute / 60
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= h < hi:
            return i
    return len(BANDS) - 1


def clip(v: float, lo: float = 1.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, v))


@dataclass
class TrueState:
    mental: float
    physical: float
    focus: float
    stress: float


@dataclass
class SyntheticUser:
    seed: int
    ratios: dict[str, float]  # true mean overrun ratio per category
    mental_curve: list[float]  # true mental offset per time band
    physical_curve: list[float]
    follow: float  # true chance of starting a planned block when the fit is perfect
    rng: random.Random = field(repr=False, default_factory=random.Random)
    next_id: int = 1

    @classmethod
    def create(cls, seed: int) -> "SyntheticUser":
        r = random.Random(seed)
        ratios = {c: r.uniform(0.9, 1.6) for c in CATEGORIES}
        # A chronotype: morning people peak early, evening people peak late.
        lark = r.random() < 0.5
        shape = [-1.5, 1.2, 0.3, -1.0, 0.0, -0.6, -1.8] if lark else [-2.0, -0.6, 0.0, -0.8, 0.6, 1.2, 0.2]
        mental = [s + r.gauss(0, 0.4) for s in shape]
        physical = [s * 0.6 + r.gauss(0, 0.4) for s in shape]
        return cls(seed, ratios, mental, physical, r.uniform(0.82, 0.95), random.Random(seed * 7919 + 1))

    # ---- the world -----------------------------------------------------------
    def morning_state(self) -> TrueState:
        r = self.rng
        return TrueState(clip(r.gauss(6.2, 1.2)), clip(r.gauss(5.6, 1.1)), clip(r.gauss(6.0, 1.2)), clip(r.gauss(4.5, 1.8)))

    def energy_at(self, base: TrueState, t: datetime) -> tuple[float, float]:
        b = _band(t)
        return clip(base.mental + self.mental_curve[b], 0, 10), clip(base.physical + self.physical_curve[b], 0, 10)

    def true_fit(self, base: TrueState, t: datetime, task: TaskIn) -> float:
        m, p = self.energy_at(base, t)
        dm = max(0.0, task.mental_demand - m)
        dp = max(0.0, task.physical_demand - p)
        return math.exp(-(dm**2) / 10 - (dp**2) / 12)

    def observed_checkin(self, base: TrueState, at: datetime) -> CheckIn:
        """What the user reports: the truth plus reporting noise, rounded to 1-10."""
        r = self.rng
        m, p = self.energy_at(base, at)
        return CheckIn(
            at,
            round(clip(m + r.gauss(0, 0.7))),
            round(clip(p + r.gauss(0, 0.7))),
            round(clip(base.focus + r.gauss(0, 0.7))),
            round(clip(base.stress + r.gauss(0, 0.7))),
        )

    def new_tasks(self, day: date, count_range=(4, 7)) -> list[TaskIn]:
        r = self.rng
        out = []
        for _ in range(r.randint(*count_range)):
            cat = r.choice(CATEGORIES)
            heavy = cat in ("Study", "Work")
            physical = cat in ("Errand", "Health")
            md = r.randint(5, 9) if heavy else r.randint(1, 5)
            pd = r.randint(4, 8) if physical else r.randint(1, 3)
            deadline = None
            if r.random() < 0.55:
                dd = r.choice([0, 1, 1, 2, 3, 4])
                deadline = datetime.combine(day + timedelta(days=dd), time(r.choice([12, 17, 20, 23])))
                if dd == 0 and deadline.hour < 17:
                    deadline = deadline.replace(hour=20)
            out.append(TaskIn(
                id=self.next_id, title=f"{cat} task {self.next_id}", category=cat,
                priority=r.choices([1, 2, 3, 4], weights=[2, 4, 3, 1])[0],
                est_minutes=r.choice([30, 45, 60, 60, 90, 120]),
                mental_difficulty=md, mental_req=md, physical_difficulty=pd, physical_req=pd,
                deadline=deadline,
            ))
            self.next_id += 1
        return out

    def commitments(self, day: date, classes=(1, 3)) -> list[Commitment]:
        r = self.rng
        out = [Commitment(datetime.combine(day, time(13)), datetime.combine(day, time(13, 45)), "Lunch", "unavailable")]
        for h in r.sample([9, 10, 11, 14, 15, 16, 17], k=r.randint(*classes)):
            out.append(Commitment(datetime.combine(day, time(h)), datetime.combine(day, time(h + 1)), "Class", "fixed"))
        return sorted(out, key=lambda c: c.start)

    def actual_minutes(self, task: TaskIn, est_left: float, fit: float) -> float:
        """Real duration: the category's true overrun, task noise, and slower work when the fit is poor."""
        noise = math.exp(self.rng.gauss(0, 0.2))
        return est_left * self.ratios[task.category] * noise * (1 + 0.35 * (1 - fit))

    def starts_block(self, fit: float) -> bool:
        return self.rng.random() < self.follow * (0.6 + 0.4 * fit)
