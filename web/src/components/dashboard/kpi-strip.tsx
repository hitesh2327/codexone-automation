import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { fmtMinutes, pctText, ratioText, type Overview, type Rate } from "@/lib/dashboard-format";
import { cn } from "@/lib/utils";
import { CountUp, MONO, TEXT, Unavailable, Why, useDash } from "./primitives";

/*
 * The key numbers, deliberately NOT five equal stat cards (design-system.md section 13). Three shapes, each
 * shaped by what the number is:
 *   - the lead: what shipped, as one large numeral with the 30-day pulse under it;
 *   - the rates: three percentages that are judged the same way, set as a ledger (label .... value);
 *   - the turnaround: a duration with its spread, as a figure plus a five-bin histogram.
 */

const tone = (r: Rate) => (!r.judged || r.pct === null ? "text-foreground" : r.pct >= 85 ? TEXT.ok : r.pct < 60 ? TEXT.wait : "text-foreground");

const TOO_FEW = <span className="ml-1.5 rounded-[3px] border border-dashed px-1 py-px text-[10px] whitespace-nowrap">too few to judge</span>;

/** num/den as a rail: filled part = the numerator. A pattern, not only colour, shows when it's too few to judge. */
function Rail({ r }: { r: Rate }) {
  const pct = r.den ? (100 * r.num) / r.den : 0;
  return (
    <div aria-hidden className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
      <div className={cn("h-full rounded-full", r.judged ? "bg-go/80" : "bg-muted-foreground/60")} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** 30 slim bars, one per day, tallest = a full day. Pure shape; the numbers are in the text beside it. */
function DayBars({ cad }: { cad: Overview["cadence"] }) {
  if (!cad.ok) return null;
  const days = cad.days.slice(-30);
  const max = Math.max(cad.expected_per_day, ...days.map((d) => d.n), 1);
  return (
    <svg aria-hidden viewBox={`0 0 ${days.length * 6} 24`} className="mt-4 h-7 w-full" preserveAspectRatio="none">
      {days.map((d, i) => {
        const h = d.state === "none" ? 1 : Math.max(1.5, (d.n / max) * 24);
        return <rect key={d.date} x={i * 6} y={24 - h} width="4" height={h} rx="1" className={d.state === "full" ? "fill-go/80" : d.n ? "fill-go/45" : "fill-muted-foreground/25"} />;
      })}
    </svg>
  );
}

function BinBars({ t }: { t: Overview["turnaround"] }) {
  if (!t.ok || !t.n) return null;
  const max = Math.max(...t.bins.map((b) => b.n), 1);
  return (
    <svg aria-hidden viewBox="0 0 50 24" className="mt-4 h-7 w-full max-w-36" preserveAspectRatio="none">
      {t.bins.map((b, i) => <rect key={b.label} x={i * 10} y={24 - Math.max(1.5, (b.n / max) * 24)} width="7" height={Math.max(1.5, (b.n / max) * 24)} rx="1" className="fill-wait/70" />)}
    </svg>
  );
}

/** One rate in the ledger: label + (i), dotted leader, the percentage; the ratio and its note below; the rail. */
function RateRow({ label, why, r, note }: { label: string; why: ReactNode; r: Rate; note: ReactNode }) {
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-baseline gap-2">
        <span className={MONO}>{label}</span>
        <span className="self-center"><Why label={label}>{why}</Why></span>
        <span aria-hidden className="leader" />
        <span className={cn("font-heading text-2xl leading-none font-semibold tracking-tight", r.pct === null ? "text-muted-foreground" : tone(r))}>
          {r.pct === null ? "—" : <CountUp value={r.pct} format={(n) => `${Math.round(n)}%`} />}
        </span>
      </div>
      <p className="mt-1 text-xs leading-snug text-muted-foreground">
        <span className="font-mono text-foreground/90">{ratioText(r)}</span>
        {!r.judged && TOO_FEW}
        <span> · {note}</span>
      </p>
      <Rail r={r} />
    </li>
  );
}

export function KpiStrip({ data }: { data: Overview }) {
  const { demo } = useDash();
  const k = data.kpis;
  if (!k.ok) return <Unavailable what="The key numbers" />;
  const w = data.window_days;
  const tta = k.time_to_approve;
  return (
    <section
      aria-label={`Key numbers, last ${w} days`}
      className="grid grid-cols-2 overflow-hidden rounded-xl border border-border bg-card/40 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1.6fr)_minmax(0,1fr)]"
    >
      {/* the lead: what shipped */}
      <div className="min-w-0 border-r border-border p-4 sm:p-6 lg:border-r-0">
        <div className="flex items-center gap-1.5">
          <span className={MONO}>Posts published</span>
          <Why label="Posts published">Posts that went live in the last {w} days. A topic is one carousel plus one reel; deliveries count each platform.</Why>
        </div>
        <p className="mt-3 font-heading text-5xl leading-none font-semibold tracking-tight sm:text-6xl"><CountUp value={k.posts_published.count} /></p>
        <p className="mt-2 text-xs leading-snug text-muted-foreground">{k.posts_published.topics} topics · {k.posts_published.deliveries} platform deliveries</p>
        <DayBars cad={data.cadence} />
      </div>

      {/* the turnaround: phone keeps it beside the lead; wide screens put it last */}
      <div className="min-w-0 p-4 sm:p-6 lg:order-3 lg:border-l lg:border-border">
        <div className="flex items-center gap-1.5">
          <span className={MONO}>Time to approve</span>
          <Why label="Time to approve">Median time from draft created to your decision. An upper bound: the time shown is the last decision, and Telegram taps are applied when the next check runs, up to ~20 minutes after the tap.</Why>
        </div>
        <p className={cn("mt-3 font-heading text-3xl leading-none font-semibold tracking-tight sm:text-4xl", tta.median_min === null && "text-muted-foreground")}>
          {tta.median_min === null ? "—" : <CountUp value={tta.median_min} format={(n) => fmtMinutes(n)} />}
        </p>
        <p className="mt-2 text-xs leading-snug text-muted-foreground">
          <span className="font-mono text-foreground/90">median of {tta.n}</span>
          {!tta.judged && TOO_FEW}
          <span className="block">slowest 1 in 10: {fmtMinutes(tta.p90_min)} · upper bound</span>
        </p>
        <BinBars t={data.turnaround} />
      </div>

      {/* the rates: one ledger */}
      <ul className="col-span-2 min-w-0 border-t border-border p-4 sm:p-6 lg:order-2 lg:col-span-1 lg:border-t-0 lg:border-l" aria-label="Rates">
        <RateRow
          label="Approval rate" r={k.approval}
          why={<>Of the drafts you decided on, how many you approved. Pending and expired drafts are not decisions, so they are left out and listed separately.</>}
          note={<>first pass {pctText(k.approval.first_pass)} ({ratioText(k.approval.first_pass)}){k.approval.expired ? ` · ${k.approval.expired} expired, no decision` : ""}</>}
        />
        <RateRow
          label="Publish success" r={k.publish_success}
          why={<>Platform deliveries that went live, out of those that reached a final result. Skipped platforms (not configured) are left out and listed.</>}
          note={<>first attempt {pctText(k.publish_success.first_attempt)} ({ratioText(k.publish_success.first_attempt)}){k.publish_success.skipped_count ? ` · ${k.publish_success.skipped_count} skipped: ${k.publish_success.skipped[0]?.reason || "not configured"}` : ""}</>}
        />
        <RateRow
          label="On time" r={k.punctuality}
          why={<>Posts that went live within {k.punctuality.threshold_min} minutes of their slot, or of your approval if you approved late, so a late approval is never blamed on the system.</>}
          note={`within ${k.punctuality.threshold_min} min of due`}
        />
      </ul>

      {k.posts_published.count === 0 && !demo && (
        <p className="col-span-full border-t border-border p-4 text-sm text-muted-foreground lg:order-4">
          No posts in this period yet. <Link to="/generate" className="text-primary underline-offset-4 hover:underline">Open Generate</Link> to make the first one.
        </p>
      )}
    </section>
  );
}
