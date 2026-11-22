"""Analytics computed only from stored records (design: page 5).

Nothing is estimated or invented: every number comes from outcomes, tasks,
check-ins and ratings in the database, filtered by data source, and every
section reports how many records it used.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.fuzzy.profile import BAND_NAMES, band_index

from ..models import EnergyCheckIn, Feedback, ScheduledBlock, ScheduleVersion, Task, TaskOutcome, User

FIT_ORDER = ["Excellent", "Good", "Fair", "Poor"]


def _src(model, source: str):
    return (model.source == source) if source in ("user", "demo") else True


def _mean(xs):
    return round(statistics.fmean(xs), 2) if xs else None


def compute(db: Session, user: User, source: str = "all") -> dict:
    outcomes = db.scalars(
        select(TaskOutcome).where(TaskOutcome.user_id == user.id, _src(TaskOutcome, source)).order_by(TaskOutcome.recorded_at)
    ).all()
    block_ids = [o.block_id for o in outcomes if o.block_id]
    blocks = {b.id: b for b in db.scalars(select(ScheduledBlock).where(ScheduledBlock.id.in_(block_ids)))} if block_ids else {}

    n = len(outcomes)
    counts = {s: sum(1 for o in outcomes if o.status == s) for s in ("done", "partial", "skipped")}
    done = [o for o in outcomes if o.status == "done" and o.actual_minutes]

    # Planned versus actual, by category (your estimate against what happened).
    by_cat: dict[str, list[TaskOutcome]] = defaultdict(list)
    for o in done:
        by_cat[o.category].append(o)
    categories = [
        {
            "category": c,
            "n": len(os),
            "estimate": _mean([o.est_minutes for o in os]),
            "actual": _mean([o.actual_minutes for o in os]),
            "overrun_pct": round((statistics.fmean(o.actual_minutes / o.est_minutes for o in os) - 1) * 100, 1),
        }
        for c, os in sorted(by_cat.items(), key=lambda kv: -len(kv[1]))
    ]
    status_by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"done": 0, "partial": 0, "skipped": 0})
    for o in outcomes:
        status_by_cat[o.category][o.status] += 1

    # Prediction accuracy: your estimate vs the planner's median prediction, for planned blocks.
    accuracy = []
    for o in done:
        b = blocks.get(o.block_id) if o.block_id else None
        expl = (b.explanation_json or {}) if b else {}
        ratio = (expl.get("duration") or {}).get("ratio")
        if not ratio:
            continue
        predicted = o.est_minutes * ratio
        accuracy.append({
            "at": o.recorded_at.isoformat(),
            "estimate_error_pct": round(abs(o.est_minutes - o.actual_minutes) / o.actual_minutes * 100, 1),
            "planner_error_pct": round(abs(predicted - o.actual_minutes) / o.actual_minutes * 100, 1),
        })
    for i in range(len(accuracy)):
        window = accuracy[max(0, i - 4) : i + 1]
        accuracy[i]["estimate_rolling"] = round(statistics.fmean(x["estimate_error_pct"] for x in window), 1)
        accuracy[i]["planner_rolling"] = round(statistics.fmean(x["planner_error_pct"] for x in window), 1)
        accuracy[i]["i"] = i + 1

    # Completion by energy fit and by hour, for outcomes recorded on planned blocks.
    fit_groups: dict[str, list[str]] = defaultdict(list)
    hour_groups: dict[int, list[str]] = defaultdict(list)
    for o in outcomes:
        b = blocks.get(o.block_id) if o.block_id else None
        if not b:
            continue
        label = (b.explanation_json or {}).get("fit_label")
        if label:
            fit_groups[label].append(o.status)
        hour_groups[b.start.hour].append(o.status)

    def rate(statuses):
        return round(100 * sum(1 for s in statuses if s == "done") / len(statuses), 1) if statuses else None

    by_fit = [{"label": f, "n": len(fit_groups[f]), "done_rate": rate(fit_groups[f])} for f in FIT_ORDER if fit_groups.get(f)]
    by_hour = [{"hour": h, "n": len(v), "done_rate": rate(v)} for h, v in sorted(hour_groups.items())]

    # Deadline performance from tasks.
    tasks = db.scalars(select(Task).where(Task.user_id == user.id, _src(Task, source), Task.deadline.is_not(None))).all()
    now = datetime.now()
    finished = [t for t in tasks if t.status == "done" and t.completed_at]
    deadlines = {
        "on_time": sum(1 for t in finished if t.completed_at <= t.deadline),
        "late": sum(1 for t in finished if t.completed_at > t.deadline),
        "overdue_open": sum(1 for t in tasks if t.status == "pending" and t.deadline < now and not t.recur_days),
        "upcoming": sum(1 for t in tasks if t.status == "pending" and t.deadline >= now and not t.recur_days),
        "missed": sum(1 for t in tasks if t.status == "missed"),
    }

    # Energy by time of day, from check-ins.
    checkins = db.scalars(select(EnergyCheckIn).where(EnergyCheckIn.user_id == user.id, _src(EnergyCheckIn, source))).all()
    bands: dict[int, list[EnergyCheckIn]] = defaultdict(list)
    for c in checkins:
        bands[band_index(c.recorded_at)].append(c)
    energy_by_time = [
        {"band": BAND_NAMES[i], "n": len(bands[i]),
         "mental": _mean([c.mental for c in bands[i]]), "physical": _mean([c.physical for c in bands[i]]),
         "focus": _mean([c.focus for c in bands[i]]), "stress": _mean([c.stress for c in bands[i]])}
        for i in range(len(BAND_NAMES)) if bands.get(i)
    ]

    # Plan history and ratings (ratings exist only for your own plans).
    versions = db.scalars(select(ScheduleVersion).where(ScheduleVersion.user_id == user.id, ScheduleVersion.is_main.is_(True))).all()
    ratings = db.scalars(select(Feedback.usefulness).where(Feedback.version_id.in_([v.id for v in versions]))).all() if versions else []

    return {
        "source": source,
        "outcomes": {"n": n, **counts, "completion_rate": round(100 * counts["done"] / n, 1) if n else None},
        "estimate_error_min": _mean([abs(o.actual_minutes - o.est_minutes) for o in done]),
        "planner_error_min": _mean([abs(o.actual_minutes - o.est_minutes * ((blocks[o.block_id].explanation_json or {}).get("duration") or {}).get("ratio", 1))
                                    for o in done if o.block_id in blocks and ((blocks[o.block_id].explanation_json or {}).get("duration") or {}).get("ratio")]),
        "categories": categories,
        "status_by_category": [{"category": c, **v} for c, v in sorted(status_by_cat.items())],
        "accuracy": accuracy,
        "by_fit": by_fit,
        "by_hour": by_hour,
        "deadlines": deadlines,
        "energy_by_time": energy_by_time,
        "checkins": len(checkins),
        "plans_generated": len(versions),
        "ratings": {"n": len(ratings), "mean": _mean(list(ratings))},
    }
