import { Lock, LockOpen, MoveRight, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { usePlanMutation } from "../api/hooks";
import type { Block, PlanRun } from "../api/types";
import { dayName, fromInput, hm, toInput } from "../lib/format";
import { Badge, Button, fitTone, InlineError, Meter, priorityTone, useToast } from "./ui";

export function WhyPanel({ block, onClose }: { block: Block; onClose: () => void }) {
  const toast = useToast();
  const [moveTo, setMoveTo] = useState(toInput(block.start));
  const [mins, setMins] = useState<number>(block.planned_minutes ?? 30);
  const patch = usePlanMutation((body: object) => api<PlanRun>(`/api/blocks/${block.block_id}`, { method: "PATCH", body }));
  const outcome = usePlanMutation((body: object) => api<PlanRun>(`/api/blocks/${block.block_id}/outcome`, { method: "POST", body }));
  const undo = usePlanMutation(() => api<PlanRun>(`/api/blocks/${block.block_id}/outcome`, { method: "DELETE" }));
  const ai = block.kind === "ai" && block.fit !== undefined;
  const started = new Date(block.start).getTime() <= Date.now();

  return (
    <aside className="glass rounded-card p-5" aria-label={`Why ${block.title} is placed here`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[17px] font-semibold leading-snug">{block.title}</h2>
          <p className="num mt-0.5 text-[13px] text-muted">{dayName(block.start)}, {hm(block.start)}–{hm(block.end)}</p>
        </div>
        <button type="button" onClick={onClose} className="text-[13px] text-muted hover:text-ink">Close</button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {block.priority_name && <Badge tone={priorityTone(block.priority)}>{block.priority_name} priority</Badge>}
        {block.category && <Badge>{block.category}</Badge>}
        {block.kind === "fixed-task" && <Badge tone="brown">Fixed by you</Badge>}
        {block.locked && <Badge tone="brown"><Lock size={11} aria-hidden /> Locked</Badge>}
      </div>

      {block.verdict && <p className="mt-4 text-[15px] leading-relaxed">{block.verdict}</p>}

      {ai && (
        <>
          <section className="mt-5 border-t border-line/80 pt-4">
            <div className="flex items-baseline justify-between">
              <h3 className="text-[13px] font-semibold text-muted">Energy fit</h3>
              <Badge tone={fitTone(block.fit_label)}>{block.fit_label} {block.fit?.toFixed(2)}</Badge>
            </div>
            <p className="mt-2 text-[13.5px] text-ink/90">
              Expected capacity <span className="num font-medium">{block.capacity?.toFixed(1)}</span>/10 against a mental demand of{" "}
              <span className="num font-medium">{block.mental_demand}</span>. Physical energy <span className="num">{block.slot_physical}</span> against{" "}
              <span className="num">{block.physical_demand}</span>.
              {block.energy_source === "forecast" && " Energy for this day is a forecast."}
            </p>
            {!!block.fired_rules?.length && (
              <ul className="mt-2 space-y-1">
                {block.fired_rules.map((r) => (
                  <li key={r.id} className="flex items-center gap-2 text-[13px]">
                    <span className="num w-9 shrink-0 rounded bg-beige px-1 text-center text-[12px] font-medium">{r.id}</span>
                    <span className="flex-1 text-ink/85">{r.text}</span>
                    <span className="num text-muted">{Math.round(r.strength * 100)}%</span>
                  </li>
                ))}
              </ul>
            )}
            {block.next_best && <p className="mt-2 text-[13px] text-muted">Next best time: {block.next_best.label}, fit {block.next_best.fit.toFixed(2)}.</p>}
          </section>

          <section className="mt-4 border-t border-line/80 pt-4">
            <h3 className="text-[13px] font-semibold text-muted">Duration</h3>
            <p className="mt-1 text-[13.5px]">{block.duration?.text}</p>
            <div className="mt-3 space-y-2.5">
              <Meter label="Chance it gets done in this block" value={block.p_complete ?? 0} />
              {block.p_on_time != null && <Meter label="Chance it finishes before the deadline" value={block.p_on_time} tone="sage" />}
            </div>
          </section>

          {(!!block.rules_applied?.length || !!block.warnings?.length) && (
            <section className="mt-4 border-t border-line/80 pt-4">
              <h3 className="text-[13px] font-semibold text-muted">Rules</h3>
              <ul className="mt-1 space-y-1 text-[13px]">
                {block.rules_applied?.map((r) => <li key={r}>{r}</li>)}
                {block.warnings?.map((w) => <li key={w} className="text-warn">{w}</li>)}
              </ul>
            </section>
          )}
        </>
      )}

      {block.kind !== "fixed-task" && (
        <section className="mt-4 border-t border-line/80 pt-4">
          <h3 className="text-[13px] font-semibold text-muted">Adjust</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => patch.mutate({ locked: !block.locked }, { onSuccess: () => toast({ text: block.locked ? "Unlocked" : "Locked: regenerating keeps it here" }) })}>
              {block.locked ? <LockOpen size={14} aria-hidden /> : <Lock size={14} aria-hidden />} {block.locked ? "Unlock" : "Lock"}
            </Button>
            <Button size="sm" variant="danger" onClick={() => patch.mutate({ removed: true }, { onSuccess: () => { toast({ text: "Removed from this plan" }); onClose(); } })}>
              <Trash2 size={14} aria-hidden /> Remove
            </Button>
          </div>
          <div className="mt-3 flex items-end gap-2">
            <div className="flex-1">
              <label htmlFor="move-to" className="label">Move to</label>
              <input id="move-to" type="datetime-local" step={900} className="field" value={moveTo} onChange={(e) => setMoveTo(e.target.value)} />
            </div>
            <Button size="md" onClick={() => patch.mutate({ start: fromInput(moveTo) }, { onSuccess: () => toast({ text: "Moved and locked" }) })}>
              <MoveRight size={14} aria-hidden /> Move
            </Button>
          </div>
          <InlineError error={patch.error} />
        </section>
      )}

      <section className="mt-4 border-t border-line/80 pt-4">
        <h3 className="text-[13px] font-semibold text-muted">How did it go?</h3>
        {block.outcome ? (
          <div className="mt-2 flex items-center gap-3 text-[14px]">
            <span>
              Recorded: <span className="font-medium">{block.outcome.status === "partial" ? "partly done" : block.outcome.status}</span>
              {block.outcome.actual_minutes ? ` in ${block.outcome.actual_minutes} min` : ""}
            </span>
            <Button size="sm" variant="ghost" onClick={() => undo.mutate(undefined)}>Undo</Button>
          </div>
        ) : (
          <>
            {!started && <p className="hint mt-1">You can record this once it has started.</p>}
            <div className="mt-2 flex items-end gap-2">
              <div className="w-28">
                <label htmlFor="actual" className="label">Minutes taken</label>
                <input id="actual" type="number" min={1} max={960} className="field num" value={mins} onChange={(e) => setMins(Number(e.target.value))} />
              </div>
              <Button size="md" variant="primary" disabled={!started} onClick={() => outcome.mutate({ status: "done", actual_minutes: mins }, { onSuccess: () => toast({ text: "Recorded as done. The planner learns from this." }) })}>Done</Button>
              <Button size="md" disabled={!started} onClick={() => outcome.mutate({ status: "partial", actual_minutes: mins }, { onSuccess: () => toast({ text: "Recorded as partly done. The rest carries over." }) })}>Partly</Button>
              <Button size="md" variant="ghost" disabled={!started} onClick={() => outcome.mutate({ status: "skipped" }, { onSuccess: () => toast({ text: "Recorded as skipped" }) })}>Skipped</Button>
            </div>
          </>
        )}
        <InlineError error={outcome.error ?? undo.error} />
      </section>
    </aside>
  );
}
