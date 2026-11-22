"""Calibration study for the duration models (v1 vs v2).

For each synthetic user, outcomes arrive one at a time, as in real use. Before each
new task is done, the model is fitted on everything seen so far and asked for its
P80 and median for that task. Then the true duration is revealed. Reported:

  coverage    share of tasks that finished within P80. A calibrated P80 covers 80%.
              Below 80% means blocks are too short (overruns); above means padding.
  pinball80   quantile (pinball) loss of P80, in minutes: a proper scoring rule that
              rewards a P80 that is both calibrated and tight. Lower is better.
  log_score   mean predictive log density of ln(actual / estimate). Higher is better.
  mae         absolute error of the median prediction, in minutes.

Results are split by how many outcomes the task's category had when predicted
(0, 1-2, 3-9, 10+), because that is where the models differ.

The synthetic truth is the evaluation lab's (ai.evaluation.simulator): a true ratio
per category, lognormal noise (sd 0.2), and slower work at a poor energy fit. The
energy fit of each task is drawn uniformly from 0.5-1 here, since no plan is involved.
SYNTHETIC DATA: nothing here is a real user's record.
"""
from __future__ import annotations

import math
import random
import statistics

import numpy as np

from ..probability.duration_model import DurationModel
from ..types import Outcome
from .simulator import CATEGORIES, SyntheticUser

BUCKETS = [(0, 0, "0"), (1, 2, "1-2"), (3, 9, "3-9"), (10, 10**9, "10+")]


def _bucket(n: int) -> str:
    for lo, hi, name in BUCKETS:
        if lo <= n <= hi:
            return name
    return "10+"


def run_calibration(users: int = 30, tasks_per_user: int = 40, seed: int = 2026,
                    versions: tuple[str, ...] = ("v1", "v2")) -> dict:
    rows: dict[str, list[dict]] = {v: [] for v in versions}
    for k in range(users):
        u = SyntheticUser.create(seed * 1000 + k)
        r = random.Random(f"cal-{seed}-{k}")
        # Users tend to do some categories much more than others.
        cat_weights = [r.random() ** 2 + 0.05 for _ in CATEGORIES]
        history: list[Outcome] = []
        counts = {c: 0 for c in CATEGORIES}
        for _ in range(tasks_per_user):
            cat = r.choices(CATEGORIES, weights=cat_weights)[0]
            est = r.choice([30, 45, 60, 60, 90, 120])
            fit = r.uniform(0.5, 1.0)
            actual = est * u.ratios[cat] * math.exp(r.gauss(0, 0.2)) * (1 + 0.35 * (1 - fit))
            for v in versions:
                d = DurationModel(history, version=v).for_category(cat)
                p80 = d.p80(est)
                rows[v].append({
                    "bucket": _bucket(counts[cat]),
                    "covered": actual <= p80,
                    "pinball": (0.8 * (actual - p80) if actual >= p80 else 0.2 * (p80 - actual)),
                    "log_score": d.log_density(actual, est),
                    "abs_err": abs(d.median(est) - actual),
                    "p80_over_est": p80 / est,
                })
            history.append(Outcome(cat, "done", est, int(round(actual))))
            counts[cat] += 1

    def agg(xs: list[dict]) -> dict:
        if not xs:
            return {"n": 0}
        return {
            "n": len(xs),
            "coverage": round(100 * statistics.fmean(1.0 if x["covered"] else 0.0 for x in xs), 1),
            "pinball80": round(statistics.fmean(x["pinball"] for x in xs), 2),
            "log_score": round(statistics.fmean(x["log_score"] for x in xs), 3),
            "mae": round(statistics.fmean(x["abs_err"] for x in xs), 2),
            "p80_padding": round(statistics.fmean(x["p80_over_est"] for x in xs), 3),
        }

    out: dict = {"config": {"users": users, "tasks_per_user": tasks_per_user, "seed": seed}, "versions": {}}
    for v in versions:
        out["versions"][v] = {"all": agg(rows[v])}
        for _, _, name in BUCKETS:
            out["versions"][v][name] = agg([x for x in rows[v] if x["bucket"] == name])
    # Paired comparison of pinball loss per prediction (same tasks, same order).
    if len(versions) == 2:
        a = np.array([x["pinball"] for x in rows[versions[0]]])
        b = np.array([x["pinball"] for x in rows[versions[1]]])
        diff = b - a
        rng = np.random.default_rng(seed)
        boots = rng.choice(diff, size=(2000, diff.size), replace=True).mean(axis=1)
        out["pinball_difference"] = {
            "mean": round(float(diff.mean()), 3),
            "ci": [round(float(np.percentile(boots, 2.5)), 3), round(float(np.percentile(boots, 97.5)), 3)],
            "meaning": f"{versions[1]} minus {versions[0]}, minutes; negative favours {versions[1]}",
        }
    out["data"] = "synthetic"
    return out
