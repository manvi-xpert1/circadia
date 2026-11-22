"""The genetic algorithm loop (design section 3.3d).

Population 60, tournament selection (size 3), elitism 2, OX1 + uniform
crossover (rate 0.85), mutation, stop after 120 generations or 20
generations without improvement. The random seed is stored with every plan,
so the same inputs always give the same plan.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..problem import Problem
from .decoder import Decoded, decode
from .fitness import Score, evaluate
from .operators import mutate, order_crossover, tournament, uniform_crossover


@dataclass
class GAConfig:
    population: int = 60
    generations: int = 120
    patience: int = 20
    crossover_rate: float = 0.85
    elitism: int = 2
    tournament_size: int = 3
    min_gain: float = 1e-4


@dataclass
class GAResult:
    order: np.ndarray
    hints: np.ndarray
    decoded: Decoded
    score: Score
    log: list[dict] = field(default_factory=list)  # best and mean fitness per generation
    generations: int = 0
    evaluations: int = 0
    seconds: float = 0.0
    optimizer: str = "ga"  # "ga", "hybrid" or "cpsat"
    details: dict = field(default_factory=dict)  # optimiser-specific stats (local search, solver status)


def best_fit_hints(p: Problem) -> np.ndarray:
    """Seed: each task's preferred start = the slot where its block fits best."""
    hints = np.zeros(len(p.tasks), dtype=np.int64)
    for ti in p.tasks:
        L = ti.slots_p80
        last = min(p.G, ti.dl_end) - L
        if last < 0:
            continue
        means = (p.Ucs[ti.idx, L : last + L + 1] - p.Ucs[ti.idx, : last + 1]) / L
        hints[ti.idx] = int(np.argmax(means))
    return hints


def previous_chromosome(p: Problem) -> tuple[np.ndarray, np.ndarray]:
    """Seed for stability-aware replanning: the previous plan, with new tasks at their best-fit start."""
    best = best_fit_hints(p)
    hints = np.array([s if s is not None else int(best[i]) for i, s in enumerate(p.prev_slot)], dtype=np.int64)
    order = np.array(
        sorted(range(len(p.tasks)), key=lambda i: (p.prev_slot[i] is None, p.prev_slot[i] or 0, i)), dtype=np.int64
    )
    return order, hints


def seed_population(p: Problem, rng: np.random.Generator, size: int):
    n = len(p.tasks)
    by_deadline = np.array(sorted(range(n), key=lambda i: (p.tasks[i].dl_end, -p.tasks[i].task.priority)), dtype=np.int64)
    by_priority = np.array(sorted(range(n), key=lambda i: (-p.tasks[i].task.priority, p.tasks[i].dl_end)), dtype=np.int64)
    earliest = np.zeros(n, dtype=np.int64)
    best = best_fit_hints(p)
    pop = [
        (by_deadline, earliest.copy()),
        (by_priority, earliest.copy()),
        (by_priority.copy(), best.copy()),
        (by_deadline.copy(), best.copy()),
    ]
    while len(pop) < size:
        pop.append((rng.permutation(n).astype(np.int64), rng.integers(0, p.G, size=n)))
    return pop[:size]


def run_ga(
    p: Problem,
    preset: str = "balanced",
    seed: int = 42,
    config: GAConfig | None = None,
    initial: list[tuple[np.ndarray, np.ndarray]] | None = None,
) -> GAResult:
    cfg = config or GAConfig()
    rng = np.random.default_rng(seed)
    t0 = time.perf_counter()
    n = len(p.tasks)
    if n == 0:
        dec = Decoded([], [], {})
        return GAResult(np.array([], dtype=np.int64), np.array([], dtype=np.int64), dec, evaluate(p, [], [], preset))

    cache: dict[bytes, tuple[Decoded, Score]] = {}

    def assess(order, hints):
        key = order.tobytes() + hints.tobytes()
        hit = cache.get(key)
        if hit is None:
            dec = decode(p, order, hints)
            hit = (dec, evaluate(p, dec.starts, dec.lengths, preset))
            cache[key] = hit
        return hit

    pop = seed_population(p, rng, cfg.population)
    if initial is None and p.has_previous and p.stability > 0:
        initial = [previous_chromosome(p)]
    if initial:
        pop = (list(initial) + pop)[: cfg.population]
    scores = [assess(o, h)[1].total for o, h in pop]
    log: list[dict] = []
    best_val = max(scores)
    stale = 0
    gen = 0
    for gen in range(1, cfg.generations + 1):
        ranked = np.argsort(scores)[::-1]
        new_pop = [pop[i] for i in ranked[: cfg.elitism]]
        while len(new_pop) < cfg.population:
            a = pop[tournament(rng, scores, cfg.tournament_size)]
            b = pop[tournament(rng, scores, cfg.tournament_size)]
            if rng.random() < cfg.crossover_rate:
                order = order_crossover(rng, a[0], b[0])
                hints = uniform_crossover(rng, a[1], b[1])
            else:
                order, hints = a[0].copy(), a[1].copy()
            new_pop.append(mutate(rng, order, hints, p.G))
        pop = new_pop
        scores = [assess(o, h)[1].total for o, h in pop]
        top = max(scores)
        log.append({"gen": gen, "best": round(top, 5), "mean": round(float(np.mean(scores)), 5)})
        if top > best_val + cfg.min_gain:
            best_val, stale = top, 0
        else:
            stale += 1
            if stale >= cfg.patience:
                break
    i = int(np.argmax(scores))
    dec, sc = assess(*pop[i])
    return GAResult(pop[i][0], pop[i][1], dec, sc, log, gen, len(cache), time.perf_counter() - t0)


def run_hybrid(
    p: Problem,
    preset: str = "balanced",
    seed: int = 42,
    config: GAConfig | None = None,
    ls_config: "LSConfig | None" = None,
) -> GAResult:
    """GA followed by local-search refinement of its best plan (a memetic algorithm)."""
    from dataclasses import replace

    from .local_search import LSConfig, chromosome_for, local_search

    base = run_ga(p, preset, seed, config)
    lcfg = replace(ls_config or LSConfig(), seed=seed)
    dec, sc, stats = local_search(p, base.decoded, preset, lcfg)
    order, hints = chromosome_for(p, dec.starts)
    log = list(base.log)
    if stats.end_score > stats.start_score:
        log.append({"gen": base.generations + 1, "best": round(sc.total, 5), "mean": None, "stage": "local search"})
    return GAResult(
        order, hints, dec, sc, log, base.generations, base.evaluations + stats.evaluations,
        base.seconds + stats.seconds, "hybrid", {"local_search": stats.as_dict(), "ga_score": round(base.score.total, 5)},
    )
