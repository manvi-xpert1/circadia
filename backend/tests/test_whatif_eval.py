"""What-if simulator and the evaluation experiment."""
from datetime import timedelta

import pytest

from ai.evaluation.experiment import METRICS, EvalConfig, make_world, run_experiment
from ai.types import CheckIn, PlanRequest, Preferences
from ai.whatif import URGENT_ID, simulate

from .helpers import NOW, random_request, task


def base_req():
    tasks = [task(i, est_minutes=60, priority=2 + i % 2) for i in range(1, 7)]
    return PlanRequest(NOW, tasks, checkins=[CheckIn(NOW, 7, 6, 7, 3)], prefs=Preferences(horizon_days=2), seed=5)


def test_no_change_without_effect_is_reported_honestly():
    out = simulate(base_req(), {"lose_time": {"day": 1, "start": "21:30", "end": "21:45"}})
    assert out["before"]["summary"]["tasks_planned"] == 6
    assert out["explanation"]


def test_late_start_removes_free_time_and_moves_work():
    out = simulate(base_req(), {"late_start_minutes": 240})
    assert out["after"]["days"][0]["free_minutes"] < out["before"]["days"][0]["free_minutes"]
    assert any("Free time today" in line for line in out["explanation"])
    for b in out["after"]["blocks"]:
        if b["day"] == 0:
            assert b["start"] >= (NOW + timedelta(minutes=240)).isoformat()[:16]


def test_urgent_task_is_placed_before_its_deadline():
    out = simulate(base_req(), {"urgent_task": {"title": "Fix bug", "est_minutes": 45, "deadline_hours": 5}})
    urgent = [b for b in out["after"]["blocks"] if b["task_id"] == URGENT_ID]
    assert urgent and urgent[0]["end"] <= (NOW + timedelta(hours=5)).isoformat()
    assert any(a["task_id"] == URGENT_ID for a in out["diff"]["added"])


def test_lower_energy_lowers_capacity():
    out = simulate(base_req(), {"energy_delta": -4})
    assert any("mental energy" in line for line in out["explanation"])


def test_extending_a_task_lengthens_its_block():
    out = simulate(base_req(), {"extend_task": {"task_id": 1, "extra_minutes": 60}})
    before = next(b for b in out["before"]["blocks"] if b["task_id"] == 1)
    after = next((b for b in out["after"]["blocks"] if b["task_id"] == 1), None)
    assert after is None or after["planned_minutes"] > before["planned_minutes"]


def test_worlds_are_identical_for_every_scheduler():
    cfg = EvalConfig(users=1, days=3)
    a, b = make_world(7, cfg), make_world(7, cfg)
    assert [t.title for t in a.new_tasks[0]] == [t.title for t in b.new_tasks[0]]
    assert a.states[2] == b.states[2]


def test_small_experiment_is_complete_reproducible_and_legal():
    cfg = EvalConfig(users=3, days=3, compare_horizon=True)
    r1 = run_experiment(cfg)
    r2 = run_experiment(cfg)
    assert r1["summary"] == r2["summary"]
    assert set(r1["summary"]) == {"priority", "duration", "energy", "ga", "hybrid", "ga_1day"}
    for name, metrics in r1["summary"].items():
        assert set(metrics) == set(METRICS)
        assert metrics["plan_violations"]["mean"] == 0, name  # every scheduler obeys the hard rules
        lo, hi = metrics["completion_rate"]["ci"]
        assert lo <= metrics["completion_rate"]["mean"] <= hi
    assert r1["data"] == "synthetic"
