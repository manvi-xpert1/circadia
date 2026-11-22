# Phase 1: Codebase audit

The audit of the Circadia AI code (`backend/ai/`, about 1,700 statements) before any changes. It decided what was built in the later phases, and what was not.

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
| 1 | GA | The greedy decoder snaps tasks to the nearest legal gap in chromosome order. Small exact moves (shift 15 min into a better-fit slot, swap two blocks, re-seat a block to make room) are hard to reach through hints: a mutated hint often decodes to the same plan. | On 10 random 20-task problems the GA stopped after 25–120 generations (mean 73), and a local search started from its best plan still improved it every time (Phase 2). | Phase 2: local search |
| 2 | GA | No reference point for solution quality beyond a brute-force check on 5-task problems. "Near-optimal" was unmeasured at realistic sizes. | `test_ga_close_to_brute_force_on_small_problems` only covers n = 5. | Phase 3: CP-SAT |
| 3 | Durations | A category switches abruptly from the pooled estimate to its own data at exactly 3 outcomes, and its prior is the population default, not the user's own pace. | `DurationModel.for_category`. | Phase 4 |
| 4 | Durations | P80 ignores uncertainty in the mean itself, so with few outcomes it is too narrow. | The calibration study measured P80 coverage of 74% against a target of 80%. | Phase 4 |
| 5 | Probability | P(complete) is per block. Knock-on delays (a long block pushes the next one into a lecture or past the end of the day) are invisible to the planner and the user. | `TaskInfo.p_complete`. | Phase 5 |
| 6 | Replanning | Every Regenerate or What-if replans from scratch: a different seed or a small change can reshuffle the whole plan. | What-if test: an urgent task moved 11 of 12 blocks. | Phase 6 |
| 7 | Alternatives | Alternatives are filtered only by similarity; nothing tells the user whether one is simply worse than another. | `pipeline.similarity`. | Phase 7 (Pareto filter) |
| 8 | Evaluation | No effect sizes, no multiple-comparison correction, a single workload level, no ablations, no runtime figures. | `experiment.run_experiment`. | Phase 8 |
| 9 | Behaviour | In the closed-loop lab, the priority baseline finishes more tasks per day than the GA (about 5 vs 3.4) and misses fewer deadlines (6% vs 14%). | README "The evaluation, honestly". | Investigated with ablations (Phase 8) |

## Performance

- One decode costs about 0.05 ms and one fitness evaluation about 0.06 ms (25 tasks, 3 days). A GA run makes 2,000–3,000 of each, so most of its 0.5–1 s goes to Python overhead in the operators and the loop. Local search on decoded plans is cheap by comparison: a few thousand moves cost under 0.1 s.
- The suitability matrix is built with a Python double loop over (slot, task), about 0.1 s for 25 tasks × 3 days. That is acceptable and was left alone.

## Decisions

- **Build:** local-search refinement (memetic GA), a CP-SAT scheduler behind the same `GAResult` interface, a hierarchical duration model as a selectable version, Monte Carlo replay of finished plans, a stability term in the objective, a Pareto filter on alternatives, and an extended evaluation lab.
- **Keep:** the decoder-based legality guarantee and the independent validator, used for every optimiser.
- **Don't build:** NSGA-II (see `IMPROVEMENTS.md`, Phase 7), and Monte Carlo inside the GA fitness function (60 × 120 × N simulations per plan is too slow, and it would double-count the P80 padding the fitness already rewards).
- **Don't rename modules** to match a generic architecture list. The existing package layout (`fuzzy/`, `probability/`, `rules/`, `ga/`, `evaluation/`) already separates the concerns.

## Compatibility risks and how they were handled

| Risk | Handling |
|---|---|
| Explainer counterfactuals need a chromosome that decodes to the plan | `local_search.chromosome_for` builds one; a property test checks it round-trips. |
| A new duration model changes the design doc's worked examples | The original model stays available as `version="v1"`; the worked-example tests pin v1. |
| Existing `planner.db` files lack new preference columns | The existing startup migration adds them with defaults. |
| CP-SAT is non-deterministic with several workers and a wall-clock limit | Documented; a deterministic mode exists; the lab counts solver fallbacks instead of dropping them. |
| Wall-clock timing breaks the "same seed, same results" guarantee | Runtime is reported in a separate `runtime` section, outside the reproducible `summary`. |
