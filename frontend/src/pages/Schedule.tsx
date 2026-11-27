import clsx from "clsx";
import { RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { usePlan, usePlanMutation, usePrefs, useTasks } from "../api/hooks";
import { PRIORITY_NAMES, type PlanRun, type PlanVersion } from "../api/types";
import { DayTimeline, HorizonView } from "../components/Timeline";
import { WhyPanel } from "../components/WhyPanel";
import { Badge, Button, Card, EmptyState, ErrorState, InlineError, PageHeader, priorityTone, Segmented, Skeleton, Tabs, useToast } from "../components/ui";
import { relDeadline } from "../lib/format";

const shortDay = (date: string) => {
  const d = new Date(`${date}T12:00:00`);
  return `${d.toLocaleDateString(undefined, { weekday: "short" })} ${d.getDate()}`;
};

const PART_LABELS: Record<string, { label: string; penalty?: boolean }> = {
  pri: { label: "Priority coverage" },
  dl: { label: "Deadline safety" },
  en: { label: "Chance blocks happen" },
  dur: { label: "Realistic durations" },
  pref: { label: "Breaks and late work" },
  over: { label: "Overload", penalty: true },
  cs: { label: "Context switching", penalty: true },
  bal: { label: "Uneven days", penalty: true },
  stab: { label: "Changes to your previous plan", penalty: true },
};

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`);

export function SchedulePage() {
  const plan = usePlan();
  const prefs = usePrefs();
  const tasks = useTasks("status=pending");
  const toast = useToast();
  const [view, setView] = useState<"day" | "horizon">("day");
  const [day, setDay] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [horizon, setHorizon] = useState<number | null>(null);
  const [preset, setPreset] = useState<string | null>(null);
  const [tab, setTab] = useState<"unscheduled" | "alternatives" | "risk" | "score">("unscheduled");
  const [keepSteady, setKeepSteady] = useState(true);
  const generate = usePlanMutation(() =>
    api<PlanRun>("/api/schedules/generate", {
      method: "POST",
      body: {
        horizon_days: horizon ?? prefs.data?.horizon_days,
        preset: preset ?? prefs.data?.ga_preset,
        // Replanning keeps the current plan as steady as the saved preference says, unless switched off.
        stability: keepSteady ? (prefs.data?.replan_stability ?? 0.5) : 0,
      },
    }),
  );
  const activate = usePlanMutation((vid: number) => api<PlanRun>(`/api/schedules/${vid}/activate`, { method: "POST" }));

  const run = plan.data;
  const active = run?.plans.find((p) => p.version_id === run.active_version_id) ?? run?.plans[0];
  const blocks = active?.blocks ?? [];
  const sel = blocks.find((b) => b.block_id === selected) ?? null;
  const dayInfo = run?.days[Math.min(day, (run?.days.length ?? 1) - 1)];
  const dayBlocks = useMemo(() => blocks.filter((b) => dayInfo && b.start.slice(0, 10) === dayInfo.date), [blocks, dayInfo]);

  useEffect(() => { if (run && day >= run.days.length) setDay(0); }, [run, day]);

  const onGenerate = () =>
    generate.mutate(undefined, {
      onSuccess: (r) => {
        setSelected(null);
        toast({ text: `Planned ${r?.plans[0].blocks.filter((b) => b.kind === "ai").length ?? 0} tasks in ${r?.meta.seconds ?? "?"} s` });
      },
    });

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-[13px] text-muted">
        Plan
        <select className="field h-10 w-auto py-1 pr-8" value={horizon ?? prefs.data?.horizon_days ?? 3} onChange={(e) => setHorizon(Number(e.target.value))}>
          {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n === 1 ? "today only" : `${n} days`}</option>)}
        </select>
      </label>
      <label className="flex items-center gap-2 text-[13px] text-muted">
        Style
        <select className="field h-10 w-auto py-1 pr-8" value={preset ?? prefs.data?.ga_preset ?? "balanced"} onChange={(e) => setPreset(e.target.value)}>
          <option value="balanced">Balanced</option><option value="deadline">Deadline-first</option><option value="gentle">Gentle</option>
        </select>
      </label>
      {plan.data && (
        <label className="flex items-center gap-2 text-[13px] text-muted" title="When on, regenerating moves as few of your current blocks as it can">
          <input type="checkbox" checked={keepSteady} onChange={(e) => setKeepSteady(e.target.checked)} className="h-4 w-4 accent-teal" />
          Keep current plan steady
        </label>
      )}
      <Button variant="primary" onClick={onGenerate} loading={generate.isPending}>
        {run ? <RefreshCw size={16} aria-hidden /> : <Sparkles size={16} aria-hidden />} {run ? "Regenerate" : "Plan my days"}
      </Button>
    </div>
  );

  if (plan.isLoading) return <><PageHeader title="AI Schedule" /><Skeleton className="h-96" /></>;
  if (plan.error) return <><PageHeader title="AI Schedule" /><ErrorState error={plan.error} onRetry={() => plan.refetch()} /></>;

  if (!run || !active) {
    return (
      <>
        <PageHeader title="AI Schedule" sub="Your tasks placed where your energy fits, with a reason for every choice." actions={controls} />
        <InlineError error={generate.error} />
        {tasks.data && !tasks.data.length ? (
          <EmptyState title="Add a few tasks first" body="The planner needs something to plan. Add tasks with rough durations and how demanding they feel." action={<Link to="/tasks"><Button variant="primary">Go to tasks</Button></Link>} />
        ) : (
          <EmptyState title="No plan yet" body="Press Plan my days. A quick energy check-in first makes the plan fit today better." action={<Link to="/check-in"><Button>Check in first</Button></Link>} />
        )}
      </>
    );
  }

  const stale = (Date.now() - new Date(run.created_at).getTime()) / 3600000 > 6;
  return (
    <>
      <PageHeader
        title="AI Schedule"
        sub={
          <span className="flex flex-wrap items-center gap-2">
            <span>{active.blocks.filter((b) => b.kind === "ai").length} tasks planned over {run.days.length} day{run.days.length > 1 ? "s" : ""}</span>
            <Badge tone={run.meta.mode === "personalized" ? "teal" : "muted"}>
              {run.meta.mode === "personalized" ? `Personalized from ${run.meta.outcomes_used} outcomes` : "Cold start: default assumptions"}
            </Badge>
            <Badge>{active.label} style</Badge>
            {active.optimizer_label && <Badge tone="muted">{active.optimizer_label}</Badge>}
          </span>
        }
        actions={controls}
      />
      <InlineError error={generate.error ?? activate.error} />
      {stale && <p className="mb-4 rounded-lg bg-warn-tint px-3 py-2 text-[13.5px] text-warn">This plan is from {new Date(run.created_at).toLocaleString()}. Regenerate to plan from now.</p>}
      {active.stability && (
        <p className="mb-4 rounded-lg bg-teal-tint px-3 py-2 text-[13.5px] text-teal">
          Replanned against your previous plan: kept {active.stability.kept} of {active.stability.previous_blocks} blocks
          {active.stability.moved > 0 && `, moved ${active.stability.moved}`}
          {active.stability.removed > 0 && `, removed ${active.stability.removed}`}
          {active.stability.added > 0 && `, added ${active.stability.added} new`}.
        </p>
      )}
      {run.meta.warnings.map((w) => <p key={w} className="mb-4 rounded-lg bg-warn-tint px-3 py-2 text-[13.5px] text-warn">{w}</p>)}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented label="View" value={view} onChange={setView} options={[{ value: "day", label: "Day" }, { value: "horizon", label: "All days" }]} />
        {view === "day" && (
          <div className="flex gap-1" role="tablist" aria-label="Day">
            {run.days.map((d) => (
              <button type="button" key={d.date} role="tab" aria-selected={day === d.day} onClick={() => { setDay(d.day); setSelected(null); }}
                className={clsx("h-8 rounded-md px-3 text-[13px] font-medium", day === d.day ? "bg-ink text-white" : "text-muted hover:bg-beige hover:text-ink")}>
                {d.day === 0 ? "Today" : d.day === 1 ? "Tomorrow" : shortDay(d.date)}
              </button>
            ))}
          </div>
        )}
        {view === "day" && dayInfo && (
          <span className="text-[13px] text-muted">
            {dayInfo.energy_source === "check-in"
              ? `Energy from your check-in: mental ${dayInfo.energy.mental}, focus ${dayInfo.energy.focus}, stress ${dayInfo.energy.stress}`
              : "Energy is a forecast from your recent check-ins"}
            {dayInfo.stress_cap && " · high stress, load capped at 70%"}
          </span>
        )}
      </div>

      {view === "day" && dayInfo ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <Card className="p-4 sm:p-5">
            <p className="mb-3 text-[12.5px] text-muted">The shaded strip shows your expected mental energy; darker means sharper.</p>
            <DayTimeline run={run} day={dayInfo} blocks={dayBlocks} selected={selected} onSelect={setSelected} />
          </Card>
          <div className="lg:sticky lg:top-6 lg:self-start">
            {sel ? <WhyPanel key={sel.block_id} block={sel} onClose={() => setSelected(null)} /> : (
              <div className="rounded-card border border-dashed border-line p-5 text-muted">
                <p className="font-medium text-ink">Select a block to see why it is there</p>
                <p className="mt-1 text-[13.5px]">You'll see how likely it is to happen at that time and why, the predicted duration, and the rules that shaped its time.</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          <HorizonView run={run} blocks={blocks} loads={active.day_load} onPick={(d, id) => { setView("day"); setDay(d); setSelected(id); }} />
        </>
      )}

      <div className="mt-10">
        <Tabs value={tab} onChange={setTab} tabs={[
          { value: "unscheduled", label: `Not planned (${active.unscheduled.length})` },
          { value: "alternatives", label: `Alternatives (${run.plans.length - 1})` },
          { value: "risk", label: "What could go wrong" },
          { value: "score", label: "How the plan was scored" },
        ]} />
        {tab === "unscheduled" && <Unscheduled plan={active} />}
        {tab === "alternatives" && <Alternatives run={run} onUse={(vid) => activate.mutate(vid, { onSuccess: () => toast({ text: "Switched plan" }) })} />}
        {tab === "risk" && <Risk plan={active} run={run} />}
        {tab === "score" && <Score plan={active} run={run} />}
      </div>
    </>
  );
}

function Unscheduled({ plan }: { plan: PlanVersion }) {
  if (!plan.unscheduled.length) return <EmptyState title="Everything fits" body="Every pending task has a place in this plan." />;
  return (
    <Card className="p-0">
      <ul className="divide-y divide-line">
        {plan.unscheduled.map((u) => (
          <li key={u.task_id} className="flex flex-wrap items-start gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="font-medium">{u.title}</div>
              <p className="mt-0.5 text-[13.5px] text-muted">{u.reason}</p>
            </div>
            <Badge tone={priorityTone(u.priority)}>{PRIORITY_NAMES[u.priority]}</Badge>
            {u.deadline && <Badge tone="brown">Due {relDeadline(u.deadline)}</Badge>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Alternatives({ run, onUse }: { run: PlanRun; onUse: (vid: number) => void }) {
  const main = run.plans[0];
  if (run.plans.length < 2) {
    return <EmptyState title="No meaningfully different alternative" body="The Deadline-first and Gentle styles placed over 70% of tasks at the same times, so they are not shown." />;
  }
  const avgFit = (p: PlanVersion) => {
    const ai = p.blocks.filter((b) => b.fit !== undefined);
    return ai.length ? ai.reduce((s, b) => s + (b.fit ?? 0), 0) / ai.length : 0;
  };
  const maxLoad = (p: PlanVersion) => Math.max(...p.day_load.map((d) => d.load));
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {run.plans.map((p) => (
        <Card key={p.version_id} className={clsx(p.version_id === run.active_version_id && "border-teal")}>
          <div className="flex items-center justify-between">
            <h3 className="text-[16px] font-semibold">{p.label}</h3>
            {p.version_id === run.active_version_id ? <Badge tone="teal">In use</Badge> : p.is_main && <Badge>Your style</Badge>}
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-y-1.5 text-[13.5px]">
            <dt className="text-muted">Tasks planned</dt><dd className="num text-right">{p.blocks.filter((b) => b.kind === "ai").length}</dd>
            <dt className="text-muted">Average chance a block happens</dt><dd className="num text-right">{Math.round(avgFit(p) * 100)}%</dd>
            <dt className="text-muted">Busiest day</dt><dd className="num text-right">{Math.round(maxLoad(p) * 100)}%</dd>
            <dt className="text-muted">Not planned</dt><dd className="num text-right">{p.unscheduled.length}</dd>
            {p.robustness && <>
              <dt className="text-muted">Expected to finish</dt><dd className="num text-right">{p.robustness.expected_completed.toFixed(1)}</dd>
              <dt className="text-muted">Deadlines met</dt><dd className="num text-right">{pct(p.robustness.deadline_safety)}</dd>
            </>}
          </dl>
          {p.tradeoffs && p.tradeoffs.best_at.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {p.tradeoffs.best_at.map((b) => <Badge key={b} tone="teal">Best for: {b.toLowerCase()}</Badge>)}
            </div>
          )}
          {p.tradeoffs && !p.tradeoffs.pareto_optimal && (
            <p className="mt-2 rounded-md bg-warn-tint px-2 py-1 text-[12.5px] text-warn"
              title="Dominated: another plan is at least as good on every measure and clearly better on one">
              {p.tradeoffs.dominated_by.join(" and ")} {p.tradeoffs.dominated_by.length > 1 ? "do" : "does"} at least as well on everything, so there is little reason to pick this one.
            </p>
          )}
          {p.tradeoffs && p.version_id !== main.version_id && p.tradeoffs.gives_up_vs_main.length > 0 && (
            <p className="mt-2 text-[12.5px] text-muted">Gives up against {main.label}: {p.tradeoffs.gives_up_vs_main.join(", ").toLowerCase()}.</p>
          )}
          {p.version_id !== main.version_id && (
            <p className="mt-3 text-[12.5px] text-muted">
              {p.preset === "deadline" ? "Safer deadlines: due work goes first, even at less ideal times." : p.preset === "gentle" ? "Lighter day: avoids packed days, even if fewer tasks fit." : "Most tasks done: weighs priority, deadlines and timing evenly."}
            </p>
          )}
          {p.version_id !== run.active_version_id && <Button className="mt-4 w-full" onClick={() => onUse(p.version_id)}>Use this plan</Button>}
        </Card>
      ))}
    </div>
  );
}

export function Risk({ plan, run }: { plan: PlanVersion; run: PlanRun }) {
  const r = plan.robustness;
  if (!r) return <EmptyState title="No simulation for this plan" body="Regenerate to see how the plan holds up when tasks run long or get skipped." />;
  const pm = (v: number | null | undefined, se: number | null | undefined) => (v == null || se == null ? "" : ` (±${Math.round(1.96 * se * 100)} pts)`);
  const sel = plan.selection;
  const rows: [string, string, string][] = [
    ["Tasks finished", `${r.expected_completed.toFixed(1)} of ${r.planned}`, `Usually between ${r.completed_p10} and ${r.completed_p90}.${r.se ? ` Estimate ±${(1.96 * r.se.expected_completed).toFixed(1)}.` : ""}`],
    ["All high-priority blocks done", pct(r.p_all_important_done),
      r.important_unplanned ? `${r.important_unplanned} high-priority task${r.important_unplanned > 1 ? "s are" : " is"} not in the plan at all.` : `${r.important_planned} High or Critical blocks planned.`],
    ["Every planned deadline met", pct(r.p_all_deadlines_met), `Chance that no deadline is missed, counting knock-on delays.${pm(r.p_all_deadlines_met, r.se?.p_all_deadlines_met)}`],
    ["Deadline work finished on time", pct(r.deadline_safety), "Share of tasks due in this horizon that finish before their deadline; unplanned ones count as late."],
    ["Work left over", `${Math.round(r.expected_unfinished_minutes)} min`, "Expected minutes skipped, or cut off at the end of the day."],
    ["A day runs past its end", pct(r.p_overrun_any_day), r.p_overrun_by_day.map((p, d) => `${d === 0 ? "today" : d === 1 ? "tomorrow" : shortDay(run.days[d]?.date ?? "")} ${pct(p)}`).join(" · ")],
    ["Spare time", `${Math.round(r.expected_unused_minutes / 60 * 10) / 10} h`, "Free time not used by planned work, on average."],
  ];
  return (
    <Card>
      <h3 className="text-[15px] font-semibold">How this plan holds up</h3>
      <p className="hint mt-1">
        The plan was replayed {r.runs} times. Each time, durations were drawn from what you have taught the planner and some blocks were skipped
        at your usual rate. A block that runs long pushes the next one later. These are estimates, not guarantees.
        {r.adaptive && ` The number of runs was chosen automatically (${r.stopped === "target" ? "it stopped once the estimate was precise" : "it reached the cap"}).`}
      </p>
      {sel && (
        <p className="mt-2 rounded-md bg-canvas px-3 py-2 text-[13px]">
          {sel.switched
            ? `Chosen from ${sel.candidates.length} candidate plans because it did clearly better in simulation (${sel.chosen}).`
            : `${sel.candidates.length} candidate plans were simulated; none did clearly better than this one, so it was kept.`}
        </p>
      )}
      <dl className="mt-4 divide-y divide-line">
        {rows.map(([k, v, note]) => (
          <div key={k} className="grid gap-1 py-2.5 sm:grid-cols-[220px_90px_1fr] sm:items-baseline">
            <dt className="text-[14px]">{k}</dt>
            <dd className="num text-[15px] font-semibold">{v}</dd>
            <dd className="text-[13px] text-muted">{note}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function Score({ plan, run }: { plan: PlanVersion; run: PlanRun }) {
  const [rated, setRated] = useState<number | null>(null);
  const toast = useToast();
  async function rate(n: number) {
    await api(`/api/schedules/${plan.version_id}/feedback`, { method: "POST", body: { usefulness: n } });
    setRated(n);
    toast({ text: "Thanks. Ratings feed the evaluation." });
  }
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <h3 className="text-[15px] font-semibold">Fitness {plan.fitness.toFixed(3)}</h3>
        <p className="hint mt-1">The optimiser ({plan.optimizer_label ?? "genetic algorithm"}) maximises this weighted sum. Hard rules are never traded off: every plan shown already obeys them.</p>
        <ul className="mt-4 space-y-3">
          {Object.entries(PART_LABELS).map(([k, meta]) => {
            const v = plan.components[k] ?? 0;
            const w = plan.weights?.[k] ?? 0;
            return (
              <li key={k}>
                <div className="flex justify-between text-[13.5px]">
                  <span>{meta.label}<span className="text-muted"> {meta.penalty ? "−" : "+"}{w.toFixed(2)} × </span></span>
                  <span className="num">{v.toFixed(2)}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-beige">
                  <div className={clsx("h-full rounded-full", meta.penalty ? "bg-warn" : "bg-teal")} style={{ width: `${Math.max(1, v * 100)}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
      <Card>
        <h3 className="text-[15px] font-semibold">Search progress</h3>
        <p className="hint mt-1">
          {plan.generations} generations in {plan.seconds} s, seed {run.seed}. It stops after 20 generations without improvement.
          {plan.convergence.some((c) => (c as { stage?: string }).stage) && " The last point is the refinement step (local search, or the CP-SAT solver) after the GA finished."}
        </p>
        <div className="mt-3 h-52">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={plan.convergence} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
              <CartesianGrid stroke="#EFE8DA" vertical={false} />
              <XAxis dataKey="gen" tick={{ fontSize: 11, fill: "#5B6660" }} axisLine={false} tickLine={false} label={{ value: "Generation", position: "insideBottom", offset: -2, fontSize: 11, fill: "#5B6660" }} height={32} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#5B6660" }} axisLine={false} tickLine={false} tickFormatter={(v) => Number(v).toFixed(2)} />
              <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #E4DCCB", fontSize: 13 }} formatter={(v, n) => [Number(v).toFixed(4), n]} labelFormatter={(g) => `Generation ${g}`} />
              <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
              <Line name="Best plan" dataKey="best" stroke="#1F6F6B" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line name="Population average" dataKey="mean" stroke="#8C948F" strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-5 border-t border-line pt-4">
          <p className="text-[14px] font-medium">How useful is this plan?</p>
          <div className="mt-2 flex gap-1.5" role="group" aria-label="Usefulness rating 1 to 5">
            {[1, 2, 3, 4, 5].map((n) => (
              <button type="button" key={n} onClick={() => rate(n)} aria-pressed={rated === n}
                className={clsx("num h-9 w-9 rounded-lg border text-[14px]", rated === n ? "border-teal bg-teal text-white" : "border-line bg-surface hover:border-teal")}>
                {n}
              </button>
            ))}
          </div>
          <p className="hint mt-1">1 = not useful, 5 = exactly what I needed.</p>
        </div>
      </Card>
    </div>
  );
}
