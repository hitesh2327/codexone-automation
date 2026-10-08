import { Link } from "react-router-dom";
import { CircleCheck, CircleX, ExternalLink, Film, Images, Sparkles, TriangleAlert, ShieldCheck, ThumbsUp, ThumbsDown, RefreshCw, Hourglass, Clapperboard } from "lucide-react";

import { FEED_VERB, agoLabel, pctText, ratioText, stampIST, timeIST, type Overview } from "@/lib/dashboard-format";
import { cn, safeHref } from "@/lib/utils";
import { DEMO_TIP, Empty, MONO, TEXT, Unavailable, useDash } from "./primitives";

const PLATFORM_NOTE: Record<string, string> = { private: "Private: not public yet", unlisted: "Unlisted: only people with the link", public: "Public" };

export function Platforms({ data }: { data: Overview }) {
  const { demo, now } = useDash();
  const p = data.platforms;
  if (!p.ok) return <Unavailable what="Platform results" />;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
      {p.items.map((pl) => (
        <article key={pl.platform} aria-label={pl.name} className="min-w-0 rounded-xl border bg-card">
          <header className="flex items-start justify-between gap-3 border-b p-4 sm:p-5">
            <div>
              <h3 className="font-heading font-semibold">{pl.platform === "ig" ? "Instagram" : "YouTube Shorts"}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                <span className={cn("font-mono", TEXT.ok)}>{pl.published}</span> published ·{" "}
                <span className={cn("font-mono", pl.failed ? TEXT.bad : "")}>{pl.failed}</span> failed ·{" "}
                <span className="font-mono">{pl.skipped}</span> skipped
              </p>
            </div>
            <div className="text-right">
              <p className="font-heading text-2xl leading-none font-semibold">{pctText(pl.success)}</p>
              <p className="mt-1 font-mono text-[10px] text-muted-foreground">{pl.success.den ? ratioText(pl.success) : "no data"}{pl.success.den && !pl.success.judged ? " · too few to judge" : ""}</p>
            </div>
          </header>
          {pl.recent.length === 0 ? (
            <Empty title="Nothing published here yet" className="border-0" />
          ) : (
            <ul className="divide-y">
              {pl.recent.map((r) => (
                <li key={r.post_id + r.at} className="flex items-center gap-3 px-4 py-3 sm:px-5">
                  <span aria-hidden className="text-muted-foreground">{r.kind === "reel" ? <Film className="size-4" /> : <Images className="size-4" />}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{r.topic}</p>
                    <p className="text-xs text-muted-foreground">{r.at ? agoLabel(r.at, now) : "—"}{r.privacy && <span className={cn("ml-2 rounded border px-1 py-px text-[10px]", r.privacy === "private" && "border-wait/50 text-wait")} title={PLATFORM_NOTE[r.privacy]}>{r.privacy}{r.privacy === "private" ? " · not public" : ""}</span>}</p>
                  </div>
                  {safeHref(r.url) && !demo ? (
                    <a href={safeHref(r.url)} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-9 items-center gap-1 rounded-md px-2 text-xs text-primary hover:bg-muted">
                      Open<ExternalLink className="size-3" aria-hidden /><span className="sr-only"> on {pl.name} (new tab)</span>
                    </a>
                  ) : (
                    <span className="px-2 text-xs text-muted-foreground" title={demo ? DEMO_TIP : "No link recorded"}>{demo ? "sample" : "no link"}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </article>
      ))}
    </div>
  );
}

const GLYPH: Record<string, string> = { AI: "AI", SystemDesign: "SD", DSA: "DSA", Interview: "IV", OS: "OS", Dev: "DEV" };

/** Used when there's no slide thumbnail (always, in the demo): a typographic tile, never a fake image. */
function Poster({ category, index }: { category: string; index: number }) {
  return (
    <div className="relative grid h-full w-full content-between overflow-hidden bg-[color-mix(in_srgb,var(--brand-primary)_7%,var(--brand-bg))] p-2.5">
      <span className="truncate font-mono text-[10px] tracking-wider text-primary uppercase">{category === "SystemDesign" ? "Sys design" : category || "topic"}</span>
      <span aria-hidden className="font-heading text-4xl leading-none font-bold text-transparent [-webkit-text-stroke:1px_color-mix(in_srgb,var(--brand-primary)_55%,transparent)]">{GLYPH[category] ?? (category.slice(0, 3).toUpperCase() || "·")}</span>
      <span aria-hidden className="absolute right-2.5 bottom-2 font-mono text-[10px] text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
    </div>
  );
}

export function Gallery({ data }: { data: Overview }) {
  const { demo, now } = useDash();
  const r = data.recent_posts;
  if (!r.ok) return <Unavailable what="Recently shipped" />;
  if (!r.items.length) return <Empty title="Nothing has gone live yet">The last eight topics appear here, newest first.</Empty>;
  return (
    <ul tabIndex={demo ? 0 : undefined} className="relative flex snap-x gap-3 overflow-x-auto rounded-lg pb-2 [scrollbar-width:thin] lg:grid lg:grid-cols-8 lg:overflow-visible" aria-label="Last topics that went live">
      {r.items.map((it, idx) => {
        const inner = (
          <>
            <div className="aspect-[4/5] overflow-hidden rounded-lg border bg-muted">
              {it.thumb && !demo ? <img src={it.thumb} alt="" loading="lazy" referrerPolicy="no-referrer" className="size-full object-cover" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} /> : <Poster category={it.category} index={idx} />}
            </div>
            <div className="mt-2 grid gap-1">
              <p className="line-clamp-2 text-xs leading-snug font-medium">{it.topic}</p>
              <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                <span>{it.at ? agoLabel(it.at, now) : "—"}</span>
              </p>
              <p className="flex flex-wrap gap-1">
                {it.chips.map((c, i) => (
                  <span key={i} className={cn("inline-flex items-center gap-0.5 rounded border px-1.5 py-px font-mono text-[10px] uppercase", c.status === "published" ? "border-ok/40 text-ok" : c.status === "failed" ? "border-bad/40 text-bad" : "text-muted-foreground")}>
                    {c.platform}{c.kind === "reel" ? " reel" : " post"}<span className="sr-only"> {c.status}</span>
                  </span>
                ))}
              </p>
            </div>
          </>
        );
        return (
          <li key={it.group_id} className="w-32 shrink-0 snap-start lg:w-auto">
            {demo ? <div title={DEMO_TIP}>{inner}</div> : (
              <Link to={`/posts?post=${encodeURIComponent(it.post_id)}`} className="block rounded-lg">{inner}</Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const FEED_ICON: Record<string, typeof Sparkles> = {
  "post.generated": Sparkles, "post.regenerated": RefreshCw, "post.approved": ThumbsUp, "post.scheduled": Hourglass,
  "post.rejected": ThumbsDown, "post.published": CircleCheck, "publish.failed": CircleX, "post.expired": Hourglass,
  "generate.finished": Clapperboard, "generate.failed": TriangleAlert,
};

const VERB_PREFIX = /^(published|approved|rejected|generated|regenerated|scheduled)\s+/i;
const TAG_TONE: Record<string, string> = {
  "post.published": "text-ok", "publish.failed": "text-bad", "generate.failed": "text-bad",
  "post.approved": "text-primary", "post.scheduled": "text-primary", "post.rejected": "text-muted-foreground", "post.expired": "text-muted-foreground",
};

/** The last 15 things that happened, as a ledger: time, what, who. Actors are role labels only. */
export function Feed({ data }: { data: Overview }) {
  const { demo, now } = useDash();
  const a = data.activity;
  if (!a.ok) return <Unavailable what="The activity feed" />;
  return (
    <div className="rounded-xl border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-x-4 border-b px-4 py-2 sm:px-5">
        <p className={MONO}>Activity ledger · last {a.items.length}</p>
        {demo ? <span className="text-xs text-muted-foreground" title={DEMO_TIP}>Logs off in the demo</span> : (
          <Link to="/logs" className="inline-flex min-h-9 items-center text-xs text-primary underline-offset-4 hover:underline">View all in Logs</Link>
        )}
      </div>
      {a.items.length === 0 ? <Empty title="Activity will appear here" className="border-0">Approvals, publishes and failures are listed as they happen.</Empty> : (
        <ol className="divide-y divide-dashed font-mono text-xs">
          {a.items.map((e) => {
            const Icon = FEED_ICON[e.event] ?? ShieldCheck;
            const msg = e.message.replace(VERB_PREFIX, "");
            return (
              <li key={e.id} className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-3 px-4 py-2.5 sm:grid-cols-[4.5rem_minmax(0,1fr)_5.5rem] sm:px-5">
                <time dateTime={e.at} title={`${stampIST(e.at)} IST`} className="text-muted-foreground tabular-nums">
                  {timeIST(e.at)}<span className="block text-[10px] text-muted-foreground">{agoLabel(e.at, now)}</span>
                </time>
                <p className="min-w-0 font-sans text-sm leading-snug break-words">
                  <span className={cn("mr-1.5 inline-flex items-center gap-1 font-mono text-[10px] tracking-wide uppercase", TAG_TONE[e.event] ?? "text-muted-foreground")}>
                    <Icon className="size-3" aria-hidden />{FEED_VERB[e.event] ?? e.event}
                  </span>
                  <span className="text-foreground/85">{msg ? msg.charAt(0).toUpperCase() + msg.slice(1) : ""}</span>
                  <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground sm:hidden">by {e.actor}</span>
                </p>
                <span className="hidden text-right text-[11px] text-muted-foreground sm:block">{e.actor}</span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

/** Honest placeholder: the product does not measure reach or followers, so no figures are shown. */
export function Roadmap() {
  return (
    <aside className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
      <span className={cn(MONO, "rounded border px-1.5 py-px text-[10px]")}>On the roadmap</span>
      <span>Engagement analytics. Likes, reach and follower growth are not measured yet, so nothing is shown here rather than something made up.</span>
    </aside>
  );
}
