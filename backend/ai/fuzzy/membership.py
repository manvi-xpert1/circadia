"""Membership functions and the linguistic terms used by the fuzzy engine.

trap(a, b, c, d): 0 below a, rises to 1 at b, stays 1 until c, falls to 0 at d.
A triangle is a trapezoid with b == c. Shoulders use a == b or c == d.
"""
from __future__ import annotations

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


def suitability_label(u: float) -> str:
    """The term with the highest membership, used for badges in the UI."""
    degrees = fuzzify(u, SUITABILITY_TERMS)
    return max(degrees, key=degrees.get)
