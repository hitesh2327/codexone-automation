import { useMemo, useRef, useState } from "react";
import { Flame } from "lucide-react";

import { MONTHS, cadenceSummary, cellSummary, dayText, heatGrid, stateWord, type CadenceDay, type Overview } from "@/lib/dashboard-format";
import { cn } from "@/lib/utils";
import { CountUp, Empty, MONO, Unavailable } from "./primitives";

const CELL: Record<CadenceDay["state"], string> = {
  // a calm, filled cyan: done days are the norm, so they must not out-shout what needs you (today keeps full cyan)
  full: "bg-go/35 border-go/45",
  // diagonal hatching, so "partly" is not told apart from "full" by colour alone
  partial: "border-primary/60 bg-[repeating-linear-gradient(135deg,color-mix(in_srgb,var(--brand-primary)_55%,transparent)_0_2px,transparent_2px_5px)]",
  missed: "border-dashed border-wait bg-wait/10",
  today: "border-2 border-go bg-go/10 motion-safe:animate-pulse",
  none: "border-transparent bg-muted-foreground/15",
};
const LABEL_ROWS = ["Mon", "", "Wed", "", "Fri", "", ""];

export function Cadence({ data }: { data: Overview }) {
  const c = data.cadence;
  const grid = useMemo(() => (c.ok ? heatGrid(c.days) : []), [c]);
  const [active, setActive] = useState<string | null>(null);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const flat = grid.flat();
  const lastReal = c.ok ? c.days[c.days.length - 1]?.date : null;
  const focusDate = active ?? lastReal;

  if (!c.ok) return <Unavailable what="The cadence heatmap" />;
  if (!c.days.some((d) => d.state !== "none")) return <Empty title="Your first day will show up here">Once the first post is generated, each day gets a cell: filled when everything went out.</Empty>;

  const shown = flat.find((d) => d?.date === (active ?? lastReal)) ?? null;

  function onKey(e: React.KeyboardEvent, idx: number) {
    const move = { ArrowRight: 7, ArrowLeft: -7, ArrowDown: 1, ArrowUp: -1 }[e.key];
    if (move === undefined) return;
    e.preventDefault();
    let i = idx + move;
    const step = Math.sign(move);
    while (i >= 0 && i < flat.length && !flat[i]) i += step; // skip padding cells
    const target = flat[i];
    if (target) { setActive(target.date); refs.current[target.date]?.focus(); }
  }

  const big = c.days.length <= 31;        // 30 days: a calendar with dates; 90 days: a dense strip
  const cell = big ? "2.75rem" : "1.625rem";
  const legend = (["full", "partial", "missed", "today", "none"] as const);
  const weeks = grid
    .map((col) => col.filter((d): d is CadenceDay => !!d && d.state !== "none"))
    .filter((col) => col.length)
    .map((col) => ({ from: col[0].date, pub: col.reduce((a, d) => a + d.n, 0), exp: col.reduce((a, d) => a + d.expected, 0) }));
  return (
    <div className={cn("grid gap-6 lg:gap-10", big ? "lg:grid-cols-[minmax(0,15rem)_auto_minmax(0,1fr)]" : "lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]")}>
      <div className="grid content-start gap-4">
        <div>
          <p className={MONO}>Days fully published</p>
          <p className="mt-1.5 font-heading text-5xl leading-none font-semibold tracking-tight">
            <CountUp value={c.full_days} /><span className="text-2xl text-muted-foreground"> / {c.counted_days}</span>
          </p>
        </div>
        <p className="flex w-fit items-center gap-1.5 text-sm">
          <Flame className={cn("size-4", c.streak ? "text-[var(--brand-accent)]" : "text-muted-foreground")} aria-hidden />
          {c.streak ? <><strong className="tabular-nums">{c.streak}</strong> day{c.streak === 1 ? "" : "s"} in a row</> : "No current streak"}
        </p>
        <p className="min-h-10 border-l-2 border-primary/60 pl-3 text-sm leading-snug text-foreground/90" aria-live="polite">
          {shown ? cellSummary(shown) : "Hover or focus a day for its numbers."}
        </p>
        <ul className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-muted-foreground" aria-hidden>
          {legend.map((s) => (
            <li key={s} className="flex items-center gap-1.5"><span className={cn("size-3 shrink-0 rounded-[3px] border", CELL[s], s === "today" && "animate-none")} />{s === "full" ? "All published" : s === "partial" ? "Partly" : s === "missed" ? "Missed" : s === "today" ? "Today" : "Before first post"}</li>
          ))}
        </ul>
      </div>

      <div className="relative min-w-0 overflow-x-auto pb-1">
        <div className="inline-flex gap-1" style={{ ["--cell" as string]: cell }} role="group" aria-label={`Daily publishing, last ${c.days.length} days. ${cadenceSummary(c)}. Arrow keys move between days.`}>
          <div aria-hidden className="grid grid-rows-[1rem_repeat(7,var(--cell))] gap-1 pr-1">
            <span />
            {LABEL_ROWS.map((l, i) => <span key={i} className="flex items-center font-mono text-[10px] text-muted-foreground">{big ? ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i] : l}</span>)}
          </div>
          {grid.map((col, ci) => {
            const firstDay = col.find(Boolean)!;
            const prev = grid[ci - 1]?.find(Boolean);
            const month = new Date(`${firstDay.date}T12:00:00Z`).getUTCMonth();
            const showMonth = !prev || new Date(`${prev.date}T12:00:00Z`).getUTCMonth() !== month;
            return (
              <div key={ci} className="grid grid-rows-[1rem_repeat(7,var(--cell))] gap-1">
                <span aria-hidden className="overflow-visible font-mono text-[10px] whitespace-nowrap text-muted-foreground">{showMonth ? MONTHS[month] : ""}</span>
                {col.map((d, ri) =>
                  d ? (
                    <button
                      key={d.date} type="button" ref={(el) => { refs.current[d.date] = el; }}
                      tabIndex={d.date === focusDate ? 0 : -1}
                      aria-label={cellSummary(d)}
                      onFocus={() => setActive(d.date)} onMouseEnter={() => setActive(d.date)} onClick={() => setActive(d.date)}
                      onKeyDown={(e) => onKey(e, ci * 7 + ri)}
                      className={cn("relative size-[var(--cell)] rounded-[28%] border transition-transform focus-visible:z-10 motion-safe:hover:scale-110", CELL[d.state],
                        d.date === shown?.date && "ring-2 ring-foreground/80 ring-offset-2 ring-offset-background")}
                    >
                      {/* drawn by CSS (attr), so the visible glyphs never contradict the cell's accessible name */}
                      {big && <span aria-hidden data-glyph={Number(d.date.slice(8))} className={cn("absolute top-1 left-1.5 font-mono text-[10px] leading-none before:content-[attr(data-glyph)]", d.state === "full" || d.state === "partial" || d.state === "today" ? "text-foreground" : "text-muted-foreground", d.state === "partial" && "-mx-0.5 rounded-[2px] bg-background/85 px-0.5")} />}
                      {d.state === "missed" && <span aria-hidden data-glyph="×" className="absolute inset-0 grid place-items-center font-mono text-xs leading-none text-wait before:content-[attr(data-glyph)]" />}
                      {big && (d.state === "partial" || d.state === "today") && <span aria-hidden data-glyph={d.n} className="absolute right-1 bottom-1 rounded-[2px] bg-background/85 px-0.5 font-mono text-[10px] leading-none text-foreground before:content-[attr(data-glyph)]" />}
                    </button>
                  ) : <span key={`p${ri}`} aria-hidden className="size-[var(--cell)]" />,
                )}
              </div>
            );
          })}
        </div>
      </div>

      {big && (
        <div className="grid content-start gap-2" aria-hidden>
          <p className={MONO}>Week by week</p>
          <ul className="divide-y divide-dashed font-mono text-xs">
            {weeks.map((w) => (
              <li key={w.from} className="grid grid-cols-[4.5rem_minmax(0,1fr)_3.5rem] items-center gap-3 py-2">
                <span className="text-muted-foreground">{dayText(w.from, false)}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <span className={cn("block h-full rounded-full", w.pub >= w.exp ? "bg-go/70" : "bg-go/40")} style={{ width: `${w.exp ? Math.min(100, (100 * w.pub) / w.exp) : 0}%` }} />
                </span>
                <span className="text-right tabular-nums">{w.pub}<span className="text-muted-foreground">/{w.exp}</span></span>
              </li>
            ))}
          </ul>
          <p className="text-[11px] leading-snug text-muted-foreground">Posts live of posts expected ({c.expected_per_day} a day), Monday to Sunday, IST.</p>
        </div>
      )}

      {/* the same figures as text, for screen readers */}
      <div className="sr-only"><table>
        <caption>{cadenceSummary(c)}</caption>
        <thead><tr><th>Day (IST)</th><th>Published</th><th>Expected</th><th>Topics</th><th>Result</th></tr></thead>
        <tbody>{c.days.map((d) => <tr key={d.date}><td>{dayText(d.date)}</td><td>{d.n}</td><td>{d.expected}</td><td>{d.topics}</td><td>{stateWord(d.state)}</td></tr>)}</tbody>
      </table></div>
    </div>
  );
}
