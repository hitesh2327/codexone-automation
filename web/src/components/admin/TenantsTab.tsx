import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Ban, CheckCircle, Eye, PlusCircle, Search } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { grantBonusQuota, listTenants, startImpersonation, suspendTenant, type TenantRow } from "@/lib/admin";
import { useAuth, type User } from "@/lib/auth";
import { cn } from "@/lib/utils";

const ANY = "__any";
const PAGE_SIZE = 50;

export function TenantsTab({ onMutated }: { onMutated: () => void }) {
  const { user: me, applySessionUser } = useAuth();
  const navigate = useNavigate();

  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [tier, setTier] = useState(ANY);

  const [suspendTarget, setSuspendTarget] = useState<TenantRow | null>(null);
  const [suspendReason, setSuspendReason] = useState("");
  const [quotaTarget, setQuotaTarget] = useState<TenantRow | null>(null);
  const [bonusReels, setBonusReels] = useState("5");
  const [bonusCarousels, setBonusCarousels] = useState("10");
  const [bonusReason, setBonusReason] = useState("");
  const [impTarget, setImpTarget] = useState<TenantRow | null>(null);
  const [impReason, setImpReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listTenants({
        q: q.trim() || undefined,
        tier: tier === ANY ? undefined : tier,
        limit: PAGE_SIZE,
        offset,
      });
      setTenants(res.tenants);
      setTotal(res.total);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load tenants");
    } finally {
      setLoading(false);
    }
  }, [q, tier, offset]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  async function handleSuspend() {
    if (!suspendTarget) return;
    setBusy(true);
    try {
      await suspendTenant(suspendTarget.id, !suspendTarget.is_active, suspendReason.trim());
      toast.success(suspendTarget.is_active ? "Tenant suspended & sessions revoked" : "Tenant reactivated");
      setSuspendTarget(null);
      setSuspendReason("");
      await load();
      onMutated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update tenant status");
    } finally {
      setBusy(false);
    }
  }

  async function handleBonusQuota() {
    if (!quotaTarget) return;
    setBusy(true);
    try {
      await grantBonusQuota(quotaTarget.id, {
        reels: Number(bonusReels) || 0,
        carousels: Number(bonusCarousels) || 0,
        mode: "add",
        reason: bonusReason.trim(),
      });
      toast.success("Bonus quota added");
      setQuotaTarget(null);
      setBonusReason("");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to adjust quota");
    } finally {
      setBusy(false);
    }
  }

  async function handleImpersonate() {
    if (!impTarget) return;
    if (impReason.trim().length < 10) {
      toast.error("Please enter a support ticket or reason (at least 10 characters).");
      return;
    }
    setBusy(true);
    try {
      const res = await startImpersonation(impTarget.id, impReason.trim());
      applySessionUser(res.user as User);
      toast.success(`Read-only impersonation active for @${impTarget.username || impTarget.email}`);
      navigate("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to start impersonation");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="text-base">Tenants & Unit Economics ({total})</CardTitle>
          <CardDescription>Cycle usage, estimated COGS vs revenue, quota overrides, and audited support access.</CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-56">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden />
            <Input
              value={q}
              onChange={(e) => { setQ(e.target.value); setOffset(0); }}
              placeholder="Search user or email…"
              aria-label="Search tenants"
              className="pl-8"
            />
          </div>
          <Select value={tier} onValueChange={(v) => { setTier(v); setOffset(0); }}>
            <SelectTrigger className="w-36" aria-label="Filter by plan tier">
              <SelectValue placeholder="All tiers" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>All tiers</SelectItem>
              <SelectItem value="free">Free</SelectItem>
              <SelectItem value="lite">Lite</SelectItem>
              <SelectItem value="starter">Starter</SelectItem>
              <SelectItem value="creator">Creator</SelectItem>
              <SelectItem value="pro">Pro</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>

      <CardContent>
        {loading && tenants.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading tenants…</p>
        ) : tenants.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No matching tenants found.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tenant</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Cycle Quota</TableHead>
                <TableHead>COGS / Rev</TableHead>
                <TableHead>Margin</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tenants.map((t) => {
                const isLowMargin = t.margin_pct !== null && t.margin_pct < 60;
                const canMutate =
                  t.id !== me?.id &&
                  t.role !== "owner" &&
                  (t.role !== "admin" || me?.role === "owner");
                return (
                  <TableRow key={t.id}>
                    <TableCell>
                      <div className="grid">
                        <span className="font-medium">{t.username || t.name || `user#${t.id}`}</span>
                        <span className="font-mono text-xs text-muted-foreground">{t.email || "—"}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <Badge variant="outline" className="capitalize">{t.subscription_tier}</Badge>
                        <span className="text-xs text-muted-foreground">{t.subscription_status}</span>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      <div>R {t.quota_used.reels}/{t.quota_limit.reels} · C {t.quota_used.carousels}/{t.quota_limit.carousels}</div>
                      {(t.bonus_quota.reels > 0 || t.bonus_quota.carousels > 0) && (
                        <div className="text-primary">+{t.bonus_quota.reels}R / +{t.bonus_quota.carousels}C bonus</div>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      ₹{t.cogs_inr} / ₹{t.revenue_inr}
                    </TableCell>
                    <TableCell>
                      {t.margin_pct === null ? (
                        <span className="font-mono text-xs text-muted-foreground">—</span>
                      ) : (
                        <Badge variant="outline" className={cn("font-mono text-xs tabular-nums", isLowMargin ? "border-bad/50 text-bad" : "border-ok/40 text-ok")}>
                          {t.margin_pct}%
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {t.is_active ? (
                        <Badge variant="outline" className="border-ok/40 bg-ok/10 text-ok">Active</Badge>
                      ) : (
                        <Badge variant="outline" className="border-bad/40 bg-bad/10 text-bad">Suspended</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          title="Add bonus quota"
                          onClick={() => setQuotaTarget(t)}
                          className="h-8 px-2 text-xs"
                        >
                          <PlusCircle className="mr-1 size-3.5" aria-hidden />
                          Quota
                        </Button>
                        {t.role === "client" && t.is_active && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            title="Support impersonation (15m read-only)"
                            onClick={() => setImpTarget(t)}
                            className="h-8 px-2 text-xs"
                          >
                            <Eye className="mr-1 size-3.5" aria-hidden />
                            View as
                          </Button>
                        )}
                        {canMutate && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => setSuspendTarget(t)}
                            className={cn("h-8 px-2 text-xs", t.is_active ? "text-bad hover:text-bad" : "text-ok hover:text-ok")}
                          >
                            {t.is_active ? <Ban className="mr-1 size-3.5" /> : <CheckCircle className="mr-1 size-3.5" />}
                            {t.is_active ? "Suspend" : "Restore"}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        {total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
            <span className="font-mono tabular-nums">
              Showing {offset + 1}–{Math.min(offset + tenants.length, total)} of {total}
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={offset === 0 || loading}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={offset + PAGE_SIZE >= total || loading}
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </CardContent>

      {/* Suspend / Restore Dialog */}
      <Dialog open={!!suspendTarget} onOpenChange={(o) => !o && setSuspendTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{suspendTarget?.is_active ? "Suspend Tenant Account" : "Reactivate Tenant Account"}</DialogTitle>
            <DialogDescription>
              {suspendTarget?.is_active
                ? `Suspending ${suspendTarget?.username || suspendTarget?.email} immediately revokes all active sessions.`
                : `Restoring ${suspendTarget?.username || suspendTarget?.email} re-enables sign-in access.`}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="suspend-reason">Audit reason (optional)</Label>
            <Input
              id="suspend-reason"
              value={suspendReason}
              onChange={(e) => setSuspendReason(e.target.value)}
              placeholder="e.g. Chargeback / spam abuse"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSuspendTarget(null)}>Cancel</Button>
            <Button
              type="button"
              variant={suspendTarget?.is_active ? "destructive" : "default"}
              onClick={handleSuspend}
              disabled={busy}
            >
              {busy ? "Saving…" : suspendTarget?.is_active ? "Confirm Suspend" : "Confirm Restore"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bonus Quota Dialog */}
      <Dialog open={!!quotaTarget} onOpenChange={(o) => !o && setQuotaTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adjust Bonus Quota</DialogTitle>
            <DialogDescription>
              Add extra reels or carousels for {quotaTarget?.username || quotaTarget?.email} on top of their plan limit.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="bonus-reels">Add Reels</Label>
              <Input id="bonus-reels" type="number" value={bonusReels} onChange={(e) => setBonusReels(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bonus-carousels">Add Carousels</Label>
              <Input id="bonus-carousels" type="number" value={bonusCarousels} onChange={(e) => setBonusCarousels(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="bonus-reason">Reason</Label>
            <Input id="bonus-reason" value={bonusReason} onChange={(e) => setBonusReason(e.target.value)} placeholder="e.g. Incident compensation" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setQuotaTarget(null)}>Cancel</Button>
            <Button type="button" onClick={handleBonusQuota} disabled={busy}>{busy ? "Applying…" : "Apply Bonus"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Support Impersonation Dialog */}
      <Dialog open={!!impTarget} onOpenChange={(o) => !o && setImpTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Start Audited Support Impersonation</DialogTitle>
            <DialogDescription>
              Issues a 15-minute read-only session as @{impTarget?.username || impTarget?.email}. Every write action is blocked and this session is logged.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="imp-reason">Support Ticket / Reason (min 10 characters)</Label>
            <Input
              id="imp-reason"
              value={impReason}
              onChange={(e) => setImpReason(e.target.value)}
              placeholder="Ticket #SUP-1042: Investigating failed YouTube publish"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setImpTarget(null)}>Cancel</Button>
            <Button type="button" onClick={handleImpersonate} disabled={busy || impReason.trim().length < 10}>
              {busy ? "Starting…" : "Start Read-Only Session"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
