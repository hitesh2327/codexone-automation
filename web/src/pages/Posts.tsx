import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowRight, ArrowUpRight, FilterX, Film, Images, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { PostPanel } from "@/components/post-panel";
import { ProgressTrack } from "@/components/progress-track";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import {
  ACTIVE_STATUSES, formatIST, listPosts, PLATFORM_LABEL, syncTelegram, type Filters, type Group, type Item, type PostsResponse,
} from "@/lib/posts";
import { stageOf } from "@/lib/stage";
import { cn } from "@/lib/utils";

const ANY = "__any";
const STATUS_OPTIONS = ["pending", "approved", "publishing", "published", "failed", "regenerate", "rejected", "expired"];

// ---------------------------------------------------------------------------------------------
// Pieces of a row
// ---------------------------------------------------------------------------------------------
function PlatformMarks({ item }: { item: Item }) {
  return (
    <span className="relative z-10 flex flex-wrap gap-1">
      {item.targets.map((t) => {
        const r = item.platforms[t];
        const tone = r?.status === "published" ? "text-ok border-ok/40 hover:bg-ok/10"
          : r?.status === "failed" ? "text-bad border-bad/45" : "text-muted-foreground border-border";
        const cls = `inline-flex h-5 items-center gap-0.5 rounded-[4px] border px-1 font-mono text-[10px] font-medium tracking-wider uppercase transition-colors ${tone}`;
        return r?.url ? (
          <a key={t} href={r.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
             className={cls} title={`Open on ${t === "ig" ? "Instagram" : "YouTube"}`} aria-label={`Open on ${PLATFORM_LABEL[t]}`}>
            {t}<ArrowUpRight className="size-3" aria-hidden />
          </a>
        ) : (
          <span key={t} className={cls} title={r?.error ?? r?.status ?? "not posted yet"}>{t}</span>
        );
      })}
      {!item.targets.length && <span className="text-xs text-muted-foreground">no platforms</span>}
    </span>
  );
}

/** One format (reel or carousel) of a topic: what it is, where it stands, where it goes. */
function Lane({ item, kind, now }: { item: Item | null; kind: "reel" | "carousel"; now: number }) {
  const Icon = kind === "reel" ? Film : Images;
  const name = kind === "reel" ? "Reel" : "Carousel";
  if (!item) {
    return (
      <div className="grid content-start gap-1.5 opacity-60">
        <span className="label-mono flex items-center gap-1.5"><Icon className="size-3.5" aria-hidden />{name}</span>
        <span className="text-xs text-muted-foreground">No {name.toLowerCase()} for this topic</span>
      </div>
    );
  }
  const stage = stageOf(item, formatIST(item.publish_at), now);
  return (
    <div className="grid min-w-0 content-start gap-2">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <span className="label-mono flex items-center gap-1.5"><Icon className="size-3.5" aria-hidden />{name}</span>
        <PlatformMarks item={item} />
      </div>
      <ProgressTrack stage={stage} />
    </div>
  );
}

/** Tiny contact sheet of whatever media exists: reel cover first, then the first carousel slides. */
function MediaStrip({ group, className }: { group: Group; className?: string }) {
  const [broken, setBroken] = useState<Set<string>>(new Set());
  const cover = group.items.reel?.media.cover;
  const slides = group.items.carousel?.media.carousel ?? [];
  const shots = [
    ...(cover ? [{ src: cover, shape: "aspect-[9/16]" }] : []),
    ...slides.slice(0, 2).map((src) => ({ src, shape: "aspect-[4/5]" })),
  ].filter((s) => !broken.has(s.src));
  if (!shots.length) return null;
  const more = Math.max(0, slides.length - 2);
  return (
    <div aria-hidden className={cn("flex items-end gap-1", className)}>
      {shots.map((s) => (
        <img key={s.src} src={s.src} alt="" loading="lazy" draggable={false}
             onError={() => setBroken((b) => new Set(b).add(s.src))}
             className={cn("h-14 rounded-[5px] border border-border bg-sunken object-cover", s.shape)} />
      ))}
      {more > 0 && <span className="pb-0.5 font-mono text-[10px] text-muted-foreground">+{more}</span>}
    </div>
  );
}

function TopicRow({ g, now, selected, onOpen }: { g: Group; now: number; selected: boolean; onOpen: () => void }) {
  const time = formatIST(g.publish_at, false);
  const past = new Date(g.publish_at).getTime() < now;
  return (
    <li
      className={cn(
        "group/row relative grid gap-x-6 gap-y-4 px-4 py-4 transition-colors duration-(--dur-fast) sm:px-5",
        "grid-cols-[3.75rem_minmax(0,1fr)] lg:grid-cols-[4rem_minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,1fr)] xl:grid-cols-[4rem_minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,1fr)_auto]",
        selected ? "bg-selected" : "hover:bg-raised",
      )}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px] bg-signal transition-opacity", selected ? "opacity-100" : "opacity-0")} />
      <div className="grid content-start">
        <span className={cn("font-mono text-lg leading-none font-medium tabular-nums", past ? "text-muted-foreground" : "text-foreground")}>{time}</span>
        <span className="mt-1.5 font-mono text-[10px] tracking-[0.16em] text-muted-foreground uppercase">IST</span>
      </div>
      <div className="min-w-0">
        {/* the real control: a button whose hit area is stretched over the whole row */}
        <button
          type="button"
          onClick={onOpen}
          aria-haspopup="dialog"
          className="text-left font-heading text-[15px] leading-snug font-medium text-balance outline-none after:absolute after:inset-0 after:content-[''] group-hover/row:text-primary focus-visible:after:outline-2 focus-visible:after:outline-offset-[-2px] focus-visible:after:outline-ring sm:text-base"
        >
          {g.topic}
        </button>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <span className="tracking-wider uppercase">{g.category}</span>
          {g.versions > 1 && <><span aria-hidden>·</span><span>v{g.versions}</span></>}
        </p>
      </div>
      <div className="col-span-2 grid grid-cols-2 gap-x-5 gap-y-4 lg:col-span-2">
        <Lane item={g.items.reel} kind="reel" now={now} />
        <Lane item={g.items.carousel} kind="carousel" now={now} />
      </div>
      <MediaStrip group={g} className="col-span-2 xl:col-span-1 xl:self-center" />
    </li>
  );
}

// ---------------------------------------------------------------------------------------------
// Days
// ---------------------------------------------------------------------------------------------
const DAY_KEY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" });
const DAY_NAME = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short" });
const MONTH = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", month: "short" });

function dayDiff(key: string, now: number) {
  const a = Date.parse(`${key}T00:00:00Z`);
  const b = Date.parse(`${DAY_KEY.format(now)}T00:00:00Z`);
  return Math.round((a - b) / 86400000);
}

function relative(diff: number) {
  return diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : diff === -1 ? "Yesterday" : null;
}

type Day = { key: string; at: string; groups: Group[] };
function byDay(groups: Group[]): Day[] {
  const out: Day[] = [];
  for (const g of groups) {
    const key = DAY_KEY.format(new Date(g.publish_at));
    const last = out[out.length - 1];
    if (last && last.key === key) last.groups.push(g);
    else out.push({ key, at: g.publish_at, groups: [g] });
  }
  return out;
}

function DayMark({ day, now }: { day: Day; now: number }) {
  const d = new Date(day.at);
  const rel = relative(dayDiff(day.key, now));
  const items = day.groups.reduce((n, g) => n + (g.items.reel ? 1 : 0) + (g.items.carousel ? 1 : 0), 0);
  return (
    <div className="flex items-baseline gap-3 lg:sticky lg:top-6 lg:grid lg:content-start lg:gap-1 lg:self-start">
      <span className="font-heading text-[2.5rem] leading-none font-semibold tracking-tight tabular-nums lg:text-5xl">{day.key.slice(8)}</span>
      <span className="grid gap-0.5 lg:mt-1">
        <span className="font-mono text-xs tracking-[0.14em] text-foreground/90 uppercase">{DAY_NAME.format(d)} · {MONTH.format(d)}</span>
        {rel && <span className={cn("font-mono text-[11px] tracking-[0.14em] uppercase", rel === "Today" ? "text-signal" : "text-muted-foreground")}>{rel}</span>}
      </span>
      <span className="ml-auto font-mono text-[11px] text-muted-foreground lg:mt-3 lg:ml-0">
        {day.groups.length} {day.groups.length === 1 ? "topic" : "topics"} · {items} {items === 1 ? "post" : "posts"}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// The flow strip: four buckets laid out as the path a post travels, each a one-click filter
// ---------------------------------------------------------------------------------------------
const SUMMARY: { key: string; label: string; status: string; tone: string; bar: string; count: (c: PostsResponse["counts"]) => number }[] = [
  { key: "approval", label: "Waiting for approval", status: "pending", tone: "text-wait", bar: "bg-wait", count: (c) => c.pending ?? 0 },
  { key: "scheduled", label: "Approved / publishing", status: "approved", tone: "text-go", bar: "bg-go", count: (c) => (c.approved ?? 0) + (c.publishing ?? 0) },
  { key: "live", label: "Live", status: "published", tone: "text-ok", bar: "bg-ok", count: (c) => c.published ?? 0 },
  { key: "failed", label: "Failed", status: "failed", tone: "text-bad", bar: "bg-bad", count: (c) => c.failed ?? 0 },
];

export default function Posts() {
  const [params, setParams] = useSearchParams();
  const filters: Filters = useMemo(
    () => Object.fromEntries(["status", "platform", "category", "date_from", "date_to", "q"].map((k) => [k, params.get(k) ?? ""])),
    [params],
  );
  const [data, setData] = useState<PostsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(params.get("post"));
  const [now, setNow] = useState(() => Date.now());
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [search, setSearch] = useState(filters.q ?? "");
  const abort = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      const res = await listPosts(filters, ctrl.signal);
      setData(res);
      setUpdatedAt(Date.now());
      setError(null);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError(e instanceof ApiError ? e.message : "Couldn't load posts.");
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [filters]);

  // On open: apply any Telegram taps first, so both places agree, then load.
  useEffect(() => {
    syncTelegram()
      .then((r) => {
        if (r.changes.length) toast.info(`Applied ${r.changes.length} Telegram update(s)`);
      })
      .catch(() => {})
      .finally(load);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  // Keep fresh: quickly while something is publishing/regenerating, slowly while posts are waiting or
  // scheduled (approvals and publishes happen in CI, not here). Paused while the tab is hidden.
  const items = data?.groups.flatMap((g) => Object.values(g.items)).filter(Boolean) as Item[] | undefined;
  const busy = items?.some((i) => ACTIVE_STATUSES.includes(i.status));
  const waiting = items?.some((i) => i.status === "pending" || i.status === "approved");
  useEffect(() => {
    if (!busy && !waiting) return;
    const t = setInterval(() => { if (!document.hidden) load(); }, busy ? 8000 : 30000);
    return () => clearInterval(t);
  }, [busy, waiting, load]);

  // Tick once a minute so "in 7h 12m" counts down without refetching.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(t);
  }, []);

  // Debounced search box -> ?q=
  useEffect(() => {
    const t = setTimeout(() => setFilter("q", search.trim()), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function setFilter(key: keyof Filters | "post", value: string) {
    // Read the live URL, not the router's render-time copy: navigations commit in a transition, so two quick
    // changes (or Clear followed by the debounced search effect) would otherwise overwrite each other.
    setParams(() => {
      const next = new URLSearchParams(window.location.search);
      if (value && value !== ANY) next.set(key, value); else next.delete(key);
      return next;
    }, { replace: true });
  }

  function open(group: Group) {
    const id = (group.items.reel ?? group.items.carousel)!.id;
    setOpenId(id);
    setFilter("post", id);
  }

  const openGroup = data?.groups.find((g) => g.items.reel?.id === openId || g.items.carousel?.id === openId) ?? null;
  const hasFilters = ["status", "platform", "category", "date_from", "date_to", "q"].some((k) => params.get(k));
  const pendingCount = data?.counts.pending ?? 0;
  const days = useMemo(() => byDay(data?.groups ?? []), [data]);
  const clearFilters = () => { setSearch(""); setParams(openId ? { post: openId } : {}, { replace: true }); };

  return (
    <AppShell>
      <div className="mx-auto grid max-w-[78rem] gap-7 px-4 py-6 md:px-8 md:py-9">
        <PageHeader
          index="02"
          eyebrow="Run of show"
          title="Posts"
          lead={pendingCount ? `${pendingCount} waiting for approval. Nothing goes out until you say so.` : "Nothing waiting for approval"}
          meta={updatedAt && (
            <span className="font-mono text-[11px] text-muted-foreground" title="Refreshes by itself while posts are waiting or publishing">
              Updated {new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }).format(updatedAt)} IST
            </span>
          )}
          actions={(
            <Button variant="outline" size="sm" onClick={() => { setLoading(true); syncTelegram().catch(() => {}).finally(load); }}>
              <RefreshCw className={loading ? "animate-spin" : ""} />
              Refresh
            </Button>
          )}
        />

        {data && (
          <div className="grid grid-cols-2 overflow-hidden rounded-xl border border-border sm:grid-cols-[1fr_auto_1fr_auto_1fr_1fr]" role="group" aria-label="Posts by stage">
            {SUMMARY.map((b, i) => {
              const n = b.count(data.counts);
              const active = filters.status === b.status;
              return (
                <div key={b.key} className="contents">
                  {i > 0 && i < 3 && (
                    <span aria-hidden className="hidden items-center text-muted-foreground/60 sm:flex"><ArrowRight className="size-4" /></span>
                  )}
                  <button
                    type="button" aria-pressed={active}
                    onClick={() => setFilter("status", active ? "" : b.status)}
                    className={cn(
                      "relative grid gap-1 px-4 py-4 text-left transition-colors duration-(--dur-fast) focus-visible:outline-offset-[-2px] sm:px-5",
                      "border-border",
                      i % 2 === 0 && "max-sm:border-r",
                      i >= 2 && "max-sm:border-t",
                      i === 3 && "sm:border-l sm:border-dashed sm:bg-[color-mix(in_srgb,var(--bad)_3%,transparent)]",
                      active ? "bg-raised" : "hover:bg-raised",
                    )}
                  >
                    <span aria-hidden className={cn("absolute inset-x-0 top-0 h-0.5 transition-opacity", b.bar, active ? "opacity-100" : "opacity-0")} />
                    <span className={cn("font-mono text-[1.75rem] leading-none font-medium tabular-nums", n ? b.tone : "text-muted-foreground")}>{String(n).padStart(2, "0")}</span>
                    <span className="label-mono">{b.label}</span>
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* filters */}
        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
            <div className="relative col-span-2 sm:w-60">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search topics" className="pl-9" aria-label="Search topics" />
            </div>
            <Select value={filters.status || ANY} onValueChange={(v) => setFilter("status", v)}>
              <SelectTrigger className="w-full sm:w-40" aria-label="Status"><SelectValue placeholder="Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any status</SelectItem>
                {STATUS_OPTIONS.map((s) => (
                  <SelectItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}{data?.counts[s as keyof typeof data.counts] ? ` (${data.counts[s as keyof typeof data.counts]})` : ""}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filters.platform || ANY} onValueChange={(v) => setFilter("platform", v)}>
              <SelectTrigger className="w-full sm:w-36" aria-label="Platform"><SelectValue placeholder="Platform" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any platform</SelectItem>
                <SelectItem value="ig">Instagram</SelectItem>
                <SelectItem value="yt">YouTube</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filters.category || ANY} onValueChange={(v) => setFilter("category", v)}>
              <SelectTrigger className="col-span-2 w-full sm:col-span-1 sm:w-40" aria-label="Category"><SelectValue placeholder="Category" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any category</SelectItem>
                {(data?.categories ?? []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="col-span-2 grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:flex">
              <Input type="date" value={filters.date_from ?? ""} onChange={(e) => setFilter("date_from", e.target.value)} aria-label="From date" className="w-full sm:w-38" />
              <span aria-hidden className="font-mono text-xs text-muted-foreground">to</span>
              <Input type="date" value={filters.date_to ?? ""} onChange={(e) => setFilter("date_to", e.target.value)} aria-label="To date" className="w-full sm:w-38" />
            </div>
            {hasFilters && (
              <Button variant="ghost" size="sm" className="col-span-2 sm:col-span-1" onClick={clearFilters}>
                <FilterX />
                Clear
              </Button>
            )}
            {data && (
              <span className="col-span-2 font-mono text-[11px] text-muted-foreground sm:ml-auto" aria-live="polite">
                {data.groups.length} {data.groups.length === 1 ? "topic" : "topics"}{hasFilters ? " match" : ""}
              </span>
            )}
          </div>
        </div>

        {error && (
          <p role="alert" className="border-l-[3px] border-bad bg-bad/10 py-3 pr-4 pl-4 text-sm text-bad">{error}</p>
        )}

        {loading && !data ? (
          <div className="grid gap-px overflow-hidden rounded-xl border border-border" role="status" aria-label="Loading posts">
            {[0, 1, 2].map((i) => (
              <div key={i} className="grid grid-cols-[4rem_1fr] gap-6 p-5 lg:grid-cols-[4rem_1.25fr_1fr_1fr]">
                <Skeleton className="h-5 w-12" />
                <div className="grid gap-2"><Skeleton className="h-4 w-4/5" /><Skeleton className="h-3 w-24" /></div>
                <Skeleton className="hidden h-10 lg:block" /><Skeleton className="hidden h-10 lg:block" />
              </div>
            ))}
          </div>
        ) : data && !data.groups.length ? (
          <div className="grid justify-items-start gap-3 border-t border-dashed border-border py-14 sm:grid-cols-[auto_1fr] sm:gap-x-8">
            <span aria-hidden className="font-heading text-7xl leading-none font-bold text-transparent [-webkit-text-stroke:1px_var(--rule)]">00</span>
            <div className="grid content-center gap-1.5">
              <p className="font-heading text-lg font-semibold">{hasFilters ? "No posts match these filters" : "No posts yet"}</p>
              <p className="max-w-prose text-sm text-muted-foreground">
                {hasFilters ? "Try clearing a filter." : "New posts appear here after the daily generation runs."}
              </p>
              {hasFilters && (
                <Button variant="outline" size="sm" className="mt-2 w-fit" onClick={clearFilters}><FilterX />Clear filters</Button>
              )}
            </div>
          </div>
        ) : data ? (
          <div className="grid gap-10">
            {days.map((day) => (
              <section key={day.key} aria-label={`${relative(dayDiff(day.key, now)) ?? ""} ${formatIST(day.at).split(",")[0]}`.trim()}
                       className="grid gap-4 lg:grid-cols-[7.5rem_minmax(0,1fr)] lg:gap-8">
                <DayMark day={day} now={now} />
                <ol className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card/40">
                  {day.groups.map((g) => (
                    <TopicRow key={g.group_id} g={g} now={now}
                              selected={!!openGroup && openGroup.group_id === g.group_id}
                              onOpen={() => open(g)} />
                  ))}
                </ol>
              </section>
            ))}
          </div>
        ) : null}
      </div>

      <PostPanel
        group={openGroup}
        open={!!openGroup}
        onOpenChange={(o) => { if (!o) { setOpenId(null); setFilter("post", ""); } }}
        onChanged={load}
        publishingEnabled={data?.publishing_enabled ?? false}
      />
    </AppShell>
  );
}
