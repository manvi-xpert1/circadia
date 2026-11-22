"""Tasks and commitments (fixed or unavailable time)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

ONE_TO_TEN = "BETWEEN 1 AND 10"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(f"mental_difficulty {ONE_TO_TEN}", name="ck_md"),
        CheckConstraint(f"physical_difficulty {ONE_TO_TEN}", name="ck_pd"),
        CheckConstraint(f"mental_energy_req {ONE_TO_TEN}", name="ck_mr"),
        CheckConstraint(f"physical_energy_req {ONE_TO_TEN}", name="ck_pr"),
        CheckConstraint("est_minutes BETWEEN 5 AND 480", name="ck_est"),
        CheckConstraint("priority BETWEEN 1 AND 4", name="ck_pri"),
        Index("ux_task_occurrence", "parent_id", "occurrence_date", unique=True),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="Study")
    priority: Mapped[int] = mapped_column(Integer, default=2)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    est_minutes: Mapped[int] = mapped_column(Integer, default=60)
    mental_difficulty: Mapped[int] = mapped_column(Integer, default=5)
    physical_difficulty: Mapped[int] = mapped_column(Integer, default=3)
    mental_energy_req: Mapped[int] = mapped_column(Integer, default=5)
    physical_energy_req: Mapped[int] = mapped_column(Integer, default=3)
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False)
    fixed_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fixed_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    depends_on_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    minutes_done: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | done | missed
    # Repeating tasks: a template has recur_days set (weekday numbers, Monday = 0, e.g. "0,2,4").
    # Each day's copy is a normal task with parent_id pointing at the template.
    recur_days: Mapped[str] = mapped_column(String(20), default="")
    recur_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    occurrence_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(10), default="user")  # user | demo | synthetic
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Commitment(Base):
    __tablename__ = "commitments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String(12), default="fixed")  # fixed | unavailable
    label: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(10), default="user")
