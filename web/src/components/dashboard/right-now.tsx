import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CircleAlert, Clock3, Film, Images, ShieldCheck, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { agoLabel, fmtMinutes, headline, stampIST, timeIST, untilLabel, type Overview, type Severity } from "@/lib/dashboard-format";
import { formatIST } from "@/lib/posts";
import { stageOf } from "@/lib/stage";
import { cn } from "@/lib/utils";
import { BG, DEMO_TIP, MONO, SampleMark, TEXT, Unavailable, useDash } from "./primitives";

const SEV: Record<Severity, { icon: typeof CircleAlert; tone: "bad" | "wait" | "idle"; word: string }> = {
  high: { icon: CircleAlert, tone: "bad", word: "Urgent" },
  medium: { icon: TriangleAlert, tone: "wait", word: "Soon" },
  low: { icon: Clock3, tone: "idle", word: "Waiting" },
};

/** An action that deep-links into Posts/Logs; in the demo it is a disabled button with an explanation. */
function ActionLink({ to, label }: { to: string; label: string }) {
  const { demo } = useDash();
  if (demo) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="inline-flex" aria-label={`${label} (${DEMO_TIP})`}>
            <Button variant="outline" size="sm" disabled className="pointer-events-none">{label}</Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{DEMO_TIP}</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <Button asChild variant="outline" size="sm" className="min-h-9">
      <Link to={to}>{label}<ArrowRight /></Link>
    </Button>
  );
}

const PEEK = 2; // rows shown before "show all" on wide screens (one on a phone, so the numbers stay on the first screen)

function Attention({ a }: { a: Overview["attention"] }) {
  const { now, demo } = useDash();
  const [open, setOpen] = useState(false);
  if (!a.ok) {
    return (
      <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm">
        <p className="font-medium text-destructive">Couldn't check what needs you.</p>
        <p className="mt-1 text-muted-foreground">This is not an all-clear. Open Posts to look yourself.</p>
        <Button asChild variant="outline" size="sm" className="mt-3"><Link to="/posts">Open Posts<ArrowRight /></Link></Button>
      </div>
    );
  }
  if (!a.items.length) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-[#2ea043]/30 bg-[#2ea043]/[0.07] p-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[#2ea043]/20 text-[#56d364]"><ShieldCheck className="size-5" aria-hidden /></span>
        <div>
          <p className="font-medium">Nothing needs you.</p>
          <p className="text-sm text-muted-foreground">{a.last_decision_at ? `Last decision ${agoLabel(a.last_decision_at, now)}.` : "No decisions yet."}</p>
        </div>
      </div>
    );
  }
  const hiddenWide = Math.max(0, a.items.length - PEEK);
  const hiddenPhone = a.items.length - 1;
  return (
    <div>
      <p className={cn(MONO, "mb-2 flex items-center gap-2")}>
        What needs you<span aria-hidden className="h-px flex-1 bg-border" /><span className="normal-case tracking-normal">most urgent first</span>
      </p>
      <ol id="attention-list" className="overflow-hidden rounded-xl border bg-background/40">
        {a.items.map((it, i) => {
          const s = SEV[it.severity];
          const Icon = s.icon;
          const tucked = !open && (i >= PEEK ? "hidden" : i >= 1 ? "hidden sm:flex" : "");
          return (
            <li key={`${it.code}-${it.post_id ?? i}`} className={cn("flex items-center gap-3 border-t px-3 py-2.5 first:border-t-0", tucked || "flex")}>
              <span className={cn("hidden size-8 shrink-0 place-items-center rounded-[10px] border sm:grid", TEXT[s.tone], it.severity === "high" ? "border-destructive/40 bg-destructive/10" : it.severity === "medium" ? "border-[var(--brand-accent)]/40 bg-[var(--brand-accent)]/10" : "border-border bg-muted/50")}>
                <Icon className="size-4" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm leading-snug font-medium"><span className="sr-only">{s.word}: </span>{it.title}</p>
                <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
                  <span className={cn("font-mono text-[10px] tracking-wide uppercase", TEXT[s.tone])}>{s.word}</span>
                  <span aria-hidden> · </span>{it.detail}
                  <span className="whitespace-nowrap"><span aria-hidden> · </span><span className="sr-only">waiting for </span>{fmtMinutes(it.age_min)}</span>
                </p>
              </div>
              <ActionLink to={it.action.to} label={it.action.label} />
            </li>
          );
        })}
      </ol>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {hiddenPhone > 0 && (
          <button type="button" aria-expanded={open} aria-controls="attention-list" onClick={() => setOpen((o) => !o)}
            className={cn("min-h-9 rounded-md text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring", !hiddenWide && "sm:hidden")}>
            {open ? "Show fewer" : <><span className="sm:hidden">Show {hiddenPhone} more</span><span className="hidden sm:inline">Show {hiddenWide} more</span></>}
          </button>
        )}
        {a.total > a.items.length && (
          <span>+{a.total - a.items.length} beyond these.{" "}
            {demo ? "" : <Link to="/posts" className="text-primary underline-offset-4 hover:underline">Open Posts</Link>}
          </span>
        )}
      </div>
    </div>
  );
}

function Chip({ icon: Icon, label, chip, now }: { icon: typeof Film; label: string; chip: NonNullable<Overview["next_slots"]["items"][number]["reel"]>; now: number }) {
  const stage = stageOf({ ...chip, platforms: chip.platforms as never, publish_at: chip.publish_at ?? new Date().toISOString(), status: chip.status as never }, formatIST(chip.publish_at, false), now);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-background/60 px-2 py-0.5 text-xs" title={stage.note}>
      <Icon className="size-3 text-muted-foreground" aria-hidden />
      <span className="text-muted-foreground">{label}</span>
      <span aria-hidden className={cn("size-1.5 rounded-full", BG[stage.tone])} />
      <span className={cn("font-medium", TEXT[stage.tone])}>{stage.title}</span>
    </span>
  );
}

function NextSlots({ n }: { n: Overview["next_slots"] }) {
  const { now } = useDash();
  if (!n.ok) return <Unavailable what="The slot timeline" />;
  if (!n.items.length) return <p className="text-sm text-muted-foreground">{n.configured ? "No upcoming slots." : "No posting slots are configured."}</p>;
  return (
    <ol className="relative grid gap-5">
      <span aria-hidden className="absolute top-2 bottom-2 left-[5px] w-px bg-border" />
      {n.items.map((s, i) => (
        <li key={s.slot_at} className="relative pl-6">
          <span aria-hidden className={cn("absolute top-1.5 left-0 size-[11px] rounded-full border-2 bg-background", i === 0 ? "border-primary shadow-[0_0_0_4px_color-mix(in_srgb,var(--brand-primary)_18%,transparent)]" : "border-muted-foreground/50")} />
          <div className="flex flex-wrap items-baseline gap-x-3">
            <span className="font-mono text-xl font-semibold tabular-nums">{s.label}</span>
            <span className={cn("text-sm", i === 0 ? "font-medium text-primary" : "text-muted-foreground")}>{untilLabel(s.slot_at, now)}</span>
            <span className={cn(MONO, "text-[10px]")}>{new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" }).format(new Date(s.slot_at))} IST</span>
          </div>
          {s.generated ? (
            <>
              <p className="mt-1 text-sm leading-snug">{s.topic}{s.category && <span className="text-muted-foreground"> · {s.category}</span>}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {s.reel && <Chip icon={Film} label="Reel" chip={s.reel} now={now} />}
                {s.carousel && <Chip icon={Images} label="Carousel" chip={s.carousel} now={now} />}
              </div>
            </>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">
              Not generated yet{s.generation_starts ? ` · generation starts about ${timeIST(s.generation_starts)}` : ""}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Band A: the one sentence (status + reason + next slot countdown) and what needs you. */
export function RightNow({ data }: { data: Overview }) {
  const { now } = useDash();
  const h = headline(data.status, now);
  const bar = h.tone === "bad" ? "bg-destructive" : h.tone === "wait" ? "bg-[var(--brand-accent)]" : h.tone === "ok" ? "bg-[#2ea043]" : "bg-muted-foreground/50";
  return (
    <section aria-labelledby="now-h" className="relative overflow-hidden rounded-2xl border bg-card">
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", bar)} />
      <SampleMark />
      <div className="grid content-start gap-3.5 p-4 pl-5 sm:gap-4 sm:p-6 sm:pl-8">
        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className={cn("inline-flex items-center gap-1.5 rounded-full border border-current/40 px-2.5 py-0.5 text-xs font-medium", TEXT[h.tone])}>
              <span aria-hidden className={cn("size-1.5 rounded-full", BG[h.tone], h.tone === "ok" && "motion-safe:animate-pulse")} />
              {h.label}
            </span>
            <span className={cn(MONO, "text-[10px]")}>as of <span className="sm:hidden">{timeIST(data.generated_at)}</span><span className="max-sm:hidden">{stampIST(data.generated_at)}</span> IST</span>
          </div>
          <h2 id="now-h" aria-live="polite" className="mt-2 font-heading text-[2rem] leading-[1.05] font-semibold tracking-tight sm:text-5xl">{h.title}</h2>
          <p className="mt-1.5 text-sm text-muted-foreground sm:text-base">{h.sub}</p>
        </div>
        <Attention a={data.attention} />
      </div>
    </section>
  );
}

/** Band B, right: the next four slots as a timeline. */
export function NextSlotsCard({ data }: { data: Overview }) {
  return (
    <section aria-labelledby="next-h" className="relative rounded-2xl border bg-[color-mix(in_srgb,var(--brand-bg)_55%,black)] p-4 sm:p-6">
      <SampleMark />
      <h2 id="next-h" className={cn(MONO, "mb-4")}>Going out next</h2>
      <NextSlots n={data.next_slots} />
    </section>
  );
}
