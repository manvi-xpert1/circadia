import clsx from "clsx";
import { CheckCircle2, CircleSlash, Lock, PieChart } from "lucide-react";
import type { Block, DayInfo, PlanRun } from "../api/types";
import { hm } from "../lib/format";
import { Badge, fitTone } from "./ui";

const HOUR_PX = 60;
const toMin = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
const minOfDay = (iso: string) => {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
};

function OutcomeIcon({ b }: { b: Block }) {
  if (!b.outcome) return null;
  const s = b.outcome.status;
  const Icon = s === "done" ? CheckCircle2 : s === "partial" ? PieChart : CircleSlash;
  return <Icon size={15} className={s === "skipped" ? "text-muted" : "text-teal"} aria-label={`Outcome: ${s}`} />;
}

/** Capacity 3.5 or lower is pale; 8 or higher is full teal. */
function ribbonGradient(cap: number[]): string {
  const n = cap.length;
  const stops = cap.flatMap((c, i) => {
    const a = Math.min(1, Math.max(0.08, (c - 3.5) / 4.5)).toFixed(2);
    return [`rgba(31,111,107,${a}) ${((i / n) * 100).toFixed(2)}%`, `rgba(31,111,107,${a}) ${(((i + 1) / n) * 100).toFixed(2)}%`];
  });
  return `linear-gradient(180deg, ${stops.join(", ")})`;
}

/**
 * One day: hour rail, the energy ribbon (expected mental capacity per 15-minute
 * slot from the fuzzy engine), busy times and planned blocks.
 */
export function DayTimeline({
  run, day, blocks, selected, onSelect,
}: { run: PlanRun; day: DayInfo; blocks: Block[]; selected: number | null; onSelect: (id: number) => void }) {
  const start = toMin(run.meta.day_start);
  const end = toMin(run.meta.day_end);
  const top = (m: number) => ((m - start) / 60) * HOUR_PX;
  const height = top(end);
  const hours = Array.from({ length: Math.floor((end - start) / 60) + 1 }, (_, i) => start + i * 60);
  const commitments = run.commitments.filter((c) => c.start.slice(0, 10) === day.date);
  const now = new Date();
  const isToday = day.date === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const nowMin = now.getHours() * 60 + now.getMinutes();
  
  return (
    <div className="relative flex select-none" style={{ height: height + 12 }}>
      {/* Hour rail */}
      <div className="relative w-12 shrink-0">
        {hours.map((m) => (
          <span key={m} className="num absolute -translate-y-1/2 text-[12px] text-muted" style={{ top: top(m) }}>
            {String(Math.floor(m / 60)).padStart(2, "0")}:00
          </span>
        ))}
      </div>

      {/* Energy ribbon: one gradient stop pair per 15-minute slot */}
      <div
        className="relative mr-3 w-3 shrink-0 rounded-full bg-beige"
        role="img"
        aria-label={`Expected mental capacity through the day, ${day.energy_source === "forecast" ? "forecast" : "from your check-in"}: from ${Math.min(...day.capacity).toFixed(1)} to ${Math.max(...day.capacity).toFixed(1)} out of 10`}
        style={{ height, background: ribbonGradient(day.capacity) }}
      />

      {/* Grid + items */}
      <div className="relative flex-1">
        {hours.map((m) => <div key={m} className="absolute left-0 right-0 border-t border-line/70" style={{ top: top(m) }} />)}

        {commitments.map((c, i) => {
          const s = Math.max(start, minOfDay(c.start));
          const e = Math.min(end, minOfDay(c.end));
          if (e <= s) return null;
          return (
            <div key={i} className={clsx("absolute left-0 right-0 overflow-hidden rounded-lg px-3 py-1.5 text-[12.5px]", c.kind === "fixed" ? "bg-beige text-ink/80" : "border border-dashed border-line bg-canvas/80 text-muted")}
              style={{ top: top(s) + 1, height: top(e) - top(s) - 2 }}>
              <span className="font-medium">{c.label}</span> <span className="num text-muted">{hm(c.start)}–{hm(c.end)}</span>
            </div>
          );
        })}

        {blocks.map((b) => {
          const s = minOfDay(b.start);
          const e = minOfDay(b.end);
          const h = Math.max(top(e) - top(s) - 2, 22);
          const isSel = selected === b.block_id;
          const ai = b.kind === "ai";
          return (
            <button type="button"
              key={b.block_id}
              onClick={() => onSelect(b.block_id)}
              aria-pressed={isSel}
              aria-label={`${b.title}, ${hm(b.start)} to ${hm(b.end)}${b.fit_label ? `, ${b.fit_label} energy fit` : ""}`}
              className={clsx(
                "absolute left-0 right-0 overflow-hidden rounded-lg border text-left transition-shadow",
                ai ? "bg-surface" : "bg-beige/80",
                isSel ? "z-10 border-teal shadow-glass ring-2 ring-teal/25" : "border-line hover:border-teal/50 hover:shadow-lift",
                b.outcome && "opacity-75",
              )}
              style={{ top: top(s) + 1, height: h }}
            >
              <div className={clsx("absolute inset-y-0 left-0 w-1",
                ai ? (b.fit_label === "Excellent" ? "bg-teal" : b.fit_label === "Good" ? "bg-sage" : b.fit_label === "Fair" ? "bg-warn" : "bg-danger") : "bg-brown")} />
              <div className={clsx("flex h-full flex-col gap-0.5 pl-3.5 pr-2", h < 34 ? "justify-center py-0" : "justify-start py-1.5")}>
                <div className="flex items-center gap-1.5">
                  <span className={clsx("truncate font-medium", h < 34 ? "text-[12.5px]" : "text-[13.5px]")}>{b.title}</span>
                  {h < 48 && <span className="num shrink-0 text-[12px] text-muted">{hm(b.start)}</span>}
                  {b.locked && <Lock size={12} className="shrink-0 text-muted" aria-label="Locked" />}
                  <OutcomeIcon b={b} />
                  {ai && b.fit_label && h >= 34 && <Badge tone={fitTone(b.fit_label)} className="ml-auto">{b.fit_label} fit</Badge>}
                </div>
                {h >= 48 && (
                  <span className="num text-[12px] text-muted">
                    {hm(b.start)}–{hm(b.end)}{b.planned_minutes ? `  ·  planned ${b.planned_minutes} min` : b.kind === "fixed-task" ? "  ·  fixed" : ""}
                  </span>
                )}
              </div>
            </button>
          );
        })}

        {isToday && nowMin > start && nowMin < end && (
          <div className="pointer-events-none absolute left-0 right-0 z-20 flex items-center" style={{ top: top(nowMin) }}>
            <span className="h-2 w-2 -translate-x-1 rounded-full bg-teal" />
            <span className="h-px flex-1 bg-teal" />
          </div>
        )}
      </div>
    </div>
  );
}

/** All days side by side, compact. */
export function HorizonView({
  run, blocks, loads, onPick,
}: { run: PlanRun; blocks: Block[]; loads: { day: number; load: number; planned_minutes: number; heavy: boolean }[]; onPick: (day: number, id: number) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
      {run.days.map((d) => {
        const items = blocks.filter((b) => b.start.slice(0, 10) === d.date);
        const load = loads.find((l) => l.day === d.day);
        const commits = run.commitments.filter((c) => c.start.slice(0, 10) === d.date);
        return (
          <div key={d.date} className={clsx("rounded-card border p-3", d.day === 0 ? "border-line bg-surface" : "border-dashed border-line bg-surface/60")}>
            <div className="flex items-baseline justify-between">
              <h3 className="font-medium">{new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}</h3>
              <Badge tone={d.energy_source === "check-in" ? "teal" : "muted"}>{d.energy_source === "check-in" ? "Checked in" : "Forecast"}</Badge>
            </div>
            {load && (
              <div className="mt-2" title={`${load.planned_minutes} of ${d.free_minutes} free minutes planned`}>
                <div className="flex justify-between text-[12px] text-muted"><span>Load</span><span className="num">{Math.round(load.load * 100)}%</span></div>
                <div className="mt-1 h-1.5 rounded-full bg-beige">
                  <div className={clsx("h-full rounded-full", load.load > 0.85 || (load.heavy && load.load > 0.6) ? "bg-warn" : "bg-teal")} style={{ width: `${Math.min(100, load.load * 100)}%` }} />
                </div>
              </div>
            )}
            <ul className="mt-3 space-y-1.5">
              {[...items.map((b) => ({ t: b.start, b })), ...commits.map((c) => ({ t: c.start, c }))]
                .sort((x, y) => x.t.localeCompare(y.t))
                .map((x, i) =>
                  "b" in x && x.b ? (
                    <li key={`b${x.b.block_id}`}>
                      <button type="button" onClick={() => onPick(d.day, x.b!.block_id)} className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left hover:bg-teal-tint/40">
                        <span className={clsx("h-6 w-1 shrink-0 rounded-full", x.b.kind !== "ai" ? "bg-brown" : x.b.fit_label === "Excellent" ? "bg-teal" : x.b.fit_label === "Good" ? "bg-sage" : "bg-warn")} />
                        <span className="num w-11 shrink-0 text-[12px] text-muted">{hm(x.b.start)}</span>
                        <span className="truncate text-[13px]">{x.b.title}</span>
                      </button>
                    </li>
                  ) : (
                    <li key={`c${i}`} className="flex items-center gap-2 px-1.5 text-[12.5px] text-muted">
                      <span className="h-6 w-1 shrink-0 rounded-full bg-line" />
                      <span className="num w-11 shrink-0">{hm(x.t)}</span>
                      <span className="truncate">{"c" in x && x.c ? x.c.label : ""}</span>
                    </li>
                  ),
                )}
              {!items.length && <li className="text-[13px] text-muted">Nothing planned.</li>}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
