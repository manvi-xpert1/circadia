"""Insights: analytics from stored records only."""
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import current_user
from ..services import insights

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("")
def get_insights(source: Literal["all", "user", "demo"] = "all", user: User = Depends(current_user), db: Session = Depends(get_db)):
    return insights.compute(db, user, source)
