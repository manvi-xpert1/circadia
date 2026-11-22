"""Stability-aware replanning, Monte Carlo robustness and the trade-off filter."""
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from ai.ga.fitness import MOVE_BASE, evaluate, move_cost, stability_penalty, weights_for
from ai.ga.runner import run_hybrid
from ai.pipeline import plan, stability_report, verify
from ai.problem import build_problem
from ai.tradeoffs import annotate, dominates
from ai.types import Commitment, PlanRequest, Preferences
from ai.uncertainty import MCConfig, simulate_plan
from ai.whatif import simulate

from .helpers import NOW, random_request, task


def _previous(req):
    p = build_problem(req)
    r = run_hybrid(p, "balanced", req.seed)
    return [(p.tasks[i].task.id, p.slot_dt(s)) for i, s in enumerate(r.decoded.starts) if s >= 0]


def test_move_cost_is_zero_kept_grows_with_distance_and_one_dropped():
    assert move_cost(10, 10, 56) == 0
    assert move_cost(10, 11, 56) == pytest.approx(MOVE_BASE + (1 - MOVE_BASE) / 56)
    assert move_cost(10, 11, 56) < move_cost(10, 30, 56) < move_cost(10, 100, 56) <= 1
    assert move_cost(10, -1, 56) == 1


def test_stability_term_only_appears_when_replanning():
    req = random_request(5, n=8)
    p = build_problem(req)
    assert "stab" not in weights_for(p, "balanced")
    req2 = replace(req, previous=_previous(req), stability=0.5)
    p2 = build_problem(req2)
    assert weights_for(p2, "balanced")["stab"] == pytest.approx(0.2)
    kept = [p2.prev_slot[i] if p2.prev_slot[i] is not None else -1 for i in range(len(p2.tasks))]
    assert stability_penalty(p2, kept) == 0
    assert evaluate(p2, kept, [t.slots_p80 for t in p2.tasks]).parts["stab"] == 0


def test_unchanged_inputs_with_full_stability_keep_the_plan():
    req = random_request(8, n=10)
    prev = _previous(req)
    p = build_problem(replace(req, previous=prev, stability=1.0))
    r = run_hybrid(p, "balanced", 8)
    rep = stability_report(p, r.decoded.starts)
    assert rep["previous_blocks"] == len(prev)
    assert rep["kept"] == len(prev) and rep["moved"] == rep["removed"] == 0


def test_more_stability_changes_fewer_blocks_after_a_disruption():
    changed = {}
    for lv in (0.0, 1.0):
        total = 0
        for seed in range(4):
            req = random_request(20 + seed, n=10)
            prev = _previous(req)
            later = replace(req, now=NOW + timedelta(hours=1), previous=prev, stability=lv,
                            commitments=req.commitments + [Commitment(NOW.replace(hour=15), NOW.replace(hour=17), "Lost", "unavailable")],
                            tasks=req.tasks + [task(500, priority=4, est_minutes=60, deadline=NOW + timedelta(hours=8))])
            p = build_problem(later)
            r = run_hybrid(p, "balanced", later.seed)
            verify(p, r)
            rep = stability_report(p, r.decoded.starts)
            total += rep["moved"] + rep["removed"]
        changed[lv] = total
    assert changed[1.0] < changed[0.0]


def test_previous_blocks_in_the_past_or_for_done_tasks_are_ignored():
    req = random_request(3, n=6)
    prev = [(1, NOW - timedelta(hours=1)), (9999, NOW + timedelta(hours=2))]
    p = build_problem(replace(req, previous=prev, stability=1.0))
    assert not p.has_previous


def test_locked_blocks_stay_put_when_replanning_with_stability():
    req = random_request(6, n=8)
    prev = _previous(req)
    tid, start = prev[0]
    p = build_problem(replace(req, previous=prev[1:], stability=0.7, locked=[(tid, start)]))
    r = run_hybrid(p, "balanced", 6)
    verify(p, r)
    assert any(fb.task.id == tid and fb.start == start and fb.kind == "locked" for fb in p.fixed_blocks)


def test_whatif_compares_stable_and_free_replans():
    out = simulate(random_request(4, n=10), {"urgent_task": {"title": "Urgent", "est_minutes": 60, "deadline_hours": 8},
                                             "stability": 0.8})
    assert out["stability"] == 0.8
    s, f = out["stable_replan"]["changes"], out["free_replan"]["changes"]
    assert s["moved"] + s["dropped"] <= f["moved"] + f["dropped"]
    assert out["after"]["summary"]["stability"]["previous_blocks"] > 0


# ---- Monte Carlo --------------------------------------------------------------------------

def _plan_starts(seed=7, n=10):
    p = build_problem(random_request(seed, n=n))
    return p, run_hybrid(p, "balanced", seed).decoded.starts


def test_monte_carlo_is_reproducible_and_bounded():
    p, starts = _plan_starts()
    a = simulate_plan(p, starts, MCConfig(runs=200, seed=1))
    b = simulate_plan(p, starts, MCConfig(runs=200, seed=1))
    assert a == b
    for k in ("p_all_important_done", "p_all_deadlines_met", "deadline_safety", "p_overrun_any_day"):
        assert a[k] is None or 0 <= a[k] <= 1
    assert 0 <= a["expected_completed"] <= a["planned"]
    assert a["completed_p10"] <= a["expected_completed"] <= a["completed_p90"] + 1e-9
    assert a["runs"] == 200


def test_monte_carlo_of_an_empty_plan():
    p = build_problem(random_request(2, n=5))
    out = simulate_plan(p, [-1] * len(p.tasks), MCConfig(runs=20))
    assert out["expected_completed"] == 0 and out["planned"] == 0
    assert out["p_overrun_any_day"] == 0


def test_monte_carlo_sees_knock_on_delays():
    """Back-to-back blocks overrun into each other; the same blocks with gaps finish more often."""
    tasks = [task(i, est_minutes=60, deadline=NOW.replace(hour=21)) for i in range(1, 6)]
    req = PlanRequest(NOW, tasks, [], [], [], Preferences(horizon_days=1, day_start=NOW.time().replace(hour=8),
                                                           day_end=NOW.time().replace(hour=22)), seed=3)
    p = build_problem(req)
    L = p.tasks[0].slots_p80
    first = p.npd - 5 * L  # pack all five blocks right at the end of the day
    packed = [first + k * L for k in range(5)]
    spread = [2 + k * (L + 3) for k in range(5)]
    late = simulate_plan(p, packed, MCConfig(runs=400, seed=0))
    early = simulate_plan(p, spread, MCConfig(runs=400, seed=0))
    assert late["p_overrun_any_day"] > early["p_overrun_any_day"]
    assert late["expected_unfinished_minutes"] > early["expected_unfinished_minutes"]


def test_robustness_and_tradeoffs_are_attached_to_plans():
    out = plan(random_request(5, n=12), mc_runs=100)
    for pl in out["plans"]:
        assert pl["robustness"]["runs"] == 100
        t = pl["tradeoffs"]
        assert set(t["objectives"]) >= {"completion", "deadlines", "energy", "calm"}
        assert t["pareto_optimal"] == (not t["dominated_by"])
    assert plan(random_request(5, n=4), mc_runs=0, alternatives=False)["plans"][0]["robustness"] is None


def test_dominance_uses_tolerances():
    a = {"completion": 5.0, "deadlines": 0.9, "energy": 0.6, "calm": 0.4}
    assert dominates(a, {**a, "calm": 0.3})
    assert not dominates(a, {**a, "calm": 0.395})  # within tolerance: a tie, not domination
    assert not dominates(a, {**a, "calm": 0.3, "energy": 0.7})


def test_annotate_marks_a_strictly_worse_plan_as_dominated():
    base = {"components": {"en": 0.6}, "day_load": [{"load": 0.5}], "robustness": {"expected_completed": 5, "deadline_safety": 0.9},
            "label": "A"}
    worse = {"components": {"en": 0.5}, "day_load": [{"load": 0.7}], "robustness": {"expected_completed": 4, "deadline_safety": 0.8},
             "label": "B"}
    plans = [base, worse]
    annotate(plans)
    assert base["tradeoffs"]["pareto_optimal"] and not worse["tradeoffs"]["pareto_optimal"]
    assert worse["tradeoffs"]["dominated_by"] == ["A"]
    assert "Energy fit" in base["tradeoffs"]["best_at"]
