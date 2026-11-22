import { FormEvent, useState } from "react";
import { useSaveTask, useTasks } from "../api/hooks";
import type { Task, TaskBody } from "../api/types";
import { fromInput, hm, repeatText, toInput } from "../lib/format";
import { Button, EnergySlider, Field, InlineError, Segmented, useToast } from "./ui";

export const CATEGORIES = ["Study", "Work", "Errand", "Health", "Admin", "Personal"];

const EMPTY: TaskBody = {
  title: "", category: "Study", priority: 2, deadline: null, est_minutes: 60,
  mental_difficulty: 5, physical_difficulty: 3, mental_energy_req: 5, physical_energy_req: 3,
  is_fixed: false, fixed_start: null, fixed_end: null, depends_on_id: null, notes: "",
  recur_days: "", recur_until: null,
};
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
type RepeatMode = "never" | "daily" | "weekdays" | "custom";
const modeOf = (d: string): RepeatMode => (!d ? "never" : d === "0,1,2,3,4,5,6" ? "daily" : d === "0,1,2,3,4" ? "weekdays" : "custom");

export function TaskForm({ task, onDone }: { task?: Task; onDone: () => void }) {
  const [f, setF] = useState<TaskBody>(task ? { ...EMPTY, ...task } : EMPTY);
  const save = useSaveTask();
  const toast = useToast();
  const others = useTasks("status=pending").data?.filter((t) => t.id !== task?.id && !t.recur_days) ?? [];
  const isCopy = !!task?.parent_id;
  const [mode, setMode] = useState<RepeatMode>(modeOf(f.recur_days));
  const days = new Set(f.recur_days ? f.recur_days.split(",").map(Number) : []);
  const setRepeat = (m: RepeatMode) => {
    setMode(m);
    setF((x) => ({ ...x, recur_days: m === "never" ? "" : m === "daily" ? "0,1,2,3,4,5,6" : m === "weekdays" ? "0,1,2,3,4" : x.recur_days || String((new Date().getDay() + 6) % 7), depends_on_id: m === "never" ? x.depends_on_id : null }));
  };
  const toggleDay = (d: number) => {
    const next = new Set(days);
    if (next.has(d)) next.delete(d); else next.add(d);
    if (next.size) setF((x) => ({ ...x, recur_days: [...next].sort().join(",") }));
  };
  const set = <K extends keyof TaskBody>(k: K, v: TaskBody[K]) => setF((x) => ({ ...x, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body: TaskBody = { ...f, fixed_start: f.is_fixed ? f.fixed_start : null, fixed_end: f.is_fixed ? f.fixed_end : null };
    await save.mutateAsync({ id: task?.id, body });
    toast({ text: task ? "Task saved" : "Task added" });
    onDone();
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <fieldset className="space-y-4">
        <legend className="mb-2 text-[13px] font-semibold text-muted">Basics</legend>
        <Field label="Title" htmlFor="t-title">
          <input id="t-title" className="field" value={f.title} onChange={(e) => set("title", e.target.value)} required maxLength={200} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category" htmlFor="t-cat">
            <input id="t-cat" className="field" list="cats" value={f.category} onChange={(e) => set("category", e.target.value)} required maxLength={40} />
            <datalist id="cats">{CATEGORIES.map((c) => <option key={c} value={c} />)}</datalist>
          </Field>
          <Field label="Your estimate (minutes)" htmlFor="t-est" hint="The planner adds slack once it learns your pace.">
            <input id="t-est" type="number" min={5} max={480} step={5} className="field num" value={f.est_minutes} onChange={(e) => set("est_minutes", Number(e.target.value))} required />
          </Field>
        </div>
        <div>
          <span className="label">Priority</span>
          <Segmented label="Priority" value={f.priority} onChange={(v) => set("priority", v)}
            options={[{ value: 1, label: "Low" }, { value: 2, label: "Medium" }, { value: 3, label: "High" }, { value: 4, label: "Critical" }]} />
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="mb-2 text-[13px] font-semibold text-muted">Timing</legend>
        {isCopy ? (
          <p className="rounded-lg bg-beige/70 px-3 py-2 text-[13px] text-muted">
            This is the {task?.occurrence_date} copy of a repeating task. Changes here affect only this day; edit the repeating task to change every day.
          </p>
        ) : (
          <div>
            <span className="label">Repeats</span>
            <Segmented label="Repeats" value={mode} onChange={setRepeat}
              options={[{ value: "never", label: "Never" }, { value: "daily", label: "Every day" }, { value: "weekdays", label: "Weekdays" }, { value: "custom", label: "Pick days" }]} />
            {mode === "custom" && (
              <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Days it repeats on">
                {DAYS.map((d, i) => (
                  <button key={d} type="button" aria-pressed={days.has(i)} onClick={() => toggleDay(i)}
                    className={days.has(i) ? "h-8 w-11 rounded-md bg-teal text-[13px] font-medium text-white" : "h-8 w-11 rounded-md border border-line bg-surface text-[13px] text-muted hover:border-teal"}>
                    {d}
                  </button>
                ))}
              </div>
            )}
            {mode !== "never" && (
              <div className="mt-3 grid grid-cols-2 items-end gap-3">
                <Field label="Stop repeating after (optional)" htmlFor="t-until">
                  <input id="t-until" type="date" className="field" value={f.recur_until ?? ""} onChange={(e) => set("recur_until", e.target.value || null)} />
                </Field>
                <p className="hint pb-2">
                  Repeats {repeatText(f.recur_days)}. A copy is added for each of those days in your planning horizon
                  {f.deadline ? `, due by ${hm(f.deadline)} that day.` : ", due by the end of that day."}
                </p>
              </div>
            )}
          </div>
        )}
        <Field label={mode !== "never" && !isCopy ? "Due by (time used for each day; optional)" : "Deadline (optional)"} htmlFor="t-dl">
          <input id="t-dl" type="datetime-local" className="field" value={toInput(f.deadline)} onChange={(e) => set("deadline", fromInput(e.target.value))} />
        </Field>
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" className="h-4 w-4 accent-teal" checked={f.is_fixed} onChange={(e) => set("is_fixed", e.target.checked)} />
          Fixed time: the planner must not move it
        </label>
        {f.is_fixed && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Starts" htmlFor="t-fs">
              <input id="t-fs" type="datetime-local" className="field" value={toInput(f.fixed_start)} onChange={(e) => set("fixed_start", fromInput(e.target.value))} required />
            </Field>
            <Field label="Ends" htmlFor="t-fe">
              <input id="t-fe" type="datetime-local" className="field" value={toInput(f.fixed_end)} onChange={(e) => set("fixed_end", fromInput(e.target.value))} required />
            </Field>
          </div>
        )}
        <Field label="Must come after (optional)" htmlFor="t-dep">
          <select id="t-dep" className="field" disabled={mode !== "never" && !isCopy} value={f.depends_on_id ?? ""} onChange={(e) => set("depends_on_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">Nothing, it can start any time</option>
            {others.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
          </select>
        </Field>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="mb-1 text-[13px] font-semibold text-muted">Energy demand</legend>
        <p className="hint -mt-2">The fuzzy engine compares these with your energy in each time slot.</p>
        <EnergySlider id="t-md" label="Mental difficulty" low="Easy" high="Hard" value={f.mental_difficulty} onChange={(v) => set("mental_difficulty", v)} />
        <EnergySlider id="t-mr" label="Mental energy needed" low="Little" high="A lot" value={f.mental_energy_req} onChange={(v) => set("mental_energy_req", v)} />
        <EnergySlider id="t-pd" label="Physical difficulty" low="Easy" high="Hard" value={f.physical_difficulty} onChange={(v) => set("physical_difficulty", v)} />
        <EnergySlider id="t-pr" label="Physical energy needed" low="Little" high="A lot" value={f.physical_energy_req} onChange={(v) => set("physical_energy_req", v)} />
      </fieldset>

      <Field label="Notes" htmlFor="t-notes">
        <textarea id="t-notes" rows={2} className="field" value={f.notes} onChange={(e) => set("notes", e.target.value)} maxLength={2000} />
      </Field>

      <InlineError error={save.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" variant="primary" loading={save.isPending}>{task ? "Save task" : "Add task"}</Button>
      </div>
    </form>
  );
}
