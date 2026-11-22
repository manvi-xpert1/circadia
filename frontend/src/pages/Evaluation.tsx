import clsx from "clsx";
import { FlaskConical, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { EvalConfigIn, EvalResults, EvalRun, EvalRunSummary, Studies } from "../api/types";
import { Badge, Button, Card, EmptyState, ErrorState, InlineError, PageHeader, SectionTitle, Skeleton } from "../components/ui";

const TEAL = "#1F6F6B";
const GREY = "#A3AAA4";
const AXIS = { fontSize: 11, fill: "#5B6660" };
const TIP = { borderRadius: 10, border: "1px solid #E4DCCB", background: "rgba(255,253,248,.96)", fontSize: 13 };
const MAIN_ALL = ["priority", "duration", "fuzzy", "ga", "hybrid", "cpsat"];
const SHORT: Record<string, string> = {
  priority: "Priority", duration: "Duration", fuzzy: "Fuzzy", ga: "GA", hybrid: "GA+LS", cpsat: "CP-SAT", ga_1day: "GA 1-day",
  abl_no_fuzzy: "No fuzzy", abl_no_prob: "No P80", abl_v1_durations: "Old durations",
};
const KEY = ["completed_per_day", "deadline_violation_rate", "energy_fit", "overloaded_days", "overload_minutes"];
const pfmt = (p: number | null | undefined) => (p == null ? "–" : p < 0.001 ? "<0.001" : p.toFixed(3));

export function EvaluationPage() {
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["eval-runs"], queryFn: () => api<EvalRunSummary[]>("/api/evaluation/runs") });
  const [selected, setSelected] = useState<number | null>(null);
  const [cfg, setCfg] = useState<EvalConfigIn>({
    users: 10, days: 7, horizon: 3, seed: 2026, compare_horizon: true, difficulty: "moderate",
    include_cpsat: false, ablations: false, calibration: true, stability: false, solver_benchmark: false,
  });
  const current = selected ?? runs.data?.[0]?.id ?? null;
  const run = useQuery({
    queryKey: ["eval-run", current],
    queryFn: () => api<EvalRun>(`/api/evaluation/runs/${current}`),
    enabled: current != null,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 1000 : false),
  });
  useEffect(() => {
    if (run.data?.status && run.data.status !== "running") qc.invalidateQueries({ queryKey: ["eval-runs"] });
  }, [run.data?.status, qc]);
  const start = useMutation({
    mutationFn: () => api<EvalRun>("/api/evaluation/runs", { method: "POST", body: cfg }),
    onSuccess: (r) => { setSelected(r.id); qc.invalidateQueries({ queryKey: ["eval-runs"] }); },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/api/evaluation/runs/${id}`, { method: "DELETE" }),
    onSuccess: () => { setSelected(null); qc.invalidateQueries({ queryKey: ["eval-runs"] }); },
  });
  const perUserDay = 0.75 + (cfg.compare_horizon ? 0.15 : 0) + (cfg.ablations ? 0.6 : 0) + (cfg.include_cpsat ? 4.2 : 0);
  const estimate = Math.round(cfg.users * cfg.days * perUserDay * (cfg.difficulty === "tight" ? 1.5 : cfg.difficulty === "easy" ? 0.7 : 1)
    + (cfg.calibration ? 3 : 0) + (cfg.stability ? 90 : 0) + (cfg.solver_benchmark ? 240 : 0));
  const busy = run.data?.status === "running" || start.isPending;

  return (
    <>
      <PageHeader title="Evaluation lab" sub="Schedulers compared on synthetic users whose true habits the planner never sees. All numbers are computed when you run it." />
      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card>
            <SectionTitle>New experiment</SectionTitle>
            <div className="grid grid-cols-2 gap-3">
              <label><span className="label">Synthetic users</span><input type="number" min={2} max={40} className="field num" value={cfg.users} onChange={(e) => setCfg({ ...cfg, users: Number(e.target.value) })} /></label>
              <label><span className="label">Days each</span><input type="number" min={2} max={21} className="field num" value={cfg.days} onChange={(e) => setCfg({ ...cfg, days: Number(e.target.value) })} /></label>
              <label><span className="label">Plan ahead (days)</span><input type="number" min={1} max={5} className="field num" value={cfg.horizon} onChange={(e) => setCfg({ ...cfg, horizon: Number(e.target.value) })} /></label>
              <label><span className="label">Seed</span><input type="number" min={0} className="field num" value={cfg.seed} onChange={(e) => setCfg({ ...cfg, seed: Number(e.target.value) })} /></label>
            </div>
            <label className="mt-3 block"><span className="label">Workload</span>
              <select className="field" value={cfg.difficulty} onChange={(e) => setCfg({ ...cfg, difficulty: e.target.value as EvalConfigIn["difficulty"] })}>
                <option value="easy">Easy: 2–4 new tasks a day</option>
                <option value="moderate">Moderate: 4–7 new tasks a day</option>
                <option value="tight">Tight: 7–10 new tasks a day, more lectures</option>
              </select>
            </label>
            {([
              ["compare_horizon", "Also run the GA with a 1-day horizon"],
              ["include_cpsat", "Include the CP-SAT solver (2 s per plan)"],
              ["ablations", "Ablations: remove one component at a time"],
              ["calibration", "Duration model calibration study"],
              ["stability", "Replanning stability study"],
              ["solver_benchmark", "Solver benchmark by problem size (slow)"],
            ] as [keyof EvalConfigIn, string][]).map(([k, label]) => (
              <label key={k} className="mt-2 flex items-center gap-2 text-[13.5px]">
                <input type="checkbox" className="h-4 w-4 accent-teal" checked={!!cfg[k]} onChange={(e) => setCfg({ ...cfg, [k]: e.target.checked })} />
                {label}
              </label>
            ))}
            <InlineError error={start.error} />
            <Button variant="primary" className="mt-4 w-full" loading={start.isPending} disabled={busy} onClick={() => start.mutate()}>
              <FlaskConical size={16} aria-hidden /> Run experiment
            </Button>
            <p className="hint mt-2">Takes about {estimate < 60 ? `${estimate} s` : `${Math.round(estimate / 60)} min`} on a typical laptop. The same seed always gives the same results.</p>
          </Card>
          <Card className="p-4">
            <h3 className="mb-2 text-[14px] font-semibold">Saved runs</h3>
            {runs.isLoading ? <Skeleton className="h-20" /> : !runs.data?.length ? <p className="text-[13px] text-muted">None yet.</p> : (
              <ul className="space-y-1">
                {runs.data.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => setSelected(r.id)} className={clsx("flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-[13px]", current === r.id ? "bg-teal-tint/60" : "hover:bg-beige")}>
                      <span>#{r.id} · {r.config.users} users × {r.config.days} days</span>
                      <span className="text-muted">{r.status === "done" ? new Date(r.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : r.status}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="min-w-0">
          {current == null ? (
            <EmptyState title="No experiments yet" body="Run one to compare the conventional priority scheduler, the duration-aware and energy-aware greedy schedulers, the genetic algorithm and the GA with local search. Start with the defaults." />
          ) : run.isLoading ? <Skeleton className="h-96" /> : run.error ? <ErrorState error={run.error} onRetry={() => run.refetch()} /> : run.data?.status === "running" ? (
            <Card>
              <p className="font-medium">Running experiment #{run.data.id}</p>
              <div className="mt-3 h-2 rounded-full bg-beige"><div className="h-full rounded-full bg-teal transition-all" style={{ width: `${Math.max(3, run.data.progress * 100)}%` }} /></div>
              <p className="num mt-2 text-[13px] text-muted">{Math.round(run.data.progress * 100)}% done</p>
            </Card>
          ) : run.data?.status === "failed" ? (
            <ErrorState error={{ message: "The experiment failed. Details below.", code: "EVAL_FAILED" }} />
          ) : run.data?.results ? (
            <Results run={run.data} res={run.data.results} onDelete={() => remove.mutate(run.data!.id)} />
          ) : null}
          {run.data?.error && <pre className="mt-3 overflow-x-auto rounded-lg bg-beige p-3 text-[12px]">{run.data.error}</pre>}
        </div>
      </div>
    </>
  );
}

function fmt(v: number, unit: string) {
  if (unit === "0-1") return v.toFixed(2);
  if (unit.startsWith("%")) return `${v.toFixed(1)}%`;
  return v.toFixed(unit === "total" ? 0 : 1);
}

function Results({ run, res, onDelete }: { run: EvalRun; res: EvalResults; onDelete: () => void }) {
  const names = Object.keys(res.schedulers);
  const MAIN = MAIN_ALL.filter((n) => res.summary[n]);
  const ref = res.reference && res.summary[res.reference] ? res.reference : "ga";
  const best = (m: string) => {
    const hb = res.metrics[m].higher_is_better;
    const vals = MAIN.filter((n) => res.summary[n]).map((n) => res.summary[n][m].mean);
    return hb ? Math.max(...vals) : Math.min(...vals);
  };
  const p = (base: string, m: string) => (res.comparisons ? res.comparisons[base]?.[m]?.p_holm : res.wilcoxon_ga_vs[base]?.[m]);
  const keyCharts = ["completed_per_day", "deadline_violation_rate", "energy_fit", "overloaded_days"];
  const curve = res.learning_curve.priority.map((_, d) => ({ day: d + 1, estimate: res.learning_curve.priority[d], model: res.learning_curve[ref][d] }));
  const ablations = names.filter((n) => n.startsWith("abl_"));
  const hasHorizon = !!res.summary.ga_1day;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="brown">Synthetic data</Badge>
        <span className="text-[13px] text-muted">
          Run #{run.id}: {res.config.users} users × {res.config.days} days, {res.config.horizon}-day horizon, {res.config.difficulty ?? "moderate"} workload, seed {res.config.seed}, computed in {res.seconds} s
        </span>
        <button type="button" onClick={onDelete} className="ml-auto rounded-md p-1.5 text-muted hover:bg-danger-tint hover:text-danger" aria-label="Delete this run"><Trash2 size={15} /></button>
      </div>

      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-[13.5px]">
          <caption className="px-4 pt-4 text-left text-[15px] font-semibold text-ink">Results per scheduler</caption>
          <thead className="text-left text-[12.5px] text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Measure</th>
              {names.map((n) => <th key={n} className={clsx("px-3 font-medium", n === ref && "text-teal")}>{res.schedulers[n]}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {Object.entries(res.metrics).map(([m, meta]) => (
              <tr key={m}>
                <td className="px-4 py-2.5">
                  <div>{meta.label}</div>
                  <div className="text-[12px] text-muted">{meta.unit}, {meta.higher_is_better ? "higher" : "lower"} is better</div>
                </td>
                {names.map((n) => {
                  const s = res.summary[n][m];
                  const isBest = MAIN.includes(n) && Math.abs(s.mean - best(m)) < 1e-9;
                  const pv = n !== ref ? p(n, m) : undefined;
                  return (
                    <td key={n} className="px-3 py-2.5 align-top">
                      <div className={clsx("num", isBest && "font-semibold")}>{fmt(s.mean, meta.unit)}{isBest && <span className="sr-only"> (best)</span>}</div>
                      <div className="num text-[11.5px] text-muted">{fmt(s.ci[0], meta.unit)} to {fmt(s.ci[1], meta.unit)}</div>
                      {pv !== undefined && <div className={clsx("num text-[11.5px]", pv != null && pv < 0.05 ? "text-ink" : "text-muted")}>{pv == null ? `same as ${SHORT[ref]}` : `p = ${pfmt(pv)} vs ${SHORT[ref]}`}</div>}
                    </td>
                  );
                })}
              </tr>
            ))}
            {res.runtime && (
              <tr>
                <td className="px-4 py-2.5"><div>Planning time</div><div className="text-[12px] text-muted">s per plan, on this computer; varies between runs</div></td>
                {names.map((n) => <td key={n} className="num px-3 py-2.5 align-top">{res.runtime![n]?.plan_seconds.mean.toFixed(2) ?? "–"}</td>)}
              </tr>
            )}
          </tbody>
        </table>
        <p className="px-4 pb-4 pt-2 text-[12.5px] text-muted">
          Each cell: mean over synthetic users, then the 95% bootstrap confidence interval. Bold marks the best of the main schedulers (not the ablations).
          p-values come from a Wilcoxon signed-rank test pairing each user's result under {res.schedulers[ref]} with the same user under that scheduler
          {res.comparisons ? ", Holm-adjusted for the number of schedulers compared" : ""}; below 0.05 is usually read as a real difference.
        </p>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        {keyCharts.map((m) => {
          const meta = res.metrics[m];
          const data = MAIN.map((n) => ({ name: SHORT[n], key: n, mean: res.summary[n][m].mean, err: [res.summary[n][m].mean - res.summary[n][m].ci[0], res.summary[n][m].ci[1] - res.summary[n][m].mean] }));
          return (
            <Card key={m} className="p-4">
              <h3 className="text-[14px] font-medium">{meta.label}</h3>
              <p className="text-[12px] text-muted">{meta.unit}, {meta.higher_is_better ? "higher" : "lower"} is better. Bars show the mean, whiskers the 95% interval.</p>
              <div className="mt-2 h-44">
                <ResponsiveContainer>
                  <BarChart data={data} margin={{ top: 18, right: 6, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke="#EFE8DA" vertical={false} />
                    <XAxis dataKey="name" tick={AXIS} axisLine={false} tickLine={false} />
                    <YAxis tick={AXIS} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={TIP} formatter={(v) => [fmt(Number(v), meta.unit), meta.label]} />
                    <Bar dataKey="mean" radius={[4, 4, 0, 0]} maxBarSize={44} isAnimationActive={false}>
                      {data.map((d) => <Cell key={d.key} fill={d.key === ref ? TEAL : GREY} />)}
                      <ErrorBar dataKey="err" width={6} stroke="#1F2A26" strokeWidth={1} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <SectionTitle>Does learning reduce duration error?</SectionTitle>
          <p className="mb-2 text-[13px] text-muted">Average error per finished task, by simulated day. The priority scheduler uses the user's raw estimate; the GA uses the learned model, which starts from defaults on day 1.</p>
          <div className="h-52">
            <ResponsiveContainer>
              <LineChart data={curve} margin={{ top: 6, right: 12, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="#EFE8DA" vertical={false} />
                <XAxis dataKey="day" tick={AXIS} axisLine={false} tickLine={false} label={{ value: "Day", position: "insideBottomRight", fontSize: 11, fill: "#5B6660" }} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} unit=" min" width={60} />
                <Tooltip contentStyle={TIP} labelFormatter={(d) => `Day ${d}`} formatter={(v, n) => [v == null ? "n/a" : `${v} min`, n]} />
                <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
                <Line name="User's own estimate" dataKey="estimate" stroke="#8C948F" strokeWidth={2} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />
                <Line name={`Learned model (${SHORT[ref]})`} dataKey="model" stroke={TEAL} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionTitle>Reading these results</SectionTitle>
          <ul className="space-y-2 text-[13.5px] leading-relaxed">
            <li>Each step of the ladder adds one idea: realistic durations (Duration), then energy matching (Fuzzy), then global search with every goal weighed together (GA), then local refinement of the GA's best plan (GA+LS){res.summary.cpsat ? ", with an exact solver as a yardstick (CP-SAT)" : ""}.</li>
            {hasHorizon && (
              <li>
                Planning 3 days ahead versus 1: deadline violations {fmt(res.summary.ga.deadline_violation_rate.mean, "%")} vs {fmt(res.summary.ga_1day.deadline_violation_rate.mean, "%")},
                tasks completed per day {res.summary.ga.completed_per_day.mean.toFixed(2)} vs {res.summary.ga_1day.completed_per_day.mean.toFixed(2)}.
              </li>
            )}
            <li>
              Real usefulness ratings cannot be simulated. From your own rated plans: {run.usefulness.n ? `${run.usefulness.mean} / 5 over ${run.usefulness.n} rating${run.usefulness.n === 1 ? "" : "s"}` : "no ratings yet"} (GA plans only).
            </li>
          </ul>
        </Card>
      </div>

      {res.comparisons && <Comparisons res={res} ref_={ref} names={names.filter((n) => n !== ref && !n.startsWith("abl_"))} title={`Effect sizes: ${res.schedulers[ref]} against each scheduler`} />}
      {ablations.length > 0 && res.comparisons && (
        <Comparisons res={res} ref_={ref} names={ablations} title="Ablations: what each component contributes"
          note="Each row removes one component from the full system. A positive difference in a higher-is-better measure means the full system is better than the version without that component." />
      )}
      {res.studies && <StudiesView studies={res.studies} />}

      <Card>
        <SectionTitle>Method, assumptions and limits</SectionTitle>
        <div className="grid gap-6 text-[13.5px] leading-relaxed md:grid-cols-2">
          <div>
            <h3 className="mb-1 font-medium">Procedure</h3>
            <ul className="list-disc space-y-1 pl-5">
              <li>Every synthetic user gets the same tasks, lectures and morning check-ins under every scheduler (paired design).</li>
              <li>Each day the user plans at 08:30 and again at 14:00, then works through today's blocks. Outcomes feed the learning models.</li>
              <li>Unfinished work carries over; a task still open after its deadline counts as a violation.</li>
              <li>The GA runs with a lighter setting here (population 40, 60 generations) so a run takes about a minute. Local search gets 3,000 evaluations, budgeted by count rather than time so runs repeat exactly.</li>
              <li>CP-SAT is limited to {res.config.cpsat_seconds ?? 2} s per plan. A plan where it found no solution in time is counted under solver fallbacks, never dropped.</li>
            </ul>
          </div>
          <div>
            <h3 className="mb-1 font-medium">Hidden truth and assumptions</h3>
            <ul className="list-disc space-y-1 pl-5">
              <li>True overrun per category between 0.9× and 1.6×; a morning or evening chronotype; follow-through 82–95%.</li>
              <li>True fit is a simple formula on energy shortfall, not the planner's fuzzy rules, so the planner is not graded by its own model.</li>
              <li>A free user starts the next block up to 30 minutes early. Overruns into a lecture pause until it ends. Work past 22:00 stops.</li>
              <li>These are modelling choices. Results show behaviour under these assumptions, not proof of real-world benefit.</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
}

export function Comparisons({ res, ref_, names, title, note }: { res: EvalResults; ref_: string; names: string[]; title: string; note?: string }) {
  const metrics = KEY.filter((m) => res.metrics[m]);
  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full min-w-[720px] text-[13px]">
        <caption className="px-4 pt-4 text-left text-[15px] font-semibold text-ink">{title}</caption>
        <thead className="text-left text-[12px] text-muted">
          <tr><th className="px-4 py-2 font-medium">Compared with</th>{metrics.map((m) => <th key={m} className="px-3 font-medium">{res.metrics[m].label}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-line">
          {names.map((n) => (
            <tr key={n}>
              <td className="px-4 py-2">{res.schedulers[n]}</td>
              {metrics.map((m) => {
                const c = res.comparisons![n]?.[m];
                if (!c) return <td key={m} className="px-3">–</td>;
                const sig = c.p_holm != null && c.p_holm < 0.05;
                return (
                  <td key={m} className="px-3 py-2 align-top">
                    <div className={clsx("num", sig && "font-semibold")}>{c.diff > 0 ? "+" : ""}{c.diff.toFixed(2)}</div>
                    <div className="num text-[11px] text-muted">[{c.ci[0].toFixed(2)}, {c.ci[1].toFixed(2)}] · p {pfmt(c.p_holm)} · r {c.effect == null ? "–" : c.effect.toFixed(2)}</div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-4 pb-4 pt-2 text-[12.5px] text-muted">
        Each cell: {res.schedulers[ref_]} minus that scheduler, averaged over the same users, with a 95% bootstrap interval, the Holm-adjusted
        Wilcoxon p-value and the rank-biserial effect size r (about 0.1 small, 0.3 medium, 0.5 large). Bold: p below 0.05. {note}
      </p>
    </Card>
  );
}

export function StudiesView({ studies }: { studies: Studies }) {
  const cal = studies.calibration;
  const stab = studies.stability;
  const sb = studies.solver_benchmark;
  return (
    <div className="space-y-6">
      {cal && (
        <Card className="overflow-x-auto">
          <SectionTitle>Duration models: is P80 really an 80% estimate?</SectionTitle>
          <p className="mb-3 text-[13px] text-muted">
            {cal.config.users} synthetic users × {cal.config.tasks_per_user} tasks, each predicted from earlier outcomes only. A calibrated P80 covers 80% of real
            durations. Pinball loss scores calibration and tightness together (lower is better). v1 is the original model; v2 is the hierarchical model now in use.
          </p>
          <table className="w-full min-w-[560px] text-[13px]">
            <thead className="text-left text-[12px] text-muted"><tr><th className="py-1 font-medium">Model</th><th className="font-medium">Records in category</th><th className="font-medium">Tasks</th><th className="font-medium">P80 coverage</th><th className="font-medium">Pinball (min)</th><th className="font-medium">Median error (min)</th></tr></thead>
            <tbody className="divide-y divide-line">
              {Object.entries(cal.versions).flatMap(([v, rows]) => Object.entries(rows).filter(([, r]) => r.n).map(([b, r]) => (
                <tr key={v + b} className={clsx(b === "all" && "font-medium")}>
                  <td className="py-1.5">{v}</td><td>{b === "all" ? "all" : b}</td><td className="num">{r.n}</td>
                  <td className="num">{r.coverage.toFixed(1)}%</td><td className="num">{r.pinball80.toFixed(2)}</td><td className="num">{r.mae.toFixed(1)}</td>
                </tr>
              )))}
            </tbody>
          </table>
          {cal.pinball_difference && <p className="hint mt-2">Pinball difference ({cal.pinball_difference.meaning}): {cal.pinball_difference.mean.toFixed(3)} [{cal.pinball_difference.ci[0].toFixed(3)}, {cal.pinball_difference.ci[1].toFixed(3)}].</p>}
        </Card>
      )}
      {stab && (
        <Card className="overflow-x-auto">
          <SectionTitle>Replanning stability</SectionTitle>
          <p className="mb-3 text-[13px] text-muted">{stab.cases} disruptions (an urgent task, or two hours lost), each replanned at 11:00 against the 08:30 plan of about {stab.previous_blocks_mean.toFixed(1)} blocks. {stab.note}</p>
          <table className="w-full min-w-[560px] text-[13px]">
            <thead className="text-left text-[12px] text-muted"><tr><th className="py-1 font-medium">Stability</th><th className="font-medium">Blocks changed</th><th className="font-medium">Minutes moved</th><th className="font-medium">Quality</th><th className="font-medium">Deadline safety</th><th className="font-medium">Urgent placed</th></tr></thead>
            <tbody className="divide-y divide-line">
              {Object.entries(stab.table).map(([lv, e]) => (
                <tr key={lv}>
                  <td className="py-1.5 num">{Math.round(Number(lv) * 100)}%</td>
                  <td className="num">{e.changed.mean.toFixed(2)}{e.vs_free && <span className="text-muted"> (p {pfmt(e.vs_free.changed.p)})</span>}</td>
                  <td className="num">{Math.round(e.displacement.mean)}</td>
                  <td className="num">{e.quality.mean.toFixed(3)}{e.vs_free && <span className="text-muted"> ({e.vs_free.quality.diff >= 0 ? "+" : ""}{e.vs_free.quality.diff.toFixed(3)})</span>}</td>
                  <td className="num">{(e.deadline_safety.mean * 100).toFixed(1)}%</td>
                  <td className="num">{e.urgent_placed_pct == null ? "–" : `${e.urgent_placed_pct}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {sb && (
        <Card className="overflow-x-auto">
          <SectionTitle>Solver benchmark</SectionTitle>
          <p className="mb-3 text-[13px] text-muted">{sb.config.instances} random problems per size. Fitness is the full Balanced fitness for every optimiser; gap is the shortfall from the best plan any of them found. {sb.note}</p>
          <table className="w-full min-w-[620px] text-[13px]">
            <thead className="text-left text-[12px] text-muted"><tr><th className="py-1 font-medium">Tasks</th><th className="font-medium">Optimiser</th><th className="font-medium">Fitness</th><th className="font-medium">Gap</th><th className="font-medium">Best on</th><th className="font-medium">Seconds</th><th className="font-medium">Rule violations</th><th className="font-medium">Solver status</th></tr></thead>
            <tbody className="divide-y divide-line">
              {Object.entries(sb.table).flatMap(([n, row]) => Object.entries(row).map(([name, v]) => (
                <tr key={n + name}>
                  <td className="py-1.5 num">{n}</td><td>{name}</td><td className="num">{v.fitness.toFixed(4)}</td><td className="num">{v.gap_pct.toFixed(2)}%</td>
                  <td className="num">{v.best_count}/{sb.config.instances}</td><td className="num">{v.seconds.toFixed(2)}</td><td className="num">{v.violations}</td>
                  <td className="text-[12px] text-muted">{v.status ? Object.entries(v.status).map(([k, c]) => `${k} ${c}`).join(", ") : ""}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
