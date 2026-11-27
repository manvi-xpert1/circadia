import clsx from "clsx";
import { X } from "lucide-react";
import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";

/* ---------- Button ---------------------------------------------------------- */
type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
export function Button({
  variant = "secondary", size = "md", className, loading, children, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button type="button"
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-3 text-[13px]" : "h-10 px-4 text-[14px]",
        variant === "primary" && "bg-teal text-white hover:bg-teal-hover",
        variant === "secondary" && "border border-line bg-surface text-ink hover:border-teal/40 hover:bg-teal-tint/40",
        variant === "ghost" && "text-ink hover:bg-beige/70",
        variant === "danger" && "border border-danger/30 bg-surface text-danger hover:bg-danger-tint",
        className,
      )}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden />}
      {children}
    </button>
  );
}

/* ---------- Surfaces -------------------------------------------------------- */
export function Card({ className, children, glass }: { className?: string; children: ReactNode; glass?: boolean }) {
  return <section className={clsx(glass ? "glass rounded-card" : "card", "p-5", className)}>{children}</section>;
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-[15px] font-semibold text-ink">{children}</h2>
      {action}
    </div>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[26px] font-light leading-tight tracking-[-0.01em] text-ink">{title}</h1>
        {sub && <p className="mt-1 text-[14px] text-muted">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

/* ---------- Badges ---------------------------------------------------------- */
export type Tone = "teal" | "sage" | "brown" | "warn" | "danger" | "muted";
const TONES: Record<Tone, string> = {
  teal: "bg-teal-tint text-teal",
  sage: "bg-sage-tint text-sage-ink",
  brown: "bg-brown-tint text-brown",
  warn: "bg-warn-tint text-warn",
  danger: "bg-danger-tint text-danger",
  muted: "bg-beige text-muted",
};
export function Badge({ tone = "muted", children, className, title }: { tone?: Tone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[12px] font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}

/** Plans saved before the completion model used fuzzy-fit labels; show them in the nearest band. */
const OLD_FIT_LABELS: Record<string, string> = { Excellent: "Very likely", Good: "Likely", Fair: "Uncertain", Poor: "Unlikely" };

/** Colour of the thin bar beside a planned block. */
export function fitBar(label?: string) {
  const bars: Record<string, string> = { teal: "bg-teal", sage: "bg-sage", warn: "bg-warn", danger: "bg-danger" };
  return bars[fitTone(label)] ?? "bg-warn";
}

export function fitTone(label?: string): Tone {
  const l = OLD_FIT_LABELS[label ?? ""] ?? label;
  return l === "Very likely" ? "teal" : l === "Likely" ? "sage" : l === "Uncertain" ? "warn" : "danger";
}

export const priorityTone = (p?: number): Tone => (p === 4 ? "danger" : p === 3 ? "brown" : p === 2 ? "muted" : "muted");

/* ---------- States ---------------------------------------------------------- */
export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-lg bg-beige/80", className)} />;
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-card border border-dashed border-line bg-surface/60 p-6">
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {body && <p className="max-w-prose text-muted">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = error as { message?: string; code?: string };
  return (
    <div role="alert" className="rounded-card border border-danger/30 bg-danger-tint/60 p-4">
      <p className="font-medium text-danger">{e?.message ?? "Something went wrong."}</p>
      <div className="mt-2 flex items-center gap-3">
        {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
        {e?.code && <span className="text-[12px] text-muted">Code {e.code}</span>}
      </div>
    </div>
  );
}

export function InlineError({ error }: { error: unknown }) {
  if (!error) return null;
  return <p role="alert" className="text-[13px] text-danger">{(error as Error).message}</p>;
}

/* ---------- Form bits ------------------------------------------------------- */
export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <p className="hint mt-1">{hint}</p>}
    </div>
  );
}

export function EnergySlider({
  id, label, value, onChange, low, high,
}: { id: string; label: string; value: number; onChange: (v: number) => void; low: string; high: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-[14px] font-medium">{label}</label>
        <span className="num text-[20px] font-light text-teal" aria-hidden>{value}</span>
      </div>
      <input
        id={id}
        type="range"
        min={1}
        max={10}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="energy"
        style={{ ["--fill" as string]: `${((value - 1) / 9) * 100}%` }}
        aria-valuetext={`${value} out of 10`}
      />
      <div className="flex justify-between text-[12px] text-muted">
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </div>
  );
}

export function Segmented<T extends string | number>({
  value, options, onChange, label,
}: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-line bg-surface p-0.5">
      {options.map((o) => (
        <button type="button"
          key={String(o.value)}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "h-8 rounded-md px-3 text-[13px] font-medium transition-colors",
            value === o.value ? "bg-teal text-white" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ value, tabs, onChange }: { value: T; tabs: { value: T; label: ReactNode }[]; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 border-b border-line">
      {tabs.map((t) => (
        <button type="button"
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={clsx(
            "-mb-px border-b-2 px-3 py-2 text-[14px] font-medium transition-colors",
            value === t.value ? "border-teal text-ink" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- Modal / drawer -------------------------------------------------- */
export function Modal({
  open, onClose, title, children, side = false, width = "max-w-lg",
}: { open: boolean; onClose: () => void; title: string; children: ReactNode; side?: boolean; width?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    setTimeout(() => ref.current?.querySelector<HTMLElement>("input,select,textarea,button")?.focus(), 30);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-ink/25" onClick={onClose} />
      <div
        ref={ref}
        className={clsx(
          "glass relative flex max-h-full w-full flex-col overflow-hidden",
          side ? `ml-auto h-full ${width} rounded-none sm:rounded-l-2xl` : `m-auto ${width} max-h-[90vh] rounded-2xl mx-4`,
        )}
      >
        <div className="flex items-center justify-between border-b border-line/70 px-5 py-4">
          <h2 className="text-[17px] font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-muted hover:bg-beige hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

/* ---------- Toasts ---------------------------------------------------------- */
interface Toast { id: number; text: string; action?: { label: string; run: () => void }; tone?: "ok" | "error" }
const ToastCtx = createContext<(t: Omit<Toast, "id">) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts, { ...t, id }]);
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), t.action ? 7000 : 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={clsx(
              "glass pointer-events-auto flex items-center gap-4 rounded-xl px-4 py-3 text-[14px]",
              t.tone === "error" && "border-danger/40 text-danger",
            )}
          >
            <span>{t.text}</span>
            {t.action && (
              <button type="button"
                className="font-semibold text-teal hover:underline"
                onClick={() => {
                  t.action!.run();
                  setToasts((ts) => ts.filter((x) => x.id !== t.id));
                }}
              >
                {t.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------- Probability bar ------------------------------------------------- */
export function Meter({ value, label, tone = "teal" }: { value: number; label: string; tone?: "teal" | "sage" | "warn" }) {
  const color = tone === "teal" ? "bg-teal" : tone === "sage" ? "bg-sage" : "bg-warn";
  return (
    <div>
      <div className="mb-1 flex justify-between text-[13px]">
        <span className="text-muted">{label}</span>
        <span className="num font-medium">{Math.round(value * 100)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-beige" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label={label}>
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${Math.max(2, value * 100)}%` }} />
      </div>
    </div>
  );
}
