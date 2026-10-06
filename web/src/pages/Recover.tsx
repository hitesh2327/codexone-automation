import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, LoaderCircle } from "lucide-react";

import { AuthStage, Label2 } from "@/components/auth-stage";
import { OtpInput } from "@/components/otp-input";
import { PasswordField, passwordAcceptable } from "@/components/password-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import type { Brand } from "@/lib/brand";
import { forgotPassword, resetPassword } from "@/lib/profile";
import { cn } from "@/lib/utils";

const STEPS = ["Find your account", "Enter the code", "Choose a password"] as const;

/** Resend countdown that survives re-renders; returns seconds left and a way to restart it. */
function useCountdown() {
  const [until, setUntil] = useState(0);
  const [left, setLeft] = useState(0);
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.ceil((until - Date.now()) / 1000)));
    tick();
    const t = setInterval(tick, 500);
    return () => clearInterval(t);
  }, [until]);
  return { left, start: (secs: number) => setUntil(Date.now() + secs * 1000) };
}

export default function Recover({ brand }: { brand: Brand | null }) {
  const navigate = useNavigate();
  const prefill = (useLocation().state as { identifier?: string } | null)?.identifier ?? "";
  const [step, setStep] = useState(0);
  const [identifier, setIdentifier] = useState(prefill);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const cooldown = useCountdown();

  const mismatch = pw2.length > 0 && pw !== pw2;
  const canFinish = passwordAcceptable(pw, identifier) && pw === pw2;

  async function send(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await forgotPassword(identifier.trim());
      cooldown.start(r.cooldown ?? 60);
      setCode("");
      setStep(1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function finish(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await resetPassword(identifier.trim(), code, pw);
      setDone(true);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
      setError(msg);
      if (err instanceof ApiError && err.status === 400) { setStep(1); setCode(""); } // wrong/expired code: back to the boxes
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthStage handle={brand?.handle} aside={<h1 className="font-heading text-[3.4rem] leading-[1.02] font-semibold tracking-tight">You're<br />back in.</h1>}>
        <span className="grid size-12 place-items-center rounded-[30%] bg-ok/15 text-ok"><Check aria-hidden /></span>
        <span aria-hidden className="amber-rule mt-8" />
        <h2 className="mt-4 font-heading text-3xl font-semibold tracking-tight">Password updated</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Every device that was signed in has been signed out. Sign in with your new password{identifier.includes("@") ? " or your email" : ""}.
        </p>
        <Button className="mt-8 h-11 w-full justify-between font-semibold" onClick={() => navigate("/login", { replace: true, state: { notice: "Password updated. Sign in with the new one." } })}>
          Go to sign in <ArrowRight />
        </Button>
      </AuthStage>
    );
  }

  return (
    <AuthStage
      handle={brand?.handle}
      aside={
        <>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Account recovery</p>
          <h1 className="mt-5 max-w-md font-heading text-[3.1rem] leading-[1.04] font-semibold tracking-tight">
            Lost the key?<br />We'll email a new one.
          </h1>
          <ol className="mt-12 grid max-w-sm gap-5" aria-label="Steps">
            {STEPS.map((label, i) => (
              <li key={label} className={cn("flex items-baseline gap-4 transition-opacity", i > step && "opacity-35")}>
                <span className={cn("font-mono text-sm tabular-nums", i === step ? "text-[var(--brand-accent)]" : "text-muted-foreground")}>0{i + 1}</span>
                <span className="flex-1 border-b border-dotted border-foreground/20 pb-1 text-lg">
                  {label}{i < step && <span className="sr-only"> (done)</span>}{i === step && <span className="sr-only"> (current step)</span>}
                </span>
                {i < step && <Check className="size-4 text-ok" aria-hidden />}
              </li>
            ))}
          </ol>
        </>
      }
    >
      <Link to="/login" className="mb-8 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Back to sign in</Link>
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground lg:hidden">Step {step + 1} of 3 · {STEPS[step]}</p>

      {step === 0 && (
        <form onSubmit={send} className="grid gap-6" noValidate>
          <div>
            <h2 className="font-heading text-3xl font-semibold tracking-tight">Forgot your password?</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Enter the email or username on your account and we'll send a 6-digit code. This also works if you've only ever signed in with Google and want to add a password.
            </p>
          </div>
          <div className="grid gap-2">
            <Label2 htmlFor="identifier">Email or username</Label2>
            <Input id="identifier" autoFocus autoComplete="username" autoCapitalize="none" spellCheck={false} value={identifier}
                   onChange={(e) => setIdentifier(e.target.value)} disabled={busy} className="h-11" />
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="h-11 justify-between font-semibold" disabled={busy || !identifier.trim()}>
            {busy ? "Sending…" : "Email me a code"}{busy ? <LoaderCircle className="animate-spin" /> : <ArrowRight />}
          </Button>
        </form>
      )}

      {step === 1 && (
        <form onSubmit={(e) => { e.preventDefault(); if (code.length === 6) { setError(null); setStep(2); } }} className="grid gap-6">
          <div>
            <h2 className="font-heading text-3xl font-semibold tracking-tight">Check your inbox</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              If that matches an account with an email address, a 6-digit code is on its way. It's good for 10 minutes.
            </p>
          </div>
          <OtpInput value={code} onChange={(v) => { setCode(v); setError(null); }} onComplete={() => setStep(2)} invalid={!!error} />
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="h-11 justify-between font-semibold" disabled={code.length !== 6}>Continue<ArrowRight /></Button>
          <p className="text-sm text-muted-foreground">
            Didn't get it?{" "}
            {cooldown.left > 0 ? (
              <span className="tabular-nums">Resend in 0:{String(cooldown.left).padStart(2, "0")}</span>
            ) : (
              <button type="button" className="text-primary underline-offset-4 hover:underline" disabled={busy} onClick={() => send()}>Send a new code</button>
            )}
            {" · "}
            <button type="button" className="underline-offset-4 hover:underline" onClick={() => { setStep(0); setError(null); }}>Change account</button>
          </p>
        </form>
      )}

      {step === 2 && (
        <form onSubmit={finish} className="grid gap-6" noValidate>
          <div>
            <h2 className="font-heading text-3xl font-semibold tracking-tight">Choose a new password</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">Pick something you don't use anywhere else. A few unrelated words works well.</p>
          </div>
          <PasswordField label="New password" value={pw} onChange={setPw} meter identity={[identifier]} autoFocus disabled={busy} />
          <PasswordField label="Type it again" value={pw2} onChange={setPw2} disabled={busy} error={mismatch ? "These don't match yet." : null} />
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="h-11 justify-between font-semibold" disabled={busy || !canFinish}>
            {busy ? "Saving…" : "Update password"}{busy ? <LoaderCircle className="animate-spin" /> : <Check />}
          </Button>
          <button type="button" className="text-left text-sm text-muted-foreground underline-offset-4 hover:underline" onClick={() => setStep(1)}>← Re-enter the code</button>
        </form>
      )}
    </AuthStage>
  );
}
