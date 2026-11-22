"""Users, login sessions and preferences."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(60))
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day_start: Mapped[str] = mapped_column(String(5), default="08:00")
    day_end: Mapped[str] = mapped_column(String(5), default="22:00")
    break_minutes: Mapped[int] = mapped_column(Integer, default=10)
    max_focus_block: Mapped[int] = mapped_column(Integer, default=90)
    no_work_after: Mapped[str] = mapped_column(String(5), default="21:00")
    ga_preset: Mapped[str] = mapped_column(String(20), default="balanced")
    horizon_days: Mapped[int] = mapped_column(Integer, default=3)
    optimizer: Mapped[str] = mapped_column(String(10), default="hybrid")  # ga | hybrid | cpsat
    replan_stability: Mapped[float] = mapped_column(Float, default=0.5)  # 0 = free replan, 1 = keep the plan
