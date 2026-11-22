"""Repeating tasks.

A repeating task is a template (recur_days set, e.g. "0,1,2,3,4,5,6" for every day).
The template is never planned itself. For each matching day inside the planning
horizon, a normal task is created for that day (parent_id = template, occurrence_date =
that day). Copies are what get planned, completed and learned from.

Timing of each copy:
  - a template deadline applies to each copy at the same clock time;
    without one, each copy is due by the end of its own day;
  - a fixed template (e.g. gym 07:00-08:00) gives each copy the same fixed clock times.
Copies from earlier days that were never done are marked "missed", so they don't pile up.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Task, TaskOutcome, User, UserPreferences

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
COPY_FIELDS = ("title", "category", "priority", "est_minutes", "mental_difficulty", "physical_difficulty",
               "mental_energy_req", "physical_energy_req", "is_fixed", "notes", "source")


def parse_days(s: str) -> set[int]:
    return {int(x) for x in s.split(",") if x.strip() != ""} if s else set()


def describe(s: str) -> str:
    days = sorted(parse_days(s))
    if len(days) == 7:
        return "every day"
    if days == [0, 1, 2, 3, 4]:
        return "weekdays"
    if days == [5, 6]:
        return "weekends"
    return ", ".join(DAY_NAMES[d] for d in days)


def _hhmm(s: str) -> time:
    return time(int(s[:2]), int(s[3:]))


def make_copy(t: Task, day: date, day_end: time) -> Task:
    c = Task(user_id=t.user_id, parent_id=t.id, occurrence_date=day, recur_days="",
             **{f: getattr(t, f) for f in COPY_FIELDS})
    c.deadline = datetime.combine(day, t.deadline.time()) if t.deadline else datetime.combine(day, day_end)
    if t.is_fixed and t.fixed_start and t.fixed_end:
        length = t.fixed_end - t.fixed_start
        c.fixed_start = datetime.combine(day, t.fixed_start.time())
        c.fixed_end = c.fixed_start + length
    return c


def ensure_copies(db: Session, user: User, start: date, days: int, now: datetime | None = None) -> int:
    """Create missing copies for [start, start + days) and mark old unfinished copies missed."""
    now = now or datetime.now()
    prefs = db.get(UserPreferences, user.id)
    day_end = _hhmm(prefs.day_end) if prefs else time(22, 0)
    made = 0
    templates = db.scalars(select(Task).where(Task.user_id == user.id, Task.recur_days != "", Task.parent_id.is_(None))).all()
    for t in templates:
        wanted = parse_days(t.recur_days)
        first = max(start, t.created_at.date())
        have = set(db.scalars(select(Task.occurrence_date).where(Task.parent_id == t.id)).all())
        for k in range(days):
            d = start + timedelta(days=k)
            if d < first or (t.recur_until and d > t.recur_until):
                continue
            if d.weekday() in wanted and d not in have:
                db.add(make_copy(t, d, day_end))
                made += 1
    for old in db.scalars(select(Task).where(Task.user_id == user.id, Task.parent_id.is_not(None),
                                             Task.status == "pending", Task.occurrence_date < now.date())):
        old.status = "missed"
    db.commit()
    return made


def refresh_future_copies(db: Session, template: Task, today: date) -> None:
    """After a template changes, drop its untouched copies from today on; they are rebuilt next time."""
    for c in db.scalars(select(Task).where(Task.parent_id == template.id, Task.status == "pending",
                                           Task.occurrence_date >= today)):
        touched = c.minutes_done > 0 or db.scalar(select(TaskOutcome.id).where(TaskOutcome.task_id == c.id))
        if not touched:
            db.delete(c)
    db.commit()
