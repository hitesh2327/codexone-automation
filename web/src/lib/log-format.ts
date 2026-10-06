// Pure types and helpers for the Logs page (no browser/API imports, so node can test them).

export type Level = "info" | "warning" | "error";

export type LogEntry = {
  id: number;
  created_at: string; // ISO, UTC
  level: Level;
  source: string;
  event: string;
  message: string;
  post_id: string | null;
  actor: string | null;
  detail: Record<string, unknown> | null;
};

export type LogsResponse = {
  items: LogEntry[];
  facets: { level: Record<string, number>; source: Record<string, number> };
  next_before_id: number | null;
};

export type Summary = {
  last_24h: Record<Level, number>;
  last_error: LogEntry | null;
  last_publish: LogEntry | null;
};

export type LogFilters = { level?: string; source?: string; event?: string; post_id?: string; q?: string; date_from?: string; date_to?: string };

/** Query string for /api/logs. `level` may be several comma-separated levels (sent as repeated params). */
export function logsQuery(filters: LogFilters, opts: { before_id?: number | null; limit?: number } = {}): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (!v) continue;
    if (k === "level") v.split(",").filter(Boolean).forEach((l) => p.append("level", l));
    else p.set(k, v);
  }
  if (opts.before_id) p.set("before_id", String(opts.before_id));
  if (opts.limit) p.set("limit", String(opts.limit));
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------------------
// Display helpers (all times IST)
// ---------------------------------------------------------------------------
const TZ = "Asia/Kolkata";
const dayFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-05" (IST calendar day). */
export const dayKey = (iso: string) => dayFmt.format(new Date(iso));
/** "14:03:22" (IST). */
export const timeIST = (iso: string) => timeFmt.format(new Date(iso));

/** "Today", "Yesterday" or "Mon 5 Oct 2026". */
export function dayLabel(key: string, now = Date.now()): string {
  if (key === dayKey(new Date(now).toISOString())) return "Today";
  if (key === dayKey(new Date(now - 86_400_000).toISOString())) return "Yesterday";
  const [y, m, d] = key.split("-").map(Number);
  return `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MONTHS[m - 1]} ${y}`;
}

export type DayGroup = { key: string; entries: LogEntry[] };

/** Entries are newest-first; groups keep that order. */
export function groupByDay(entries: LogEntry[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const e of entries) {
    const key = dayKey(e.created_at);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.entries.push(e);
    else groups.push({ key, entries: [e] });
  }
  return groups;
}

/** Merge a fresh first page into what is already loaded (live tail): new ids first, no duplicates. */
export function mergeNewest(current: LogEntry[], fresh: LogEntry[]): LogEntry[] {
  if (!current.length) return fresh;
  const top = current[0].id;
  const added = fresh.filter((e) => e.id > top);
  return added.length ? [...added, ...current] : current;
}

/** "3m ago", "2h ago", "4d ago". */
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86_400)}d ago`;
}
