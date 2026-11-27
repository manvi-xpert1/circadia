"""The one entry point: plan(request) -> a plan with explanations.

Order of work (design section 3.4, data flow):
  rule pre-check -> predictions (durations; U = P(block happens) per task and slot)
  -> genetic algorithm (main preset + alternatives) -> final hard-rule check
  -> explanations
"""
from __future__ import annotations

import time
from datetime import timedelta

from .explain.explainer import explain_block, explain_unscheduled, soft_flags
from .ga.fitness import PRESET_LABELS, PRESETS, grid_blocks, weights_for
from .ga.runner import GAResult, GAConfig, run_ga, run_hybrid
from .problem import SLOT, Problem, build_problem
from .rules import soft_rules as sr
from .rules.hard_rules import FactBase, PlacedBlock, check_hard
from .tradeoffs import annotate
from .types import PlanRequest
from .selection import Candidate, select
from .uncertainty import MCConfig, simulate_plan

SIMILARITY_LIMIT = 0.70
OPTIMIZERS = {
    "ga": "Genetic algorithm",
    "hybrid": "Genetic algorithm + local search",
    "cpsat": "Thorough: hybrid, then the CP-SAT solver",
}
DEFAULT_OPTIMIZER = "hybrid"
VERSION = "2.0"  # recorded with every plan and evaluation run


def optimise(p: Problem, preset: str, seed: int, optimizer: str = DEFAULT_OPTIMIZER,
             config: GAConfig | None = None, cpsat_seconds: float = 8.0) -> GAResult:
    """Run the chosen optimiser. Every optimiser returns a GAResult so the rest of the pipeline is shared."""
    if optimizer == "ga":
        return run_ga(p, preset, seed, config)
    hybrid = run_hybrid(p, preset, seed, config)
    if optimizer != "cpsat":
        return hybrid
    try:
        import ortools  # noqa: F401
    except ImportError:  # OR-Tools is optional (no wheels for every Python version)
        hybrid.details["cpsat"] = {"status": "UNAVAILABLE", "note": "OR-Tools is not installed; used GA + local search."}
        return hybrid
    from .cpsat.scheduler import CPSATConfig, run_cpsat

    cp = run_cpsat(p, preset, seed, CPSATConfig(time_limit=cpsat_seconds, seed=seed), warm_start=hybrid.decoded.starts)
    cp.details["hybrid_score"] = round(hybrid.score.total, 5)
    if cp.score.total > hybrid.score.total + 1e-9:
        cp.log = hybrid.log + [{"gen": hybrid.generations + 2, "best": round(cp.score.total, 5), "mean": None,
                                "stage": "CP-SAT"}]
        cp.generations = hybrid.generations
        cp.evaluations = hybrid.evaluations
        cp.seconds += hybrid.seconds
        return cp
    hybrid.details["cpsat"] = cp.details.get("cpsat")  # the solver could not improve on it; say so
    hybrid.optimizer = "cpsat"
    hybrid.seconds += cp.seconds
    return hybrid


def stability_report(p: Problem, starts: list[int]) -> dict | None:
    """How much a replanned schedule differs from the plan it replaces."""
    prev = [(i, s) for i, s in enumerate(p.prev_slot) if s is not None]
    if not prev:
        return None
    moved = removed = kept = 0
    shift = 0
    for i, s in prev:
        if starts[i] < 0:
            removed += 1
        elif starts[i] == s:
            kept += 1
        else:
            moved += 1
            shift += abs(starts[i] - s)
    added = sum(1 for i, s in enumerate(starts) if s >= 0 and p.prev_slot[i] is None)
    return {"previous_blocks": len(prev), "kept": kept, "moved": moved, "removed": removed, "added": added,
            "displacement_minutes": shift * SLOT}


class RuleViolationError(RuntimeError):
    """Raised if a plan ever breaks a hard rule. Tests assert this never happens."""


def verify(p: Problem, res: GAResult) -> None:
    blocks = [
        PlacedBlock(ti.task, p.slot_dt(s), p.slot_dt(s) + timedelta(minutes=ti.planned_minutes), ti.planned_minutes)
        for ti, s in zip(p.tasks, res.decoded.starts)
        if s >= 0
    ]
    blocks += [PlacedBlock(fb.task, fb.start, fb.end, 0, fb.kind) for fb in p.fixed_blocks]
    tasks = {t.id: t for t in p.req.tasks}
    facts = FactBase(p.req.now, p.req.prefs, p.req.commitments, tasks, blocks)
    violations = check_hard(facts)
    if violations:
        raise RuleViolationError("; ".join(f"{v.rule} task {v.task_id}: {v.message}" for v in violations))


def similarity(a: GAResult, b: GAResult) -> float:
    sa, sb = a.decoded.starts, b.decoded.starts
    either = [i for i in range(len(sa)) if sa[i] >= 0 or sb[i] >= 0]
    if not either:
        return 1.0
    same = sum(1 for i in either if sa[i] >= 0 and sb[i] >= 0 and abs(sa[i] - sb[i]) <= 1)
    return same / len(either)


def describe_plan(p: Problem, res: GAResult, preset: str, mc: MCConfig | None = None) -> dict:
    flags = soft_flags(p, res.decoded.starts, res.decoded.lengths)
    blocks = [explain_block(p, i, res, flags) for i, s in enumerate(res.decoded.starts) if s >= 0]
    blocks.sort(key=lambda b: b["start"])
    planned, loads = sr.day_loads(grid_blocks(p, res.decoded.starts, res.decoded.lengths), p.npd, p.horizon, p.day_free_minutes)
    heavy = sr.a8_heavy_days(loads, p.day_free_minutes)
    return {
        "preset": preset,
        "label": PRESET_LABELS[preset],
        "fitness": round(res.score.total, 4),
        "components": res.score.parts,
        "weights": weights_for(p, preset),
        "optimizer": res.optimizer,
        "optimizer_label": OPTIMIZERS.get(res.optimizer, res.optimizer),
        "optimizer_details": res.details,
        "stability": stability_report(p, res.decoded.starts),
        "robustness": simulate_plan(p, res.decoded.starts, mc) if mc is not None else None,
        "blocks": blocks,
        "unscheduled": explain_unscheduled(p, res, preset),
        "day_load": [
            {"day": d, "planned_minutes": planned[d], "load": round(loads[d], 2), "heavy": d in heavy}
            for d in range(p.horizon)
        ],
        "convergence": res.log,
        "generations": res.generations,
        "evaluations": res.evaluations,
        "seconds": round(res.seconds, 2),
    }


def fixed_items(p: Problem) -> list[dict]:
    return [
        {
            "task_id": fb.task.id,
            "title": fb.task.title,
            "category": fb.task.category,
            "kind": fb.kind,
            "start": fb.start.isoformat(),
            "end": fb.end.isoformat(),
            "day": fb.start_slot // p.npd,
        }
        for fb in p.fixed_blocks
    ]


def plan(req: PlanRequest, config: GAConfig | None = None, alternatives: bool = True,
         optimizer: str | None = None, mc_runs: int | None = None) -> dict:
    """Plan the horizon.

    optimizer: "ga" (original), "hybrid" (default: GA + local search) or "cpsat"
               (hybrid, then CP-SAT; only the main plan uses the solver, to keep it quick).
    mc_runs:   fixed number of Monte Carlo replays per plan, overriding req.simulation
               (0 turns robustness estimates and outcome-based selection off).
    alternatives: also optimise for the other presets. Those plans, and a second seed of
               the user's preset, are candidates for the main plan, which is chosen by
               simulated outcome when req.select_by_outcome is set (see ai.selection).
    """
    t0 = time.perf_counter()
    p = build_problem(req)
    opt = optimizer or getattr(req, "optimizer", None) or DEFAULT_OPTIMIZER
    if opt not in OPTIMIZERS:
        raise ValueError(f"Unknown optimizer {opt!r}; choose one of {', '.join(OPTIMIZERS)}")
    mc = MCConfig(runs=mc_runs, seed=req.seed) if mc_runs is not None else MCConfig.tier(req.simulation, req.seed)
    simulate = mc.adaptive or mc.runs > 0
    main_preset = req.prefs.preset if req.prefs.preset in PRESETS else "balanced"
    main = optimise(p, main_preset, req.seed, opt, config)
    verify(p, main)
    results: list[tuple[str, str, GAResult]] = [(main_preset, f"{PRESET_LABELS[main_preset]}, seed {req.seed}", main)]
    alts: list[tuple[str, GAResult]] = []
    if alternatives:
        alt_opt = "hybrid" if opt == "cpsat" else opt
        for preset in PRESETS:
            if preset == main_preset:
                continue
            alt = optimise(p, preset, req.seed, alt_opt, config)
            verify(p, alt)
            alts.append((preset, alt))
            results.append((preset, f"{PRESET_LABELS[preset]} plan", alt))
        if simulate and req.select_by_outcome:
            reseed = optimise(p, main_preset, req.seed + 1, alt_opt, config)
            verify(p, reseed)
            results.insert(1, (main_preset, f"{PRESET_LABELS[main_preset]}, seed {req.seed + 1}", reseed))
    selection = None
    chosen = main
    if simulate and req.select_by_outcome and len(results) > 1:
        k, selection = select(p, [Candidate(label, r.decoded.starts) for _, label, r in results], main_preset, mc)
        chosen = results[k][2]
    first = describe_plan(p, chosen, main_preset, mc if simulate else None)
    first["selection"] = selection
    plans = [first]
    for preset, alt in alts:
        if alt is not chosen and similarity(chosen, alt) < SIMILARITY_LIMIT:
            plans.append(describe_plan(p, alt, preset, mc if simulate else None))
    if simulate:
        annotate(plans)

    days = []
    for d in range(p.horizon):
        st = p.day_states[d]
        days.append(
            {
                "day": d,
                "date": (p.day0 + timedelta(days=d)).isoformat(),
                "free_minutes": p.day_free_minutes[d],
                "energy_source": st.source,
                "energy": {k: round(getattr(st, k), 1) for k in ("mental", "physical", "focus", "stress")},
                "stress_cap": d == 0 and p.stress_cap_day0(),
                "capacity": [round(float(c), 2) for c in p.cap[d * p.npd : (d + 1) * p.npd]],
            }
        )
    n_out = len(req.outcomes)
    return {
        "meta": {
            "now": req.now.isoformat(),
            "horizon_days": p.horizon,
            "day_start": req.prefs.day_start.strftime("%H:%M"),
            "day_end": req.prefs.day_end.strftime("%H:%M"),
            "slot_minutes": SLOT,
            "seed": req.seed,
            "optimizer": opt,
            "simulation": {"runs": first["robustness"]["runs"], "adaptive": mc.adaptive} if first.get("robustness") else None,
            "version": VERSION,
            "stability_weight": p.stability if p.has_previous else None,
            "mode": "personalized" if n_out >= 3 else "cold",
            "outcomes_used": n_out,
            "checkins_used": len(req.checkins),
            "profile": p.profile.as_dict(),
            "warnings": p.warnings,
            "seconds": round(time.perf_counter() - t0, 2),
        },
        "days": days,
        "fixed": fixed_items(p),
        "commitments": [
            {"label": c.label, "kind": c.kind, "start": c.start.isoformat(), "end": c.end.isoformat()}
            for c in req.commitments
        ],
        "plans": plans,
    }
