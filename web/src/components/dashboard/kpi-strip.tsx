import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlarmClock, CircleCheck, Send, ThumbsUp, Timer } from "lucide-react";

import { fmtMinutes, pctText, ratioText, type Overview, type Rate } from "@/lib/dashboard-format";
import { cn } from "@/lib/utils";
import { CountUp, TEXT, Unavailable, Why, useDash } from "./primitives";

/* The key numbers as one calm row (docs/design/references/dashboard-reference): icon, label, value, note. */

const tone = (r: Rate) => (!r.judged || r.pct === null ? "text-foreground" : r.pct >= 85 ? TEXT.ok : r.pct < 60 ? TEXT.wait : "text-foreground");

/** One number in the stats row: a soft round icon, a plain label, the value and a short note (reference: logip). */
function Stat({ icon: Icon, label, why, value, note, valueClass }: {
  icon: typeof Send; label: string; why: ReactNode; value: ReactNode; note: ReactNode; valueClass?: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-3.5 py-1 2xl:px-5 2xl:first:pl-0">
      <span aria-hidden className="grid size-11 shrink-0 place-items-center rounded-full bg-raised text-muted-foreground ring-1 ring-border">
        <Icon className="size-[18px]" />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">{label}<Why label={label}>{why}</Why></div>
        <p className={cn("mt-0.5 font-heading text-2xl leading-tight font-semibold tracking-tight", valueClass)}>{value}</p>
        <p className="truncate text-xs text-muted-foreground">{note}</p>
      </div>
    </div>
  );
}

const pctValue = (r: Rate) => (r.pct === null ? "—" : <CountUp value={r.pct} format={(n) => `${Math.round(n)}%`} />);
const pctTone = (r: Rate) => (r.pct === null ? "text-muted-foreground" : tone(r));

export function KpiStrip({ data }: { data: Overview }) {
  const { demo } = useDash();
  const k = data.kpis;
  if (!k.ok) return <Unavailable what="The key numbers" />;
  const w = data.window_days;
  const tta = k.time_to_approve;
  return (
    <section aria-label={`Key numbers, last ${w} days`} className="border-y border-border py-5">
      <div className="grid grid-cols-1 gap-x-6 gap-y-6 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 2xl:gap-x-0 2xl:divide-x 2xl:divide-border">
        <Stat icon={Send} label="Published"
          why={<>Posts that went live in the last {w} days. A topic is one carousel plus one reel; deliveries count each platform.</>}
          value={<CountUp value={k.posts_published.count} />} note={`${k.posts_published.topics} topics · ${k.posts_published.deliveries} deliveries`} />
        <Stat icon={ThumbsUp} label="Approved" valueClass={pctTone(k.approval)}
          why={<>Of the drafts you decided on, how many you approved. Pending and expired drafts are not decisions, so they are left out.</>}
          value={pctValue(k.approval)} note={<>{ratioText(k.approval)}{!k.approval.judged && " · too few to judge"}</>} />
        <Stat icon={CircleCheck} label="Published OK" valueClass={pctTone(k.publish_success)}
          why={<>Platform deliveries that went live, out of those that reached a final result. Skipped platforms are left out.</>}
          value={pctValue(k.publish_success)} note={<>first attempt {pctText(k.publish_success.first_attempt)}{!k.publish_success.judged && " · too few to judge"}</>} />
        <Stat icon={AlarmClock} label="On time" valueClass={pctTone(k.punctuality)}
          why={<>Posts that went live within {k.punctuality.threshold_min} minutes of their slot, or of your approval if you approved late.</>}
          value={pctValue(k.punctuality)} note={`within ${k.punctuality.threshold_min} min of due`} />
        <Stat icon={Timer} label="Time to approve" valueClass={tta.median_min === null ? "text-muted-foreground" : undefined}
          why={<>Median time from draft created to your decision. An upper bound: Telegram taps are applied when the next check runs, up to ~20 minutes after the tap.</>}
          value={tta.median_min === null ? "—" : <CountUp value={tta.median_min} format={(n) => fmtMinutes(n)} />}
          note={<>median of {tta.n} · slowest 1 in 10: {fmtMinutes(tta.p90_min)}</>} />
      </div>
      {k.posts_published.count === 0 && !demo && (
        <p className="mt-4 text-sm text-muted-foreground">
          No posts in this period yet. <Link to="/generate" className="text-primary underline-offset-4 hover:underline">Open Generate</Link> to make the first one.
        </p>
      )}
    </section>
  );
}
