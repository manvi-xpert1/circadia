"""Monte Carlo robustness of a finished plan.

The fitness function scores each block on its own: P(complete) = follow-through x
P(duration <= reserved P80 block). What it cannot see is knock-on delay: when a block
runs long, the next one starts late, may hit a lecture, and the last block of the
day may run out of time. This module replays a plan many times to measure that.

One simulated run, for each day in start order:
  - each planned block happens with probability = its category's follow-through
    (the same Beta mean the planner uses);
  - its real duration is drawn from the same lognormal duration model that set its
    P80 length: estimate x exp(m + s z);
  - it starts at its planned time or when the previous block ends, whichever is
    later; it waits out a commitment it would start inside, and an overrun that
    reaches a commitment pauses until the commitment ends;
  - work stops at the end of the working day; the rest counts as unfinished.

Avoiding double counting: durations are sampled from the model's own distribution,
not from P80 plus extra noise, and block lengths stay at P80 as planned. Daily energy
is NOT varied: the planner has no learned link from energy to duration or
follow-through, so any such effect here would be invented rather than estimated.
(The evaluation lab's synthetic users do have one, as part of their hidden truth.)

These are estimates from the planner's own models, not guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .problem import SLOT, Problem


@dataclass
class MCConfig:
    runs: int = 300
    seed: int = 0


def _obstacles(p: Problem, day: int) -> list[tuple[float, float]]:
    """Commitments and fixed / locked blocks on one day, in minutes from that day's start."""
    ds = p.day_start_dt[day]
    de = ds + timedelta(minutes=p.npd * SLOT)
    out = []
    spans: list[tuple[datetime, datetime]] = [(c.start, c.end) for c in p.req.commitments]
    spans += [(fb.start, fb.end) for fb in p.fixed_blocks]
    for a, b in spans:
        if b <= ds or a >= de:
            continue
        out.append(((max(a, ds) - ds).total_seconds() / 60, (min(b, de) - ds).total_seconds() / 60))
    return sorted(out)


def simulate_plan(p: Problem, starts: list[int], config: MCConfig | None = None) -> dict:
    cfg = config or MCConfig()
    R = max(1, int(cfg.runs))
    rng = np.random.default_rng(cfg.seed)
    n = len(p.tasks)
    day_len = p.npd * SLOT
    done = np.zeros((R, n), dtype=bool)
    on_time = np.zeros((R, n), dtype=bool)
    unfinished = np.zeros(R)
    worked = np.zeros(R)
    overrun_day = np.zeros((R, p.horizon), dtype=bool)
    planned = [i for i in range(n) if starts[i] >= 0]

    for d in range(p.horizon):
        day_blocks = sorted((starts[i], i) for i in planned if starts[i] // p.npd == d)
        if not day_blocks:
            continue
        obst = _obstacles(p, d)
        cursor = np.zeros(R)
        if d == 0:
            cursor[:] = max(0.0, (p.req.now - p.day_start_dt[0]).total_seconds() / 60)
        for s, i in day_blocks:
            ti = p.tasks[i]
            planned_start = (s - d * p.npd) * SLOT
            happens = rng.random(R) < ti.follow
            dur = ti.est * np.exp(ti.dur.m + ti.dur.s * ti.dur.sample_z(rng, R))
            start = np.maximum(cursor, planned_start)
            for a, b in obst:  # starting inside a commitment means waiting it out
                start = np.where((start >= a) & (start < b), b, start)
            end = start + dur
            for a, b in obst:  # an overrun that reaches a commitment pauses until it ends
                end = np.where((start < a) & (end > a), end + (b - a), end)
            cut = end > day_len
            finished = happens & ~cut
            done[:, i] = finished
            if ti.task.deadline is not None:
                end_dt_min = (ti.task.deadline - p.day_start_dt[d]).total_seconds() / 60
                on_time[:, i] = finished & (end <= end_dt_min)
            got = np.where(happens, np.clip(np.minimum(end, day_len) - start, 0, None), 0.0)
            # Work time excludes paused commitment time inside the block.
            got = np.minimum(got, dur)
            worked += got
            unfinished += np.where(happens, np.where(cut, np.maximum(dur - got, 0), 0.0), dur)
            overrun_day[:, d] |= happens & cut
            cursor = np.where(happens, np.minimum(end, day_len), cursor)

    important = [i for i in range(n) if p.tasks[i].task.priority >= 3]
    imp_planned = [i for i in important if starts[i] >= 0]
    due = [ti.idx for ti in p.tasks if ti.dl_end < p.G and not ti.blocked_reason]
    due_planned = [i for i in due if starts[i] >= 0]
    completed = done.sum(axis=1)
    free_total = sum(sum(b - a for a, b in p.intervals if a // p.npd == d) for d in range(p.horizon)) * SLOT
    per_task = {
        p.tasks[i].task.id: {
            "p_done": round(float(done[:, i].mean()), 3),
            "p_on_time": round(float(on_time[:, i].mean()), 3) if p.tasks[i].task.deadline else None,
        }
        for i in planned
    }
    return {
        "runs": R,
        "seed": cfg.seed,
        "expected_completed": round(float(completed.mean()), 2),
        "completed_p10": int(np.percentile(completed, 10)),
        "completed_p90": int(np.percentile(completed, 90)),
        "completed_sd": round(float(completed.std()), 2),
        "planned": len(planned),
        "p_all_important_done": round(float(done[:, imp_planned].all(axis=1).mean()), 3) if imp_planned else None,
        "important_planned": len(imp_planned),
        "important_unplanned": len(important) - len(imp_planned),
        "p_all_deadlines_met": round(float(on_time[:, due_planned].all(axis=1).mean()), 3) if due_planned else None,
        # Share of all tasks due in the horizon that finish on time; an unplanned due task counts as late.
        "deadline_safety": round(float(on_time[:, due].sum(axis=1).mean() / len(due)), 3) if due else None,
        "expected_unfinished_minutes": round(float(unfinished.mean()), 1),
        "p_overrun_any_day": round(float(overrun_day.any(axis=1).mean()), 3),
        "p_overrun_by_day": [round(float(x), 3) for x in overrun_day.mean(axis=0)],
        "expected_unused_minutes": round(float(max(0.0, free_total - worked.mean())), 1),
        "per_task": per_task,
        "note": "Estimates from the planner's own duration and follow-through models, not guarantees.",
    }
