"""Energy check-ins."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import EnergyCheckIn, User
from ..schemas import CheckInIn, CheckInOut
from ..security import current_user

router = APIRouter(prefix="/api/checkins", tags=["checkins"])


@router.get("", response_model=list[CheckInOut])
def list_checkins(limit: int = 60, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = (select(EnergyCheckIn).where(EnergyCheckIn.user_id == user.id)
         .order_by(EnergyCheckIn.recorded_at.desc()).limit(max(1, min(limit, 500))))
    return list(db.scalars(q))


@router.get("/latest", response_model=CheckInOut | None)
def latest(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalar(select(EnergyCheckIn).where(EnergyCheckIn.user_id == user.id).order_by(EnergyCheckIn.recorded_at.desc()))


@router.post("", response_model=CheckInOut, status_code=201)
def create(body: CheckInIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = EnergyCheckIn(user_id=user.id, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.delete("/{cid}", status_code=204)
def delete(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(EnergyCheckIn, cid)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Check-in not found."})
    db.delete(c)
    db.commit()
