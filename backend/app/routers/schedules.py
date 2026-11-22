"""Generate, read and adjust plans; record outcomes and feedback."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Feedback, ScheduledBlock, ScheduleVersion, Task, TaskOutcome, User
from ..schemas import BlockPatch, FeedbackIn, GenerateIn, OutcomeIn
from ..security import current_user
from ..services import planner

router = APIRouter(prefix="/api", tags=["schedules"])


def _version(db: Session, user: User, vid: int) -> ScheduleVersion:
    v = db.get(ScheduleVersion, vid)
    if v is None or v.user_id != user.id:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Plan not found."})
    return v


def _block(db: Session, user: User, bid: int) -> ScheduledBlock:
    b = db.get(ScheduledBlock, bid)
    if b is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Block not found."})
    _version(db, user, b.version_id)
    return b


@router.post("/schedules/generate")
def generate(body: GenerateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run_id = planner.generate(db, user, horizon=body.horizon_days, preset=body.preset, seed=body.seed,
                              optimizer=body.optimizer, stability=body.stability)
    return planner.run_dict(db, user, run_id)


@router.get("/schedules/current")
def current(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return planner.run_dict(db, user)


@router.get("/schedules/history")
def history(limit: int = 20, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ScheduleVersion).where(ScheduleVersion.user_id == user.id, ScheduleVersion.is_main.is_(True))
        .order_by(ScheduleVersion.created_at.desc()).limit(max(1, min(limit, 100)))
    ).all()
    return [
        {"run_id": v.run_id, "created_at": v.created_at.isoformat(), "start_date": v.start_date.isoformat(),
         "horizon_days": v.horizon_days, "preset": v.preset, "fitness": v.fitness, "mode": v.mode, "seed": v.seed}
        for v in rows
    ]


@router.get("/schedules/runs/{run_id}")
def run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = planner.run_dict(db, user, run_id)
    if out is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Plan not found."})
    return out


@router.post("/schedules/{vid}/activate")
def activate(vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = _version(db, user, vid)
    db.execute(update(ScheduleVersion).where(ScheduleVersion.user_id == user.id).values(is_active=False))
    v.is_active = True
    db.commit()
    return planner.run_dict(db, user, v.run_id)


@router.patch("/blocks/{bid}")
def patch_block(bid: int, body: BlockPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = _block(db, user, bid)
    if b.kind == "fixed-task":
        raise HTTPException(409, {"code": "FIXED", "message": "Fixed tasks keep their time (rule H6). Edit the task instead."})
    if body.start is not None:
        start = body.start.replace(second=0, microsecond=0)
        b.end = planner.validate_move(db, user, b, start)
        b.start = start
        b.locked = True
        expl = dict(b.explanation_json or {})
        expl["verdict"] = f"Moved by you to {start:%a %H:%M}; locked so regenerating keeps it here."
        expl["start"], expl["end"] = b.start.isoformat(), b.end.isoformat()
        b.explanation_json = expl
    if body.locked is not None:
        b.locked = body.locked
    if body.removed is not None:
        b.removed = body.removed
    db.commit()
    v = db.get(ScheduleVersion, b.version_id)
    return planner.run_dict(db, user, v.run_id)


@router.post("/blocks/{bid}/outcome")
def record_outcome(bid: int, body: OutcomeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = _block(db, user, bid)
    if db.scalar(select(TaskOutcome).where(TaskOutcome.block_id == b.id)):
        raise HTTPException(409, {"code": "ALREADY_RECORDED", "message": "An outcome is already recorded. Undo it first."})
    t = db.get(Task, b.task_id)
    expl = b.explanation_json or {}
    est = int(expl.get("est_minutes") or max(t.est_minutes - t.minutes_done, 5))
    db.add(TaskOutcome(user_id=user.id, block_id=b.id, task_id=t.id, category=t.category, est_minutes=est,
                       planned_minutes=expl.get("planned_minutes"), status=body.status,
                       actual_minutes=body.actual_minutes if body.status != "skipped" else None))
    if body.status == "done":
        t.status, t.completed_at = "done", datetime.now()
    elif body.status == "partial":
        t.minutes_done = min(t.est_minutes - 5, t.minutes_done + (body.actual_minutes or 0))
    db.commit()
    return planner.run_dict(db, user, db.get(ScheduleVersion, b.version_id).run_id)


@router.delete("/blocks/{bid}/outcome")
def undo_outcome(bid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = _block(db, user, bid)
    o = db.scalar(select(TaskOutcome).where(TaskOutcome.block_id == b.id))
    if o is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "No outcome recorded for this block."})
    t = db.get(Task, b.task_id)
    if t is not None:
        if o.status == "done":
            t.status, t.completed_at = "pending", None
        elif o.status == "partial":
            t.minutes_done = max(0, t.minutes_done - (o.actual_minutes or 0))
    db.delete(o)
    db.commit()
    return planner.run_dict(db, user, db.get(ScheduleVersion, b.version_id).run_id)


@router.post("/schedules/{vid}/feedback", status_code=201)
def feedback(vid: int, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _version(db, user, vid)
    f = Feedback(version_id=vid, **body.model_dump())
    db.add(f)
    db.commit()
    return {"id": f.id}
