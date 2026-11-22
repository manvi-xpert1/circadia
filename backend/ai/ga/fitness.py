"""Fitness function (design section 3.3d).

F = 0.30 S_pri + 0.20 S_dl + 0.20 S_en + 0.15 S_dur + 0.05 S_pref
    - 0.05 P_over - 0.03 P_cs - 0.02 P_bal          (Balanced preset)

Every term is scaled to 0-1. Hard rules are NOT part of this score: the
decoder only produces legal plans, so no score can buy a rule violation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from ..problem import SLOT, Problem
from ..rules import soft_rules as sr

PRESETS: dict[str, dict[str, float]] = {
    "balanced": {"pri": 0.30, "dl": 0.20, "en": 0.20, "dur": 0.15, "pref": 0.05, "over": 0.05, "cs": 0.03, "bal": 0.02},
    "deadline": {"pri": 0.30, "dl": 0.35, "en": 0.10, "dur": 0.15, "pref": 0.05, "over": 0.05, "cs": 0.03, "bal": 0.02},
    "gentle": {"pri": 0.20, "dl": 0.20, "en": 0.20, "dur": 0.15, "pref": 0.05, "over": 0.15, "cs": 0.03, "bal": 0.02},
}
PRESET_LABELS = {"balanced": "Balanced", "deadline": "Deadline-first", "gentle": "Gentle"}
DAY_DISCOUNT = 0.9  # a task placed on day k counts 0.9^k toward S_pri
OVERLOAD_AT = 0.85
STRESS_OVERLOAD_AT = 0.70
BALANCE_FLOOR = 0.60  # below this load a day is never "too busy" for the balance term
STABILITY_SCALE = 0.40  # fitness weight of the stability penalty at stability = 1
MOVE_BASE = 0.25  # cost of moving a block at all, as a share of the cost of dropping it


def move_cost(prev: int, new: int, npd: int) -> float:
    """Cost of one previously planned block: 0 kept, 0.25-1 moved (more for further), 1 dropped."""
    if new < 0:
        return 1.0
    if new == prev:
        return 0.0
    return MOVE_BASE + (1 - MOVE_BASE) * min(1.0, abs(new - prev) / npd)


def stability_penalty(p: Problem, starts: list[int]) -> float:
    """Weighted mean move cost over tasks that were in the previous plan (0 when there was none)."""
    num = den = 0.0
    for i, prev in enumerate(p.prev_slot):
        if prev is None:
            continue
        w = p.tasks[i].task.weight
        num += w * move_cost(prev, starts[i], p.npd)
        den += w
    return num / den if den else 0.0


def weights_for(p: Problem, preset: str) -> dict[str, float]:
    """The preset's weights, plus the stability weight when replanning against a previous plan."""
    w = dict(PRESETS[preset])
    if p.has_previous and p.stability > 0:
        w["stab"] = round(STABILITY_SCALE * p.stability, 4)
    return w


@dataclass
class Score:
    total: float
    parts: dict[str, float]


def on_time_table(p: Problem) -> np.ndarray:
    """P(finishes before deadline) for every task and start slot, computed once."""
    cached = getattr(p, "_on_time", None)
    if cached is not None:
        return cached
    n = len(p.tasks)
    table = np.ones((n, p.G))
    starts = np.array([(p.slot_dt(g) - p.req.now).total_seconds() / 60 for g in range(p.G)])
    for ti in p.tasks:
        if ti.task.deadline is None:
            continue
        to_deadline = (ti.task.deadline - p.req.now).total_seconds() / 60 - starts
        mins = np.maximum(to_deadline, 1e-6)
        z = (np.log(mins / ti.est) - ti.dur.m) / ti.dur.s
        table[ti.idx] = np.where(to_deadline > 0, ti.dur.cdf_log(z), 0.0)
    p._on_time = table  # type: ignore[attr-defined]
    return table


def grid_blocks(p: Problem, starts: list[int], lengths: list[int]) -> list[sr.GridBlock]:
    blocks = [
        sr.GridBlock(i, s, lengths[i], p.tasks[i].task.category, p.tasks[i].task.mental_demand)
        for i, s in enumerate(starts)
        if s >= 0
    ]
    for fb in p.fixed_blocks:
        blocks.append(sr.GridBlock(-1, fb.start_slot, fb.end_slot - fb.start_slot, fb.task.category, fb.task.mental_demand))
    return blocks


def evaluate(p: Problem, starts: list[int], lengths: list[int], preset: str = "balanced") -> Score:
    w = PRESETS[preset]
    tasks = p.tasks
    if not tasks:
        return Score(0.0, {k: 0.0 for k in ("pri", "dl", "en", "dur", "pref", "over", "cs", "bal")})
    on_time = on_time_table(p)
    weights = [ti.task.weight for ti in tasks]
    w_all = sum(weights) or 1.0
    sched = [i for i, s in enumerate(starts) if s >= 0]
    w_sched = sum(weights[i] for i in sched)

    s_pri = sum(weights[i] * DAY_DISCOUNT ** p.day_of(starts[i]) for i in sched) / w_all
    if sched:
        s_en = sum(weights[i] * p.block_fit(i, starts[i], lengths[i]) for i in sched) / w_sched
        s_dur = sum(weights[i] * tasks[i].p_complete for i in sched) / w_sched
    else:
        s_en = s_dur = 0.0
    due = [ti.idx for ti in tasks if ti.dl_end < p.G]
    if due:
        s_dl = sum(on_time[i, starts[i]] if starts[i] >= 0 else 0.0 for i in due) / len(due)
    else:
        s_dl = 1.0

    blocks = grid_blocks(p, starts, lengths)
    movable = [b for b in blocks if b.key >= 0]
    prefs = p.req.prefs
    flagged = sr.a1_focus_runs(blocks, p.npd, prefs.max_focus_block)
    late_limit = int(
        ((prefs.no_work_after.hour * 60 + prefs.no_work_after.minute) - (prefs.day_start.hour * 60 + prefs.day_start.minute))
        // SLOT
    )
    flagged |= sr.a7_late(movable, p.npd, late_limit)
    s_pref = 1.0 - (sum(1 for b in movable if b.start in flagged) / len(movable) if movable else 0.0)

    _, loads = sr.day_loads(blocks, p.npd, p.horizon, p.day_free_minutes)
    over = 0.0
    for d, load in enumerate(loads):
        th = STRESS_OVERLOAD_AT if (d == 0 and p.stress_cap_day0()) else OVERLOAD_AT
        over = max(over, max(0.0, load - th) / (1 - th))
    p_over = min(1.0, over)

    switches, heavy = sr.a6_and_switches(blocks, p.npd)
    p_cs = min(1.0, (switches + heavy) / max(1, len(blocks) - 1))

    # Day balance (A8): only a genuinely busy day is penalised. A day counts as too busy
    # when it is above BALANCE_FLOOR load and above the horizon's average; light days are
    # never pushed apart, so work that comfortably fits today stays today.
    active = [l for l, f in zip(loads, p.day_free_minutes) if f > 0]
    if len(active) >= 2:
        threshold = max(BALANCE_FLOOR, sum(active) / len(active))
        p_bal = min(1.0, max(max(0.0, l - threshold) for l in active) / (1 - BALANCE_FLOOR))
    else:
        p_bal = 0.0

    parts = {"pri": s_pri, "dl": s_dl, "en": s_en, "dur": s_dur, "pref": s_pref, "over": p_over, "cs": p_cs, "bal": p_bal}
    total = (
        w["pri"] * s_pri + w["dl"] * s_dl + w["en"] * s_en + w["dur"] * s_dur + w["pref"] * s_pref
        - w["over"] * p_over - w["cs"] * p_cs - w["bal"] * p_bal
    )
    if p.has_previous and p.stability > 0:
        p_stab = stability_penalty(p, starts)
        parts["stab"] = p_stab
        total -= STABILITY_SCALE * p.stability * p_stab
    return Score(float(total), {k: round(float(v), 4) for k, v in parts.items()})
