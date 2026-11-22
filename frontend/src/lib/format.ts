/** Date helpers. The backend uses local times without a zone, which JS reads as local. */
export const pad = (n: number) => String(n).padStart(2, "0");

export function toLocalIso(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
}

/** Value for <input type="datetime-local"> */
export const toInput = (iso: string | null | undefined) => (iso ? iso.slice(0, 16) : "");
export const fromInput = (v: string) => (v ? `${v}:00` : null);

export const hm = (iso: string) => {
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

export function dayName(iso: string, short = false): string {
  const d = new Date(iso);
  const today = new Date();
  const diff = Math.round((new Date(d.toDateString()).getTime() - new Date(today.toDateString()).getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  return d.toLocaleDateString(undefined, short ? { weekday: "short" } : { weekday: "long", day: "numeric", month: "short" });
}

export function relDeadline(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  const h = ms / 3600000;
  if (h < 0) return "overdue";
  if (h < 1) return `in ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 24) return `in ${Math.round(h)} h`;
  const d = Math.round(h / 24);
  return `in ${d} day${d > 1 ? "s" : ""}`;
}

export const minutes = (m: number) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`);

export function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

const DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
/** "0,1,2,3,4" -> "weekdays"; "0,2,4" -> "Mon, Wed, Fri" */
export function repeatText(days: string): string {
  const d = days ? days.split(",").map(Number).sort() : [];
  if (d.length === 7) return "every day";
  if (d.join() === "0,1,2,3,4") return "weekdays";
  if (d.join() === "5,6") return "weekends";
  return d.map((x) => DAY_SHORT[x]).join(", ");
}
