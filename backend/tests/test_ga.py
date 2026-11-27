"""Genetic algorithm, decoder, baselines and the full pipeline."""
import itertools
import time
from datetime import datetime, timedelta

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ai.baselines.schedulers import BASELINES
from ai.ga.decoder import decode
from ai.ga.fitness import evaluate
from ai.ga.operators import order_crossover
from ai.ga.runner import GAConfig, best_fit_hints, run_ga
from ai.pipeline import plan, verify
from ai.problem import build_problem
from ai.types import CheckIn, Commitment, PlanRequest, Preferences

from .helpers import NOW, random_request, task


@given(st.integers(2, 30), st.integers(0, 10_000))
def test_ox1_always_gives_a_permutation(n, seed):
    rng = np.random.default_rng(seed)
    a, b = rng.permutation(n), rng.permutation(n)
    child = order_crossover(rng, a, b)
    assert sorted(child.tolist()) == list(range(n))


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 100_000))
def test_decoder_never_breaks_a_hard_rule(seed):
    """Any chromosome, however random, decodes to a legal plan."""
    req = random_request(seed, n=10)
    p = build_problem(req)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(p.tasks))
    hints = rng.integers(-1, p.G, size=len(p.tasks))
    dec = decode(p, order, hints)

    class R:  # minimal stand-in for GAResult
        decoded = dec

    verify(p, R)


def test_same_seed_same_plan():
    req = random_request(7, n=12)
    a = plan(req, alternatives=False)
    b = plan(req, alternatives=False)
    assert [x["start"] for x in a["plans"][0]["blocks"]] == [x["start"] for x in b["plans"][0]["blocks"]]


def test_ga_is_at_least_as_good_as_every_baseline():
    for seed in range(5):
        p = build_problem(random_request(seed, n=12))
        ga = run_ga(p, "balanced", seed)
        for name, fn in BASELINES.items():
            dec = fn(p)
            assert ga.score.total >= evaluate(p, dec.starts, dec.lengths).total - 1e-9, name


def test_ga_close_to_brute_force_on_small_problems():
    """5 tasks: try every order x (earliest | best-fit) start for each task."""
    for seed in range(3):
        req = random_request(100 + seed, n=5, horizon=1)
        for t in req.tasks:
            t.depends_on = None
        p = build_problem(req)
        n = len(p.tasks)
        best_fit = best_fit_hints(p)
        best = -1e9
        for order in itertools.permutations(range(n)):
            for choice in itertools.product([0, 1], repeat=n):
                hints = np.where(np.array(choice) == 1, best_fit, 0)
                dec = decode(p, np.array(order), hints)
                best = max(best, evaluate(p, dec.starts, dec.lengths).total)
        ga = run_ga(p, "balanced", seed)
        assert ga.score.total >= best - 0.02


def test_report_goes_to_the_morning_and_errand_to_the_afternoon():
    """The design's worked example, run through the whole pipeline."""
    report = task(1, title="Write report section", mental_req=7, mental_difficulty=7, physical_req=2, physical_difficulty=2, priority=3, est_minutes=30)
    errand = task(2, title="Grocery run", category="Errand", mental_req=2, mental_difficulty=2, physical_req=5, physical_difficulty=5, est_minutes=30)
    commits = [Commitment(NOW.replace(hour=h), NOW.replace(hour=h + 1), "Busy") for h in (8, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21)]
    commits.append(Commitment(NOW.replace(hour=9), NOW.replace(hour=10), "Busy"))
    req = PlanRequest(NOW, [report, errand], commits, [CheckIn(NOW, 6.5, 5, 6, 4)], [], Preferences(horizon_days=1))
    out = plan(req, alternatives=False)
    blocks = {b["task_id"]: b for b in out["plans"][0]["blocks"]}
    # The report goes where projected mental energy covers its demand; with no history the
    # completion model is its prior, so the probability is moderate, not near-certain.
    assert blocks[1]["start"].startswith("2026-11-11T10") and blocks[1]["fit"] >= 0.7
    assert blocks[2]["start"].startswith("2026-11-11T14")


def test_deadline_passed_and_cycle_are_reported_not_scheduled():
    a = task(1, deadline=NOW - timedelta(hours=1))
    b = task(2, depends_on=3)
    c = task(3, depends_on=2)
    out = plan(PlanRequest(NOW, [a, b, c], prefs=Preferences(horizon_days=1)), alternatives=False)
    codes = {u["task_id"]: u["code"] for u in out["plans"][0]["unscheduled"]}
    assert codes[1] == "DEADLINE_PASSED"
    assert codes[2] == "BLOCKED" and codes[3] == "BLOCKED"


def test_locked_and_fixed_blocks_stay_put():
    fixed = task(1, is_fixed=True, fixed_start=NOW.replace(hour=15), fixed_end=NOW.replace(hour=16))
    locked = task(2)
    free = task(3)
    lock_at = NOW.replace(hour=11)
    req = PlanRequest(NOW, [fixed, locked, free], locked=[(2, lock_at)], prefs=Preferences(horizon_days=1))
    out = plan(req, alternatives=False)
    fx = {f["task_id"]: f for f in out["fixed"]}
    assert fx[1]["start"] == NOW.replace(hour=15).isoformat()
    assert fx[2]["start"] == lock_at.isoformat() and fx[2]["kind"] == "locked"
    assert [b["task_id"] for b in out["plans"][0]["blocks"]] == [3]


def test_dependency_respected_in_plan():
    a = task(1, est_minutes=60)
    b = task(2, depends_on=1, priority=4)
    out = plan(PlanRequest(NOW, [b, a], prefs=Preferences(horizon_days=1)), alternatives=False)
    blocks = {x["task_id"]: x for x in out["plans"][0]["blocks"]}
    assert blocks[1]["end"] <= blocks[2]["start"]


def test_multi_day_spreads_work_and_respects_deadlines():
    tasks = [task(i, est_minutes=120, deadline=NOW + timedelta(days=2, hours=8)) for i in range(1, 10)]
    out = plan(PlanRequest(NOW, tasks, prefs=Preferences(horizon_days=3)), alternatives=False)
    days = {b["day"] for b in out["plans"][0]["blocks"]}
    assert len(days) >= 2
    for b in out["plans"][0]["blocks"]:
        assert b["end"] <= b["deadline"]


def test_high_stress_caps_today():
    tasks = [task(i, est_minutes=60) for i in range(1, 16)]
    calm = PlanRequest(NOW, tasks, checkins=[CheckIn(NOW, 6, 6, 6, 3)], prefs=Preferences(horizon_days=1))
    tense = PlanRequest(NOW, tasks, checkins=[CheckIn(NOW, 6, 6, 6, 9)], prefs=Preferences(horizon_days=1, preset="gentle"))
    a = plan(calm, alternatives=False)["plans"][0]["day_load"][0]["load"]
    b_out = plan(tense, alternatives=False)
    assert b_out["days"][0]["stress_cap"] is True
    assert b_out["plans"][0]["day_load"][0]["load"] <= a


def test_25_tasks_three_days_within_budget():
    try:
        import coverage
        if coverage.Coverage.current() is not None:
            pytest.skip("timing is not meaningful while coverage is tracing every line")
    except ImportError:
        pass
    req = random_request(3, n=25, horizon=3)
    t0 = time.perf_counter()
    out = plan(req)
    assert time.perf_counter() - t0 < 5.0
    assert out["plans"][0]["blocks"]


def test_every_block_has_an_explanation():
    out = plan(random_request(11, n=12))
    for b in out["plans"][0]["blocks"]:
        assert b["verdict"] and b["duration"]["text"]
    for u in out["plans"][0]["unscheduled"]:
        assert u["reason"]


def test_release_time_keeps_a_copy_on_its_own_day():
    tomorrow = (NOW + timedelta(days=1)).replace(hour=0, minute=0)
    copy = task(1, not_before=tomorrow, deadline=tomorrow.replace(hour=22))
    out = plan(PlanRequest(NOW, [copy], prefs=Preferences(horizon_days=3)), alternatives=False)
    b = out["plans"][0]["blocks"][0]
    assert b["start"] >= tomorrow.isoformat() and b["day"] == 1


def test_light_work_is_not_scattered_across_days():
    """Four short tasks with no deadlines and an empty day: they belong today."""
    tasks = [task(i, est_minutes=m, priority=p) for i, (m, p) in enumerate([(30, 2), (20, 2), (45, 1), (45, 3)], start=1)]
    out = plan(PlanRequest(NOW, tasks, prefs=Preferences(horizon_days=3)), alternatives=False)
    assert {b["day"] for b in out["plans"][0]["blocks"]} == {0}
