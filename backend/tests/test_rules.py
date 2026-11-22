"""Hard rules H1-H8: each has a passing and a failing case."""
from datetime import datetime, timedelta

import pytest

from ai.rules.hard_rules import FactBase, PlacedBlock, check_hard
from ai.types import Commitment, Preferences, TaskIn

NOW = datetime(2026, 11, 11, 8, 30)


def t(i, **kw):
    return TaskIn(id=i, title=f"T{i}", category="Study", priority=2, est_minutes=60, **kw)


def facts(blocks, commitments=(), tasks=None):
    tasks = tasks or {b.task.id: b.task for b in blocks}
    return FactBase(NOW, Preferences(), list(commitments), tasks, blocks)


def at(h, m=0, d=0):
    return datetime(2026, 11, 11 + d, h, m)


def ids(violations):
    return sorted({v.rule for v in violations})


def test_legal_plan_has_no_violations():
    a, b = t(1), t(2, depends_on=1, deadline=at(18))
    blocks = [PlacedBlock(a, at(9), at(10), 60), PlacedBlock(b, at(10), at(11), 60)]
    assert check_hard(facts(blocks, [Commitment(at(12), at(13), "Lecture")])) == []


@pytest.mark.parametrize(
    "start, end, rule",
    [
        (at(7), at(8), "H1"),  # before day_start
        (at(21, 30), at(22, 30), "H1"),  # after day_end
        (at(8), at(8, 30), "H1"),  # in the past
    ],
)
def test_h1_window(start, end, rule):
    assert rule in ids(check_hard(facts([PlacedBlock(t(1), start, end, 30)])))


def test_h2_fixed_commitment_overlap():
    v = check_hard(facts([PlacedBlock(t(1), at(12, 30), at(13, 30), 60)], [Commitment(at(12), at(13), "Lecture")]))
    assert ids(v) == ["H2"]


def test_h3_unavailable_overlap():
    v = check_hard(facts([PlacedBlock(t(1), at(12, 30), at(13, 30), 60)], [Commitment(at(12), at(13), "Gym", "unavailable")]))
    assert ids(v) == ["H3"]


def test_touching_blocks_are_fine_but_overlap_is_h4():
    ok = [PlacedBlock(t(1), at(9), at(10), 60), PlacedBlock(t(2), at(10), at(11), 60)]
    assert check_hard(facts(ok)) == []
    bad = [PlacedBlock(t(1), at(9), at(10), 60), PlacedBlock(t(2), at(9, 30), at(10, 30), 60)]
    assert ids(check_hard(facts(bad))) == ["H4"]


def test_h5_dependency_order():
    a, b = t(1), t(2, depends_on=1)
    bad = [PlacedBlock(b, at(9), at(10), 60), PlacedBlock(a, at(10), at(11), 60)]
    assert ids(check_hard(facts(bad))) == ["H5"]
    missing = [PlacedBlock(b, at(9), at(10), 60)]
    assert ids(check_hard(facts(missing, tasks={1: a, 2: b}))) == ["H5"]
    done = [PlacedBlock(b, at(9), at(10), 60)]  # prerequisite done -> not in pending tasks
    assert check_hard(facts(done, tasks={2: b})) == []


def test_h6_fixed_task_must_not_move():
    f = t(1, is_fixed=True, fixed_start=at(16), fixed_end=at(17))
    assert check_hard(facts([PlacedBlock(f, at(16), at(17), 0, "fixed-task")])) == []
    assert ids(check_hard(facts([PlacedBlock(f, at(15), at(16), 0, "fixed-task")]))) == ["H6"]


def test_h7_deadline():
    late = t(1, deadline=at(10))
    assert ids(check_hard(facts([PlacedBlock(late, at(9, 30), at(10, 30), 60)]))) == ["H7"]


def test_h8_block_length():
    assert ids(check_hard(facts([PlacedBlock(t(1), at(9), at(9, 45), 60)]))) == ["H8"]


def test_h9_release_time():
    copy = t(1, not_before=at(0, 0, d=1))
    assert ids(check_hard(facts([PlacedBlock(copy, at(9), at(10), 60)]))) == ["H9"]
    assert check_hard(facts([PlacedBlock(copy, at(9, d=1), at(10, d=1), 60)])) == []
