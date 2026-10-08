import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Info, TriangleAlert } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Tone } from "@/lib/stage";
import { cn } from "@/lib/utils";

/** Page-wide facts every widget needs: demo (actions off), a ticking clock, and whether the intro count-up plays. */
export const DashCtx = createContext<{ demo: boolean; now: number; intro: boolean }>({ demo: false, now: Date.now(), intro: false });
export const useDash = () => useContext(DashCtx);

export const MONO = "font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground";
export const DEMO_TIP = "Sample data. Actions are off.";

export const TEXT: Record<Tone, string> = {
  wait: "text-wait", go: "text-primary", ok: "text-ok", bad: "text-bad", idle: "text-muted-foreground",
};
export const BG: Record<Tone, string> = {
  wait: "bg-wait", go: "bg-primary", ok: "bg-ok-solid", bad: "bg-bad", idle: "bg-muted-foreground/40",
};

export const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Counts up once, only when mounted during the first load; later refreshes just show the new value. */
export function CountUp({ value, format = (n: number) => String(Math.round(n)) }: { value: number; format?: (n: number) => string }) {
  const { intro } = useDash();
  const [shown, setShown] = useState(() => (intro && !reducedMotion() ? 0 : value));
  // Idempotent (safe under StrictMode's double effect run): it animates only while `intro` is true, which
  // is the first ~1.5 s after the first data lands; afterwards every refresh just sets the new value.
  useEffect(() => {
    if (!intro || reducedMotion()) { setShown(value); return; }
    const start = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, Math.max(0, (t - start) / 900)); // rAF time can precede "start"
      setShown(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, intro]);
  return <span className="tabular-nums"><span className="sr-only">{format(value)}</span><span aria-hidden>{format(shown)}</span></span>;
}

/** "02 · Delivery" label with a hairline; every section carries one, and the SAMPLE mark in the demo. */
export function SectionHead({ n, title, hint, id }: { n: string; title: string; hint?: string; id: string }) {
  const { demo } = useDash();
  return (
    <header className="mb-4 flex items-end gap-3">
      <span aria-hidden className="font-heading text-3xl leading-none font-bold text-transparent [-webkit-text-stroke:1px_color-mix(in_srgb,var(--brand-text)_55%,transparent)]">{n}</span>
      <div className="min-w-0">
        <h2 id={id} className="font-heading text-lg font-semibold tracking-tight">{title}</h2>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <span aria-hidden className="mb-1.5 h-px flex-1 bg-border" />
      {demo && <span className={cn(MONO, "mb-0.5 rounded border border-[var(--brand-accent)]/50 px-1.5 py-px text-[10px] text-[var(--brand-accent)]")}>Sample</span>}
    </header>
  );
}

/** Corner tag on the demo's top cards (section heads carry their own), part of any screenshot. */
export function SampleMark({ className }: { className?: string }) {
  const { demo } = useDash();
  if (!demo) return null;
  return <span className={cn(MONO, "pointer-events-none absolute top-2.5 right-3 z-[1] rounded border border-[var(--brand-accent)]/50 bg-card/80 px-1.5 py-px text-[10px] text-[var(--brand-accent)]", className)}>Sample</span>;
}

export function Unavailable({ what, className }: { what: string; className?: string }) {
  return (
    <div role="status" className={cn("flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground", className)}>
      <TriangleAlert className="size-4 shrink-0 text-wait" aria-hidden />
      <span><span className="text-foreground/90">{what}</span>: unavailable right now. The rest of the page is unaffected.</span>
    </div>
  );
}

export function Empty({ title, children, className }: { title: string; children?: ReactNode; className?: string }) {
  return (
    <div className={cn("grid place-items-center gap-1 rounded-lg border border-dashed px-4 py-8 text-center", className)}>
      <p className="text-sm font-medium">{title}</p>
      {children && <p className="max-w-sm text-xs text-muted-foreground">{children}</p>}
    </div>
  );
}

/** A small (i) that explains how a number is made. Keyboard focusable. */
export function Why({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" aria-label={`How ${label} is calculated`} className="relative rounded-full text-muted-foreground after:absolute after:-inset-1.5 after:content-[''] hover:text-foreground touch:after:-inset-[15px]">
          <Info className="size-3.5" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-64 flex-col items-start text-left leading-snug">{children}</TooltipContent>
    </Tooltip>
  );
}

export function Segmented<T extends string | number>({ label, value, options, onChange, className }: {
  label: string; value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; className?: string;
}) {
  function onKey(e: React.KeyboardEvent) {
    const i = options.findIndex((o) => o.value === value);
    const next = e.key === "ArrowRight" || e.key === "ArrowDown" ? i + 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? i - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const o = options[(next + options.length) % options.length];
    onChange(o.value);
    (e.currentTarget.querySelectorAll("[role=radio]")[(next + options.length) % options.length] as HTMLElement | undefined)?.focus();
  }
  return (
    <div role="radiogroup" aria-label={label} onKeyDown={onKey} className={cn("inline-flex rounded-lg border bg-muted/40 p-0.5", className)}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={String(o.value)} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1} onClick={() => onChange(o.value)}
            className={cn("min-h-9 rounded-md px-2.5 text-sm font-medium transition-colors touch:min-h-11 sm:px-3",
              on ? "bg-background text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground")}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function DashSkeleton({ days }: { days?: number }) {
  return (
    <div className="grid gap-6" role="status" aria-busy="true" aria-label="Loading the dashboard">
      {/* one line of words, so a slow cold start reads as "working", not "broken" */}
      <p className="font-mono text-xs text-muted-foreground">Loading the last {days ?? 30} days…</p>
      <Skeleton className="h-[22rem] w-full rounded-2xl" />
      <Skeleton className="h-28 w-full rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-2"><Skeleton className="h-56" /><Skeleton className="h-56" /></div>
    </div>
  );
}
