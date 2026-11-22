"""Soft rules A1-A8 (design section 3.3c).

Soft rules never make a plan illegal. They feed penalties into the fitness
function and warnings into the explanations. They work on the optimiser's
slot grid so the fitness function and the explainer share one definition.
"""
from __future__ import annotations

from dataclasses import dataclass

SOFT_RULES = [
    ("A1", "Focus run longer than your max focus block without a break", "Penalty; suggest a break"),
    ("A2", "A day's planned minutes exceed 85% of its free minutes", "Overload penalty"),
    ("A3", "Task placed where its energy fit is below 0.35", "Penalty; warns 'low energy fit'"),
    ("A4", "High-priority task due within a day", "Bonus for earlier placement (via priority discount)"),
    ("A5", "Latest check-in has stress 8 or more", "Cap that day's load at 70%"),
    ("A6", "Two back-to-back blocks both with mental demand 7 or more", "Context-load penalty"),
    ("A7", "Block ends after your 'no work after' time", "Penalty"),
    ("A8", "A day is above 60% load and busier than the horizon's average", "Balance penalty"),
]


@dataclass
class GridBlock:
    key: int  # task index for movable tasks, -1 for fixed / locked
    start: int
    length: int
    category: str
    mental_demand: float

    @property
    def end(self) -> int:
        return self.start + self.length


def sort_blocks(blocks: list[GridBlock]) -> list[GridBlock]:
    return sorted(blocks, key=lambda b: b.start)


def adjacent_pairs(blocks: list[GridBlock], npd: int):
    """Neighbouring blocks on the same day with at most one free slot between."""
    bs = sort_blocks(blocks)
    for x, y in zip(bs, bs[1:]):
        if x.start // npd == y.start // npd and y.start - x.end <= 1:
            yield x, y


def a1_focus_runs(blocks: list[GridBlock], npd: int, max_focus_minutes: int, slot: int = 15) -> set[int]:
    """Blocks (by start slot) that sit in a run of touching blocks longer than allowed."""
    flagged: set[int] = set()
    run: list[GridBlock] = []

    def close():
        if run and sum(b.length for b in run) * slot > max_focus_minutes and len(run) > 1:
            flagged.update(b.start for b in run)

    for b in sort_blocks(blocks):
        if run and (b.start != run[-1].end or b.start // npd != run[-1].start // npd):
            close()
            run = []
        run.append(b)
    close()
    return flagged


def a7_late(blocks: list[GridBlock], npd: int, limit_slot_in_day: int) -> set[int]:
    return {b.start for b in blocks if (b.end - (b.start // npd) * npd) > limit_slot_in_day}


def a6_and_switches(blocks: list[GridBlock], npd: int) -> tuple[int, int]:
    switches = heavy = 0
    for x, y in adjacent_pairs(blocks, npd):
        if x.category != y.category:
            switches += 1
        if x.mental_demand >= 7 and y.mental_demand >= 7:
            heavy += 1
    return switches, heavy


def day_loads(blocks: list[GridBlock], npd: int, horizon: int, free_minutes: list[int], slot: int = 15):
    planned = [0] * horizon
    for b in blocks:
        planned[b.start // npd] += b.length * slot
    loads = [planned[d] / free_minutes[d] if free_minutes[d] > 0 else 0.0 for d in range(horizon)]
    return planned, loads


def a8_heavy_days(loads: list[float], free_minutes: list[int]) -> list[int]:
    active = [l for l, f in zip(loads, free_minutes) if f > 0]
    if len(active) < 2:
        return []
    mean = sum(active) / len(active)
    threshold = max(0.6, mean)
    return [d for d, l in enumerate(loads) if free_minutes[d] > 0 and l > threshold]


def describe() -> list[dict]:
    return [{"id": i, "logic": cond, "meaning": effect, "type": "soft"} for i, cond, effect in SOFT_RULES]
