"""Does context predict whether a block happens? Completion models compared, prequentially.

Data: outcome histories from the closed-loop simulation (synthetic users following
plans made by the hybrid planner). Every outcome carries the context saved when its
plan was made.

Protocol: for each user, walk the history in order; before each outcome, fit each
model on that user's earlier outcomes only, predict, then reveal the outcome. No
model ever sees the future. Censored ("unreached") blocks are not predicted.

Models
  constant     one Beta(4, 1) rate for everything (the follow-through prior, pooled)
  category     the category follow-through model (Beta(4, 1) per category)
  contextual   the Bayesian logistic completion model with its default prior
  contextual (flat prior)   the same model with zero-mean priors on the energy terms,
               to show how much comes from the prior rather than the data

Metrics (lower is better unless noted)
  Brier score  mean squared error of the probability
  log loss     mean negative log-likelihood
  ECE          expected calibration error over 10 equal-width bins
  AUC          ranking quality, higher is better; reported, but with a few dozen
               outcomes per user it is noisy and says nothing about calibration
Paired per-user differences in Brier score get a bootstrap 95% interval.

SYNTHETIC DATA. In the simulator, the chance of starting a block depends on how
the task's demand compares with the user's true energy at that time. That is an
assumption about people; a real-user pilot is needed to check it.
"""
from __future__ import annotations

import math
import statistics

import numpy as np

from ..probability.completion import DEFAULT_PRIOR, FLAT_CONTEXT_PRIOR, CompletionModel, context_features
from ..probability.followthrough import FollowThroughModel, PRIOR_DONE, PRIOR_SKIPPED
from .experiment import EvalConfig, make_world, simulate

MODELS = ["constant", "category", "contextual", "contextual_flat"]
LABELS = {"constant": "Constant rate", "category": "Category follow-through",
          "contextual": "Contextual model", "contextual_flat": "Contextual, flat prior"}


def _label(o) -> float | None:
    if o.status in ("done", "partial"):
        return 1.0
    if o.status == "skipped":
        return 0.0
    return None


def _predict(name: str, history, o) -> float:
    if name == "constant":
        ys = [y for y in (_label(h) for h in history) if y is not None]
        return (PRIOR_DONE + sum(ys)) / (PRIOR_DONE + PRIOR_SKIPPED + len(ys))
    if name == "category":
        return FollowThroughModel(history).for_category(o.category).p
    model = CompletionModel(history, FLAT_CONTEXT_PRIOR if name == "contextual_flat" else DEFAULT_PRIOR)
    c = o.context
    if c is None:
        return model.predict(o.category, model.fill).p
    x = context_features(c.mental_demand, c.physical_demand, c.expected_mental, c.expected_physical,
                         c.focus, c.stress, o.est_minutes)
    return model.predict(o.category, x).p


def auc(p: np.ndarray, y: np.ndarray) -> float | None:
    if y.min() == y.max():
        return None
    from scipy.stats import rankdata

    r = rankdata(p)
    n1 = y.sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    idx = np.minimum((p * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.sum() * abs(p[m].mean() - y[m].mean())
    return float(total / len(p))


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 5) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.any():
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()), "predicted": round(float(p[m].mean()), 3),
                        "observed": round(float(y[m].mean()), 3)})
    return out


def metrics(p: np.ndarray, y: np.ndarray) -> dict:
    eps = 1e-9
    a = auc(p, y)
    return {
        "n": int(len(y)),
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "log_loss": round(float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))), 4),
        "ece": round(ece(p, y), 4),
        "auc": None if a is None else round(a, 3),
        "mean_predicted": round(float(p.mean()), 3),
        "observed_rate": round(float(y.mean()), 3),
    }


def collect_histories(users: int, days: int, seed: int, difficulty: str = "moderate") -> list[list]:
    cfg = EvalConfig(users=users, days=days, seed=seed, difficulty=difficulty, compare_horizon=False)
    out = []
    for k in range(users):
        useed = seed * 1000 + k
        out.append(simulate(make_world(useed, cfg), "hybrid", cfg, useed).outcomes)
    return out


def run_completion_study(users: int = 12, days: int = 10, seed: int = 2026, histories=None) -> dict:
    histories = histories if histories is not None else collect_histories(users, days, seed)
    preds = {m: [] for m in MODELS}
    ys, sizes, owner = [], [], []
    for u, hist in enumerate(histories):
        for j, o in enumerate(hist):
            y = _label(o)
            if y is None:
                continue
            past = hist[:j]
            for m in MODELS:
                preds[m].append(_predict(m, past, o))
            ys.append(y)
            sizes.append(sum(1 for h in past if _label(h) is not None))
            owner.append(u)
    y = np.array(ys)
    sizes = np.array(sizes)
    owner = np.array(owner)
    P = {m: np.clip(np.array(v), 1e-6, 1 - 1e-6) for m, v in preds.items()}
    result = {m: metrics(P[m], y) for m in MODELS}
    buckets = {"0-9": sizes < 10, "10-29": (sizes >= 10) & (sizes < 30), "30+": sizes >= 30}
    by_history = {b: {m: metrics(P[m][mask], y[mask]) for m in MODELS} for b, mask in buckets.items() if mask.sum() >= 20}
    # Paired per-user Brier difference (contextual minus category), bootstrap CI over users.
    users_ = sorted(set(owner.tolist()))
    diffs = []
    for u in users_:
        m = owner == u
        diffs.append(float(np.mean((P["contextual"][m] - y[m]) ** 2) - np.mean((P["category"][m] - y[m]) ** 2)))
    rng = np.random.default_rng(seed)
    boots = [float(np.mean(rng.choice(diffs, size=len(diffs)))) for _ in range(2000)]
    from scipy.stats import wilcoxon

    try:
        pval = float(wilcoxon(diffs).pvalue)
    except ValueError:
        pval = None
    return {
        "config": {"users": len(histories), "days": days, "seed": seed},
        "labels": LABELS,
        "overall": result,
        "by_history": by_history,
        "reliability": {m: reliability(P[m], y) for m in ("category", "contextual")},
        "brier_difference": {"mean": round(statistics.fmean(diffs), 4),
                             "ci": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)],
                             "p": None if pval is None else round(pval, 4),
                             "users_better": int(sum(d < 0 for d in diffs)),
                             "meaning": "contextual minus category, per user; negative favours the contextual model"},
        "data": "synthetic",
    }
