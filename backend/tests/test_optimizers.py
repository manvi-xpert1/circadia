"""Local search, the hybrid GA and the CP-SAT scheduler: legality, quality and reproducibility."""
import time
from datetime import timedelta

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ai.baselines.schedulers import BASELINES
from ai.cpsat.scheduler import CPSATConfig, run_cpsat
from ai.ga.decoder import NO_ROOM, decode
from ai.ga.fitness import evaluate
from ai.ga.local_search import LSConfig, chromosome_for, local_search
from ai.ga.runner import run_ga, run_hybrid
from ai.pipeline import plan, verify
from ai.problem import build_problem
from ai.types import Commitment, PlanRequest, Preferences

from .helpers import NOW, random_request, task

FAST_CP = CPSATConfig(time_limit=1.0, workers=1)
from ai.cpsat import available as _cp_available  # noqa: E402

needs_ortools = pytest.mark.skipif(not _cp_available(), reason="OR-Tools not installed (optional)")


class _R:
    def __init__(self, dec):
        self.decoded = dec


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 100_000))
def test_local_search_never_breaks_a_hard_rule_and_never_gets_worse(seed):
    """Start local search from a random chromosome: the result must be legal and at least as good."""
    p = build_problem(random_request(seed, n=10))
    rng = np.random.default_rng(seed)
    dec = decode(p, rng.permutation(len(p.tasks)), rng.integers(-1, p.G, size=len(p.tasks)))
    before = evaluate(p, dec.starts, dec.lengths).total
    out, score, _ = local_search(p, dec, "balanced", LSConfig(max_evaluations=400, seed=seed))
    verify(p, _R(out))
    assert score.total >= before - 1e-12
    assert score.total == pytest.approx(evaluate(p, out.starts, out.lengths).total)


@settings(max_examples=25, deadline=None)
@given(st.integers(0, 100_000))
def test_chromosome_for_decodes_back_to_the_same_plan(seed):
    p = build_problem(random_request(seed, n=12))
    r = run_hybrid(p, "balanced", seed)
    order, hints = chromosome_for(p, r.decoded.starts)
    assert decode(p, order, hints).starts == r.decoded.starts


def test_hybrid_is_at_least_as_good_as_the_ga_and_every_baseline():
    for seed in range(5):
        p = build_problem(random_request(seed, n=15))
        ga = run_ga(p, "balanced", seed)
        hy = run_hybrid(p, "balanced", seed)
        assert hy.score.total >= ga.score.total - 1e-12
        assert hy.optimizer == "hybrid" and "local_search" in hy.details
        for fn in BASELINES.values():
            d = fn(p)
            assert hy.score.total >= evaluate(p, d.starts, d.lengths).total - 1e-9


def test_hybrid_is_reproducible():
    p = build_problem(random_request(11, n=15))
    a = run_hybrid(p, "balanced", 11, ls_config=LSConfig(max_seconds=1e9))
    b = run_hybrid(p, "balanced", 11, ls_config=LSConfig(max_seconds=1e9))
    assert a.decoded.starts == b.decoded.starts


def test_local_search_respects_its_evaluation_budget():
    p = build_problem(random_request(3, n=20))
    dec = run_ga(p, "balanced", 3).decoded
    _, _, stats = local_search(p, dec, "balanced", LSConfig(max_evaluations=25))
    assert stats.evaluations <= 25 + 40  # finishes the candidate set it is scoring


@needs_ortools
@pytest.mark.parametrize("seed", range(6))
def test_cpsat_plans_pass_the_independent_rule_check(seed):
    p = build_problem(random_request(seed, n=10))
    r = run_cpsat(p, "balanced", seed, FAST_CP)
    verify(p, r)
    info = r.details["cpsat"]
    assert info["status"] in ("OPTIMAL", "FEASIBLE", "UNKNOWN")
    assert r.score.total == pytest.approx(evaluate(p, r.decoded.starts, r.decoded.lengths).total)


@needs_ortools
def test_cpsat_respects_prerequisites_commitments_and_deadlines():
    tasks = [task(1, est_minutes=60), task(2, est_minutes=60, depends_on=1),
             task(3, est_minutes=45, deadline=NOW.replace(hour=12))]
    commits = [Commitment(NOW.replace(hour=9), NOW.replace(hour=11), "Lecture")]
    req = PlanRequest(NOW, tasks, commits, [], [], Preferences(horizon_days=1), seed=1)
    p = build_problem(req)
    r = run_cpsat(p, "balanced", 1, FAST_CP)
    verify(p, r)
    s = {p.tasks[i].task.id: x for i, x in enumerate(r.decoded.starts)}
    if s[2] >= 0:
        assert s[1] >= 0 and s[2] >= s[1] + p.tasks[0].slots_p80
    if s[3] >= 0:
        assert p.slot_dt(s[3]) + timedelta(minutes=p.tasks[2].planned_minutes) <= NOW.replace(hour=12)


@needs_ortools
def test_cpsat_handles_tasks_that_cannot_fit():
    """A task longer than any free gap is reported unscheduled, not an error."""
    commits = [Commitment(NOW.replace(hour=h), NOW.replace(hour=h, minute=45), "Class") for h in range(9, 22)]
    req = PlanRequest(NOW, [task(1, est_minutes=120), task(2, est_minutes=15)], commits, [], [],
                      Preferences(horizon_days=1), seed=2)
    p = build_problem(req)
    r = run_cpsat(p, "balanced", 2, FAST_CP)
    verify(p, r)
    assert r.decoded.starts[0] == -1 and r.decoded.reasons[0] == NO_ROOM


@needs_ortools
def test_cpsat_with_no_tasks():
    p = build_problem(PlanRequest(NOW, [], [], [], [], Preferences(horizon_days=1)))
    r = run_cpsat(p, "balanced", 0, FAST_CP)
    assert r.decoded.starts == [] and r.optimizer == "cpsat"


@pytest.mark.parametrize("optimizer", ["ga", "hybrid", pytest.param("cpsat", marks=needs_ortools)])
def test_every_optimizer_works_through_the_pipeline(optimizer, monkeypatch):
    import ai.pipeline as pl

    monkeypatch.setattr(pl, "optimise", lambda p, preset, seed, opt="hybrid", config=None, cpsat_seconds=8.0:
                        _orig_optimise(p, preset, seed, opt, config, cpsat_seconds=1.0))
    out = plan(random_request(4, n=8), optimizer=optimizer, mc_runs=50)
    main = out["plans"][0]
    assert out["meta"]["optimizer"] == optimizer and main["optimizer"] == optimizer
    assert main["robustness"]["runs"] == 50
    assert all("tradeoffs" in p for p in out["plans"])


from ai.pipeline import optimise as _orig_optimise  # noqa: E402


def test_unknown_optimizer_is_rejected():
    with pytest.raises(ValueError):
        plan(random_request(1, n=3), optimizer="quantum")


def test_hybrid_plans_25_tasks_within_budget():
    req = random_request(99, n=25)
    t0 = time.perf_counter()
    plan(req)
    assert time.perf_counter() - t0 < 8.0  # 3 styles x (GA + local search) + Monte Carlo


@pytest.mark.parametrize("n", [5, 15, 30])
def test_hybrid_scales_with_task_count(n):
    p = build_problem(random_request(n, n=n))
    t0 = time.perf_counter()
    r = run_hybrid(p, "balanced", n)
    verify(p, r)
    assert time.perf_counter() - t0 < 6.0


def test_thorough_mode_falls_back_when_ortools_is_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "ortools":
            raise ImportError("no ortools")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from ai.pipeline import optimise

    p = build_problem(random_request(2, n=6))
    r = optimise(p, "balanced", 2, "cpsat")
    verify(p, r)
    assert r.optimizer == "hybrid" and r.details["cpsat"]["status"] == "UNAVAILABLE"
