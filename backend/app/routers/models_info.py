"""What the planner has learned so far, and the rule base, for transparency."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai.ga.fitness import PRESETS
from ai.probability.completion import CompletionModel
from ai.probability.duration_model import DurationModel
from ai.probability.energy_profile import learn_profile
from ai.rules import hard_rules, soft_rules

from ..db import get_db
from ..models import User
from ..security import current_user
from ..services.demo import counts
from ..services.planner import load_checkins, load_outcomes

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
def learned(user: User = Depends(current_user), db: Session = Depends(get_db)):
    outcomes = load_outcomes(db, user)
    checkins = load_checkins(db, user)
    n_done = sum(1 for o in outcomes if o.status == "done" and o.actual_minutes)
    return {
        "mode": "personalized" if len(outcomes) >= 3 else "cold",
        "durations": DurationModel(outcomes).summary(),
        "completion": CompletionModel(outcomes).summary(),
        "profile": learn_profile(checkins).as_dict(),
        "finished_with_minutes": n_done,
        "records": counts(db, user),
    }


@router.get("/rules")
def rules():
    return {
        "hard": hard_rules.describe(),
        "soft": soft_rules.describe(),
        "presets": PRESETS,
    }
