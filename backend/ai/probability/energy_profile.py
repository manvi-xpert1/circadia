"""Time-of-day energy profile: projects a check-in to every slot of the day.

A check-in is one reading at one moment. To estimate energy in other slots
we add a time-of-day offset. Defaults are a generic assumption; once the user
has check-ins in a band, the offset blends toward their own pattern with
weight n / (n + 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

from ..types import CheckIn

# (band start hour, band end hour, mental offset, physical offset)
DEFAULT_BANDS = [
    (0, 9, -0.5, -0.5),
    (9, 12, 0.5, 0.0),
    (12, 13, 0.0, 0.0),
    (13, 15, -1.0, -0.5),
    (15, 18, 0.0, 0.5),
    (18, 21, -0.5, 0.0),
    (21, 24, -1.5, -1.0),
]
BAND_NAMES = ["before 09:00", "09-12", "12-13", "13-15", "15-18", "18-21", "after 21:00"]
DEFAULT_LEVELS = {"mental": 6.0, "physical": 5.0, "focus": 6.0, "stress": 4.0}
SHRINK = 5.0  # pseudo-count given to the default offsets


def band_index(t: time | datetime) -> int:
    hour = t.hour + t.minute / 60
    for i, (lo, hi, _, _) in enumerate(DEFAULT_BANDS):
        if lo <= hour < hi:
            return i
    return len(DEFAULT_BANDS) - 1


def clip(v: float) -> float:
    return max(0.0, min(10.0, v))


@dataclass
class EnergyProfile:
    mental_offsets: list[float]
    physical_offsets: list[float]
    counts: list[int] = field(default_factory=lambda: [0] * len(DEFAULT_BANDS))

    @property
    def is_learned(self) -> bool:
        return sum(self.counts) >= 5

    def offset(self, t: time | datetime) -> tuple[float, float]:
        i = band_index(t)
        return self.mental_offsets[i], self.physical_offsets[i]

    def as_dict(self) -> dict:
        return {
            "bands": BAND_NAMES,
            "mental": [round(x, 2) for x in self.mental_offsets],
            "physical": [round(x, 2) for x in self.physical_offsets],
            "counts": self.counts,
            "learned": self.is_learned,
        }


def default_profile() -> EnergyProfile:
    return EnergyProfile([b[2] for b in DEFAULT_BANDS], [b[3] for b in DEFAULT_BANDS])


def learn_profile(history: list[CheckIn]) -> EnergyProfile:
    """Blend default offsets with the user's own band averages.

    learned offset for a band = (mean value in that band) - (mean of all check-ins).
    final offset = (SHRINK x default + n x learned) / (SHRINK + n)
    """
    prof = default_profile()
    if len(history) < 2:
        return prof
    overall_m = sum(c.mental for c in history) / len(history)
    overall_p = sum(c.physical for c in history) / len(history)
    for i in range(len(DEFAULT_BANDS)):
        in_band = [c for c in history if band_index(c.recorded_at) == i]
        n = len(in_band)
        prof.counts[i] = n
        if n == 0:
            continue
        lm = sum(c.mental for c in in_band) / n - overall_m
        lp = sum(c.physical for c in in_band) / n - overall_p
        dm, dp = DEFAULT_BANDS[i][2], DEFAULT_BANDS[i][3]
        prof.mental_offsets[i] = (SHRINK * dm + n * lm) / (SHRINK + n)
        prof.physical_offsets[i] = (SHRINK * dp + n * lp) / (SHRINK + n)
    return prof


@dataclass
class DayState:
    """The energy reading used as the anchor for one day."""

    mental: float
    physical: float
    focus: float
    stress: float
    anchor_time: time
    source: str  # "check-in" or "forecast"


def forecast_state(history: list[CheckIn], profile: EnergyProfile) -> DayState:
    """Baseline for a day without a check-in: band-neutral mean of the last 7."""
    recent = history[-7:]
    if not recent:
        d = DEFAULT_LEVELS
        return DayState(d["mental"], d["physical"], d["focus"], d["stress"], time(12, 30), "forecast")
    ms, ps = [], []
    for c in recent:
        om, op = profile.offset(c.recorded_at)
        ms.append(c.mental - om)
        ps.append(c.physical - op)
    n = len(recent)
    return DayState(
        sum(ms) / n,
        sum(ps) / n,
        sum(c.focus for c in recent) / n,
        sum(c.stress for c in recent) / n,
        time(12, 30),  # band with zero offset, so values are already neutral
        "forecast",
    )


def state_for_day(day, history: list[CheckIn], profile: EnergyProfile) -> DayState:
    """Use the latest check-in recorded on that day, otherwise a forecast."""
    same_day = [c for c in history if c.recorded_at.date() == day]
    if same_day:
        c = same_day[-1]
        return DayState(c.mental, c.physical, c.focus, c.stress, c.recorded_at.time(), "check-in")
    return forecast_state(history, profile)


def project(state: DayState, profile: EnergyProfile, slot_time: time) -> tuple[float, float]:
    """Mental and physical energy expected at slot_time.

    slot value = anchor value - offset(anchor time) + offset(slot time), clipped to 0-10.
    """
    am, ap = profile.offset(state.anchor_time)
    sm, sp = profile.offset(slot_time)
    return clip(state.mental - am + sm), clip(state.physical - ap + sp)
