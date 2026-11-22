"""Run every experiment and write a results report.

    python -m ai.evaluation.benchmark                 # full run (tens of minutes on a laptop)
    python -m ai.evaluation.benchmark --quick         # small run to check everything works
    python -m ai.evaluation.benchmark --out ../docs   # where to write results.json and RESULTS.md

Every number in RESULTS.md is computed by this script from seeded synthetic data;
nothing is typed in by hand. The JSON holds the full results, including per-user values.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time
from datetime import datetime
from pathlib import Path

from .calibration import run_calibration
from .experiment import METRICS, EvalConfig, run_experiment
from .studies import run_solver_benchmark, run_stability_study

KEY_METRICS = ["completed_per_day", "completion_rate", "deadline_violation_rate", "energy_fit", "overload_minutes",
               "overloaded_days", "collisions", "plan_violations"]


def _fmt(v: float | None, digits: int = 2) -> str:
    return "–" if v is None else f"{v:.{digits}f}"


def _p(v: float | None) -> str:
    if v is None:
        return "–"
    return "<0.001" if v < 0.001 else f"{v:.3f}"


def experiment_table(res: dict, names: list[str]) -> list[str]:
    lines = ["| Scheduler | " + " | ".join(res["metrics"][m]["label"] + f" ({res['metrics'][m]['unit']})" for m in KEY_METRICS)
             + " | Planning time (s per plan) |",
             "|---|" + "---|" * (len(KEY_METRICS) + 1)]
    for n in names:
        cells = []
        for m in KEY_METRICS:
            s = res["summary"][n][m]
            cells.append(f"{s['mean']:.2f} [{s['ci'][0]:.2f}, {s['ci'][1]:.2f}]")
        cells.append(f"{res['runtime'][n]['plan_seconds']['mean']:.2f}")
        lines.append(f"| {res['schedulers'][n]} | " + " | ".join(cells) + " |")
    return lines


def comparison_table(res: dict, names: list[str], metrics: list[str]) -> list[str]:
    ref = res["schedulers"][res["reference"]]
    lines = [f"Paired differences, **{ref} minus the other scheduler**, same users. "
             "Δ = mean difference [95% bootstrap CI]; p = Wilcoxon signed-rank, Holm-adjusted across schedulers; "
             "r = rank-biserial effect size.", "",
             "| Compared with | " + " | ".join(res["metrics"][m]["label"] for m in metrics) + " |",
             "|---|" + "---|" * len(metrics)]
    for n in names:
        if n == res["reference"]:
            continue
        cells = []
        for m in metrics:
            c = res["comparisons"][n][m]
            cells.append(f"Δ {c['diff']:+.2f} [{c['ci'][0]:+.2f}, {c['ci'][1]:+.2f}], p {_p(c.get('p_holm'))}, r {_fmt(c['effect'])}")
        lines.append(f"| {res['schedulers'][n]} | " + " | ".join(cells) + " |")
    return lines


def write_markdown(out: dict, path: Path) -> None:
    L: list[str] = []
    meta = out["meta"]
    L += ["# Circadia benchmark results", "",
          f"Generated {meta['generated']} by `python -m ai.evaluation.benchmark{' --quick' if meta['quick'] else ''}` "
          f"in {meta['seconds'] / 60:.1f} min on {meta['machine']} ({meta['cpus']} CPU threads).", "",
          "**All data is synthetic.** Synthetic users have hidden habits (true overrun per category, a daily energy "
          "curve, a follow-through rate) that the planner never sees. Plans are graded against that hidden truth, "
          "not against the planner's own models. Numbers are means over users with 95% bootstrap confidence intervals.", ""]

    for tier, res in out["experiments"].items():
        names = list(res["schedulers"])
        main = [n for n in names if not n.startswith("abl_")]
        cfg = res["config"]
        L += [f"## Closed-loop comparison: {tier} workload", "",
              f"{cfg['users']} users × {cfg['days']} days, {cfg['horizon']}-day horizon, seed {cfg['seed']}. "
              f"Each day the user plans at 08:30 and 14:00, then follows the plan against their hidden truth.", ""]
        L += experiment_table(res, main) + [""]
        L += comparison_table(res, main, ["completed_per_day", "deadline_violation_rate", "energy_fit", "overload_minutes"]) + [""]
        abl = [n for n in names if n.startswith("abl_")]
        if abl:
            L += [f"### Ablations ({tier})", "",
                  "Each row removes one component from the full system (GA + local search, hierarchical durations).", ""]
            L += experiment_table(res, ["hybrid"] + abl) + [""]
            L += comparison_table(res, ["hybrid"] + abl + ["ga"], ["completed_per_day", "deadline_violation_rate",
                                                                    "energy_fit", "overloaded_days"]) + [""]

    if "solver_benchmark" in out:
        b = out["solver_benchmark"]
        L += ["## Solver benchmark: plan quality by problem size", "",
              f"{b['config']['instances']} random problems per size, 3-day horizon. Fitness is the full Balanced fitness "
              "(higher is better) for every optimiser. Gap = shortfall from the best plan any optimiser found for that "
              "problem. Every plan was re-checked by the independent hard-rule engine.", ""]
        L += ["| Tasks | Optimiser | Fitness | Gap to best | Best on | Seconds | Rule violations | Solver status |",
              "|---|---|---|---|---|---|---|---|"]
        for n, row in b["table"].items():
            for name, v in row.items():
                st = ", ".join(f"{k} {c}" for k, c in v.get("status", {}).items()) if name.startswith("cpsat") else ""
                L.append(f"| {n} | {name} | {v['fitness']:.4f} | {v['gap_pct']:.2f}% | {v['best_count']}/{b['config']['instances']} "
                         f"| {v['seconds']:.2f} | {v['violations']} | {st} |")
        L += ["", b["note"], ""]

    if "stability" in out:
        s = out["stability"]
        L += ["## Replanning stability", "",
              f"{s['cases']} disruptions (an urgent 90-minute task, or 2 hours of lost time), each replanned at 11:00 "
              f"against the 08:30 plan (about {s['previous_blocks_mean']:.1f} planned blocks). {s['note']}", "",
              "| Stability | Blocks changed | Minutes moved | Quality | Deadline safety (MC) | Urgent task placed |",
              "|---|---|---|---|---|---|"]
        for lv, e in s["table"].items():
            vs = e.get("vs_free", {})
            ch = f"{e['changed']['mean']:.2f}" + (f" (p {_p(vs['changed']['p'])})" if vs else "")
            q = f"{e['quality']['mean']:.4f}" + (f" (Δ {vs['quality']['diff']:+.4f}, p {_p(vs['quality']['p'])})" if vs else "")
            L.append(f"| {lv} | {ch} | {e['displacement']['mean']:.0f} | {q} | {e['deadline_safety']['mean']:.3f} | "
                     f"{_fmt(e['urgent_placed_pct'], 1)}% |")
        L += [""]

    if "calibration" in out:
        c = out["calibration"]
        L += ["## Duration model calibration", "",
              f"{c['config']['users']} users × {c['config']['tasks_per_user']} tasks, predicted one at a time from "
              "earlier outcomes. A calibrated P80 covers 80% of real durations. Pinball loss (minutes) scores P80 for "
              "calibration and tightness together; lower is better.", "",
              "| Model | Outcomes in category | Tasks | P80 coverage | Pinball loss | Log score | Median error (min) |",
              "|---|---|---|---|---|---|---|"]
        for v, rows in c["versions"].items():
            for bucket, r in rows.items():
                if r.get("n"):
                    L.append(f"| {v} | {bucket} | {r['n']} | {r['coverage']:.1f}% | {r['pinball80']:.2f} | "
                             f"{r['log_score']:.3f} | {r['mae']:.2f} |")
        d = c.get("pinball_difference")
        if d:
            L += ["", f"Pinball difference ({d['meaning']}): {d['mean']:+.3f} [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]."]
        L += [""]

    path.write_text("\n".join(L), encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="small sizes, to check the pipeline")
    ap.add_argument("--out", default="results", help="output folder")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-cpsat", action="store_true", help="skip CP-SAT (it needs several seconds per plan)")
    ap.add_argument("--parts", default="experiment,solver,stability,calibration",
                    help="comma-separated: experiment, solver, stability, calibration")
    args = ap.parse_args(argv)
    parts = set(args.parts.split(","))
    t0 = time.perf_counter()
    q = args.quick
    out: dict = {"experiments": {}}

    def say(msg: str) -> None:
        print(f"[{time.perf_counter() - t0:7.1f}s] {msg}", flush=True)

    if "experiment" in parts:
        for tier in (["moderate"] if q else ["easy", "moderate", "tight"]):
            say(f"closed-loop experiment, {tier}")
            cfg = EvalConfig(users=3 if q else 12, days=3 if q else 7, seed=args.seed, difficulty=tier,
                             include_cpsat=not args.no_cpsat and tier == "moderate", cpsat_seconds=2.0,
                             ablations=tier == "moderate", compare_horizon=tier == "moderate")
            out["experiments"][tier] = run_experiment(cfg)
    if "solver" in parts:
        say("solver benchmark")
        out["solver_benchmark"] = run_solver_benchmark(
            sizes=(10, 20) if q else (10, 20, 30, 40), instances=2 if q else 5, seed=args.seed,
            cpsat_limits=(2.0,) if q else (2.0, 10.0), include_cpsat=not args.no_cpsat)
    if "stability" in parts:
        say("stability study")
        out["stability"] = run_stability_study(users=3 if q else 12, days=2 if q else 3, seed=args.seed)
    if "calibration" in parts:
        say("calibration study")
        out["calibration"] = run_calibration(users=10 if q else 40, seed=args.seed)
    out["meta"] = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "seconds": time.perf_counter() - t0,
                   "quick": q, "machine": platform.platform(terse=True), "cpus": os.cpu_count(), "seed": args.seed}
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    write_markdown(out, folder / "RESULTS.md")
    say(f"wrote {folder / 'RESULTS.md'} and {folder / 'results.json'}")


if __name__ == "__main__":
    main()
