import { Trash2 } from "lucide-react";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { useCheckins, useRefreshAll } from "../api/hooks";
import type { CheckIn } from "../api/types";
import { Badge, Button, Card, EmptyState, EnergySlider, ErrorState, InlineError, PageHeader, SectionTitle, Skeleton, useToast } from "../components/ui";
import { dayName, hm } from "../lib/format";

const MEASURES = [
  { key: "mental", label: "Mental energy", low: "Drained", high: "Sharp" },
  { key: "physical", label: "Physical energy", low: "Exhausted", high: "Energetic" },
  { key: "focus", label: "Focus", low: "Scattered", high: "Locked in" },
  { key: "stress", label: "Stress", low: "Calm", high: "Overwhelmed" },
] as const;
type Key = (typeof MEASURES)[number]["key"];

export function CheckInForm({ compact = false, onSaved }: { compact?: boolean; onSaved?: () => void }) {
  const [v, setV] = useState<Record<Key, number>>({ mental: 6, physical: 5, focus: 6, stress: 4 });
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const refresh = useRefreshAll();
  const toast = useToast();

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/checkins", { method: "POST", body: { ...v, note } });
      await refresh();
      toast({ text: "Check-in saved. Regenerate your plan to use it." });
      setNote("");
      onSaved?.();
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  return (
    <form onSubmit={save} className="space-y-5">
      <div className={compact ? "space-y-4" : "grid gap-x-10 gap-y-6 sm:grid-cols-2"}>
        {MEASURES.map((m) => (
          <EnergySlider key={m.key} id={`ci-${m.key}`} label={m.label} low={m.low} high={m.high} value={v[m.key]} onChange={(x) => setV({ ...v, [m.key]: x })} />
        ))}
      </div>
      {!compact && (
        <div>
          <label htmlFor="ci-note" className="label">Note (optional)</label>
          <input id="ci-note" className="field" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} placeholder="Slept badly, big exam tomorrow…" />
        </div>
      )}
      <InlineError error={error} />
      <Button type="submit" variant="primary" loading={busy} className={compact ? "w-full" : ""}>Save check-in</Button>
    </form>
  );
}

function Trend({ data, k, label }: { data: CheckIn[]; k: Key; label: string }) {
  const rows = data.map((c) => ({ t: c.recorded_at, v: c[k] }));
  const last = rows.at(-1)?.v;
  const avg = rows.reduce((s, r) => s + r.v, 0) / rows.length;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[14px] font-medium">{label}</h3>
        <span className="num text-[13px] text-muted">latest {last} · average {avg.toFixed(1)}</span>
      </div>
      <div className="mt-2 h-28">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 6, right: 6, bottom: 0, left: -28 }}>
            <CartesianGrid stroke="#EFE8DA" vertical={false} />
            <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleDateString(undefined, { day: "numeric", month: "short" })} tick={{ fontSize: 11, fill: "#5B6660" }} axisLine={false} tickLine={false} minTickGap={24} />
            <YAxis domain={[1, 10]} ticks={[1, 5, 10]} tick={{ fontSize: 11, fill: "#5B6660" }} axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ stroke: "#C9BFA9" }}
              contentStyle={{ borderRadius: 10, border: "1px solid #E4DCCB", background: "rgba(255,253,248,.95)", fontSize: 13 }}
              labelFormatter={(t) => `${dayName(String(t))} ${hm(String(t))}`}
              formatter={(val) => [`${val} / 10`, label]}
            />
            <Line type="monotone" dataKey="v" stroke="#1F6F6B" strokeWidth={2} dot={{ r: 3, fill: "#1F6F6B", stroke: "#FFFDF8", strokeWidth: 2 }} activeDot={{ r: 5 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function CheckInPage() {
  const list = useCheckins(60);
  const refresh = useRefreshAll();
  const nav = useNavigate();
  const toast = useToast();
  const recent = [...(list.data ?? [])].reverse();
  const today = new Date().toDateString();
  const doneToday = recent.some((c) => new Date(c.recorded_at).toDateString() === today);

  async function remove(id: number) {
    await api(`/api/checkins/${id}`, { method: "DELETE" });
    await refresh();
    toast({ text: "Check-in deleted" });
  }

  return (
    <>
      <PageHeader
        title="Energy check-in"
        sub="Twenty seconds. The fuzzy engine turns these into your expected capacity for every time slot."
        actions={!doneToday && (
          <Button variant="ghost" onClick={() => { toast({ text: "Skipped. Today uses your recent average instead." }); nav("/schedule"); }}>
            Skip today
          </Button>
        )}
      />
      <Card glass className="mb-8 max-w-3xl">
        <CheckInForm onSaved={() => nav("/schedule")} />
      </Card>

      <SectionTitle>Trends</SectionTitle>
      {list.isLoading ? <Skeleton className="h-40" /> : list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : recent.length < 2 ? (
        <EmptyState title="Not enough check-ins for a trend yet" body="After a few days you'll see how your energy moves, and the planner will start learning your daily rhythm." />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {MEASURES.map((m) => <Trend key={m.key} data={recent.slice(-21)} k={m.key} label={m.label} />)}
          </div>
          <p className="hint mt-2">Last {Math.min(21, recent.length)} check-ins, each on the same 1–10 scale.</p>
          <SectionTitle><span className="mt-8 block">Recent check-ins</span></SectionTitle>
          <Card className="overflow-hidden p-0">
            <table className="w-full text-[14px]">
              <caption className="sr-only">Recent check-ins</caption>
              <thead className="bg-beige/50 text-left text-[12.5px] text-muted">
                <tr><th className="px-4 py-2 font-medium">When</th><th className="px-2 font-medium">Mental</th><th className="px-2 font-medium">Physical</th><th className="px-2 font-medium">Focus</th><th className="px-2 font-medium">Stress</th><th className="px-2 font-medium">Note</th><th /></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {[...recent].reverse().slice(0, 10).map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-2">{dayName(c.recorded_at)} {hm(c.recorded_at)}</td>
                    <td className="num px-2">{c.mental}</td><td className="num px-2">{c.physical}</td><td className="num px-2">{c.focus}</td><td className="num px-2">{c.stress}</td>
                    <td className="max-w-[16rem] truncate px-2 text-muted">{c.note}{c.source !== "user" && <Badge tone="brown" className="ml-1">Demo</Badge>}</td>
                    <td className="px-2 text-right">
                      <button type="button" onClick={() => remove(c.id)} className="rounded-md p-1 text-muted hover:bg-danger-tint hover:text-danger" aria-label="Delete check-in"><Trash2 size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </>
  );
}
