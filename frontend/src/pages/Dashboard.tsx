import clsx from "clsx";
import { CheckCircle2, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useCheckins, usePlan, useRefreshAll, useTasks } from "../api/hooks";
import type { User } from "../api/types";
import { TaskForm } from "../components/TaskForm";
import { Badge, Button, Card, EmptyState, ErrorState, fitTone, Modal, PageHeader, SectionTitle, Skeleton, useToast } from "../components/ui";
import { greeting, hm, minutes, relDeadline } from "../lib/format";
import { CheckInForm } from "./CheckIn";

export function Dashboard({ user }: { user: User }) {
  const plan = usePlan();
  const pending = useTasks("status=pending&sort=deadline");
  const checkins = useCheckins(1);
  const [adding, setAdding] = useState(false);
  const refresh = useRefreshAll();
  const toast = useToast();
  const [loadingDemo, setLoadingDemo] = useState(false);

  const now = new Date();
  const todayStr = now.toDateString();
  const run = plan.data;
  const active = run?.plans.find((p) => p.version_id === run.active_version_id);
  const today = (active?.blocks ?? []).filter((b) => new Date(b.start).toDateString() === todayStr);
  const todayAi = today.filter((b) => b.kind !== "fixed-task");
  const next = todayAi.find((b) => !b.outcome && new Date(b.end) > now);
  const done = todayAi.filter((b) => b.outcome && b.outcome.status !== "skipped").length;
  const latest = checkins.data?.[0];
  const checkedInToday = latest && new Date(latest.recorded_at).toDateString() === todayStr;
  const deadlines = (pending.data ?? []).filter((t) => t.deadline && !t.recur_days).slice(0, 5);

  async function loadDemo() {
    setLoadingDemo(true);
    await api("/api/data/demo", { method: "POST" });
    await refresh();
    setLoadingDemo(false);
    toast({ text: "Demo week loaded. Every demo record is labelled and can be cleared in Settings." });
  }

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${user.display_name}`}
        sub={now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
        actions={<>
          <Button onClick={() => setAdding(true)}><Plus size={16} aria-hidden /> Add task</Button>
          <Link to="/schedule"><Button variant="primary">Open schedule</Button></Link>
        </>}
      />

      {pending.data && pending.data.length === 0 && !run && (
        <div className="mb-6">
          <EmptyState
            title="Nothing to plan yet"
            body="Add your own tasks, or load a demo student week to see how the planner works. Demo records are labelled and easy to remove."
            action={<div className="flex gap-2"><Button variant="primary" onClick={() => setAdding(true)}>Add a task</Button><Button onClick={loadDemo} loading={loadingDemo}>Load demo week</Button></div>}
          />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-6">
          {plan.isLoading ? <Skeleton className="h-40" /> : plan.error ? <ErrorState error={plan.error} onRetry={() => plan.refetch()} /> : (
            <Card glass className="p-6">
              {next ? (
                <>
                  <p className="text-[13px] text-muted">{new Date(next.start) <= now ? "Now" : `Next, at ${hm(next.start)}`}</p>
                  <h2 className="mt-1 text-[28px] font-light leading-tight tracking-[-0.01em]">{next.title}</h2>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="num text-[14px] text-muted">{hm(next.start)}–{hm(next.end)}</span>
                    {next.fit_label && <Badge tone={fitTone(next.fit_label)}>{next.fit_label} energy fit</Badge>}
                    {next.deadline && <Badge tone="brown">Due {relDeadline(next.deadline)}</Badge>}
                  </div>
                  {next.verdict && <p className="mt-4 max-w-prose text-[15px] leading-relaxed text-ink/90">{next.verdict}</p>}
                  <Link to="/schedule" className="mt-4 inline-block text-[14px] font-medium text-teal hover:underline">See the full reasoning</Link>
                </>
              ) : run ? (
                <>
                  <h2 className="text-[22px] font-light">{todayAi.length ? "That's everything planned for today." : "Nothing planned for the rest of today."}</h2>
                  <p className="mt-2 text-muted">{todayAi.length ? "Record how your blocks went so the planner learns your pace." : "Regenerate to plan from now, or look ahead in the schedule."}</p>
                </>
              ) : (
                <>
                  <h2 className="text-[22px] font-light">No plan yet</h2>
                  <p className="mt-2 text-muted">Check in, then let the planner place your tasks where your energy fits.</p>
                  <Link to="/schedule"><Button variant="primary" className="mt-4">Plan my days</Button></Link>
                </>
              )}
            </Card>
          )}

          <Card>
            <SectionTitle action={<Link to="/schedule" className="text-[13px] font-medium text-teal hover:underline">Open schedule</Link>}>Today</SectionTitle>
            {!today.length ? <p className="text-muted">No blocks today.</p> : (
              <ol className="space-y-1">
                {today.map((b) => (
                  <li key={b.block_id} className={clsx("flex items-center gap-3 rounded-lg px-2 py-2", b === next && "bg-teal-tint/50")}>
                    <span className="num w-24 shrink-0 text-[13px] text-muted">{hm(b.start)}–{hm(b.end)}</span>
                    <span className={clsx("h-2 w-2 shrink-0 rounded-full", b.kind !== "ai" ? "bg-brown" : b.fit_label === "Excellent" ? "bg-teal" : b.fit_label === "Good" ? "bg-sage" : "bg-warn")} aria-hidden />
                    <span className={clsx("flex-1 truncate", b.outcome && "text-muted line-through")}>{b.title}</span>
                    {b.outcome && <CheckCircle2 size={16} className="text-teal" aria-label={`Recorded: ${b.outcome.status}`} />}
                    {b.planned_minutes && <span className="num text-[12.5px] text-muted">{minutes(b.planned_minutes)}</span>}
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {active && active.day_load.length > 1 && (
            <Card>
              <SectionTitle>Coming days</SectionTitle>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                {active.day_load.map((d) => {
                  const info = run!.days[d.day];
                  return (
                    <div key={d.day}>
                      <div className="text-[13px] font-medium">{d.day === 0 ? "Today" : new Date(`${info.date}T12:00:00`).toLocaleDateString(undefined, { weekday: "long" })}</div>
                      <div className="num text-[12.5px] text-muted">{minutes(d.planned_minutes)} planned</div>
                      <div className="mt-1.5 h-1.5 rounded-full bg-beige"><div className={clsx("h-full rounded-full", d.load > 0.85 ? "bg-warn" : "bg-teal")} style={{ width: `${Math.min(100, d.load * 100)}%` }} /></div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <SectionTitle action={checkedInToday && <Link to="/check-in" className="text-[13px] font-medium text-teal hover:underline">Update</Link>}>Your energy</SectionTitle>
            {checkedInToday && latest ? (
              <>
                <dl className="grid grid-cols-2 gap-3">
                  {(["mental", "physical", "focus", "stress"] as const).map((k) => (
                    <div key={k} className="rounded-lg bg-canvas px-3 py-2">
                      <dt className="text-[12.5px] capitalize text-muted">{k}</dt>
                      <dd className="num text-[22px] font-light">{latest[k]}<span className="text-[13px] text-muted">/10</span></dd>
                    </div>
                  ))}
                </dl>
                <p className="hint mt-2">Checked in at {hm(latest.recorded_at)}.</p>
              </>
            ) : (
              <>
                <p className="mb-4 text-[13.5px] text-muted">No check-in today. Twenty seconds makes today's plan fit you better.</p>
                <CheckInForm compact />
              </>
            )}
          </Card>

          <Card>
            <SectionTitle>Today's progress</SectionTitle>
            {todayAi.length ? (
              <>
                <div className="num text-[28px] font-light">{done}<span className="text-[15px] text-muted"> of {todayAi.length} blocks done</span></div>
                <div className="mt-2 h-2 rounded-full bg-beige"><div className="h-full rounded-full bg-teal" style={{ width: `${(done / todayAi.length) * 100}%` }} /></div>
              </>
            ) : <p className="text-muted">Nothing planned today yet.</p>}
            <p className="hint mt-3">{(pending.data ?? []).filter((t) => !t.recur_days).length} tasks still to do in total.</p>
          </Card>

          <Card>
            <SectionTitle action={<Link to="/tasks" className="text-[13px] font-medium text-teal hover:underline">All tasks</Link>}>Upcoming deadlines</SectionTitle>
            {!deadlines.length ? <p className="text-muted">No deadlines coming up.</p> : (
              <ul className="space-y-2">
                {deadlines.map((t) => {
                  const soon = new Date(t.deadline!).getTime() - Date.now() < 86400000;
                  return (
                    <li key={t.id} className="flex items-baseline justify-between gap-3">
                      <span className="truncate text-[14px]">{t.title}</span>
                      <span className={clsx("num shrink-0 text-[13px]", soon ? "font-medium text-danger" : "text-muted")}>{relDeadline(t.deadline!)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Modal open={adding} onClose={() => setAdding(false)} title="Add task" side width="max-w-xl">
        {adding && <TaskForm onDone={() => setAdding(false)} />}
      </Modal>
    </>
  );
}
