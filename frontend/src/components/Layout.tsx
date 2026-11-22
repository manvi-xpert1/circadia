import clsx from "clsx";
import { CalendarClock, Gauge, LayoutDashboard, ListTodo, LogOut, Settings, Sparkles, SplitSquareHorizontal, FlaskConical, LineChart } from "lucide-react";
import { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useCounts, useModels } from "../api/hooks";
import type { User } from "../api/types";
import { Badge } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/tasks", label: "Tasks", icon: ListTodo },
  { to: "/check-in", label: "Check-in", icon: Gauge },
  { to: "/schedule", label: "AI Schedule", icon: CalendarClock },
  { to: "/insights", label: "Insights", icon: LineChart },
  { to: "/what-if", label: "What-if", icon: SplitSquareHorizontal },
  { to: "/evaluation", label: "Evaluation lab", icon: FlaskConical },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#1F6F6B" />
        <path d="M9 22V10m7 12V14m7 8v-5" stroke="#FAF7F0" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold">Circadia</div>
        <div className="text-[12px] text-muted">Energy-aware planner</div>
      </div>
    </div>
  );
}

export function Layout({ user, children }: { user: User; children: ReactNode }) {
  const qc = useQueryClient();
  const models = useModels();
  const counts = useCounts();
  const hasDemo = counts.data && Object.values(counts.data).some((c) => (c.demo ?? 0) > 0);
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    qc.clear();
    window.location.href = "/";
  };
  const link = ({ isActive }: { isActive: boolean }) =>
    clsx(
      "flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] transition-colors",
      isActive ? "bg-surface font-medium text-teal shadow-lift" : "text-ink/80 hover:bg-surface/60 hover:text-ink",
    );

  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-beige/70 px-3 py-5 lg:sticky lg:top-0 lg:flex lg:h-screen">
        <div className="px-2"><Brand /></div>
        <nav className="mt-8 flex flex-col gap-1" aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={link}>
              <n.icon size={18} aria-hidden /> {n.label}
            </NavLink>
          ))}
          <NavLink to="/settings" className={(s) => clsx(link(s), "mt-4")}>
            <Settings size={18} aria-hidden /> Settings
          </NavLink>
        </nav>
        <div className="mt-auto space-y-3 px-2">
          <div className="flex flex-wrap gap-1.5">
            {models.data && (
              <Badge tone={models.data.mode === "personalized" ? "teal" : "muted"} title="Personalized after 3 recorded outcomes">
                <Sparkles size={12} aria-hidden /> {models.data.mode === "personalized" ? "Personalized" : "Cold start"}
              </Badge>
            )}
            {hasDemo && <Badge tone="brown" title="Some records are demo data. Clear them in Settings.">Demo data</Badge>}
          </div>
          <div className="flex items-center justify-between gap-2 border-t border-line pt-3">
            <span className="truncate text-[13px] text-muted">Signed in as {user.display_name}</span>
            <button type="button" onClick={logout} className="rounded-md p-1.5 text-muted hover:bg-surface hover:text-ink" aria-label="Log out" title="Log out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Compact header for tablets and phones */}
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur lg:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <Brand />
          <button type="button" onClick={logout} className="rounded-md p-2 text-muted hover:bg-beige" aria-label="Log out"><LogOut size={18} /></button>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-2" aria-label="Main">
          {[...NAV, { to: "/settings", label: "Settings", icon: Settings }].map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => clsx("flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-[13px]", isActive ? "bg-teal text-white" : "text-ink/80 hover:bg-beige")}>
              <n.icon size={15} aria-hidden /> {n.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 lg:py-10">
        <div className="mx-auto max-w-[1180px]">{children}</div>
      </main>
    </div>
  );
}
