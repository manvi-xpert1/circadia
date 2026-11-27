"""Monte Carlo robustness of a finished plan.

The fitness function scores each block on its own: P(complete) = P(the block happens
at that time) x P(duration <= reserved block). What it cannot see is knock-on delay: when a block
runs long, the next one starts late, may hit a lecture, and the last block of the
day may run out of time. This module replays a plan many times to measure that.

One simulated run, for each day in start order:
  - each planned block happens with the completion model's probability for that
    task at that time (the same number the planner optimised);
  - its real duration is drawn from the same lognormal duration model that set its
    block length: estimate x exp(m + s z);
  - it starts at its planned time or when the previous block ends, whichever is
    later; it waits out a commitment it would start inside, and an overrun that
    reaches a commitment pauses until the commitment ends;
  - work stops at the end of the working day; the rest counts as unfinished.

Avoiding double counting: durations are sampled from the model's own distribution,
not from the reserved length plus extra noise, and block lengths stay as planned.
Draws are truncated at MAX_RATIO x the estimate (an assumption, stated below). Daily
energy is not re-drawn: it already enters through the completion model's context at
planning time, and the planner has no learned link from energy to duration, so a
second energy effect here would be invented rather than estimated. (The evaluation
lab's synthetic users do have one, as part of their hidden truth.)

Common random numbers: every task gets its own random stream, seeded by the run seed
and the task's position, so two candidate plans for the same problem are replayed
against the same "luck" for each task (whether it happens, how long it really takes).
Differences between plans then reflect the plans, not sampling noise, which is what
lets a few dozen runs rank candidates reliably.

Tiers: quick (30 runs), standard (100) and research (300). Adaptive mode starts with
30 runs and adds batches until the standard error of expected completions falls below
a target or the run cap is reached. Every estimate is reported with its standard error.

These are estimates from the planner's own models, not guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from datetime import datetime, timedelta

import numpy as np

from .problem import SLOT, Problem


# Durations are truncated at 4x the user's estimate. With little history the predictive
# distribution is a Student-t on the log scale, whose tails would otherwise produce
# blocks hundreds of hours long and let a handful of runs dominate every average.
MAX_RATIO = 4.0
TIERS = {"quick": 30, "standard": 100, "research": 300}


@dataclass
class MCConfig:
    runs: int = 100
    seed: int = 0
    adaptive: bool = False
    max_runs: int = 300  # adaptive cap
    batch: int = 30  # adaptive step
    target_se: float = 0.1  # adaptive stop: SE of expected completed tasks

    @classmethod
    def tier(cls, name: str, seed: int = 0) -> "MCConfig":
        if name == "adaptive":
            return cls(runs=TIERS["quick"], seed=seed, adaptive=True)
        if name not in TIERS:
            raise ValueError(f"Unknown simulation tier {name!r}; choose one of {', '.join([*TIERS, 'adaptive'])}")
        return cls(runs=TIERS[name], seed=seed)


def task_draws(p: Problem, runs: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-task random numbers shared by every plan of this problem (common random numbers).

    u[r, i] decides whether task i happens in run r; z[r, i] is its standardised duration
    noise. Run r of task i is the same whatever plan, slot or run count is used.
    """
    n = len(p.tasks)
    u = np.empty((runs, n))
    z = np.empty((runs, n))
    for i, ti in enumerate(p.tasks):
        u[:, i] = np.random.default_rng([seed, i, 0]).random(runs)
        z[:, i] = ti.dur.sample_z(np.random.default_rng([seed, i, 1]), runs)
    return u, z


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


def replay(p: Problem, starts: list[int], u: np.ndarray, z: np.ndarray) -> dict[str, np.ndarray]:
    """Replay a plan once per row of the draws; returns per-run outcome arrays."""
    R = u.shape[0]
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
            happens = u[:, i] < p.U[i, s]
            dur = ti.est * np.minimum(np.exp(ti.dur.m + ti.dur.s * z[:, i]), MAX_RATIO)
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

    return {"done": done, "on_time": on_time, "unfinished": unfinished, "worked": worked, "overrun_day": overrun_day}


def _se(x: np.ndarray) -> float:
    return float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0


def simulate_plan(p: Problem, starts: list[int], config: MCConfig | None = None) -> dict:
    cfg = config or MCConfig()
    t0 = time.perf_counter()
    if cfg.adaptive:
        cap = max(cfg.batch, int(cfg.max_runs))
        u_all, z_all = task_draws(p, cap, cfg.seed)
        R, stopped = min(cfg.batch, cap), "cap"
        while True:
            out = replay(p, starts, u_all[:R], z_all[:R])
            if _se(out["done"].sum(axis=1)) <= cfg.target_se:
                stopped = "target"
                break
            if R >= cap:
                break
            R = min(cap, R + cfg.batch)
    else:
        R, stopped = max(1, int(cfg.runs)), "fixed"
        u, z = task_draws(p, R, cfg.seed)
        out = replay(p, starts, u, z)
    res = summarise(p, starts, out)
    res.update({"runs": R, "seed": cfg.seed, "adaptive": cfg.adaptive, "stopped": stopped,
                "seconds": round(time.perf_counter() - t0, 4)})
    return res


def summarise(p: Problem, starts: list[int], out: dict[str, np.ndarray]) -> dict:
    done, on_time, unfinished, worked, overrun_day = (out[k] for k in ("done", "on_time", "unfinished", "worked", "overrun_day"))
    n = len(p.tasks)
    planned = [i for i in range(n) if starts[i] >= 0]
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
    all_imp = done[:, imp_planned].all(axis=1) if imp_planned else None
    all_dl = on_time[:, due_planned].all(axis=1) if due_planned else None
    safety = on_time[:, due].sum(axis=1) / len(due) if due else None
    return {
        "expected_completed": round(float(completed.mean()), 2),
        "completed_p10": int(np.percentile(completed, 10)),
        "completed_p90": int(np.percentile(completed, 90)),
        "completed_sd": round(float(completed.std()), 2),
        "planned": len(planned),
        "p_all_important_done": round(float(all_imp.mean()), 3) if imp_planned else None,
        "important_planned": len(imp_planned),
        "important_unplanned": len(important) - len(imp_planned),
        "p_all_deadlines_met": round(float(all_dl.mean()), 3) if due_planned else None,
        # Share of all tasks due in the horizon that finish on time; an unplanned due task counts as late.
        "deadline_safety": round(float(safety.mean()), 3) if due else None,
        "expected_unfinished_minutes": round(float(unfinished.mean()), 1),
        "p_overrun_any_day": round(float(overrun_day.any(axis=1).mean()), 3),
        "p_overrun_by_day": [round(float(x), 3) for x in overrun_day.mean(axis=0)],
        "expected_unused_minutes": round(float(max(0.0, free_total - worked.mean())), 1),
        "per_task": per_task,
        "se": {
            "expected_completed": round(_se(completed), 3),
            "p_all_important_done": round(_se(all_imp.astype(float)), 3) if all_imp is not None else None,
            "p_all_deadlines_met": round(_se(all_dl.astype(float)), 3) if all_dl is not None else None,
            "deadline_safety": round(_se(safety), 3) if safety is not None else None,
            "expected_unfinished_minutes": round(_se(unfinished), 1),
        },
        "note": "Estimates from the planner's own duration and completion models, not guarantees.",
    }
