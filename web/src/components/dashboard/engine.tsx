import { agoLabel, dayIST, fmtMinutes, pctText, ratioText, type Overview, type Rate } from "@/lib/dashboard-format";
import type { Tone } from "@/lib/stage";
import { cn } from "@/lib/utils";
import { BG, CountUp, Empty, MONO, TEXT, Unavailable, Why, useDash } from "./primitives";

function Row({ label, tone, word, children, hint }: { label: string; tone: Tone; word: string; children: React.ReactNode; hint?: string }) {
  return (
    <li className="flex items-baseline gap-2.5 py-2.5">
      <span aria-hidden className={cn("relative top-px size-2 shrink-0 self-center rounded-full", BG[tone])} />
      <span className="sr-only">{word}:</span>
      <span className="shrink-0 font-mono text-xs tracking-wide uppercase">{label}</span>
      <span aria-hidden className="leader min-w-4 flex-1" />
      <span className="text-right font-mono text-sm">{children}</span>
      {hint && <span className="sr-only">{hint}</span>}
    </li>
  );
}

const rateTone = (r: Rate): Tone => (!r.judged || r.pct === null ? "idle" : r.pct >= 90 ? "ok" : r.pct >= 70 ? "wait" : "bad");
const rateWord = (r: Rate) => (!r.judged || r.pct === null ? "Too few to judge" : r.pct >= 90 ? "Healthy" : r.pct >= 70 ? "Watch" : "Poor");

/** The engine's vital signs as a console readout: LED, label, dotted leader, value. */
export function PipelineConsole({ data }: { data: Overview }) {
  const { now } = useDash();
  const p = data.pipeline;
  if (!p.ok) return <Unavailable what="Pipeline health" />;
  const g = p.generation;
  const pub = p.publishing;
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center justify-between">
        <p className={MONO}>Engine · last {data.window_days} days</p>
        <Why label="pipeline health">Slot fill rate comes from posts and works from day one. Generation figures come from recorded runs and say "tracking since" when the history is short.</Why>
      </div>
      <ul className="divide-y divide-border/60">
        <Row label="Slots filled" tone={rateTone(p.slot_fill)} word={rateWord(p.slot_fill)}>
          {p.slot_fill.den ? <>{ratioText(p.slot_fill)} <span className="text-muted-foreground">({pctText(p.slot_fill)})</span></> : <span className="text-muted-foreground">no slots yet</span>}
        </Row>
        {g.ok ? (
          g.runs === 0 && !g.tracking_since ? (
            <Row label="Generation runs" tone="idle" word="No history">
              <span className="text-muted-foreground">tracking starts at go-live</span>
            </Row>
          ) : (
            <>
              <Row label="Generation runs" tone={g.success ? rateTone(g.success) : "idle"} word={g.success ? rateWord(g.success) : "No data"}>
                {g.success && g.success.den ? <>{ratioText(g.success)} succeeded <span className="text-muted-foreground">({pctText(g.success)})</span></> : <span className="text-muted-foreground">none in this period</span>}
              </Row>
              <Row label="Success streak" tone={g.streak ? "ok" : "idle"} word={g.streak ? "Running" : "None"}>{g.streak ?? 0} in a row</Row>
              <Row label="Last run" tone={g.last?.status === "failed" ? "bad" : g.last ? "ok" : "idle"} word={g.last?.status === "failed" ? "Failed" : "OK"}>
                {g.last ? <>{agoLabel(g.last.at, now)} <span className="text-muted-foreground">· {g.last.status}</span></> : "—"}
              </Row>
              <Row label="Last failure" tone="idle" word="Info">{g.last_failure ?? <span className="text-muted-foreground">none</span>}</Row>
              {(g.skipped || g.cancelled) ? <Row label="Skipped / cancelled" tone="idle" word="Info">{g.skipped ?? 0} / {g.cancelled ?? 0}</Row> : null}
            </>
          )
        ) : (
          <Row label="Generation runs" tone="idle" word="Unavailable"><span className="text-muted-foreground">unavailable</span></Row>
        )}
        <Row label="Last post live" tone={pub.last_published_at ? "ok" : "idle"} word={pub.last_published_at ? "OK" : "None yet"}>
          {pub.last_published_at ? <>{agoLabel(pub.last_published_at, now)}</> : <span className="text-muted-foreground">nothing yet</span>}
        </Row>
        <Row label="Failed deliveries" tone={pub.failed_deliveries ? "wait" : "ok"} word={pub.failed_deliveries ? "Watch" : "None"}>{pub.failed_deliveries}</Row>
      </ul>
      {g.ok && g.tracking_since && <p className="mt-3 text-[11px] text-muted-foreground">Generation history tracked since {dayIST(g.tracking_since)}.</p>}
    </div>
  );
}

/** How fast decisions come: median / slowest-in-ten, a five-bar histogram, and where the decisions are made. */
export function Turnaround({ data }: { data: Overview }) {
  const t = data.turnaround;
  if (!t.ok) return <Unavailable what="Approval turnaround" />;
  if (!t.n) return <Empty title="No decisions in this period yet">Turnaround appears once you have approved something.</Empty>;
  const max = Math.max(...t.bins.map((b) => b.n), 1);
  return (
    <div className="min-w-0 max-lg:border-t max-lg:border-dashed max-lg:pt-5 lg:border-l lg:pl-8">
      <div className="flex items-start justify-between gap-3">
        <div className="flex gap-8">
          <div>
            <p className={cn(MONO, "mb-1")}>Median</p>
            <p className="font-heading text-3xl leading-none font-semibold">{t.median_min === null ? "—" : <CountUp value={t.median_min} format={fmtMinutes} />}</p>
          </div>
          <div>
            <p className={cn(MONO, "mb-1")}>Slowest 1 in 10</p>
            <p className="font-heading text-3xl leading-none font-semibold text-muted-foreground">{fmtMinutes(t.p90_min)}</p>
          </div>
        </div>
        <Why label="time to approve">An upper bound. It uses your last decision, and Telegram taps are applied when the next check runs (up to ~20 minutes later).</Why>
      </div>
      <div role="img" aria-label={`How long decisions took: ${t.bins.map((b) => `${b.label}: ${b.n}`).join(", ")}.`} className="mt-5 grid grid-cols-5 items-end gap-2">
        {t.bins.map((b) => (
          <div key={b.label} className="grid justify-items-center gap-1.5">
            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{b.n}</span>
            <div className="flex h-24 w-full items-end"><div className="w-full rounded-t-[3px] bg-wait/75" style={{ height: `${Math.max(b.n ? 4 : 1, (b.n / max) * 100)}%` }} /></div>
            <span className="text-center text-[10px] leading-tight text-muted-foreground">{b.label.replace("under ", "< ").replace(" or more", "+")}</span>
          </div>
        ))}
      </div>
      <div className="sr-only"><table><caption>Decision time, {t.n} decisions</caption><tbody>{t.bins.map((b) => <tr key={b.label}><th scope="row">{b.label}</th><td>{b.n}</td></tr>)}</tbody></table></div>
      {t.channels.length > 0 && (
        <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
          Decided in{" "}
          {t.channels.map((c, i) => (
            <span key={c.channel}>{i ? " · " : ""}<strong className={cn("font-medium", TEXT.go)}>{c.channel === "telegram" ? "Telegram" : "the dashboard"}</strong> {c.n} (median {fmtMinutes(c.median_min)})</span>
          ))}
        </p>
      )}
    </div>
  );
}

