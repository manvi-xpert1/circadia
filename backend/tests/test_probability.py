"""Probability models: the worked example in design section 3.3b.

These check the design doc's formulas, i.e. the original duration model (version "v1").
The hierarchical model (v2, now the default) has its own tests in test_duration_v2.py.
"""
import math

import pytest

from ai.probability.duration_model import DurationModel
from ai.probability.followthrough import FollowThroughModel
from ai.types import Outcome

RATIOS = [1.40, 1.10, 1.60, 1.25, 1.30]


def study_outcomes():
    return [Outcome("Study", "done", 60, round(60 * r)) for r in RATIOS]


def test_cold_start_uses_defaults():
    est = DurationModel([], version="v1").for_category("Study")
    assert est.source == "default"
    assert est.median(60) == pytest.approx(69, abs=0.5)
    assert est.p80(60) == pytest.approx(88.8, abs=0.5)
    assert est.p_fits(60, 60) == pytest.approx(0.32, abs=0.01)
    assert est.p_fits(90, 60) == pytest.approx(0.81, abs=0.01)


def test_learned_estimate_matches_worked_example():
    est = DurationModel(study_outcomes(), version="v1").for_category("Study")
    assert est.source == "learned"
    assert est.ratio == pytest.approx(1.25, abs=0.01)
    assert est.s == pytest.approx(0.22, abs=0.01)
    assert est.median(60) == pytest.approx(75, abs=0.5)
    assert est.p80(60) == pytest.approx(90.7, abs=0.5)
    assert est.p_fits(60, 60) == pytest.approx(0.16, abs=0.01)
    assert est.p_fits(90, 60) == pytest.approx(0.79, abs=0.01)


def test_sparse_category_borrows_pooled_estimate():
    model = DurationModel(study_outcomes(), version="v1")
    est = model.for_category("Errand")
    assert est.source == "pooled"
    assert est.n == 5


def test_skipped_and_partial_do_not_update_durations():
    outs = study_outcomes() + [Outcome("Study", "skipped", 60, None), Outcome("Study", "partial", 60, 200)]
    assert DurationModel(outs, version="v1").for_category("Study").n == 5


def test_followthrough_worked_example():
    outs = [Outcome("Study", "done", 60, 60)] * 7 + [Outcome("Study", "skipped", 60)] * 3
    m = FollowThroughModel(outs)
    assert FollowThroughModel([]).for_category("Study").p == pytest.approx(0.80)
    assert m.for_category("Study").p == pytest.approx(11 / 15)


def test_completion_probability_worked_example():
    dur = DurationModel(study_outcomes(), version="v1").for_category("Study")
    follow = 11 / 15
    assert follow * dur.p_fits(90, 60) == pytest.approx(0.58, abs=0.01)
    cold = DurationModel([], version="v1").for_category("Study")
    assert 0.8 * cold.p_fits(90, 60) == pytest.approx(0.65, abs=0.01)


def test_extreme_ratio_is_clipped():
    outs = [Outcome("Work", "done", 60, 6000)] * 3
    assert DurationModel(outs, version="v1").for_category("Work").ratio <= math.exp(math.log(5.0)) + 1e-9
