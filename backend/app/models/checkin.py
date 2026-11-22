"""Energy check-ins."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class EnergyCheckIn(Base):
    __tablename__ = "energy_checkins"
    __table_args__ = tuple(
        CheckConstraint(f"{c} BETWEEN 1 AND 10", name=f"ck_{c}") for c in ("mental", "physical", "focus", "stress")
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    mental: Mapped[int] = mapped_column(Integer)
    physical: Mapped[int] = mapped_column(Integer)
    focus: Mapped[int] = mapped_column(Integer)
    stress: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(10), default="user")
