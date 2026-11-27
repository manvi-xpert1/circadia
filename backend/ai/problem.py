"""Builds the scheduling problem on a 15-minute grid (design section 3.3d).

Each day of the horizon is cut into 15-minute slots between day_start and
day_end; all slots are numbered in one sequence (g = day * slots_per_day + k).
This module turns raw inputs into everything the optimiser looks up:
free intervals, block lengths, deadline limits, dependencies and the matrix
U[task, slot] = P(the block happens if it starts in that slot), from the
contextual completion model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cached_property
from datetime import date, datetime, time, timedelta

import numpy as np

from .probability.completion import FEATURES, FOCUS_CENTRE, FOCUS_SCALE, STRESS_CENTRE, STRESS_SCALE, CompletionModel, context_features
from .probability.duration_model import DurationEstimate, DurationModel
from .probability.energy_profile import DayState, EnergyProfile, learn_profile, project, state_for_day
from .types import PlanRequest, TaskIn

SLOT = 15  # minutes


def ceil_to(minutes: float, step: int) -> int:
    return int(math.ceil(minutes / step) * step)


@dataclass
class TaskInfo:
    """Everything the optimiser needs to know about one movable task."""

    task: TaskIn
    idx: int
    est: float  # minutes still to do (estimate minus minutes already spent)
    dur: DurationEstimate
    p80: float  # predicted 80th-percentile duration (a prediction, not a reservation)
    planned_minutes: int  # time reserved for the block: the reservation quantile, rounded up to 5 minutes
    slots_p80: int
    slots_est: int
    follow: float  # P(a block of this task happens) at an average time, from the completion model
    dl_end: int  # latest allowed end slot (exclusive index); G when no deadline in horizon
    dep_idx: int | None = None  # index of a movable task this one depends on
    dep_earliest: int = 0  # earliest start because of a fixed / locked dependency
    blocked_reason: str | None = None  # set when the task can't be scheduled at all
    blocked_by_room: bool = False  # True when the pre-check found no gap long enough for P80

    @cached_property
    def p_fits(self) -> float:
        """P(the work fits the reserved block), from the duration model."""
        return self.dur.p_fits(self.planned_minutes, self.est)

    @cached_property
    def p_complete(self) -> float:
        """P(happens) x P(fits), at an average time; block-specific values use U."""
        return self.follow * self.p_fits


@dataclass
class FixedBlock:
    task: TaskIn
    start: datetime
    end: datetime
    start_slot: int
    end_slot: int
    kind: str  # "fixed-task" or "locked"


@dataclass
class Problem:
    req: PlanRequest
    day0: date
    horizon: int
    npd: int  # slots per day
    G: int
    day_start_dt: list[datetime]
    intervals: list[tuple[int, int]]  # free [a, b) slot intervals, never crossing a day
    day_free_minutes: list[int]
    tasks: list[TaskInfo]
    fixed_blocks: list[FixedBlock]
    unschedulable: list[tuple[TaskIn, str, str]]  # task, code, text
    U: np.ndarray  # n x G: P(the block happens) if it runs in that slot
    Ucs: np.ndarray  # n x (G+1) cumulative sums, for block averages
    cap: np.ndarray  # projected mental energy per slot, 0-10
    day_states: list[DayState]
    profile: EnergyProfile
    durations: DurationModel
    completion: CompletionModel
    warnings: list[str] = field(default_factory=list)
    prev_slot: list[int | None] = field(default_factory=list)  # previous plan's start slot per task, if any
    stability: float = 0.0  # 0-1, from the request

    @property
    def has_previous(self) -> bool:
        return any(s is not None for s in self.prev_slot)

    # ---- time helpers -------------------------------------------------------
    def slot_dt(self, g: int) -> datetime:
        d, k = divmod(g, self.npd)
        return self.day_start_dt[d] + timedelta(minutes=SLOT * k)

    def day_of(self, g: int) -> int:
        return g // self.npd

    def block_fit(self, i: int, start: int, length: int) -> float:
        return float((self.Ucs[i, start + length] - self.Ucs[i, start]) / length)

    def slot_energy(self, g: int) -> tuple[float, float]:
        """Projected (mental, physical) energy at slot g."""
        st = self.day_states[self.day_of(g)]
        return project(st, self.profile, self.slot_dt(g).time())

    def stress_cap_day0(self) -> bool:
        s = self.day_states[0]
        return s.source == "check-in" and s.stress >= 8


def _floor_slot(p_day_start: datetime, t: datetime) -> int:
    return math.floor((t - p_day_start).total_seconds() / 60 / SLOT)


def _ceil_slot(p_day_start: datetime, t: datetime) -> int:
    return math.ceil((t - p_day_start).total_seconds() / 60 / SLOT)


def build_problem(req: PlanRequest) -> Problem:
    prefs = req.prefs
    horizon = max(1, min(7, prefs.horizon_days))
    day0 = req.now.date()
    ds = datetime.combine(day0, prefs.day_start)
    de = datetime.combine(day0, prefs.day_end)
    npd = int((de - ds).total_seconds() // 60 // SLOT)
    if npd <= 0:
        raise ValueError("day_end must be after day_start")
    G = horizon * npd
    day_start_dt = [ds + timedelta(days=d) for d in range(horizon)]

    free = np.ones(G, dtype=bool)

    def block_out(start: datetime, end: datetime):
        for d in range(horizon):
            a = max(0, _floor_slot(day_start_dt[d], start))
            b = min(npd, _ceil_slot(day_start_dt[d], end))
            if b > a:
                free[d * npd + a : d * npd + b] = False

    # Past time on day 0 (round "now" up to the next slot).
    past = min(npd, max(0, _ceil_slot(day_start_dt[0], req.now)))
    free[:past] = False

    for c in req.commitments:
        block_out(c.start, c.end)

    # Fixed tasks and locked blocks occupy time but are not optimised.
    fixed_blocks: list[FixedBlock] = []
    by_id = {t.id: t for t in req.tasks}
    locked = {tid: start for tid, start in req.locked}
    unschedulable: list[tuple[TaskIn, str, str]] = []

    durations = DurationModel(req.outcomes, version=req.duration_version)
    completion = CompletionModel(req.outcomes)

    def est_left(t: TaskIn) -> float:
        return max(float(t.est_minutes - t.minutes_done), 15.0)

    def slot_range(start: datetime, end: datetime):
        d = (start.date() - day0).days
        if not (0 <= d < horizon):
            return None
        a = _floor_slot(day_start_dt[d], start)
        b = _ceil_slot(day_start_dt[d], end)
        return d * npd + max(0, a), d * npd + min(npd, b)

    for t in req.tasks:
        if t.is_fixed and t.fixed_start and t.fixed_end:
            rng = slot_range(t.fixed_start, t.fixed_end)
            block_out(t.fixed_start, t.fixed_end)
            if rng:
                fixed_blocks.append(FixedBlock(t, t.fixed_start, t.fixed_end, rng[0], rng[1], "fixed-task"))
        elif t.id in locked:
            dur = durations.for_category(t.category)
            minutes = ceil_to(dur.p80(est_left(t)), 5)
            start = locked[t.id]
            end = start + timedelta(minutes=minutes)
            rng = slot_range(start, end)
            block_out(start, end)
            if rng:
                fixed_blocks.append(FixedBlock(t, start, end, rng[0], rng[1], "locked"))

    # Shared daily buffer: keep the last part of each day's free time empty, for overruns.
    if req.day_buffer > 0:
        for d in range(horizon):
            idx = np.flatnonzero(free[d * npd : (d + 1) * npd])
            k = int(math.ceil(req.day_buffer * len(idx)))
            if k:
                free[d * npd + idx[-k:]] = False

    # Free intervals, split at day boundaries.
    intervals: list[tuple[int, int]] = []
    day_free_minutes = []
    for d in range(horizon):
        seg = free[d * npd : (d + 1) * npd]
        day_free_minutes.append(int(seg.sum()) * SLOT)
        k = 0
        while k < npd:
            if seg[k]:
                j = k
                while j < npd and seg[j]:
                    j += 1
                intervals.append((d * npd + k, d * npd + j))
                k = j
            else:
                k += 1
    # Fixed-task minutes count as available working time for load purposes.
    for fb in fixed_blocks:
        d = fb.start_slot // npd
        day_free_minutes[d] += (fb.end_slot - fb.start_slot) * SLOT

    # Movable tasks.
    fixed_ids = {fb.task.id for fb in fixed_blocks}
    fixed_end_slot = {fb.task.id: fb.end_slot for fb in fixed_blocks}
    infos: list[TaskInfo] = []
    for t in req.tasks:
        if t.is_fixed or t.id in fixed_ids:
            continue
        est = est_left(t)
        dur = durations.for_category(t.category)
        p80 = dur.p80(est)
        reserved = est if "no_probability" in req.ablations else dur.quantile(est, req.reserve_quantile)
        planned = ceil_to(reserved, 5)
        slots_p80 = max(1, math.ceil(planned / SLOT))
        slots_est = max(1, math.ceil(est / SLOT))
        # Deadline -> latest allowed end slot.
        dl_end = G
        if t.deadline is not None:
            if t.deadline <= req.now:
                unschedulable.append((t, "DEADLINE_PASSED", "The deadline has already passed. Update the deadline or mark it done."))
                continue
            d = (t.deadline.date() - day0).days
            if d < horizon:
                k = _floor_slot(day_start_dt[d], t.deadline)
                dl_end = d * npd + min(npd, max(0, k))
        infos.append(
            TaskInfo(
                task=t,
                idx=len(infos),
                est=est,
                dur=dur,
                p80=p80,
                planned_minutes=planned,
                slots_p80=slots_p80,
                slots_est=slots_est,
                follow=completion.predict(t.category, completion.fill).p,
                dl_end=dl_end,
            )
        )

    # Release times (rule H9): a task may not start before its not_before time.
    for ti in infos:
        nb = ti.task.not_before
        if nb is None:
            continue
        d = (nb.date() - day0).days
        if d >= horizon:
            ti.blocked_reason = "Its day is after the planning horizon."
        elif d >= 0:
            ti.dep_earliest = max(ti.dep_earliest, d * npd + min(npd, max(0, _ceil_slot(day_start_dt[d], nb))))

    # Dependencies (rule H5).
    pos = {ti.task.id: ti.idx for ti in infos}
    for ti in infos:
        dep = ti.task.depends_on
        if dep is None:
            continue
        if dep in pos:
            ti.dep_idx = pos[dep]
        elif dep in fixed_end_slot:
            ti.dep_earliest = fixed_end_slot[dep]
        elif dep in by_id:
            # The prerequisite exists but cannot be scheduled (e.g. its deadline passed).
            ti.blocked_reason = f"Waits for \"{by_id[dep].title}\", which cannot be scheduled."
        # dep not in by_id: prerequisite already done (only pending tasks are sent).
    # Cycle detection.
    for ti in infos:
        seen = set()
        cur = ti
        while cur.dep_idx is not None:
            if cur.idx in seen:
                ti.blocked_reason = "Its prerequisites form a circle (A waits for B, B waits for A)."
                break
            seen.add(cur.idx)
            cur = infos[cur.dep_idx]

    # Projected energy per slot, then P(block happens) for every task and slot.
    profile = learn_profile(req.checkins)
    day_states = [state_for_day(day0 + timedelta(days=d), req.checkins, profile) for d in range(horizon)]
    n = len(infos)
    mental = np.zeros(G)
    physical = np.zeros(G)
    focus = np.zeros(G)
    stress = np.zeros(G)
    for g in range(G):
        d = g // npd
        st = day_states[d]
        slot_time = (day_start_dt[d] + timedelta(minutes=SLOT * (g % npd))).time()
        mental[g], physical[g] = project(st, profile, slot_time)
        focus[g], stress[g] = st.focus, st.stress
    cap = mental.copy()
    if "fuzzy_reference" in req.ablations:  # evaluation only: the fuzzy score the completion model replaced
        from .evaluation.fuzzy_reference import suitability_matrix

        U = suitability_matrix(infos, mental, physical, focus, stress)
    else:
        U = completion_matrix(completion, infos, mental, physical, focus, stress, neutral="no_context" in req.ablations)
    Ucs = np.concatenate([np.zeros((n, 1)), np.cumsum(U, axis=1)], axis=1) if n else np.zeros((0, G + 1))

    prob = Problem(
        req=req,
        day0=day0,
        horizon=horizon,
        npd=npd,
        G=G,
        day_start_dt=day_start_dt,
        intervals=intervals,
        day_free_minutes=day_free_minutes,
        tasks=infos,
        fixed_blocks=fixed_blocks,
        unschedulable=unschedulable,
        U=U,
        Ucs=Ucs,
        cap=cap,
        day_states=day_states,
        profile=profile,
        durations=durations,
        completion=completion,
    )
    _precheck(prob)
    _map_previous(prob)
    return prob


def completion_matrix(model: CompletionModel, infos: list[TaskInfo], mental: np.ndarray, physical: np.ndarray,
                      focus: np.ndarray, stress: np.ndarray, neutral: bool = False) -> np.ndarray:
    """U[i, g] = P(task i's block happens if it starts in slot g).

    neutral=True (an evaluation ablation) ignores the context: every slot gets the
    task's average-context probability, so only the category and duration matter.
    """
    n, G = len(infos), len(mental)
    if n == 0:
        return np.zeros((0, G))
    if neutral:
        return np.array([[ti.follow] * G for ti in infos])
    ctx = np.zeros((n, G, len(FEATURES)))
    for ti in infos:
        t = ti.task
        ctx[ti.idx, :, 0] = 1.0
        ctx[ti.idx, :, 1] = np.maximum(0.0, t.mental_demand - mental)
        ctx[ti.idx, :, 2] = np.maximum(0.0, t.physical_demand - physical)
        ctx[ti.idx, :, 3] = (focus - FOCUS_CENTRE) / FOCUS_SCALE
        ctx[ti.idx, :, 4] = (stress - STRESS_CENTRE) / STRESS_SCALE
        ctx[ti.idx, :, 5] = context_features(0, 0, 0, 0, FOCUS_CENTRE, STRESS_CENTRE, ti.est)[5]
    return model.predict_matrix([ti.task.category for ti in infos], ctx)


def _map_previous(p: Problem) -> None:
    """Translate the previous plan's (task_id, start) pairs into grid slots for stability scoring.

    Only future blocks of tasks that are still movable count; a previous start that is
    no longer on the grid (in the past, or outside the horizon) is ignored.
    """
    p.prev_slot = [None] * len(p.tasks)
    p.stability = max(0.0, min(1.0, float(p.req.stability)))
    if not p.req.previous:
        return
    pos = {ti.task.id: ti.idx for ti in p.tasks}
    for tid, start in p.req.previous:
        i = pos.get(tid)
        if i is None or start < p.req.now:
            continue
        d = (start.date() - p.day0).days
        if not (0 <= d < p.horizon):
            continue
        k = _floor_slot(p.day_start_dt[d], start)
        if 0 <= k < p.npd:
            p.prev_slot[i] = d * p.npd + k


def _precheck(p: Problem) -> None:
    """Rule pre-check: warn early when deadline work cannot fit (design 3.3c)."""
    total_free = sum(b - a for a, b in p.intervals) * SLOT
    due = [ti for ti in p.tasks if ti.dl_end < p.G]
    need = sum(ti.planned_minutes for ti in due)
    if need > total_free:
        p.warnings.append(
            f"Tasks due inside the horizon need about {need} min, but only {total_free} min are free. "
            "Some will be left unscheduled."
        )
    for ti in p.tasks:
        if ti.blocked_reason:
            continue
        room = sum(max(0, min(b, ti.dl_end) - max(a, ti.dep_earliest)) for a, b in p.intervals)
        longest = max((min(b, ti.dl_end) - max(a, ti.dep_earliest) for a, b in p.intervals), default=0)
        if ti.dl_end < p.G and longest < ti.slots_p80:
            ti.blocked_by_room = True
            ti.blocked_reason = (
                f"No free gap of {ti.planned_minutes} min exists before its deadline "
                f"({room * SLOT} min free in total, but not in one piece)."
                if room * SLOT >= ti.planned_minutes
                else f"Needs about {ti.planned_minutes} min, but only {room * SLOT} min are free before the deadline."
            )
