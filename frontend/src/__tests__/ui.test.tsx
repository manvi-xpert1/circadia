import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EnergySlider, Meter } from "../components/ui";
import { fromInput, minutes, toInput, toLocalIso } from "../lib/format";
import { Login } from "../pages/Login";

describe("format helpers", () => {
  it("round-trips datetime-local values without a time zone", () => {
    expect(toInput("2026-11-12T17:00:00")).toBe("2026-11-12T17:00");
    expect(fromInput("2026-11-12T17:00")).toBe("2026-11-12T17:00:00");
    expect(fromInput("")).toBeNull();
    expect(toLocalIso(new Date(2026, 10, 12, 9, 5))).toBe("2026-11-12T09:05:00");
  });
  it("formats durations", () => {
    expect(minutes(45)).toBe("45 min");
    expect(minutes(90)).toBe("1 h 30 min");
    expect(minutes(120)).toBe("2 h");
  });
});

describe("EnergySlider", () => {
  it("reports changes and exposes an accessible value", () => {
    const onChange = vi.fn();
    render(<EnergySlider id="m" label="Mental energy" low="Drained" high="Sharp" value={6} onChange={onChange} />);
    const slider = screen.getByLabelText("Mental energy");
    expect(slider).toHaveAttribute("aria-valuetext", "6 out of 10");
    fireEvent.change(slider, { target: { value: "8" } });
    expect(onChange).toHaveBeenCalledWith(8);
  });
});

describe("Meter", () => {
  it("shows a percentage", () => {
    render(<Meter label="Chance it gets done" value={0.58} />);
    expect(screen.getByText("58%")).toBeInTheDocument();
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "58");
  });
});

describe("Login", () => {
  it("refuses mismatched passwords on first run before calling the server", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<QueryClientProvider client={new QueryClient()}><Login firstRun /></QueryClientProvider>);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Manvi" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-pass" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "different" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The two passwords are different.");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("TaskForm", () => {
  it("does not save when you pick a priority or a repeat option", async () => {
    const { TaskForm } = await import("../components/TaskForm");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }));
    const onDone = vi.fn();
    render(<QueryClientProvider client={new QueryClient()}><TaskForm onDone={onDone} /></QueryClientProvider>);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Essay" } });
    fireEvent.click(screen.getByRole("radio", { name: "High" }));
    fireEvent.click(screen.getByRole("radio", { name: "Every day" }));
    expect(screen.getByRole("radio", { name: "High" })).toHaveAttribute("aria-checked", "true");
    const posts = fetchSpy.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "POST");
    expect(posts).toHaveLength(0);
    expect(onDone).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
