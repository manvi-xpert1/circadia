"""Follow-through: does a planned block actually happen? (design section 3.3b)

follow-through = (4 + done) / (5 + done + skipped)

Equivalent to a Beta(4, 1) prior updated with counts: start by assuming 4 of 5
planned blocks happen, then count real outcomes. Partial counts as done.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..types import Outcome

PRIOR_DONE = 4
PRIOR_SKIPPED = 1


@dataclass
class FollowThrough:
    done: int
    skipped: int

    @property
    def p(self) -> float:
        return (PRIOR_DONE + self.done) / (PRIOR_DONE + PRIOR_SKIPPED + self.done + self.skipped)

    @property
    def learned(self) -> bool:
        return self.done + self.skipped >= 3


class FollowThroughModel:
    def __init__(self, outcomes: list[Outcome]):
        self.counts: dict[str, list[int]] = {}
        for o in outcomes:
            c = self.counts.setdefault(o.category, [0, 0])
            if o.status in ("done", "partial"):
                c[0] += 1
            elif o.status == "skipped":
                c[1] += 1

    def for_category(self, category: str) -> FollowThrough:
        done, skipped = self.counts.get(category, [0, 0])
        return FollowThrough(done, skipped)

    def summary(self) -> dict:
        return {
            c: {"done": d, "skipped": s, "p": round(FollowThrough(d, s).p, 3)}
            for c, (d, s) in sorted(self.counts.items())
        }
