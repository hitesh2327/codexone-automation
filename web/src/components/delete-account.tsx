import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LoaderCircle, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { OtpInput } from "@/components/otp-input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Profile } from "@/lib/profile";

const GOES = [
  "Your profile, preferences and billing details",
  "Your Instagram, YouTube and Telegram connections",
  "Every post Mintly made for you, with its images and videos",
  "Your subscription, cancelled now with no refund for the time left",
];
const STAYS = [
  "Posts already published on Instagram or YouTube (delete them there)",
  "Payment records Razorpay must keep for tax law",
];

/**
 * Profile > Security: close the account and erase its data (DPDP right to erasure; Meta and YouTube deletion).
 * Proof first: the password, or an emailed code for accounts without one; then the word DELETE.
 */
export function DeleteAccount({ p }: { p: Profile }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t pt-6">
      <div>
        <p className="font-medium">Delete your account</p>
        <p className="text-sm text-muted-foreground">Erase your account and everything Mintly made for you. This can't be undone.</p>
      </div>
      <Button variant="outline" className="text-bad hover:text-bad" onClick={() => setOpen(true)}>
        <Trash2 aria-hidden />Delete account
      </Button>
      <DeleteDialog p={p} open={open} onOpenChange={setOpen} />
    </div>
  );
}

function DeleteDialog({ p, open, onOpenChange }: { p: Profile; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [left, setLeft] = useState(0);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (!open) { setPassword(""); setCode(""); setTyped(""); setError(null); } }, [open]);
  useEffect(() => { if (left <= 0) return; const t = setTimeout(() => setLeft((n) => n - 1), 1000); return () => clearTimeout(t); }, [left]);

  async function sendCode() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ cooldown?: number }>("/api/profile/delete/otp", { method: "POST" });
      setSent(true);
      setLeft(r.cooldown ?? 60);
      toast.success(`Code sent to ${p.email}`);
    } catch (x) {
      setError(x instanceof ApiError ? x.message : "Couldn't send the code. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (p.has_password ? !password : code.length < 6) {
      setError(p.has_password ? "Enter your password." : "Enter the 6-digit code from your email.");
      return;
    }
    if (typed.trim() !== "DELETE") { setError("Type DELETE to confirm."); return; }
    setBusy(true);
    setError(null);
    try {
      await api("/api/profile/delete", { method: "POST", body: { confirm: typed.trim(),
        ...(p.has_password ? { current_password: password } : { code }) } });
      await logout().catch(() => undefined);   // the server already ended the session
      navigate("/login", { replace: true, state: { notice: "Your account and its data were deleted." } });
    } catch (x) {
      setError(x instanceof ApiError ? x.message : "Couldn't delete the account. Nothing was changed.");
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Delete your account?</DialogTitle>
          <DialogDescription>This is permanent and can't be undone.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 text-sm">
          <div className="grid gap-1.5">
            <p className="label-mono">Deleted</p>
            <ul className="grid gap-1">
              {GOES.map((t) => <li key={t} className="flex gap-2"><span aria-hidden className="mt-[0.55em] size-1.5 shrink-0 rounded-[1px] bg-bad" />{t}</li>)}
            </ul>
          </div>
          <div className="grid gap-1.5">
            <p className="label-mono">Kept</p>
            <ul className="grid gap-1 text-muted-foreground">
              {STAYS.map((t) => <li key={t} className="flex gap-2"><span aria-hidden className="mt-[0.55em] size-1.5 shrink-0 rounded-[1px] bg-muted-foreground/60" />{t}</li>)}
            </ul>
          </div>

          {p.has_password ? (
            <label className="grid gap-1.5 text-xs text-muted-foreground">Your password
              <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} />
            </label>
          ) : sent ? (
            <div className="grid gap-2">
              <p className="text-xs text-muted-foreground">Enter the code we sent to {p.email}.</p>
              <OtpInput value={code} onChange={setCode} disabled={busy} label="Code to delete your account" />
              <button type="button" onClick={sendCode} disabled={busy || left > 0}
                      className="justify-self-start text-xs text-primary underline-offset-4 hover:underline disabled:text-muted-foreground disabled:no-underline">
                {left > 0 ? `Send a new code in ${left}s` : "Send a new code"}
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">You signed in with Google, so we'll email {p.email} a code to prove it's you.</p>
              <Button variant="outline" size="sm" onClick={sendCode} disabled={busy}>Email me a code</Button>
            </div>
          )}

          <label className="grid gap-1.5 text-xs text-muted-foreground">Type DELETE to confirm
            <Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} disabled={busy} className="font-mono" />
          </label>
          {error && <p role="alert" className="text-xs text-bad">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>Keep my account</Button>
          <Button variant="destructive" onClick={remove} disabled={busy}>
            {busy ? <LoaderCircle className="animate-spin" /> : <Trash2 aria-hidden />}Delete account
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
