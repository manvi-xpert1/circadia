"""The hierarchical duration model (v2) and the evaluation statistics."""
import math

import pytest

from ai.evaluation.calibration import run_calibration
from ai.evaluation.experiment import EvalConfig, holm, rank_biserial, run_experiment
from ai.probability.duration_model import PRIOR_M, PRIOR_S, DurationModel
from ai.types import Outcome


def outs(cat, ratios, est=60):
    return [Outcome(cat, "done", est, round(est * r)) for r in ratios]


def test_cold_start_is_the_default_with_wider_predictive_p80():
    v2 = DurationModel([], version="v2").for_category("Study")
    v1 = DurationModel([], version="v1").for_category("Study")
    assert v2.source == "default" and v2.m == pytest.approx(PRIOR_M)
    assert v2.median(60) == pytest.approx(v1.median(60))
    assert v2.p80(60) > v1.p80(60)  # uncertainty about the mean itself widens P80


def test_one_outcome_is_used_but_shrunk():
    """v1 ignores a category until it has 3 outcomes; v2 moves part of the way after one."""
    m = DurationModel(outs("Study", [2.0]), version="v2")
    est = m.for_category("Study")
    assert PRIOR_M < est.m < math.log(2.0)
    assert DurationModel(outs("Study", [2.0]), version="v1").for_category("Study").source == "default"


def test_category_is_pulled_toward_the_users_pace_not_the_population_default():
    """A user who overruns everything by 50% gets that as the prior for a category with little data."""
    history = outs("Work", [1.5] * 10) + outs("Study", [1.5] * 10) + outs("Errand", [1.5])
    m = DurationModel(history, version="v2")
    errand = m.for_category("Errand")
    assert errand.ratio == pytest.approx(1.5, abs=0.06)
    v1 = DurationModel(history, version="v1").for_category("Errand")
    assert v1.source == "pooled"  # v1 also borrows, but only below 3 outcomes, then switches abruptly


def test_different_categories_are_kept_apart():
    history = outs("Work", [1.0] * 12) + outs("Study", [1.8] * 12)
    m = DurationModel(history, version="v2")
    assert m.for_category("Work").ratio < 1.12
    assert m.for_category("Study").ratio > 1.65


def test_a_single_outlier_does_not_drag_a_category():
    base = outs("Study", [1.2, 1.25, 1.15, 1.2, 1.3, 1.2])
    clean = DurationModel(base, version="v2").for_category("Study")
    dirty = DurationModel(base + outs("Study", [4.5]), version="v2").for_category("Study")
    v1_dirty = DurationModel(base + outs("Study", [4.5]), version="v1").for_category("Study")
    assert dirty.ratio - clean.ratio < v1_dirty.ratio - clean.ratio


def test_predictive_spread_shrinks_with_more_data_and_matches_v1_in_the_limit():
    few = DurationModel(outs("Study", [1.1, 1.3, 1.2]), version="v2").for_category("Study")
    many = DurationModel(outs("Study", [1.1, 1.3, 1.2] * 30), version="v2").for_category("Study")
    assert many.p80(60) < few.p80(60)
    v1 = DurationModel(outs("Study", [1.1, 1.3, 1.2] * 30), version="v1").for_category("Study")
    assert many.p80(60) == pytest.approx(v1.p80(60), rel=0.03)


def test_probabilities_are_monotone_and_bounded():
    est = DurationModel(outs("Study", [1.2, 1.4]), version="v2").for_category("Study")
    xs = [est.p_fits(m, 60) for m in (30, 60, 90, 120, 240)]
    assert xs == sorted(xs) and 0 <= xs[0] and xs[-1] <= 1
    assert est.p_fits(0, 60) == 0


def test_summary_reports_version_and_shrinkage():
    s = DurationModel(outs("Study", [1.2] * 4) + outs("Work", [1.6] * 4), version="v2").summary()
    assert s["version"] == "v2" and s["shrinkage_strength"] > 0 and "between_category_spread" in s


def test_calibration_study_reports_both_models():
    r = run_calibration(users=4, tasks_per_user=15, seed=1)
    for v in ("v1", "v2"):
        assert 0 <= r["versions"][v]["all"]["coverage"] <= 100
        assert r["versions"][v]["all"]["n"] == 60
    assert r["data"] == "synthetic"


# ---- statistics ------------------------------------------------------------------------------

def test_holm_adjustment():
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] == pytest.approx(0.06) and adj["b"] == pytest.approx(0.06)
    assert adj["d"] is None


def test_rank_biserial():
    assert rank_biserial([2, 3, 4], [1, 1, 1]) == 1.0
    assert rank_biserial([1, 1, 1], [2, 3, 4]) == -1.0
    assert rank_biserial([1, 2], [1, 2]) is None


@pytest.mark.skipif(not __import__("ai.cpsat", fromlist=["available"]).available(), reason="OR-Tools not installed")
def test_experiment_counts_solver_results_and_runs_ablations():
    r = run_experiment(EvalConfig(users=2, days=2, include_cpsat=True, cpsat_seconds=0.5, ablations=True,
                                  compare_horizon=False))
    assert {"hybrid", "cpsat", "abl_no_fuzzy", "abl_no_prob", "abl_v1_durations"} <= set(r["schedulers"])
    for n in r["schedulers"]:
        assert r["summary"][n]["plan_violations"]["mean"] == 0
        assert "solver_fallbacks" in r["summary"][n]
    c = r["comparisons"]["ga"]["completed_per_day"]
    assert {"diff", "ci", "p", "p_holm", "effect"} <= set(c)
    assert r["reference"] == "hybrid" and r["versions"]["duration_model"] == "v2"
    assert r["runtime"]["hybrid"]["plan_seconds"]["mean"] > 0 and "plan_seconds" not in r["summary"]["hybrid"]


@pytest.mark.parametrize("tier", ["easy", "tight"])
def test_difficulty_tiers_change_the_workload(tier):
    from ai.evaluation.experiment import make_world

    w = make_world(5, EvalConfig(days=3, difficulty=tier))
    per_day = sum(len(x) for x in w.new_tasks) / 3
    assert (per_day <= 4) if tier == "easy" else (per_day >= 7)
