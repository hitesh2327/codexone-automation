import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api";
import { type Overview, WORKSPACE_KEY } from "./dashboard-format";

export * from "./dashboard-format";

export type Workspace = "live" | "demo";
export const REFRESH_MS = 60_000;

export const getOverview = (range: 30 | 90, workspace: Workspace, signal?: AbortSignal) =>
  api<Overview>(`/api/dashboard/overview?range=${range}&workspace=${workspace}`, { signal });

export const storedWorkspace = (): string | null => {
  try { return sessionStorage.getItem(WORKSPACE_KEY); } catch { return null; }
};
export const storeWorkspace = (w: Workspace) => {
  try { if (w === "demo") sessionStorage.setItem(WORKSPACE_KEY, "demo"); else sessionStorage.removeItem(WORKSPACE_KEY); } catch { /* private mode */ }
};

/**
 * One aggregate request per load; refreshes every minute while the tab is visible (and once when it
 * becomes visible again after a minute away). On failure the last good data stays on screen (`stale`).
 */
export function useOverview(range: 30 | 90, workspace: Workspace, onDemoOff: () => void) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const abort = useRef<AbortController | null>(null);
  const last = useRef(0);
  const demoOff = useRef(onDemoOff);
  demoOff.current = onDemoOff;

  const load = useCallback(async () => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setLoading(true);
    try {
      const res = await getOverview(range, workspace, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setData(res);
      setFetchedAt(Date.now());
      last.current = Date.now();
      setError(null);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      if (e instanceof ApiError && e.status === 404 && workspace === "demo") { demoOff.current(); return; }
      setError(e instanceof ApiError ? e.message : "Couldn't load the dashboard.");
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [range, workspace]);

  useEffect(() => { void load(); return () => abort.current?.abort(); }, [load]);

  useEffect(() => {
    const tick = setInterval(() => { if (!document.hidden) void load(); }, REFRESH_MS);
    const onVisible = () => { if (!document.hidden && Date.now() - last.current > REFRESH_MS) void load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(tick); document.removeEventListener("visibilitychange", onVisible); };
  }, [load]);

  // Only ever show data that belongs to the requested workspace (never demo numbers under "Live").
  const shown = data && data.workspace === workspace ? data : null;
  return { data: shown, error, loading, fetchedAt, stale: !!error && !!shown, reload: load };
}
