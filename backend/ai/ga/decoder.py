"""Decoder: turns a chromosome into a legal plan (design section 3.3d).

Chromosome = (order, hints):
  order  - a permutation of task indices: who gets placed first
  hints  - a preferred start slot per task, or -1 for "not in this horizon"

For each task in order, the decoder picks the free gap that is long enough,
respects the deadline and prerequisites, and whose start is nearest the hint.
This greedy "nearest legal gap" step is a simple heuristic search, and because
it only ever uses free time, every decoded plan obeys the hard rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..problem import Problem

# Reason codes for tasks that end up unscheduled.
LEFT_OUT = "LEFT_OUT"
NO_ROOM = "NO_ROOM"
DEPENDENCY = "DEPENDENCY"
BLOCKED = "BLOCKED"


@dataclass
class Decoded:
    starts: list[int]  # start slot per task index, -1 when unscheduled
    lengths: list[int]
    reasons: dict[int, str] = field(default_factory=dict)


def dependency_order(p: Problem, order) -> list[int]:
    """Repair the order so every task comes after the task it depends on."""
    out: list[int] = []
    seen: set[int] = set()

    def visit(i: int, stack: set[int]):
        if i in seen or i in stack:
            return
        dep = p.tasks[i].dep_idx
        if dep is not None:
            visit(dep, stack | {i})
        seen.add(i)
        out.append(i)

    for i in order:
        visit(int(i), set())
    return out


def decode(p: Problem, order, hints, use_estimates: bool = False) -> Decoded:
    n = len(p.tasks)
    lengths = [ti.slots_est if use_estimates else ti.slots_p80 for ti in p.tasks]
    starts = [-1] * n
    reasons: dict[int, str] = {}
    free = list(p.intervals)

    for i in dependency_order(p, order):
        ti = p.tasks[i]
        # A task blocked only because its P80 length does not fit is still tried
        # by the estimate-based baseline, which plans with the user's own estimate.
        if ti.blocked_reason and not (use_estimates and ti.blocked_by_room):
            reasons[i] = BLOCKED
            continue
        h = int(hints[i])
        if h < 0:
            reasons[i] = LEFT_OUT
            continue
        earliest = ti.dep_earliest
        if ti.dep_idx is not None:
            ds = starts[ti.dep_idx]
            if ds < 0:
                reasons[i] = DEPENDENCY
                continue
            earliest = max(earliest, ds + lengths[ti.dep_idx])
        L = lengths[i]
        best_k, best_s, best_d = -1, -1, None
        for k, (a, b) in enumerate(free):
            lo = max(a, earliest)
            hi = min(b, ti.dl_end) - L
            if hi < lo:
                continue
            s = min(max(h, lo), hi)
            dist = abs(s - h)
            if best_d is None or dist < best_d:
                best_k, best_s, best_d = k, s, dist
        if best_k < 0:
            reasons[i] = NO_ROOM
            continue
        a, b = free[best_k]
        pieces = [(a, best_s), (best_s + L, b)]
        free[best_k : best_k + 1] = [(x, y) for x, y in pieces if y > x]
        starts[i] = best_s
    return Decoded(starts, lengths, reasons)
