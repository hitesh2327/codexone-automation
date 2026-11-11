import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, LogOut, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { exitImpersonation } from "@/lib/admin";
import { useAuth, type User } from "@/lib/auth";

export function SupportImpersonationBanner() {
  const { user, applySessionUser } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number>(() => {
    if (!user?.impersonation_expires_at) return 900;
    return Math.max(0, Math.floor((new Date(user.impersonation_expires_at).getTime() - Date.now()) / 1000));
  });

  useEffect(() => {
    if (!user?.impersonated_by || !user.impersonation_expires_at) return;
    const targetMs = new Date(user.impersonation_expires_at).getTime();
    const tick = () => setSecondsLeft(Math.max(0, Math.floor((targetMs - Date.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [user?.impersonated_by, user?.impersonation_expires_at]);

  if (!user?.impersonated_by) return null;

  const mins = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
  const secs = String(secondsLeft % 60).padStart(2, "0");
  const targetLabel = user.username ? `@${user.username}` : user.email || `User #${user.id}`;

  async function handleExit() {
    setBusy(true);
    try {
      const res = await exitImpersonation();
      applySessionUser(res.user as User);
      toast.success("Returned to your operator session");
      navigate("/admin", { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to exit impersonation");
      setBusy(false);
    }
  }

  return (
    <div
      role="alert"
      className="sticky top-0 z-50 flex flex-wrap items-center justify-between gap-3 border-b border-amber-600 bg-amber-500 px-4 py-2 text-sm font-medium text-amber-950 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <ShieldAlert className="size-4 shrink-0" aria-hidden />
        <span>
          <strong>SUPPORT IMPERSONATION:</strong> Viewing as{" "}
          <span className="font-mono font-semibold underline underline-offset-2">{targetLabel}</span>
        </span>
        <span className="rounded border border-amber-950/20 bg-amber-950/10 px-2 py-0.5 font-mono text-[11px] font-semibold uppercase">
          {user.impersonation_read_only !== false ? "Read-Only" : "Write Enabled"}
        </span>
        {user.impersonation_reason && (
          <span className="hidden text-xs text-amber-950/85 lg:inline">
            Reason: {user.impersonation_reason}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="inline-flex items-center gap-1.5 font-mono text-xs tabular-nums">
          <Clock className="size-3.5" aria-hidden />
          {secondsLeft > 0 ? `${mins}:${secs}` : "Expired"}
        </span>
        <Button
          type="button"
          size="sm"
          onClick={handleExit}
          disabled={busy}
          className="h-7 gap-1.5 bg-amber-950 px-3 text-xs font-semibold text-amber-50 hover:bg-amber-900"
        >
          <LogOut className="size-3.5" aria-hidden />
          {busy ? "Exiting…" : "Exit Impersonation"}
        </Button>
      </div>
    </div>
  );
}
