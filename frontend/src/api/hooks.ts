import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AuthStatus, CheckIn, Commitment, Counts, ModelsInfo, PlanRun, Preferences, Task, TaskBody } from "./types";

export const useAuthStatus = () => useQuery({ queryKey: ["auth"], queryFn: () => api<AuthStatus>("/api/auth/status") });

export const useTasks = (params = "") =>
  useQuery({ queryKey: ["tasks", params], queryFn: () => api<Task[]>(`/api/tasks${params ? `?${params}` : ""}`) });

export const useCommitments = (days = 7) =>
  useQuery({ queryKey: ["commitments", days], queryFn: () => api<Commitment[]>(`/api/commitments?days=${days}`) });

export const useCheckins = (limit = 60) =>
  useQuery({ queryKey: ["checkins", limit], queryFn: () => api<CheckIn[]>(`/api/checkins?limit=${limit}`) });

export const usePlan = () => useQuery({ queryKey: ["plan"], queryFn: () => api<PlanRun | null>("/api/schedules/current") });

export const usePrefs = () => useQuery({ queryKey: ["prefs"], queryFn: () => api<Preferences>("/api/preferences") });

export const useModels = () => useQuery({ queryKey: ["models"], queryFn: () => api<ModelsInfo>("/api/models") });

export const useCounts = () => useQuery({ queryKey: ["counts"], queryFn: () => api<Counts>("/api/data/counts") });

/** Invalidate everything that depends on tasks, plans or learning. */
export function useRefreshAll() {
  const qc = useQueryClient();
  return () =>
    Promise.all(["tasks", "plan", "models", "counts", "checkins", "commitments"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export function useSaveTask() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Partial<TaskBody> & { status?: string } }) =>
      id ? api<Task>(`/api/tasks/${id}`, { method: "PATCH", body }) : api<Task>("/api/tasks", { method: "POST", body }),
    onSuccess: refresh,
  });
}

export function usePlanMutation<V>(fn: (v: V) => Promise<PlanRun | null>) {
  const qc = useQueryClient();
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      qc.setQueryData(["plan"], data);
      refresh();
    },
  });
}
