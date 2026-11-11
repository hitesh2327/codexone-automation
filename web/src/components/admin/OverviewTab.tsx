import { useState } from "react";
import { AlertTriangle, CheckCircle2, Download, IndianRupee, Layers, Radio, RefreshCw, Users, Zap } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { downloadGstCsv, type AdminOverview } from "@/lib/admin";
import { cn } from "@/lib/utils";

const inr = (n: number) => `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(n)}`;

export function OverviewTab({ data, onJumpTab }: { data: AdminOverview; onJumpTab: (tab: string) => void }) {
  const [exporting, setExporting] = useState(false);
  const { revenue, jobs, failures, youtube_quota: yt, oauth_health: oauth } = data;
  const totalJobs24h = Object.values(jobs.counts_24h).reduce((a, b) => a + b, 0);

  async function handleExportGst() {
    setExporting(true);
    try {
      await downloadGstCsv();
      toast.success("Downloaded GST summary CSV");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to export GST CSV");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="grid gap-6">
      {(jobs.stuck_count > 0 || yt.warning || failures.failed_publishes_count > 0) && (
        <Alert className="border-wait/50 bg-wait/10 text-foreground">
          <AlertTriangle className="size-4 text-wait" aria-hidden />
          <AlertTitle>Attention needed</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            {jobs.stuck_count > 0 && <span>{jobs.stuck_count} stuck generation job(s) detected.</span>}
            {failures.failed_publishes_count > 0 && <span>{failures.failed_publishes_count} failed publish(es) in DLQ.</span>}
            {yt.warning && <span>YouTube daily quota at {yt.utilization_pct}% ({yt.units_used}/{yt.daily_limit} units).</span>}
            <Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => onJumpTab("operations")}>
              Open Jobs & DLQ
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Top KPI Grid */}
      <section aria-label="Key metrics" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between font-mono text-xs uppercase tracking-wider">
              <span>Live MRR</span>
              <IndianRupee className="size-3.5 text-primary" aria-hidden />
            </CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums">{inr(revenue.mrr_inr)}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground tabular-nums">
            ARR {inr(revenue.arr_inr)} · {revenue.active_subscribers} active paid
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between font-mono text-xs uppercase tracking-wider">
              <span>Tenants</span>
              <Users className="size-3.5 text-primary" aria-hidden />
            </CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums">{revenue.total_tenants}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground tabular-nums">
            {revenue.total_users} total accounts (incl. operators)
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between font-mono text-xs uppercase tracking-wider">
              <span>24h Generation</span>
              <Zap className="size-3.5 text-primary" aria-hidden />
            </CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums">{totalJobs24h}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-2 text-xs tabular-nums">
            <span className="text-ok">{jobs.counts_24h.succeeded ?? 0} ok</span>
            <span className="text-muted-foreground">·</span>
            <span className={cn(jobs.counts_24h.failed ? "text-bad" : "text-muted-foreground")}>
              {jobs.counts_24h.failed ?? 0} failed
            </span>
            <span className="text-muted-foreground">·</span>
            <span className={cn(jobs.stuck_count ? "text-wait font-medium" : "text-muted-foreground")}>
              {jobs.stuck_count} stuck
            </span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between font-mono text-xs uppercase tracking-wider">
              <span>YouTube Quota</span>
              <Radio className="size-3.5 text-primary" aria-hidden />
            </CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums">{yt.utilization_pct}%</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1.5">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
              <div
                className={cn("h-full transition-all", yt.warning ? "bg-wait" : "bg-primary")}
                style={{ width: `${Math.min(100, yt.utilization_pct)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground tabular-nums">
              {yt.units_used.toLocaleString()} / {yt.daily_limit.toLocaleString()} units ({yt.uploads_today} uploads today)
            </p>
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Subscribers by Tier */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Layers className="size-4 text-primary" aria-hidden />
              Subscribers by Tier
            </CardTitle>
            <CardDescription>Active and trialing plans contributing to MRR.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2.5">
            {revenue.by_tier.map((t) => (
              <div key={t.id} className="flex items-center justify-between border-b border-border/60 pb-2 text-sm last:border-b-0 last:pb-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{t.name}</span>
                  <Badge variant="outline" className="font-mono text-[11px] tabular-nums">
                    {t.count}
                  </Badge>
                </div>
                <span className="font-mono text-sm tabular-nums text-muted-foreground">{inr(t.mrr_inr)}/mo</span>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* GST Compliance Ledger */}
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle className="text-base">GST Tax Ledger (Monthly Run-Rate)</CardTitle>
              <CardDescription>CGST/SGST (intra-state), IGST (inter-state), and 0% exports.</CardDescription>
            </div>
            <Button type="button" size="sm" variant="outline" onClick={handleExportGst} disabled={exporting} className="gap-1.5">
              {exporting ? <RefreshCw className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
              Export CSV
            </Button>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div className="rounded-md border bg-sunken p-3">
              <p className="font-mono text-[11px] uppercase text-muted-foreground">Taxable Base</p>
              <p className="mt-1 font-mono font-semibold tabular-nums">{inr(revenue.gst_summary.taxable_inr)}</p>
            </div>
            <div className="rounded-md border bg-sunken p-3">
              <p className="font-mono text-[11px] uppercase text-muted-foreground">CGST + SGST</p>
              <p className="mt-1 font-mono font-semibold tabular-nums">
                {inr(revenue.gst_summary.cgst_inr + revenue.gst_summary.sgst_inr)}
              </p>
            </div>
            <div className="rounded-md border bg-sunken p-3">
              <p className="font-mono text-[11px] uppercase text-muted-foreground">IGST (18%)</p>
              <p className="mt-1 font-mono font-semibold tabular-nums">{inr(revenue.gst_summary.igst_inr)}</p>
            </div>
            <div className="rounded-md border bg-sunken p-3">
              <p className="font-mono text-[11px] uppercase text-muted-foreground">0% Exports</p>
              <p className="mt-1 font-mono font-semibold tabular-nums">{inr(revenue.gst_summary.export_inr)}</p>
            </div>
            <div className="rounded-md border bg-sunken p-3 sm:col-span-2">
              <p className="font-mono text-[11px] uppercase text-muted-foreground">Total Output GST</p>
              <p className="mt-1 font-mono font-semibold tabular-nums text-primary">{inr(revenue.gst_summary.total_tax_inr)}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* OAuth & Channel Health */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Channel & OAuth Health</CardTitle>
          <CardDescription>Connected tenant credentials and DLQ token alerts.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-4">
          <div className="rounded-md border p-3">
            <p className="font-mono text-[11px] uppercase text-muted-foreground">Instagram Tokens</p>
            <p className="mt-1 text-lg font-semibold tabular-nums">{oauth.ig_connected_tenants}</p>
            <p className="text-xs text-muted-foreground">
              {oauth.ig_needs_reauth_posts > 0 ? `${oauth.ig_needs_reauth_posts} post(s) hit Error 190` : "No Error 190 alerts"}
            </p>
          </div>
          <div className="rounded-md border p-3">
            <p className="font-mono text-[11px] uppercase text-muted-foreground">YouTube Tokens</p>
            <p className="mt-1 text-lg font-semibold tabular-nums">{oauth.yt_connected_tenants}</p>
            <p className="text-xs text-muted-foreground">
              {failures.yt_quota_errors_count > 0 ? `${failures.yt_quota_errors_count} quota error(s)` : "Within daily quota"}
            </p>
          </div>
          <div className="rounded-md border p-3">
            <p className="font-mono text-[11px] uppercase text-muted-foreground">Telegram Linked</p>
            <p className="mt-1 text-lg font-semibold tabular-nums">{oauth.tg_connected_tenants}</p>
            <p className="text-xs text-muted-foreground">Active approval chats</p>
          </div>
          <div className="rounded-md border p-3">
            <p className="font-mono text-[11px] uppercase text-muted-foreground">7d Job Reliability</p>
            <p className="mt-1 flex items-center gap-1.5 text-lg font-semibold tabular-nums">
              <CheckCircle2 className="size-4 text-ok" aria-hidden />
              {jobs.counts_7d.succeeded ?? 0} / {Object.values(jobs.counts_7d).reduce((a, b) => a + b, 0)}
            </p>
            <p className="text-xs text-muted-foreground">Succeeded in last 7 days</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
