# Circadia 2.0: algorithmic improvements

This file covers what changed on top of the school version, why, and how each change was checked. Measured results are in [RESULTS.md](RESULTS.md); the audit that motivated the work is in [AUDIT.md](AUDIT.md).

## Headline findings

All on synthetic users; see RESULTS.md for every table, confidence interval and test.

| Question | Answer |
|---|---|
| Does local search improve the GA? | Yes, on its objective. The hybrid found the best plan on 14 of 15 problems with 20–40 tasks; the GA alone was 2.2–3.4% behind. It takes about the same time (~1 s). |
| How close is it to an exact solver? | CP-SAT proved optimality on all 10-task problems, where the hybrid was 0.33% behind. At 20+ tasks, CP-SAT with 10 s (2 threads) did not catch up: 0.8% behind at 20 tasks, 9% at 30–40. |
| Do better plans give better days? | Not measurably. Against the plain GA, the hybrid's paired differences in tasks completed, deadlines and energy fit were all small and non-significant in all three workloads. |
| Which component matters most? | Learned P80 durations, in the wrong direction for task count: planning with raw estimates finished ~1 more task per day (p = 0.004), and missed fewer deadlines in this simulation. Fuzzy energy fit made no significant difference to outcomes once the GA was optimising. |
| Is the new duration model better? | Calibration: yes (P80 coverage 79.1% vs 73.9%, target 80%; lower median error). Closed loop: its wider blocks finished slightly fewer tasks (3.38 vs 3.61 per day, p = 0.039). |
| Does stability-aware replanning work? | Yes: 6.2 → 1.5 blocks changed per disruption at 50% stability (p < 0.001), for a 1% quality cost. |

What this means for the next version: the planner optimises its objective well, but the objective (especially reserving P80 time) is now the bottleneck, not the search. The next experiment is the block-length quantile as a setting (P50 / P65 / P80), evaluated in the same lab.

Everything still runs offline, the app's screens and API are unchanged apart from additions, and every plan from every optimiser still passes the independent hard-rule check.

---

## Phase 2: Hybrid GA (GA + local search)

**Change.** After the GA finishes, its best plan is refined by best-improvement hill climbing over five neighbourhoods (`ai/ga/local_search.py`):

| Move | What it does |
|---|---|
| Relocate | Move a block ±1, 2 or 4 slots, or to the earliest / best-energy-fit legal start on any day |
| Insert | Place an unscheduled task at the earliest / best-fit legal start on any day |
| Remove | Drop a block, if nothing scheduled depends on it |
| Swap | Exchange the starts of two blocks |
| Make room | Insert an unscheduled task over one or two blocks and re-seat them at their nearest legal start |

**Reasoning.** The decoder places tasks greedily from hints, so many hint mutations decode to the same plan, and the GA plateaus. Local search works on the decoded plan directly and makes exact single-block moves. "Make room" is a depth-one ejection chain. Hill climbing can't find it as two separate moves, because moving a block out of the way scores worse on its own. Without it, a stability-aware replan would leave an urgent task out rather than nudge one block.

**Guarantees.**
- Every candidate is checked against the grid before scoring: one free gap of one day, after the release time and the prerequisite's end, ending by the deadline, and not past any scheduled dependent's start.
- Scoring uses the GA's own fitness, and a move is accepted only if it improves it. The result can therefore never be worse than the GA's plan.
- Budgets: an evaluation cap (default 4,000) and a time cap (1 s; the evaluation lab budgets by count only, so runs repeat exactly).
- `chromosome_for` rebuilds a chromosome that decodes to the refined plan, so the explainer's counterfactuals keep working.

**Interaction.** `run_hybrid` = `run_ga` + `local_search` and returns the same `GAResult`. The hybrid is now the default optimiser; the plain GA remains selectable in Settings.

**Files.** New: `ai/ga/local_search.py`. Changed: `ai/ga/runner.py` (`run_hybrid`, `GAResult.optimizer/details`), `ai/pipeline.py`.

**Tests.** A random-chromosome property test checks that local search never breaks a hard rule and never gets worse. Others cover the chromosome round-trip, hybrid ≥ GA ≥ every baseline, reproducibility, the evaluation budget, and scaling to 30 tasks.

---

## Phase 3: CP-SAT scheduler

**Change.** `ai/cpsat/scheduler.py` adds a time-indexed constraint-programming model solved by Google OR-Tools CP-SAT, as an extra optimiser (not a replacement).

**Formulation.**
- Variables: x[i,s] ∈ {0,1}, "task i starts at slot s". A variable exists only for starts that are legal in isolation, which encodes H1–H3, H6–H9 by construction.
- Constraints: Σₛ x[i,s] ≤ 1 per task; at most one block covering each slot (H4); y_dep ≥ y_j and S_j ≥ S_dep + L_dep when y_j = 1 (H5).
- Objective: the fitness is a weighted sum of eight terms.
  - Priority coverage, deadline safety and late-work preference are linear in x.
  - Energy fit and realistic durations are weighted averages over scheduled tasks. They become linear once the denominator is fixed, so the solver iterates: solve with the previous solution's denominator, recompute, and re-solve warm-started (2 rounds).
  - Overload and day balance are linearised with auxiliary max() variables. Day load uses a two-sided ceiling (load·free ≥ work and ≤ work + free − 1), so the solver can neither shrink nor inflate a day's load.
  - Context switching and focus runs depend on which blocks touch. They are approximated by charging each touching (or one-slot-apart) pair of blocks.

**Honesty about the surrogate.** CP-SAT optimises this surrogate. Every solution is re-scored with the real fitness and re-checked by the hard-rule engine, so reported numbers are on the same scale as the GA's. "OPTIMAL" in the results means optimal for the surrogate in that round, not for the full fitness, and the benchmark reports solver status rather than claiming optimality. The first version left out the adjacency terms entirely and scored about 0.05 below the GA, because it packed blocks back-to-back. Adding the adjacency approximation brought the surrogate within about 0.002 of the true fitness on the test problems.

**Configuration.**
- Wall-clock limit (default 10 s in the app's Thorough mode, 2 s in the lab), shared across rounds.
- Worker count (default: one per core, up to 8).
- An optional deterministic mode: work-unit limit with interleaved workers. It is reproducible, at about 3× the time for the same quality.
- If the solver finds nothing in time, the greedy start plan is kept and the run is flagged as a fallback. The lab counts fallbacks instead of dropping them.

**Interaction.** Same `GAResult` interface. In the app, "Thorough" runs the hybrid first and warm-starts CP-SAT from it, keeping whichever plan scores higher. Only the main plan uses the solver, so a plan takes under about 10 s.

**Tests.** Covered: independent rule check on random problems, prerequisites / lectures / deadlines, a task that can't fit anywhere (reported as NO_ROOM, not an error), an empty problem, and every optimiser through the full pipeline.

---

## Phase 4: Hierarchical duration model (v2)

**Change.** `DurationModel(version="v2")`, now the default, is an empirical-Bayes two-level model of ln(actual / estimate).

1. **User level.** A Normal–scaled-inverse-χ² posterior over all of the user's outcomes, with the original default as prior (mean ln 1.15, spread 0.30, worth 3 outcomes).
2. **Category level.** The same update, but the prior is the user's posterior, worth κ = s²/τ² outcomes. τ² is the between-category variance, estimated by method of moments from the category means minus their sampling noise, and floored at 0.05². Similar categories share strength; genuinely different ones keep their own estimate. κ is clipped to [0.5, 20].
3. **Predictive P80.** A Student-t with ν + n − 1 degrees of freedom and scale s·√(1 + 1/(κ + n)). It widens P80 when data are scarce, and reduces to v1's formula as n grows (tested).
4. **Robustness.** Log ratios are winsorised at the user's median ± 3 robust standard deviations (MAD, at least 0.15), so one "forgot to stop the timer" record can't drag a category.

**Assumptions.** Ratios are lognormal and stable over time (no recency weighting); categories are exchangeable a priori; outcomes are independent.

**Evidence.** The calibration study (`ai/evaluation/calibration.py`) predicts each task from earlier outcomes only and compares P80 coverage, pinball loss, log score and median error across v1 and v2, split by how much data the category had. See RESULTS.md.

**Interface.** `for_category()` still returns a `DurationEstimate` with `m`, `s`, `median`, `p80` and `p_fits`. New methods (`cdf_log`, `sample_z`, `log_density`) make the deadline table and the Monte Carlo replay use the right distribution. The design doc's worked examples are v1 formulas, so those tests pin `version="v1"`.

---

## Phase 5: Monte Carlo robustness of finished plans

**Change.** `ai/uncertainty.py` replays a finished plan (default 300 runs, configurable, seeded):
- A block happens with its category's follow-through probability.
- Its duration is drawn from the same duration model that set its P80 length.
- It starts at its planned time or when the previous block ends, whichever is later.
- It waits out a commitment it would start inside, and pauses for one it overruns into.
- Work stops at the end of the day.

**Reported:**
- expected tasks finished, with a P10–P90 range
- P(all high-priority blocks done)
- P(all planned deadlines met)
- deadline safety: the share of tasks due in the horizon that finish on time, where unplanned ones count as late
- expected unfinished minutes
- P(a day overruns), overall and per day
- expected spare time

These appear in a new "What could go wrong" tab and on every alternative.

**Avoiding double counting.** Durations are sampled from the model's own distribution, not P80 plus extra noise, and the planner's P(complete) is not reused. Energy is not varied. The planner has no learned link from energy to duration or follow-through, so any effect here would be invented rather than estimated. (The synthetic users in the lab do have one, as part of their hidden truth.)

**Why not inside the GA.** 60 individuals × ~100 generations × hundreds of replays per plan is too slow. And the fitness already rewards P80 padding through the "realistic durations" term, so adding simulated outcomes there would count the same uncertainty twice. The replay is used to score and compare finished plans instead.

**Tests.** Covered: reproducibility, bounds, an empty plan, and a test that the replay detects knock-on delays (the same five blocks packed at the end of the day overrun more often than spread out).

---

## Phase 6: Stability-aware replanning

**Change.** A replan can carry the plan it replaces (`PlanRequest.previous`) and a stability level in [0, 1]. The fitness gains a penalty:

```
P_stab = Σ wᵢ · cost(prevᵢ, newᵢ) / Σ wᵢ          over tasks in the previous plan
cost   = 0 kept · 0.25 + 0.75 · min(1, |Δslots| / slots_per_day) moved · 1 dropped
F      = F_preset − 0.40 · stability · P_stab
```

At stability 1, dropping all previous blocks costs about as much as the priority term is worth. Locked blocks stay fixed as before, and fixed tasks never move.

When there is a previous plan, the GA is seeded with it, with new tasks at their best-fit start. Local search and CP-SAT optimise the same term, CP-SAT as a linear per-start bonus.

**Product integration.**
- The app replans against the current plan when you press Regenerate. A "Keep current plan steady" toggle and a Settings slider control it (default 50%).
- What-if replans the "after" plan against the "before" plan. It also returns a from-scratch replan so the two can be compared side by side.
- When steadiness is what keeps an urgent task out, What-if says what fitting it in would cost and points to the slider.

**Metrics.** Blocks kept / moved / removed / added and total displacement, reported on every plan (`plan.stability`).

**Evidence.** The stability study (`ai/evaluation/studies.py`) replans the same disruptions at levels 0, 0.25, 0.5 and 1. It reports blocks changed, minutes moved, quality *without* the stability term (so stability can't flatter itself), simulated deadline safety, and whether the urgent task was placed, all paired against the free replan.

---

## Phase 7: Trade-offs between alternatives (instead of NSGA-II)

**Decision.** NSGA-II was not implemented.

**Why.**
- Circadia already produces up to three plans: three weightings of one fitness, i.e. three points on the trade-off surface.
- With five objectives, NSGA-II's crowding distance spreads solutions poorly.
- A single user can't usefully compare a large front.
- It would add a second evolutionary optimiser to maintain and test.

**What was built.** `ai/tradeoffs.py` compares the existing alternatives on separate objectives, without adding them up:
- expected tasks finished (Monte Carlo)
- deadline safety (Monte Carlo)
- energy fit
- a lighter busiest day
- keeping the existing plan (when replanning)

Each plan is marked Pareto-optimal or dominated (with tolerances, because Monte Carlo estimates are noisy). It is labelled with what it is best at, and what it gives up compared with the main plan. On the demo week it flagged the Balanced plan as dominated by the Deadline-first and Gentle plans, which the UI now says plainly.

---

## Phase 8: Evaluation lab

New in the closed-loop experiment (`ai/evaluation/experiment.py`):

- **Schedulers.**
  - New: GA + local search (now the reference) and CP-SAT (optional, 2 s per plan).
  - Ablations of the full system: without fuzzy energy fit (U ≡ 0.5), without learned durations (block = user's estimate), and with the original duration model.
- **Difficulty tiers.**

  | Tier | New tasks per day | Lectures per day |
  |---|---|---|
  | Easy | 2–4 | 1–2 |
  | Moderate | 4–7 | 1–3 |
  | Tight | 7–10 | 2–4 |

- **Statistics.** Paired difference against the reference with a bootstrap 95% CI, Wilcoxon signed-rank p, Holm correction across the schedulers compared for each metric, and the matched-pairs rank-biserial effect size.
- **Honest accounting.**
  - Solver fallbacks are counted, never dropped.
  - Planning time is reported separately from the reproducible summary.
  - The algorithm version, duration-model version and GA / local-search settings are recorded with every run.
- **Studies.** Duration calibration, replanning stability, and a solver benchmark (GA vs hybrid vs CP-SAT at 2 s and 10 s on 10–40-task problems: fitness, gap to best, runtime, rule violations, solver status).
- **One command.** `python -m ai.evaluation.benchmark` runs everything and writes `RESULTS.md` plus the full JSON. All of it is selectable in the lab UI too.

---

## Test suite

- **Backend:** 130 tests (71 original + 59 new), 97% line coverage of `ai/`, including property-based tests with Hypothesis for the decoder and local search.
- **Frontend:** 9 tests (6 original + 3 new).
- Every optimiser's plans are checked by the independent hard-rule engine.
- CI (`.github/workflows/ci.yml`) runs the backend tests with coverage, a quick benchmark, and the frontend tests and build.

## Known limitations

- All evaluation data is synthetic. The synthetic users' hidden truth is a modelling choice, and results show behaviour under those assumptions, not proof of real-world benefit.
- CP-SAT optimises a surrogate of the fitness; time-limited multi-worker runs can vary slightly between runs and machines.
- The duration model assumes stable habits; a recency-weighted version would adapt faster to change but was not evaluated.
- Stability is a soft preference. At high levels it can keep a lower-priority block over a new urgent one (urgent placement fell from 55.6% to 44.4% at stability 1.0), which is why What-if spells out that trade-off.
- The CP-SAT figures were measured on 2 CPU threads. With more cores it will do better within the same time limit; rerun the benchmark to see.
- Where the four ablations disagree with the main comparison, the sample is 12 users. Several differences have wide intervals and do not survive the Holm correction.
