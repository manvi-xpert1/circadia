"""Request and response models. Pydantic validates every write."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Level = Field(ge=1, le=10)
HHMM = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


# ---- auth -------------------------------------------------------------------
class SetupIn(BaseModel):
    username: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=8, max_length=200)
    display_name: Optional[str] = Field(default=None, max_length=60)

    @field_validator("username")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


# ---- tasks ------------------------------------------------------------------
class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(default="Study", min_length=1, max_length=40)
    priority: int = Field(default=2, ge=1, le=4)
    deadline: Optional[datetime] = None
    est_minutes: int = Field(default=60, ge=5, le=480)
    mental_difficulty: int = Level
    physical_difficulty: int = Level
    mental_energy_req: int = Level
    physical_energy_req: int = Level
    is_fixed: bool = False
    fixed_start: Optional[datetime] = None
    fixed_end: Optional[datetime] = None
    depends_on_id: Optional[int] = None
    notes: str = Field(default="", max_length=2000)
    recur_days: str = Field(default="", pattern=r"^([0-6](,[0-6])*)?$", max_length=40, description="Weekdays it repeats on, Monday = 0")
    recur_until: Optional[date] = None

    @field_validator("recur_days")
    @classmethod
    def tidy_days(cls, v: str) -> str:
        return ",".join(str(d) for d in sorted({int(x) for x in v.split(",") if x != ""})) if v else ""

    @model_validator(mode="after")
    def check_fixed(self):
        if self.recur_days and self.depends_on_id is not None:
            raise ValueError("A repeating task can't wait for another task")
        if self.is_fixed:
            if not (self.fixed_start and self.fixed_end):
                raise ValueError("A fixed task needs a start and an end time")
            if self.fixed_end <= self.fixed_start:
                raise ValueError("End time must be after start time")
        return self


class TaskIn(TaskBase):
    pass


class TaskPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[str] = Field(default=None, min_length=1, max_length=40)
    priority: Optional[int] = Field(default=None, ge=1, le=4)
    deadline: Optional[datetime] = None
    est_minutes: Optional[int] = Field(default=None, ge=5, le=480)
    mental_difficulty: Optional[int] = Field(default=None, ge=1, le=10)
    physical_difficulty: Optional[int] = Field(default=None, ge=1, le=10)
    mental_energy_req: Optional[int] = Field(default=None, ge=1, le=10)
    physical_energy_req: Optional[int] = Field(default=None, ge=1, le=10)
    is_fixed: Optional[bool] = None
    fixed_start: Optional[datetime] = None
    fixed_end: Optional[datetime] = None
    depends_on_id: Optional[int] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[Literal["pending", "done"]] = None
    recur_days: Optional[str] = Field(default=None, pattern=r"^([0-6](,[0-6])*)?$", max_length=40)
    recur_until: Optional[date] = None


class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parent_id: Optional[int] = None
    occurrence_date: Optional[date] = None
    status: str
    minutes_done: int
    completed_at: Optional[datetime]
    source: str
    created_at: datetime
    updated_at: datetime


# ---- commitments ------------------------------------------------------------
class CommitmentIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    start: datetime
    end: datetime
    kind: Literal["fixed", "unavailable"] = "fixed"
    repeat_days: int = Field(default=1, ge=1, le=14, description="Create the same slot on this many consecutive days")

    @model_validator(mode="after")
    def check_order(self):
        if self.end <= self.start:
            raise ValueError("End time must be after start time")
        return self


class CommitmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str
    start: datetime
    end: datetime
    kind: str
    source: str


# ---- check-ins --------------------------------------------------------------
class CheckInIn(BaseModel):
    mental: int = Level
    physical: int = Level
    focus: int = Level
    stress: int = Level
    note: str = Field(default="", max_length=1000)


class CheckInOut(CheckInIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recorded_at: datetime
    source: str


# ---- preferences ------------------------------------------------------------
class PreferencesIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    day_start: str = HHMM
    day_end: str = HHMM
    break_minutes: int = Field(ge=0, le=60)
    max_focus_block: int = Field(ge=30, le=240)
    no_work_after: str = HHMM
    ga_preset: Literal["balanced", "deadline", "gentle"]
    horizon_days: int = Field(ge=1, le=7)
    optimizer: Literal["ga", "hybrid", "cpsat"] = "hybrid"
    replan_stability: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def check_window(self):
        if self.day_end <= self.day_start:
            raise ValueError("Day end must be after day start")
        if (int(self.day_end[:2]) * 60 + int(self.day_end[3:])) - (int(self.day_start[:2]) * 60 + int(self.day_start[3:])) < 120:
            raise ValueError("The working window must be at least 2 hours")
        return self


# ---- schedules --------------------------------------------------------------
class GenerateIn(BaseModel):
    horizon_days: Optional[int] = Field(default=None, ge=1, le=7)
    preset: Optional[Literal["balanced", "deadline", "gentle"]] = None
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    optimizer: Optional[Literal["ga", "hybrid", "cpsat"]] = None
    # How strongly to keep the current plan when replanning (0-1). None uses the saved preference.
    stability: Optional[float] = Field(default=None, ge=0, le=1)


class BlockPatch(BaseModel):
    locked: Optional[bool] = None
    start: Optional[datetime] = None  # move: the block keeps its length and becomes locked
    removed: Optional[bool] = None


class OutcomeIn(BaseModel):
    status: Literal["done", "partial", "skipped"]
    actual_minutes: Optional[int] = Field(default=None, ge=1, le=960)

    @model_validator(mode="after")
    def need_minutes(self):
        if self.status in ("done", "partial") and self.actual_minutes is None:
            raise ValueError("Enter how many minutes it actually took")
        return self


class FeedbackIn(BaseModel):
    usefulness: int = Field(ge=1, le=5)
    rater: str = Field(default="me", min_length=1, max_length=40)
    comment: str = Field(default="", max_length=1000)
