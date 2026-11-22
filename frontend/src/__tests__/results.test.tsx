import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EvalResults, PlanRun, PlanVersion } from "../api/types";
import { Comparisons, StudiesView } from "../pages/Evaluation";
import { Risk } from "../pages/Schedule";

const res = {
  config: { users: 3, days: 3, horizon: 3, seed: 1, compare_horizon: false },
  schedulers: { hybrid: "GA + local search", ga: "Constraint-aware GA" },
  metrics: { completed_per_day: { label: "Tasks completed", unit: "per day", higher_is_better: true } },
  summary: {}, wilcoxon_ga_vs: {}, per_user: {}, learning_curve: {}, seconds: 1, data: "synthetic", reference: "hybrid",
  comparisons: { ga: { completed_per_day: { diff: 0.42, ci: [0.1, 0.8], p: 0.01, p_holm: 0.02, effect: 0.61 } } },
} as unknown as EvalResults;

describe("Evaluation results", () => {
  it("shows paired differences with Holm p and effect size", () => {
    render(<Comparisons res={res} ref_="hybrid" names={["ga"]} title="Effect sizes" />);
    expect(screen.getByText("+0.42")).toBeInTheDocument();
    expect(screen.getByText(/p 0.020 · r 0.61/)).toBeInTheDocument();
  });
  it("renders the calibration study", () => {
    const row = { n: 10, coverage: 78.8, pinball80: 7.19, log_score: -0.03, mae: 17.9, p80_padding: 1.6 };
    render(<StudiesView studies={{ calibration: { config: { users: 2, tasks_per_user: 5 }, versions: { v2: { all: row } } } }} />);
    expect(screen.getByText("78.8%")).toBeInTheDocument();
  });
});

describe("Risk tab", () => {
  it("explains the Monte Carlo estimates", () => {
    const plan = { robustness: {
      runs: 300, expected_completed: 8.4, completed_p10: 7, completed_p90: 10, completed_sd: 1, planned: 10,
      p_all_important_done: 0.62, important_planned: 3, important_unplanned: 1, p_all_deadlines_met: 0.5, deadline_safety: 0.81,
      expected_unfinished_minutes: 64, p_overrun_any_day: 0.12, p_overrun_by_day: [0.12, 0], expected_unused_minutes: 600, note: "",
    } } as unknown as PlanVersion;
    const run = { days: [{ date: "2026-11-12" }, { date: "2026-11-13" }] } as unknown as PlanRun;
    render(<Risk plan={plan} run={run} />);
    expect(screen.getByText("8.4 of 10")).toBeInTheDocument();
    expect(screen.getByText(/1 high-priority task is not in the plan/)).toBeInTheDocument();
    expect(screen.getByText(/replayed 300 times/)).toBeInTheDocument();
  });
});
