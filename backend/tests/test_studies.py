"""The solver benchmark, the stability study and the benchmark report, at tiny sizes."""
import json

from ai.evaluation import benchmark
import pytest

from ai.cpsat import available
from ai.evaluation.studies import random_instance, run_solver_benchmark, run_stability_study

needs_ortools = pytest.mark.skipif(not available(), reason="OR-Tools not installed (optional)")


@needs_ortools
def test_solver_benchmark_reports_every_optimiser_and_no_violations():
    r = run_solver_benchmark(sizes=(6,), instances=1, cpsat_limits=(0.5,))
    row = r["table"]["6"]
    assert set(row) == {"ga", "hybrid", "cpsat_0s"}
    assert all(v["violations"] == 0 for v in row.values())
    assert min(v["gap_pct"] for v in row.values()) == 0  # someone found the best plan
    assert row["hybrid"]["fitness"] >= row["ga"]["fitness"] - 1e-9


def test_solver_benchmark_without_cpsat():
    r = run_solver_benchmark(sizes=(5,), instances=1, include_cpsat=False)
    assert r["optimizers"] == ["ga", "hybrid"]


def test_stability_study_pairs_levels_against_the_free_replan():
    r = run_stability_study(users=1, days=2, levels=(0.0, 1.0))
    assert r["cases"] == 2
    free, full = r["table"]["0.0"], r["table"]["1.0"]
    assert full["changed"]["mean"] <= free["changed"]["mean"]
    assert "vs_free" in full and "vs_free" not in free


def test_random_instances_are_reproducible():
    a, b = random_instance(3, 8), random_instance(3, 8)
    assert [t.est_minutes for t in a.tasks] == [t.est_minutes for t in b.tasks]


def test_benchmark_cli_writes_report_and_json(tmp_path):
    benchmark.main(["--quick", "--parts", "calibration,stability", "--out", str(tmp_path)])
    md = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert "Duration model calibration" in md and "Replanning stability" in md
    assert data["meta"]["quick"] is True and "calibration" in data


def test_benchmark_report_renders_experiment_and_solver_sections(tmp_path):
    from ai.evaluation.experiment import EvalConfig, run_experiment

    out = {"experiments": {"moderate": run_experiment(EvalConfig(users=2, days=2, ablations=True, compare_horizon=False))},
           "solver_benchmark": run_solver_benchmark(sizes=(5,), instances=1, cpsat_limits=(0.5,)),
           "meta": {"generated": "now", "seconds": 1.0, "quick": True, "machine": "test", "cpus": 1}}
    benchmark.write_markdown(out, tmp_path / "R.md")
    md = (tmp_path / "R.md").read_text(encoding="utf-8")
    assert "Ablations (moderate)" in md and "Solver benchmark" in md and "Holm" in md
