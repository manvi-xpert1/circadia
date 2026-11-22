"""Local-search refinement for the hybrid GA (memetic step).

The GA's decoder is greedy: every task snaps to the free gap nearest its hint, in
chromosome order. That reaches good regions quickly but rarely makes the small,
exact moves that finish a plan off: nudging a block 15 minutes into a better-fit
slot, swapping two blocks, pulling a task to another day, or dropping a block
that overloads a day. This module makes those moves directly on the decoded plan.

Search: best-improvement hill climbing over five neighbourhoods
  RELOCATE  a scheduled block to a nearby start (+-1, 2, 4 slots) or to the
            earliest / best-energy-fit start on any day
  INSERT    an unscheduled task at the earliest / best-fit start on any day
  REMOVE    a scheduled block (only if nothing scheduled depends on it)
  SWAP      the starts of two scheduled blocks
  MAKE ROOM insert an unscheduled task where one or two blocks already sit, and move
            those blocks to their nearest other legal start (an ejection chain of
            depth one). Hill climbing cannot find this as two single moves, because
            the first one alone (moving a block out of the way) scores worse. It is
            what lets a stability-aware replan fit an urgent task in by nudging one
            block, instead of leaving the urgent task out.
  repeated until a full pass finds no improving move, or the evaluation or time
  budget runs out.

Every candidate is checked against the grid before it is scored: inside one free
gap of one day, at or after the release time and the prerequisite's end, ending
by the deadline, and not starting before any scheduled dependent's prerequisite
ends. So, like the decoder, local search can only ever produce legal plans, and the
independent hard-rule engine still re-checks the result in ``pipeline.verify``.

The score is the same ``fitness.evaluate`` the GA uses, so a refined plan is
never worse than the plan it started from (ties keep the original).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..problem import Problem
from .decoder import BLOCKED, DEPENDENCY, LEFT_OUT, NO_ROOM, Decoded
from .fitness import Score, evaluate


@dataclass
class LSConfig:
    max_evaluations: int = 4000
    max_seconds: float = 1.0
    swap_sample: int = 60  # random pairs tried per pass in the SWAP neighbourhood
    near_steps: tuple[int, ...] = (1, 2, 4)
    seed: int = 0
    min_gain: float = 1e-7


@dataclass
class LSStats:
    passes: int = 0
    evaluations: int = 0
    moves: dict[str, int] | None = None
    start_score: float = 0.0
    end_score: float = 0.0
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "passes": self.passes,
            "evaluations": self.evaluations,
            "moves": self.moves or {},
            "start_score": round(self.start_score, 5),
            "end_score": round(self.end_score, 5),
            "gain": round(self.end_score - self.start_score, 5),
            "seconds": round(self.seconds, 3),
        }


class Grid:
    """Legality checks for single-block moves on the 15-minute grid."""

    def __init__(self, p: Problem, lengths: list[int]):
        self.p = p
        self.lengths = lengths
        self.free = np.zeros(p.G, dtype=bool)
        for a, b in p.intervals:
            self.free[a:b] = True
        n = len(p.tasks)
        self.dependents: list[list[int]] = [[] for _ in range(n)]
        for ti in p.tasks:
            if ti.dep_idx is not None:
                self.dependents[ti.dep_idx].append(ti.idx)
        # Start-of-block offset within the day, for the "same day" check.
        self.in_day = np.arange(p.G) % p.npd

    def occupancy(self, starts: list[int], skip: tuple[int, ...] = ()) -> np.ndarray:
        occ = np.zeros(self.p.G, dtype=bool)
        for i, s in enumerate(starts):
            if s >= 0 and i not in skip:
                occ[s : s + self.lengths[i]] = True
        return occ

    def legal_starts(self, i: int, starts: list[int], occ: np.ndarray) -> np.ndarray:
        """All legal start slots for task i, given the other blocks in ``occ``."""
        p, ti, L = self.p, self.p.tasks[i], self.lengths[i]
        if ti.blocked_reason:
            return np.empty(0, dtype=np.int64)
        lo = ti.dep_earliest
        if ti.dep_idx is not None:
            ds = starts[ti.dep_idx]
            if ds < 0:
                return np.empty(0, dtype=np.int64)
            lo = max(lo, ds + self.lengths[ti.dep_idx])
        hi = min(p.G, ti.dl_end) - L  # last allowed start
        for j in self.dependents[i]:  # a scheduled dependent must still start after this block ends
            if starts[j] >= 0:
                hi = min(hi, starts[j] - L)
        if hi < lo:
            return np.empty(0, dtype=np.int64)
        avail = self.free & ~occ
        c = np.concatenate([[0], np.cumsum(avail)])
        cand = np.arange(lo, hi + 1)
        ok = (c[cand + L] - c[cand] == L) & (self.in_day[cand] + L <= p.npd)
        return cand[ok]


def _per_day_picks(p: Problem, i: int, L: int, legal: np.ndarray) -> list[int]:
    """Earliest and best-energy-fit legal start on each day."""
    out: list[int] = []
    if legal.size == 0:
        return out
    days = legal // p.npd
    fits = (p.Ucs[i, legal + L] - p.Ucs[i, legal]) / L
    for d in np.unique(days):
        sel = days == d
        out.append(int(legal[sel][0]))
        out.append(int(legal[sel][int(np.argmax(fits[sel]))]))
    return out


def _nearest(legal: np.ndarray, target: int) -> int | None:
    if legal.size == 0:
        return None
    k = int(np.searchsorted(legal, target))
    best = None
    for j in (k - 1, k):
        if 0 <= j < legal.size and (best is None or abs(int(legal[j]) - target) < abs(best - target)):
            best = int(legal[j])
    return best


def unscheduled_reasons(p: Problem, starts: list[int], lengths: list[int]) -> dict[int, str]:
    """Reason codes for every unscheduled task, matching the decoder's codes."""
    grid = Grid(p, lengths)
    occ = grid.occupancy(starts)
    out: dict[int, str] = {}
    for i, s in enumerate(starts):
        if s >= 0:
            continue
        ti = p.tasks[i]
        if ti.blocked_reason:
            out[i] = BLOCKED
        elif ti.dep_idx is not None and starts[ti.dep_idx] < 0:
            out[i] = DEPENDENCY
        elif grid.legal_starts(i, starts, occ).size:
            out[i] = LEFT_OUT
        else:
            out[i] = NO_ROOM
    return out


def chromosome_for(p: Problem, starts: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """A chromosome that decodes back to exactly these starts.

    Placing tasks in start order with hint = start always finds the hinted slot free
    and legal, so the decoder reproduces the plan. Unscheduled tasks get hint -1.
    The explainer uses this to run its counterfactuals on refined plans.
    """
    n = len(starts)
    order = np.array(sorted(range(n), key=lambda i: (starts[i] < 0, starts[i], i)), dtype=np.int64)
    hints = np.array([s if s >= 0 else -1 for s in starts], dtype=np.int64)
    return order, hints


def local_search(
    p: Problem, decoded: Decoded, preset: str = "balanced", config: LSConfig | None = None
) -> tuple[Decoded, Score, LSStats]:
    cfg = config or LSConfig()
    rng = np.random.default_rng(cfg.seed)
    t0 = time.perf_counter()
    lengths = list(decoded.lengths)
    starts = list(decoded.starts)
    grid = Grid(p, lengths)
    n = len(starts)
    stats = LSStats(moves={"relocate": 0, "insert": 0, "remove": 0, "swap": 0, "make_room": 0})
    cur = evaluate(p, starts, lengths, preset)
    stats.start_score = cur.total
    evals = 0

    def out_of_budget() -> bool:
        return evals >= cfg.max_evaluations or time.perf_counter() - t0 >= cfg.max_seconds

    def score(cand: list[int]) -> Score:
        nonlocal evals
        evals += 1
        return evaluate(p, cand, lengths, preset)

    improved = True
    while improved and not out_of_budget() and n:
        improved = False
        stats.passes += 1
        for i in rng.permutation(n).tolist():
            if out_of_budget():
                break
            s0 = starts[i]
            occ = grid.occupancy(starts, skip=(i,))
            legal = grid.legal_starts(i, starts, occ)
            cands: set[int] = set(_per_day_picks(p, i, lengths[i], legal))
            if s0 >= 0:
                for step in cfg.near_steps:
                    for t in (s0 - step, s0 + step):
                        x = _nearest(legal, t)
                        if x is not None:
                            cands.add(x)
                if not any(starts[j] >= 0 for j in grid.dependents[i]):
                    cands.add(-1)  # REMOVE
            cands.discard(s0)
            best_s, best = None, cur
            for c in sorted(cands):
                trial = list(starts)
                trial[i] = c
                sc = score(trial)
                if sc.total > best.total + cfg.min_gain:
                    best_s, best = c, sc
            if best_s is not None:
                kind = "remove" if best_s < 0 else ("insert" if s0 < 0 else "relocate")
                stats.moves[kind] += 1
                starts[i] = best_s
                cur = best
                improved = True

        # MAKE ROOM: place an unscheduled task over one or two blocks and re-seat them nearby.
        for i in rng.permutation(n).tolist():
            if out_of_budget():
                break
            if starts[i] >= 0:
                continue
            trial_cur, gain = _make_room(p, grid, starts, i, cfg, score)
            if trial_cur is not None and gain.total > cur.total + cfg.min_gain:
                starts, cur = trial_cur, gain
                stats.moves["make_room"] += 1
                improved = True

        # SWAP: exchange the starts of two scheduled blocks.
        sched = [i for i, s in enumerate(starts) if s >= 0]
        if len(sched) >= 2:
            pairs = [(a, b) for k, a in enumerate(sched) for b in sched[k + 1 :]]
            pick = rng.permutation(len(pairs))[: cfg.swap_sample]
            for k in pick.tolist():
                if out_of_budget():
                    break
                a, b = pairs[k]
                sa, sb = starts[a], starts[b]
                if sa < 0 or sb < 0 or sa == sb:
                    continue
                trial = list(starts)
                trial[a], trial[b] = sb, sa
                occ = grid.occupancy(trial, skip=(a, b))
                la = grid.legal_starts(a, trial, occ | _mask(p.G, sa, lengths[b]))
                if sb not in set(la.tolist()):
                    continue
                occ_b = occ | _mask(p.G, sb, lengths[a])
                lb = grid.legal_starts(b, trial, occ_b)
                if sa not in set(lb.tolist()):
                    continue
                sc = score(trial)
                if sc.total > cur.total + cfg.min_gain:
                    starts = trial
                    cur = sc
                    stats.moves["swap"] += 1
                    improved = True

    stats.evaluations = evals
    stats.end_score = cur.total
    stats.seconds = time.perf_counter() - t0
    dec = Decoded(starts, lengths, unscheduled_reasons(p, starts, lengths))
    return dec, cur, stats


def _make_room(p: Problem, grid: Grid, starts: list[int], i: int, cfg: LSConfig, score):
    """Best plan found by inserting task i over at most two blocks and re-seating them; (None, None) if none."""
    L = grid.lengths[i]
    static = grid.legal_starts(i, starts, np.zeros(p.G, dtype=bool))
    if static.size == 0:
        return None, None
    best_plan, best = None, None
    for s0 in sorted(set(_per_day_picks(p, i, L, static))):
        conflicts = [j for j, sj in enumerate(starts) if sj >= 0 and sj < s0 + L and s0 < sj + grid.lengths[j]]
        if not conflicts or len(conflicts) > 2:
            continue
        trial = list(starts)
        for j in conflicts:
            trial[j] = -1
        trial[i] = s0
        ok = True
        for j in conflicts:
            occ = grid.occupancy(trial, skip=(j,))
            legal = grid.legal_starts(j, trial, occ)
            x = _nearest(legal, starts[j])
            if x is None:
                if any(trial[k] >= 0 for k in grid.dependents[j]):
                    ok = False  # can't drop a prerequisite of a scheduled task
                    break
                continue  # dropped
            trial[j] = x
        if not ok:
            continue
        # Re-check the inserted task against the final arrangement (prerequisites may have moved).
        occ = grid.occupancy(trial, skip=(i,))
        if s0 not in set(grid.legal_starts(i, trial, occ).tolist()):
            continue
        sc = score(trial)
        if best is None or sc.total > best.total:
            best_plan, best = trial, sc
    return best_plan, best


def _mask(G: int, s: int, L: int) -> np.ndarray:
    m = np.zeros(G, dtype=bool)
    m[s : s + L] = True
    return m
