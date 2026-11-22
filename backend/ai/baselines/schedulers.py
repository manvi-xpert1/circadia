"""Baseline schedulers for the evaluation ladder (design: Evaluation plan).

All baselines share the rule engine and decoder with the GA, so a comparison
isolates the planning idea being added at each step:

  1. priority_deadline  - sort by priority then deadline, earliest gap, user's own estimates
  2. duration_aware     - same, but with P80 durations from the probability model
  3. fuzzy_greedy       - same order, but each task goes to the legal gap with the best energy fit
  4. (the full GA lives in ai.ga.runner)
"""
from __future__ import annotations

import numpy as np

from ..ga.decoder import Decoded, decode, dependency_order
from ..problem import Problem


def _priority_order(p: Problem) -> np.ndarray:
    n = len(p.tasks)
    return np.array(sorted(range(n), key=lambda i: (-p.tasks[i].task.priority, p.tasks[i].dl_end, i)), dtype=np.int64)


def priority_deadline(p: Problem) -> Decoded:
    n = len(p.tasks)
    return decode(p, _priority_order(p), np.zeros(n, dtype=np.int64), use_estimates=True)


def duration_aware(p: Problem) -> Decoded:
    n = len(p.tasks)
    return decode(p, _priority_order(p), np.zeros(n, dtype=np.int64))


def fuzzy_greedy(p: Problem) -> Decoded:
    """Place each task, in priority order, at the free start with the highest energy fit."""
    n = len(p.tasks)
    lengths = [ti.slots_p80 for ti in p.tasks]
    starts = [-1] * n
    reasons: dict[int, str] = {}
    free = np.zeros(p.G, dtype=bool)
    for a, b in p.intervals:
        free[a:b] = True
    for i in dependency_order(p, _priority_order(p)):
        ti = p.tasks[i]
        if ti.blocked_reason:
            reasons[i] = "BLOCKED"
            continue
        earliest = ti.dep_earliest
        if ti.dep_idx is not None:
            if starts[ti.dep_idx] < 0:
                reasons[i] = "DEPENDENCY"
                continue
            earliest = max(earliest, starts[ti.dep_idx] + lengths[ti.dep_idx])
        L = lengths[i]
        best, best_fit = -1, -1.0
        for g in range(earliest, min(p.G, ti.dl_end) - L + 1):
            if p.day_of(g) != p.day_of(g + L - 1) or not free[g : g + L].all():
                continue
            f = p.block_fit(i, g, L)
            if f > best_fit + 1e-9:
                best, best_fit = g, f
        if best < 0:
            reasons[i] = "NO_ROOM"
            continue
        free[best : best + L] = False
        starts[i] = best
    return Decoded(starts, lengths, reasons)


BASELINES = {
    "priority_deadline": priority_deadline,
    "duration_aware": duration_aware,
    "fuzzy_greedy": fuzzy_greedy,
}
