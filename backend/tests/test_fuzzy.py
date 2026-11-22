"""Fuzzy engine: membership functions and the worked example in design section 3.3a."""
from datetime import datetime, time

import pytest

from ai.fuzzy.engine import capacity, suitability
from ai.fuzzy.membership import LEVEL_TERMS, fuzzify, trap, tri
from ai.fuzzy.profile import DayState, default_profile, learn_profile, project
from ai.types import CheckIn


def test_trapezoid_breakpoints():
    assert trap(0, 0, 0, 2, 5) == 1.0
    assert trap(2, 0, 0, 2, 5) == 1.0
    assert trap(3.5, 0, 0, 2, 5) == pytest.approx(0.5)
    assert trap(5, 0, 0, 2, 5) == 0.0
    assert tri(5, 2, 5, 8) == 1.0
    assert tri(6.5, 2, 5, 8) == pytest.approx(0.5)


def test_memberships_of_worked_example():
    e = fuzzify(7.5, LEVEL_TERMS)
    assert e["Medium"] == pytest.approx(1 / 6)
    assert e["High"] == pytest.approx(5 / 6)


def test_projection_of_checkin_to_slots():
    state = DayState(6.5, 5, 6, 4, time(8, 30), "check-in")
    prof = default_profile()
    assert project(state, prof, time(10, 0)) == (7.5, 5.5)
    assert project(state, prof, time(14, 0)) == (6.0, 5.0)


def test_capacity_worked_example():
    assert capacity(7.5, 6, 4).value == pytest.approx(7.04, abs=0.01)
    assert capacity(6.0, 6, 4).value == pytest.approx(6.28, abs=0.01)


def test_high_stress_lowers_capacity():
    calm = capacity(7.5, 6, 4)
    stressed = capacity(7.5, 6, 8.5)
    assert stressed.value == pytest.approx(6.01, abs=0.01)
    assert any("Stress High" in f.rule for f in stressed.fired)
    assert stressed.value < calm.value


@pytest.mark.parametrize(
    "cap, phys, md, pd, expected",
    [
        (7.036, 5.5, 7, 2, 0.89),  # report at 10:00
        (6.282, 5.0, 7, 2, 0.67),  # report at 14:00
        (7.036, 5.5, 2, 5, 0.65),  # groceries at 10:00
        (6.282, 5.0, 2, 5, 0.65),  # groceries at 14:00
    ],
)
def test_suitability_worked_example(cap, phys, md, pd, expected):
    assert suitability(cap - md, phys - pd).value == pytest.approx(expected, abs=0.01)


def test_physical_deficit_is_poor():
    assert suitability(0, -6).value < 0.3


def test_learned_profile_moves_toward_user_pattern():
    # A user who is always sharp in the evening.
    hist = []
    for d in range(1, 11):
        hist.append(CheckIn(datetime(2026, 11, d, 19, 0), 9, 5, 6, 3))
        hist.append(CheckIn(datetime(2026, 11, d, 10, 0), 5, 5, 6, 3))
    prof = learn_profile(hist)
    evening = prof.mental_offsets[5]
    assert evening > 0  # default is -0.5; the user's data pulls it up
    assert prof.is_learned
