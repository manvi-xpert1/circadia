import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import type { Block } from "../api/types";
import { WhyPanel } from "../components/WhyPanel";
import { fitBar, fitTone, ToastProvider } from "../components/ui";

describe("likelihood labels", () => {
  it("maps the completion bands and the older fuzzy labels to the same tones", () => {
    expect(fitTone("Very likely")).toBe("teal");
    expect(fitTone("Excellent")).toBe("teal");
    expect(fitTone("Uncertain")).toBe(fitTone("Fair"));
    expect(fitTone("Unlikely")).toBe("danger");
    expect(fitBar("Likely")).toBe("bg-sage");
  });
});

const block: Block = {
  block_id: 1, task_id: 1, title: "Write report", category: "Study", kind: "ai",
  start: "2099-01-01T10:00:00", end: "2099-01-01T11:00:00", day: 0, locked: false, outcome: null,
  fit: 0.62, fit_label: "Uncertain", mental_demand: 8, physical_demand: 2, slot_mental: 5, slot_physical: 6,
  happens: { p: 0.62, low: 0.3, high: 0.85, based_on: 0, label: "Uncertain" },
  factors: [{ factor: "mental_shortfall", text: "needs 8/10 mental energy; about 5/10 expected then", effect: -14 }],
};

function wrap(node: ReactNode) {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}><ToastProvider>{node}</ToastProvider></QueryClientProvider>;
}

describe("WhyPanel", () => {
  it("explains the chance a block happens, its range and what moves it", () => {
    render(wrap(<WhyPanel block={block} onClose={() => {}} />));
    expect(screen.getByText("Chance it happens at this time")).toBeInTheDocument();
    expect(screen.getByText("Uncertain · 62%")).toBeInTheDocument();
    expect(screen.getByText(/starting assumption/)).toBeInTheDocument();
    expect(screen.getByText("−14")).toBeInTheDocument();
    expect(screen.getByText(/about 5\/10 expected then/)).toBeInTheDocument();
  });
});
