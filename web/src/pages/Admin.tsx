import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { OperationsTab } from "@/components/admin/OperationsTab";
import { OverviewTab } from "@/components/admin/OverviewTab";
import { SafetyFlagsTab } from "@/components/admin/SafetyFlagsTab";
import { TenantsTab } from "@/components/admin/TenantsTab";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getOverview, type AdminOverview } from "@/lib/admin";
import { cn } from "@/lib/utils";

export default function AdminPage() {
  const [tab, setTab] = useState("overview");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await getOverview());
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load admin overview";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const anyTripped = Boolean(
    overview?.kill_switches.generation || overview?.kill_switches.publishing || overview?.kill_switches.signups,
  );

  return (
    <AppShell>
      <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <PageHeader
          index="07"
          eyebrow="Operator console"
          title="Admin & Stakeholders"
          lead="Live MRR & GST ledger, tenant unit economics, queue reliability, and emergency kill-switches."
          meta={
            anyTripped && (
              <Badge variant="outline" className="border-bad bg-bad/10 font-mono text-xs text-bad">
                KILL-SWITCH ACTIVE
              </Badge>
            )
          }
          actions={
            <Button type="button" variant="outline" size="sm" onClick={loadOverview} disabled={loading} className="gap-1.5">
              <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
              Refresh
            </Button>
          }
        />

        <Tabs value={tab} onValueChange={setTab} className="grid gap-5">
          <TabsList className="w-full justify-start overflow-x-auto">
            <TabsTrigger value="overview">Overview & GST</TabsTrigger>
            <TabsTrigger value="tenants">Tenants & Economics</TabsTrigger>
            <TabsTrigger value="operations">
              Jobs & DLQ
              {(overview?.failures.failed_publishes_count ?? 0) + (overview?.jobs.stuck_count ?? 0) > 0 && (
                <Badge variant="outline" className="ml-1.5 border-bad/40 font-mono text-[10px] text-bad tabular-nums">
                  {(overview?.failures.failed_publishes_count ?? 0) + (overview?.jobs.stuck_count ?? 0)}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="safety">Safety & Flags</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            {loading && !overview ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-28 rounded-xl" />
                ))}
              </div>
            ) : error && !overview ? (
              <div className="rounded-lg border border-bad/40 bg-bad/10 p-6 text-center text-sm">
                <p className="font-medium text-bad">{error}</p>
                <Button type="button" variant="outline" size="sm" onClick={loadOverview} className="mt-3">
                  Retry
                </Button>
              </div>
            ) : overview ? (
              <OverviewTab data={overview} onJumpTab={setTab} />
            ) : null}
          </TabsContent>

          <TabsContent value="tenants">
            <TenantsTab onMutated={loadOverview} />
          </TabsContent>

          <TabsContent value="operations">
            <OperationsTab onMutated={loadOverview} />
          </TabsContent>

          <TabsContent value="safety">
            <SafetyFlagsTab onMutated={loadOverview} />
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
