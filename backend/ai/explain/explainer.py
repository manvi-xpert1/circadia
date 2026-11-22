"""Explanation module (design section 3.2, module 6).

Template-based, expert-system style explanations: every sentence is built
from numbers the algorithms actually used (fuzzy rule strengths, duration
estimates, probabilities, rules applied). Nothing here is generated text.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from ..fuzzy.engine import RULE_TEXT, suitability
from ..fuzzy.membership import suitability_label
from ..ga.decoder import BLOCKED, DEPENDENCY, LEFT_OUT, NO_ROOM, decode
from ..ga.fitness import evaluate, on_time_table, weights_for
from ..ga.runner import GAResult, best_fit_hints
from ..problem import SLOT, Problem, TaskInfo
from ..rules import soft_rules as sr
from ..types import PRIORITY_NAMES

PART_NAMES = {
    "pri": "priority coverage",
    "dl": "deadline safety",
    "en": "energy fit",
    "dur": "realistic durations",
    "pref": "your break and late-work preferences",
    "over": "overload",
    "cs": "context switching",
    "bal": "day balance",
    "stab": "keeping your existing plan",
}


def hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def when(p: Problem, dt: datetime) -> str:
    d = (dt.date() - p.day0).days
    day = "today" if d == 0 else "tomorrow" if d == 1 else dt.strftime("%a %d %b")
    return f"{day} {hm(dt)}"


def span(minutes: float) -> str:
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    if h < 24:
        return f"{h} h {m} min" if m else f"{h} h"
    d, h = divmod(h, 24)
    return f"{d} day{'s' if d > 1 else ''} {h} h" if h else f"{d} day{'s' if d > 1 else ''}"


def duration_text(ti: TaskInfo) -> str:
    t, dur = ti.task, ti.dur
    pct = round((dur.ratio - 1) * 100)
    trend = f"about {abs(pct)}% {'over' if pct >= 0 else 'under'}"
    done = f" ({t.minutes_done} min already done)" if t.minutes_done else ""
    est = int(ti.est)
    if dur.source == "learned":
        return f"Planned {ti.planned_minutes} min, not {est}: your last {dur.n} {t.category} tasks ran {trend}{done}."
    if dur.source == "pooled":
        return (
            f"Planned {ti.planned_minutes} min for a {est}-min estimate: across your {dur.n} recorded tasks you run {trend}. "
            f"{t.category} has fewer than 3 records of its own{done}."
        )
    return (
        f"Planned {ti.planned_minutes} min for a {est}-min estimate: default assumption of a 15% overrun plus slack "
        f"until you record 3 finished tasks{done}."
    )


def _free_mask(p: Problem, starts, lengths, skip: int) -> np.ndarray:
    mask = np.zeros(p.G, dtype=bool)
    for a, b in p.intervals:
        mask[a:b] = True
    for j, s in enumerate(starts):
        if s >= 0 and j != skip:
            mask[s : s + lengths[j]] = False
    return mask


def next_best(p: Problem, i: int, starts, lengths) -> dict | None:
    """The best other legal start for this block if everything else stays put."""
    ti = p.tasks[i]
    L = lengths[i]
    mask = _free_mask(p, starts, lengths, i)
    earliest = ti.dep_earliest
    if ti.dep_idx is not None and starts[ti.dep_idx] >= 0:
        earliest = max(earliest, starts[ti.dep_idx] + lengths[ti.dep_idx])
    latest_end = ti.dl_end
    for j, tj in enumerate(p.tasks):  # must still finish before anything that depends on it
        if tj.dep_idx == i and starts[j] >= 0:
            latest_end = min(latest_end, starts[j])
    best = None
    for g in range(earliest, min(p.G, latest_end) - L + 1):
        if abs(g - starts[i]) < 4 or p.day_of(g) != p.day_of(g + L - 1) or not mask[g : g + L].all():
            continue
        f = p.block_fit(i, g, L)
        if best is None or f > best[1] + 1e-9:
            best = (g, f)
    if best is None:
        return None
    return {"start": p.slot_dt(best[0]).isoformat(), "label": when(p, p.slot_dt(best[0])), "fit": round(best[1], 2)}


def explain_block(p: Problem, i: int, res: GAResult, flags: dict) -> dict:
    ti = p.tasks[i]
    t = ti.task
    s = res.decoded.starts[i]
    L = res.decoded.lengths[i]
    start = p.slot_dt(s)
    end = start + timedelta(minutes=ti.planned_minutes)
    fit = p.block_fit(i, s, L)
    label = suitability_label(fit)
    cap = float(p.cap[s])
    mental, physical = p.slot_energy(s)
    trace = suitability(round(cap - t.mental_demand, 2), round(physical - t.physical_demand, 2))
    fired = [
        {"id": f.rule, "strength": round(f.strength, 2), "text": RULE_TEXT[f.rule]}
        for f in sorted(trace.fired, key=lambda f: -f.strength)
    ]
    state = p.day_states[p.day_of(s)]
    p_on_time = float(on_time_table(p)[i, s]) if t.deadline else None

    rules: list[str] = []
    for c in p.req.commitments:
        if c.start.date() != start.date():
            continue
        if timedelta(0) <= start - c.end <= timedelta(minutes=30) or timedelta(0) <= c.start - end <= timedelta(minutes=30):
            rid = "H2" if c.kind == "fixed" else "H3"
            rules.append(f"Fits around {c.label} {hm(c.start)}–{hm(c.end)} ({rid})")
    if ti.dep_idx is not None:
        rules.append(f"After its prerequisite \"{p.tasks[ti.dep_idx].task.title}\" ({'H5'})")
    if t.deadline:
        rules.append(f"Finishes {span((t.deadline - end).total_seconds() / 60)} before its deadline (H7)")

    warnings: list[str] = []
    if fit < 0.35:
        warnings.append("Low energy fit for this task (A3); expect it to feel harder.")
    if s in flags["a1"]:
        warnings.append("Part of a long run of work with no break (A1); consider a short pause before it.")
    if s in flags["a7"]:
        warnings.append("Ends after your 'no work after' time (A7).")
    if s in flags["a6"]:
        warnings.append("Back-to-back with another mentally heavy task (A6).")
    if state.source == "forecast":
        warnings.append("Energy for this day is a forecast; check in that morning to refine the plan.")

    # One-sentence verdict: name the factor that mattered most.
    slack_h = (t.deadline - end).total_seconds() / 3600 if t.deadline else None
    if slack_h is not None and slack_h < 24:
        verdict = f"Placed {when(p, start)} so it finishes {span(slack_h * 60)} before its deadline."
    elif fit >= 0.7:
        verdict = (
            f"Placed {when(p, start)} because your expected capacity then ({cap:.1f}/10) "
            f"matches what this task needs ({t.mental_demand:.1f}/10)."
        )
    elif fit < 0.45:
        verdict = f"Placed {when(p, start)} because no better-fitting free time was left; the fit is only {label.lower()}."
    else:
        verdict = f"Placed {when(p, start)}, a {label.lower()} fit ({fit:.2f}) at the best time left after higher-priority work."

    return {
        "task_id": t.id,
        "title": t.title,
        "category": t.category,
        "priority": t.priority,
        "priority_name": PRIORITY_NAMES.get(t.priority, ""),
        "kind": "ai",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "day": p.day_of(s),
        "planned_minutes": ti.planned_minutes,
        "est_minutes": int(ti.est),
        "fit": round(fit, 2),
        "fit_label": label,
        "capacity": round(cap, 2),
        "mental_demand": t.mental_demand,
        "physical_demand": t.physical_demand,
        "slot_mental": round(mental, 1),
        "slot_physical": round(physical, 1),
        "energy_source": state.source,
        "fired_rules": fired,
        "duration": {**ti.dur.as_dict(), "text": duration_text(ti), "p80": round(ti.p80, 1)},
        "p_complete": round(ti.p_complete, 2),
        "p_on_time": round(p_on_time, 2) if p_on_time is not None else None,
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "rules_applied": rules,
        "warnings": warnings,
        "next_best": next_best(p, i, res.decoded.starts, res.decoded.lengths),
        "verdict": verdict,
    }


def explain_left_out(p: Problem, i: int, res: GAResult, preset: str) -> str:
    """Counterfactual: put the task back in and see which score parts get worse."""
    hints = res.hints.copy()
    hints[i] = best_fit_hints(p)[i]
    dec = decode(p, res.order, hints)
    if dec.starts[i] < 0:
        return no_room_text(p, p.tasks[i])
    with_it = evaluate(p, dec.starts, dec.lengths, preset)
    if with_it.total > res.score.total:
        return "The optimiser did not include it in this run, although a place exists. Regenerate, or lock it in yourself."
    w = weights_for(p, preset)
    losses = []
    for k, v in with_it.parts.items():
        delta = v - res.score.parts[k]
        signed = -delta if k in ("over", "cs", "bal", "stab") else delta
        if signed < -1e-6:
            losses.append((w[k] * signed, k))
    losses.sort()
    worst = " and ".join(PART_NAMES[k] for _, k in losses[:2]) or "the overall score"
    return f"Left out to keep the plan realistic: adding it would worsen {worst}."


def no_room_text(p: Problem, ti: TaskInfo) -> str:
    if ti.dl_end < p.G and ti.task.deadline:
        return (
            f"No free gap of {ti.planned_minutes} min is left before its deadline "
            f"({when(p, ti.task.deadline)}) once higher-priority work is placed."
        )
    return f"No free gap of {ti.planned_minutes} min is left in the next {p.horizon} day{'s' if p.horizon > 1 else ''} once higher-priority work is placed."


def explain_unscheduled(p: Problem, res: GAResult, preset: str) -> list[dict]:
    out = []
    for t, code, text in p.unschedulable:
        out.append(_unsched(t, code, text, None))
    for i, code in res.decoded.reasons.items():
        ti = p.tasks[i]
        if code == BLOCKED:
            text = ti.blocked_reason or "Cannot be scheduled."
        elif code == DEPENDENCY:
            text = f"Waits for \"{p.tasks[ti.dep_idx].task.title}\", which is not in this plan." if ti.dep_idx is not None else "Waits for a prerequisite."
        elif code == NO_ROOM:
            text = no_room_text(p, ti)
        elif code == LEFT_OUT:
            text = explain_left_out(p, i, res, preset)
        else:
            text = code
        out.append(_unsched(ti.task, code, text, ti.planned_minutes))
    order = {4: 0, 3: 1, 2: 2, 1: 3}
    out.sort(key=lambda u: (order.get(u["priority"], 9), u["deadline"] or "9999"))
    return out


def _unsched(t, code, text, planned):
    return {
        "task_id": t.id,
        "title": t.title,
        "category": t.category,
        "priority": t.priority,
        "priority_name": PRIORITY_NAMES.get(t.priority, ""),
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "planned_minutes": planned,
        "code": code,
        "reason": text,
    }


def soft_flags(p: Problem, starts, lengths) -> dict:
    from ..ga.fitness import grid_blocks

    blocks = grid_blocks(p, starts, lengths)
    prefs = p.req.prefs
    late_limit = int(
        ((prefs.no_work_after.hour * 60 + prefs.no_work_after.minute) - (prefs.day_start.hour * 60 + prefs.day_start.minute))
        // SLOT
    )
    heavy: set[int] = set()
    for x, y in sr.adjacent_pairs(blocks, p.npd):
        if x.mental_demand >= 7 and y.mental_demand >= 7:
            heavy.add(y.start)
    return {
        "a1": sr.a1_focus_runs(blocks, p.npd, prefs.max_focus_block),
        "a7": sr.a7_late([b for b in blocks if b.key >= 0], p.npd, late_limit),
        "a6": heavy,
    }
