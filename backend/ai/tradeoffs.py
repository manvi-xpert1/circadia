"""Trade-offs between alternative plans (a Pareto filter, used instead of NSGA-II).

Circadia already produces up to three plans, one per style (Balanced, Deadline-first,
Gentle): three weightings of one fitness, i.e. three points on the trade-off curve.
This module compares them on separate objectives without adding them up:

  completion   expected tasks finished (Monte Carlo)
  deadlines    share of tasks due in the horizon that finish on time (Monte Carlo)
  energy       weighted mean chance that placed blocks happen at their times
  calm         1 - the busiest day's load
  stability    1 - the stability penalty (only when replanning against a previous plan)

A plan is dominated when another plan is at least as good on every objective and
clearly better on one (differences under TOLERANCE count as ties, since Monte Carlo
estimates carry noise). Each plan is labelled with what it is best at and what it
gives up compared with the main plan.

Why not NSGA-II: with three to five plans to show, a full evolutionary multi-objective
search adds a second optimiser to maintain, its crowding distance works poorly with
five objectives, and a single user can't compare a large front. The filter answers
the question the user actually has ("which of these plans is better at what?").
"""
from __future__ import annotations

OBJECTIVES = {
    "completion": "Expected tasks finished",
    "deadlines": "Deadlines met",
    "energy": "Blocks likely to happen",
    "calm": "Lighter busiest day",
    "stability": "Keeps your existing plan",
}
TOLERANCE = {"completion": 0.15, "deadlines": 0.01, "energy": 0.005, "calm": 0.01, "stability": 0.01}


def objectives(plan: dict) -> dict[str, float]:
    rob = plan.get("robustness") or {}
    out = {
        "completion": float(rob.get("expected_completed", 0.0)),
        "deadlines": float(rob["deadline_safety"]) if rob.get("deadline_safety") is not None else 1.0,
        "energy": float(plan["components"].get("en", 0.0)),
        "calm": 1.0 - max((d["load"] for d in plan["day_load"]), default=0.0),
    }
    if "stab" in plan["components"]:
        out["stability"] = 1.0 - float(plan["components"]["stab"])
    return out


def dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    keys = [k for k in a if k in b]
    better = False
    for k in keys:
        if a[k] < b[k] - TOLERANCE[k]:
            return False
        if a[k] > b[k] + TOLERANCE[k]:
            better = True
    return better


def annotate(plans: list[dict]) -> None:
    """Adds a ``tradeoffs`` entry to every plan dict, in place."""
    objs = [objectives(p) for p in plans]
    keys = list(objs[0]) if objs else []
    for i, pl in enumerate(plans):
        o = objs[i]
        by = [plans[j]["label"] for j in range(len(plans)) if j != i and dominates(objs[j], o)]
        best_at = [OBJECTIVES[k] for k in keys
                   if len(plans) > 1 and all(o[k] >= objs[j][k] - TOLERANCE[k] for j in range(len(plans)))
                   and any(o[k] > objs[j][k] + TOLERANCE[k] for j in range(len(plans)) if j != i)]
        gives_up = []
        if i > 0:
            main = objs[0]
            for k in keys:
                if o[k] < main[k] - TOLERANCE[k]:
                    gives_up.append(OBJECTIVES[k])
        pl["tradeoffs"] = {
            "objectives": {k: round(v, 3) for k, v in o.items()},
            "pareto_optimal": not by,
            "dominated_by": by,
            "best_at": best_at,
            "gives_up_vs_main": gives_up,
        }
