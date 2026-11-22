"""Genetic operators: tournament selection, OX1 and uniform crossover, mutation."""
from __future__ import annotations

import numpy as np


def tournament(rng: np.random.Generator, fitness: list[float], size: int = 3) -> int:
    """Pick `size` individuals at random and return the index of the fittest."""
    picks = rng.choice(len(fitness), size=size, replace=False)
    return int(max(picks, key=lambda i: fitness[i]))


def order_crossover(rng: np.random.Generator, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """OX1: copy a slice from parent 1, fill the rest in parent 2's order.

    The child is always a valid permutation.
    """
    n = len(p1)
    if n < 2:
        return p1.copy()
    a, b = sorted(rng.choice(n + 1, size=2, replace=False))
    child = np.full(n, -1, dtype=p1.dtype)
    child[a:b] = p1[a:b]
    taken = set(p1[a:b].tolist())
    fill = [g for g in np.concatenate([p2[b:], p2[:b]]).tolist() if g not in taken]
    positions = list(range(b, n)) + list(range(0, a))
    for pos, gene in zip(positions, fill):
        child[pos] = gene
    return child


def uniform_crossover(rng: np.random.Generator, h1: np.ndarray, h2: np.ndarray) -> np.ndarray:
    mask = rng.random(len(h1)) < 0.5
    return np.where(mask, h1, h2)


def mutate(
    rng: np.random.Generator,
    order: np.ndarray,
    hints: np.ndarray,
    G: int,
    swap_rate: float = 0.20,
    shift_rate: float = 0.20,
    jump_rate: float = 0.05,
    toggle_rate: float = 0.02,
) -> tuple[np.ndarray, np.ndarray]:
    order = order.copy()
    hints = hints.copy()
    n = len(order)
    if n >= 2 and rng.random() < swap_rate:
        i, j = rng.choice(n, size=2, replace=False)
        order[i], order[j] = order[j], order[i]
    # Shift: move a preferred start by 1-4 slots (15-60 minutes).
    shift = rng.random(n) < shift_rate
    steps = rng.integers(1, 5, size=n) * rng.choice([-1, 1], size=n)
    active = hints >= 0
    hints = np.where(shift & active, np.clip(hints + steps, 0, G - 1), hints)
    # Jump: try a completely different time, possibly another day.
    jump = rng.random(n) < jump_rate
    hints = np.where(jump & (hints >= 0), rng.integers(0, G, size=n), hints)
    # Toggle: switch a task in or out of this horizon.
    toggle = rng.random(n) < toggle_rate
    hints = np.where(toggle, np.where(hints >= 0, -1, rng.integers(0, G, size=n)), hints)
    return order, hints
