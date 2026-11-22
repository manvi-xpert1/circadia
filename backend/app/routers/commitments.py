"""Fixed commitments (lectures, meetings) and unavailable time."""
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Commitment, User
from ..schemas import CommitmentIn, CommitmentOut
from ..security import current_user

router = APIRouter(prefix="/api/commitments", tags=["commitments"])


@router.get("", response_model=list[CommitmentOut])
def list_commitments(start: Optional[date] = None, days: int = 7, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lo = datetime.combine(start or date.today(), time(0))
    hi = lo + timedelta(days=max(1, min(days, 60)))
    q = select(Commitment).where(Commitment.user_id == user.id, Commitment.end > lo, Commitment.start < hi).order_by(Commitment.start)
    return list(db.scalars(q))


@router.post("", response_model=list[CommitmentOut], status_code=201)
def create_commitment(body: CommitmentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    made = []
    for d in range(body.repeat_days):
        c = Commitment(user_id=user.id, label=body.label, kind=body.kind,
                       start=body.start + timedelta(days=d), end=body.end + timedelta(days=d))
        db.add(c)
        made.append(c)
    db.commit()
    return made


@router.delete("/{cid}", status_code=204)
def delete_commitment(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Commitment, cid)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Commitment not found."})
    db.delete(c)
    db.commit()
