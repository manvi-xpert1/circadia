import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api } from "../api/client";
import { Button, Field, InlineError } from "../components/ui";

export function Login({ firstRun }: { firstRun: boolean }) {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (firstRun && password !== confirm) return setError(new Error("The two passwords are different."));
    if (firstRun && password.length < 8) return setError(new Error("Use at least 8 characters for the password."));
    setBusy(true);
    try {
      await api(firstRun ? "/api/auth/setup" : "/api/auth/login", { method: "POST", body: { username, password } });
      await qc.invalidateQueries();
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="glass w-full max-w-sm rounded-2xl p-7" aria-label={firstRun ? "Create account" : "Log in"}>
        <svg width="36" height="36" viewBox="0 0 32 32" aria-hidden>
          <rect width="32" height="32" rx="8" fill="#1F6F6B" />
          <path d="M9 22V10m7 12V14m7 8v-5" stroke="#FAF7F0" strokeWidth="3" strokeLinecap="round" />
        </svg>
        <p className="mt-4 text-[13px] font-semibold text-teal">Circadia</p>
        <h1 className="mt-1 text-[24px] font-light tracking-[-0.01em]">{firstRun ? "Set up your planner" : "Welcome back"}</h1>
        <p className="mt-1 text-muted">
          {firstRun
            ? "Create the one account for this computer. Everything stays on this machine."
            : "Log in to see today's plan."}
        </p>
        <div className="mt-6 space-y-4">
          <Field label="Name" htmlFor="username">
            <input id="username" className="field" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required minLength={2} />
          </Field>
          <Field label="Password" htmlFor="password" hint={firstRun ? "At least 8 characters." : undefined}>
            <input id="password" type="password" className="field" autoComplete={firstRun ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          {firstRun && (
            <Field label="Confirm password" htmlFor="confirm">
              <input id="confirm" type="password" className="field" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </Field>
          )}
          <InlineError error={error} />
          <Button variant="primary" type="submit" className="w-full" loading={busy}>
            {firstRun ? "Create account" : "Log in"}
          </Button>
        </div>
        {!firstRun && (
          <p className="mt-5 text-[12.5px] text-muted">
            Forgot it? In the backend folder run <code className="rounded bg-beige px-1">python -m app.reset_password</code>. Your data is kept.
          </p>
        )}
      </form>
    </div>
  );
}
