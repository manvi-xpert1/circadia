# Circadia benchmark results

Generated 2026-11-12 10:22 by `python -m ai.evaluation.benchmark` in 15.1 min on Linux-6.18.44-fc-v378-x86_64-with-glibc2.39 (2 CPU threads).

**All data is synthetic.** Synthetic users have hidden habits (true overrun per category, a daily energy curve, a follow-through rate) that the planner never sees. Plans are graded against that hidden truth, not against the planner's own models. Numbers are means over users with 95% bootstrap confidence intervals.

## Closed-loop comparison: easy workload

12 users × 7 days, 3-day horizon, seed 2026. Each day the user plans at 08:30 and 14:00, then follows the plan against their hidden truth.

| Scheduler | Tasks completed (per day) | Task completion rate (% of planned blocks) | Deadline violations (% of tasks due) | Energy suitability (true fit) (0-1) | Overrun past day end (min/day) | Days planned above 85% load (%) | Overruns into commitments (per day) | Hard-rule violations in plans (total) | Planning time (s per plan) |
|---|---|---|---|---|---|---|---|---|---|
| Priority / deadline | 2.95 [2.75, 3.15] | 79.25 [74.86, 83.58] | 1.89 [0.00, 4.76] | 0.81 [0.77, 0.86] | 1.15 [0.00, 2.76] | 0.00 [0.00, 0.00] | 1.46 [1.26, 1.67] | 0.00 [0.00, 0.00] | 0.00 |
| Duration-aware | 2.85 [2.68, 3.01] | 79.73 [75.62, 84.39] | 4.39 [0.69, 8.64] | 0.82 [0.79, 0.86] | 0.21 [0.00, 0.65] | 5.95 [0.00, 11.90] | 1.20 [1.05, 1.37] | 0.00 [0.00, 0.00] | 0.00 |
| Energy-aware fuzzy | 2.26 [2.05, 2.48] | 78.95 [74.70, 83.26] | 14.32 [8.90, 19.85] | 0.83 [0.79, 0.88] | 0.00 [0.00, 0.00] | 1.19 [0.00, 3.57] | 0.64 [0.46, 0.83] | 0.00 [0.00, 0.00] | 0.00 |
| Constraint-aware GA | 2.50 [2.35, 2.67] | 79.76 [74.71, 85.12] | 4.79 [1.04, 8.96] | 0.84 [0.81, 0.88] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 1.05 [0.94, 1.16] | 0.00 [0.00, 0.00] | 0.12 |
| GA + local search | 2.51 [2.36, 2.70] | 80.44 [75.28, 86.06] | 4.10 [0.00, 8.27] | 0.84 [0.81, 0.88] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 1.09 [1.01, 1.19] | 0.00 [0.00, 0.00] | 0.12 |

Paired differences, **GA + local search minus the other scheduler**, same users. Δ = mean difference [95% bootstrap CI]; p = Wilcoxon signed-rank, Holm-adjusted across schedulers; r = rank-biserial effect size.

| Compared with | Tasks completed | Deadline violations | Energy suitability (true fit) | Overrun past day end |
|---|---|---|---|---|
| Priority / deadline | Δ -0.44 [-0.58, -0.29], p 0.004, r -1.00 | Δ +2.21 [-1.29, +6.59], p 1.000, r 0.60 | Δ +0.03 [+0.00, +0.06], p 0.308, r 0.59 | Δ -1.15 [-2.76, +0.00], p 1.000, r -1.00 |
| Duration-aware | Δ -0.33 [-0.42, -0.23], p 0.004, r -1.00 | Δ -0.29 [-2.72, +2.48], p 1.000, r 0.00 | Δ +0.02 [-0.01, +0.04], p 0.904, r 0.36 | Δ -0.21 [-0.65, +0.00], p 1.000, r -1.00 |
| Energy-aware fuzzy | Δ +0.25 [+0.12, +0.37], p 0.016, r 0.96 | Δ -10.22 [-14.99, -5.22], p 0.031, r -0.96 | Δ +0.00 [-0.03, +0.04], p 1.000, r 0.10 | Δ +0.00 [+0.00, +0.00], p –, r – |
| Constraint-aware GA | Δ +0.01 [+0.00, +0.04], p 1.000, r 1.00 | Δ -0.69 [-2.08, +0.00], p 1.000, r -1.00 | Δ -0.01 [-0.02, +0.01], p 1.000, r -0.28 | Δ +0.00 [+0.00, +0.00], p –, r – |

## Closed-loop comparison: moderate workload

12 users × 7 days, 3-day horizon, seed 2026. Each day the user plans at 08:30 and 14:00, then follows the plan against their hidden truth.

| Scheduler | Tasks completed (per day) | Task completion rate (% of planned blocks) | Deadline violations (% of tasks due) | Energy suitability (true fit) (0-1) | Overrun past day end (min/day) | Days planned above 85% load (%) | Overruns into commitments (per day) | Hard-rule violations in plans (total) | Planning time (s per plan) |
|---|---|---|---|---|---|---|---|---|---|
| Priority / deadline | 5.07 [4.81, 5.32] | 79.18 [75.24, 83.04] | 5.38 [2.76, 7.81] | 0.83 [0.81, 0.86] | 12.50 [7.05, 18.48] | 13.10 [4.76, 22.62] | 2.61 [2.42, 2.81] | 0.00 [0.00, 0.00] | 0.01 |
| Duration-aware | 3.99 [3.74, 4.26] | 82.80 [78.67, 86.49] | 14.94 [11.97, 17.86] | 0.84 [0.82, 0.87] | 0.46 [0.00, 1.09] | 26.19 [16.67, 36.91] | 1.73 [1.58, 1.94] | 0.00 [0.00, 0.00] | 0.00 |
| Energy-aware fuzzy | 3.29 [2.96, 3.56] | 83.22 [78.77, 87.06] | 22.09 [18.39, 26.06] | 0.86 [0.82, 0.89] | 0.00 [0.00, 0.00] | 8.33 [2.38, 14.31] | 1.32 [1.17, 1.49] | 0.00 [0.00, 0.00] | 0.01 |
| Constraint-aware GA | 3.37 [3.11, 3.64] | 83.39 [80.07, 86.70] | 14.29 [9.46, 19.00] | 0.84 [0.81, 0.87] | 0.12 [0.00, 0.34] | 4.76 [0.00, 9.52] | 1.71 [1.50, 1.96] | 0.00 [0.00, 0.00] | 0.25 |
| GA + local search | 3.38 [3.13, 3.62] | 84.60 [80.63, 88.47] | 14.09 [9.15, 18.94] | 0.85 [0.82, 0.88] | 0.00 [0.00, 0.00] | 3.57 [0.00, 7.14] | 1.57 [1.38, 1.76] | 0.00 [0.00, 0.00] | 0.25 |
| CP-SAT solver | 3.46 [3.21, 3.70] | 86.02 [81.74, 90.58] | 12.49 [8.62, 16.13] | 0.83 [0.80, 0.87] | 0.33 [0.00, 0.98] | 8.33 [2.38, 15.48] | 1.64 [1.49, 1.81] | 0.00 [0.00, 0.00] | 1.25 |
| GA, 1-day horizon | 3.89 [3.55, 4.23] | 87.61 [83.08, 92.21] | 18.34 [13.44, 23.79] | 0.87 [0.84, 0.90] | 0.00 [0.00, 0.00] | 3.57 [0.00, 7.14] | 1.74 [1.55, 1.92] | 0.00 [0.00, 0.00] | 0.12 |

Paired differences, **GA + local search minus the other scheduler**, same users. Δ = mean difference [95% bootstrap CI]; p = Wilcoxon signed-rank, Holm-adjusted across schedulers; r = rank-biserial effect size.

| Compared with | Tasks completed | Deadline violations | Energy suitability (true fit) | Overrun past day end |
|---|---|---|---|---|
| Priority / deadline | Δ -1.69 [-1.89, -1.50], p 0.004, r -1.00 | Δ +8.71 [+4.10, +13.16], p 0.088, r 0.85 | Δ +0.02 [-0.01, +0.04], p 1.000, r 0.20 | Δ -12.50 [-18.48, -7.05], p 0.004, r -1.00 |
| Duration-aware | Δ -0.61 [-0.82, -0.39], p 0.004, r -1.00 | Δ -0.85 [-5.37, +3.42], p 1.000, r -0.09 | Δ +0.01 [-0.02, +0.04], p 1.000, r 0.03 | Δ -0.46 [-1.09, +0.00], p 1.000, r -1.00 |
| Energy-aware fuzzy | Δ +0.10 [-0.08, +0.30], p 0.992, r 0.28 | Δ -8.01 [-12.84, -3.16], p 0.130, r -0.79 | Δ -0.01 [-0.04, +0.02], p 1.000, r -0.31 | Δ +0.00 [+0.00, +0.00], p –, r – |
| Constraint-aware GA | Δ +0.01 [-0.15, +0.18], p 0.992, r 0.06 | Δ -0.20 [-3.12, +2.43], p 1.000, r 0.00 | Δ +0.01 [-0.02, +0.03], p 1.000, r 0.39 | Δ -0.12 [-0.34, +0.00], p 1.000, r -1.00 |
| CP-SAT solver | Δ -0.08 [-0.21, +0.04], p 0.992, r -0.40 | Δ +1.60 [-0.04, +3.28], p 0.938, r 0.52 | Δ +0.01 [-0.01, +0.04], p 1.000, r 0.31 | Δ -0.33 [-0.98, +0.00], p 1.000, r -1.00 |
| GA, 1-day horizon | Δ -0.51 [-0.71, -0.29], p 0.017, r -0.91 | Δ -4.25 [-9.25, +0.39], p 0.824, r -0.46 | Δ -0.02 [-0.05, +0.00], p 1.000, r -0.49 | Δ +0.00 [+0.00, +0.00], p –, r – |

### Ablations (moderate)

Each row removes one component from the full system (GA + local search, hierarchical durations).

| Scheduler | Tasks completed (per day) | Task completion rate (% of planned blocks) | Deadline violations (% of tasks due) | Energy suitability (true fit) (0-1) | Overrun past day end (min/day) | Days planned above 85% load (%) | Overruns into commitments (per day) | Hard-rule violations in plans (total) | Planning time (s per plan) |
|---|---|---|---|---|---|---|---|---|---|
| GA + local search | 3.38 [3.13, 3.62] | 84.60 [80.63, 88.47] | 14.09 [9.15, 18.94] | 0.85 [0.82, 0.88] | 0.00 [0.00, 0.00] | 3.57 [0.00, 7.14] | 1.57 [1.38, 1.76] | 0.00 [0.00, 0.00] | 0.25 |
| Hybrid without fuzzy energy fit | 3.52 [3.32, 3.74] | 84.03 [80.12, 87.63] | 11.14 [6.92, 15.53] | 0.82 [0.79, 0.86] | 0.21 [0.00, 0.56] | 4.76 [0.00, 9.52] | 1.77 [1.61, 1.93] | 0.00 [0.00, 0.00] | 0.20 |
| Hybrid without learned durations | 4.33 [4.05, 4.66] | 86.16 [82.63, 89.85] | 6.23 [3.19, 9.07] | 0.86 [0.83, 0.89] | 0.84 [0.15, 1.72] | 0.00 [0.00, 0.00] | 2.14 [1.96, 2.33] | 0.00 [0.00, 0.00] | 0.23 |
| Hybrid with the original duration model | 3.61 [3.32, 3.88] | 85.24 [80.42, 89.57] | 11.29 [6.37, 16.39] | 0.85 [0.83, 0.87] | 0.33 [0.00, 0.98] | 1.19 [0.00, 3.57] | 1.71 [1.52, 1.93] | 0.00 [0.00, 0.00] | 0.26 |

Paired differences, **GA + local search minus the other scheduler**, same users. Δ = mean difference [95% bootstrap CI]; p = Wilcoxon signed-rank, Holm-adjusted across schedulers; r = rank-biserial effect size.

| Compared with | Tasks completed | Deadline violations | Energy suitability (true fit) | Days planned above 85% load |
|---|---|---|---|---|
| Hybrid without fuzzy energy fit | Δ -0.14 [-0.34, +0.02], p 0.992, r -0.44 | Δ +2.95 [+0.47, +5.66], p 0.469, r 0.72 | Δ +0.02 [-0.01, +0.06], p 1.000, r 0.36 | Δ -1.19 [-5.95, +2.38], p 1.000, r -0.33 |
| Hybrid without learned durations | Δ -0.95 [-1.17, -0.73], p 0.004, r -1.00 | Δ +7.86 [+3.83, +12.02], p 0.088, r 0.89 | Δ -0.01 [-0.04, +0.01], p 1.000, r -0.28 | Δ +3.57 [+0.00, +7.14], p 1.000, r 1.00 |
| Hybrid with the original duration model | Δ -0.23 [-0.36, -0.10], p 0.039, r -0.93 | Δ +2.80 [+0.01, +6.11], p 0.742, r 0.61 | Δ -0.00 [-0.02, +0.01], p 1.000, r -0.08 | Δ +2.38 [+0.00, +5.95], p 1.000, r 1.00 |
| Constraint-aware GA | Δ +0.01 [-0.15, +0.18], p 0.992, r 0.06 | Δ -0.20 [-3.12, +2.43], p 1.000, r 0.00 | Δ +0.01 [-0.02, +0.03], p 1.000, r 0.39 | Δ -1.19 [-5.95, +3.57], p 1.000, r -0.20 |

## Closed-loop comparison: tight workload

12 users × 7 days, 3-day horizon, seed 2026. Each day the user plans at 08:30 and 14:00, then follows the plan against their hidden truth.

| Scheduler | Tasks completed (per day) | Task completion rate (% of planned blocks) | Deadline violations (% of tasks due) | Energy suitability (true fit) (0-1) | Overrun past day end (min/day) | Days planned above 85% load (%) | Overruns into commitments (per day) | Hard-rule violations in plans (total) | Planning time (s per plan) |
|---|---|---|---|---|---|---|---|---|---|
| Priority / deadline | 5.82 [5.54, 6.12] | 71.81 [67.50, 76.22] | 20.46 [16.20, 25.10] | 0.83 [0.81, 0.85] | 34.96 [23.64, 48.78] | 90.48 [83.33, 96.43] | 3.58 [3.42, 3.73] | 0.00 [0.00, 0.00] | 0.01 |
| Duration-aware | 4.25 [4.06, 4.46] | 83.58 [79.61, 87.71] | 36.93 [31.90, 42.50] | 0.85 [0.83, 0.88] | 0.38 [0.00, 1.04] | 47.62 [38.09, 58.33] | 2.35 [2.21, 2.49] | 0.00 [0.00, 0.00] | 0.01 |
| Energy-aware fuzzy | 3.86 [3.57, 4.09] | 81.80 [77.60, 85.89] | 38.51 [31.82, 44.73] | 0.85 [0.83, 0.88] | 0.54 [0.00, 1.25] | 29.76 [22.62, 39.29] | 1.84 [1.69, 1.99] | 0.00 [0.00, 0.00] | 0.01 |
| Constraint-aware GA | 3.99 [3.79, 4.21] | 86.82 [82.52, 91.20] | 18.19 [14.11, 22.62] | 0.88 [0.86, 0.90] | 1.39 [0.00, 2.80] | 10.71 [5.95, 15.48] | 2.14 [1.93, 2.35] | 0.00 [0.00, 0.00] | 0.35 |
| GA + local search | 3.90 [3.67, 4.16] | 85.60 [82.59, 88.57] | 21.24 [17.23, 24.92] | 0.88 [0.85, 0.90] | 0.34 [0.03, 0.78] | 16.67 [9.52, 23.81] | 2.19 [2.02, 2.35] | 0.00 [0.00, 0.00] | 0.38 |

Paired differences, **GA + local search minus the other scheduler**, same users. Δ = mean difference [95% bootstrap CI]; p = Wilcoxon signed-rank, Holm-adjusted across schedulers; r = rank-biserial effect size.

| Compared with | Tasks completed | Deadline violations | Energy suitability (true fit) | Overrun past day end |
|---|---|---|---|---|
| Priority / deadline | Δ -1.92 [-2.17, -1.64], p 0.002, r -1.00 | Δ +0.78 [-4.01, +5.27], p 0.733, r 0.13 | Δ +0.05 [+0.02, +0.08], p 0.014, r 0.90 | Δ -34.62 [-48.37, -23.52], p 0.002, r -1.00 |
| Duration-aware | Δ -0.34 [-0.62, -0.05], p 0.243, r -0.61 | Δ -15.68 [-21.76, -10.28], p 0.004, r -0.95 | Δ +0.02 [-0.00, +0.05], p 0.904, r 0.36 | Δ -0.05 [-0.92, +0.63], p 1.000, r 0.07 |
| Energy-aware fuzzy | Δ +0.05 [-0.17, +0.29], p 1.000, r 0.00 | Δ -17.27 [-22.81, -11.44], p 0.002, r -1.00 | Δ +0.02 [-0.01, +0.05], p 0.904, r 0.31 | Δ -0.20 [-1.04, +0.36], p 1.000, r 0.00 |
| Constraint-aware GA | Δ -0.08 [-0.24, +0.07], p 0.668, r -0.36 | Δ +3.05 [-0.62, +6.53], p 0.259, r 0.51 | Δ +0.00 [-0.02, +0.02], p 1.000, r 0.00 | Δ -1.06 [-2.49, +0.10], p 0.938, r -0.60 |

## Solver benchmark: plan quality by problem size

5 random problems per size, 3-day horizon. Fitness is the full Balanced fitness (higher is better) for every optimiser. Gap = shortfall from the best plan any optimiser found for that problem. Every plan was re-checked by the independent hard-rule engine.

| Tasks | Optimiser | Fitness | Gap to best | Best on | Seconds | Rule violations | Solver status |
|---|---|---|---|---|---|---|---|
| 10 | ga | 0.7348 | 0.73% | 0/5 | 0.71 | 0 |  |
| 10 | hybrid | 0.7378 | 0.33% | 0/5 | 0.71 | 0 |  |
| 10 | cpsat_2s | 0.7400 | 0.03% | 3/5 | 1.87 | 0 | FEASIBLE 3, OPTIMAL 2 |
| 10 | cpsat_10s | 0.7402 | 0.00% | 5/5 | 4.24 | 0 | OPTIMAL 5 |
| 20 | ga | 0.6921 | 2.24% | 0/5 | 1.05 | 0 |  |
| 20 | hybrid | 0.7080 | 0.01% | 4/5 | 0.95 | 0 |  |
| 20 | cpsat_2s | 0.6017 | 14.97% | 0/5 | 2.05 | 0 | FEASIBLE 5 |
| 20 | cpsat_10s | 0.7024 | 0.78% | 1/5 | 10.06 | 0 | FEASIBLE 5 |
| 30 | ga | 0.6217 | 2.77% | 0/5 | 1.24 | 0 |  |
| 30 | hybrid | 0.6397 | 0.00% | 5/5 | 1.31 | 0 |  |
| 30 | cpsat_2s | 0.5044 | 21.09% | 0/5 | 1.88 | 0 | FEASIBLE 5 |
| 30 | cpsat_10s | 0.5820 | 8.99% | 0/5 | 10.08 | 0 | FEASIBLE 5 |
| 40 | ga | 0.5640 | 3.37% | 0/5 | 0.95 | 0 |  |
| 40 | hybrid | 0.5836 | 0.00% | 5/5 | 1.07 | 0 |  |
| 40 | cpsat_2s | 0.4451 | 23.69% | 0/5 | 2.02 | 0 | UNKNOWN 4, FEASIBLE 1 |
| 40 | cpsat_10s | 0.5305 | 9.24% | 0/5 | 10.11 | 0 | FEASIBLE 5 |

Gap = shortfall from the best plan any optimiser found for that instance (full fitness). CP-SAT is time-limited and multi-threaded, so its numbers can vary slightly between runs and machines.

## Replanning stability

36 disruptions (an urgent 90-minute task, or 2 hours of lost time), each replanned at 11:00 against the 08:30 plan (about 8.4 planned blocks). Quality is the Balanced fitness without the stability term. Each case is one disruption replanned at every level from the same morning plan (paired).

| Stability | Blocks changed | Minutes moved | Quality | Deadline safety (MC) | Urgent task placed |
|---|---|---|---|---|---|
| 0.0 | 6.22 | 3246 | 0.7050 | 0.762 | 55.6% |
| 0.25 | 2.06 (p <0.001) | 780 | 0.7010 (Δ -0.0040, p 0.001) | 0.764 | 55.6% |
| 0.5 | 1.53 (p <0.001) | 642 | 0.6980 (Δ -0.0070, p <0.001) | 0.758 | 55.6% |
| 1.0 | 1.08 (p <0.001) | 338 | 0.6880 (Δ -0.0170, p <0.001) | 0.739 | 44.4% |

## Duration model calibration

40 users × 40 tasks, predicted one at a time from earlier outcomes. A calibrated P80 covers 80% of real durations. Pinball loss (minutes) scores P80 for calibration and tightness together; lower is better.

| Model | Outcomes in category | Tasks | P80 coverage | Pinball loss | Log score | Median error (min) |
|---|---|---|---|---|---|---|
| v1 | all | 1600 | 73.9% | 7.12 | -0.036 | 18.37 |
| v1 | 0 | 184 | 73.4% | 7.39 | -0.115 | 19.88 |
| v1 | 1-2 | 323 | 73.7% | 8.16 | -0.174 | 20.95 |
| v1 | 3-9 | 708 | 72.9% | 6.87 | 0.008 | 17.28 |
| v1 | 10+ | 385 | 76.1% | 6.56 | 0.037 | 17.46 |
| v2 | all | 1600 | 79.1% | 7.08 | -0.027 | 17.82 |
| v2 | 0 | 184 | 78.3% | 7.52 | -0.183 | 19.62 |
| v2 | 1-2 | 323 | 79.6% | 7.78 | -0.119 | 19.36 |
| v2 | 3-9 | 708 | 79.0% | 6.84 | 0.023 | 16.96 |
| v2 | 10+ | 385 | 79.5% | 6.70 | 0.033 | 17.25 |

Pinball difference (v2 minus v1, minutes; negative favours v2): -0.040 [-0.199, +0.114].
