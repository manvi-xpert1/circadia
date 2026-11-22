"""Small builders shared by the tests."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from ai.types import CheckIn, Commitment, PlanRequest, Preferences, TaskIn

NOW = datetime(2026, 11, 11, 8, 30)


def task(i, **kw) -> TaskIn:
    base = dict(id=i, title=f"Task {i}", category="Study", priority=2, est_minutes=60)
    base.update(kw)
    return TaskIn(**base)


def random_request(seed: int, n: int = 12, horizon: int = 3) -> PlanRequest:
    rnd = random.Random(seed)
    cats = ["Study", "Work", "Errand", "Health", "Admin"]
    tasks = []
    for i in range(1, n + 1):
        tasks.append(
            TaskIn(
                id=i,
                title=f"T{i}",
                category=rnd.choice(cats),
                priority=rnd.randint(1, 4),
                est_minutes=rnd.choice([15, 30, 45, 60, 90, 120]),
                mental_difficulty=rnd.randint(1, 10),
                physical_difficulty=rnd.randint(1, 10),
                mental_req=rnd.randint(1, 10),
                physical_req=rnd.randint(1, 10),
                deadline=NOW + timedelta(hours=rnd.randint(2, 24 * horizon + 24)) if rnd.random() < 0.5 else None,
            )
        )
    # A few dependencies (always on a lower id, so no cycles).
    for t in tasks[3:]:
        if rnd.random() < 0.2:
            t.depends_on = rnd.randint(1, t.id - 1)
    if rnd.random() < 0.5:
        tasks[0].is_fixed = True
        tasks[0].fixed_start = NOW.replace(hour=16, minute=0)
        tasks[0].fixed_end = NOW.replace(hour=17, minute=0)
    commits = []
    for d in range(horizon):
        day = NOW + timedelta(days=d)
        if rnd.random() < 0.8:
            h = rnd.randint(9, 18)
            commits.append(Commitment(day.replace(hour=h, minute=0), day.replace(hour=h + 1, minute=30), "Lecture"))
    checkins = [CheckIn(NOW, rnd.randint(2, 9), rnd.randint(2, 9), rnd.randint(2, 9), rnd.randint(1, 10))]
    return PlanRequest(NOW, tasks, commits, checkins, [], Preferences(horizon_days=horizon), seed=seed)
