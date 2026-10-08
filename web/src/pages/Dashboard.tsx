import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { RefreshCw, TriangleAlert } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Cadence } from "@/components/dashboard/cadence";
import { PipelineConsole, Turnaround } from "@/components/dashboard/engine";
import { Funnel, Mix } from "@/components/dashboard/funnel-mix";
import { KpiStrip } from "@/components/dashboard/kpi-strip";
import { DashCtx, DashSkeleton, MONO, SampleMark, Segmented, SectionHead, useDash } from "@/components/dashboard/primitives";
import { NextSlotsCard, RightNow } from "@/components/dashboard/right-now";
import { Feed, Gallery, Platforms, Roadmap } from "@/components/dashboard/shipped";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cadenceSummary, pickWorkspace, timeIST, type Overview } from "@/lib/dashboard-format";
import { storeWorkspace, storedWorkspace, useOverview, type Workspace } from "@/lib/dashboard";
import { cn } from "@/lib/utils";

/** Non-dismissible, part of the page (and of any screenshot): nobody mistakes the demo for a real account. */
function DemoBanner({ handle }: { handle: string }) {
  return (
    <div
      role="note"
      className="sticky top-14 z-10 flex flex-wrap items-center gap-x-3 gap-y-0.5 border-y border-[var(--brand-accent)]/60 bg-[color-mix(in_srgb,var(--brand-accent)_16%,var(--brand-bg))] px-4 py-2 md:top-0 md:px-8"
    >
      <span aria-hidden className="h-4 w-1 shrink-0 rounded bg-[var(--brand-accent)]" />
      <strong className="font-mono text-xs tracking-[0.14em] text-[var(--brand-accent)] uppercase">Demo workspace</strong>
      <span className="text-sm text-foreground/90">Sample data, not a real account{handle ? ` · ${handle}` : ""}. Actions and links are off.</span>
    </div>
  );
}

function Stamp({ data, fetchedAt, stale, loading, onRefresh }: { data: Overview | null; fetchedAt: number | null; stale: boolean; loading: boolean; onRefresh: () => void }) {
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      {fetchedAt && (
        <span title="Refreshes every minute while this tab is open" className={stale ? undefined : "max-sm:hidden"}>
          as of <span className="font-mono text-foreground/80">{timeIST(new Date(fetchedAt).toISOString())}</span> IST
          {stale && <span className="ml-1.5 rounded border border-[var(--brand-accent)]/60 px-1 py-px text-[10px] text-[var(--brand-accent)]">stale</span>}
        </span>
      )}
      <Button variant="outline" size="sm" className="touch:h-11 touch:min-w-11" onClick={onRefresh} disabled={loading && !data} aria-label="Refresh the dashboard">
        <RefreshCw className={loading ? "animate-spin" : ""} />
        <span className="hidden sm:inline">Refresh</span>
      </Button>
    </div>
  );
}

function Body({ data }: { data: Overview }) {
  const { demo } = useDash();
  const cadenceHint = data.cadence.ok ? cadenceSummary(data.cadence) : undefined;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-12">
      {/* phone order: sentence + what needs you, the numbers, then the slots; wide: hero beside slots, numbers below */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <RightNow data={data} />
        <div className="order-3 grid lg:order-2"><NextSlotsCard data={data} /></div>
        <div className="relative order-2 lg:order-3 lg:col-span-2"><SampleMark className="-top-2 bg-background" /><KpiStrip data={data} /></div>
      </div>

      <section aria-labelledby="cad-h">
        <SectionHead id="cad-h" n="01" title="Do we ship every day?" hint={cadenceHint} />
        <Cadence data={data} />
      </section>

      <section aria-labelledby="mix-h">
        <SectionHead id="mix-h" n="02" title="Does it follow the strategy?" hint="Funnel of what was drafted, and the topic mix against your targets" />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
          <Funnel data={data} />
          <Mix data={data} />
        </div>
      </section>

      <section aria-labelledby="eng-h">
        <SectionHead id="eng-h" n="03" title="Is the engine healthy?" hint="Reliability of generation and publishing, and how quickly you respond" />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-5 border-t border-rule pt-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-x-8">
          <PipelineConsole data={data} />
          <Turnaround data={data} />
        </div>
      </section>

      <section aria-labelledby="ship-h">
        <SectionHead id="ship-h" n="04" title="What has shipped" hint="Where it landed, and what happened along the way" />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
          <Platforms data={data} />
          <Gallery data={data} />
          <Feed data={data} />
          <Roadmap />
        </div>
      </section>
      {demo && <p className={cn(MONO, "text-center text-[10px]")}>End of the sample workspace</p>}
    </div>
  );
}

export default function Dashboard() {
  const [, setParams] = useSearchParams();
  const [demoOk, setDemoOk] = useState(true);
  const [workspace, setWorkspace] = useState<Workspace>(() => pickWorkspace(window.location.search, storedWorkspace(), true));
  const [range, setRange] = useState<30 | 90>(30);
  const [now, setNow] = useState(() => Date.now());
  const [introDone, setIntroDone] = useState(false);

  const demoOff = useCallback(() => {
    setDemoOk(false); setWorkspace("live"); storeWorkspace("live");
    setParams((p) => { const n = new URLSearchParams(p); n.delete("workspace"); return n; }, { replace: true });
  }, [setParams]);

  const { data, error, loading, fetchedAt, stale, reload } = useOverview(range, workspace, demoOff);
  const demo = workspace === "demo";

  useEffect(() => { if (data && data.config.demo_enabled === false && demoOk) setDemoOk(false); }, [data, demoOk]);

  // Count-up plays once, when the first data of this visit lands; it never replays on refresh.
  const intro = !!data && !introDone;
  useEffect(() => {
    if (!data || introDone) return;
    const t = setTimeout(() => setIntroDone(true), 1500);
    return () => clearTimeout(t);
  }, [data, introDone]);

  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);

  useEffect(() => {
    const prev = document.title;
    document.title = demo ? "[DEMO] Dashboard" : "Dashboard";
    return () => { document.title = prev; };
  }, [demo]);

  function pick(w: Workspace) {
    setWorkspace(w);
    storeWorkspace(w);
    setParams((p) => { const n = new URLSearchParams(p); n.delete("workspace"); return n; }, { replace: true });
  }

  const ctx = useMemo(() => ({ demo, now, intro }), [demo, now, intro]);
  const handle = data?.handle ?? "";

  return (
    <AppShell>
      <DashCtx.Provider value={ctx}>
        <TooltipProvider delayDuration={150}>
          {demo && <DemoBanner handle={data?.workspace === "demo" ? handle : "@demo_dev_daily"} />}
          <div className="mx-auto grid max-w-[78rem] grid-cols-[minmax(0,1fr)] gap-7 px-4 py-6 md:px-8 md:py-9">
            <PageHeader
              index="01"
              eyebrow={<span className="truncate">Control room{!demo && handle ? ` · ${handle}` : ""}</span>}
              title="Dashboard"
              lead="What needs you now, whether you ship every day, and whether the engine is healthy."
              actions={<>
              {(demoOk || demo) && (
                <Segmented<Workspace> label="Workspace" value={workspace} onChange={pick}
                  options={[{ value: "live", label: "Live" }, { value: "demo", label: <><span className="sm:hidden">Demo</span><span className="hidden sm:inline">Demo workspace</span></> }]} />
              )}
              <Segmented<30 | 90> label="Time window" value={range} onChange={setRange}
                options={[{ value: 30, label: <>30<span className="hidden sm:inline"> days</span><span className="sm:hidden">d</span></> }, { value: 90, label: <>90<span className="hidden sm:inline"> days</span><span className="sm:hidden">d</span></> }]} />
              <Stamp data={data} fetchedAt={fetchedAt} stale={stale} loading={loading} onRefresh={() => void reload()} />
              </>}
            />

            {error && (
              <div role="alert" className="flex flex-wrap items-center gap-3 border-l-[3px] border-bad bg-bad/10 py-2.5 pr-3 pl-4 text-sm text-bad">
                <TriangleAlert className="size-4 shrink-0" aria-hidden />
                <span className="min-w-0 flex-1">
                  {data ? "Couldn't refresh. Showing the last numbers loaded; they are marked stale." : (
                    <>Couldn't load the dashboard ({error}). This is not an all-clear: <Link to="/posts" className="underline underline-offset-4">open Posts</Link> to check what needs you.</>
                  )}
                </span>
                <Button variant="outline" size="sm" onClick={() => void reload()}>Try again</Button>
              </div>
            )}

            {data ? <Body data={data} /> : !error || loading ? <DashSkeleton days={range} /> : null}
          </div>
        </TooltipProvider>
      </DashCtx.Provider>
    </AppShell>
  );
}
