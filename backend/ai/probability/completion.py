"""Contextual completion model: P(a planned block happens | task, time, user state).

What it predicts
----------------
The probability that the user actually works a planned block (status "done" or
"partial") rather than skipping it, given what is known when the plan is made:

    category               one effect per task category, shrunk toward 0
    mental shortfall       max(0, task's mental demand - projected mental energy at that time)
    physical shortfall     the same for physical demand and energy
    focus, stress          the day's check-in (centred)
    log duration           longer blocks may be skipped more often

Projected energy at a time of day comes from the day's check-in and the learned
time-of-day profile (``energy_profile``), so the model sees context, not clock time.

Model
-----
Bayesian logistic regression, fitted by Newton's method to the maximum a posteriori
estimate, with a Laplace (Gaussian) approximation of the posterior:

    logit P = b0 + b_cat + b_m * mental_shortfall + b_p * physical_shortfall
                 + b_f * focus + b_s * stress + b_d * log(duration / 60)

Priors (all Gaussian):
    b0      mean logit(0.8), sd 1.0  - most planned blocks happen (the follow-through prior)
    b_cat   mean 0, sd 0.5           - categories differ, but only as far as the data shows
    b_m     mean -0.25, sd 0.25      - working above your energy makes skipping more likely;
    b_p     mean -0.20, sd 0.25        this is the domain knowledge the old rule base encoded,
                                       kept as a prior the data can overturn
    b_f, b_s, b_d   mean 0, sd 0.5

With no history the prediction is the prior: about 0.8, lowered for blocks well
above the projected energy. Each observation moves the posterior a little.

Uncertainty
-----------
The predictive probability integrates over the posterior with the probit
approximation, P = sigmoid(mu / sqrt(1 + pi * v / 8)), where mu and v are the
mean and variance of the logit. Sparse data means a large v, which pulls the
prediction toward 0.5 instead of trusting a few observations. ``predict`` also
returns a 95% interval and how many outcomes the model has learned from.

Training targets
----------------
done / partial = 1, skipped = 0. "unreached" blocks (the day ran out before they
could start) are censored and left out. Only the context saved at planning time is
used, never anything recorded after the block. Outcomes saved without context
(older records) still inform the intercept and category terms: their context
features are set to the mean of the outcomes that have one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..types import Outcome, OutcomeContext

POSITIVE = ("done", "partial")
NEGATIVE = ("skipped",)
FOCUS_CENTRE, FOCUS_SCALE = 6.0, 2.0
STRESS_CENTRE, STRESS_SCALE = 4.5, 2.0
PRIOR_P = 0.8
FEATURES = ["intercept", "mental_shortfall", "physical_shortfall", "focus", "stress", "log_duration"]


@dataclass(frozen=True)
class Prior:
    mean: tuple[float, ...] = (math.log(PRIOR_P / (1 - PRIOR_P)), -0.25, -0.20, 0.0, 0.0, 0.0)
    sd: tuple[float, ...] = (1.0, 0.25, 0.25, 0.5, 0.5, 0.5)
    category_sd: float = 0.5


DEFAULT_PRIOR = Prior()
FLAT_CONTEXT_PRIOR = Prior(mean=(math.log(PRIOR_P / (1 - PRIOR_P)), 0.0, 0.0, 0.0, 0.0, 0.0))


@dataclass
class Prediction:
    p: float  # predictive probability (posterior-averaged)
    low: float  # 95% interval for the probability
    high: float
    n: int  # outcomes the model has learned from
    contributions: dict[str, float]  # each feature's share of the logit, relative to a neutral block


def context_features(mental_demand: float, physical_demand: float, expected_mental: float, expected_physical: float,
                     focus: float, stress: float, est_minutes: float) -> np.ndarray:
    """The non-category features of one block, in FEATURES order."""
    return np.array([
        1.0,
        max(0.0, mental_demand - expected_mental),
        max(0.0, physical_demand - expected_physical),
        (focus - FOCUS_CENTRE) / FOCUS_SCALE,
        (stress - STRESS_CENTRE) / STRESS_SCALE,
        math.log(max(5.0, est_minutes) / 60.0),
    ])


def _ctx_row(c: OutcomeContext, est: float) -> np.ndarray:
    return context_features(c.mental_demand, c.physical_demand, c.expected_mental, c.expected_physical,
                            c.focus, c.stress, est)


def training_rows(outcomes: list[Outcome]) -> tuple[list[str], np.ndarray | None, np.ndarray]:
    """(categories, context matrix or None per row, labels) for the usable outcomes."""
    cats, rows, ys = [], [], []
    for o in outcomes:
        if o.status in POSITIVE:
            y = 1.0
        elif o.status in NEGATIVE:
            y = 0.0
        else:
            continue  # censored ("unreached") or unknown
        cats.append(o.category)
        rows.append(None if o.context is None else _ctx_row(o.context, o.est_minutes))
        ys.append(y)
    return cats, rows, np.array(ys)


class CompletionModel:
    """Bayesian logistic regression over block context. See the module docstring."""

    def __init__(self, outcomes: list[Outcome], prior: Prior = DEFAULT_PRIOR, max_iter: int = 30):
        self.prior = prior
        cats, rows, y = training_rows(outcomes)
        self.n = len(y)
        self.categories = sorted(set(cats))
        k0 = len(FEATURES)
        self.k = k0 + len(self.categories)
        mean = np.concatenate([np.array(prior.mean), np.zeros(len(self.categories))])
        prec = np.concatenate([1 / np.array(prior.sd) ** 2, np.full(len(self.categories), 1 / prior.category_sd ** 2)])
        self.prior_mean, self.prior_prec = mean, prec
        observed = [r for r in rows if r is not None]
        self.fill = np.mean(observed, axis=0) if observed else np.array([1.0, 0, 0, 0, 0, 0])
        self.n_context = len(observed)
        X = np.zeros((self.n, self.k))
        for j, (c, r) in enumerate(zip(cats, rows)):
            X[j, :k0] = self.fill if r is None else r
            X[j, k0 + self.categories.index(c)] = 1.0
        beta = mean.copy()
        for _ in range(max_iter):
            z = X @ beta
            p = 1 / (1 + np.exp(-z))
            grad = X.T @ (y - p) - prec * (beta - mean)
            H = (X.T * (p * (1 - p))) @ X + np.diag(prec)
            step = np.linalg.solve(H, grad)
            beta = beta + step
            if np.max(np.abs(step)) < 1e-8:
                break
        z = X @ beta
        p = 1 / (1 + np.exp(-z))
        H = (X.T * (p * (1 - p))) @ X + np.diag(prec)
        self.beta = beta
        self.cov = np.linalg.inv(H)

    # ---- prediction -----------------------------------------------------------------
    def _design(self, category: str, ctx: np.ndarray) -> np.ndarray:
        x = np.zeros(self.k)
        x[: len(FEATURES)] = ctx
        if category in self.categories:
            x[len(FEATURES) + self.categories.index(category)] = 1.0
        return x

    def predict_logit(self, category: str, ctx: np.ndarray) -> tuple[float, float]:
        x = self._design(category, ctx)
        return float(x @ self.beta), float(x @ self.cov @ x)

    def predict(self, category: str, ctx: np.ndarray) -> Prediction:
        mu, v = self.predict_logit(category, ctx)
        p = _probit_mean(mu, v)
        sd = math.sqrt(max(v, 0.0))
        neutral = context_features(0, 0, 0, 0, FOCUS_CENTRE, STRESS_CENTRE, 60)
        contrib = {f: float(self.beta[j] * (ctx[j] - neutral[j])) for j, f in enumerate(FEATURES) if j > 0}
        if category in self.categories:
            contrib["category"] = float(self.beta[len(FEATURES) + self.categories.index(category)])
        return Prediction(p, _sigmoid(mu - 1.96 * sd), _sigmoid(mu + 1.96 * sd), self.n, contrib)

    def predict_matrix(self, categories: list[str], ctx: np.ndarray) -> np.ndarray:
        """Predictive probabilities for many blocks at once. ctx: (..., len(FEATURES)) per task row."""
        k0 = len(FEATURES)
        B0, S00 = self.beta[:k0], self.cov[:k0, :k0]
        out = np.empty(ctx.shape[:-1])
        for i, c in enumerate(categories):
            mu = ctx[i] @ B0
            v = np.einsum("...j,jk,...k->...", ctx[i], S00, ctx[i])
            if c in self.categories:
                j = k0 + self.categories.index(c)
                mu = mu + self.beta[j]
                v = v + self.cov[j, j] + 2 * ctx[i] @ self.cov[:k0, j]
            out[i] = _probit_mean(mu, v)
        return out

    def coefficients(self) -> dict:
        sd = np.sqrt(np.diag(self.cov))
        out = {f: {"mean": round(float(self.beta[j]), 3), "sd": round(float(sd[j]), 3)} for j, f in enumerate(FEATURES)}
        for c in self.categories:
            j = len(FEATURES) + self.categories.index(c)
            out[f"category: {c}"] = {"mean": round(float(self.beta[j]), 3), "sd": round(float(sd[j]), 3)}
        return out

    def summary(self) -> dict:
        return {"n": self.n, "with_context": self.n_context, "coefficients": self.coefficients(),
                "baseline_p": round(_probit_mean(*self.predict_logit("", self.fill)), 3)}


def _sigmoid(z):
    return 1 / (1 + np.exp(-z)) if isinstance(z, np.ndarray) else 1 / (1 + math.exp(-z))


def _probit_mean(mu, v):
    """E[sigmoid(z)] for z ~ N(mu, v), by the probit approximation (MacKay 1992)."""
    return _sigmoid(mu / np.sqrt(1 + math.pi * np.asarray(v) / 8)) if isinstance(mu, np.ndarray) \
        else _sigmoid(mu / math.sqrt(1 + math.pi * v / 8))
