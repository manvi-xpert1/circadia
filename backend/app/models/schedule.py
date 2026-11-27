"""Schedule versions, their blocks, unscheduled items, outcomes and feedback."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ScheduleVersion(Base):
    __tablename__ = "schedule_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)  # plans generated together share a run
    start_date: Mapped[date] = mapped_column(Date)
    horizon_days: Mapped[int] = mapped_column(Integer)
    scheduler: Mapped[str] = mapped_column(String(20), default="ga")
    preset: Mapped[str] = mapped_column(String(20))
    seed: Mapped[int] = mapped_column(Integer)
    fitness: Mapped[float] = mapped_column(Float)
    components_json: Mapped[dict] = mapped_column(JSON)
    plan_json: Mapped[dict] = mapped_column(JSON)  # day loads, convergence, weights
    meta_json: Mapped[dict] = mapped_column(JSON)  # shared meta, days, commitments, fixed items
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(15), default="cold")
    checkin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("energy_checkins.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    source: Mapped[str] = mapped_column(String(10), default="user")


class ScheduledBlock(Base):
    __tablename__ = "scheduled_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String(12), default="ai")  # ai | fixed-task | locked
    suitability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_complete: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_deadline: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    explanation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    removed: Mapped[bool] = mapped_column(Boolean, default=False)


class UnscheduledItem(Base):
    __tablename__ = "unscheduled_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    reason_code: Mapped[str] = mapped_column(String(30))
    reason_text: Mapped[str] = mapped_column(Text)


class TaskOutcome(Base):
    __tablename__ = "task_outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    block_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scheduled_blocks.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(40))  # copied so learning survives task deletion
    est_minutes: Mapped[int] = mapped_column(Integer)
    planned_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(10))  # done | partial | skipped
    actual_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    source: Mapped[str] = mapped_column(String(10), default="user")
    # What the planner knew when it placed the block (the completion model's inputs).
    # Empty when the block was moved after planning, since the saved context no longer applies.
    context_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id", ondelete="CASCADE"))
    usefulness: Mapped[int] = mapped_column(Integer)
    rater: Mapped[str] = mapped_column(String(40), default="me")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
