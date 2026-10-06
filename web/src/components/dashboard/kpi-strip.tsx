import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { fmtMinutes, pctText, ratioText, type Overview, type Rate } from "@/lib/dashboard-format";
import { cn } from "@/lib/utils";
import { CountUp, MONO, TEXT, Unavailable, Why, useDash } from "./primitives";

function Cell({ label, why, children, className }: { label: string; why: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0 content-start gap-1.5 bg-card p-3.5 sm:p-5", className ?? "grid")}>
      <div className="flex items-center gap-1.5"><span className={MONO}>{label}</span><Why label={label}>{why}</Why></div>
      {children}
    </div>
  );
}

const tone = (r: Rate) => (!r.judged || r.pct === null ? "text-foreground" : r.pct >= 85 ? TEXT.ok : r.pct < 60 ? TEXT.wait : "text-foreground");

function Big({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("font-heading text-3xl leading-none font-semibold tracking-tight sm:text-4xl", className)}>{children}</p>;
}

/** num/den as a rail: filled part = the numerator. A pattern, not only colour, shows when it's too few to judge. */
function Rail({ r }: { r: Rate }) {
  const pct = r.den ? (100 * r.num) / r.den : 0;
  return (
    <div aria-hidden className="mt-1 hidden h-1.5 overflow-hidden rounded-full bg-muted sm:block">
      <div className={cn("h-full rounded-full", r.judged ? "bg-primary" : "bg-muted-foreground/60")} style={{ width: `${pct}%` }} />
    </div>
  );
}

function RateBig({ r }: { r: Rate }) {
  return r.pct === null ? <Big className="text-muted-foreground">—</Big> : <Big className={tone(r)}><CountUp value={r.pct} format={(n) => `${Math.round(n)}%`} /></Big>;
}

function Judge({ r, note }: { r: Rate; note?: ReactNode }) {
  return (
    <p className="text-xs leading-snug text-muted-foreground">
      <span className="font-mono text-foreground/90">{ratioText(r)}</span>
      {!r.judged && <span className="ml-1.5 rounded border border-dashed px-1 py-px text-[10px] whitespace-nowrap">too few to judge</span>}
      {note && <span className="block">{note}</span>}
    </p>
  );
}

/** 30 slim bars, one per day, tallest = a full day. Pure shape; the numbers are in the text beside it. */
function DayBars({ cad }: { cad: Overview["cadence"] }) {
  if (!cad.ok) return null;
  const days = cad.days.slice(-30);
  const max = Math.max(cad.expected_per_day, ...days.map((d) => d.n), 1);
  return (
    <svg aria-hidden viewBox={`0 0 ${days.length * 6} 24`} className="mt-1 hidden h-6 w-full max-w-40 sm:block" preserveAspectRatio="none">
      {days.map((d, i) => {
        const h = d.state === "none" ? 1 : Math.max(1.5, (d.n / max) * 24);
        return <rect key={d.date} x={i * 6} y={24 - h} width="4" height={h} rx="1" className={d.state === "full" ? "fill-primary" : d.n ? "fill-primary/50" : "fill-muted-foreground/25"} />;
      })}
    </svg>
  );
}

function BinBars({ t }: { t: Overview["turnaround"] }) {
  if (!t.ok || !t.n) return null;
  const max = Math.max(...t.bins.map((b) => b.n), 1);
  return (
    <svg aria-hidden viewBox="0 0 50 24" className="mt-1 hidden h-6 w-full max-w-24 sm:block" preserveAspectRatio="none">
      {t.bins.map((b, i) => <rect key={b.label} x={i * 10} y={24 - Math.max(1.5, (b.n / max) * 24)} width="7" height={Math.max(1.5, (b.n / max) * 24)} rx="1" className="fill-[var(--brand-accent)]/70" />)}
    </svg>
  );
}

export function KpiStrip({ data }: { data: Overview }) {
  const { demo } = useDash();
  const k = data.kpis;
  if (!k.ok) return <Unavailable what="The key numbers" />;
  const w = data.window_days;
  const tta = k.time_to_approve;
  return (
    <section aria-label={`Key numbers, last ${w} days`} className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border lg:grid-cols-5">
      <Cell label="Posts published" why={<>Posts that went live in the last {w} days. A topic is one carousel plus one reel; deliveries count each platform.</>}>
        <Big><CountUp value={k.posts_published.count} /></Big>
        <p className="text-xs leading-snug text-muted-foreground">{k.posts_published.topics} topics · {k.posts_published.deliveries} platform deliveries</p>
        <DayBars cad={data.cadence} />
      </Cell>
      <Cell label="Approval rate" why={<>Of the drafts you decided on, how many you approved. Pending and expired drafts are not decisions, so they are left out and listed separately.</>}>
        <RateBig r={k.approval} />
        <Judge r={k.approval} note={<>first pass {pctText(k.approval.first_pass)} ({ratioText(k.approval.first_pass)}){k.approval.expired ? ` · ${k.approval.expired} expired, no decision` : ""}</>} />
        <Rail r={k.approval} />
      </Cell>
      <Cell label="Publish success" why={<>Platform deliveries that went live, out of those that reached a final result. Skipped platforms (not configured) are left out and listed.</>}>
        <RateBig r={k.publish_success} />
        <Judge r={k.publish_success} note={<>first attempt {pctText(k.publish_success.first_attempt)} ({ratioText(k.publish_success.first_attempt)}){k.publish_success.skipped_count ? ` · ${k.publish_success.skipped_count} skipped: ${k.publish_success.skipped[0]?.reason || "not configured"}` : ""}</>} />
        <Rail r={k.publish_success} />
      </Cell>
      <Cell label="Time to approve" why={<>Median time from draft created to your decision. An upper bound: the time shown is the last decision, and Telegram taps are applied when the next check runs, up to ~20 minutes after the tap.</>}>
        <Big className={tta.median_min === null ? "text-muted-foreground" : undefined}>
          {tta.median_min === null ? "—" : <CountUp value={tta.median_min} format={(n) => fmtMinutes(n)} />}
        </Big>
        <p className="text-xs leading-snug text-muted-foreground">
          <span className="font-mono text-foreground/90">median of {tta.n}</span>
          {!tta.judged && <span className="ml-1.5 rounded border border-dashed px-1 py-px text-[10px] whitespace-nowrap">too few to judge</span>}
          <span className="block">slowest 1 in 10: {fmtMinutes(tta.p90_min)} · upper bound</span>
        </p>
        <BinBars t={data.turnaround} />
      </Cell>
      <Cell label="On time" className="hidden lg:grid" why={<>Posts that went live within {k.punctuality.threshold_min} minutes of their slot, or of your approval if you approved late, so a late approval is never blamed on the system.</>}>
        <RateBig r={k.punctuality} />
        <Judge r={k.punctuality} note={`within ${k.punctuality.threshold_min} min of due`} />
        <Rail r={k.punctuality} />
      </Cell>
      {k.posts_published.count === 0 && !demo && (
        <p className="col-span-full bg-card p-4 text-sm text-muted-foreground">
          No posts in this period yet. <Link to="/generate" className="text-primary underline-offset-4 hover:underline">Open Generate</Link> to make the first one.
        </p>
      )}
    </section>
  );
}
