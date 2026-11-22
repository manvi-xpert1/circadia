/** Thin fetch wrapper. Errors carry the backend's {code, message, field}. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public field?: string | null) {
    super(message);
  }
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method ?? "GET",
      credentials: "include",
      headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "OFFLINE", "Can't reach the planner server. Is start.bat still running?");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, data.code ?? "ERROR", data.message ?? `Request failed (${res.status})`, data.field);
  }
  return data as T;
}
