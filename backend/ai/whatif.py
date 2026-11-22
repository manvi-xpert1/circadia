"""What-if simulator (design: page 6).

Plans twice with the same seed: once as things are, once with the scenario
applied. Because the seed is shared, every difference comes from the scenario,
not from the genetic algorithm's randomness. Then it compares the two plans and
explains what changed in plain sentences built from the numbers.
"""
from __future__ import annotations

import copy
import statistics
from dataclasses import replace
from datetime import datetime, timedelta

from .fuzzy.profile import learn_profile, state_for_day
from .pipeline import plan
from .types import CheckIn, Commitment, PlanRequest, TaskIn

URGENT_ID = -1


def _clip(v: float) -> int:
    return int(max(1, min(10, round(v))))


def apply_scenario(req: PlanRequest, sc: dict) -> tuple[PlanRequest, list[str]]:
    """Return a modified copy of the request and one sentence per change applied."""
    r = copy.deepcopy(req)
    notes: list[str] = []
    day0 = r.now.date()

    late = int(sc.get("late_start_minutes") or 0)
    if late > 0:
        start = max(r.now, datetime.combine(day0, r.prefs.day_start))
        r.now = start + timedelta(minutes=late)
        notes.append(f"You start today at {r.now:%H:%M} instead of {start:%H:%M}.")

    lose = sc.get("lose_time")
    if lose:
        day = day0 + timedelta(days=int(lose.get("day", 0)))
        s = datetime.combine(day, datetime.strptime(lose["start"], "%H:%M").time())
        e = datetime.combine(day, datetime.strptime(lose["end"], "%H:%M").time())
        if e > s:
            r.commitments.append(Commitment(s, e, lose.get("label") or "Lost time", "unavailable"))
            notes.append(f"You lose {lose['start']}–{lose['end']} on {day:%a %d %b}.")

    delta = int(sc.get("energy_delta") or 0)
    if delta:
        st = state_for_day(day0, r.checkins, learn_profile(r.checkins))
        r.checkins.append(CheckIn(r.now, _clip(st.mental + delta), _clip(st.physical + delta),
                                  _clip(st.focus + delta), _clip(st.stress - delta / 2)))
        notes.append(f"Your energy today is {abs(delta)} point{'s' if abs(delta) != 1 else ''} {'lower' if delta < 0 else 'higher'} than expected.")

    urgent = sc.get("urgent_task")
    if urgent:
        md = int(urgent.get("mental", 6))
        pd = int(urgent.get("physical", 2))
        r.tasks.append(TaskIn(
            id=URGENT_ID, title=urgent.get("title") or "Urgent task", category=urgent.get("category") or "Work",
            priority=int(urgent.get("priority", 4)), est_minutes=int(urgent.get("est_minutes", 60)),
            mental_difficulty=md, mental_req=md, physical_difficulty=pd, physical_req=pd,
            deadline=r.now + timedelta(hours=float(urgent.get("deadline_hours", 6))),
        ))
        hours = float(urgent.get("deadline_hours", 6))
        notes.append(f"An urgent task \"{r.tasks[-1].title}\" ({r.tasks[-1].est_minutes} min) is due in {hours:g} h.")

    ext = sc.get("extend_task")
    if ext:
        for i, t in enumerate(r.tasks):
            if t.id == int(ext["task_id"]):
                extra = int(ext.get("extra_minutes", 30))
                r.tasks[i] = replace(t, est_minutes=min(480, t.est_minutes + extra))
                notes.append(f"\"{t.title}\" takes {extra} min longer than you estimated.")
                break
    return r, notes


def _blocks(plan_out: dict) -> dict[int, dict]:
    return {b["task_id"]: b for b in plan_out["plans"][0]["blocks"]}


def _summary(out: dict) -> dict:
    pl = out["plans"][0]
    blocks = pl["blocks"]
    on_time = [b["p_on_time"] for b in blocks if b.get("p_on_time") is not None]
    rob = pl.get("robustness") or {}
    return {
        "expected_completed": rob.get("expected_completed"),
        "deadline_safety_mc": rob.get("deadline_safety"),
        "stability": pl.get("stability"),
        "tasks_planned": len(blocks),
        "not_planned": len(pl["unscheduled"]),
        "avg_fit": round(statistics.fmean(b["fit"] for b in blocks), 3) if blocks else 0.0,
        "deadline_safety": round(statistics.fmean(on_time), 3) if on_time else None,
        "busiest_day_load": round(max((d["load"] for d in pl["day_load"]), default=0), 3),
        "today_minutes": sum(b["planned_minutes"] for b in blocks if b["day"] == 0),
        "fitness": pl["fitness"],
    }


def _lite(out: dict) -> dict:
    """Only what the comparison view needs."""
    keep = ("task_id", "title", "category", "start", "end", "day", "fit", "fit_label", "planned_minutes", "priority")
    return {
        "days": [{"day": d["day"], "date": d["date"], "free_minutes": d["free_minutes"], "energy_source": d["energy_source"]} for d in out["days"]],
        "blocks": [{k: b.get(k) for k in keep} for b in out["plans"][0]["blocks"]],
        "fixed": out["fixed"],
        "commitments": out["commitments"],
        "unscheduled": out["plans"][0]["unscheduled"],
        "summary": _summary(out),
    }


def compare(before: dict, after: dict) -> dict:
    b, a = _blocks(before), _blocks(after)
    after_unsched = {u["task_id"]: u for u in after["plans"][0]["unscheduled"]}
    moved, added, dropped = [], [], []
    unchanged = 0
    for tid, blk in a.items():
        if tid not in b:
            added.append({"task_id": tid, "title": blk["title"], "to": blk["start"], "to_day": blk["day"]})
        elif blk["start"] != b[tid]["start"]:
            moved.append({"task_id": tid, "title": blk["title"], "from": b[tid]["start"], "to": blk["start"],
                          "from_day": b[tid]["day"], "to_day": blk["day"]})
        else:
            unchanged += 1
    for tid, blk in b.items():
        if tid not in a:
            u = after_unsched.get(tid)
            dropped.append({"task_id": tid, "title": blk["title"], "from": blk["start"],
                            "reason": u["reason"] if u else "Not in the new plan."})
    moved.sort(key=lambda m: m["to"])
    return {"moved": moved, "added": added, "dropped": dropped, "unchanged": unchanged}


def explain(notes: list[str], before: dict, after: dict, diff: dict) -> list[str]:
    sb, sa = _summary(before), _summary(after)
    lines = list(notes)
    free_b = before["days"][0]["free_minutes"]
    free_a = after["days"][0]["free_minutes"]
    if free_a != free_b:
        lines.append(f"Free time today goes from {free_b} to {free_a} min.")
    cap_b = statistics.fmean(before["days"][0]["capacity"])
    cap_a = statistics.fmean(after["days"][0]["capacity"])
    if abs(cap_a - cap_b) >= 0.05:
        lines.append(f"Your expected mental capacity today averages {cap_a:.1f}/10 instead of {cap_b:.1f}.")
    later = [m for m in diff["moved"] if m["to_day"] > m["from_day"]]
    if diff["moved"]:
        lines.append(
            f"{len(diff['moved'])} task{'s' if len(diff['moved']) != 1 else ''} moved"
            + (f", {len(later)} of them to a later day" if later else "") + "."
        )
    for d in diff["dropped"]:
        lines.append(f"\"{d['title']}\" no longer fits: {d['reason']}")
    urgent_blk = _blocks(after).get(URGENT_ID)
    if urgent_blk:
        start = datetime.fromisoformat(urgent_blk["start"])
        when = "today" if urgent_blk["day"] == 0 else "tomorrow" if urgent_blk["day"] == 1 else f"on {start:%a %d %b}"
        slack = ""
        if urgent_blk.get("deadline"):
            mins = (datetime.fromisoformat(urgent_blk["deadline"]) - datetime.fromisoformat(urgent_blk["end"])).total_seconds() / 60
            slack = f", finishing {int(mins // 60)} h {int(mins % 60)} min before its deadline" if mins >= 60 else f", finishing {int(mins)} min before its deadline"
        lines.append(f"The urgent task goes in {when} at {start:%H:%M}{slack}.")
    if any(u["task_id"] == URGENT_ID for u in after["plans"][0]["unscheduled"]):
        u = next(u for u in after["plans"][0]["unscheduled"] if u["task_id"] == URGENT_ID)
        lines.append(f"The urgent task could not be placed: {u['reason']}")
    if abs(sa["avg_fit"] - sb["avg_fit"]) >= 0.01:
        lines.append(f"Average energy fit changes from {sb['avg_fit']:.2f} to {sa['avg_fit']:.2f}.")
    if sb["deadline_safety"] is not None and sa["deadline_safety"] is not None and abs(sa["deadline_safety"] - sb["deadline_safety"]) >= 0.01:
        lines.append(f"Average chance of meeting deadlines changes from {sb['deadline_safety']:.0%} to {sa['deadline_safety']:.0%}.")
    if not diff["moved"] and not diff["dropped"] and not diff["added"]:
        lines.append("The plan does not change: there was enough slack to absorb it.")
    return lines


DEFAULT_STABILITY = 0.5


def _counts(diff: dict) -> dict:
    return {"moved": len(diff["moved"]), "added": len(diff["added"]), "dropped": len(diff["dropped"]),
            "unchanged": diff["unchanged"]}


def simulate(req: PlanRequest, scenario: dict) -> dict:
    """Before/after with the same seed. The "after" plan is a stability-aware replan of the
    "before" plan (scenario["stability"], default 0.5); when stability > 0, a free replan
    (stability 0) is also returned so the two can be compared."""
    stability = float(scenario.get("stability", DEFAULT_STABILITY))
    before = plan(req, alternatives=False)
    mod, notes = apply_scenario(req, scenario)
    mod.previous = [(b["task_id"], datetime.fromisoformat(b["start"])) for b in before["plans"][0]["blocks"]]
    mod.stability = stability
    after = plan(mod, alternatives=False)
    diff = compare(before, after)
    out = {
        "scenario": scenario,
        "seed": req.seed,
        "stability": stability,
        "before": _lite(before),
        "after": _lite(after),
        "diff": diff,
        "explanation": explain(notes, before, after, diff),
    }
    if stability > 0:
        free_req = copy.deepcopy(mod)
        free_req.stability = 0.0
        free = plan(free_req, alternatives=False)
        fdiff = compare(before, free)
        out["free_replan"] = {"summary": _summary(free), "changes": _counts(fdiff)}
        out["stable_replan"] = {"summary": _summary(after), "changes": _counts(diff)}
        f, a = _counts(fdiff), _counts(diff)
        fewer = (f["moved"] + f["dropped"]) - (a["moved"] + a["dropped"])
        if fewer > 0:
            out["explanation"].append(
                f"Keeping your plan steady changed {fewer} fewer block{'s' if fewer != 1 else ''} than a full replan would."
            )
        # Say so when steadiness is what kept the urgent task out, and what fitting it would cost.
        if URGENT_ID in _blocks(free) and URGENT_ID not in _blocks(after):
            given_up = [d["title"] for d in fdiff["dropped"]]
            cost = f" by dropping {', '.join(chr(34) + t + chr(34) for t in given_up)}" if given_up else f" by moving {f['moved']} blocks"
            out["explanation"].append(
                f"A full replan would fit the urgent task in{cost}. Lower \"keep the current plan steady\" to allow that."
            )
    return out
