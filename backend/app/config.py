"""Paths and settings. Everything stays inside the project folder."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.environ.get("EAP_DB_PATH", DATA_DIR / "planner.db"))
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

SESSION_COOKIE = "eap_session"
SESSION_DAYS = 7
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 60
MIN_PASSWORD_LENGTH = 8
