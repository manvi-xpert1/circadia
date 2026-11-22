"""Duration prediction (design section 3.3b, extended with a hierarchical model).

Real duration = estimate x overrun ratio r, and ln r is modelled as normal.

Version "v1" (the original model)
---------------------------------
Each category is learned on its own once it has MIN_CATEGORY_N outcomes; until
then it borrows the pooled estimate. The default guess counts as PRIOR_WEIGHT past
tasks:

    m   = (k0 * ln 1.15 + sum ln r_i) / (k0 + n)
    s^2 = (k0 * 0.30^2 + sum (ln r_i - mean)^2) / (k0 + n - 1)

This is the posterior mean of a conjugate normal model with prior strength k0.
P80 = estimate x exp(m + z80 s).

Version "v2" (hierarchical, empirical Bayes)
--------------------------------------------
Three changes, each aimed at a weakness of v1:

1. Partial pooling instead of a hard switch. v1 jumps from the pooled estimate to
   the category's own data at exactly 3 outcomes, and the category's prior is the
   population default (ln 1.15), not what this user is like. v2 is a two-level
   model: the user's overall pace is learned from all their outcomes (with the
   ln 1.15 / 0.30 default as its prior), and each category is shrunk toward the
   user's pace with strength kappa = s^2 / tau^2, where tau^2 is the between-
   category variance estimated from the data (method of moments, floored at
   TAU_MIN). Categories that really differ get little shrinkage; similar ones
   share strength. Few outcomes -> close to the user's pace; many -> the
   category's own data.

2. Predictive uncertainty. v1's P80 uses the fitted spread only, as if m were
   known exactly. With few outcomes it is not, so v2 uses the posterior
   predictive: a Student-t with df = nu + n - 1 and scale s * sqrt(1 + 1/(kappa + n)).
   This widens P80 when data are scarce and converges to v1's formula as n grows.

3. Robustness to one-off outliers. Each log ratio is winsorised at the user's
   median +- 3 robust standard deviations (MAD-based, at least 0.15) before
   fitting, so a single "forgot to stop the timer" record cannot drag a category.

Assumptions: ratios are lognormal and stable over time (no recency weighting);
categories are exchangeable a priori; outcomes are independent. Which version is
the default is decided by the calibration study in ai.evaluation.calibration.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from scipy.stats import norm, t as student_t

from ..types import Outcome

PRIOR_RATIO = 1.15
PRIOR_M = math.log(PRIOR_RATIO)
PRIOR_S = 0.30
PRIOR_WEIGHT = 3
MIN_CATEGORY_N = 3  # v1: below this a category borrows the pooled estimate
Z80 = float(norm.ppf(0.80))  # 0.8416

TAU_MIN = 0.05  # v2: smallest between-category spread of ln r assumed
KAPPA_RANGE = (0.5, 20.0)  # v2: limits on how many "virtual outcomes" the user's pace is worth
WINSOR_K = 3.0
DEFAULT_VERSION = "v2"


@dataclass
class DurationEstimate:
    m: float
    s: float
    n: int
    source: str  # "default", "pooled", "learned" (v1) or "default", "shrunk", "learned" (v2)
    df: float | None = None  # Student-t degrees of freedom for the predictive (v2); None = normal

    @property
    def ratio(self) -> float:
        return math.exp(self.m)

    def _q(self, p: float) -> float:
        return float(student_t.ppf(p, self.df)) if self.df else float(norm.ppf(p))

    def cdf_log(self, z):
        """CDF of the standardised log ratio (works on numpy arrays too)."""
        return student_t.cdf(z, self.df) if self.df else norm.cdf(z)

    def median(self, est: float) -> float:
        return est * math.exp(self.m)

    def quantile(self, est: float, p: float) -> float:
        return est * math.exp(self.m + self._q(p) * self.s)

    def p80(self, est: float) -> float:
        if self.df is None:
            return est * math.exp(self.m + Z80 * self.s)
        return self.quantile(est, 0.80)

    def p_fits(self, minutes: float, est: float) -> float:
        """Probability the task finishes within `minutes`."""
        if minutes <= 0:
            return 0.0
        return float(self.cdf_log((math.log(minutes / est) - self.m) / self.s))

    def log_density(self, actual: float, est: float) -> float:
        """Predictive log density of ln(actual / est): a proper scoring rule for calibration studies."""
        z = (math.log(actual / est) - self.m) / self.s
        if self.df:
            return float(student_t.logpdf(z, self.df)) - math.log(self.s)
        return float(norm.logpdf(z)) - math.log(self.s)

    def sample_z(self, rng, size):
        return rng.standard_t(self.df, size) if self.df else rng.standard_normal(size)

    def as_dict(self) -> dict:
        out = {"ratio": round(self.ratio, 3), "spread": round(self.s, 3), "n": self.n, "source": self.source}
        if self.df:
            out["df"] = round(self.df, 1)
        return out


def fit(log_ratios: list[float], source: str) -> DurationEstimate:
    """v1 fit: conjugate normal with the population default as prior."""
    n = len(log_ratios)
    if n == 0:
        return DurationEstimate(PRIOR_M, PRIOR_S, 0, "default")
    mean = sum(log_ratios) / n
    m = (PRIOR_WEIGHT * PRIOR_M + sum(log_ratios)) / (PRIOR_WEIGHT + n)
    ss = sum((x - mean) ** 2 for x in log_ratios)
    s2 = (PRIOR_WEIGHT * PRIOR_S**2 + ss) / (PRIOR_WEIGHT + n - 1)
    return DurationEstimate(m, math.sqrt(s2), n, source)


def _posterior(xs: list[float], m0: float, s0: float, kappa: float, nu: float) -> tuple[float, float, float, float]:
    """Normal / scaled-inverse-chi-square update. Returns (mean, spread, kappa_n, nu_n)."""
    n = len(xs)
    if n == 0:
        return m0, s0, kappa, nu
    xbar = sum(xs) / n
    ss = sum((x - xbar) ** 2 for x in xs)
    kn = kappa + n
    mn = (kappa * m0 + n * xbar) / kn
    nun = nu + n
    s2 = (nu * s0**2 + ss + kappa * n / kn * (xbar - m0) ** 2) / nun
    return mn, math.sqrt(s2), kn, nun


def _predictive(m: float, s: float, kn: float, nun: float, n: int, source: str) -> DurationEstimate:
    scale = s * math.sqrt(1 + 1 / kn)
    return DurationEstimate(m, scale, n, source, df=max(2.0, nun))


class DurationModel:
    """Per-category duration estimates. ``version`` selects the original ("v1") or hierarchical ("v2") model."""

    def __init__(self, outcomes: list[Outcome], version: str | None = None):
        self.version = version or DEFAULT_VERSION
        self.by_cat: dict[str, list[float]] = {}
        for o in outcomes:
            if o.status == "done" and o.actual_minutes and o.est_minutes > 0:
                r = o.actual_minutes / o.est_minutes
                r = min(max(r, 0.2), 5.0)  # guard against typos such as 600 for 60
                self.by_cat.setdefault(o.category, []).append(math.log(r))
        pooled = [x for xs in self.by_cat.values() for x in xs]
        if self.version == "v1":
            self.pooled = fit(pooled, "pooled") if len(pooled) >= MIN_CATEGORY_N else fit([], "default")
            return
        self._fit_v2(pooled)

    # ---- v2 -------------------------------------------------------------------
    def _fit_v2(self, pooled: list[float]) -> None:
        if len(pooled) >= 3:
            med = statistics.median(pooled)
            mad = statistics.median(abs(x - med) for x in pooled) * 1.4826
            lim = WINSOR_K * max(0.15, mad)
            self.clean = {c: [min(max(x, med - lim), med + lim) for x in xs] for c, xs in self.by_cat.items()}
        else:
            self.clean = dict(self.by_cat)
        allx = [x for xs in self.clean.values() for x in xs]
        # Level 1: the user's overall pace, with the population default as prior.
        self.user = _posterior(allx, PRIOR_M, PRIOR_S, PRIOR_WEIGHT, PRIOR_WEIGHT)
        mu, su = self.user[0], self.user[1]
        # Between-category spread tau^2 (method of moments on category means).
        means = [(sum(xs) / len(xs), len(xs)) for xs in self.clean.values() if xs]
        if len(means) >= 2:
            grand = sum(m for m, _ in means) / len(means)
            between = sum((m - grand) ** 2 for m, _ in means) / (len(means) - 1)
            noise = sum(su**2 / k for _, k in means) / len(means)
            tau2 = max(TAU_MIN**2, between - noise)
        else:
            tau2 = max(TAU_MIN**2, (PRIOR_S / 2) ** 2)  # one category: assume moderate differences
        self.tau = math.sqrt(tau2)
        self.kappa = min(max(su**2 / tau2, KAPPA_RANGE[0]), KAPPA_RANGE[1])
        n_all = len(allx)
        src = "default" if n_all == 0 else "pooled"
        self.pooled = _predictive(mu, su, self.user[2], self.user[3], n_all, src)

    def for_category(self, category: str) -> DurationEstimate:
        if self.version == "v1":
            xs = self.by_cat.get(category, [])
            if len(xs) >= MIN_CATEGORY_N:
                return fit(xs, "learned")
            return self.pooled
        xs = self.clean.get(category, [])
        if not xs:
            return self.pooled
        mu, su, _, nu_u = self.user
        # Level 2: shrink the category toward the user's pace. The spread prior is the user's
        # spread, worth as many outcomes as the user's estimate is (capped at the prior weight).
        m, s, kn, nun = _posterior(xs, mu, su, self.kappa, min(nu_u, PRIOR_WEIGHT + 2))
        source = "learned" if len(xs) >= self.kappa else "shrunk"
        return _predictive(m, s, kn, nun, len(xs), source)

    def summary(self) -> dict:
        cats = {c: {**self.for_category(c).as_dict(), "own_n": len(self.by_cat[c])} for c in sorted(self.by_cat)}
        out = {"categories": cats, "pooled": self.pooled.as_dict(), "version": self.version}
        if self.version == "v2":
            out["between_category_spread"] = round(self.tau, 3)
            out["shrinkage_strength"] = round(self.kappa, 2)
        return out
