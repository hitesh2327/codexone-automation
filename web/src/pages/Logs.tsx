import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronRight, CircleDot, ExternalLink, FilterX, RefreshCw, Search } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import {
  ago, dayLabel, groupByDay, listLogs, logsSummary, mergeNewest, timeIST,
  type Level, type LogEntry, type LogFilters, type LogsResponse, type Summary,
} from "@/lib/logs";
import { cn } from "@/lib/utils";

const ANY = "__any";
const PAGE = 100;
const LIVE_MS = 5000;
const FILTER_KEYS = ["level", "source", "event", "post_id", "q", "date_from", "date_to"] as const;
const SOURCES = ["dashboard", "telegram", "pipeline", "publisher", "auth"];

const LEVELS: { id: Level; label: string; tag: string; text: string; bar: string; chip: string }[] = [
  { id: "info", label: "Info", tag: "INFO", text: "text-go", bar: "bg-go/60", chip: "border-go/45 bg-go/10 text-go" },
  { id: "warning", label: "Warnings", tag: "WARN", text: "text-wait", bar: "bg-wait", chip: "border-wait/45 bg-wait/10 text-wait" },
  { id: "error", label: "Errors", tag: "ERR", text: "text-bad", bar: "bg-bad", chip: "border-bad/45 bg-bad/10 text-bad" },
];

/** One segment of the terminal status line: a toggle that filters the ledger and keeps the other filters. */
function Seg({ on, disabled, onClick, label, children }: { on?: boolean; disabled?: boolean; onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button
      type="button" aria-pressed={disabled ? undefined : !!on} disabled={disabled} onClick={onClick} aria-label={label}
      className={cn(
        "inline-flex min-h-8 items-center gap-1.5 rounded-[4px] border px-2 whitespace-nowrap transition-colors duration-(--dur-fast) touch:min-h-11 disabled:cursor-default",
        on ? "border-rule bg-raised text-foreground" : "border-transparent enabled:hover:bg-raised enabled:hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
const LEVEL = Object.fromEntries(LEVELS.map((l) => [l.id, l])) as Record<Level, (typeof LEVELS)[number]>;

function Row({ e, open, fresh, onToggle }: { e: LogEntry; open: boolean; fresh: boolean; onToggle: () => void }) {
  const lv = LEVEL[e.level] ?? LEVEL.info;
  const panelId = `log-${e.id}`;
  return (
    <li className={cn("relative border-b border-border/60 last:border-b-0", fresh && "animate-pulse bg-go/5")}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-0.5", lv.bar)} />
      <button
        type="button" onClick={onToggle} aria-expanded={open} aria-controls={panelId}
        className="grid w-full grid-cols-[auto_1fr] items-start gap-x-3 gap-y-0.5 py-2.5 pr-3 pl-4 text-left transition-colors duration-(--dur-fast) hover:bg-raised focus-visible:bg-raised focus-visible:outline-offset-[-2px] sm:grid-cols-[4.5rem_3rem_minmax(0,13rem)_1fr]"
      >
        <span className="font-mono text-xs tabular-nums text-muted-foreground sm:pt-px">{timeIST(e.created_at)}</span>
        <span className={cn("font-mono text-[10px] font-semibold tracking-wider sm:pt-[3px]", lv.text)}>{lv.tag}</span>
        <span className="col-start-2 row-start-2 truncate font-mono text-xs text-muted-foreground sm:col-start-3 sm:row-start-1 sm:pt-px">{e.event}</span>
        <span className="col-start-2 row-start-3 min-w-0 text-sm break-words sm:col-start-4 sm:row-start-1">
          <ChevronRight aria-hidden className={cn("mr-1 -ml-0.5 inline size-3.5 text-muted-foreground transition-transform", open && "rotate-90")} />
          {e.message}
        </span>
      </button>
      {open && (
        <div id={panelId} className="mb-2 ml-4 grid gap-2 border-l border-dashed border-border pr-3 pl-3 text-xs sm:ml-[4.75rem]">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-muted-foreground">
            <dt>entry</dt><dd className="break-all">#{e.id} · {e.created_at}</dd>
            <dt>source</dt><dd>{e.source}</dd>
            {e.actor && <><dt>actor</dt><dd className="break-all">{e.actor}</dd></>}
            {e.post_id && (
              <>
                <dt>post</dt>
                <dd className="break-all">
                  <Link to={`/posts?post=${encodeURIComponent(e.post_id)}`} className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline">
                    {e.post_id}<ExternalLink className="size-3" aria-hidden />
                  </Link>
                </dd>
              </>
            )}
          </dl>
          {e.detail ? (
            <pre className="max-h-72 overflow-auto rounded-md border bg-sunken p-2.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words">
              {JSON.stringify(e.detail, null, 2)}
            </pre>
          ) : (
            <p className="font-mono text-muted-foreground">no extra detail</p>
          )}
        </div>
      )}
    </li>
  );
}

export default function Logs() {
  const [params, setParams] = useSearchParams();
  const filters: LogFilters = useMemo(
    () => Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ""])),
    [params],
  );
  const filterKey = JSON.stringify(filters);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [facets, setFacets] = useState<LogsResponse["facets"]>({ level: {}, source: {} });
  const [next, setNext] = useState<number | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState(filters.q ?? "");
  const [now, setNow] = useState(() => Date.now());
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  const entriesRef = useRef<LogEntry[]>([]);
  entriesRef.current = entries;
  const filterRef = useRef(filterKey);
  filterRef.current = filterKey;

  const loadSummary = useCallback(() => {
    logsSummary().then(setSummary).catch(() => {});
  }, []);

  /** reset=true: first page for the current filters. reset=false (live tail): merge anything newer. */
  const load = useCallback(async (reset: boolean) => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    const key = filterKey;
    try {
      const res = await listLogs(filters, { limit: PAGE }, ctrl.signal);
      if (filterRef.current !== key) return;
      if (reset) {
        setEntries(res.items);
        setNext(res.next_before_id);
        setOpenIds(new Set());
      } else {
        const cur = entriesRef.current;
        const merged = mergeNewest(cur, res.items);
        if (merged !== cur) {
          setFresh(new Set(merged.slice(0, merged.length - cur.length).map((e) => e.id)));
          setEntries(merged);
        }
      }
      setFacets(res.facets);
      setUpdatedAt(Date.now());
      setError(null);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError(e instanceof ApiError ? e.message : "Couldn't load the log.");
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [filters, filterKey]);

  useEffect(() => { setLoading(true); load(true); }, [load]);
  useEffect(() => { loadSummary(); }, [loadSummary]);

  // Live tail: poll every few seconds, paused while the tab is hidden.
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => {
      if (document.hidden) return;
      load(false);
      loadSummary();
    }, LIVE_MS);
    return () => clearInterval(t);
  }, [live, load, loadSummary]);

  useEffect(() => {
    if (!fresh.size) return;
    const t = setTimeout(() => setFresh(new Set()), 1800);
    return () => clearTimeout(t);
  }, [fresh]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);

  function setFilter(key: (typeof FILTER_KEYS)[number], value: string) {
    setParams((p) => {
      const n = new URLSearchParams(p);
      if (value && value !== ANY) n.set(key, value); else n.delete(key);
      return n;
    }, { replace: true });
  }

  // Debounced search box -> ?q=
  useEffect(() => {
    const t = setTimeout(() => { if (search.trim() !== (params.get("q") ?? "")) setFilter("q", search.trim()); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  async function loadMore() {
    if (!next) return;
    setLoadingMore(true);
    try {
      const res = await listLogs(filters, { before_id: next, limit: PAGE });
      setEntries((cur) => [...cur, ...res.items.filter((i) => !cur.some((c) => c.id === i.id))]);
      setNext(res.next_before_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load older entries.");
    } finally {
      setLoadingMore(false);
    }
  }

  const levels = (filters.level ?? "").split(",").filter(Boolean);
  const toggleLevel = (id: string) =>
    setFilter("level", (levels.includes(id) ? levels.filter((l) => l !== id) : [...levels, id]).join(","));
  const errorsOnly = levels.length === 1 && levels[0] === "error";
  const warnOnly = levels.length === 1 && levels[0] === "warning";
  const hasFilters = FILTER_KEYS.some((k) => params.get(k));
  const groups = useMemo(() => groupByDay(entries), [entries]);
  const sources = Array.from(new Set([...SOURCES, ...Object.keys(facets.source), ...(filters.source ? [filters.source] : [])]));
  const errors24 = summary?.last_24h.error ?? 0;
  const warn24 = summary?.last_24h.warning ?? 0;

  const pubOn = filters.event === "post.published";
  const lastPub = summary?.last_publish;
  const lastErr = summary?.last_error;

  return (
    <AppShell>
      <div className="mx-auto grid max-w-[78rem] gap-6 px-4 py-6 md:px-8 md:py-9">
        <PageHeader
          index="06"
          eyebrow="Record"
          title="Logs"
          lead="Everything that happened to your posts: decisions, publishing, sign-ins."
          meta={updatedAt && (
            <span className="font-mono text-[11px] text-muted-foreground tabular-nums" title="Last checked">
              {live && <span className="text-go">tailing · </span>}{timeIST(new Date(updatedAt).toISOString())} IST
            </span>
          )}
          actions={(
            <>
              <Button
                variant={live ? "default" : "outline"} size="sm" aria-pressed={live} onClick={() => setLive((v) => !v)}
                title={`Check for new entries every ${LIVE_MS / 1000}s while this tab is open`}
              >
                <CircleDot className={live ? "animate-pulse" : ""} />
                Live tail
              </Button>
              <Button variant="outline" size="sm" onClick={() => { setLoading(true); load(true); loadSummary(); }}>
                <RefreshCw className={loading ? "animate-spin" : ""} />
                Refresh
              </Button>
            </>
          )}
        />

        {/* the last 24 hours as one terminal status line; every segment is a shortcut filter that keeps the others */}
        <div role="group" aria-label="Last 24 hours"
             className="grid grid-cols-2 items-center gap-x-1 gap-y-0.5 rounded-lg border bg-sunken px-2 py-1.5 font-mono text-xs text-muted-foreground sm:flex sm:flex-wrap">
          <span aria-hidden className="col-span-2 px-2 pt-1 text-[11px] tracking-[0.14em] text-foreground uppercase sm:px-1.5 sm:pt-0">24h</span>
          <span aria-hidden className="mr-1 hidden h-4 w-px bg-rule sm:block" />
          <Seg on={errorsOnly} onClick={() => setFilter("level", errorsOnly ? "" : "error")}
               label={`Errors in the last 24 hours: ${summary ? errors24 : "loading"}. Show errors only`}>
            <span className={cn("font-semibold", errors24 ? "text-bad" : "")}>ERR</span>
            <span className={cn("tabular-nums", errors24 ? "text-foreground" : "")}>{summary ? errors24 : "–"}</span>
          </Seg>
          <span aria-hidden className="max-sm:hidden">·</span>
          <Seg on={warnOnly} onClick={() => setFilter("level", warnOnly ? "" : "warning")}
               label={`Warnings in the last 24 hours: ${summary ? warn24 : "loading"}. Show warnings only`}>
            <span className={cn("font-semibold", warn24 ? "text-wait" : "")}>WARN</span>
            <span className={cn("tabular-nums", warn24 ? "text-foreground" : "")}>{summary ? warn24 : "–"}</span>
          </Seg>
          <span aria-hidden className="max-sm:hidden">·</span>
          <Seg on={pubOn} onClick={() => setFilter("event", pubOn ? "" : "post.published")}
               label={`Last publish: ${summary ? (lastPub ? `${ago(lastPub.created_at, now)}, ${lastPub.message}` : "never") : "loading"}. Show publishes only`}>
            <span>last publish</span>
            <span className={lastPub ? "text-ok" : ""}>{summary ? (lastPub ? ago(lastPub.created_at, now) : "never") : "–"}</span>
            {lastPub && <span className="hidden max-w-[18rem] truncate sm:inline">({lastPub.message.replace(/^Published /, "")})</span>}
          </Seg>
          <span aria-hidden className="max-sm:hidden">·</span>
          <Seg disabled={!lastErr} onClick={() => setFilter("level", "error")}
               label={`Last error: ${summary ? (lastErr ? `${ago(lastErr.created_at, now)}, ${lastErr.event}: ${lastErr.message}` : "none") : "loading"}${lastErr ? ". Show errors" : ""}`}>
            <span>last error</span>
            <span className={lastErr ? "text-bad" : ""}>{summary ? (lastErr ? ago(lastErr.created_at, now) : "none") : "–"}</span>
            {lastErr && <span className="hidden sm:inline" title={lastErr.message}>({lastErr.event})</span>}
          </Seg>
        </div>

        {/* filters */}
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Level">
            <span aria-hidden className="label-mono mr-1">Level</span>
            {LEVELS.map((l) => {
              const on = levels.includes(l.id);
              return (
                <button
                  key={l.id} type="button" aria-pressed={on} onClick={() => toggleLevel(l.id)}
                  className={cn("inline-flex h-8 items-center gap-1.5 rounded-[4px] border px-2.5 font-mono text-xs transition-colors duration-(--dur-fast) touch:h-11",
                    on ? l.chip : "text-muted-foreground hover:bg-raised hover:text-foreground")}
                >
                  <span aria-hidden className={cn("size-1.5 rounded-[1px]", l.bar)} />
                  {l.label}
                  <span className="tabular-nums">{facets.level[l.id] ?? 0}</span>
                </button>
              );
            })}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
            <div className="relative col-span-2 sm:w-64">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search messages" className="pl-9" aria-label="Search messages" />
            </div>
            <Select value={filters.source || ANY} onValueChange={(v) => setFilter("source", v)}>
              <SelectTrigger className="col-span-2 w-full sm:w-44" aria-label="Source"><SelectValue placeholder="Source" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any source</SelectItem>
                {sources.map((s) => <SelectItem key={s} value={s}>{s}{facets.source[s] ? ` (${facets.source[s]})` : ""}</SelectItem>)}
              </SelectContent>
            </Select>
            <Input type="date" value={filters.date_from ?? ""} onChange={(e) => setFilter("date_from", e.target.value)} aria-label="From date" className="w-full sm:w-38" />
            <Input type="date" value={filters.date_to ?? ""} onChange={(e) => setFilter("date_to", e.target.value)} aria-label="To date" className="w-full sm:w-38" />
            {(filters.event || filters.post_id) && (
              <span className="col-span-2 inline-flex items-center gap-1 rounded-[4px] border border-rule px-2 py-1 font-mono text-xs break-all text-muted-foreground">
                {filters.event && <>event: {filters.event}*</>}{filters.post_id && <>post: {filters.post_id}</>}
              </span>
            )}
            {hasFilters && (
              <Button variant="ghost" size="sm" className="col-span-2 sm:col-span-1" onClick={() => { setSearch(""); setParams({}, { replace: true }); }}>
                <FilterX />
                Clear
              </Button>
            )}
          </div>
        </div>

        {error && <p role="alert" className="border-l-[3px] border-bad bg-bad/10 py-3 pr-4 pl-4 text-sm text-bad">{error}</p>}

        {/* the ledger */}
        {loading && !entries.length ? (
          <div className="grid gap-1.5" role="status" aria-label="Loading the log">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
        ) : !entries.length ? (
          <div className="grid justify-items-start gap-3 border-t border-dashed border-border py-14 sm:grid-cols-[auto_1fr] sm:gap-x-8">
            <span aria-hidden className="font-heading text-7xl leading-none font-bold text-transparent [-webkit-text-stroke:1px_var(--rule)]">00</span>
            <div className="grid content-center gap-1.5">
              <p className="font-heading text-lg font-semibold">{hasFilters ? "No entries match these filters" : "Nothing logged yet"}</p>
              <p className="max-w-prose text-sm text-muted-foreground">{hasFilters ? "Try clearing a filter." : "Approvals, publishes and sign-ins will show up here."}</p>
              {hasFilters && (
                <Button variant="outline" size="sm" className="mt-2 w-fit" onClick={() => { setSearch(""); setParams({}, { replace: true }); }}><FilterX />Clear filters</Button>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border bg-card/40" role="log" aria-label="Activity log" aria-live={live ? "polite" : "off"}>
            {groups.map((g) => (
              <section key={g.key} aria-label={dayLabel(g.key, now)}>
                <h2 className="sticky top-14 z-10 flex items-baseline gap-2 border-y bg-[color-mix(in_srgb,var(--muted)_94%,transparent)] px-4 py-1.5 font-mono text-xs font-semibold tracking-wide text-foreground backdrop-blur first:border-t-0 md:top-0">
                  {dayLabel(g.key, now)}
                  <span className="font-normal text-muted-foreground">{g.key} · {g.entries.length}</span>
                </h2>
                <ul>
                  {g.entries.map((e) => (
                    <Row key={e.id} e={e} open={openIds.has(e.id)} fresh={fresh.has(e.id)}
                         onToggle={() => setOpenIds((s) => { const n = new Set(s); if (n.has(e.id)) n.delete(e.id); else n.add(e.id); return n; })} />
                  ))}
                </ul>
              </section>
            ))}
            <div className="border-t p-3 text-center font-mono text-xs text-muted-foreground">
              {next ? (
                <Button variant="outline" size="sm" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? "Loading…" : "Load older entries"}
                </Button>
              ) : (
                <>— start of log · {entries.length} {entries.length === 1 ? "entry" : "entries"} · kept 90 days —</>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
