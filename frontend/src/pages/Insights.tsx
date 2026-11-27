import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { Insights } from "../api/types";
import { Card, EmptyState, ErrorState, PageHeader, SectionTitle, Segmented, Skeleton } from "../components/ui";

const TEAL = "#1F6F6B";
const GREY = "#8C948F";
const AXIS = { fontSize: 11, fill: "#5B6660" };
const TIP = { borderRadius: 10, border: "1px solid #E4DCCB", background: "rgba(255,253,248,.96)", fontSize: 13 };

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card p-4">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="num mt-1 text-[28px] font-light leading-none">{value}</div>
      <div className="mt-1.5 text-[12.5px] text-muted">{sub}</div>
    </div>
  );
}

function NotEnough({ need, have, what }: { need: number; have: number; what: string }) {
  return (
    <div className="flex h-40 items-center justify-center rounded-lg bg-canvas px-6 text-center text-[13.5px] text-muted">
      Needs at least {need} {what}; you have {have}. Record outcomes on planned blocks in the AI Schedule.
    </div>
  );
}

export function InsightsPage() {
  const [source, setSource] = useState<"all" | "user" | "demo">("all");
  const q = useQuery({ queryKey: ["insights", source], queryFn: () => api<Insights>(`/api/insights?source=${source}`) });
  const d = q.data;

  return (
    <>
      <PageHeader
        title="Insights"
        sub="Computed only from what you have recorded. Every chart shows how many records it uses."
        actions={<Segmented label="Data source" value={source} onChange={setSource} options={[{ value: "all", label: "All data" }, { value: "user", label: "Mine" }, { value: "demo", label: "Demo" }]} />}
      />
      {q.isLoading ? <Skeleton className="h-96" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !d ? null : d.outcomes.n === 0 && d.checkins === 0 ? (
        <EmptyState
          title={source === "demo" ? "No demo data loaded" : "Nothing recorded yet"}
          body="Insights appear once you record how planned blocks went (Done, Partly, Skipped) and do a few check-ins."
          action={<Link to="/schedule" className="font-medium text-teal hover:underline">Open the AI Schedule</Link>}
        />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Completion rate" value={d.outcomes.completion_rate == null ? "n/a" : `${d.outcomes.completion_rate}%`}
              sub={`${d.outcomes.done} done, ${d.outcomes.partial} partly, ${d.outcomes.skipped} skipped`} />
            <Tile label="Your estimates are off by" value={d.estimate_error_min == null ? "n/a" : `${Math.round(d.estimate_error_min)} min`}
              sub={d.planner_error_min == null ? "Planner comparison needs outcomes on planned blocks" : `Planner's prediction: ${Math.round(d.planner_error_min)} min`} />
            <Tile label="Deadlines met" value={d.deadlines.on_time + d.deadlines.late ? `${d.deadlines.on_time} of ${d.deadlines.on_time + d.deadlines.late}` : "n/a"}
              sub={`${d.deadlines.overdue_open} overdue and open, ${d.deadlines.upcoming} upcoming`} />
            <Tile label="Plan usefulness" value={d.ratings.mean == null ? "n/a" : `${d.ratings.mean} / 5`} sub={`${d.ratings.n} rating${d.ratings.n === 1 ? "" : "s"} across ${d.plans_generated} plans`} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <SectionTitle>Your estimate versus what it took</SectionTitle>
              {!d.categories.length ? <NotEnough need={1} have={0} what="finished tasks with minutes" /> : <Dumbbell rows={d.categories} />}
            </Card>

            <Card>
              <SectionTitle>Is the planner learning?</SectionTitle>
              {d.accuracy.length < 3 ? <NotEnough need={3} have={d.accuracy.length} what="finished planned blocks" /> : (
                <>
                  <p className="mb-2 text-[13px] text-muted">Average error over the last 5 finished blocks, as a share of the real duration. Lower is better.</p>
                  <div className="h-56">
                    <ResponsiveContainer>
                      <LineChart data={d.accuracy} margin={{ top: 6, right: 12, left: -12, bottom: 0 }}>
                        <CartesianGrid stroke="#EFE8DA" vertical={false} />
                        <XAxis dataKey="i" tick={AXIS} axisLine={false} tickLine={false} />
                        <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="%" />
                        <Tooltip contentStyle={TIP} labelFormatter={(i) => `Block ${i}`} formatter={(v, n) => [`${v}%`, n]} />
                        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
                        <Line name="Your own estimate" dataKey="estimate_rolling" stroke={GREY} strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                        <Line name="Planner's prediction" dataKey="planner_rolling" stroke={TEAL} strokeWidth={2} dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </>
              )}
            </Card>

            <Card>
              <SectionTitle>Do well-fitting blocks get done more?</SectionTitle>
              {!d.by_fit.length ? <NotEnough need={1} have={0} what="outcomes on planned blocks" /> : (
                <BarRates data={d.by_fit.map((x) => ({ name: x.label, rate: x.done_rate, n: x.n }))} xLabel="Predicted chance the block would happen" />
              )}
            </Card>

            <Card>
              <SectionTitle>Completion by time of day</SectionTitle>
              {!d.by_hour.length ? <NotEnough need={1} have={0} what="outcomes on planned blocks" /> : (
                <BarRates data={d.by_hour.map((x) => ({ name: `${String(x.hour).padStart(2, "0")}:00`, rate: x.done_rate, n: x.n }))} xLabel="Block start" />
              )}
            </Card>

            <Card>
              <SectionTitle>Mental energy through the day</SectionTitle>
              {!d.energy_by_time.length ? <NotEnough need={1} have={0} what="check-ins" /> : (
                <>
                  <div className="h-52">
                    <ResponsiveContainer>
                      <BarChart data={d.energy_by_time} margin={{ top: 18, right: 8, left: -18, bottom: 0 }}>
                        <CartesianGrid stroke="#EFE8DA" vertical={false} />
                        <XAxis dataKey="band" tick={AXIS} axisLine={false} tickLine={false} />
                        <YAxis domain={[0, 10]} ticks={[0, 2, 4, 6, 8, 10]} tick={AXIS} axisLine={false} tickLine={false} />
                        <Tooltip contentStyle={TIP} formatter={(v, _n, p) => [`${v} / 10 from ${p.payload.n} check-ins`, "Mental energy"]} />
                        <Bar dataKey="mental" fill={TEAL} radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false}>
                          <LabelList dataKey="mental" position="top" style={{ fontSize: 11, fill: "#1F2A26" }} />
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="hint mt-1">Average of {d.checkins} check-ins, grouped by when you checked in.</p>
                </>
              )}
            </Card>

            <Card>
              <SectionTitle>Outcomes by category</SectionTitle>
              {!d.status_by_category.length ? <NotEnough need={1} have={0} what="outcomes" /> : (
                <table className="w-full text-[14px]">
                  <thead className="text-left text-[12.5px] text-muted"><tr><th className="py-1 font-medium">Category</th><th className="font-medium">Done</th><th className="font-medium">Partly</th><th className="font-medium">Skipped</th><th className="font-medium">Done rate</th></tr></thead>
                  <tbody className="divide-y divide-line">
                    {d.status_by_category.map((c) => {
                      const total = c.done + c.partial + c.skipped;
                      return (
                        <tr key={c.category}>
                          <td className="py-1.5">{c.category}</td><td className="num">{c.done}</td><td className="num">{c.partial}</td><td className="num">{c.skipped}</td>
                          <td className="num">{total ? Math.round((100 * c.done) / total) : 0}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </Card>

            <Calibration includeDemo={source !== "user"} />
          </div>
        </div>
      )}
    </>
  );
}

interface PilotCalibration {
  n: number; brier: number | null; enough_data: boolean; note: string;
  bands: { band: string; n: number; predicted: number | null; observed: number | null }[];
}

/** Are the planner's "chance it happens" numbers honest? Predicted vs what you actually did. */
function Calibration({ includeDemo }: { includeDemo: boolean }) {
  const q = useQuery({
    queryKey: ["pilot-calibration", includeDemo],
    queryFn: () => api<{ calibration: PilotCalibration }>(`/api/data/pilot?include_demo=${includeDemo}`),
  });
  const c = q.data?.calibration;
  return (
    <Card>
      <SectionTitle>Are the predictions honest?</SectionTitle>
      {!c ? <Skeleton className="h-32" /> : c.n === 0 ? <NotEnough need={30} have={0} what="outcomes on blocks with a prediction" /> : (
        <>
          <table className="w-full text-[14px]">
            <caption className="sr-only">Predicted chance a block happens against how often it did</caption>
            <thead className="text-left text-[12.5px] text-muted"><tr><th className="py-1 font-medium">Predicted</th><th className="font-medium">Blocks</th><th className="font-medium">Average prediction</th><th className="font-medium">Actually happened</th></tr></thead>
            <tbody className="divide-y divide-line">
              {c.bands.map((b) => (
                <tr key={b.band}>
                  <td className="num py-1.5">{b.band}</td><td className="num">{b.n}</td>
                  <td className="num">{b.predicted == null ? "–" : `${Math.round(b.predicted * 100)}%`}</td>
                  <td className="num">{b.observed == null ? "–" : `${Math.round(b.observed * 100)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint mt-2">
            {c.n} outcome{c.n === 1 ? "" : "s"}{c.brier != null ? `, Brier score ${c.brier.toFixed(3)} (0 is perfect, 0.25 is a coin flip)` : ""}.{" "}
            {c.enough_data ? "Well-calibrated predictions have the last two columns close together." : c.note}
          </p>
        </>
      )}
    </Card>
  );
}

function BarRates({ data, xLabel }: { data: { name: string; rate: number; n: number }[]; xLabel: string }) {
  return (
    <>
      <div className="h-52">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 18, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="#EFE8DA" vertical={false} />
            <XAxis dataKey="name" tick={AXIS} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} unit="%" tick={AXIS} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={TIP} formatter={(v, _n, p) => [`${v}% of ${p.payload.n} blocks`, "Done"]} />
            <Bar dataKey="rate" fill={TEAL} radius={[4, 4, 0, 0]} maxBarSize={40} isAnimationActive={false}>
              <LabelList dataKey="n" position="top" formatter={(n: number) => `n=${n}`} style={{ fontSize: 11, fill: "#5B6660" }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="hint mt-1">Share of blocks marked Done, by {xLabel.toLowerCase()}. Small groups (low n) can swing a lot.</p>
    </>
  );
}

/** Estimate (hollow ring) against actual (filled dot) per category, on one shared minutes axis. */
function Dumbbell({ rows }: { rows: Insights["categories"] }) {
  const max = Math.max(...rows.flatMap((r) => [r.estimate, r.actual])) * 1.1;
  const x = (v: number) => `${(v / max) * 100}%`;
  return (
    <>
      <div className="mb-3 flex gap-4 text-[12.5px] text-muted">
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-[#8C948F] bg-surface" />Your estimate</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full bg-teal" />Actual average</span>
      </div>
      <ul className="space-y-3">
        {rows.map((r) => (
          <li key={r.category}>
            <div className="flex justify-between text-[13.5px]">
              <span>{r.category} <span className="text-muted">n={r.n}</span></span>
              <span className="num">{Math.round(r.estimate)} → {Math.round(r.actual)} min <span className={r.overrun_pct > 0 ? "text-warn" : "text-teal"}>({r.overrun_pct > 0 ? "+" : ""}{r.overrun_pct}%)</span></span>
            </div>
            <div className="relative mt-1.5 h-4" role="img" aria-label={`${r.category}: estimated ${Math.round(r.estimate)} minutes, actually ${Math.round(r.actual)}`}>
              <div className="absolute top-1/2 h-px w-full bg-line" />
              <div className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-[#C9BFA9]" style={{ left: x(Math.min(r.estimate, r.actual)), width: `${(Math.abs(r.actual - r.estimate) / max) * 100}%` }} />
              <span className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#8C948F] bg-surface" style={{ left: x(r.estimate) }} />
              <span className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-teal ring-2 ring-surface" style={{ left: x(r.actual) }} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
