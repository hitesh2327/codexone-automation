import { useCallback, useEffect, useState } from "react";
import { AlertCircle, RefreshCw, RotateCcw, Wrench } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  listAdminJobs,
  listFailures,
  reconcileJobs,
  retryFailures,
  type AdminJob,
  type FailureEntry,
  type FailureGroup,
} from "@/lib/admin";
import { cn } from "@/lib/utils";

export function OperationsTab({ onMutated }: { onMutated: () => void }) {
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [stuckCount, setStuckCount] = useState(0);
  const [stuckOnly, setStuckOnly] = useState(false);
  const [failures, setFailures] = useState<FailureEntry[]>([]);
  const [groups, setGroups] = useState<FailureGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [jRes, fRes] = await Promise.all([listAdminJobs(stuckOnly), listFailures()]);
      setJobs(jRes.jobs);
      setStuckCount(jRes.stuck_count);
      setFailures(fRes.failures);
      setGroups(fRes.groups);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load operations data");
    } finally {
      setLoading(false);
    }
  }, [stuckOnly]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleReconcile() {
    setBusy(true);
    try {
      const res = await reconcileJobs();
      toast.success(`Checked ${res.checked} active job(s): ${res.reconciled.length} reconciled, ${res.released.length} released.`);
      await load();
      onMutated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Reconcile failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRetry(payload: { post_ids?: string[]; signature?: string }) {
    setBusy(true);
    try {
      const res = await retryFailures(payload);
      toast.success(`Queued ${res.count} failed post(s) back to approved for retry.`);
      await load();
      onMutated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      {/* Dead-Letter Queue (Failures) */}
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertCircle className="size-4 text-bad" aria-hidden />
              Failed Publish Dead-Letter Queue ({failures.length})
            </CardTitle>
            <CardDescription>Cross-tenant failed publishes grouped by error signature.</CardDescription>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={load} disabled={loading} className="gap-1.5">
            <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </CardHeader>

        <CardContent className="grid gap-4">
          {groups.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {groups.map((g) => (
                <div key={g.signature} className="flex items-center gap-2 rounded-md border bg-sunken px-3 py-1.5 text-xs">
                  <span className="font-mono font-semibold text-bad">{g.signature}</span>
                  <Badge variant="outline" className="font-mono tabular-nums">{g.count}</Badge>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => handleRetry({ signature: g.signature })}
                    className="h-6 gap-1 px-2 text-[11px]"
                  >
                    <RotateCcw className="size-3" />
                    Bulk Retry
                  </Button>
                </div>
              ))}
            </div>
          )}

          {failures.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Dead-letter queue is empty. All publishes are healthy.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Post</TableHead>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Signature</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {failures.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell>
                      <div className="grid">
                        <span className="max-w-xs truncate font-medium">{f.topic}</span>
                        <span className="font-mono text-xs text-muted-foreground">{f.id} · {f.kind}</span>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{f.username || f.email || `user#${f.user_id}`}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="border-bad/40 font-mono text-[11px] text-bad">{f.signature}</Badge>
                    </TableCell>
                    <TableCell className="max-w-sm truncate text-xs text-muted-foreground">{f.error || "—"}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() => handleRetry({ post_ids: [f.id] })}
                        className="h-7 gap-1 px-2.5 text-xs"
                      >
                        <RotateCcw className="size-3" />
                        Retry
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Generation Jobs Queue */}
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">Generation Jobs ({jobs.length})</CardTitle>
            <CardDescription>
              {stuckCount > 0 ? `${stuckCount} stuck job(s) exceeding >35m running or >10m queued.` : "No stuck generation jobs detected."}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant={stuckOnly ? "default" : "outline"}
              onClick={() => setStuckOnly((v) => !v)}
            >
              Stuck only ({stuckCount})
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={handleReconcile}
              className="gap-1.5"
            >
              <Wrench className="size-3.5" />
              Reconcile Stuck Jobs
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">No generation jobs matching the current filter.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job ID</TableHead>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Phase / Reason</TableHead>
                  <TableHead>Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell className="font-mono text-xs">
                      {j.id}
                      {j.is_stuck && (
                        <Badge variant="outline" className="ml-2 border-wait/50 bg-wait/10 text-[10px] text-wait">STUCK</Badge>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{j.username || j.email || `user#${j.user_id}`}</TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={cn(
                          "capitalize",
                          j.status === "succeeded" && "border-ok/40 text-ok",
                          j.status === "failed" && "border-bad/40 text-bad",
                          (j.status === "running" || j.status === "queued") && "border-go/40 text-go",
                        )}
                      >
                        {j.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-xs text-muted-foreground">
                      {j.phase || j.failure_reason || j.message || "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      {j.duration_sec != null ? `${Math.round(j.duration_sec / 60)}m ${j.duration_sec % 60}s` : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
