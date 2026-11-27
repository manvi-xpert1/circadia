"""Outcome-based choice of the main plan."""
import numpy as np

from ai.ga.runner import run_hybrid
from ai.pipeline import plan
from ai.problem import build_problem
from ai.selection import Candidate, outcome_values, select
from ai.uncertainty import MCConfig, replay, task_draws

from .helpers import random_request


def _problem(seed=11, n=10):
    p = build_problem(random_request(seed, n=n))
    return p, run_hybrid(p, "balanced", seed).decoded.starts


def test_identical_candidates_never_switch():
    p, starts = _problem()
    k, rep = select(p, [Candidate("a", starts), Candidate("b", list(starts))], "balanced", MCConfig(runs=60, seed=1))
    assert k == 0 and not rep["switched"]
    assert rep["candidates"][1]["vs_first"] == 0 and rep["candidates"][1]["se"] == 0


def test_a_clearly_better_plan_is_chosen():
    p, starts = _problem()
    empty = [-1] * len(starts)
    k, rep = select(p, [Candidate("empty", empty), Candidate("real", starts)], "balanced", MCConfig(runs=60, seed=1))
    assert k == 1 and rep["switched"] and rep["chosen"] == "real"


def test_outcome_value_rewards_completed_work():
    p, starts = _problem()
    u, z = task_draws(p, 40, 2)
    full = outcome_values(p, starts, replay(p, starts, u, z), "balanced")
    none = outcome_values(p, [-1] * len(starts), replay(p, [-1] * len(starts), u, z), "balanced")
    assert full.mean() > none.mean()


def test_plan_reports_its_selection():
    req = random_request(5, n=8)
    req.select_by_outcome = True
    out = plan(req, mc_runs=40)
    sel = out["plans"][0]["selection"]
    assert sel is not None and len(sel["candidates"]) >= 2
    assert sel["candidates"][0]["vs_first"] == 0
    assert out["meta"]["simulation"]["runs"] == 40


def test_selection_is_off_by_default():
    req = random_request(5, n=8)
    assert plan(req, mc_runs=30)["plans"][0]["selection"] is None


def test_compare_runner_pairs_policies_on_the_same_users():
    import pytest as _pytest

    from ai.evaluation.compare import compare
    from ai.evaluation.experiment import EvalConfig

    res = compare(["hybrid", "buf_p65"], EvalConfig(users=2, days=2), progress=None)
    assert res["reference"] == "hybrid" and len(res["per_user"]["buf_p65"]) == 2
    c = res["comparisons"]["buf_p65"]["completed_per_day"]
    a = [x["completed_per_day"] for x in res["per_user"]["hybrid"]]
    b = [x["completed_per_day"] for x in res["per_user"]["buf_p65"]]
    assert c["diff"] == _pytest.approx(round(sum(a) / 2 - sum(b) / 2, 3), abs=1e-3)
    with _pytest.raises(ValueError):
        compare(["hybrid", "nope"], EvalConfig(users=1, days=1), progress=None)
