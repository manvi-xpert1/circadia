# Circadia: an Energy-Aware Life Planner

The name comes from *circadian rhythm*, the daily cycle of energy and alertness the planner schedules around.

A planner that places your tasks where your energy fits. Everything is implemented in this repository, with no external AI service:

- **Fuzzy logic** turns your 1–10 check-in into an expected capacity for every 15-minute slot, then scores how well each task fits each slot.
- **Bayesian duration learning** learns how long your tasks really take, per category, shrinking sparse categories toward your overall pace (hierarchical, empirical Bayes), and how likely a planned block is to happen.
- **Rule-based constraints** (hard rules H1–H9) make sure no plan ever clashes with a lecture, misses a deadline or breaks a dependency. An independent rule engine re-checks every plan from every optimiser.
- **A hybrid genetic algorithm** searches thousands of possible plans across several days, then a local search refines the best one. A **CP-SAT** constraint solver (Google OR-Tools) is available as a thorough mode and serves as an exact-solver baseline.
- **Monte Carlo replay** shows how a plan holds up when tasks run long or get skipped, including knock-on delays.
- **Stability-aware replanning** fits changes (an urgent task, lost time) around your existing plan instead of reshuffling it.

What changed in version 2.0 and why: [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md). Measured results: [docs/RESULTS.md](docs/RESULTS.md). The audit that started it: [docs/AUDIT.md](docs/AUDIT.md).

Every placement comes with a plain-language explanation built from the numbers the algorithms used. The full design is in the Stage One design doc.

Everything runs offline on your computer. Your data stays in one file: `backend/data/planner.db`.

## Run it (two terminals)

You need **Python 3.13** and **Node.js 18 or newer**. Python 3.15 is very new, and some packages (numpy, scipy) may not have Windows builds for it yet, so this project uses 3.13 through `py -3.13`.

**Terminal 1, backend** (first time only: the `venv` and `pip install` lines):

```
cd "C:\Users\xpert\circaidia\backend"
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2, frontend** (first time only: `npm install`):

```
cd "C:\Users\xpert\circaidia\frontend"
npm install
npm run dev
```

The CP-SAT solver (OR-Tools) is optional and lives in `requirements-solver.txt`: `pip install -r requirements-solver.txt`. OR-Tools has packages for Python 3.9–3.13 only. Without it, everything works except the Thorough optimiser (which then falls back to GA + local search) and the CP-SAT parts of the evaluation lab.

Open **http://localhost:5173** and create your account (name and password). The frontend forwards every `/api` request to the backend on port 8000. Nothing needs the internet after the first installs.

On later days you only need `.venv\Scripts\activate` and the `uvicorn` line in terminal 1, and `npm run dev` in terminal 2.

`start.bat`, `dev.bat`, `run_tests.bat` and `frontend\dist` are optional one-click shortcuts from the first build. Nothing depends on them, and you can delete them.

### First look

To try the planner, go to the Dashboard and click **Load demo week**. This adds a made-up student week: 13 tasks, lectures, 10 days of check-ins and 18 past outcomes. Every demo record is labelled "Demo", and **Settings → Delete demo data** removes all of it without touching your own records.

### Daily use

1. **Check-in**: move four sliders. This takes about 20 seconds; you can skip it.
2. **AI Schedule → Plan my days**: plans today plus the next 2 days by default.
3. Click any block to see why it is there. You can lock it, move it or remove it.
4. After a block, record **Done**, **Partly** or **Skipped** with the minutes it took. The planner learns from this.

### Forgot your password

In the `backend` folder, run `.venv\Scripts\python -m app.reset_password`. Your data is kept.

## What is built so far

| Area | Status |
| --- | --- |
| Login (single local account, Argon2 hash, 7-day session, lockout after 5 wrong tries) | Built |
| Tasks: add, edit, delete with undo, complete, filters, sorting, fixed tasks, dependencies, repeating tasks (every day, weekdays or chosen days) | Built |
| Busy times (lectures, unavailable time, repeating) | Built |
| Energy check-in with trends | Built |
| AI Schedule: multi-day plan, day and all-days views, energy ribbon, Why panel, lock / move / remove, alternatives, score breakdown, GA convergence chart, usefulness rating | Built |
| Outcome recording and learning (durations, follow-through, daily energy rhythm) | Built |
| Dashboard | Built |
| Settings: working hours, horizon, style, learned models, demo data, export, password | Built |
| Insights: completion, your estimates versus actual, planner learning curve, completion by energy fit and by hour, energy through the day, with a data-source filter | Built |
| What-if simulator: late start, urgent task, lost time, lower energy, a task taking longer, combined freely; before/after comparison with explanations; apply for real | Built |
| Evaluation lab: four schedulers plus a 1-day-horizon GA on synthetic users with hidden ground truth; confidence intervals, Wilcoxon tests, learning curve, saved runs | Built |
| **2.0:** hybrid GA (GA + local search) as the default optimiser; CP-SAT "Thorough" mode | Built |
| **2.0:** hierarchical Bayesian duration model with predictive (Student-t) P80 | Built |
| **2.0:** Monte Carlo "What could go wrong" tab; Pareto labels on alternatives | Built |
| **2.0:** stability-aware Regenerate and What-if, with a steady-vs-from-scratch comparison | Built |
| **2.0:** lab: CP-SAT, ablations, difficulty tiers, effect sizes, Holm correction, calibration / stability / solver studies, `python -m ai.evaluation.benchmark` | Built |

## Where things are

```
circaidia/
├── backend/
│   ├── ai/                the AI, with no web or database code inside
│   │   ├── fuzzy/         membership.py, engine.py (Mamdani inference), profile.py (time-of-day energy)
│   │   ├── probability/   duration_model.py (v1 conjugate normal, v2 hierarchical Bayes), followthrough.py
│   │   ├── rules/         hard_rules.py (H1–H9, predicate logic), soft_rules.py (A1–A8)
│   │   ├── ga/            decoder.py, fitness.py (+ stability term), operators.py, runner.py, local_search.py
│   │   ├── cpsat/         scheduler.py: time-indexed CP-SAT model (OR-Tools)
│   │   ├── baselines/     the three greedy comparison schedulers
│   │   ├── explain/       explanation templates
│   │   ├── evaluation/    simulator.py, experiment.py, calibration.py, studies.py, benchmark.py
│   │   ├── uncertainty.py Monte Carlo replay of a finished plan
│   │   ├── tradeoffs.py   Pareto filter over alternative plans
│   │   ├── whatif.py      scenario simulator (stability-aware)
│   │   ├── problem.py     builds the 15-minute grid and the suitability matrix
│   │   └── pipeline.py    plan(): the single entry point, optimiser choice
│   ├── app/               FastAPI routes, database models, login, demo data
│   ├── tests/             pytest: 130 tests, including the design doc's worked examples and property-based tests
│   └── data/planner.db    your data (created on first run)
├── frontend/
│   ├── src/               React + TypeScript + Tailwind source
│   └── dist/              an optional built copy (only used by start.bat)
├── docs/                  AUDIT.md, IMPROVEMENTS.md, RESULTS.md (+ results.json)
└── .github/workflows/     CI: backend tests + coverage, benchmark smoke run, frontend tests + build
```

## Tests

In the backend folder, with the venv active:

```
pip install -r requirements-dev.txt
pytest
```

Current results:

- 130 backend tests pass, with 97% line coverage of the AI code, plus 9 frontend tests.
- Every optimiser (GA, hybrid, CP-SAT) is checked against the independent hard-rule engine, including Hypothesis property tests that start local search from random chromosomes.
- The worked examples from the design doc are reproduced exactly: capacity 7.04 at 10:00 vs 6.28 at 14:00, report fit 0.89 vs 0.67, and a P80 block of 89 min (cold start) vs 91 min (learned) for a 60-minute Study estimate.
- A randomised (Hypothesis) test feeds the decoder random chromosomes and checks the independent rule engine never finds a violation.
- The GA scores at least as well as every baseline on random problems, and is within 0.02 of brute force on 5-task problems. The hybrid scores at least as well as the GA on every test problem.
- A 25-task, 3-day problem plans all three styles, with Monte Carlo replay, in about 2–3 s.

To regenerate every number in `docs/RESULTS.md` (tens of minutes; `--quick` for a smoke run):

```
python -m ai.evaluation.benchmark --out ..\docs
```

Frontend tests: `npm test` in the `frontend` folder (needs Node.js).

## Notes on this build (changes from the design doc)

- **Font:** IBM Plex Sans instead of Inter + Fraunces. It reads more distinctly and has clear tabular figures for times. It is bundled locally, so it works offline.
- **Database tables:** created directly by SQLAlchemy rather than Alembic migrations, because it is simpler for one local user. Learned model values are computed from the outcome records each time rather than cached in a `model_states` table.
- **Energy fit:** averaged over all the slots a block covers, not only its start slot, so a block that runs into the post-lunch dip is scored honestly.
- **Alternatives:** the best plan under each of the other two styles (Deadline-first, Gentle). An alternative is hidden when it places 70% or more of tasks the same way as the main plan.
- **Plan size:** blocks are reserved in 15-minute steps, so the gap after a block works as a short natural break.

## Version 2.0 results in brief

From `docs/RESULTS.md` (synthetic users, 12 users × 7 days per workload, seed 2026; full tables with confidence intervals there):

- **Solver quality.** On 20–40-task problems the hybrid GA + local search found the best plan of any optimiser on 14 of 15 problems, in about 1 s. The plain GA was 2–3% behind. CP-SAT proved optimality on all five 10-task problems but, under a 10 s limit on 2 CPU threads, fell 9% behind at 30–40 tasks. Every plan from every optimiser passed the independent hard-rule check.
- **Real outcomes.** The hybrid's better fitness did not translate into measurably better outcomes for the simulated users: against the plain GA, every paired difference was small and non-significant. Better optimisation of the planner's objective is not the same as a better day.
- **What actually limits task completion is the P80 block length.** Removing learned durations (planning with the user's own estimate) finished about 1 more task per day (4.33 vs 3.38, p = 0.004 after Holm correction). It also cut deadline violations from 14% to 6% (not significant after correction), at the cost of more overruns into lectures. This explains the school version's "priority finishes more tasks" result: reserving P80 time protects against overruns, but the simulated users don't reuse the padding.
- **Duration model v2** is better calibrated: P80 covers 79.1% of real durations against v1's 73.9% (target 80%), with lower median error. But its wider blocks finished slightly fewer tasks in the closed loop (3.38 vs 3.61 per day, p = 0.039). The model is more accurate; the decision to reserve P80 is what costs tasks.
- **Stability-aware replanning** cut the blocks changed by a disruption from 6.2 to 1.5 (p < 0.001) at 50% stability, for a 1% drop in plan quality. Urgent-task placement was unchanged up to 50% and fell at 100% (55.6% → 44.4%).

These are trade-offs to discuss, not results to hide. The natural next experiment is the block-length quantile (P50 / P65 / P80) as a setting.

## The evaluation, honestly

The Evaluation lab runs on **synthetic users**, labelled as such everywhere. Each user has hidden habits the planner never sees: true overruns per category, a morning or evening rhythm, and a follow-through rate. Plans are graded by a simple "true fit" formula that is deliberately not the planner's fuzzy model. Assumptions, all shown in the lab:

- The user plans at 08:30 and again at 14:00.
- A free user starts the next block up to 30 minutes early.
- An overrun into a lecture pauses until the lecture ends.
- Work stops at 22:00.

What the default run shows (10 users × 7 days, seed 2026):

- Among the four main schedulers, the GA had the fewest overloaded days: about 6% of days planned above 85% load, against 13% for fuzzy, 16% for priority and 40% for duration-aware.
- The GA almost never overran past 22:00 (about 0.1 minute a day). The priority scheduler overran by about 11 minutes a day.
- The priority scheduler packs the day using raw estimates. It finishes more tasks per day (about 5 against 3.4 for the GA) and misses fewer deadlines (6% against 14%), but it runs into commitments more often (2.5 times a day against 1.6).
- Planning 3 days ahead finished fewer tasks per day than planning 1 day ahead (3.4 against 3.9; p = 0.004). The difference in deadline violations (14% against 17%) was not significant (p = 0.56).

On 11 Nov the day-balance penalty (soft rule A8) was changed so that only a day above 60% load counts as too busy. Before, light work was scattered across days even when today was nearly empty. On the busy simulated weeks this changed little: tasks per day went from 3.43 to 3.36, and deadline violations went from 11.8% to 14.4%. On light days it keeps the work on today.

These are trade-offs to discuss in your report, not results to hide. Run the lab yourself to get the exact numbers for your seed.

## Repeating tasks

Choose **Repeats** in the task form: Never, Every day, Weekdays, or Pick days. A repeating task is a template that is never planned itself. For each matching day inside your planning horizon, Circadia creates a normal copy for that day. Each copy:

- is due by the end of its day, or by the "due by" time you set;
- can't start before its own day (hard rule H9, added for this);
- is planned, completed and learned from like any other task.

Copies from earlier days that were never done are marked **Missed**. Editing the template rebuilds its untouched future copies. Deleting the template stops the repeats but keeps finished history.

Existing databases are upgraded automatically on start: missing columns are added and nothing is deleted.
