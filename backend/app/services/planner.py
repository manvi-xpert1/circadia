"""Orchestration: database rows -> ai.pipeline.plan -> stored schedule versions."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ai import types as T
from ai.pipeline import plan
from ai.rules.hard_rules import FactBase, PlacedBlock, check_hard

from ..models import (
    Commitment,
    EnergyCheckIn,
    ScheduledBlock,
    ScheduleVersion,
    Task,
    TaskOutcome,
    UnscheduledItem,
    User,
    UserPreferences,
)


def hhmm(s: str) -> time:
    return time(int(s[:2]), int(s[3:]))


def get_prefs(db: Session, user: User) -> UserPreferences:
    prefs = db.get(UserPreferences, user.id)
    if prefs is None:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)
        db.commit()
    return prefs


def to_ai_prefs(p: UserPreferences, horizon: int | None = None, preset: str | None = None) -> T.Preferences:
    return T.Preferences(
        day_start=hhmm(p.day_start),
        day_end=hhmm(p.day_end),
        break_minutes=p.break_minutes,
        max_focus_block=p.max_focus_block,
        no_work_after=hhmm(p.no_work_after),
        preset=preset or p.ga_preset,
        horizon_days=horizon or p.horizon_days,
    )


def to_ai_task(t: Task) -> T.TaskIn:
    return T.TaskIn(
        id=t.id,
        title=t.title,
        category=t.category,
        priority=t.priority,
        est_minutes=t.est_minutes,
        mental_difficulty=t.mental_difficulty,
        physical_difficulty=t.physical_difficulty,
        mental_req=t.mental_energy_req,
        physical_req=t.physical_energy_req,
        deadline=t.deadline,
        depends_on=t.depends_on_id,
        is_fixed=t.is_fixed,
        fixed_start=t.fixed_start,
        fixed_end=t.fixed_end,
        minutes_done=t.minutes_done,
        not_before=datetime.combine(t.occurrence_date, time(0)) if t.occurrence_date else None,
    )


def load_outcomes(db: Session, user: User) -> list[T.Outcome]:
    rows = db.scalars(select(TaskOutcome).where(TaskOutcome.user_id == user.id).order_by(TaskOutcome.recorded_at))
    return [T.Outcome(o.category, o.status, o.est_minutes, o.actual_minutes) for o in rows]


def load_checkins(db: Session, user: User, limit: int = 120) -> list[T.CheckIn]:
    rows = db.scalars(
        select(EnergyCheckIn).where(EnergyCheckIn.user_id == user.id).order_by(EnergyCheckIn.recorded_at.desc()).limit(limit)
    ).all()
    return [T.CheckIn(c.recorded_at, c.mental, c.physical, c.focus, c.stress) for c in reversed(rows)]


def active_version(db: Session, user: User) -> ScheduleVersion | None:
    return db.scalar(
        select(ScheduleVersion)
        .where(ScheduleVersion.user_id == user.id, ScheduleVersion.is_active.is_(True))
        .order_by(ScheduleVersion.created_at.desc())
    )


def build_request(db: Session, user: User, now: datetime, horizon: int | None, preset: str | None, seed: int,
                  optimizer: str | None = None, stability: float | None = None) -> T.PlanRequest:
    prefs = to_ai_prefs(get_prefs(db, user), horizon, preset)
    day0 = datetime.combine(now.date(), time(0))
    end = day0 + timedelta(days=prefs.horizon_days)
    from .recurrence import ensure_copies

    ensure_copies(db, user, now.date(), prefs.horizon_days, now)
    # Repeating-task templates are never planned themselves; their daily copies are.
    tasks = db.scalars(select(Task).where(Task.user_id == user.id, Task.status == "pending", Task.recur_days == "")).all()
    pending_ids = {t.id for t in tasks}
    commits = db.scalars(
        select(Commitment).where(Commitment.user_id == user.id, Commitment.end > day0, Commitment.start < end)
    ).all()
    locked: list[tuple[int, datetime]] = []
    previous: list[tuple[int, datetime]] = []
    current = active_version(db, user)
    if current:
        for b in db.scalars(select(ScheduledBlock).where(ScheduledBlock.version_id == current.id)):
            if b.removed or b.kind == "fixed-task" or b.start < now or b.task_id not in pending_ids:
                continue
            if b.locked:
                locked.append((b.task_id, b.start))
            elif b.kind == "ai":
                previous.append((b.task_id, b.start))  # the plan being replaced, for stability-aware replanning
    stored = get_prefs(db, user)
    return T.PlanRequest(
        now=now,
        tasks=[to_ai_task(t) for t in tasks],
        commitments=[T.Commitment(c.start, c.end, c.label, c.kind) for c in commits],
        checkins=load_checkins(db, user),
        outcomes=load_outcomes(db, user),
        prefs=prefs,
        seed=seed,
        locked=locked,
        previous=previous,
        stability=float(stored.replan_stability if stability is None else stability),
        optimizer=optimizer or stored.optimizer or "hybrid",
    )


def generate(db: Session, user: User, now: datetime | None = None, horizon: int | None = None,
             preset: str | None = None, seed: int | None = None, optimizer: str | None = None,
             stability: float | None = None) -> str:
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    req = build_request(db, user, now, horizon, preset, seed, optimizer, stability)
    result = plan(req)
    run_id = uuid.uuid4().hex
    db.execute(update(ScheduleVersion).where(ScheduleVersion.user_id == user.id).values(is_active=False))
    latest_checkin = db.scalar(
        select(EnergyCheckIn.id).where(EnergyCheckIn.user_id == user.id).order_by(EnergyCheckIn.recorded_at.desc())
    )
    shared = {k: result[k] for k in ("meta", "days", "fixed", "commitments")}
    for i, pl in enumerate(result["plans"]):
        v = ScheduleVersion(
            user_id=user.id,
            run_id=run_id,
            start_date=now.date(),
            horizon_days=result["meta"]["horizon_days"],
            preset=pl["preset"],
            scheduler=pl.get("optimizer", "ga"),
            seed=seed,
            fitness=pl["fitness"],
            components_json=pl["components"],
            plan_json={k: pl.get(k) for k in ("label", "weights", "day_load", "convergence", "generations", "evaluations",
                                              "seconds", "optimizer", "optimizer_label", "optimizer_details",
                                              "stability", "robustness", "tradeoffs")},
            meta_json=shared,
            is_active=(i == 0),
            is_main=(i == 0),
            mode=result["meta"]["mode"],
            checkin_id=latest_checkin,
        )
        db.add(v)
        db.flush()
        for b in pl["blocks"]:
            db.add(
                ScheduledBlock(
                    version_id=v.id,
                    task_id=b["task_id"],
                    start=datetime.fromisoformat(b["start"]),
                    end=datetime.fromisoformat(b["end"]),
                    kind="ai",
                    suitability=b["fit"],
                    p_complete=b["p_complete"],
                    p_deadline=b["p_on_time"],
                    explanation_json=b,
                )
            )
        for f in result["fixed"]:
            db.add(
                ScheduledBlock(
                    version_id=v.id,
                    task_id=f["task_id"],
                    start=datetime.fromisoformat(f["start"]),
                    end=datetime.fromisoformat(f["end"]),
                    kind=f["kind"],
                    locked=f["kind"] == "locked",
                    explanation_json=f,
                )
            )
        for u in pl["unscheduled"]:
            db.add(UnscheduledItem(version_id=v.id, task_id=u["task_id"], reason_code=u["code"], reason_text=u["reason"]))
    db.commit()
    return run_id


def block_dict(b: ScheduledBlock, outcome: TaskOutcome | None) -> dict:
    d = dict(b.explanation_json or {})
    d.update(
        {
            "block_id": b.id,
            "task_id": b.task_id,
            "kind": b.kind,
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "locked": b.locked,
            "outcome": {"status": outcome.status, "actual_minutes": outcome.actual_minutes} if outcome else None,
        }
    )
    return d


def version_dict(db: Session, v: ScheduleVersion) -> dict:
    blocks = db.scalars(
        select(ScheduledBlock).where(ScheduledBlock.version_id == v.id, ScheduledBlock.removed.is_(False)).order_by(ScheduledBlock.start)
    ).all()
    outcomes = {
        o.block_id: o
        for o in db.scalars(select(TaskOutcome).where(TaskOutcome.block_id.in_([b.id for b in blocks]))).all()
    }
    titles = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_([b.task_id for b in blocks])))}
    out_blocks = []
    for b in blocks:
        d = block_dict(b, outcomes.get(b.id))
        t = titles.get(b.task_id)
        if t:
            d["title"] = t.title
            d["category"] = t.category
            d["task_status"] = t.status
        out_blocks.append(d)
    unsched = db.scalars(select(UnscheduledItem).where(UnscheduledItem.version_id == v.id)).all()
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_([u.task_id for u in unsched])))}
    return {
        "version_id": v.id,
        "preset": v.preset,
        "label": v.plan_json.get("label", v.preset),
        "is_active": v.is_active,
        "is_main": v.is_main,
        "fitness": v.fitness,
        "components": v.components_json,
        "weights": v.plan_json.get("weights"),
        "day_load": v.plan_json.get("day_load"),
        "convergence": v.plan_json.get("convergence"),
        "generations": v.plan_json.get("generations"),
        "seconds": v.plan_json.get("seconds"),
        "optimizer": v.plan_json.get("optimizer") or v.scheduler,
        "optimizer_label": v.plan_json.get("optimizer_label"),
        "optimizer_details": v.plan_json.get("optimizer_details"),
        "stability": v.plan_json.get("stability"),
        "robustness": v.plan_json.get("robustness"),
        "tradeoffs": v.plan_json.get("tradeoffs"),
        "blocks": out_blocks,
        "unscheduled": [
            {
                "task_id": u.task_id,
                "title": tasks[u.task_id].title if u.task_id in tasks else "",
                "category": tasks[u.task_id].category if u.task_id in tasks else "",
                "priority": tasks[u.task_id].priority if u.task_id in tasks else 2,
                "deadline": tasks[u.task_id].deadline.isoformat() if u.task_id in tasks and tasks[u.task_id].deadline else None,
                "code": u.reason_code,
                "reason": u.reason_text,
            }
            for u in unsched
            if u.task_id in tasks and tasks[u.task_id].status == "pending"
        ],
    }


def run_dict(db: Session, user: User, run_id: str | None = None) -> dict | None:
    if run_id is None:
        v = active_version(db, user)
        if v is None:
            return None
        run_id = v.run_id
    versions = db.scalars(
        select(ScheduleVersion).where(ScheduleVersion.user_id == user.id, ScheduleVersion.run_id == run_id).order_by(ScheduleVersion.id)
    ).all()
    if not versions:
        return None
    meta = versions[0].meta_json
    return {
        "run_id": run_id,
        "created_at": versions[0].created_at.isoformat(),
        "seed": versions[0].seed,
        **meta,
        "active_version_id": next((v.id for v in versions if v.is_active), versions[0].id),
        "plans": [version_dict(db, v) for v in versions],
    }


def validate_move(db: Session, user: User, block: ScheduledBlock, new_start: datetime) -> datetime:
    """Re-check every hard rule for a block the user moved by hand."""
    length = block.end - block.start
    new_end = new_start + length
    version = db.get(ScheduleVersion, block.version_id)
    prefs = to_ai_prefs(get_prefs(db, user), version.horizon_days)
    blocks = db.scalars(
        select(ScheduledBlock).where(ScheduledBlock.version_id == block.version_id, ScheduledBlock.removed.is_(False))
    ).all()
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.user_id == user.id, Task.status == "pending", Task.recur_days == ""))}
    day0 = datetime.combine(new_start.date(), time(0))
    commits = db.scalars(
        select(Commitment).where(Commitment.user_id == user.id, Commitment.end > day0, Commitment.start < day0 + timedelta(days=1))
    ).all()
    placed = []
    for b in blocks:
        t = tasks.get(b.task_id)
        if t is None:
            continue
        s, e = (new_start, new_end) if b.id == block.id else (b.start, b.end)
        planned = (b.explanation_json or {}).get("planned_minutes", 0) if b.kind == "ai" else 0
        placed.append(PlacedBlock(to_ai_task(t), s, e, planned, "ai" if b.kind != "fixed-task" else "fixed-task"))
    facts = FactBase(
        datetime.now(), prefs, [T.Commitment(c.start, c.end, c.label, c.kind) for c in commits],
        {i: to_ai_task(t) for i, t in tasks.items()}, placed,
    )
    problems = [v for v in check_hard(facts) if v.task_id == block.task_id or v.rule == "H4"]
    if problems:
        msg = "; ".join(f"{v.rule}: {v.message}" for v in problems)
        raise HTTPException(409, {"code": "RULE_VIOLATION", "message": f"Can't move it there. {msg}"})
    return new_end
