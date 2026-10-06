import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check, CircleDashed, LoaderCircle, Minus, TriangleAlert, X } from "lucide-react";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { CheckRow, State } from "@/lib/config";
import { STATE_LABEL, STATE_ROLE, errorAnchor } from "@/lib/config-format";
import { GUIDES, TROUBLESHOOTING, VERIFIED_ON, type Guide } from "@/lib/config-guides";
import { cn } from "@/lib/utils";

const ROLE_TAG = {
  ok: "text-ok border-ok/35 bg-ok/10",
  wait: "text-wait border-wait/40 bg-wait/10",
  bad: "text-bad border-bad/40 bg-bad/10",
  go: "text-go border-go/35 bg-go/10",
  idle: "text-muted-foreground border-border",
} as const;

/** Card/step status: icon + words (never colour alone). */
export function StateTag({ state, className }: { state: State; className?: string }) {
  const role = STATE_ROLE[state] ?? "idle";
  const Icon = state === "checking" ? LoaderCircle : state === "valid" ? Check : state === "invalid" ? X
    : state === "not_set" || state === "unverified" ? CircleDashed : TriangleAlert;
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-2 text-xs font-medium", ROLE_TAG[role], className)}>
      <Icon aria-hidden className={cn("size-3.5", state === "checking" && "animate-spin")} />
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

/** A dot for compact places (step rail). The label sits next to it, and the state is in sr-only text. */
export function StateDot({ state }: { state: State }) {
  const role = STATE_ROLE[state] ?? "idle";
  const bg = { ok: "bg-ok", wait: "bg-wait", bad: "bg-bad", go: "bg-go animate-pulse", idle: "border border-muted-foreground/60" }[role];
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", bg)}><span className="sr-only">{STATE_LABEL[state]}</span></span>;
}

/** The individual checks of one verification, as a ledger. */
export function CheckList({ checks }: { checks: CheckRow[] }) {
  return (
    <ul className="grid gap-px overflow-hidden rounded-md border border-rule bg-rule text-sm">
      {checks.map((c) => {
        const state = c.ok === true ? (c.soft ? "warn" : "ok") : c.ok === false ? "fail" : "skip";
        const Icon = { ok: Check, warn: TriangleAlert, fail: X, skip: Minus }[state];
        const word = { ok: "Passed", warn: "Passed with a warning", fail: "Failed", skip: "Not run" }[state];
        const tone = { ok: "text-ok", warn: "text-wait", fail: "text-bad", skip: "text-muted-foreground" }[state];
        return (
          <li key={c.name} className="grid grid-cols-[1.25rem_1fr] gap-x-2 bg-background px-3 py-2 sm:grid-cols-[1.25rem_minmax(0,1fr)_auto]">
            <Icon aria-hidden className={cn("mt-0.5 size-4", tone)} />
            <span className="min-w-0">
              <span className="sr-only">{word}: </span>
              {c.label}
              {c.evidence && <span className="block text-xs break-words text-muted-foreground">{c.evidence}</span>}
            </span>
            <span className="col-start-2 font-mono text-[10px] tracking-wide text-muted-foreground uppercase sm:col-start-3 sm:self-start sm:pt-1">
              {c.depth === "format" ? "format" : c.depth === "deep" ? "real test" : "live"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function External({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-baseline gap-0.5 break-all text-primary underline-offset-4 hover:underline">
      {children}<ArrowUpRight aria-hidden className="size-3 shrink-0 self-center" /><span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

export function Unverified({ why }: { why: string }) {
  return (
    <details className="mt-1.5 text-xs text-muted-foreground">
      <summary className="inline-flex cursor-pointer items-center gap-1 rounded-[3px] border border-wait/40 px-1.5 py-px font-mono text-[10px] tracking-wide text-wait uppercase">Unverified</summary>
      <p className="mt-1 max-w-prose">{why}</p>
    </details>
  );
}

/** One integration's guide: time, before you start, a numbered step rail, success, mistakes, security, sources. */
export function GuideBody({ guide, compact = false }: { guide: Guide; compact?: boolean }) {
  return (
    <div className="grid gap-7">
      <p className="max-w-prose text-[15px] leading-relaxed">{guide.purpose}</p>
      <dl className="grid gap-2 text-sm">
        <div className="flex items-baseline gap-3"><dt className="label-mono">Time</dt><span aria-hidden className="leader" /><dd>{guide.minutes ? `about ${guide.minutes} min` : "done at install"}</dd></div>
        <div className="flex items-baseline gap-3"><dt className="label-mono">Checked</dt><span aria-hidden className="leader" /><dd>against the official docs on {VERIFIED_ON}</dd></div>
      </dl>
      {guide.before.length > 0 && (
        <section>
          <h3 className="label-mono mb-2">Before you start</h3>
          <ul className="grid gap-1 text-sm">{guide.before.map((b) => <li key={b} className="flex gap-2"><span aria-hidden className="text-signal">·</span>{b}</li>)}</ul>
        </section>
      )}
      <section>
        <h3 className="label-mono mb-3">Steps</h3>
        <ol className="relative grid gap-5 pl-9 before:absolute before:top-2 before:bottom-2 before:left-[11px] before:w-px before:bg-rule">
          {guide.steps.map((s, i) => (
            <li key={i} className="relative text-sm leading-relaxed">
              <span aria-hidden className="absolute top-0 -left-9 grid size-6 place-items-center rounded-full border border-rule bg-background font-mono text-[11px]">{i + 1}</span>
              <span className="sr-only">Step {i + 1}: </span>{s.text}
              {s.link && <div className="mt-1"><External href={s.link.href}>{s.link.label}</External></div>}
              {s.unverified && <Unverified why={s.unverified} />}
            </li>
          ))}
        </ol>
      </section>
      <section className="border-l-2 border-ok/60 pl-4">
        <h3 className="label-mono mb-1">When it works</h3>
        <p className="text-sm">{guide.success}</p>
      </section>
      <section>
        <h3 className="label-mono mb-2">Common mistakes</h3>
        <ul className="grid gap-2 text-sm">{guide.mistakes.map((m) => <li key={m} className="flex gap-2"><TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0 text-wait" />{m}</li>)}</ul>
      </section>
      <section>
        <h3 className="label-mono mb-1">Security</h3>
        <p className="text-sm text-muted-foreground">{guide.security}</p>
      </section>
      {!compact && (
        <section>
          <h3 className="label-mono mb-2">Sources</h3>
          <ul className="grid gap-1 text-sm">{guide.sources.map((s) => <li key={s.href}><External href={s.href}>{s.label}</External></li>)}</ul>
        </section>
      )}
    </div>
  );
}

/** "Where do I get this?": the guide in a side sheet, so the form stays where it is. */
export function GuideSheet({ id, open, onOpenChange }: { id: string | null; open: boolean; onOpenChange: (v: boolean) => void }) {
  const guide = GUIDES.find((g) => g.id === id);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg data-[side=right]:sm:max-w-lg">
        {guide && (
          <>
            <SheetHeader className="border-b border-rule px-6 pt-6 pb-4">
              <p className="label-mono">Setup guide</p>
              <SheetTitle className="text-2xl">{guide.title}</SheetTitle>
              <SheetDescription>Follow these steps in another tab, then come back and paste.</SheetDescription>
            </SheetHeader>
            <div className="px-6 pb-8">
              <GuideBody guide={guide} compact />
              <p className="mt-8 text-sm"><Link to={`/config/guide/${guide.id}`} className="text-primary underline-offset-4 hover:underline">Open the full guide with sources</Link></p>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

/** Message + next step for a failed/warning result, linking to its troubleshooting entry. */
export function ResultNote({ code, message, hint }: { code: string | null; message: string; hint: string }) {
  if (!code) return null;
  const t = TROUBLESHOOTING[code];
  return (
    <div className="grid gap-1 text-sm">
      <p className="font-medium">{message || t?.title}</p>
      {hint && <p className="text-muted-foreground">{hint}</p>}
      {t && <p><Link to={`/config/guide/errors#${errorAnchor(code)}`} className="text-primary underline-offset-4 hover:underline">How to fix: {t.title}</Link></p>}
    </div>
  );
}
