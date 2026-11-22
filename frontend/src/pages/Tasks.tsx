import clsx from "clsx";
import { Check, Pencil, Plus, Repeat, Trash2 } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useCommitments, useRefreshAll, useSaveTask, useTasks } from "../api/hooks";
import { PRIORITY_NAMES, type Task, type TaskBody } from "../api/types";
import { TaskForm } from "../components/TaskForm";
import {
  Badge, Button, Card, EmptyState, ErrorState, Field, InlineError, Modal, PageHeader, priorityTone, Skeleton, Tabs, useToast,
} from "../components/ui";
import { dayName, hm, minutes, relDeadline, repeatText, toLocalIso } from "../lib/format";

export function TasksPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as "tasks" | "busy") ?? "tasks";
  return (
    <>
      <PageHeader title="Tasks" sub="What needs doing, and the time you are not free." />
      <Tabs value={tab} onChange={(v) => setParams(v === "tasks" ? {} : { tab: v })}
        tabs={[{ value: "tasks", label: "Tasks" }, { value: "busy", label: "Busy times" }]} />
      {tab === "tasks" ? <TaskList /> : <BusyTimes />}
    </>
  );
}

function TaskList() {
  const [status, setStatus] = useState("pending");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [kind, setKind] = useState("");
  const [sort, setSort] = useState("deadline");
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const qs = new URLSearchParams({ status, sort, ...(category && { category }), ...(priority && { priority }), ...(kind && { kind }) }).toString();
  const tasks = useTasks(qs);
  const all = useTasks("status=all");
  const categories = useMemo(() => [...new Set((all.data ?? []).map((t) => t.category))].sort(), [all.data]);
  const save = useSaveTask();
  const refresh = useRefreshAll();
  const toast = useToast();

  async function remove(t: Task) {
    await api(`/api/tasks/${t.id}`, { method: "DELETE" });
    await refresh();
    const body: Partial<TaskBody> = { ...t, depends_on_id: null, recur_days: t.parent_id ? "" : t.recur_days };
    toast({ text: `Deleted "${t.title}"`, action: { label: "Undo", run: () => save.mutate({ body }) } });
  }
  async function toggleDone(t: Task) {
    await save.mutateAsync({ id: t.id, body: { status: t.status === "done" ? "pending" : "done" } });
    toast({ text: t.status === "done" ? "Marked as not done" : "Marked as done" });
  }

  const sel = "field h-9 w-auto py-1 pr-8";
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select aria-label="Status" className={sel} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">To do</option><option value="done">Done</option><option value="missed">Missed</option><option value="all">All</option>
        </select>
        <select aria-label="Category" className={sel} value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>{categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select aria-label="Priority" className={sel} value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="">Any priority</option>{[4, 3, 2, 1].map((p) => <option key={p} value={p}>{PRIORITY_NAMES[p]}</option>)}
        </select>
        <select aria-label="Fixed or movable" className={sel} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Fixed and movable</option><option value="movable">Movable only</option><option value="fixed">Fixed only</option>
        </select>
        <label className="ml-auto flex items-center gap-2 text-[13px] text-muted">
          Sort by
          <select className={sel} value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="deadline">Deadline</option><option value="priority">Priority</option><option value="duration">Duration</option>
            <option value="title">Title</option><option value="created">Newest</option>
          </select>
        </label>
        <Button variant="primary" onClick={() => setEditing("new")}><Plus size={16} aria-hidden /> Add task</Button>
      </div>

      {tasks.isLoading ? (
        <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : tasks.error ? (
        <ErrorState error={tasks.error} onRetry={() => tasks.refetch()} />
      ) : !tasks.data?.length ? (
        <EmptyState
          title={status === "done" ? "Nothing finished yet" : "No tasks match"}
          body={status === "pending" && !category && !priority && !kind ? "Add what you need to do. Rate how demanding each task is and the planner will place it where your energy fits." : "Try clearing a filter."}
          action={<Button variant="primary" onClick={() => setEditing("new")}>Add your first task</Button>}
        />
      ) : (
        <Card className="overflow-hidden p-0">
          <ul className="divide-y divide-line">
            {tasks.data.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:flex-nowrap">
                {t.recur_days ? (
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center text-teal" title="Repeating task: mark each day's copy done">
                    <Repeat size={16} aria-label="Repeating task" />
                  </span>
                ) : (
                  <button type="button"
                    onClick={() => toggleDone(t)}
                    disabled={t.status === "missed"}
                    aria-label={t.status === "done" ? `Mark "${t.title}" as not done` : `Mark "${t.title}" as done`}
                    className={clsx("flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
                      t.status === "done" ? "border-teal bg-teal text-white" : "border-line bg-surface hover:border-teal")}
                  >
                    {t.status === "done" && <Check size={14} />}
                  </button>
                )}
                <div className="min-w-0 flex-1">
                  <div className={clsx("truncate font-medium", t.status === "done" && "text-muted line-through")}>{t.title}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted">
                    <span>{t.category}</span>
                    {t.recur_days && <Badge tone="teal">Repeats {repeatText(t.recur_days)}</Badge>}
                    {t.parent_id && t.occurrence_date && <Badge>{dayName(`${t.occurrence_date}T12:00:00`)}'s copy</Badge>}
                    {t.status === "missed" && <Badge tone="warn">Missed</Badge>}
                    {t.is_fixed && t.fixed_start && <Badge>Fixed {t.recur_days ? "" : `${dayName(t.fixed_start, true)} `}{hm(t.fixed_start)}</Badge>}
                    {t.minutes_done > 0 && <Badge tone="sage">{t.minutes_done} min done</Badge>}
                    {t.depends_on_id && <Badge>After another task</Badge>}
                    {t.source !== "user" && <Badge tone="brown">Demo</Badge>}
                  </div>
                </div>
                <Badge tone={priorityTone(t.priority)}>{PRIORITY_NAMES[t.priority]}</Badge>
                <span className="num w-24 text-[13px] text-muted">{minutes(t.est_minutes)}</span>
                <span className={clsx("num w-28 text-[13px]", !t.recur_days && t.deadline && new Date(t.deadline).getTime() - Date.now() < 86400000 ? "font-medium text-danger" : "text-muted")}>
                  {t.recur_days ? (t.deadline ? `Due by ${hm(t.deadline)} each day` : "Due each day") : t.deadline ? `Due ${relDeadline(t.deadline)}` : "No deadline"}
                </span>
                <span className="w-24 text-[12.5px] text-muted" title="Mental and physical demand, 1 to 10">
                  Mind {Math.round(0.6 * t.mental_energy_req + 0.4 * t.mental_difficulty)} · Body {Math.round(0.6 * t.physical_energy_req + 0.4 * t.physical_difficulty)}
                </span>
                <div className="flex gap-1">
                  <button type="button" onClick={() => setEditing(t)} className="rounded-md p-1.5 text-muted hover:bg-beige hover:text-ink" aria-label={`Edit "${t.title}"`}><Pencil size={16} /></button>
                  <button type="button" onClick={() => remove(t)} className="rounded-md p-1.5 text-muted hover:bg-danger-tint hover:text-danger" aria-label={`Delete "${t.title}"`}><Trash2 size={16} /></button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add task" : "Edit task"} side width="max-w-xl">
        {editing !== null && <TaskForm key={editing === "new" ? "new" : editing.id} task={editing === "new" ? undefined : editing} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

function BusyTimes() {
  const list = useCommitments(14);
  const refresh = useRefreshAll();
  const today = toLocalIso(new Date()).slice(0, 10);
  const [f, setF] = useState({ label: "", kind: "fixed", date: today, start: "10:00", end: "11:00", repeat_days: 1 });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/api/commitments", { method: "POST", body: { label: f.label, kind: f.kind, start: `${f.date}T${f.start}:00`, end: `${f.date}T${f.end}:00`, repeat_days: f.repeat_days } });
      setF({ ...f, label: "" });
      await refresh();
    } catch (err) { setError(err); } finally { setBusy(false); }
  }
  async function remove(id: number) {
    await api(`/api/commitments/${id}`, { method: "DELETE" });
    await refresh();
  }
  const byDay = useMemo(() => {
    const m = new Map<string, typeof list.data>();
    for (const c of list.data ?? []) {
      const k = c.start.slice(0, 10);
      m.set(k, [...(m.get(k) ?? []), c]);
    }
    return [...m.entries()];
  }, [list.data]);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div>
        {list.isLoading ? <Skeleton className="h-40" /> : list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !byDay.length ? (
          <EmptyState title="No busy times in the next two weeks" body="Add lectures, meetings, travel or sleep. The planner never puts tasks on top of them." />
        ) : (
          <div className="space-y-4">
            {byDay.map(([day, items]) => (
              <Card key={day} className="p-4">
                <h3 className="mb-2 font-medium">{dayName(`${day}T12:00:00`)}</h3>
                <ul className="space-y-1.5">
                  {items!.map((c) => (
                    <li key={c.id} className="flex items-center gap-3 text-[14px]">
                      <span className="num w-28 text-muted">{hm(c.start)}–{hm(c.end)}</span>
                      <span className="flex-1">{c.label}</span>
                      <Badge tone={c.kind === "fixed" ? "teal" : "muted"}>{c.kind === "fixed" ? "Commitment" : "Unavailable"}</Badge>
                      {c.source !== "user" && <Badge tone="brown">Demo</Badge>}
                      <button type="button" onClick={() => remove(c.id)} className="rounded-md p-1 text-muted hover:bg-danger-tint hover:text-danger" aria-label={`Delete ${c.label}`}><Trash2 size={15} /></button>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        )}
      </div>
      <Card>
        <h2 className="mb-3 text-[15px] font-semibold">Add busy time</h2>
        <form onSubmit={add} className="space-y-3">
          <Field label="What" htmlFor="c-label"><input id="c-label" className="field" placeholder="AI lecture" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} required /></Field>
          <Field label="Type" htmlFor="c-kind">
            <select id="c-kind" className="field" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option value="fixed">Commitment (lecture, meeting)</option><option value="unavailable">Unavailable (travel, meals, rest)</option>
            </select>
          </Field>
          <Field label="Date" htmlFor="c-date"><input id="c-date" type="date" className="field" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} required /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="From" htmlFor="c-s"><input id="c-s" type="time" className="field" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} required /></Field>
            <Field label="To" htmlFor="c-e"><input id="c-e" type="time" className="field" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} required /></Field>
          </div>
          <Field label="Repeat on the next days" htmlFor="c-r" hint="1 means just this day.">
            <input id="c-r" type="number" min={1} max={14} className="field num" value={f.repeat_days} onChange={(e) => setF({ ...f, repeat_days: Number(e.target.value) })} />
          </Field>
          <InlineError error={error} />
          <Button type="submit" variant="primary" className="w-full" loading={busy}>Add busy time</Button>
        </form>
      </Card>
    </div>
  );
}
