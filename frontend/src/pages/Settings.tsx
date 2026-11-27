import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { useCounts, useModels, usePrefs, useRefreshAll } from "../api/hooks";
import type { ModelsInfo, Preferences } from "../api/types";
import { Badge, Button, Card, ErrorState, Field, InlineError, Modal, PageHeader, SectionTitle, Skeleton, useToast } from "../components/ui";

const QUANTILE_HINTS: Record<string, string> = {
  "0.5": "Fits the most work; blocks run over about half the time.",
  "0.65": "Recommended. In testing it finished more tasks than P80 without clearly more overruns.",
  "0.8": "Most padding; fewest overruns, fewer tasks fit.",
};

const SIM_HINTS: Record<string, string> = {
  quick: "Fastest; estimates vary by a few percent.",
  standard: "Recommended balance of speed and precision.",
  research: "Most precise; a little slower.",
  adaptive: "Adds runs until the estimate is precise enough.",
};

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" sub="Your working hours, what the planner has learned, and your data." />
      <div className="grid gap-6 lg:grid-cols-2">
        <PrefsForm />
        <Learned />
        <DataCard />
        <PasswordCard />
      </div>
    </>
  );
}

function PrefsForm() {
  const prefs = usePrefs();
  const [f, setF] = useState<Preferences | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const refresh = useRefreshAll();
  useEffect(() => { if (prefs.data) setF(prefs.data); }, [prefs.data]);
  if (prefs.error) return <ErrorState error={prefs.error} onRetry={() => prefs.refetch()} />;
  if (!f) return <Skeleton className="h-80" />;
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setF({ ...f, [k]: v });

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api("/api/preferences", { method: "PUT", body: f });
      await prefs.refetch(); await refresh();
      toast({ text: "Settings saved. They apply the next time you generate a plan." });
    } catch (err) { setError(err); } finally { setBusy(false); }
  }
  return (
    <Card>
      <SectionTitle>Planning</SectionTitle>
      <form onSubmit={save} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Day starts" htmlFor="p-ds"><input id="p-ds" type="time" className="field" value={f.day_start} onChange={(e) => set("day_start", e.target.value)} /></Field>
          <Field label="Day ends" htmlFor="p-de"><input id="p-de" type="time" className="field" value={f.day_end} onChange={(e) => set("day_end", e.target.value)} /></Field>
          <Field label="No work after" htmlFor="p-nw" hint="Blocks ending later get a small penalty (A7)."><input id="p-nw" type="time" className="field" value={f.no_work_after} onChange={(e) => set("no_work_after", e.target.value)} /></Field>
          <Field label="Longest focus run (min)" htmlFor="p-mf" hint="Longer runs without a break are penalised (A1)."><input id="p-mf" type="number" min={30} max={240} step={15} className="field num" value={f.max_focus_block} onChange={(e) => set("max_focus_block", Number(e.target.value))} /></Field>
          <Field label="Days to plan ahead" htmlFor="p-h">
            <select id="p-h" className="field" value={f.horizon_days} onChange={(e) => set("horizon_days", Number(e.target.value))}>
              {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </Field>
          <Field label="Default style" htmlFor="p-p">
            <select id="p-p" className="field" value={f.ga_preset} onChange={(e) => set("ga_preset", e.target.value as Preferences["ga_preset"])}>
              <option value="balanced">Balanced: most tasks done</option><option value="deadline">Safer deadlines</option><option value="gentle">Lighter day</option>
            </select>
          </Field>
          <Field label={`Fewer changes when replanning: ${Math.round(f.replan_stability * 100)}%`} htmlFor="p-st"
            hint="When you regenerate, how hard the planner tries not to move blocks you already have. 0% replans freely.">
            <input id="p-st" type="range" min={0} max={1} step={0.05} className="w-full accent-teal" value={f.replan_stability}
              onChange={(e) => set("replan_stability", Number(e.target.value))} />
          </Field>
        </div>
        <details className="rounded-card border border-line/80 px-3 py-2">
          <summary className="cursor-pointer text-[13.5px] font-medium text-muted">Advanced</summary>
          <div className="mt-3 grid grid-cols-2 gap-3">
          <Field label="Optimiser" htmlFor="p-o" hint={f.optimizer === "cpsat" ? "Adds up to 8 s per plan." : f.optimizer === "ga" ? "The original search, kept for comparison." : "Recommended. About 1 s per style."}>
            <select id="p-o" className="field" value={f.optimizer} onChange={(e) => set("optimizer", e.target.value as Preferences["optimizer"])}>
              <option value="hybrid">GA + local search</option>
              <option value="ga">Genetic algorithm only</option>
              <option value="cpsat">Thorough: + CP-SAT solver</option>
            </select>
          </Field>
          <Field label="Risk simulation" htmlFor="p-sim" hint={SIM_HINTS[f.simulation ?? "standard"]}>
            <select id="p-sim" className="field" value={f.simulation ?? "standard"} onChange={(e) => set("simulation", e.target.value as Preferences["simulation"])}>
              <option value="quick">Quick (30 runs)</option>
              <option value="standard">Standard (100 runs)</option>
              <option value="research">Research (300 runs)</option>
              <option value="adaptive">Adaptive (30–300, stops when precise)</option>
            </select>
          </Field>
          <Field label="Block length" htmlFor="p-q" hint={QUANTILE_HINTS[String(f.block_quantile ?? 0.65)] ?? ""}>
            <select id="p-q" className="field" value={f.block_quantile ?? 0.65} onChange={(e) => set("block_quantile", Number(e.target.value))}>
              <option value={0.5}>Tight: median time (P50)</option>
              <option value={0.65}>Balanced (P65)</option>
              <option value={0.8}>Cautious (P80)</option>
            </select>
          </Field>
          </div>
          <p className="hint mt-2">Each plan is replayed this many times with realistic durations to estimate what could go wrong.</p>
        </details>
        <InlineError error={error} />
        <Button type="submit" variant="primary" loading={busy}>Save settings</Button>
      </form>
    </Card>
  );
}

function Learned() {
  const m = useModels();
  if (m.error) return <ErrorState error={m.error} onRetry={() => m.refetch()} />;
  if (!m.data) return <Skeleton className="h-80" />;
  const d = m.data;
  const cats = Object.entries(d.durations.categories);
  return (
    <Card>
      <SectionTitle action={<Badge tone={d.mode === "personalized" ? "teal" : "muted"}>{d.mode === "personalized" ? "Personalized" : "Cold start"}</Badge>}>What the planner has learned</SectionTitle>
      <p className="text-[13.5px] text-muted">
        Based on {d.finished_with_minutes} finished tasks with recorded minutes.
        {d.durations.version === "v2"
          ? " Each category starts from your overall pace and moves toward its own records as they add up, so one unusual task can't swing it."
          : " A category with fewer than 3 records of its own uses the estimate pooled across all categories."}
      </p>
      <table className="mt-3 w-full text-[13.5px]">
        <caption className="sr-only">Learned duration estimates by category</caption>
        <thead className="text-left text-[12.5px] text-muted"><tr><th className="py-1 font-medium">Category</th><th className="font-medium">Typical overrun</th><th className="font-medium">Records</th><th className="font-medium">Source</th></tr></thead>
        <tbody className="divide-y divide-line">
          {cats.map(([c, v]) => (
            <tr key={c}>
              <td className="py-1.5">{c}</td>
              <td className="num">{v.ratio >= 1 ? "+" : ""}{Math.round((v.ratio - 1) * 100)}%</td>
              <td className="num">{v.own_n}</td>
              <td>{v.source === "learned" ? <Badge tone="teal">Learned</Badge> : v.source === "shrunk" ? <Badge title="Blends this category's records with your overall pace">Blended</Badge> : v.source === "pooled" ? <Badge>Pooled</Badge> : <Badge>Default</Badge>}</td>
            </tr>
          ))}
          <tr>
            <td className="py-1.5 text-muted">Everything else</td>
            <td className="num">+{Math.round((d.durations.pooled.ratio - 1) * 100)}%</td>
            <td className="num">{d.durations.pooled.n}</td>
            <td><Badge>{d.durations.pooled.source === "pooled" ? "Pooled" : "Default"}</Badge></td>
          </tr>
        </tbody>
      </table>
      <CompletionSummary c={d.completion} />
      <h3 className="mt-5 text-[13px] font-semibold text-muted">Daily energy rhythm {d.profile.learned ? "(learned)" : "(default profile)"}</h3>
      <div className="mt-2 grid grid-cols-7 gap-1 text-center">
        {d.profile.bands.map((b, i) => (
          <div key={b} title={`${d.profile.counts[i]} check-ins in this band`}>
            <div className="mx-auto flex h-14 w-full items-end justify-center rounded bg-canvas">
              <div className="w-3/5 rounded-t bg-teal" style={{ height: `${Math.max(6, ((d.profile.mental[i] + 2) / 3.5) * 100)}%`, opacity: 0.85 }} />
            </div>
            <div className="mt-1 text-[11px] leading-tight text-muted">{b}</div>
            <div className="num text-[11.5px]">{d.profile.mental[i] > 0 ? "+" : ""}{d.profile.mental[i].toFixed(1)}</div>
          </div>
        ))}
      </div>
      <p className="hint mt-2">Mental-energy offset for each part of the day, added to your check-in.</p>
    </Card>
  );
}

const FACTOR_WORDS: Record<string, string> = {
  mental_shortfall: "Each point a block needs above your expected mental energy",
  physical_shortfall: "Each point above your expected physical energy",
  focus: "Higher focus that day (per 2 points)",
  stress: "Higher stress that day (per 2 points)",
  log_duration: "Longer blocks (per doubling)",
};

function CompletionSummary({ c }: { c: ModelsInfo["completion"] }) {
  const rows = Object.entries(c.coefficients).filter(([k]) => k !== "intercept");
  return (
    <>
      <h3 className="mt-5 text-[13px] font-semibold text-muted">Will a planned block happen?</h3>
      <p className="mt-1 text-[13.5px] text-muted">
        {c.n === 0
          ? "No outcomes yet, so the planner assumes about 8 in 10 blocks happen, a little less when a block asks for more energy than you are likely to have."
          : `Learned from ${c.n} recorded outcome${c.n === 1 ? "" : "s"} (${c.with_context} with the context they were planned in). A typical block: about ${Math.round(c.baseline_p * 100)}% likely.`}
      </p>
      <table className="mt-2 w-full text-[13px]">
        <caption className="sr-only">What changes the chance that a block happens</caption>
        <thead className="text-left text-[12.5px] text-muted"><tr><th className="py-1 font-medium">Factor</th><th className="font-medium">Effect (log-odds)</th><th className="font-medium">Certainty</th></tr></thead>
        <tbody className="divide-y divide-line">
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td className="py-1.5">{FACTOR_WORDS[k] ?? k.replace("category: ", "Your record with ") }</td>
              <td className="num">{v.mean > 0 ? "+" : ""}{v.mean.toFixed(2)}</td>
              <td>{Math.abs(v.mean) > 2 * v.sd ? <Badge tone="teal">Clear</Badge> : <Badge>Uncertain</Badge>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint mt-1">Negative makes a block less likely to happen. "Clear" means the effect is more than two standard deviations from zero.</p>
    </>
  );
}

function DataCard() {
  const counts = useCounts();
  const refresh = useRefreshAll();
  const toast = useToast();
  const [confirm, setConfirm] = useState<"demo" | "user" | null>(null);
  const [busy, setBusy] = useState(false);
  const c = counts.data ?? {};
  const total = (src: string) => Object.values(c).reduce((s, x) => s + (x[src] ?? 0), 0);

  async function loadDemo() {
    setBusy(true);
    await api("/api/data/demo", { method: "POST" });
    await refresh(); setBusy(false);
    toast({ text: "Demo week loaded" });
  }
  async function clear(src: "demo" | "user") {
    setBusy(true);
    await api(`/api/data?source=${src}`, { method: "DELETE" });
    await refresh(); setBusy(false); setConfirm(null);
    toast({ text: src === "demo" ? "Demo data deleted" : "Your records deleted" });
  }
  async function exportPilot() {
    const data = await api<object>("/api/data/pilot");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `pilot-outcomes-${new Date().toISOString().slice(0, 10)}.json` });
    a.click();
    URL.revokeObjectURL(url);
  }
  async function exportAll() {
    const data = await api<object>("/api/data/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `planner-export-${new Date().toISOString().slice(0, 10)}.json` });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card>
      <SectionTitle>Your data</SectionTitle>
      <p className="text-[13.5px] text-muted">Everything is stored in one file on this computer: <code className="rounded bg-beige px-1">backend/data/planner.db</code>. Nothing is sent anywhere.</p>
      <table className="mt-3 w-full text-[13.5px]">
        <thead className="text-left text-[12.5px] text-muted"><tr><th className="py-1 font-medium">Records</th><th className="font-medium">Yours</th><th className="font-medium">Demo</th></tr></thead>
        <tbody className="divide-y divide-line">
          {([["tasks", "Tasks"], ["commitments", "Busy times"], ["checkins", "Check-ins"], ["outcomes", "Recorded outcomes"]] as const).map(([k, name]) => (
            <tr key={k}><td className="py-1.5">{name}</td><td className="num">{c[k]?.user ?? 0}</td><td className="num">{c[k]?.demo ?? 0}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button onClick={loadDemo} loading={busy}>{total("demo") ? "Reload demo week" : "Load demo week"}</Button>
        <Button onClick={() => setConfirm("demo")} disabled={!total("demo")}>Delete demo data</Button>
        <Button onClick={exportAll}>Export everything (JSON)</Button>
        <Button onClick={exportPilot} title="Outcomes and predictions only: no titles, notes or names">Anonymous pilot export</Button>
        <Button variant="danger" onClick={() => setConfirm("user")} disabled={!total("user")}>Delete my records</Button>
      </div>
      <Modal open={confirm !== null} onClose={() => setConfirm(null)} title={confirm === "demo" ? "Delete demo data?" : "Delete your records?"}>
        <p>
          This permanently deletes {total(confirm ?? "demo")} {confirm === "demo" ? "demo" : "of your"} records (tasks, busy times, check-ins and outcomes)
          {confirm === "user" ? ", and what the planner learned from them" : ""}. It cannot be undone.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setConfirm(null)}>Keep them</Button>
          <Button variant="danger" loading={busy} onClick={() => clear(confirm!)}>Delete {total(confirm ?? "demo")} records</Button>
        </div>
      </Modal>
    </Card>
  );
}

function PasswordCard() {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<unknown>(null);
  const toast = useToast();
  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/api/auth/password", { method: "POST", body: { current_password: cur, new_password: next } });
      setCur(""); setNext("");
      toast({ text: "Password changed" });
    } catch (err) { setError(err); }
  }
  return (
    <Card>
      <SectionTitle>Password</SectionTitle>
      <form onSubmit={save} className="space-y-3">
        <Field label="Current password" htmlFor="pw-c"><input id="pw-c" type="password" autoComplete="current-password" className="field" value={cur} onChange={(e) => setCur(e.target.value)} required /></Field>
        <Field label="New password" htmlFor="pw-n" hint="At least 8 characters."><input id="pw-n" type="password" autoComplete="new-password" minLength={8} className="field" value={next} onChange={(e) => setNext(e.target.value)} required /></Field>
        <InlineError error={error} />
        <Button type="submit">Change password</Button>
      </form>
    </Card>
  );
}
