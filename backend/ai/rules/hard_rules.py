"""Hard rules H1-H9 (design section 3.3c; H9 added with repeating tasks).

Each rule is written once in predicate-logic notation (shown in the app) and
once as a Python check. The check works on real datetimes, independently of
the optimiser's slot grid, so it is a genuine second opinion: if the genetic
algorithm or its decoder ever produced an illegal plan, this would catch it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..types import Commitment, Preferences, TaskIn

TOLERANCE = timedelta(minutes=1)


@dataclass
class PlacedBlock:
    task: TaskIn
    start: datetime
    end: datetime
    planned_minutes: float  # minutes the duration model says to reserve (P80)
    kind: str = "ai"  # "ai", "fixed-task" or "locked"


@dataclass
class FactBase:
    """Ground facts for one planning run."""

    now: datetime
    prefs: Preferences
    commitments: list[Commitment]
    tasks: dict[int, TaskIn]  # every pending task, by id
    blocks: list[PlacedBlock]


@dataclass
class Violation:
    rule: str
    task_id: int
    message: str


@dataclass
class Rule:
    id: str
    logic: str
    meaning: str
    check: Callable[[FactBase], list[Violation]]


def _overlaps(a0, a1, b0, b1) -> bool:
    return a0 < b1 - TOLERANCE and b0 < a1 - TOLERANCE


def h1_window(f: FactBase):
    out = []
    for b in f.blocks:
        ds = datetime.combine(b.start.date(), f.prefs.day_start)
        de = datetime.combine(b.start.date(), f.prefs.day_end)
        if b.kind == "fixed-task":
            continue  # the user placed it; H6 keeps it where it is
        if b.start < ds or b.end > de + TOLERANCE or b.end.date() != b.start.date():
            out.append(Violation("H1", b.task.id, "Outside the working window"))
        if b.kind == "ai" and b.start < f.now - TOLERANCE:
            out.append(Violation("H1", b.task.id, "Starts in the past"))
    return out


def _commit_overlap(kind: str, rule: str):
    def check(f: FactBase):
        out = []
        for b in f.blocks:
            if b.kind == "fixed-task":
                continue
            for c in f.commitments:
                if c.kind == kind and _overlaps(b.start, b.end, c.start, c.end):
                    out.append(Violation(rule, b.task.id, f"Overlaps {c.label}"))
        return out

    return check


def h4_no_overlap(f: FactBase):
    out = []
    bs = sorted(f.blocks, key=lambda b: b.start)
    for x, y in zip(bs, bs[1:]):
        if _overlaps(x.start, x.end, y.start, y.end):
            out.append(Violation("H4", y.task.id, f"Overlaps {x.task.title}"))
    return out


def h5_dependencies(f: FactBase):
    out = []
    placed = {b.task.id: b for b in f.blocks}
    for b in f.blocks:
        dep = b.task.depends_on
        if dep is None or dep not in f.tasks:
            continue  # no prerequisite, or it is already done
        pre = placed.get(dep)
        if pre is None:
            out.append(Violation("H5", b.task.id, f"Prerequisite \"{f.tasks[dep].title}\" is not scheduled"))
        elif pre.end > b.start + TOLERANCE:
            out.append(Violation("H5", b.task.id, f"Starts before \"{pre.task.title}\" ends"))
    return out


def h6_fixed(f: FactBase):
    out = []
    for b in f.blocks:
        t = b.task
        if t.is_fixed and (b.start != t.fixed_start or b.end != t.fixed_end):
            out.append(Violation("H6", t.id, "Fixed task was moved"))
    return out


def h7_deadline(f: FactBase):
    out = []
    for b in f.blocks:
        if b.kind == "ai" and b.task.deadline and b.end > b.task.deadline + TOLERANCE:
            out.append(Violation("H7", b.task.id, "Ends after its deadline"))
    return out


def h8_length(f: FactBase):
    out = []
    for b in f.blocks:
        if b.kind == "ai" and (b.end - b.start).total_seconds() / 60 + 0.5 < b.planned_minutes:
            out.append(Violation("H8", b.task.id, "Block is shorter than the predicted duration"))
    return out


def h9_release(f: FactBase):
    out = []
    for b in f.blocks:
        nb = b.task.not_before
        if b.kind == "ai" and nb is not None and b.start < nb - TOLERANCE:
            out.append(Violation("H9", b.task.id, "Starts before the day it belongs to"))
    return out


HARD_RULES: list[Rule] = [
    Rule("H1", "∀T,d,s,e: block(T,d,s,e) → s ≥ day_start(d) ∧ e ≤ day_end(d) ∧ s ≥ now",
         "Inside that day's working window and not in the past", h1_window),
    Rule("H2", "∀T,F: block(T,s,e) ∧ fixed(F,s′,e′) → e ≤ s′ ∨ s ≥ e′",
         "No overlap with fixed commitments", _commit_overlap("fixed", "H2")),
    Rule("H3", "∀T: block(T,s,e) ∧ unavailable(s′,e′) → e ≤ s′ ∨ s ≥ e′",
         "No overlap with unavailable time", _commit_overlap("unavailable", "H3")),
    Rule("H4", "∀T₁≠T₂: block(T₁,s₁,e₁) ∧ block(T₂,s₂,e₂) → e₁ ≤ s₂ ∨ e₂ ≤ s₁",
         "No two tasks at once", h4_no_overlap),
    Rule("H5", "depends(T₂,T₁) ∧ block(T₂,s₂,_) → block(T₁,_,e₁) ∧ e₁ ≤ s₂, or done(T₁)",
         "Prerequisites come first", h5_dependencies),
    Rule("H6", "fixed_task(T,s,e) → block(T,s,e)", "Fixed tasks never move", h6_fixed),
    Rule("H7", "deadline(T) ∧ block(T,d,s,e) → (d,e) ≤ deadline(T)",
         "No block ends after its deadline", h7_deadline),
    Rule("H8", "block(T,s,e) → e − s ≥ P80(T)", "Blocks are long enough for the predicted duration", h8_length),
    Rule("H9", "not_before(T,r) ∧ block(T,s,e) → s ≥ r", "A repeating task's copy is done on its own day, not earlier", h9_release),
]


def check_hard(facts: FactBase) -> list[Violation]:
    """Forward pass over every hard rule; returns all violations found."""
    out: list[Violation] = []
    for rule in HARD_RULES:
        out.extend(rule.check(facts))
    return out


def describe() -> list[dict]:
    return [{"id": r.id, "logic": r.logic, "meaning": r.meaning, "type": "hard"} for r in HARD_RULES]
