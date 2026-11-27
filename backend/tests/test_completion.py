"""Contextual completion model: priors, learning, uncertainty, censoring and calibration."""
import math
import random
from datetime import datetime

import numpy as np
import pytest

from ai.evaluation.completion_study import auc, ece, metrics
from ai.probability.completion import (DEFAULT_PRIOR, FEATURES, CompletionModel, context_features,
                                       training_rows)
from ai.types import Outcome, OutcomeContext

T0 = datetime(2026, 11, 10, 10, 0)


def ctx(mental_demand=5, expected_mental=6, focus=6, stress=4.5, physical_demand=2, expected_physical=6):
    return OutcomeContext(T0, mental_demand, physical_demand, expected_mental, expected_physical, focus, stress)


def out(status, c=None, category="study", est=60):
    return Outcome(category, status, est, None, c)


def feats(c: OutcomeContext, est=60):
    return context_features(c.mental_demand, c.physical_demand, c.expected_mental, c.expected_physical,
                            c.focus, c.stress, est)


def test_cold_start_is_the_prior():
    m = CompletionModel([])
    easy = m.predict("study", feats(ctx(mental_demand=3)))
    hard = m.predict("study", feats(ctx(mental_demand=9, expected_mental=4)))
    assert m.n == 0
    assert 0.7 < easy.p < 0.85  # about the 0.8 follow-through prior, a little shrunk by uncertainty
    assert hard.p < easy.p  # the expert prior: working above your energy is riskier
    assert easy.low < easy.p < easy.high


def test_features_follow_the_declared_order():
    f = feats(ctx(mental_demand=8, expected_mental=5, physical_demand=7, expected_physical=4, focus=8, stress=2.5), est=120)
    assert len(f) == len(FEATURES)
    assert f[1] == 3 and f[2] == 3  # shortfalls
    assert f[3] == pytest.approx(1.0) and f[4] == pytest.approx(-1.0)
    assert f[5] == pytest.approx(math.log(2))
    assert context_features(2, 2, 8, 8, 6, 4.5, 60)[1] == 0  # no shortfall when energy covers the demand


def test_unreached_blocks_are_censored_not_skips():
    cats, rows, y = training_rows([out("done"), out("skipped"), out("unreached"), out("partial")])
    assert len(y) == 3 and list(y) == [1, 0, 1]


def test_sparse_data_stays_close_to_the_prior():
    m = CompletionModel([out("skipped", ctx()) for _ in range(2)])
    p0 = CompletionModel([]).predict("study", feats(ctx())).p
    p2 = m.predict("study", feats(ctx())).p
    assert p2 < p0  # it moves
    assert p2 > 0.45  # but two skips do not make a skipper


def test_posterior_narrows_with_data():
    rng = random.Random(1)
    few = CompletionModel([out("done" if rng.random() < 0.8 else "skipped", ctx()) for _ in range(5)])
    many = CompletionModel([out("done" if rng.random() < 0.8 else "skipped", ctx()) for _ in range(200)])
    w = lambda m: (lambda pr: pr.high - pr.low)(m.predict("study", feats(ctx())))
    assert w(many) < w(few)


def test_learns_a_context_effect_from_data():
    """A user who skips whenever a block is above their energy, and almost never otherwise."""
    rng = random.Random(4)
    hist = []
    for _ in range(150):
        hard = rng.random() < 0.5
        c = ctx(mental_demand=9, expected_mental=4) if hard else ctx(mental_demand=3, expected_mental=7)
        p = 0.3 if hard else 0.95
        hist.append(out("done" if rng.random() < p else "skipped", c))
    m = CompletionModel(hist)
    assert m.beta[FEATURES.index("mental_shortfall")] < DEFAULT_PRIOR.mean[1]  # steeper than the prior
    assert m.predict("study", feats(ctx(mental_demand=3, expected_mental=7))).p > 0.85
    assert m.predict("study", feats(ctx(mental_demand=9, expected_mental=4))).p < 0.5


def test_data_can_overturn_the_expert_prior():
    """A user who does hard work regardless: the shortfall effect shrinks toward zero."""
    rng = random.Random(5)
    hist = [out("done" if rng.random() < 0.9 else "skipped",
                ctx(mental_demand=9, expected_mental=4) if rng.random() < 0.5 else ctx()) for _ in range(300)]
    m = CompletionModel(hist)
    assert abs(m.beta[FEATURES.index("mental_shortfall")]) < abs(DEFAULT_PRIOR.mean[1])


def test_outcomes_without_context_still_inform_the_baseline():
    m = CompletionModel([out("skipped") for _ in range(30)])
    assert m.n == 30 and m.n_context == 0
    assert m.predict("study", m.fill).p < 0.5


def test_categories_are_shrunk_and_unknown_categories_get_the_baseline():
    hist = [out("skipped", ctx(), category="chores") for _ in range(3)] + [out("done", ctx()) for _ in range(30)]
    m = CompletionModel(hist)
    chores = m.predict("chores", feats(ctx())).p
    unseen = m.predict("hobby", feats(ctx())).p
    assert chores < unseen
    assert chores > 0.3  # three skips are not enough to write the category off


def test_matrix_prediction_matches_single_prediction():
    rng = random.Random(2)
    hist = [out(rng.choice(["done", "skipped", "partial"]), ctx(mental_demand=rng.uniform(1, 9)),
                category=rng.choice(["study", "chores"])) for _ in range(60)]
    m = CompletionModel(hist)
    cs = [ctx(mental_demand=2), ctx(mental_demand=8, expected_mental=4)]
    X = np.stack([np.stack([feats(c) for c in cs])] * 2)  # 2 tasks x 2 slots
    P = m.predict_matrix(["study", "hobby"], X)
    for i, cat in enumerate(["study", "hobby"]):
        for g, c in enumerate(cs):
            assert P[i, g] == pytest.approx(m.predict(cat, feats(c)).p, abs=1e-9)


def test_is_calibrated_on_data_from_its_own_family():
    """Fitted to outcomes from a known logistic truth, predictions on new blocks are calibrated."""
    rng = np.random.default_rng(3)
    def sample(n):
        rows = []
        for _ in range(n):
            c = ctx(mental_demand=float(rng.uniform(1, 10)), expected_mental=float(rng.uniform(3, 8)),
                    focus=float(rng.uniform(3, 9)), stress=float(rng.uniform(1, 8)))
            f = feats(c)
            p = 1 / (1 + math.exp(-(1.6 - 0.45 * f[1] + 0.3 * f[3] - 0.3 * f[4])))
            rows.append((c, f, int(rng.random() < p)))
        return rows
    train, test = sample(600), sample(600)
    m = CompletionModel([out("done" if y else "skipped", c) for c, _, y in train])
    P = np.array([m.predict("study", f).p for _, f, _ in test])
    y = np.array([y for *_, y in test])
    assert ece(P, y) < 0.05
    assert auc(P, y) > 0.65
    assert metrics(P, y)["brier"] < metrics(np.full_like(P, y.mean()), y)["brier"]
