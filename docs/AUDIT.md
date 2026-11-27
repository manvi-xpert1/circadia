# Codebase audit

The audit of the Circadia AI code (`backend/ai/`, about 1,700 statements) before any changes. It decided what was built, and what was not.

## How the AI components fit together

```
PlanRequest ──► problem.build_problem ──► Problem ──► optimiser ──► Decoded plan ──► pipeline.verify ──► explainer
                 │ 15-min grid, free gaps             (GA)          (start slot        (hard rules on
                 │ DurationModel → P80 block length                  per task)          real datetimes)
                 │ FollowThroughModel → P(happens)
                 │ fuzzy engine → U[task, slot]
                 └ deadlines, dependencies, release times → slot limits
```

- **Fuzzy logic** (`fuzzy/`): two Mamdani stages, defuzzified by centroid. The first gives capacity per slot from check-in energy, focus and stress plus a learned time-of-day profile. The second gives suitability U[task, slot] from capacity minus demand.
- **Probability** (`probability/`): a lognormal duration model per category whose spread is learned with a prior, and a Beta(4, 1) follow-through model. P80 sets block length; P(complete) = follow-through × P(duration ≤ block).
- **Rules** (`rules/`): hard rules H1–H9 written once as grid-free predicates over datetimes (the independent validator), and soft rules A1–A8 that feed fitness penalties.
- **GA** (`ga/`): the chromosome is (order, hint start per task). A greedy decoder places each task in the free gap nearest its hint, so every decoded plan is legal by construction. Population 60, tournament of 3, OX1 + uniform crossover, swap/shift/jump/toggle mutation, elitism 2, early stop after 20 stale generations. Fitness is a weighted sum of 8 terms, with three presets.
- **Evaluation** (`evaluation/`): a closed-loop simulation on synthetic users with hidden truth, paired by seed, with bootstrap CIs and Wilcoxon tests.

## What already works well

- **Legality is structural, not penalised.** The decoder can only use free time, and an independent rule engine re-checks every plan on real datetimes. A Hypothesis test feeds random chromosomes and finds no violations. Any new optimiser should keep both layers.
- **The evaluation is not circular.** Plans are graded by a hidden "true fit" formula, not the planner's fuzzy model, and every scheduler sees the identical world.
- **Explanations are computed, not templated guesses.** Counterfactuals re-decode the chromosome, which requires any new optimiser to return a chromosome that decodes to its plan.
- **Reproducibility.** Seeds are stored with plans; the experiment is deterministic.

## Weaknesses found

| # | Area | Finding | Evidence | Addressed in |
|---|---|---|---|---|
| 1 | GA | The greedy decoder snaps tasks to the nearest legal gap in chromosome order. Small exact moves (shift 15 min into a better-fit slot, swap two blocks, re-seat a block to make room) are hard to reach through hints: a mutated hint often decodes to the same plan. | On 10 random 20-task problems the GA stopped after 25–120 generations (mean 73), and a local search started from its best plan still improved it every time. | Local search |
| 2 | GA | No reference point for solution quality beyond a brute-force check on 5-task problems. "Near-optimal" was unmeasured at realistic sizes. | `test_ga_close_to_brute_force_on_small_problems` only covers n = 5. | CP-SAT |
| 3 | Durations | A category switches abruptly from the pooled estimate to its own data at exactly 3 outcomes, and its prior is the population default, not the user's own pace. | `DurationModel.for_category`. | Hierarchical duration model |
| 4 | Durations | P80 ignores uncertainty in the mean itself, so with few outcomes it is too narrow. | The calibration study measured P80 coverage of 74% against a target of 80%. | Hierarchical duration model |
| 5 | Probability | P(complete) is per block. Knock-on delays (a long block pushes the next one into a lecture or past the end of the day) are invisible to the planner and the user. | `TaskInfo.p_complete`. | Monte Carlo replay |
| 6 | Replanning | Every Regenerate or What-if replans from scratch: a different seed or a small change can reshuffle the whole plan. | What-if test: an urgent task moved 11 of 12 blocks. | Stability-aware replanning |
| 7 | Alternatives | Alternatives are filtered only by similarity; nothing tells the user whether one is simply worse than another. | `pipeline.similarity`. | Pareto filter |
| 8 | Evaluation | No effect sizes, no multiple-comparison correction, a single workload level, no ablations, no runtime figures. | `experiment.run_experiment`. | Evaluation lab |
| 9 | Behaviour | In the closed-loop lab, the priority baseline finishes more tasks per day than the GA (about 5 vs 3.4) and misses fewer deadlines (6% vs 14%). | README "The evaluation, honestly". | Investigated with ablations |

## Performance

- One decode costs about 0.05 ms and one fitness evaluation about 0.06 ms (25 tasks, 3 days). A GA run makes 2,000–3,000 of each, so most of its 0.5–1 s goes to Python overhead in the operators and the loop. Local search on decoded plans is cheap by comparison: a few thousand moves cost under 0.1 s.
- The suitability matrix is built with a Python double loop over (slot, task), about 0.1 s for 25 tasks × 3 days. That is acceptable and was left alone.

## Decisions

- **Build:** local-search refinement (memetic GA), a CP-SAT scheduler behind the same `GAResult` interface, a hierarchical duration model as a selectable version, Monte Carlo replay of finished plans, a stability term in the objective, a Pareto filter on alternatives, and an extended evaluation lab.
- **Keep:** the decoder-based legality guarantee and the independent validator, used for every optimiser.
- **Don't build:** NSGA-II (see `IMPROVEMENTS.md`, "Trade-offs between alternatives"), and Monte Carlo inside the GA fitness function (60 × 120 × N simulations per plan is too slow, and it would double-count the P80 padding the fitness already rewards).
- **Don't rename modules** to match a generic architecture list. The existing package layout (`fuzzy/`, `probability/`, `rules/`, `ga/`, `evaluation/`) already separates the concerns.

## Compatibility risks and how they were handled

| Risk | Handling |
|---|---|
| Explainer counterfactuals need a chromosome that decodes to the plan | `local_search.chromosome_for` builds one; a property test checks it round-trips. |
| A new duration model changes the design doc's worked examples | The original model stays available as `version="v1"`; the worked-example tests pin v1. |
| Existing `planner.db` files lack new preference columns | The existing startup migration adds them with defaults. |
| CP-SAT is non-deterministic with several workers and a wall-clock limit | Documented; a deterministic mode exists; the lab counts solver fallbacks instead of dropping them. |
| Wall-clock timing breaks the "same seed, same results" guarantee | Runtime is reported in a separate `runtime` section, outside the reproducible `summary`. |

---

# Second review: scoring, Monte Carlo and block length

A second review of the AI code, done before changing the scoring, to decide which changes the evidence could justify. Each finding was checked in code; the experiments that settled them are in `RESULTS.md`, Part 1.

| # | Area | Finding | Evidence in code | Outcome |
|---|---|---|---|---|
| 10 | Scoring | Two models answered overlapping questions. The fuzzy engine gave a 0–1 "suitability" per slot; the follow-through model gave a probability per category. They were multiplied as if both were probabilities, but suitability is not one, and neither learned how energy affects whether a block actually happens. | `problem.py` built U from fuzzy suitability; `TaskInfo.p_complete = follow × P(fits)`. | Replaced by one contextual completion model (`probability/completion.py`). It predicts better (Brier −0.0046, AUC 0.70 against 0.58), with no measurable change in closed-loop outcomes. |
| 11 | Learning data | Outcomes were stored without the context the plan was made in (projected energy, focus, stress, demands). A model of "does this block happen at this time" could not be trained from them. | `TaskOutcome` had status and minutes only. | Context is now saved with each block at planning time and stored with the outcome only if the block wasn't moved (`schedules.record_outcome`). |
| 12 | Censoring | In the simulator, blocks the day never reached were recorded as **skipped**, teaching the model that users skip blocks that were simply never started. | `experiment.simulate`, end-of-day handling. | Recorded as "unreached" and excluded from training (censored). |
| 13 | Monte Carlo | The replay reported risk but never influenced which plan was chosen. Each estimate had no standard error, and draws were taken in block order, so two plans were compared under different luck. | `uncertainty.simulate_plan`. | Standard errors, tiers, adaptive stopping and common random numbers added. Outcome-based plan selection was built and tested; it showed no benefit, so it is off by default. |
| 14 | Monte Carlo | Heavy-tailed cold-start durations (Student-t, 3 df, on the log scale) produced replayed blocks of hundreds of hours. | A 120-min task replayed at 219× its estimate. | Replayed durations truncated at 4× the estimate. |
| 15 | Block length | Every block was reserved at P80. The earlier benchmark had already shown that this costs completed tasks (ablation `abl_no_prob`). | `TaskInfo.planned`. | Quantile made a setting, plus an optional shared daily buffer; P65 chosen as the app default from a paired experiment. |
| 16 | Interface | Optimiser, stability and simulation details sat beside everyday settings; the Why panel listed fuzzy rule strengths that users could not act on. | `Settings.tsx`, `WhyPanel.tsx`. | Advanced section; the Why panel now shows the chance a block happens, its range, how much data it rests on and the factors that move it. |

What was deliberately **not** changed: the decoder-based legality guarantee and the independent hard-rule validator; the GA + local search optimiser; the hierarchical duration model; the closed-loop evaluation design. The fuzzy rules were kept as an evaluation-only reference (`ai/evaluation/fuzzy_reference.py`) so the comparison stays reproducible from code.
