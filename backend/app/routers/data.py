"""Demo data, clearing by source, and full export."""
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Commitment, EnergyCheckIn, Feedback, ScheduleVersion, Task, TaskOutcome, User
from ..security import current_user
from ..services.demo import clear_source, counts, load_demo

router = APIRouter(prefix="/api/data", tags=["data"])


def _rows(db, model, user_id):
    out = []
    for r in db.scalars(select(model).where(model.user_id == user_id)):
        out.append({c.name: (getattr(r, c.name).isoformat() if hasattr(getattr(r, c.name), "isoformat") else getattr(r, c.name))
                    for c in model.__table__.columns})
    return out


@router.get("/counts")
def get_counts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return counts(db, user)


@router.post("/demo")
def demo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return load_demo(db, user)


@router.delete("")
def clear(source: Literal["demo", "user", "synthetic"], user: User = Depends(current_user), db: Session = Depends(get_db)):
    clear_source(db, user, source)
    return counts(db, user)


@router.get("/export")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    versions = _rows(db, ScheduleVersion, user.id)
    vids = [v["id"] for v in versions]
    fb = [
        {"version_id": f.version_id, "usefulness": f.usefulness, "rater": f.rater, "comment": f.comment, "created_at": f.created_at.isoformat()}
        for f in db.scalars(select(Feedback).where(Feedback.version_id.in_(vids)))
    ]
    return {
        "user": {"username": user.username, "display_name": user.display_name},
        "tasks": _rows(db, Task, user.id),
        "commitments": _rows(db, Commitment, user.id),
        "checkins": _rows(db, EnergyCheckIn, user.id),
        "outcomes": _rows(db, TaskOutcome, user.id),
        "schedule_versions": [{k: v for k, v in x.items() if k not in ("meta_json",)} for x in versions],
        "feedback": fb,
    }
