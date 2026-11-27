"""Paired closed-loop comparison of a chosen set of schedulers or policies.

    python -m ai.evaluation.compare hybrid,abl_fuzzy,abl_no_context --users 20 --days 10 --difficulty tight
    python -m ai.evaluation.compare hybrid,buf_p50,buf_p65 --out ../docs/results/buffers_tight.json

The first name is the reference; every other name is compared with it on the same
synthetic users (bootstrap CI of the paired difference, Wilcoxon p, Holm-adjusted
across the comparisons for each metric). Names are the keys of experiment.SCHEDULERS.
Differences are reported as reference minus other.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from .experiment import SCHEDULERS, EvalConfig, holm, make_world, paired_comparison, simulate

METRICS = ["completed_per_day", "completion_rate", "deadline_violation_rate", "collisions", "overload_minutes",
           "energy_fit", "duration_mae", "plan_seconds"]


def compare(names: list[str], cfg: EvalConfig, progress=print) -> dict:
    unknown = [n for n in names if n not in SCHEDULERS]
    if unknown:
        raise ValueError(f"Unknown scheduler(s): {', '.join(unknown)}")
    t0 = time.perf_counter()
    per = {n: [] for n in names}
    for k in range(cfg.users):
        useed = cfg.seed * 1000 + k
        for n in names:
            per[n].append(simulate(make_world(useed, cfg), n, cfg, useed).metrics(cfg.days))
        if progress:
            progress(f"user {k + 1}/{cfg.users}, {time.perf_counter() - t0:.0f} s")
    ref = names[0]
    summary, comparisons = {}, {}
    for m in METRICS:
        summary[m] = {n: round(statistics.fmean(x[m] for x in per[n]), 4) for n in names}
        raw = {}
        for o in names[1:]:
            c = paired_comparison([x[m] for x in per[ref]], [x[m] for x in per[o]], cfg.seed)
            comparisons.setdefault(o, {})[m] = c
            raw[o] = c["p"]
        for o, ph in holm(raw).items():
            comparisons[o][m]["p_holm"] = None if ph is None else round(ph, 4)
    return {
        "config": {"users": cfg.users, "days": cfg.days, "horizon": cfg.horizon, "seed": cfg.seed,
                   "difficulty": cfg.difficulty},
        "reference": ref,
        "schedulers": {n: SCHEDULERS[n] for n in names},
        "summary": summary,
        "comparisons": comparisons,
        "per_user": per,
        "seconds": round(time.perf_counter() - t0, 1),
        "data": "synthetic",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", help="comma-separated scheduler names; the first is the reference")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--difficulty", default="moderate", choices=["easy", "moderate", "tight"])
    ap.add_argument("--out", type=Path, help="write the full result as JSON")
    a = ap.parse_args()
    res = compare(a.names.split(","), EvalConfig(users=a.users, days=a.days, seed=a.seed, difficulty=a.difficulty))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1, default=str))
    for m, row in res["summary"].items():
        print(f"{m:26s}", "  ".join(f"{n} {v}" for n, v in row.items()))


if __name__ == "__main__":
    main()
