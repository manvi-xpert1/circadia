"""What the planner has learned so far, and the rule base, for transparency."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai.fuzzy.engine import CAPACITY_RULES, RULE_TEXT, STRESS_RULES
from ai.fuzzy.profile import learn_profile
from ai.ga.fitness import PRESETS
from ai.probability.duration_model import DurationModel
from ai.probability.followthrough import FollowThroughModel
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
        "followthrough": FollowThroughModel(outcomes).summary(),
        "profile": learn_profile(checkins).as_dict(),
        "finished_with_minutes": n_done,
        "records": counts(db, user),
    }


@router.get("/rules")
def rules():
    return {
        "hard": hard_rules.describe(),
        "soft": soft_rules.describe(),
        "fuzzy_capacity": [{"if": f"Energy {e} and Focus {f}", "then": c} for (e, f), c in CAPACITY_RULES.items()]
        + [{"if": f"Stress High and Energy {e}", "then": c} for e, c in STRESS_RULES.items()],
        "fuzzy_suitability": [{"id": k, "meaning": v} for k, v in RULE_TEXT.items()],
        "presets": PRESETS,
    }
