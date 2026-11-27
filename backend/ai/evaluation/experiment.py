"""The four-scheduler comparison (design: Evaluation plan).

Protocol: N synthetic users x D days x each scheduler, paired by user seed.
Every scheduler sees the same tasks, commitments and check-ins; the random
draws that decide skips and real durations are seeded per (user, day, task),
so differences come from the planning, not from luck.

Each simulated day: plan the horizon at 08:30 and again at 14:00 (as a user
pressing Regenerate after lunch would), execute today's blocks against the
user's hidden truth, record outcomes (so the learning schedulers learn), and
carry unfinished work to the next day.

Stated assumptions: a user who is free starts the next planned block up to
30 minutes early; an overrun into a commitment pauses until it ends; work past
22:00 stops and counts as overload.

All results are computed here; nothing is typed in by hand.
"""
from __future__ import annotations

import math
import random
import statistics
import time as clock
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Callable

import numpy as np
from scipy.stats import wilcoxon

from ..baselines.schedulers import duration_aware, energy_greedy, priority_deadline
from ..ga.decoder import Decoded
from ..ga.local_search import LSConfig
from ..ga.runner import GAConfig, run_ga, run_hybrid
from ..problem import SLOT, Problem, build_problem
from ..rules.hard_rules import FactBase, PlacedBlock, check_hard
from ..types import CheckIn, Commitment, Outcome, OutcomeContext, PlanRequest, Preferences, TaskIn
from .simulator import DAY_END, SyntheticUser, TrueState

EVAL_GA = GAConfig(population=40, generations=60, patience=12)
EVAL_LS = LSConfig(max_evaluations=3000, max_seconds=1e9)  # budget by evaluations only, so runs are reproducible
EARLY_START_MIN = 30  # assumption: a free user starts the next block up to 30 min early
REPLAN_AT = [time(8, 30), time(14, 0)]  # assumption: the user regenerates the plan each morning and after lunch

SCHEDULERS = {
    "priority": "Priority / deadline",
    "duration": "Duration-aware",
    "energy": "Energy-aware greedy",
    "ga": "Constraint-aware GA",
    "hybrid": "GA + local search",
    "cpsat": "CP-SAT solver",
    "ga_1day": "GA, 1-day horizon",
    # Ablations of the full system (GA + local search, hierarchical durations).
    "abl_no_context": "Hybrid without context (completion by category only)",
    "abl_fuzzy": "Hybrid with fuzzy suitability instead of the completion model",
    "abl_no_prob": "Hybrid without learned durations",
    "abl_v1_durations": "Hybrid with the original duration model",
    # Plan selection: fitness-best hybrid plan (A, the reference) vs best simulated outcome (B).
    "hybrid_select": "Hybrid, main plan chosen by simulated outcome",
    # Buffer policies: how long each block is reserved for, and a shared slack at the end of each day.
    "buf_p50": "Blocks at P50 (median)",
    "buf_p65": "Blocks at P65",
    "buf_p50_shared": "Blocks at P50 + 15% shared daily buffer",
    "buf_p65_shared": "Blocks at P65 + 10% shared daily buffer",
}
ABLATIONS = ["abl_no_context", "abl_fuzzy", "abl_no_prob", "abl_v1_durations"]
SELECTION = ["hybrid_select"]
BUFFERS = ["buf_p50", "buf_p65", "buf_p50_shared", "buf_p65_shared"]
REFERENCE = "hybrid"  # the scheduler every other one is compared with

# Difficulty tiers: (new tasks per day, classes per day).
DIFFICULTY = {"easy": ((2, 4), (1, 2)), "moderate": ((4, 7), (1, 3)), "tight": ((7, 10), (2, 4))}

METRICS = {
    # key: (label, unit, higher_is_better)
    "completion_rate": ("Task completion rate", "% of planned blocks", True),
    "completed_per_day": ("Tasks completed", "per day", True),
    "deadline_violation_rate": ("Deadline violations", "% of tasks due", False),
    "duration_mae": ("Duration estimation error", "min", False),
    "energy_fit": ("Energy suitability (true fit)", "0-1", True),
    "overload_minutes": ("Overrun past day end", "min/day", False),
    "overloaded_days": ("Days planned above 85% load", "%", False),
    "collisions": ("Overruns into commitments", "per day", False),
    "plan_violations": ("Hard-rule violations in plans", "total", False),
    "solver_fallbacks": ("Solver fallbacks (no solution in time)", "% of plans", False),
}
# Wall-clock measurements vary between runs and machines, so they are kept out of the
# reproducible summary and reported separately.
RUNTIME = {"plan_seconds": ("Planning time", "s per plan", False)}


@dataclass
class EvalConfig:
    users: int = 10
    days: int = 7
    horizon: int = 3
    seed: int = 2026
    compare_horizon: bool = True
    start: date = date(2026, 1, 5)  # a fixed Monday so runs are reproducible
    difficulty: str = "moderate"  # easy | moderate | tight
    include_cpsat: bool = False  # slow: one solver call per plan
    cpsat_seconds: float = 2.0
    ablations: bool = False
    selection: bool = False  # add the outcome-selection scheduler
    buffers: bool = False  # add the buffer-policy variants


@dataclass
class World:
    """Everything that happens to one synthetic user, generated once and shared by all schedulers."""

    user: SyntheticUser
    new_tasks: list[list[TaskIn]]
    commitments: list[list[Commitment]]
    states: list[TrueState]
    checkins: list[CheckIn]


def make_world(seed: int, cfg: EvalConfig) -> World:
    u = SyntheticUser.create(seed)
    days = [cfg.start + timedelta(days=d) for d in range(cfg.days + 7)]
    states = [u.morning_state() for _ in days]
    task_range, classes = DIFFICULTY.get(cfg.difficulty, DIFFICULTY["moderate"])
    return World(
        user=u,
        new_tasks=[u.new_tasks(days[d], task_range) for d in range(cfg.days)],
        commitments=[u.commitments(day, classes) for day in days],
        states=states,
        checkins=[u.observed_checkin(states[d], datetime.combine(days[d], time(8, 30))) for d in range(len(days))],
    )


def _draw(seed: int, tid: int, day: int, kind: str) -> random.Random:
    return random.Random(f"{seed}-{tid}-{day}-{kind}")


def _request_options(name: str) -> dict:
    """PlanRequest fields that differ for a scheduler (ablations change the problem, not the optimiser)."""
    if name == "abl_no_context":
        return {"ablations": ("no_context",)}
    if name == "abl_fuzzy":
        return {"ablations": ("fuzzy_reference",)}
    if name == "abl_no_prob":
        return {"ablations": ("no_probability",)}
    if name == "abl_v1_durations":
        return {"duration_version": "v1"}
    buffers = {"buf_p50": (0.5, 0.0), "buf_p65": (0.65, 0.0), "buf_p50_shared": (0.5, 0.15),
               "buf_p65_shared": (0.65, 0.10)}
    if name in buffers:
        q, b = buffers[name]
        return {"reserve_quantile": q, "day_buffer": b}
    return {}


def _plan(name: str, p: Problem, seed: int, cfg: EvalConfig | None = None) -> tuple[Decoded, bool, bool]:
    """Returns the decoded plan, whether block lengths are the user's raw estimates, and whether
    a solver fell back to its greedy start because it found no solution in time."""
    if name == "priority":
        return priority_deadline(p), True, False
    if name == "duration":
        return duration_aware(p), False, False
    if name == "energy":
        return energy_greedy(p), False, False
    if name == "cpsat":
        from ..cpsat.scheduler import CPSATConfig, run_cpsat

        secs = cfg.cpsat_seconds if cfg else 2.0
        res = run_cpsat(p, "balanced", seed, CPSATConfig(time_limit=secs, seed=seed))
        return res.decoded, False, bool(res.details.get("cpsat", {}).get("fallback"))
    if name in ("ga", "ga_1day"):
        return run_ga(p, "balanced", seed, EVAL_GA).decoded, False, False
    if name == "hybrid_select":
        from ..selection import Candidate, select
        from ..uncertainty import MCConfig

        cands = [("balanced", seed), ("balanced", seed + 1), ("deadline", seed), ("gentle", seed)]
        runs = [run_hybrid(p, pr, sd, EVAL_GA, EVAL_LS).decoded for pr, sd in cands]
        k, _ = select(p, [Candidate(f"{pr}/{sd}", d.starts) for (pr, sd), d in zip(cands, runs)], "balanced",
                      MCConfig(runs=100, seed=seed))
        return runs[k], False, False
    return run_hybrid(p, "balanced", seed, EVAL_GA, EVAL_LS).decoded, False, False


def block_context(p: Problem, i: int, s: int) -> OutcomeContext:
    """The completion model's inputs for task i starting at slot s, as known when the plan was made."""
    t = p.tasks[i].task
    m, ph = p.slot_energy(s)
    st = p.day_states[p.day_of(s)]
    return OutcomeContext(p.slot_dt(s), t.mental_demand, t.physical_demand, m, ph, st.focus, st.stress)


def _plan_violations(p: Problem, dec: Decoded, use_est: bool) -> int:
    blocks = []
    for ti, s in zip(p.tasks, dec.starts):
        if s < 0:
            continue
        minutes = ti.est if use_est else ti.planned_minutes
        blocks.append(PlacedBlock(ti.task, p.slot_dt(s), p.slot_dt(s) + timedelta(minutes=minutes), minutes))
    facts = FactBase(p.req.now, p.req.prefs, p.req.commitments, {t.id: t for t in p.req.tasks}, blocks)
    return len(check_hard(facts))


@dataclass
class UserResult:
    planned: int = 0
    done: int = 0
    due: int = 0
    violations: int = 0
    abs_errors: list[float] = field(default_factory=list)
    fits: list[float] = field(default_factory=list)
    overload: float = 0.0
    overloaded_days: int = 0
    collisions: int = 0
    plan_violations: int = 0
    mae_by_day: list[float | None] = field(default_factory=list)
    plans: int = 0
    plan_time: float = 0.0
    fallbacks: int = 0
    outcomes: list = field(default_factory=list)  # the user's outcome history, in order (for model studies)

    def metrics(self, days: int) -> dict[str, float]:
        return {
            "completion_rate": 100 * self.done / self.planned if self.planned else 0.0,
            "completed_per_day": self.done / days,
            "deadline_violation_rate": 100 * self.violations / self.due if self.due else 0.0,
            "duration_mae": statistics.fmean(self.abs_errors) if self.abs_errors else 0.0,
            "energy_fit": statistics.fmean(self.fits) if self.fits else 0.0,
            "overload_minutes": self.overload / days,
            "overloaded_days": 100 * self.overloaded_days / days,
            "collisions": self.collisions / days,
            "plan_violations": float(self.plan_violations),
            "plan_seconds": self.plan_time / self.plans if self.plans else 0.0,
            "solver_fallbacks": 100 * self.fallbacks / self.plans if self.plans else 0.0,
        }


def simulate(world: World, name: str, cfg: EvalConfig, seed: int) -> UserResult:
    u = world.user
    horizon = 1 if name == "ga_1day" else cfg.horizon
    pending: dict[int, TaskIn] = {}
    history: list[Outcome] = []
    res = UserResult()
    counted_due: set[int] = set()
    for d in range(cfg.days):
        day = cfg.start + timedelta(days=d)
        day_end = datetime.combine(day, DAY_END)
        for t in world.new_tasks[d]:
            pending[t.id] = replace(t)
        commits = [c for dd in range(d, d + horizon) for c in world.commitments[dd]]
        base = world.states[d]
        day_commits = world.commitments[d]
        cursor = datetime.combine(day, REPLAN_AT[0])
        day_errors: list[float] = []
        for k, at in enumerate(REPLAN_AT):
            now = max(cursor, datetime.combine(day, at))
            if now >= day_end or not pending:
                break
            cut = datetime.combine(day, REPLAN_AT[k + 1]) if k + 1 < len(REPLAN_AT) else day_end
            req = PlanRequest(now, list(pending.values()), commits, world.checkins[max(0, d - 29) : d + 1],
                              list(history), Preferences(horizon_days=horizon), seed=seed + d * 10 + k,
                              **_request_options(name))
            t_plan = clock.perf_counter()
            p = build_problem(req)
            dec, use_est, fell_back = _plan(name, p, seed + d * 10 + k, cfg)
            res.plan_time += clock.perf_counter() - t_plan
            res.plans += 1
            res.fallbacks += int(fell_back)
            res.plan_violations += _plan_violations(p, dec, use_est)
            today = sorted((s, i) for i, s in enumerate(dec.starts) if 0 <= s < p.npd)
            if k == 0:
                planned_min = sum(dec.lengths[i] * SLOT for _, i in today)
                free = p.day_free_minutes[0]
                if free and planned_min / free > 0.85:
                    res.overloaded_days += 1
            for s, i in today:
                if p.slot_dt(s) >= cut:
                    break  # the next replan takes over from here
                ti = p.tasks[i]
                t = pending[ti.task.id]
                res.planned += 1
                ctx = block_context(p, i, s)
                # Free early? People start the next planned task up to 30 minutes ahead of time.
                start = max(p.slot_dt(s) - timedelta(minutes=EARLY_START_MIN), cursor)
                if start >= day_end:  # the day ran out before this block could start: censored, not a skip
                    history.append(Outcome(t.category, "unreached", int(ti.est), context=ctx))
                    continue
                fit = u.true_fit(base, start, t)
                if _draw(seed, t.id, d, f"skip{k}").random() >= u.follow * (0.6 + 0.4 * fit):
                    history.append(Outcome(t.category, "skipped", int(ti.est), context=ctx))
                    continue
                for c in day_commits:  # starting inside a commitment means waiting it out
                    if c.start <= start < c.end:
                        start = c.end
                        res.collisions += 1
                res.fits.append(fit)
                noise = math.exp(_draw(seed, t.id, d, "dur").gauss(0, 0.2))
                actual = ti.est * u.ratios[t.category] * noise * (1 + 0.35 * (1 - fit))
                end = start + timedelta(minutes=actual)
                for c in day_commits:  # an overrun that hits a commitment pauses until it ends
                    if start < c.start < end:
                        end += c.end - c.start
                        res.collisions += 1
                if end > day_end:
                    spill = (end - day_end).total_seconds() / 60
                    res.overload += spill
                    worked = max(0.0, actual - spill)
                    t.minutes_done = min(t.est_minutes - 5, t.minutes_done + int(worked))
                    history.append(Outcome(t.category, "partial", int(ti.est), int(worked) or None, ctx))
                    cursor = day_end
                    continue
                res.done += 1
                predicted = ti.est if use_est else ti.dur.median(ti.est)
                err = abs(predicted - actual)
                res.abs_errors.append(err)
                day_errors.append(err)
                history.append(Outcome(t.category, "done", int(round(ti.est)), int(round(actual)), ctx))
                if t.deadline is not None:
                    res.due += 1
                    counted_due.add(t.id)
                    if end > t.deadline:
                        res.violations += 1
                del pending[t.id]
                cursor = end
        res.mae_by_day.append(statistics.fmean(day_errors) if day_errors else None)
        # Anything still pending whose deadline has passed is missed.
        for tid in [tid for tid, t in pending.items() if t.deadline and t.deadline <= day_end]:
            if tid not in counted_due:
                res.due += 1
                res.violations += 1
            del pending[tid]
    res.outcomes = history
    return res


def bootstrap_ci(values: list[float], seed: int, n: int = 1000) -> tuple[float, float]:
    if len(values) < 2:
        v = values[0] if values else 0.0
        return v, v
    rng = np.random.default_rng(seed)
    arr = np.asarray(values)
    means = rng.choice(arr, size=(n, len(arr)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_test(a: list[float], b: list[float]) -> float | None:
    """Wilcoxon signed-rank p-value; None when every pair is identical."""
    diffs = [x - y for x, y in zip(a, b)]
    if all(abs(x) < 1e-12 for x in diffs) or len(diffs) < 3:
        return None
    try:
        return float(wilcoxon(a, b).pvalue)
    except ValueError:
        return None


def rank_biserial(a: list[float], b: list[float]) -> float | None:
    """Matched-pairs rank-biserial correlation, the effect size that goes with the Wilcoxon test.

    -1..1: the share of rank-weighted pairs where a > b minus the share where a < b.
    Roughly: |r| < 0.1 negligible, 0.1-0.3 small, 0.3-0.5 medium, > 0.5 large.
    """
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    d = d[np.abs(d) > 1e-12]
    if d.size == 0:
        return None
    from scipy.stats import rankdata

    ranks = rankdata(np.abs(d))
    return float((ranks[d > 0].sum() - ranks[d < 0].sum()) / ranks.sum())


def holm(pvalues: dict[str, float | None]) -> dict[str, float | None]:
    """Holm-Bonferroni adjustment across a family of tests (None = test not run)."""
    items = sorted(((p, k) for k, p in pvalues.items() if p is not None))
    m = len(items)
    out: dict[str, float | None] = {k: None for k in pvalues}
    running = 0.0
    for j, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - j) * p))
        out[k] = running
    return out


def paired_comparison(a: list[float], b: list[float], seed: int) -> dict:
    """Mean paired difference (a - b) with a bootstrap CI, Wilcoxon p and rank-biserial effect size."""
    diffs = [x - y for x, y in zip(a, b)]
    lo, hi = bootstrap_ci(diffs, seed)
    r = rank_biserial(a, b)
    return {"diff": round(statistics.fmean(diffs), 3) if diffs else 0.0, "ci": [round(lo, 3), round(hi, 3)],
            "p": None if (pv := paired_test(a, b)) is None else round(pv, 4),
            "effect": None if r is None else round(r, 3)}


def scheduler_names(cfg: EvalConfig) -> list[str]:
    names = ["priority", "duration", "energy", "ga", "hybrid"]
    if cfg.include_cpsat:
        from ..cpsat import available

        if available():
            names.append("cpsat")
    if cfg.compare_horizon and cfg.horizon > 1:
        names.append("ga_1day")
    if cfg.ablations:
        names += ABLATIONS
    if cfg.selection:
        names += SELECTION
    if cfg.buffers:
        names += BUFFERS
    return names


def run_experiment(cfg: EvalConfig, progress: Callable[[float], None] | None = None) -> dict:
    """Paired closed-loop comparison of every scheduler on the same synthetic users.

    Statistics: per metric, each scheduler is compared with the reference (the hybrid)
    on the same users: mean paired difference with a bootstrap 95% CI, Wilcoxon signed-
    rank p-value, rank-biserial effect size, and Holm-adjusted p across the comparisons
    for that metric. Failed solver calls are counted (solver_fallbacks), not dropped.
    """
    t0 = clock.perf_counter()
    names = scheduler_names(cfg)
    per_user: dict[str, list[dict[str, float]]] = {n: [] for n in names}
    curves: dict[str, list[list[float]]] = {n: [[] for _ in range(cfg.days)] for n in names}
    total = cfg.users * len(names)
    done = 0
    for k in range(cfg.users):
        useed = cfg.seed * 1000 + k
        for name in names:
            world = make_world(useed, cfg)  # rebuilt so every scheduler gets an identical world
            r = simulate(world, name, cfg, useed)
            per_user[name].append(r.metrics(cfg.days))
            for d, v in enumerate(r.mae_by_day):
                if v is not None:
                    curves[name][d].append(v)
            done += 1
            if progress:
                progress(done / total)

    summary = {}
    runtime = {}
    for name in names:
        summary[name] = {}
        for m in METRICS:
            vals = [x[m] for x in per_user[name]]
            lo, hi = bootstrap_ci(vals, cfg.seed)
            summary[name][m] = {"mean": round(statistics.fmean(vals), 3), "ci": [round(lo, 3), round(hi, 3)]}
        vals = [x["plan_seconds"] for x in per_user[name]]
        lo, hi = bootstrap_ci(vals, cfg.seed)
        runtime[name] = {"plan_seconds": {"mean": round(statistics.fmean(vals), 4), "ci": [round(lo, 4), round(hi, 4)]}}
    # Kept for the original lab view: the plain GA against each other scheduler.
    tests = {}
    for base in [n for n in names if n != "ga"]:
        tests[base] = {}
        for m in METRICS:
            p = paired_test([x[m] for x in per_user["ga"]], [x[m] for x in per_user[base]])
            tests[base][m] = None if p is None else round(p, 4)
    comparisons: dict[str, dict[str, dict]] = {}
    others = [n for n in names if n != REFERENCE]
    for m in METRICS:
        raw = {}
        for other in others:
            c = paired_comparison([x[m] for x in per_user[REFERENCE]], [x[m] for x in per_user[other]], cfg.seed)
            comparisons.setdefault(other, {})[m] = c
            raw[other] = c["p"]
        for other, ph in holm(raw).items():
            comparisons[other][m]["p_holm"] = None if ph is None else round(ph, 4)
    learning = {
        n: [round(statistics.fmean(v), 2) if v else None for v in curves[n]] for n in names
    }
    from ..pipeline import VERSION
    from ..probability.duration_model import DEFAULT_VERSION

    return {
        "config": {"users": cfg.users, "days": cfg.days, "horizon": cfg.horizon, "seed": cfg.seed,
                   "compare_horizon": cfg.compare_horizon, "difficulty": cfg.difficulty,
                   "include_cpsat": cfg.include_cpsat and "cpsat" in names, "cpsat_seconds": cfg.cpsat_seconds, "ablations": cfg.ablations,
                   "selection": cfg.selection, "buffers": cfg.buffers},
        "versions": {"circadia": VERSION, "duration_model": DEFAULT_VERSION,
                     "ga": {"population": EVAL_GA.population, "generations": EVAL_GA.generations,
                            "patience": EVAL_GA.patience},
                     "local_search": {"max_evaluations": EVAL_LS.max_evaluations}},
        "schedulers": {n: SCHEDULERS[n] for n in names},
        "metrics": {k: {"label": v[0], "unit": v[1], "higher_is_better": v[2]} for k, v in METRICS.items()},
        "summary": summary,
        "runtime": runtime,
        "runtime_metrics": {k: {"label": v[0], "unit": v[1], "higher_is_better": v[2]} for k, v in RUNTIME.items()},
        "wilcoxon_ga_vs": tests,
        "reference": REFERENCE,
        "comparisons": comparisons,
        "per_user": per_user,
        "learning_curve": learning,
        "seconds": round(clock.perf_counter() - t0, 1),
        "data": "synthetic",
    }
