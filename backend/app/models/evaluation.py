"""Saved evaluation runs (synthetic experiments). Results are stored exactly as computed."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | done | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    dataset: Mapped[str] = mapped_column(String(20), default="synthetic")
    config_json: Mapped[dict] = mapped_column(JSON)
    results_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
