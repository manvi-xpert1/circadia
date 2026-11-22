"""What-if simulator: plan before and after a scenario with the same seed."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ai.whatif import simulate

from ..db import get_db
from ..models import User
from ..security import current_user
from ..services.planner import active_version, build_request


class UrgentTask(BaseModel):
    title: str = Field(default="Urgent task", min_length=1, max_length=200)
    category: str = Field(default="Work", max_length=40)
    est_minutes: int = Field(default=60, ge=5, le=480)
    priority: int = Field(default=4, ge=1, le=4)
    deadline_hours: float = Field(default=6, gt=0, le=168)
    mental: int = Field(default=6, ge=1, le=10)
    physical: int = Field(default=2, ge=1, le=10)


class LostTime(BaseModel):
    day: int = Field(default=0, ge=0, le=6)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    label: str = Field(default="Lost time", max_length=60)

    @model_validator(mode="after")
    def order(self):
        if self.end <= self.start:
            raise ValueError("Lost time must end after it starts")
        return self


class ExtendTask(BaseModel):
    task_id: int
    extra_minutes: int = Field(default=30, ge=5, le=480)


class ScenarioIn(BaseModel):
    late_start_minutes: Optional[int] = Field(default=None, ge=15, le=600)
    urgent_task: Optional[UrgentTask] = None
    lose_time: Optional[LostTime] = None
    energy_delta: Optional[int] = Field(default=None, ge=-6, le=4)
    extend_task: Optional[ExtendTask] = None
    horizon_days: Optional[int] = Field(default=None, ge=1, le=7)
    stability: float = Field(default=0.5, ge=0, le=1)  # how strongly the replan keeps the current plan

    @model_validator(mode="after")
    def something(self):
        if not any([self.late_start_minutes, self.urgent_task, self.lose_time, self.energy_delta, self.extend_task]):
            raise ValueError("Choose at least one change to simulate")
        return self


router = APIRouter(prefix="/api/simulate", tags=["simulate"])


@router.post("")
def run(body: ScenarioIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    active = active_version(db, user)
    seed = active.seed if active else 42
    now = datetime.now().replace(second=0, microsecond=0)
    req = build_request(db, user, now, body.horizon_days, None, seed)
    if body.extend_task and not any(t.id == body.extend_task.task_id for t in req.tasks):
        raise HTTPException(422, {"code": "INVALID", "message": "That task is not pending, so it can't be extended.", "field": "extend_task"})
    if not req.tasks and not body.urgent_task:
        raise HTTPException(409, {"code": "NO_TASKS", "message": "Add some tasks first. There is nothing to plan."})
    scenario = body.model_dump(exclude_none=True, exclude={"horizon_days"})
    return simulate(req, scenario)
