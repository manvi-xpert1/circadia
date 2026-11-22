"""Demo data for a student's week. Every record is tagged source = "demo".

The data is made up for demonstration. It is clearly labelled in the app and
can be deleted in one click without touching your own records.
"""
from __future__ import annotations

import random
from datetime import datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Commitment, EnergyCheckIn, Task, TaskOutcome, User

DEMO = "demo"

# title, category, priority, est, mental diff, physical diff, mental req, physical req, deadline (days, hour) or None
DEMO_TASKS = [
    ("Finish AI assignment: fuzzy logic section", "Study", 4, 120, 8, 2, 8, 2, (1, 17)),
    ("Revise DBMS unit 3 notes", "Study", 3, 90, 7, 2, 7, 2, (2, 9)),
    ("Lab record: write experiments 4-6", "Study", 3, 60, 5, 2, 5, 3, (1, 10)),
    ("Read paper on genetic algorithms", "Study", 2, 45, 6, 1, 6, 2, None),
    ("Prepare slides for project review", "Study", 3, 90, 6, 2, 6, 2, (2, 14)),
    ("Grocery run", "Errand", 2, 45, 2, 5, 2, 5, None),
    ("Laundry", "Errand", 1, 30, 1, 4, 1, 4, None),
    ("Gym workout", "Health", 2, 60, 2, 8, 2, 8, None),
    ("Reply to internship emails", "Admin", 3, 30, 4, 1, 4, 1, (1, 12)),
    ("Pay hostel fees online", "Admin", 4, 15, 2, 1, 2, 1, (0, 20)),
    ("Call home", "Personal", 2, 30, 2, 1, 2, 1, None),
    ("Practice DSA problems", "Study", 2, 60, 8, 1, 8, 1, None),
]

# Overrun ratios used to fake past outcomes, by category (demo only).
DEMO_RATIOS = {"Study": 1.3, "Errand": 1.0, "Admin": 0.9, "Health": 1.05, "Personal": 1.1}


def load_demo(db: Session, user: User, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    rnd = random.Random(2026)
    today = now.date()
    clear_source(db, user, DEMO)
    tasks = []
    for title, cat, pri, est, md, pd, mr, pr, dl in DEMO_TASKS:
        deadline = datetime.combine(today + timedelta(days=dl[0]), time(dl[1])) if dl else None
        if deadline and deadline <= now:
            deadline = now + timedelta(hours=3)
        t = Task(
            user_id=user.id, title=title, category=cat, priority=pri, est_minutes=est,
            mental_difficulty=md, physical_difficulty=pd, mental_energy_req=mr, physical_energy_req=pr,
            deadline=deadline, source=DEMO,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    # "Prepare slides" depends on the assignment being done.
    tasks[4].depends_on_id = tasks[0].id
    # Two repeating tasks: DSA practice every day, gym on Monday, Wednesday and Friday.
    tasks[11].recur_days = "0,1,2,3,4,5,6"
    tasks[7].recur_days = "0,2,4"
    # One fixed task: a club meeting tomorrow evening.
    db.add(Task(
        user_id=user.id, title="Coding club meeting", category="Personal", priority=2, est_minutes=60,
        mental_difficulty=4, physical_difficulty=1, mental_energy_req=4, physical_energy_req=1,
        is_fixed=True, fixed_start=datetime.combine(today + timedelta(days=1), time(18)),
        fixed_end=datetime.combine(today + timedelta(days=1), time(19)), source=DEMO,
    ))
    # Lectures on the next three days and a lunch break each day.
    lectures = [(0, 11, 12, "AI lecture"), (0, 14, 15, "DBMS lab"), (1, 10, 11, "DBMS lecture"),
                (1, 15, 16, "AI lecture"), (2, 9, 10, "Maths tutorial"), (2, 11, 13, "Project lab")]
    for d, h1, h2, label in lectures:
        day = today + timedelta(days=d)
        db.add(Commitment(user_id=user.id, label=label, kind="fixed", source=DEMO,
                          start=datetime.combine(day, time(h1)), end=datetime.combine(day, time(h2))))
    for d in range(3):
        day = today + timedelta(days=d)
        db.add(Commitment(user_id=user.id, label="Lunch", kind="unavailable", source=DEMO,
                          start=datetime.combine(day, time(13)), end=datetime.combine(day, time(13, 45))))
    # Ten days of past check-ins: sharper mornings, a post-lunch dip.
    for d in range(10, 0, -1):
        day = today - timedelta(days=d)
        m = rnd.randint(5, 8)
        db.add(EnergyCheckIn(user_id=user.id, recorded_at=datetime.combine(day, time(8, rnd.randint(0, 50))),
                             mental=m, physical=rnd.randint(4, 7), focus=min(10, m + rnd.randint(-1, 1)),
                             stress=rnd.randint(2, 6), source=DEMO))
        if d % 3 == 0:
            db.add(EnergyCheckIn(user_id=user.id, recorded_at=datetime.combine(day, time(14, 30)),
                                 mental=max(1, m - 2), physical=rnd.randint(4, 6), focus=max(1, m - 2),
                                 stress=rnd.randint(3, 6), source=DEMO))
    # Past outcomes so the learning models have something to learn from.
    for k in range(18):
        cat = rnd.choice(list(DEMO_RATIOS))
        est = rnd.choice([30, 45, 60, 90])
        status = rnd.choices(["done", "partial", "skipped"], weights=[7, 1, 2])[0]
        actual = round(est * DEMO_RATIOS[cat] * rnd.uniform(0.85, 1.2)) if status != "skipped" else None
        db.add(TaskOutcome(user_id=user.id, category=cat, est_minutes=est, status=status, actual_minutes=actual,
                           recorded_at=now - timedelta(days=10 - k // 2, hours=rnd.randint(1, 8)), source=DEMO))
    db.commit()
    from .recurrence import ensure_copies

    ensure_copies(db, user, today, 7, now)
    return counts(db, user)


def clear_source(db: Session, user: User, source: str) -> None:
    for model in (TaskOutcome, EnergyCheckIn, Commitment, Task):
        db.execute(delete(model).where(model.user_id == user.id, model.source == source))
    db.commit()


def counts(db: Session, user: User) -> dict:
    out = {}
    for name, model in (("tasks", Task), ("commitments", Commitment), ("checkins", EnergyCheckIn), ("outcomes", TaskOutcome)):
        rows = db.scalars(select(model.source).where(model.user_id == user.id)).all()
        out[name] = {s: rows.count(s) for s in sorted(set(rows))}
    return out
