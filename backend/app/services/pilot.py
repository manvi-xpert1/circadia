"""Anonymised outcome export for a small real-user pilot, and a calibration check.

What leaves the app: for each recorded outcome on a planned block, the task category,
estimate, planned and actual minutes, status, the planner's predicted chance that the
block would happen, and the context it predicted from. Times are reduced to weekday
and hour; titles, notes, user names and e-mail addresses are never included. Each
export carries a random pilot id, not the user id, so files from different people
can be pooled without identifying them.

Calibration compares predicted chances with what happened, in bands of predicted
probability. It uses only predictions the completion model made (blocks planned
before it existed carry a different score and are left out), and only real outcomes:
"done" and "partial" count as happened, "skipped" as not.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ScheduledBlock, TaskOutcome, User

BANDS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.0001)]
CONTEXT_FIELDS = ("mental_demand", "physical_demand", "expected_mental", "expected_physical", "focus", "stress")


def _rows(db: Session, user: User) -> list[dict]:
    q = (select(TaskOutcome, ScheduledBlock)
         .join(ScheduledBlock, TaskOutcome.block_id == ScheduledBlock.id, isouter=True)
         .where(TaskOutcome.user_id == user.id)
         .order_by(TaskOutcome.recorded_at))
    out = []
    for o, b in db.execute(q):
        expl = (b.explanation_json or {}) if b is not None else {}
        happens = expl.get("happens") or {}
        ctx = o.context_json or {}
        start = b.start if b is not None else None
        out.append({
            "category": o.category,
            "status": o.status,
            "est_minutes": o.est_minutes,
            "planned_minutes": o.planned_minutes,
            "actual_minutes": o.actual_minutes,
            "weekday": start.weekday() if start else None,
            "hour": start.hour if start else None,
            "predicted_p": happens.get("p"),
            "predicted_low": happens.get("low"),
            "predicted_high": happens.get("high"),
            "learned_from": happens.get("based_on"),
            "context": {k: ctx.get(k) for k in CONTEXT_FIELDS} if ctx else None,
            "source": o.source,
        })
    return out


def calibration(rows: list[dict]) -> dict:
    scored = [(r["predicted_p"], 1 if r["status"] in ("done", "partial") else 0)
              for r in rows if r["predicted_p"] is not None and r["status"] in ("done", "partial", "skipped")]
    bands = []
    for lo, hi in BANDS:
        sel = [(p, y) for p, y in scored if lo <= p < hi]
        bands.append({
            "band": f"{round(lo * 100)}-{min(100, round(hi * 100))}%",
            "n": len(sel),
            "predicted": round(sum(p for p, _ in sel) / len(sel), 3) if sel else None,
            "observed": round(sum(y for _, y in sel) / len(sel), 3) if sel else None,
        })
    n = len(scored)
    brier = round(sum((p - y) ** 2 for p, y in scored) / n, 4) if n else None
    return {
        "n": n,
        "brier": brier,
        "bands": bands,
        "enough_data": n >= 30,
        "note": "With fewer than about 30 outcomes the bands are too small to judge calibration.",
    }


def pilot_export(db: Session, user: User, include_demo: bool = False) -> dict:
    rows = [r for r in _rows(db, user) if include_demo or r["source"] == "user"]
    return {
        "pilot_id": secrets.token_hex(6),
        "exported_at": datetime.now().replace(microsecond=0).isoformat(),
        "schema": {
            "status": "done | partial | skipped | unreached (unreached = the day ran out; censored)",
            "predicted_p": "planner's chance the block would happen, at planning time",
            "context": "what the prediction used: demands, projected energy, focus, stress",
        },
        "outcomes": rows,
        "calibration": calibration(rows),
    }
