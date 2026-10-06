// Types and pure helpers for the Dashboard (no browser/API imports, so node can test them).
// No engagement, reach or follower figures exist anywhere: the product does not measure them.

export type Rate = { num: number; den: number; pct: number | null; judged: boolean };
export type Section = { ok: boolean; error?: string };
export type Severity = "high" | "medium" | "low";
export type Platform = "ig" | "yt";

export type Chip = {
  id: string; status: string; publish_at: string | null; targets: Platform[];
  platforms: Partial<Record<Platform, { status?: string }>>; error: string | null;
};

export type Overview = {
  workspace: "live" | "demo";
  demo: boolean;
  handle: string;
  generated_at: string;
  window_days: 30 | 90;
  config: {
    slots: string[]; expected_per_day: number; timezone: string; demo_enabled: boolean;
    categories: { category: string; weight: number; target: number | null }[];
    thresholds: { min_n: number; min_mix_n: number; punctual_min: number; max_attempts: number; expire_hours: number };
  };
  status: Section & {
    state: "ok" | "heads_up" | "action" | "unknown"; needs_count: number; reason: string | null;
    today_published?: number; today_expected?: number; next_slot_at?: string | null;
  };
  kpis: Section & {
    posts_published: { count: number; topics: number; deliveries: number };
    approval: Rate & { first_pass: Rate; expired: number; pending: number };
    publish_success: Rate & { first_attempt: Rate; skipped: { platform: Platform; reason: string }[]; skipped_count: number };
    time_to_approve: { n: number; median_min: number | null; p90_min: number | null; judged: boolean; upper_bound: boolean };
    punctuality: Rate & { threshold_min: number };
  };
  attention: Section & {
    total: number; high: number; medium: number; last_decision_at: string | null;
    items: { code: string; severity: Severity; title: string; detail: string; age_min: number; post_id: string | null; kinds: string[]; action: { label: string; to: string } }[];
  };
  next_slots: Section & {
    configured: boolean;
    items: { slot_at: string; label: string; in_min: number; generated: boolean; topic: string | null; category: string | null; reel: Chip | null; carousel: Chip | null; generation_starts: string | null }[];
  };
  cadence: Section & { days: CadenceDay[]; full_days: number; counted_days: number; streak: number; today_full: boolean; expected_per_day: number };
  mix: Section & { n: number; judged: boolean; min_n: number; categories: MixRow[] };
  funnel: Section & { total: number; stages: { key: string; label: string; n: number }[]; buckets: Record<string, number>; leaks: { key: string; n: number }[] };
  turnaround: Section & {
    n: number; judged: boolean; median_min: number | null; p90_min: number | null;
    bins: { label: string; n: number }[]; channels: { channel: string; n: number; median_min: number | null }[];
  };
  pipeline: Section & {
    generation: Section & {
      tracking_since?: string | null; runs?: number; success?: Rate; skipped?: number; cancelled?: number;
      last?: { at: string; status: string } | null; last_failure?: string | null; streak?: number;
    };
    slot_fill: Rate;
    publishing: { last_published_at: string | null; failed_deliveries: number };
  };
  platforms: Section & {
    items: {
      platform: Platform; name: string; published: number; failed: number; skipped: number; success: Rate;
      recent: { post_id: string; topic: string; kind: string; at: string | null; url: string | null; privacy: string | null }[];
    }[];
  };
  recent_posts: Section & {
    items: { group_id: string; post_id: string; carousel_id: string | null; topic: string; category: string; at: string | null; thumb: string | null; chips: { platform: Platform; kind: string; status: string | null }[] }[];
  };
  activity: Section & { items: { id: number; at: string; event: string; level: string; actor: string; message: string; post_id: string | null }[] };
};

export type CadenceDay = { date: string; n: number; topics: number; expected: number; state: "full" | "partial" | "missed" | "today" | "none" };
export type MixRow = { category: string; count: number; share: number; target: number | null; delta: number | null; margin: number | null; tone: "on" | "off" | "idle" };

// ---------------------------------------------------------------------------
// Numbers and durations
// ---------------------------------------------------------------------------
export const ratioText = (r: { num: number; den: number }) => `${r.num} of ${r.den}`;
export const pctText = (r: Rate) => (r.pct === null ? "—" : `${r.pct}%`);

/** "—", "12 min", "1 h 05 m", "2 d 3 h" for a length in minutes. */
export function fmtMinutes(min: number | null | undefined): string {
  if (min === null || min === undefined) return "—";
  const m = Math.round(min);
  if (m < 60) return `${m} min`;
  if (m < 48 * 60) return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} m`;
  return `${Math.floor(m / 1440)} d ${Math.floor((m % 1440) / 60)} h`;
}

/** "in 3h 12m" / "in 5m" / "now" until an instant. */
export function untilLabel(iso: string, now: number): string {
  const mins = Math.round((new Date(iso).getTime() - now) / 60000);
  if (mins <= 0) return "now";
  if (mins < 60) return `in ${mins}m`;
  if (mins < 48 * 60) return `in ${Math.floor(mins / 60)}h ${mins % 60}m`;
  return `in ${Math.floor(mins / 1440)}d ${Math.floor((mins % 1440) / 60)}h`;
}

/** "2h ago", "5m ago", "3d ago". */
export function agoLabel(iso: string | null | undefined, now: number): string {
  if (!iso) return "never";
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 48 * 60) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
}

const fmt = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", ...opts });
export const timeIST = (iso: string) => fmt({ hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
export const stampIST = (iso: string) => fmt({ weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
export const dayIST = (iso: string) => fmt({ day: "numeric", month: "short" }).format(new Date(iso));

/** A calendar day given as "YYYY-MM-DD" (already an IST date), e.g. "Tue 29 Sep". */
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** Spelled out by hand: ICU's en-IN output ("Tue, 29 Sept") differs between engines. */
export function dayText(date: string, withWeekday = true): string {
  const d = new Date(`${date}T12:00:00Z`);
  const core = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
  return withWeekday ? `${WEEKDAYS[d.getUTCDay()]} ${core}` : core;
}

// ---------------------------------------------------------------------------
// The "right now" sentence
// ---------------------------------------------------------------------------
export type Headline = { tone: "ok" | "wait" | "bad" | "idle"; label: string; title: string; sub: string };

export function headline(s: Overview["status"], now: number): Headline {
  if (!s.ok || s.state === "unknown") {
    return { tone: "idle", label: "Can't check", title: "Couldn't check what needs you.", sub: "Nothing on this page claims all is well." };
  }
  const n = s.needs_count;
  const live = s.today_published ? `${s.today_published} of ${s.today_expected ?? "?"} posts live today` : "Nothing live yet today";
  const next = s.next_slot_at ? `next goes out at ${timeIST(s.next_slot_at)} IST (${untilLabel(s.next_slot_at, now)})` : "no upcoming slot configured";
  const sub = `${live} · ${next}`;
  const tone = s.state === "action" ? "bad" : s.state === "heads_up" ? "wait" : "ok";
  const label = s.state === "action" ? "Action needed" : s.state === "heads_up" ? "Heads up" : "All running";
  return { tone, label, title: n ? `${n} thing${n === 1 ? "" : "s"} ${n === 1 ? "needs" : "need"} you.` : "All good.", sub };
}

// ---------------------------------------------------------------------------
// Cadence heatmap
// ---------------------------------------------------------------------------
/** Weeks as columns (Monday first), seven rows; padding cells are null. */
export function heatGrid(days: CadenceDay[]): (CadenceDay | null)[][] {
  if (!days.length) return [];
  const dow = (d: string) => (new Date(`${d}T12:00:00Z`).getUTCDay() + 6) % 7; // Mon = 0
  const cells: (CadenceDay | null)[] = [...Array(dow(days[0].date)).fill(null), ...days];
  while (cells.length % 7) cells.push(null);
  const cols: (CadenceDay | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) cols.push(cells.slice(i, i + 7));
  return cols;
}

const STATE_WORD: Record<CadenceDay["state"], string> = {
  full: "all published", partial: "partly published", missed: "nothing published", today: "today, still in progress", none: "before the first post",
};

/** "Tue 29 Sep: 4 of 4 published (2 topics)". */
export function cellSummary(d: CadenceDay): string {
  const when = dayText(d.date);
  if (d.state === "none") return `${when}: no posts expected (before the first post)`;
  const topics = `${d.topics} topic${d.topics === 1 ? "" : "s"}`;
  if (d.state === "today") return `${when}: ${d.n} of ${d.expected} published so far (${topics}), day in progress`;
  if (d.state === "missed") return `${when}: missed, 0 of ${d.expected} published`;
  return `${when}: ${d.n} of ${d.expected} published (${topics})${d.state === "partial" ? ", partly" : ""}`;
}

export const stateWord = (s: CadenceDay["state"]) => STATE_WORD[s];

export function cadenceSummary(c: Pick<Overview["cadence"], "full_days" | "counted_days" | "streak">): string {
  const streak = c.streak ? `current streak ${c.streak} day${c.streak === 1 ? "" : "s"}` : "no current streak";
  return `${c.full_days} of ${c.counted_days} days fully published; ${streak}`;
}

// ---------------------------------------------------------------------------
// Funnel drawn as a shape (SVG paths; labels are HTML)
// ---------------------------------------------------------------------------
export type FunnelGeometry = { w: number; h: number; bars: { x: number; y: number; w: number; h: number }[]; bands: string[] };

/** Equal-width columns; each holds a centred bar whose height is its share of the first stage, joined by smooth bands. */
export function funnelShape(counts: number[], w = 400, h = 120): FunnelGeometry {
  const top = Math.max(counts[0] ?? 0, 1);
  const col = w / Math.max(counts.length, 1);
  const barW = col * 0.34;
  const bars = counts.map((n, i) => {
    const bh = n <= 0 ? 0 : Math.max(2, (n / top) * h);
    return { x: i * col, y: (h - bh) / 2, w: barW, h: bh };
  });
  const bands = bars.slice(0, -1).map((a, i) => {
    const b = bars[i + 1];
    const x0 = a.x + a.w;
    const x1 = b.x;
    const mid = (x0 + x1) / 2;
    return `M${x0} ${a.y} C${mid} ${a.y} ${mid} ${b.y} ${x1} ${b.y} L${x1} ${b.y + b.h} C${mid} ${b.y + b.h} ${mid} ${a.y + a.h} ${x0} ${a.y + a.h} Z`;
  });
  return { w, h, bars, bands };
}

export const sharePct = (n: number, total: number) => (total ? Math.round((100 * n) / total) : 0);

export const LEAK_TEXT: Record<string, string> = {
  rejected: "rejected", regenerated: "sent back to regenerate", expired: "expired undecided", failed: "failed for good",
  retrying: "retrying after a failure", pending: "waiting for a decision", waiting: "approved, not live yet",
};

// ---------------------------------------------------------------------------
// Mix
// ---------------------------------------------------------------------------
export function mixNote(m: Pick<Overview["mix"], "n" | "judged" | "min_n">): string {
  if (!m.n) return "No topics in this period yet.";
  return m.judged
    ? `n = ${m.n} topics. Targets are applied as weighted random picks, so some drift is normal; only drift beyond the margin is flagged.`
    : `n = ${m.n} topics: too few to judge (needs ${m.min_n}). Differences from target are mostly chance at this size.`;
}

export function deltaText(r: MixRow, judged: boolean): string {
  if (r.target === null || r.delta === null) return "no target";
  const sign = r.delta > 0 ? "+" : r.delta < 0 ? "−" : "±";
  return `${sign}${Math.abs(r.delta).toFixed(1)} vs target ${Math.round(r.target)}%${judged && r.margin !== null ? ` (margin ±${r.margin})` : ""}`;
}

// ---------------------------------------------------------------------------
// Feed
// ---------------------------------------------------------------------------
export const FEED_VERB: Record<string, string> = {
  "post.generated": "Generated", "post.regenerated": "Regenerated", "post.approved": "Approved", "post.scheduled": "Scheduled",
  "post.rejected": "Rejected", "post.published": "Published", "publish.failed": "Publish failed", "post.expired": "Expired",
  "generate.finished": "Generation finished", "generate.failed": "Generation failed",
};

// ---------------------------------------------------------------------------
// Workspace choice (Live / Demo): session only, so a demo can't be left on by accident
// ---------------------------------------------------------------------------
export const WORKSPACE_KEY = "dashboard.workspace";

export function pickWorkspace(search: string, stored: string | null, demoEnabled: boolean): "live" | "demo" {
  if (!demoEnabled) return "live";
  const q = new URLSearchParams(search).get("workspace");
  if (q === "demo" || q === "live") return q;
  return stored === "demo" ? "demo" : "live";
}
