"""CP-SAT scheduler: an exact-solver baseline for the GA (Google OR-Tools).

Formulation (time-indexed, on the same 15-minute grid as the GA):

  x[i,s] in {0,1}  task i starts at slot s. Only legal starts get a variable:
                   s lies in one free gap of one day, s >= release / fixed-prerequisite
                   time, s + L_i <= deadline slot. This encodes H1, H2, H3, H6, H7,
                   H8 (L_i is the P80 block) and H9 by construction.
  sum_s x[i,s] <= 1                     each task at most once
  sum_{(i,s) covers g} x[i,s] <= 1      no two blocks share a slot (H4)
  y_j <= y_dep ; S_j >= S_dep + L_dep   prerequisites first (H5), enforced when y_j = 1

Objective: the GA's fitness has eight terms. Five are linear in x once the
"weighted average" denominators are fixed (priority coverage, deadline safety,
energy fit, realistic durations, late-work preference), and overload, day balance
and stability are linear with a few auxiliary max() variables. Two are not
modelled: context switching (A6) and focus runs (A1), which depend on which
blocks touch. So CP-SAT optimises a *surrogate* of the fitness. The weighted
averages are handled by a fixed-point loop: solve with the denominators of the
previous solution, recompute them, and solve again (warm-started).

Every solution is then re-scored with the real ``fitness.evaluate`` and re-checked
by the independent hard-rule engine, so the numbers reported for CP-SAT are on
exactly the same scale as the GA's. "OPTIMAL" from the solver means optimal for
the surrogate in that round, not for the full fitness; the report says which.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..baselines.schedulers import duration_aware
from ..ga.decoder import Decoded
from ..ga.fitness import (
    BALANCE_FLOOR, DAY_DISCOUNT, OVERLOAD_AT, PRESETS, STABILITY_SCALE, STRESS_OVERLOAD_AT,
    Score, evaluate, move_cost, on_time_table,
)
from ..ga.local_search import chromosome_for, unscheduled_reasons
from ..ga.runner import GAResult
from ..problem import SLOT, Problem


@dataclass
class CPSATConfig:
    """Solver settings.

    By default the solver is limited by wall-clock time and uses several workers, which
    is what makes it competitive. Such runs can differ slightly between machines and
    runs. ``deterministic=True`` (one worker, or interleaved workers, with a work-unit
    limit) gives identical results on every run, at roughly 3x the wall time for the
    same quality.
    """

    time_limit: float = 10.0  # wall-clock seconds, shared by all rounds
    rounds: int = 2  # fixed-point rounds for the weighted-average denominators
    workers: int = 0  # 0 = one per CPU core, up to 8
    deterministic: bool = False
    deterministic_time: float = 10.0  # solver work units per round when deterministic
    seed: int = 0


@dataclass
class CPSATInfo:
    status: str = "NOT_RUN"
    rounds: list[dict] = field(default_factory=list)
    variables: int = 0
    seconds: float = 0.0
    fallback: bool = False

    def as_dict(self) -> dict:
        return {"status": self.status, "rounds": self.rounds, "variables": self.variables,
                "seconds": round(self.seconds, 3), "fallback": self.fallback}


def candidate_starts(p: Problem, i: int, L: int, free: np.ndarray) -> np.ndarray:
    ti = p.tasks[i]
    if ti.blocked_reason:
        return np.empty(0, dtype=np.int64)
    lo, hi = ti.dep_earliest, min(p.G, ti.dl_end) - L
    if hi < lo:
        return np.empty(0, dtype=np.int64)
    c = np.concatenate([[0], np.cumsum(free)])
    cand = np.arange(lo, hi + 1)
    ok = (c[cand + L] - c[cand] == L) & ((cand % p.npd) + L <= p.npd)
    return cand[ok]


def _late_flags(p: Problem, starts: np.ndarray, L: int) -> np.ndarray:
    prefs = p.req.prefs
    limit = ((prefs.no_work_after.hour * 60 + prefs.no_work_after.minute)
             - (prefs.day_start.hour * 60 + prefs.day_start.minute)) // SLOT
    return ((starts % p.npd) + L) > limit


def _solve_round(p, preset, cand, lengths, W_s, N_s, hint, cfg, budget, info):
    from ortools.sat.python import cp_model

    w = PRESETS[preset]
    n = len(p.tasks)
    weights = [ti.task.weight for ti in p.tasks]
    W_all = sum(weights) or 1.0
    on_time = on_time_table(p)
    due = [ti.idx for ti in p.tasks if ti.dl_end < p.G]
    n_due = len(due)
    due_set = set(due)
    prev_w = sum(weights[i] for i, s in enumerate(p.prev_slot) if s is not None)
    use_stab = p.has_previous and p.stability > 0 and prev_w > 0

    m = cp_model.CpModel()
    x: dict[tuple[int, int], object] = {}
    obj = []
    cover: list[list] = [[] for _ in range(p.G)]
    day_terms: list[list] = [[] for _ in range(p.horizon)]
    y = []
    S = []
    for i in range(n):
        L = lengths[i]
        cs = cand[i]
        late = _late_flags(p, cs, L) if cs.size else np.empty(0, dtype=bool)
        fits = (p.Ucs[i, cs + L] - p.Ucs[i, cs]) / L if cs.size else np.empty(0)
        vars_i = []
        for k, s in enumerate(cs.tolist()):
            v = m.NewBoolVar(f"x_{i}_{s}")
            x[(i, s)] = v
            vars_i.append(v)
            for g in range(s, s + L):
                cover[g].append(v)
            day_terms[s // p.npd].append((v, L * SLOT))
            coef = w["pri"] * weights[i] * DAY_DISCOUNT ** (s // p.npd) / W_all
            coef += w["en"] * weights[i] * fits[k] / W_s
            coef += w["dur"] * weights[i] * p.tasks[i].p_fits / W_s
            coef += w["pref"] * (0.0 if late[k] else 1.0) / N_s
            if i in due_set:
                coef += w["dl"] * float(on_time[i, s]) / n_due
            if use_stab and p.prev_slot[i] is not None:
                # Constant part (everything dropped) is left out; each kept/moved block earns back.
                coef += STABILITY_SCALE * p.stability * weights[i] * (1 - move_cost(p.prev_slot[i], s, p.npd)) / prev_w
            obj.append(coef * v)
        yi = m.NewBoolVar(f"y_{i}")
        if vars_i:
            m.Add(sum(vars_i) == yi)
        else:
            m.Add(yi == 0)
        y.append(yi)
        S.append(sum(s * x[(i, s)] for s in cs.tolist()) if vars_i else 0)
    for g in range(p.G):
        if len(cover[g]) > 1:
            m.AddAtMostOne(cover[g])

    # Neighbouring blocks (A1 focus runs, A6 / context switching). The fitness only counts
    # touching blocks, or blocks one slot apart, on the same day. The surrogate charges each
    # such pair as if it were a category switch, and a touching pair as two focus-run flags.
    # This over-charges same-category neighbours slightly, which only nudges plans toward
    # leaving a short gap, the behaviour the real penalties reward.
    ends: list[list] = [[] for _ in range(p.G + 1)]
    begins: list[list] = [[] for _ in range(p.G + 1)]
    for (i, s0), v in x.items():
        ends[s0 + lengths[i]].append(v)
        begins[s0].append(v)
    n_pairs = max(1, N_s - 1)
    for g in range(1, p.G):
        if not ends[g]:
            continue
        for gap, cost in ((0, w["cs"] / n_pairs + 2 * w["pref"] / N_s), (1, w["cs"] / n_pairs)):
            h = g + gap
            if h >= p.G or not begins[h] or (h // p.npd) != ((g - 1) // p.npd):
                continue
            t = m.NewBoolVar(f"adj_{g}_{gap}")
            m.Add(t >= sum(ends[g]) + sum(begins[h]) - 1)
            obj.append(-cost * t)
    for ti in p.tasks:
        j, d = ti.idx, ti.dep_idx
        if d is None:
            continue
        m.AddImplication(y[j], y[d])
        m.Add(S[j] >= S[d] + lengths[d]).OnlyEnforceIf(y[j])

    # Day loads in per-mille of free minutes (fixed tasks count, as in fitness.day_loads).
    fixed_min = [0] * p.horizon
    for fb in p.fixed_blocks:
        fixed_min[fb.start_slot // p.npd] += (fb.end_slot - fb.start_slot) * SLOT
    loads = []
    for d in range(p.horizon):
        free = p.day_free_minutes[d]
        if free <= 0:
            loads.append(0)
            continue
        lv = m.NewIntVar(0, 2000, f"load_{d}")
        work = sum(v * (mins * 1000) for v, mins in day_terms[d]) + fixed_min[d] * 1000
        # lv = ceil(work / free): two-sided, so the solver can neither shrink nor inflate a day's load.
        m.Add(lv * free >= work)
        m.Add(lv * free <= work + free - 1)
        loads.append(lv)
    if w["over"] > 0:
        over = []
        for d in range(p.horizon):
            th = STRESS_OVERLOAD_AT if (d == 0 and p.stress_cap_day0()) else OVERLOAD_AT
            e = m.NewIntVar(0, 2000, f"ex_{d}")
            m.AddMaxEquality(e, [0, loads[d] - int(round(th * 1000))])
            o = m.NewIntVar(0, 2_000_000, f"ov_{d}")
            m.Add(o * int(round((1 - th) * 1000)) >= e * 1000)
            over.append(o)
        M = m.NewIntVar(0, 2_000_000, "over")
        m.AddMaxEquality(M, over)
        obj.append((-w["over"] / 1000.0) * M)  # o ~ p_over * 1000
    active = [d for d in range(p.horizon) if p.day_free_minutes[d] > 0]
    if w["bal"] > 0 and len(active) >= 2:
        mean = m.NewIntVar(0, 2000, "mean_load")
        m.AddDivisionEquality(mean, sum(loads[d] for d in active), len(active))
        thr = m.NewIntVar(0, 2000, "thr")
        m.AddMaxEquality(thr, [int(BALANCE_FLOOR * 1000), mean])
        exs = []
        for d in active:
            e = m.NewIntVar(0, 2000, f"bx_{d}")
            m.AddMaxEquality(e, [0, loads[d] - thr])
            exs.append(e)
        B = m.NewIntVar(0, 2000, "bal")
        m.AddMaxEquality(B, exs)
        obj.append((-w["bal"] / (1000.0 * (1 - BALANCE_FLOOR))) * B)
    m.Maximize(sum(obj))
    if hint is not None:
        for (i, s), v in x.items():
            m.AddHint(v, 1 if hint[i] == s else 0)

    solver = cp_model.CpSolver()
    prm = solver.parameters
    import os

    prm.num_workers = cfg.workers if cfg.workers > 0 else max(1, min(8, os.cpu_count() or 1))
    prm.random_seed = cfg.seed
    prm.max_time_in_seconds = max(0.05, budget)
    if cfg.deterministic:
        prm.max_deterministic_time = cfg.deterministic_time
        if prm.num_workers > 1:
            prm.interleave_search = True
    status = solver.Solve(m)
    name = solver.StatusName(status)
    info.variables = max(info.variables, len(x))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, name, None, None
    starts = [-1] * n
    for (i, s), v in x.items():
        if solver.Value(v):
            starts[i] = s
    obj_v, bound = solver.ObjectiveValue(), solver.BestObjectiveBound()
    return starts, name, obj_v, bound


def run_cpsat(p: Problem, preset: str = "balanced", seed: int = 0, config: CPSATConfig | None = None,
              warm_start: list[int] | None = None) -> GAResult:
    cfg = config or CPSATConfig(seed=seed)
    t0 = time.perf_counter()
    info = CPSATInfo()
    n = len(p.tasks)
    lengths = [ti.slots_p80 for ti in p.tasks]
    if n == 0:
        dec = Decoded([], [], {})
        return GAResult(np.array([], dtype=np.int64), np.array([], dtype=np.int64), dec, evaluate(p, [], [], preset),
                        optimizer="cpsat", details={"cpsat": {"status": "EMPTY"}})
    free = np.zeros(p.G, dtype=bool)
    for a, b in p.intervals:
        free[a:b] = True
    cand = [candidate_starts(p, i, lengths[i], free) for i in range(n)]

    # Denominators for the weighted averages start from a quick greedy plan.
    start_plan = warm_start if warm_start is not None else duration_aware(p).starts
    weights = [ti.task.weight for ti in p.tasks]
    best_starts = list(start_plan)
    best_score = evaluate(p, best_starts, lengths, preset)
    hint = list(start_plan)
    for r in range(max(1, cfg.rounds)):
        sched = [i for i, s in enumerate(hint) if s >= 0]
        W_s = sum(weights[i] for i in sched) or max(weights) or 1.0
        N_s = max(1, len(sched))
        budget = max(0.05, (cfg.time_limit - (time.perf_counter() - t0)) / (cfg.rounds - r))
        starts, status, obj_v, bound = _solve_round(p, preset, cand, lengths, W_s, N_s, hint, cfg, budget, info)
        rec = {"round": r + 1, "status": status}
        if starts is not None:
            sc = evaluate(p, starts, lengths, preset)
            gap = (bound - obj_v) / max(1e-9, abs(obj_v)) if obj_v else 0.0
            rec.update({"surrogate": round(obj_v, 5), "bound": round(bound, 5), "gap": round(gap, 5),
                        "fitness": round(sc.total, 5)})
            if sc.total > best_score.total + 1e-12:
                best_starts, best_score = starts, sc
            if starts == hint:
                info.rounds.append(rec)
                info.status = status
                break
            hint = starts
        info.rounds.append(rec)
        info.status = status
    if all(r.get("fitness") is None for r in info.rounds):
        info.fallback = True  # no solver solution in time: keep the greedy plan, and say so
    info.seconds = time.perf_counter() - t0
    dec = Decoded(best_starts, lengths, unscheduled_reasons(p, best_starts, lengths))
    order, hints = chromosome_for(p, best_starts)
    return GAResult(order, hints, dec, best_score, [], 0, 0, info.seconds, "cpsat", {"cpsat": info.as_dict()})
