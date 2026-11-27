# Changelog

Dates are when the change was made. Measured results behind each decision are in `RESULTS.md`.

## 26 Nov 2026: evidence-driven probabilistic refactor

**Completion model replaces fuzzy suitability**
- New `ai/probability/completion.py`: Bayesian logistic regression (MAP by Newton's method, Laplace posterior, probit-approximated predictive) for the chance a planned block happens, from energy shortfall, focus, stress, block length and category. The fuzzy rules' knowledge is kept as a prior on the energy terms, which data can overturn.
- `ai/fuzzy/` removed from the planner. The time-of-day energy profile moved to `ai/probability/energy_profile.py`. The fuzzy rules survive only as an evaluation reference (`ai/evaluation/fuzzy_reference.py`, ablation `abl_fuzzy`).
- Each block's planning context is saved and stored with its outcome; blocks never reached are censored rather than counted as skipped.
- Explanations show the chance a block happens, its likely range, how many outcomes it is based on, and the factors that move it (in percentage points). Labels are now Very likely / Likely / Uncertain / Unlikely; plans saved with the older fuzzy labels display in the nearest band.
- `/api/models` reports the completion model's coefficients and uncertainty instead of per-category follow-through.

**Monte Carlo**
- Tiers: quick (30), standard (100, default), research (300), adaptive (30–300). Standard errors on every estimate; common random numbers per task; timing reported. Replayed durations truncated at 4× the estimate.
- Outcome-based plan selection (`ai/selection.py`): candidates replayed with shared draws and ranked by a preset-specific outcome score; switches only on a difference above two standard errors. Off by default after evaluation showed no benefit.

**Block length**
- `reserve_quantile` and `day_buffer` in the planning request. The app defaults to P65 (Settings → Advanced → Block length); the library default stays P80.

**Evaluation**
- New schedulers and policies in the lab: `abl_no_context`, `abl_fuzzy`, `hybrid_select`, `buf_p50`, `buf_p65`, `buf_p50_shared`, `buf_p65_shared`. The baseline formerly called "fuzzy" is now "Energy-aware greedy" (`energy`).
- `python -m ai.evaluation.compare`: paired comparison of any set of schedulers, saving full results as JSON.
- `ai/evaluation/completion_study.py`: forward-only predictive comparison of completion models (Brier, log loss, ECE, AUC, reliability, by history length).

**Interface**
- Settings: everyday options first; optimiser, risk simulation and block length under Advanced; plain-language style names ("Most tasks done", "Safer deadlines", "Lighter day", "Fewer changes when replanning").
- Alternatives: "Best for" labels and a plain sentence when another plan does at least as well on everything, instead of "Pareto-optimal".
- Risk tab: ± margins and a note when the plan was chosen among simulated candidates.
- Insights: "Are the predictions honest?" calibration table from your own outcomes.
- Settings → Your data: anonymous pilot export (categories, minutes, status, predicted chance and its context; no titles, notes or names; a random pilot id per export).

**Tests**
- Backend: 155 tests (95% coverage of `ai/`), including the completion model (cold start, sparse data, learning a context effect, overturning the prior, censoring, calibration on its own model family), Monte Carlo tiers and common random numbers, selection, the pilot export, and the fuzzy reference against the design doc's worked example.
- Frontend: 11 component tests. New browser end-to-end test (`e2e/`, Playwright) covering first run, demo data, Advanced settings, planning, the Why panel and Insights.

## 12 Nov 2026: optimiser, duration and evaluation upgrades

Hybrid GA + local search, CP-SAT baseline, hierarchical duration model, Monte Carlo replay, stability-aware replanning, Pareto filter on alternatives, expanded evaluation lab and CI. Details: `IMPROVEMENTS.md`.
