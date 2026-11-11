import { useCallback, useEffect, useState } from "react";
import { Flag, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  deleteFlag,
  getSafety,
  listAudit,
  listFlags,
  updateSafety,
  upsertFlag,
  type AuditEvent,
  type FeatureFlag,
  type KillSwitches,
} from "@/lib/admin";
import { cn } from "@/lib/utils";

const SWITCH_META: { key: keyof Pick<KillSwitches, "generation" | "publishing" | "signups">; title: string; desc: string }[] = [
  { key: "generation", title: "Generation Kill-Switch", desc: "Halts all new /api/generate dispatches (HTTP 503)." },
  { key: "publishing", title: "Publishing Kill-Switch", desc: "Halts Instagram & YouTube publishing globally." },
  { key: "signups", title: "Signups Kill-Switch", desc: "Pauses new /api/auth/signup registrations (HTTP 503)." },
];

export function SafetyFlagsTab({ onMutated }: { onMutated: () => void }) {
  const [switches, setSwitches] = useState<KillSwitches | null>(null);
  const [reason, setReason] = useState("");
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [newKey, setNewKey] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [sRes, fRes, aRes] = await Promise.all([getSafety(), listFlags(), listAudit(30)]);
      setSwitches(sRes.kill_switches);
      setReason(sRes.kill_switches.reason || "");
      setFlags(fRes.flags);
      setAudit(aRes.events);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load safety controls");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleSwitch(key: "generation" | "publishing" | "signups") {
    if (!switches) return;
    setBusy(true);
    try {
      const nextVal = !switches[key];
      const res = await updateSafety({ [key]: nextVal, reason: reason.trim() });
      setSwitches(res.kill_switches);
      toast.success(`${key} kill-switch ${nextVal ? "ACTIVATED" : "cleared"}`);
      await load();
      onMutated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update kill-switch");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleFlag(f: FeatureFlag) {
    setBusy(true);
    try {
      const res = await upsertFlag({ ...f, enabled: !f.enabled });
      setFlags(res.flags);
      toast.success(`${f.key} ${!f.enabled ? "enabled" : "disabled"}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update flag");
    } finally {
      setBusy(false);
    }
  }

  async function handleRolloutChange(f: FeatureFlag, pct: number) {
    setBusy(true);
    try {
      const clamped = Math.max(0, Math.min(100, Math.round(pct)));
      const res = await upsertFlag({ ...f, rollout_pct: clamped });
      setFlags(res.flags);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update rollout %");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddFlag(e: React.FormEvent) {
    e.preventDefault();
    const key = newKey.trim().toLowerCase();
    if (!/^[a-z0-9_.-]+$/.test(key)) {
      toast.error("Flag key must use lowercase letters, numbers, dots, dashes, or underscores.");
      return;
    }
    setBusy(true);
    try {
      const res = await upsertFlag({ key, enabled: false, rollout_pct: 0, description: newDesc.trim() });
      setFlags(res.flags);
      setNewKey("");
      setNewDesc("");
      toast.success(`Added feature flag ${key}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create flag");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteFlag(key: string) {
    setBusy(true);
    try {
      const res = await deleteFlag(key);
      setFlags(res.flags);
      toast.success(`Deleted ${key}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete flag");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      {/* Kill Switches */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert className="size-4 text-bad" aria-hidden />
            Emergency Circuit-Breaker Kill-Switches
          </CardTitle>
          <CardDescription>Immediately halts global subsystems (cached 30s, invalidated immediately on save).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-1.5 max-w-md">
            <Label htmlFor="ks-reason">Incident / Maintenance Reason</Label>
            <Input
              id="ks-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Upstream Gemini outage / bot signup spike"
            />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {SWITCH_META.map((m) => {
              const tripped = Boolean(switches?.[m.key]);
              return (
                <div
                  key={m.key}
                  className={cn(
                    "flex flex-col justify-between gap-3 rounded-lg border p-4 transition-colors",
                    tripped ? "border-bad/60 bg-bad/10" : "bg-card",
                  )}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-sm">{m.title}</span>
                      <Badge variant="outline" className={tripped ? "border-bad text-bad font-mono" : "border-ok/40 text-ok font-mono"}>
                        {tripped ? "TRIPPED" : "NORMAL"}
                      </Badge>
                    </div>
                    <p className="mt-1.5 text-xs text-muted-foreground">{m.desc}</p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={tripped ? "outline" : "destructive"}
                    disabled={busy || !switches}
                    onClick={() => toggleSwitch(m.key)}
                  >
                    {tripped ? "Resume Service" : "Trip Kill-Switch"}
                  </Button>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Feature Flags */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Flag className="size-4 text-primary" aria-hidden />
            Feature Flags & Rollouts
          </CardTitle>
          <CardDescription>DB-backed runtime toggles with percentage rollout control.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <form onSubmit={handleAddFlag} className="flex flex-wrap items-end gap-2 rounded-md border bg-sunken p-3">
            <div className="grid gap-1">
              <Label htmlFor="flag-key" className="text-xs">Flag key</Label>
              <Input id="flag-key" value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="new_feature_beta" className="h-8 w-44 font-mono text-xs" />
            </div>
            <div className="grid flex-1 min-w-48 gap-1">
              <Label htmlFor="flag-desc" className="text-xs">Description</Label>
              <Input id="flag-desc" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Short description…" className="h-8 text-xs" />
            </div>
            <Button type="submit" size="sm" disabled={busy || !newKey.trim()} className="h-8 gap-1">
              <Plus className="size-3.5" />
              Add Flag
            </Button>
          </form>

          <div className="grid gap-2">
            {flags.map((f) => (
              <div key={f.key} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium">{f.key}</span>
                    <Badge variant="outline" className={cn("font-mono text-[11px]", f.enabled ? "border-ok/40 text-ok" : "text-muted-foreground")}>
                      {f.enabled ? "ON" : "OFF"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{f.description || "No description"}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Label htmlFor={`pct-${f.key}`} className="font-mono text-xs text-muted-foreground">Rollout %</Label>
                  <Input
                    id={`pct-${f.key}`}
                    type="number"
                    min={0}
                    max={100}
                    defaultValue={f.rollout_pct}
                    onBlur={(e) => {
                      const val = Number(e.target.value);
                      if (!Number.isNaN(val) && val !== f.rollout_pct) handleRolloutChange(f, val);
                    }}
                    className="h-8 w-20 font-mono text-xs tabular-nums"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant={f.enabled ? "outline" : "default"}
                    disabled={busy}
                    onClick={() => handleToggleFlag(f)}
                    className="h-8 px-3 text-xs"
                  >
                    {f.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    disabled={busy}
                    aria-label={`Delete flag ${f.key}`}
                    onClick={() => handleDeleteFlag(f.key)}
                    className="h-8 w-8 text-muted-foreground hover:text-bad"
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Audit Trail */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Operator Audit Trail</CardTitle>
          <CardDescription>Immutable ActivityLog record of admin mutations & support impersonations.</CardDescription>
        </CardHeader>
        <CardContent>
          {audit.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">No admin audit events recorded yet.</p>
          ) : (
            <ul className="divide-y divide-border/60 text-xs">
              {audit.map((ev) => (
                <li key={ev.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-mono text-primary">{ev.event}</span>
                    <span>{ev.message}</span>
                  </div>
                  <span className="font-mono text-muted-foreground tabular-nums">
                    {ev.actor || "system"} · {ev.created_at?.slice(0, 19).replace("T", " ")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
