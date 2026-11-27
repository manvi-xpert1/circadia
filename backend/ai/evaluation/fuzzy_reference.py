"""Reference: the two-stage Mamdani fuzzy suitability score the planner used to rank slots.

Kept only so the evaluation lab can compare it with the completion model that
replaced it (ablation "fuzzy_reference"). The planner itself never imports this.

Stage 1: mental energy, focus and stress -> mental capacity 0-10.
Stage 2: capacity minus task demand (and physical energy minus demand) -> fit 0-1.
Min for AND, max for aggregation, centroid defuzzification.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np


def trap(x, a: float, b: float, c: float, d: float):
    """Trapezoidal membership. Works on a float or a NumPy array."""
    x = np.asarray(x, dtype=float)
    y = np.zeros_like(x)
    y = np.where((x >= b) & (x <= c), 1.0, y)
    if b > a:
        rising = (x > a) & (x < b)
        y = np.where(rising, (x - a) / (b - a), y)
    if d > c:
        falling = (x > c) & (x < d)
        y = np.where(falling, (d - x) / (d - c), y)
    return y if y.ndim else float(y)


def tri(x, a: float, b: float, c: float):
    return trap(x, a, b, b, c)


# ---- Stage 1: mental capacity ----------------------------------------------
LEVEL_TERMS = {  # used for mental energy E and focus F (0-10)
    "Low": (0, 0, 2, 5),
    "Medium": (2, 5, 5, 8),
    "High": (5, 8, 10, 10),
}
STRESS_TERMS = {
    "Low": (0, 0, 2, 5),
    "Moderate": (2, 5, 5, 8),
    "High": (5, 8, 10, 10),
}
CAPACITY_TERMS = {  # output, 0-10
    "Very low": (0, 0, 1, 3),
    "Low": (1, 3, 3, 5),
    "Medium": (3, 5, 5, 7),
    "High": (5, 7, 7, 9),
    "Very high": (7, 9, 10, 10),
}

# ---- Stage 2: suitability ----------------------------------------------------
MENTAL_GAP_TERMS = {  # capacity minus mental demand, -10..10
    "Deficit": (-10, -10, -4, -2),
    "Short": (-4, -2, -2, 0),
    "Match": (-2, 0, 2, 4),
    "Surplus": (2, 5, 10, 10),
}
PHYSICAL_GAP_TERMS = {  # slot physical energy minus physical demand
    "Deficit": (-10, -10, -3, 0),
    "Adequate": (-3, 0, 10, 10),
}
SUITABILITY_TERMS = {  # output, 0-1
    "Poor": (0, 0, 0.15, 0.35),
    "Fair": (0.2, 0.4, 0.4, 0.6),
    "Good": (0.45, 0.65, 0.65, 0.85),
    "Excellent": (0.7, 0.9, 1, 1),
}


def fuzzify(value: float, terms: dict[str, tuple]) -> dict[str, float]:
    """Degree of membership of one crisp value in every term."""
    return {name: float(trap(value, *p)) for name, p in terms.items()}



CAP_UNIVERSE = np.linspace(0, 10, 1001)
SUIT_UNIVERSE = np.linspace(0, 1, 1001)

# Precompute output membership curves once.
_CAP_CURVES = {k: trap(CAP_UNIVERSE, *p) for k, p in CAPACITY_TERMS.items()}
_SUIT_CURVES = {k: trap(SUIT_UNIVERSE, *p) for k, p in SUITABILITY_TERMS.items()}

# Stage 1 rule base: (energy term, focus term) -> capacity term
CAPACITY_RULES = {
    ("Low", "Low"): "Very low",
    ("Low", "Medium"): "Low",
    ("Low", "High"): "Low",
    ("Medium", "Low"): "Low",
    ("Medium", "Medium"): "Medium",
    ("Medium", "High"): "High",
    ("High", "Low"): "Medium",
    ("High", "Medium"): "High",
    ("High", "High"): "Very high",
}
# High stress pulls capacity down one level: energy term -> capacity term
STRESS_RULES = {"High": "Medium", "Medium": "Low", "Low": "Very low"}

# Stage 2 rule base: (id, mental-gap term or None, physical-gap term or None, output)
SUITABILITY_RULES = [
    ("S1", None, "Deficit", "Poor"),
    ("S2", "Deficit", None, "Poor"),
    ("S3", "Short", "Adequate", "Fair"),
    ("S4", "Match", "Adequate", "Excellent"),
    ("S5", "Surplus", "Adequate", "Good"),
]




def _centroid(universe, curves, activation: dict[str, float]) -> float | None:
    aggregated = np.zeros_like(universe)
    for term, strength in activation.items():
        if strength > 0:
            aggregated = np.maximum(aggregated, np.minimum(strength, curves[term]))
    total = aggregated.sum()
    return None if total == 0 else float((aggregated * universe).sum() / total)


def _capacity(energy: float, focus: float, stress: float) -> float:
    e, f, s = fuzzify(energy, LEVEL_TERMS), fuzzify(focus, LEVEL_TERMS), fuzzify(stress, STRESS_TERMS)
    act = {k: 0.0 for k in CAPACITY_TERMS}
    for (et, ft), out in CAPACITY_RULES.items():
        act[out] = max(act[out], min(e[et], f[ft]))
    for et, out in STRESS_RULES.items():
        act[out] = max(act[out], min(s["High"], e[et]))
    v = _centroid(CAP_UNIVERSE, _CAP_CURVES, act)
    return 5.0 if v is None else v


def _suitability(mental_gap: float, physical_gap: float) -> float:
    m, p = fuzzify(mental_gap, MENTAL_GAP_TERMS), fuzzify(physical_gap, PHYSICAL_GAP_TERMS)
    act = {k: 0.0 for k in SUITABILITY_TERMS}
    for _, mt, pt, out in SUITABILITY_RULES:
        parts = ([m[mt]] if mt else []) + ([p[pt]] if pt else [])
        act[out] = max(act[out], min(parts))
    v = _centroid(SUIT_UNIVERSE, _SUIT_CURVES, act)
    return 0.5 if v is None else v


@lru_cache(maxsize=50_000)
def capacity_value(energy: float, focus: float, stress: float) -> float:
    return _capacity(energy, focus, stress)


@lru_cache(maxsize=200_000)
def suitability_value(mental_gap: float, physical_gap: float) -> float:
    return _suitability(mental_gap, physical_gap)


def suitability_matrix(infos, mental: np.ndarray, physical: np.ndarray, focus: np.ndarray, stress: np.ndarray) -> np.ndarray:
    """U[i, g] = fuzzy suitability (0-1, not a probability) of task i in slot g."""
    U = np.zeros((len(infos), len(mental)))
    for g in range(len(mental)):
        c = capacity_value(round(float(mental[g]), 2), round(float(focus[g]), 2), round(float(stress[g]), 2))
        for ti in infos:
            U[ti.idx, g] = suitability_value(round(c - ti.task.mental_demand, 2),
                                             round(float(physical[g]) - ti.task.physical_demand, 2))
    return U
