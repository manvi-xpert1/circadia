"""Evaluation lab: runs the four-scheduler experiment on synthetic users in the background."""
import threading
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.evaluation.calibration import run_calibration
from ai.evaluation.experiment import EvalConfig, run_experiment
from ai.evaluation.studies import run_solver_benchmark, run_stability_study

from ..db import SessionLocal, get_db
from ..models import EvaluationRun, Feedback, ScheduleVersion, User
from ..security import current_user

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])
_lock = threading.Lock()


class RunIn(BaseModel):
    users: int = Field(default=10, ge=2, le=40)
    days: int = Field(default=7, ge=2, le=21)
    horizon: int = Field(default=3, ge=1, le=5)
    seed: int = Field(default=2026, ge=0, le=10**6)
    compare_horizon: bool = True
    difficulty: Literal["easy", "moderate", "tight"] = "moderate"
    include_cpsat: bool = False  # adds about 2 s per plan
    ablations: bool = False
    # Extra studies, run after the main comparison.
    calibration: bool = True  # duration models v1 vs v2 (fast)
    stability: bool = False  # replanning at several stability levels
    solver_benchmark: bool = False  # GA vs hybrid vs CP-SAT by problem size (slow)


def _work(run_id: int, cfg: EvalConfig, body: "RunIn | None" = None) -> None:
    db = SessionLocal()
    run = db.get(EvaluationRun, run_id)
    last = [0.0]

    def progress(f: float) -> None:
        if f - last[0] >= 0.02 or f >= 1:
            last[0] = f
            run.progress = round(f, 3)
            db.commit()

    try:
        with _lock:  # one experiment at a time keeps the laptop responsive
            extra = [k for k in ("calibration", "stability", "solver_benchmark") if body and getattr(body, k)]
            share = 1.0 / (1 + len(extra))
            results = run_experiment(cfg, lambda f: progress(f * share))
            studies = {}
            for j, k in enumerate(extra):
                base = share * (j + 1)
                sub = lambda f, base=base: progress(base + f * share)  # noqa: E731
                if k == "calibration":
                    studies[k] = run_calibration(seed=cfg.seed)
                elif k == "stability":
                    studies[k] = run_stability_study(users=min(cfg.users, 10), days=min(cfg.days, 3), seed=cfg.seed,
                                                     progress=sub)
                else:
                    studies[k] = run_solver_benchmark(sizes=(10, 20, 30), instances=3, seed=cfg.seed,
                                                      cpsat_limits=(2.0, 10.0), progress=sub)
                sub(1.0)
            results["studies"] = studies
        run.results_json = results
        run.status = "done"
    except Exception:  # surfaced in the UI rather than lost
        run.status = "failed"
        run.error = traceback.format_exc(limit=3)
    run.finished_at = datetime.now()
    db.commit()
    db.close()


def _out(r: EvaluationRun, db: Session, user: User) -> dict:
    out = {
        "id": r.id, "status": r.status, "progress": r.progress, "dataset": r.dataset, "config": r.config_json,
        "created_at": r.created_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "error": r.error or None, "results": r.results_json,
    }
    # Real usefulness ratings come from your own plans, not from the simulation.
    vids = [v for v in db.scalars(select(ScheduleVersion.id).where(ScheduleVersion.user_id == user.id))]
    ratings = list(db.scalars(select(Feedback.usefulness).where(Feedback.version_id.in_(vids)))) if vids else []
    out["usefulness"] = {"n": len(ratings), "mean": round(sum(ratings) / len(ratings), 2) if ratings else None}
    return out


@router.post("/runs", status_code=202)
def start(body: RunIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.scalar(select(EvaluationRun).where(EvaluationRun.user_id == user.id, EvaluationRun.status == "running")):
        raise HTTPException(409, {"code": "BUSY", "message": "An experiment is already running. Wait for it to finish."})
    cfg = EvalConfig(users=body.users, days=body.days, horizon=body.horizon, seed=body.seed, compare_horizon=body.compare_horizon,
                     difficulty=body.difficulty, include_cpsat=body.include_cpsat, ablations=body.ablations)
    r = EvaluationRun(user_id=user.id, config_json=body.model_dump())
    db.add(r)
    db.commit()
    threading.Thread(target=_work, args=(r.id, cfg, body), daemon=True).start()
    return _out(r, db, user)


@router.get("/runs")
def list_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(EvaluationRun).where(EvaluationRun.user_id == user.id).order_by(EvaluationRun.created_at.desc()).limit(20)).all()
    return [{"id": r.id, "status": r.status, "progress": r.progress, "config": r.config_json,
             "created_at": r.created_at.isoformat(), "seconds": (r.results_json or {}).get("seconds")} for r in rows]


@router.get("/runs/{rid}")
def get_run(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(EvaluationRun, rid)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Run not found."})
    return _out(r, db, user)


@router.delete("/runs/{rid}", status_code=204)
def delete_run(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(EvaluationRun, rid)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Run not found."})
    if r.status == "running":
        raise HTTPException(409, {"code": "BUSY", "message": "Wait for the run to finish before deleting it."})
    db.delete(r)
    db.commit()
