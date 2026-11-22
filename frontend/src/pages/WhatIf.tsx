import clsx from "clsx";
import { ArrowRight, Play } from "lucide-react";
import { ReactNode, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { usePlan, usePrefs, useRefreshAll, useTasks } from "../api/hooks";
import type { LitePlan, PlanRun, Scenario, WhatIfResult } from "../api/types";
import { Badge, Button, Card, EmptyState, fitTone, InlineError, PageHeader, SectionTitle, useToast } from "../components/ui";
import { dayName, hm, toLocalIso } from "../lib/format";

type Key = "late" | "urgent" | "lose" | "energy" | "extend";

function Toggle({ on, onChange, title, children }: { on: boolean; onChange: (v: boolean) => void; title: string; children: ReactNode }) {
  return (
    <div className={clsx("rounded-xl border p-4 transition-colors", on ? "border-teal/50 bg-teal-tint/30" : "border-line bg-surface")}>
      <label className="flex cursor-pointer items-center gap-3">
        <input type="checkbox" className="h-4 w-4 accent-teal" checked={on} onChange={(e) => onChange(e.target.checked)} />
        <span className="font-medium">{title}</span>
      </label>
      {on && <div className="mt-3 grid gap-3 sm:grid-cols-2">{children}</div>}
    </div>
  );
}

export function WhatIfPage() {
  const tasks = useTasks("status=pending&sort=priority");
  const prefs = usePrefs();
  const current = usePlan();
  const refresh = useRefreshAll();
  const toast = useToast();
  const [on, setOn] = useState<Record<Key, boolean>>({ late: true, urgent: false, lose: false, energy: false, extend: false });
  const [late, setLate] = useState(120);
  const [urgent, setUrgent] = useState({ title: "Urgent request", est_minutes: 60, deadline_hours: 6, priority: 4, mental: 6, physical: 2, category: "Work" });
  const [lose, setLose] = useState({ day: 0, start: "14:00", end: "16:00" });
  const [energy, setEnergy] = useState(-3);
  const [extend, setExtend] = useState({ task_id: 0, extra_minutes: 60 });
  const horizon = prefs.data?.horizon_days ?? 3;
  const [stability, setStability] = useState<number | null>(null);
  const steady = stability ?? prefs.data?.replan_stability ?? 0.5;

  const scenario: Scenario = {
    ...(on.late && { late_start_minutes: late }),
    ...(on.urgent && { urgent_task: urgent }),
    ...(on.lose && { lose_time: lose }),
    ...(on.energy && { energy_delta: energy }),
    ...(on.extend && extend.task_id && { extend_task: extend }),
  };
  const hasChange = Object.keys(scenario).length > 0;
  const run = useMutation({ mutationFn: () => api<WhatIfResult>("/api/simulate", { method: "POST", body: { ...scenario, stability: steady } }) });
  const applicable = run.data && (run.data.scenario.urgent_task || run.data.scenario.lose_time || run.data.scenario.extend_task);
  const apply = useMutation({
    mutationFn: async () => {
      const sc = run.data!.scenario;
      if (sc.urgent_task) {
        const u = sc.urgent_task;
        await api("/api/tasks", { method: "POST", body: {
          title: u.title, category: u.category, priority: u.priority, est_minutes: u.est_minutes,
          deadline: toLocalIso(new Date(Date.now() + u.deadline_hours * 3600000)),
          mental_difficulty: u.mental, mental_energy_req: u.mental, physical_difficulty: u.physical, physical_energy_req: u.physical,
        } });
      }
      if (sc.lose_time) {
        const d = new Date(); d.setDate(d.getDate() + sc.lose_time.day);
        const day = toLocalIso(d).slice(0, 10);
        await api("/api/commitments", { method: "POST", body: { label: "Unavailable", kind: "unavailable", start: `${day}T${sc.lose_time.start}:00`, end: `${day}T${sc.lose_time.end}:00` } });
      }
      if (sc.extend_task) {
        const t = tasks.data?.find((x) => x.id === sc.extend_task!.task_id);
        if (t) await api(`/api/tasks/${t.id}`, { method: "PATCH", body: { est_minutes: Math.min(480, t.est_minutes + sc.extend_task.extra_minutes) } });
      }
      return api<PlanRun>("/api/schedules/generate", { method: "POST", body: {} });
    },
    onSuccess: async () => { await refresh(); toast({ text: "Changes saved and your plan regenerated" }); },
  });

  const dayOptions = Array.from({ length: horizon }, (_, i) => i);
  const dayLabel = (i: number) => (i === 0 ? "Today" : i === 1 ? "Tomorrow" : new Date(Date.now() + i * 86400000).toLocaleDateString(undefined, { weekday: "long" }));

  return (
    <>
      <PageHeader title="What-if" sub="Try a change to your day and see how the plan would adapt, before it happens." />
      {tasks.data && !tasks.data.length ? (
        <EmptyState title="Add tasks first" body="The simulator replans your pending tasks, so it needs some to work with." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
          <div className="space-y-3">
            <Toggle title="I start the day late" on={on.late} onChange={(v) => setOn({ ...on, late: v })}>
              <label className="sm:col-span-2 text-[13px]">
                <span className="label">By how much</span>
                <select className="field" value={late} onChange={(e) => setLate(Number(e.target.value))}>
                  {[30, 60, 90, 120, 180, 240, 300].map((m) => <option key={m} value={m}>{m < 60 ? `${m} min` : `${m / 60} h`}</option>)}
                </select>
              </label>
            </Toggle>
            <Toggle title="An urgent task comes in" on={on.urgent} onChange={(v) => setOn({ ...on, urgent: v })}>
              <label className="sm:col-span-2"><span className="label">Task</span>
                <input className="field" value={urgent.title} onChange={(e) => setUrgent({ ...urgent, title: e.target.value })} /></label>
              <label><span className="label">Minutes</span>
                <input type="number" min={5} max={480} step={5} className="field num" value={urgent.est_minutes} onChange={(e) => setUrgent({ ...urgent, est_minutes: Number(e.target.value) })} /></label>
              <label><span className="label">Due in (hours)</span>
                <input type="number" min={1} max={168} className="field num" value={urgent.deadline_hours} onChange={(e) => setUrgent({ ...urgent, deadline_hours: Number(e.target.value) })} /></label>
              <label className="sm:col-span-2"><span className="label">How demanding (mental, 1–10)</span>
                <input type="number" min={1} max={10} className="field num" value={urgent.mental} onChange={(e) => setUrgent({ ...urgent, mental: Number(e.target.value) })} /></label>
            </Toggle>
            <Toggle title="I lose some time" on={on.lose} onChange={(v) => setOn({ ...on, lose: v })}>
              <label className="sm:col-span-2"><span className="label">Day</span>
                <select className="field" value={lose.day} onChange={(e) => setLose({ ...lose, day: Number(e.target.value) })}>
                  {dayOptions.map((i) => <option key={i} value={i}>{dayLabel(i)}</option>)}
                </select></label>
              <label><span className="label">From</span><input type="time" className="field" value={lose.start} onChange={(e) => setLose({ ...lose, start: e.target.value })} /></label>
              <label><span className="label">To</span><input type="time" className="field" value={lose.end} onChange={(e) => setLose({ ...lose, end: e.target.value })} /></label>
            </Toggle>
            <Toggle title="My energy is lower than expected" on={on.energy} onChange={(v) => setOn({ ...on, energy: v })}>
              <label className="sm:col-span-2"><span className="label">Change to mental, physical and focus today: <span className="num font-semibold">{energy}</span></span>
                <input type="range" min={-6} max={-1} value={energy} onChange={(e) => setEnergy(Number(e.target.value))} className="energy" style={{ ["--fill" as string]: `${((energy + 6) / 5) * 100}%` }} />
                <span className="hint">Stress rises by half as much.</span></label>
            </Toggle>
            <Toggle title="A task takes longer" on={on.extend} onChange={(v) => setOn({ ...on, extend: v })}>
              <label className="sm:col-span-2"><span className="label">Which task</span>
                <select className="field" value={extend.task_id} onChange={(e) => setExtend({ ...extend, task_id: Number(e.target.value) })}>
                  <option value={0}>Choose a task</option>
                  {(tasks.data ?? []).filter((t) => !t.is_fixed && !t.recur_days).map((t) => <option key={t.id} value={t.id}>{t.title} ({t.est_minutes} min)</option>)}
                </select></label>
              <label className="sm:col-span-2"><span className="label">Extra minutes</span>
                <input type="number" min={5} max={480} step={5} className="field num" value={extend.extra_minutes} onChange={(e) => setExtend({ ...extend, extra_minutes: Number(e.target.value) })} /></label>
            </Toggle>
            <label className="block rounded-card border border-line bg-surface p-3">
              <span className="label">Keep the current plan steady: {Math.round(steady * 100)}%</span>
              <input type="range" min={0} max={1} step={0.05} value={steady} onChange={(e) => setStability(Number(e.target.value))} className="w-full accent-teal" aria-describedby="steady-hint" />
              <span id="steady-hint" className="hint">0% replans from scratch. Higher keeps more of your blocks where they are and fits the change around them.</span>
            </label>
            <InlineError error={run.error} />
            <Button variant="primary" className="w-full" loading={run.isPending} disabled={!hasChange} onClick={() => run.mutate()}>
              <Play size={16} aria-hidden /> Simulate
            </Button>
            <p className="hint">Both plans use the same random seed{current.data ? ` as your current plan (${current.data.seed})` : ""}, so every difference comes from the change you chose. Nothing is saved unless you apply it.</p>
          </div>

          <div className="min-w-0">
            {!run.data ? (
              <EmptyState title="Pick one or more changes and press Simulate" body="You'll see the plan before and after, which tasks moved or dropped, and why." />
            ) : (
              <Result r={run.data} onApply={applicable ? () => apply.mutate() : undefined} applying={apply.isPending} applyError={apply.error} />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function Delta({ before, after, fmt, higherBetter = true }: { before: number | null; after: number | null; fmt: (v: number) => string; higherBetter?: boolean }) {
  if (before == null || after == null) return <span className="text-muted">n/a</span>;
  const d = after - before;
  if (Math.abs(d) < 1e-9 || fmt(Math.abs(d)) === fmt(0)) return <span className="text-muted">no change</span>;
  const good = higherBetter ? d > 0 : d < 0;
  return <span className={clsx("num font-medium", good ? "text-teal" : "text-warn")}>{d > 0 ? "+" : "−"}{fmt(Math.abs(d))}</span>;
}

function Result({ r, onApply, applying, applyError }: { r: WhatIfResult; onApply?: () => void; applying: boolean; applyError: unknown }) {
  const [day, setDay] = useState(0);
  const changed = new Set([...r.diff.moved.map((m) => m.task_id), ...r.diff.added.map((a) => a.task_id)]);
  const dropped = new Set(r.diff.dropped.map((d) => d.task_id));
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  const rows: [string, number | null, number | null, (v: number) => string, boolean][] = [
    ["Tasks planned", r.before.summary.tasks_planned, r.after.summary.tasks_planned, (v) => String(Math.round(v)), true],
    ["Minutes planned today", r.before.summary.today_minutes, r.after.summary.today_minutes, (v) => `${Math.round(v)}`, true],
    ["Average energy fit", r.before.summary.avg_fit, r.after.summary.avg_fit, (v) => v.toFixed(2), true],
    ["Chance of meeting deadlines", r.before.summary.deadline_safety, r.after.summary.deadline_safety, pct, true],
    ["Busiest day load", r.before.summary.busiest_day_load, r.after.summary.busiest_day_load, pct, false],
    ["Not planned", r.before.summary.not_planned, r.after.summary.not_planned, (v) => String(Math.round(v)), false],
  ];
  return (
    <div className="space-y-6">
      <Card glass>
        <SectionTitle>What changed</SectionTitle>
        <ul className="space-y-1.5 text-[14.5px] leading-relaxed">
          {r.explanation.map((l, i) => <li key={i} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-teal" aria-hidden />{l}</li>)}
        </ul>
        {onApply && (
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <Button variant="primary" loading={applying} onClick={onApply}>Apply these changes and replan</Button>
            <span className="hint">Saves the urgent task, lost time or longer estimate for real. Late starts and energy changes are not saved; check in instead.</span>
            <InlineError error={applyError} />
          </div>
        )}
      </Card>

      {r.free_replan && r.stable_replan && (
        <Card>
          <SectionTitle>Steady replan versus starting over</SectionTitle>
          <p className="hint -mt-1 mb-3">The same change, replanned twice: once keeping your plan {Math.round((r.stability ?? 0) * 100)}% steady (shown everywhere on this page), once from scratch.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-[14px]">
              <caption className="sr-only">Steady replan compared with a full replan</caption>
              <thead className="text-left text-[12.5px] text-muted">
                <tr><th className="py-1 font-medium">Measure</th><th className="px-3 font-medium">Steady</th><th className="px-3 font-medium">From scratch</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {([
                  ["Blocks moved", r.stable_replan.changes.moved, r.free_replan.changes.moved, (v: number) => String(v)],
                  ["Blocks dropped", r.stable_replan.changes.dropped, r.free_replan.changes.dropped, (v: number) => String(v)],
                  ["Blocks kept in place", r.stable_replan.changes.unchanged, r.free_replan.changes.unchanged, (v: number) => String(v)],
                  ["Average energy fit", r.stable_replan.summary.avg_fit, r.free_replan.summary.avg_fit, (v: number) => v.toFixed(2)],
                  ["Expected tasks finished", r.stable_replan.summary.expected_completed ?? null, r.free_replan.summary.expected_completed ?? null, (v: number) => v.toFixed(1)],
                  ["Deadline work on time (simulated)", r.stable_replan.summary.deadline_safety_mc ?? null, r.free_replan.summary.deadline_safety_mc ?? null, pct],
                ] as [string, number | null, number | null, (v: number) => string][]).map(([label, a, b, fmt]) => (
                  <tr key={label}><td className="py-1.5">{label}</td><td className="num px-3">{a == null ? "n/a" : fmt(a)}</td><td className="num px-3">{b == null ? "n/a" : fmt(b)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-[14px]">
          <caption className="sr-only">Plan before and after</caption>
          <thead className="bg-beige/50 text-left text-[12.5px] text-muted">
            <tr><th className="px-4 py-2 font-medium">Measure</th><th className="px-3 font-medium">Before</th><th className="px-3 font-medium">After</th><th className="px-3 font-medium">Change</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map(([label, b, a, fmt, hb]) => (
              <tr key={label}>
                <td className="px-4 py-2">{label}</td>
                <td className="num px-3">{b == null ? "n/a" : fmt(b)}</td>
                <td className="num px-3">{a == null ? "n/a" : fmt(a)}</td>
                <td className="px-3"><Delta before={b} after={a} fmt={fmt} higherBetter={hb} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {(r.diff.moved.length > 0 || r.diff.dropped.length > 0 || r.diff.added.length > 0) && (
        <Card>
          <SectionTitle>Task by task</SectionTitle>
          <ul className="divide-y divide-line">
            {r.diff.added.map((a) => (
              <li key={`a${a.task_id}`} className="flex flex-wrap items-center gap-2 py-2"><Badge tone="teal">Added</Badge><span className="font-medium">{a.title}</span><span className="num text-muted">{dayName(a.to)} {hm(a.to)}</span></li>
            ))}
            {r.diff.moved.map((m) => (
              <li key={`m${m.task_id}`} className="flex flex-wrap items-center gap-2 py-2">
                <Badge tone="brown">Moved</Badge><span className="font-medium">{m.title}</span>
                <span className="num text-muted">{dayName(m.from)} {hm(m.from)}</span><ArrowRight size={14} className="text-muted" aria-label="to" />
                <span className="num">{dayName(m.to)} {hm(m.to)}</span>
              </li>
            ))}
            {r.diff.dropped.map((d) => (
              <li key={`d${d.task_id}`} className="py-2">
                <div className="flex flex-wrap items-center gap-2"><Badge tone="danger">Dropped</Badge><span className="font-medium">{d.title}</span><span className="num text-muted">was {dayName(d.from)} {hm(d.from)}</span></div>
                <p className="mt-1 text-[13px] text-muted">{d.reason}</p>
              </li>
            ))}
          </ul>
          <p className="hint mt-2">{r.diff.unchanged} task{r.diff.unchanged === 1 ? "" : "s"} kept the same time.</p>
        </Card>
      )}

      <div>
        <div className="mb-3 flex flex-wrap items-center gap-1" role="tablist" aria-label="Day">
          {r.after.days.map((d) => (
            <button type="button" key={d.day} role="tab" aria-selected={day === d.day} onClick={() => setDay(d.day)}
              className={clsx("h-8 rounded-md px-3 text-[13px] font-medium", day === d.day ? "bg-ink text-white" : "text-muted hover:bg-beige hover:text-ink")}>
              {dayName(`${d.date}T12:00:00`, true)}
            </button>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <DayList title="Before" plan={r.before} day={day} mark={(id) => (dropped.has(id) ? "dropped" : changed.has(id) ? "changed" : null)} />
          <DayList title="After" plan={r.after} day={day} mark={(id) => (changed.has(id) ? "changed" : null)} />
        </div>
      </div>
    </div>
  );
}

function DayList({ title, plan, day, mark }: { title: string; plan: LitePlan; day: number; mark: (id: number) => "changed" | "dropped" | null }) {
  const date = plan.days[day]?.date;
  const items = [
    ...plan.blocks.filter((b) => b.day === day).map((b) => ({ start: b.start, end: b.end, title: b.title, id: b.task_id, fit: b.fit_label, kind: "task" as const })),
    ...plan.fixed.filter((f) => f.day === day).map((f) => ({ start: f.start, end: f.end, title: f.title, id: f.task_id, fit: undefined, kind: "fixed" as const })),
    ...plan.commitments.filter((c) => c.start.slice(0, 10) === date).map((c, i) => ({ start: c.start, end: c.end, title: c.label, id: -100 - i, fit: undefined, kind: "busy" as const })),
  ].sort((a, b) => a.start.localeCompare(b.start));
  return (
    <Card className="p-4">
      <h3 className="mb-2 font-medium">{title}</h3>
      {!items.length ? <p className="text-muted">Nothing planned.</p> : (
        <ul className="space-y-1">
          {items.map((it) => {
            const m = it.kind === "task" ? mark(it.id) : null;
            return (
              <li key={`${it.kind}${it.id}${it.start}`} className={clsx("flex items-center gap-2 rounded-md px-2 py-1.5 text-[13.5px]",
                m === "changed" && "bg-teal-tint/60", m === "dropped" && "bg-danger-tint/60 line-through", it.kind === "busy" && "text-muted")}>
                <span className="num w-[5.5rem] shrink-0 text-[12.5px] text-muted">{hm(it.start)}–{hm(it.end)}</span>
                <span className="truncate">{it.title}</span>
                {it.fit && <Badge tone={fitTone(it.fit)} className="ml-auto">{it.fit}</Badge>}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
