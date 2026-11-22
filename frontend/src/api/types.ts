export type Priority = 1 | 2 | 3 | 4;
export const PRIORITY_NAMES: Record<number, string> = { 1: "Low", 2: "Medium", 3: "High", 4: "Critical" };

export interface User { id: number; username: string; display_name: string }
export interface AuthStatus { has_account: boolean; logged_in: boolean; user: User | null }

export interface TaskBody {
  title: string;
  category: string;
  priority: number;
  deadline: string | null;
  est_minutes: number;
  mental_difficulty: number;
  physical_difficulty: number;
  mental_energy_req: number;
  physical_energy_req: number;
  is_fixed: boolean;
  fixed_start: string | null;
  fixed_end: string | null;
  depends_on_id: number | null;
  notes: string;
  recur_days: string; // weekdays it repeats on, Monday = 0, e.g. "0,2,4"; "" = does not repeat
  recur_until: string | null;
}
export interface Task extends TaskBody {
  id: number;
  parent_id: number | null; // set on one day's copy of a repeating task
  occurrence_date: string | null;
  status: "pending" | "done" | "missed";
  minutes_done: number;
  completed_at: string | null;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface Commitment { id: number; label: string; start: string; end: string; kind: "fixed" | "unavailable"; source: string }

export interface CheckIn { id: number; mental: number; physical: number; focus: number; stress: number; note: string; recorded_at: string; source: string }

export interface Preferences {
  day_start: string; day_end: string; break_minutes: number; max_focus_block: number;
  no_work_after: string; ga_preset: "balanced" | "deadline" | "gentle"; horizon_days: number;
  optimizer: Optimizer; replan_stability: number;
}

export type Optimizer = "ga" | "hybrid" | "cpsat";

export interface Robustness {
  runs: number;
  expected_completed: number; completed_p10: number; completed_p90: number; completed_sd: number; planned: number;
  p_all_important_done: number | null; important_planned: number; important_unplanned: number;
  p_all_deadlines_met: number | null; deadline_safety: number | null;
  expected_unfinished_minutes: number; p_overrun_any_day: number; p_overrun_by_day: number[];
  expected_unused_minutes: number; note: string;
}
export interface StabilityReport { previous_blocks: number; kept: number; moved: number; removed: number; added: number; displacement_minutes: number }
export interface Tradeoffs {
  objectives: Record<string, number>; pareto_optimal: boolean; dominated_by: string[]; best_at: string[]; gives_up_vs_main: string[];
}

export interface FiredRule { id: string; strength: number; text: string }

export interface Block {
  block_id: number;
  task_id: number;
  title: string;
  category: string;
  kind: "ai" | "fixed-task" | "locked";
  start: string;
  end: string;
  day: number;
  locked: boolean;
  task_status?: string;
  outcome: { status: string; actual_minutes: number | null } | null;
  // explanation (ai blocks; locked blocks carry fewer fields)
  priority?: number;
  priority_name?: string;
  planned_minutes?: number;
  est_minutes?: number;
  fit?: number;
  fit_label?: string;
  capacity?: number;
  mental_demand?: number;
  physical_demand?: number;
  slot_mental?: number;
  slot_physical?: number;
  energy_source?: string;
  fired_rules?: FiredRule[];
  duration?: { ratio: number; spread: number; n: number; source: string; text: string; p80: number };
  p_complete?: number;
  p_on_time?: number | null;
  deadline?: string | null;
  rules_applied?: string[];
  warnings?: string[];
  next_best?: { start: string; label: string; fit: number } | null;
  verdict?: string;
}

export interface Unscheduled { task_id: number; title: string; category: string; priority: number; deadline: string | null; code: string; reason: string }

export interface PlanVersion {
  version_id: number;
  preset: string;
  label: string;
  is_active: boolean;
  is_main: boolean;
  fitness: number;
  components: Record<string, number>;
  weights: Record<string, number>;
  day_load: { day: number; planned_minutes: number; load: number; heavy: boolean }[];
  convergence: { gen: number; best: number; mean: number }[];
  generations: number;
  seconds: number;
  blocks: Block[];
  unscheduled: Unscheduled[];
  optimizer?: Optimizer | null;
  optimizer_label?: string | null;
  optimizer_details?: Record<string, unknown> | null;
  stability?: StabilityReport | null;
  robustness?: Robustness | null;
  tradeoffs?: Tradeoffs | null;
}

export interface DayInfo {
  day: number;
  date: string;
  free_minutes: number;
  energy_source: "check-in" | "forecast";
  energy: { mental: number; physical: number; focus: number; stress: number };
  stress_cap: boolean;
  capacity: number[];
}

export interface PlanRun {
  run_id: string;
  created_at: string;
  seed: number;
  active_version_id: number;
  meta: {
    now: string; horizon_days: number; day_start: string; day_end: string; slot_minutes: number;
    mode: "cold" | "personalized"; outcomes_used: number; checkins_used: number; warnings: string[]; seconds: number;
  };
  days: DayInfo[];
  commitments: { label: string; kind: string; start: string; end: string }[];
  plans: PlanVersion[];
}

export interface Counts { [table: string]: Record<string, number> }

export interface ModelsInfo {
  mode: "cold" | "personalized";
  durations: { categories: Record<string, { ratio: number; spread: number; n: number; own_n: number; source: string }>; pooled: { ratio: number; spread: number; n: number; source: string }; version?: "v1" | "v2" };
  followthrough: Record<string, { done: number; skipped: number; p: number }>;
  profile: { bands: string[]; mental: number[]; physical: number[]; counts: number[]; learned: boolean };
  finished_with_minutes: number;
  records: Counts;
}

/* ---- Insights ---- */
export interface Insights {
  source: string;
  outcomes: { n: number; done: number; partial: number; skipped: number; completion_rate: number | null };
  estimate_error_min: number | null;
  planner_error_min: number | null;
  categories: { category: string; n: number; estimate: number; actual: number; overrun_pct: number }[];
  status_by_category: { category: string; done: number; partial: number; skipped: number }[];
  accuracy: { i: number; at: string; estimate_error_pct: number; planner_error_pct: number; estimate_rolling: number; planner_rolling: number }[];
  by_fit: { label: string; n: number; done_rate: number }[];
  by_hour: { hour: number; n: number; done_rate: number }[];
  deadlines: { on_time: number; late: number; overdue_open: number; upcoming: number };
  energy_by_time: { band: string; n: number; mental: number; physical: number; focus: number; stress: number }[];
  checkins: number;
  plans_generated: number;
  ratings: { n: number; mean: number | null };
}

/* ---- What-if ---- */
export interface Scenario {
  late_start_minutes?: number;
  urgent_task?: { title: string; est_minutes: number; deadline_hours: number; priority: number; mental: number; physical: number; category: string };
  lose_time?: { day: number; start: string; end: string; label?: string };
  energy_delta?: number;
  extend_task?: { task_id: number; extra_minutes: number };
  horizon_days?: number;
  stability?: number;
}
export interface LiteBlock { task_id: number; title: string; category: string; start: string; end: string; day: number; fit: number; fit_label: string; planned_minutes: number; priority: number }
export interface LitePlan {
  days: { day: number; date: string; free_minutes: number; energy_source: string }[];
  blocks: LiteBlock[];
  fixed: { task_id: number; title: string; start: string; end: string; day: number; kind: string }[];
  commitments: { label: string; kind: string; start: string; end: string }[];
  unscheduled: Unscheduled[];
  summary: {
    tasks_planned: number; not_planned: number; avg_fit: number; deadline_safety: number | null; busiest_day_load: number;
    today_minutes: number; fitness: number; expected_completed?: number | null; deadline_safety_mc?: number | null;
    stability?: StabilityReport | null;
  };
}
export interface ReplanChanges { moved: number; added: number; dropped: number; unchanged: number }
export interface WhatIfResult {
  scenario: Scenario;
  seed: number;
  before: LitePlan;
  after: LitePlan;
  diff: {
    moved: { task_id: number; title: string; from: string; to: string; from_day: number; to_day: number }[];
    added: { task_id: number; title: string; to: string; to_day: number }[];
    dropped: { task_id: number; title: string; from: string; reason: string }[];
    unchanged: number;
  };
  explanation: string[];
  stability?: number;
  free_replan?: { summary: LitePlan["summary"]; changes: ReplanChanges };
  stable_replan?: { summary: LitePlan["summary"]; changes: ReplanChanges };
}

/* ---- Evaluation ---- */
export interface MetricStat { mean: number; ci: [number, number] }
export interface Comparison { diff: number; ci: [number, number]; p: number | null; p_holm: number | null; effect: number | null }
export interface EvalConfigIn {
  users: number; days: number; horizon: number; seed: number; compare_horizon: boolean;
  difficulty?: "easy" | "moderate" | "tight"; include_cpsat?: boolean; ablations?: boolean; cpsat_seconds?: number;
  calibration?: boolean; stability?: boolean; solver_benchmark?: boolean;
}
export interface CalibrationRow { n: number; coverage: number; pinball80: number; log_score: number; mae: number; p80_padding: number }
export interface Studies {
  calibration?: { config: Record<string, number>; versions: Record<string, Record<string, CalibrationRow>>;
    pinball_difference?: { mean: number; ci: [number, number]; meaning: string } };
  stability?: { cases: number; previous_blocks_mean: number; note: string;
    table: Record<string, Record<string, MetricStat> & { urgent_placed_pct: number | null; vs_free?: Record<string, { diff: number; p: number | null; effect: number | null }> }> };
  solver_benchmark?: { optimizers: string[]; note: string; config: { instances: number; cpu_count: number };
    table: Record<string, Record<string, { fitness: number; gap_pct: number; best_count: number; seconds: number; violations: number; planned: number; status?: Record<string, number>; fallbacks?: number }>> };
}
export interface EvalResults {
  config: EvalConfigIn;
  schedulers: Record<string, string>;
  metrics: Record<string, { label: string; unit: string; higher_is_better: boolean }>;
  summary: Record<string, Record<string, MetricStat>>;
  wilcoxon_ga_vs: Record<string, Record<string, number | null>>;
  per_user: Record<string, Record<string, number>[]>;
  learning_curve: Record<string, (number | null)[]>;
  seconds: number;
  data: string;
  reference?: string;
  runtime?: Record<string, Record<string, MetricStat>>;
  comparisons?: Record<string, Record<string, Comparison>>;
  versions?: Record<string, unknown>;
  studies?: Studies;
}
export interface EvalRun {
  id: number;
  status: "running" | "done" | "failed";
  progress: number;
  config: EvalConfigIn;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  results: EvalResults | null;
  usefulness: { n: number; mean: number | null };
}
export interface EvalRunSummary { id: number; status: string; progress: number; config: EvalRun["config"]; created_at: string; seconds: number | null }
