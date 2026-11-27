"""Choosing the main plan by simulated outcome rather than by fitness alone.

The optimiser maximises a fitness function: a weighted sum of per-block scores. It
cannot see knock-on delay (a long block pushing the next one into a lecture or past
the end of the day). The Monte Carlo replay can. So the pipeline produces a few
candidate plans (the user's preset with two seeds, plus the plans optimised for the
other presets), replays every candidate against the same random draws (common random
numbers), and ranks them by an outcome score:

    value = w_done  x priority-weighted share of tasks completed
          + w_dl    x share of due tasks finished on time
          - w_over  x unfinished work, hours per day
          - w_move  x share of the previous plan's blocks moved or removed (replanning only)

Weights depend on the preset the user picked, so "Deadline-first" still means
deadline-first. Because the draws are shared, the difference between two candidates
is measured per run, and its standard error is small. The fitness-best plan is kept
unless another candidate beats it by more than two standard errors; a plan is never
swapped on noise.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .problem import Problem
from .uncertainty import MCConfig, replay, task_draws

# (w_done, w_dl, w_over, w_move) per preset.
OUTCOME_WEIGHTS = {
    "balanced": (1.0, 1.0, 0.5, 1.0),
    "deadline": (0.7, 2.0, 0.3, 1.0),
    "gentle": (0.8, 0.8, 1.2, 1.0),
}
SWITCH_SE = 2.0  # a candidate must beat the fitness-best plan by this many standard errors


@dataclass
class Candidate:
    label: str  # how it was produced, e.g. "balanced, seed 42"
    starts: list[int]


def outcome_values(p: Problem, starts: list[int], out: dict[str, np.ndarray], preset: str) -> np.ndarray:
    """Per-run outcome score of one plan (higher is better)."""
    wd, wl, wo, wm = OUTCOME_WEIGHTS.get(preset, OUTCOME_WEIGHTS["balanced"])
    live = [ti.idx for ti in p.tasks if not ti.blocked_reason]
    w = np.array([p.tasks[i].task.priority for i in live], dtype=float)
    done_share = (out["done"][:, live] * w).sum(axis=1) / w.sum() if live else np.zeros(out["done"].shape[0])
    due = [ti.idx for ti in p.tasks if ti.dl_end < p.G and not ti.blocked_reason]
    on_time = out["on_time"][:, due].mean(axis=1) if due else np.ones(out["done"].shape[0])
    over_hours = out["unfinished"] / 60 / max(1, p.horizon)
    move = 0.0
    prev = [(i, s) for i, s in enumerate(p.prev_slot) if s is not None]
    if prev and p.stability > 0:
        move = p.stability * sum(1 for i, s in prev if starts[i] != s) / len(prev)
    return wd * done_share + wl * on_time - wo * over_hours - wm * move


def select(p: Problem, candidates: list[Candidate], preset: str, mc: MCConfig) -> tuple[int, dict]:
    """Index of the chosen candidate (0 is the fitness-best) and a report of the comparison."""
    runs = max(2, mc.runs if not mc.adaptive else mc.max_runs)
    u, z = task_draws(p, runs, mc.seed)
    values = [outcome_values(p, c.starts, replay(p, c.starts, u, z), preset) for c in candidates]
    base = values[0]
    rows = []
    for c, v in zip(candidates, values):
        d = v - base
        se = float(d.std(ddof=1) / np.sqrt(runs))
        rows.append({"label": c.label, "value": round(float(v.mean()), 4), "vs_first": round(float(d.mean()), 4),
                     "se": round(se, 4)})
    best = max(range(len(candidates)), key=lambda k: values[k].mean())
    clear = best != 0 and rows[best]["vs_first"] > SWITCH_SE * max(rows[best]["se"], 1e-9)
    chosen = best if clear else 0
    return chosen, {
        "chosen": candidates[chosen].label,
        "switched": chosen != 0,
        "runs": runs,
        "rule": f"keep the fitness-best plan unless another beats it by more than {SWITCH_SE:g} standard errors",
        "candidates": rows,
    }
