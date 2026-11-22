"""Working hours, horizon, presets and break rules."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import PreferencesIO
from ..security import current_user
from ..services.planner import get_prefs

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesIO)
def read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_prefs(db, user)


@router.put("", response_model=PreferencesIO)
def write(body: PreferencesIO, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_prefs(db, user)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return p
