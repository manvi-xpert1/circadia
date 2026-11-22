"""Mamdani fuzzy inference: min for AND, max for aggregation, centroid output.

Two stages (design section 3.3a):
  1. capacity(E, F, S): mental energy, focus and stress -> mental capacity 0-10
  2. suitability(gap_m, gap_p): capacity minus task demand -> fit 0-1

Every call can return a trace (memberships and fired rules) so the
explanation module can show exactly why a score came out the way it did.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from .membership import (
    CAPACITY_TERMS,
    LEVEL_TERMS,
    MENTAL_GAP_TERMS,
    PHYSICAL_GAP_TERMS,
    STRESS_TERMS,
    SUITABILITY_TERMS,
    fuzzify,
    trap,
)

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


@dataclass
class FiredRule:
    rule: str
    strength: float


@dataclass
class FuzzyResult:
    value: float
    fired: list[FiredRule] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)


def _centroid(universe, curves, activation: dict[str, float]) -> float | None:
    aggregated = np.zeros_like(universe)
    for term, strength in activation.items():
        if strength > 0:
            aggregated = np.maximum(aggregated, np.minimum(strength, curves[term]))
    total = aggregated.sum()
    if total == 0:
        return None
    return float((aggregated * universe).sum() / total)


def capacity(energy: float, focus: float, stress: float) -> FuzzyResult:
    """Stage 1: mental capacity (0-10) from mental energy, focus and stress."""
    e = fuzzify(energy, LEVEL_TERMS)
    f = fuzzify(focus, LEVEL_TERMS)
    s = fuzzify(stress, STRESS_TERMS)
    activation = {k: 0.0 for k in CAPACITY_TERMS}
    fired: list[FiredRule] = []
    for (et, ft), out in CAPACITY_RULES.items():
        w = min(e[et], f[ft])
        if w > 0:
            fired.append(FiredRule(f"Energy {et} and Focus {ft} -> Capacity {out}", w))
            activation[out] = max(activation[out], w)
    for et, out in STRESS_RULES.items():
        w = min(s["High"], e[et])
        if w > 0:
            fired.append(FiredRule(f"Stress High and Energy {et} -> Capacity {out}", w))
            activation[out] = max(activation[out], w)
    value = _centroid(CAP_UNIVERSE, _CAP_CURVES, activation)
    if value is None:  # cannot happen with full-coverage terms, kept as a guard
        value = 5.0
    return FuzzyResult(value, fired, {"energy": e, "focus": f, "stress": s})


def suitability(mental_gap: float, physical_gap: float) -> FuzzyResult:
    """Stage 2: how well a task fits a slot (0-1)."""
    m = fuzzify(mental_gap, MENTAL_GAP_TERMS)
    p = fuzzify(physical_gap, PHYSICAL_GAP_TERMS)
    activation = {k: 0.0 for k in SUITABILITY_TERMS}
    fired: list[FiredRule] = []
    for rid, mt, pt, out in SUITABILITY_RULES:
        parts = []
        if mt is not None:
            parts.append(m[mt])
        if pt is not None:
            parts.append(p[pt])
        w = min(parts)
        if w > 0:
            fired.append(FiredRule(rid, w))
            activation[out] = max(activation[out], w)
    value = _centroid(SUIT_UNIVERSE, _SUIT_CURVES, activation)
    no_rule = value is None
    if no_rule:
        value = 0.5
    return FuzzyResult(value, fired, {"mental_gap": m, "physical_gap": p, "no_rule_fired": no_rule})


RULE_TEXT = {
    "S1": "physical energy is below what the task needs",
    "S2": "mental capacity is well below what the task needs",
    "S3": "mental capacity is a little short of the task",
    "S4": "mental capacity matches the task",
    "S5": "mental capacity is well above the task (better saved for harder work)",
}


@lru_cache(maxsize=200_000)
def suitability_value(mental_gap: float, physical_gap: float) -> float:
    """Cached scalar version used to fill the suitability matrix quickly.

    Callers round gaps to 2 decimals, so the cache stays small.
    """
    return suitability(mental_gap, physical_gap).value


@lru_cache(maxsize=50_000)
def capacity_value(energy: float, focus: float, stress: float) -> float:
    return capacity(energy, focus, stress).value
