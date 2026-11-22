"""Two focused studies that complement the closed-loop experiment.

1. Solver benchmark (``run_solver_benchmark``)
   Static planning problems of increasing size, solved by the original GA, the
   hybrid GA + local search, and CP-SAT at two time limits. The score is the full
   fitness for every optimiser (CP-SAT's own objective is only a surrogate), and each
   plan is re-checked by the independent hard-rule engine. Reported per size: mean
   fitness, gap to the best plan found for that instance by any optimiser, runtime,
   hard-rule violations, and CP-SAT's status counts (OPTIMAL means optimal for its
   surrogate objective, not for the full fitness).

2. Replanning stability (``run_stability_study``)
   A morning plan is made at 08:30. At 11:00 something changes: an urgent 90-minute
   task due in 6 hours, or two hours of lost afternoon time (alternating by user).
   The day is replanned against the morning plan at several stability levels.
   Reported: blocks moved / removed, total displacement, plan quality measured
   WITHOUT the stability term (so stability can't flatter itself), Monte Carlo
   deadline safety, and whether the urgent task was placed.

SYNTHETIC DATA throughout.
"""
from __future__ import annotations

import random
import statistics
import time
from dataclasses import replace
from datetime import datetime, time as dtime, timedelta

import numpy as np

from ..ga.fitness import evaluate
from ..ga.runner import GAConfig, run_ga, run_hybrid
from ..pipeline import stability_report, verify
from ..problem import build_problem
from ..types import CheckIn, Commitment, PlanRequest, Preferences, TaskIn
from ..uncertainty import MCConfig, simulate_plan
from .experiment import EvalConfig, bootstrap_ci, make_world, paired_test, rank_biserial

NOW = datetime(2026, 1, 5, 8, 30)


def random_instance(seed: int, n: int, horizon: int = 3) -> PlanRequest:
    """A random planning problem: tasks with deadlines, dependencies, lectures and a check-in."""
    rnd = random.Random(seed)
    cats = ["Study", "Work", "Errand", "Health", "Admin"]
    tasks = []
    for i in range(1, n + 1):
        md, pd = rnd.randint(1, 10), rnd.randint(1, 8)
        tasks.append(TaskIn(
            id=i, title=f"T{i}", category=rnd.choice(cats), priority=rnd.randint(1, 4),
            est_minutes=rnd.choice([15, 30, 45, 60, 90, 120]),
            mental_difficulty=md, mental_req=md, physical_difficulty=pd, physical_req=pd,
            deadline=NOW + timedelta(hours=rnd.randint(2, 24 * horizon + 24)) if rnd.random() < 0.5 else None,
        ))
    for t in tasks[3:]:
        if rnd.random() < 0.15:
            t.depends_on = rnd.randint(1, t.id - 1)
    commits = []
    for d in range(horizon):
        day = NOW + timedelta(days=d)
        for h in rnd.sample([9, 10, 11, 14, 15, 16, 17], k=rnd.randint(1, 3)):
            commits.append(Commitment(day.replace(hour=h, minute=0), day.replace(hour=h + 1, minute=0), "Lecture"))
    checkins = [CheckIn(NOW, rnd.randint(3, 9), rnd.randint(3, 9), rnd.randint(3, 9), rnd.randint(1, 8))]
    return PlanRequest(NOW, tasks, commits, checkins, [], Preferences(horizon_days=horizon), seed=seed)


def run_solver_benchmark(sizes=(10, 20, 30, 40), instances: int = 5, seed: int = 2026,
                         cpsat_limits=(2.0, 10.0), include_cpsat: bool = True,
                         progress=None) -> dict:
    from ..cpsat import available
    from ..cpsat.scheduler import CPSATConfig, run_cpsat

    include_cpsat = include_cpsat and available()  # OR-Tools is optional
    names = ["ga", "hybrid"] + ([f"cpsat_{int(t)}s" for t in cpsat_limits] if include_cpsat else [])
    rows: dict[int, dict[str, list[dict]]] = {n: {k: [] for k in names} for n in sizes}
    total = len(sizes) * instances
    done = 0
    for n in sizes:
        for k in range(instances):
            s = seed * 100 + n * 7 + k
            p = build_problem(random_instance(s, n))
            results = {}
            t0 = time.perf_counter()
            results["ga"] = (run_ga(p, "balanced", s), time.perf_counter() - t0)
            t0 = time.perf_counter()
            results["hybrid"] = (run_hybrid(p, "balanced", s), time.perf_counter() - t0)
            if include_cpsat:
                for lim in cpsat_limits:
                    t0 = time.perf_counter()
                    r = run_cpsat(p, "balanced", s, CPSATConfig(time_limit=lim, seed=s))
                    results[f"cpsat_{int(lim)}s"] = (r, time.perf_counter() - t0)
            best = max(r.score.total for r, _ in results.values())
            for name, (r, secs) in results.items():
                try:
                    verify(p, r)
                    violations = 0
                except Exception:  # counted, never hidden
                    violations = 1
                info = r.details.get("cpsat", {})
                rows[n][name].append({
                    "fitness": r.score.total, "gap": (best - r.score.total) / max(1e-9, abs(best)),
                    "seconds": secs, "violations": violations,
                    "status": info.get("status"), "fallback": bool(info.get("fallback")),
                    "planned": sum(1 for x in r.decoded.starts if x >= 0),
                })
            done += 1
            if progress:
                progress(done / total)

    table = {}
    for n in sizes:
        table[n] = {}
        for name in names:
            xs = rows[n][name]
            statuses: dict[str, int] = {}
            for x in xs:
                if x["status"]:
                    statuses[x["status"]] = statuses.get(x["status"], 0) + 1
            table[n][name] = {
                "fitness": round(statistics.fmean(x["fitness"] for x in xs), 4),
                "gap_pct": round(100 * statistics.fmean(x["gap"] for x in xs), 2),
                "best_count": sum(1 for x in xs if x["gap"] < 1e-9),
                "seconds": round(statistics.fmean(x["seconds"] for x in xs), 2),
                "violations": sum(x["violations"] for x in xs),
                "planned": round(statistics.fmean(x["planned"] for x in xs), 1),
                **({"status": statuses, "fallbacks": sum(x["fallback"] for x in xs)} if name.startswith("cpsat") else {}),
            }
    import os

    return {"config": {"sizes": list(sizes), "instances": instances, "seed": seed, "cpsat_limits": list(cpsat_limits),
                       "cpu_count": os.cpu_count()},
            "optimizers": names, "table": {str(k): v for k, v in table.items()},
            "note": "Gap = shortfall from the best plan any optimiser found for that instance (full fitness). "
                    "CP-SAT is time-limited and multi-threaded, so its numbers can vary slightly between runs and machines.",
            "data": "synthetic"}


def _quality(p, starts, lengths) -> float:
    """Fitness without the stability term, so the comparison isn't circular."""
    s0 = p.stability
    p.stability = 0.0
    try:
        return evaluate(p, starts, lengths, "balanced").total
    finally:
        p.stability = s0


def run_stability_study(users: int = 10, days: int = 3, levels=(0.0, 0.25, 0.5, 1.0), seed: int = 2026,
                        progress=None) -> dict:
    cfg = EvalConfig(users=users, days=days, seed=seed)
    ga = GAConfig(population=40, generations=60, patience=12)
    from .experiment import EVAL_LS

    rows: dict[float, list[dict]] = {lv: [] for lv in levels}
    total = users * days
    done = 0
    for k in range(users):
        w = make_world(seed * 1000 + k, cfg)
        for d in range(days):
            day = cfg.start + timedelta(days=d)
            morning = datetime.combine(day, dtime(8, 30))
            tasks = [replace(t) for t in w.new_tasks[d]] + [replace(t) for t in w.new_tasks[min(d + 1, days - 1)]]
            commits = [c for dd in range(d, d + 3) for c in w.commitments[dd]]
            base = PlanRequest(morning, tasks, commits, w.checkins[max(0, d - 29): d + 1], [],
                               Preferences(horizon_days=3), seed=seed + k * 31 + d)
            p0 = build_problem(base)
            r0 = run_hybrid(p0, "balanced", base.seed, ga, EVAL_LS)
            prev = [(p0.tasks[i].task.id, p0.slot_dt(s)) for i, s in enumerate(r0.decoded.starts) if s >= 0]
            later = datetime.combine(day, dtime(11, 0))
            new_tasks = list(tasks)
            new_commits = list(commits)
            if (k + d) % 2 == 0:
                kind = "urgent task"
                new_tasks.append(TaskIn(id=9999, title="Urgent", category="Work", priority=4, est_minutes=90,
                                        mental_difficulty=6, mental_req=6, deadline=later + timedelta(hours=6)))
            else:
                kind = "lost time"
                new_commits.append(Commitment(datetime.combine(day, dtime(14)), datetime.combine(day, dtime(16)),
                                              "Lost time", "unavailable"))
            for lv in levels:
                req = PlanRequest(later, [replace(t) for t in new_tasks], new_commits, base.checkins, [],
                                  Preferences(horizon_days=3), seed=base.seed, previous=prev, stability=lv)
                p = build_problem(req)
                r = run_hybrid(p, "balanced", req.seed, ga, EVAL_LS)
                verify(p, r)
                rep = stability_report(p, r.decoded.starts) or {"moved": 0, "removed": 0, "displacement_minutes": 0,
                                                                "previous_blocks": 0}
                mc = simulate_plan(p, r.decoded.starts, MCConfig(runs=200, seed=req.seed))
                urgent = next((i for i, ti in enumerate(p.tasks) if ti.task.id == 9999), None)
                rows[lv].append({
                    "kind": kind, "moved": rep["moved"], "removed": rep["removed"],
                    "changed": rep["moved"] + rep["removed"], "displacement": rep["displacement_minutes"],
                    "previous": rep["previous_blocks"], "quality": _quality(p, r.decoded.starts, r.decoded.lengths),
                    "deadline_safety": mc["deadline_safety"] if mc["deadline_safety"] is not None else 1.0,
                    "urgent_placed": None if urgent is None else r.decoded.starts[urgent] >= 0,
                })
            done += 1
            if progress:
                progress(done / total)

    def mean_ci(xs):
        lo, hi = bootstrap_ci(xs, seed)
        return {"mean": round(statistics.fmean(xs), 3), "ci": [round(lo, 3), round(hi, 3)]}

    table = {}
    ref = rows[levels[0]]
    for lv in levels:
        xs = rows[lv]
        urg = [x["urgent_placed"] for x in xs if x["urgent_placed"] is not None]
        entry = {m: mean_ci([x[m] for x in xs]) for m in ("moved", "removed", "changed", "displacement", "quality",
                                                           "deadline_safety")}
        entry["urgent_placed_pct"] = round(100 * statistics.fmean(1.0 if u else 0.0 for u in urg), 1) if urg else None
        if lv != levels[0]:
            entry["vs_free"] = {}
            for m in ("changed", "displacement", "quality", "deadline_safety"):
                a, b = [x[m] for x in xs], [x[m] for x in ref]
                pv = paired_test(a, b)
                eff = rank_biserial(a, b)
                entry["vs_free"][m] = {"diff": round(statistics.fmean(np.subtract(a, b)), 3),
                                       "p": None if pv is None else round(pv, 4),
                                       "effect": None if eff is None else round(eff, 3)}
        table[str(lv)] = entry
    return {"config": {"users": users, "days": days, "levels": list(levels), "seed": seed},
            "cases": len(ref), "previous_blocks_mean": round(statistics.fmean(x["previous"] for x in ref), 2),
            "table": table,
            "note": "Quality is the Balanced fitness without the stability term. Each case is one disruption "
                    "replanned at every level from the same morning plan (paired).",
            "data": "synthetic"}
