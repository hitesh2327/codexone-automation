import { LEAK_TEXT, deltaText, funnelShape, mixNote, sharePct, type Overview } from "@/lib/dashboard-format";
import { cn } from "@/lib/utils";
import { CountUp, Empty, MONO, Unavailable } from "./primitives";

const STAGE_TEXT = ["Everything the AI drafted", "Got a decision", "You approved", "Went live"];

/** Generated -> decided -> approved -> published, drawn as bars joined by flowing bands. Labels are real text. */
export function Funnel({ data }: { data: Overview }) {
  const f = data.funnel;
  if (!f.ok) return <Unavailable what="The funnel" />;
  if (!f.total) return <Empty title="No posts in this period yet">Drafts appear here after the daily generation runs.</Empty>;
  const g = funnelShape(f.stages.map((s) => s.n), 400, 130);
  const regen = f.buckets.regenerated ?? 0;
  const leaks = f.leaks.filter((l) => l.n > 0);
  return (
    <div className="rounded-xl border bg-card p-5 sm:p-6">
      <div role="img" aria-label={`Funnel over ${data.window_days} days: ${f.stages.map((s) => `${s.label} ${s.n}`).join(", ")}.`}>
        <svg viewBox={`0 0 ${g.w} ${g.h}`} preserveAspectRatio="none" className="h-36 w-full" aria-hidden>
          {g.bands.map((d, i) => <path key={i} d={d} className="fill-primary/15" />)}
          {g.bars.map((b, i) => <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h} rx="2" className={i === g.bars.length - 1 ? "fill-[#2ea043]" : "fill-primary"} />)}
        </svg>
        <div className="mt-2 grid grid-cols-4">
          {f.stages.map((s, i) => (
            <div key={s.key} className="min-w-0 pr-1">
              <p className="font-heading text-2xl leading-none font-semibold tabular-nums sm:text-3xl"><CountUp value={s.n} /></p>
              <p className="mt-1 text-xs font-medium">{s.label}</p>
              <p className={cn(MONO, "mt-0.5 text-[10px]")}>{i ? `${sharePct(s.n, f.total)}%` : "100%"}</p>
              <p className="mt-1 hidden text-[11px] leading-snug text-muted-foreground sm:block">{STAGE_TEXT[i]}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 border-t pt-4">
        <p className={cn(MONO, "mb-2")}>Where the rest went</p>
        <ul className="flex flex-wrap gap-2">
          {leaks.length ? leaks.map((l) => (
            <li key={l.key} className="rounded-full border px-2.5 py-1 text-xs">
              <strong className="tabular-nums">{l.n}</strong> <span className="text-muted-foreground">{LEAK_TEXT[l.key] ?? l.key}</span>
            </li>
          )) : <li className="text-xs text-muted-foreground">Nothing dropped out.</li>}
        </ul>
        {regen > 0 && <p className="mt-3 text-xs leading-snug text-muted-foreground">{regen} sent back to regenerate: that is you steering quality, not a failure. The AI proposes; you decide.</p>}
      </div>
      <div className="sr-only"><table>
        <caption>Funnel, last {data.window_days} days</caption>
        <tbody>
          {f.stages.map((s) => <tr key={s.key}><th scope="row">{s.label}</th><td>{s.n}</td></tr>)}
          {f.leaks.map((l) => <tr key={l.key}><th scope="row">{LEAK_TEXT[l.key] ?? l.key}</th><td>{l.n}</td></tr>)}
        </tbody>
      </table></div>
    </div>
  );
}

/** Share of topics per category against the target weight (the amber tick). Deviation is only coloured when n is big enough. */
export function Mix({ data }: { data: Overview }) {
  const m = data.mix;
  if (!m.ok) return <Unavailable what="Content mix" />;
  if (!m.n) return <Empty title="No topics in this period yet">The mix is counted per topic, once there are some.</Empty>;
  const max = Math.max(40, ...m.categories.flatMap((c) => [c.share, c.target ?? 0]));
  return (
    <div className="rounded-xl border bg-card p-5 sm:p-6">
      <ul className="grid gap-3.5" aria-label="Topic share by category against target">
        {m.categories.map((c) => (
          <li key={c.category}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-mono text-xs tracking-wide">{c.category}</span>
              <span className="text-right text-xs text-muted-foreground">
                <span className="font-mono text-foreground">{c.share.toFixed(0)}%</span> · {c.count} topic{c.count === 1 ? "" : "s"}
              </span>
            </div>
            <div className="relative mt-1.5 h-2.5 rounded-full bg-muted">
              <div className={cn("h-full rounded-full", c.tone === "off" ? "bg-[var(--brand-accent)]" : c.tone === "on" ? "bg-primary" : "bg-muted-foreground/60")} style={{ width: `${(c.share / max) * 100}%` }} />
              {c.target !== null && <span aria-hidden className="absolute -top-1 h-4.5 w-0.5 rounded bg-foreground" style={{ left: `calc(${(c.target / max) * 100}% - 1px)` }} />}
            </div>
            <p className={cn("mt-1 text-[11px]", c.tone === "off" ? "text-[var(--brand-accent)]" : "text-muted-foreground")}>
              {deltaText(c, m.judged)}{c.tone === "off" ? ", outside the normal range" : ""}
            </p>
          </li>
        ))}
      </ul>
      <p className="mt-4 flex items-start gap-2 border-t pt-3 text-xs leading-snug text-muted-foreground">
        <span aria-hidden className="mt-0.5 inline-block h-3.5 w-0.5 shrink-0 rounded bg-foreground" />
        <span>Line = your target. {mixNote(m)}</span>
      </p>
    </div>
  );
}
