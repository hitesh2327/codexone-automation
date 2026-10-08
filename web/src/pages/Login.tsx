import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";

import { AuthStage, Label2 } from "@/components/auth-stage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, googleLoginUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { slotName, slotsHeadline, type Brand } from "@/lib/brand";

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  google_cancelled: "Google sign-in was cancelled. You can try again or sign in with your password.",
  no_verified_email: "Your Google account doesn't have a verified email address.",
  not_allowed: "That Google account isn't linked to a @codexonebyhitesh account.",
  disabled: "Your account has been disabled. Contact the account owner.",
};

function googleErrorMessage(code: string | null): string | null {
  if (!code) return null;
  return GOOGLE_ERROR_MESSAGES[code] ?? null;
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="size-4">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.07H2.18a11 11 0 0 0 0 9.86l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.55 10.55 0 0 0 12 1 11 11 0 0 0 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
    </svg>
  );
}

/** The daily slots from the brand config, set like a menu: name, a dotted leader, the time. */
function Slots({ times }: { times: string[] }) {
  if (!times.length) return null;
  const names = times.map(slotName);
  return (
    <ul className="mt-10 grid max-w-sm gap-3 font-mono text-sm motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300" aria-label="Daily posting slots">
      {times.map((time, i) => {
        // two slots in the same part of the day get numbered ("Evening slot 2"), so names stay unique
        const same = names.filter((n) => n === names[i]).length > 1;
        const name = same ? `${names[i]} ${names.slice(0, i + 1).filter((n) => n === names[i]).length}` : names[i];
        return (
        <li key={time} className="flex items-baseline gap-3">
          <span className="text-foreground/80">{name}</span>
          <span aria-hidden className="flex-1 translate-y-[-3px] border-b border-dotted border-foreground/25" />
          <span className="tabular-nums text-signal">{time} IST</span>
        </li>
        );
      })}
    </ul>
  );
}

export default function Login({ brand }: { brand: Brand | null }) {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(googleErrorMessage(params.get("error")));
  const [notice] = useState<string | null>((location.state as { notice?: string } | null)?.notice ?? null);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [providers, setProviders] = useState<"loading" | "ready" | "offline">("loading");
  const [attempt, setAttempt] = useState(0);
  const [missing, setMissing] = useState<{ username: boolean; password: boolean }>({ username: false, password: false });
  const userRef = useRef<HTMLInputElement>(null);
  const passRef = useRef<HTMLInputElement>(null);

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  // Which sign-in options exist. One failed request (a restarting server, a flaky connection) must never
  // silently remove Google sign-in, so retry with a short back-off and say so if the server can't be reached.
  useEffect(() => {
    let cancelled = false;
    setProviders("loading");
    (async () => {
      for (let i = 0; i < 4; i++) {
        try {
          const p = await api<{ google: boolean }>("/api/auth/providers");
          if (!cancelled) { setGoogleEnabled(p.google); setProviders("ready"); }
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 700 * (i + 1)));
          if (cancelled) return;
        }
      }
      if (!cancelled) setProviders("offline");
    })();
    return () => { cancelled = true; };
  }, [attempt]);

  useEffect(() => {
    if (user) navigate(from, { replace: true });
  }, [user, from, navigate]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    // validate on submit (the button stays enabled, so the first screen has a real call to action)
    const miss = { username: !username.trim(), password: !password };
    setMissing(miss);
    if (miss.username || miss.password) {
      setError(null);
      (miss.username ? userRef : passRef).current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthStage
      handle={brand?.handle}
      aside={
        <>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Content desk</p>
          <h1 className="mt-5 max-w-lg font-heading text-[3.4rem] leading-[1.02] font-semibold tracking-tight">
            {slotsHeadline(brand?.post_times_ist)}
            <br />
            <span className="relative inline-block">
              One desk.
              <span aria-hidden className="absolute -bottom-1 left-0 h-[5px] w-full bg-[var(--brand-accent)]" />
            </span>
          </h1>
          <p className="mt-6 max-w-md text-base leading-relaxed text-muted-foreground">
            Review what was written, approve what's good, and watch it go live. Nothing posts until you say so.
          </p>
          <Slots times={brand?.post_times_ist ?? []} />
        </>
      }
    >
      <h2 className="font-heading text-3xl font-semibold tracking-tight">Sign in</h2>
      <p className="mt-2 text-sm text-muted-foreground">Use your username or email.</p>

      {notice && <p role="status" className="mt-6 border-l-[3px] border-ok bg-ok/10 px-3 py-2 text-sm text-ok">{notice}</p>}
      {error && (
        <p role="alert" className="mt-6 flex items-start gap-2 border-l-[3px] border-bad bg-bad/10 px-3 py-2 text-sm text-bad">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />{error}
        </p>
      )}

      <form onSubmit={onSubmit} className="mt-8 grid gap-6" noValidate>
        <div className="grid gap-2">
          <Label2 htmlFor="username">Username or email</Label2>
          <Input id="username" ref={userRef} autoComplete="username" autoCapitalize="none" spellCheck={false} required value={username}
                 onChange={(e) => { setUsername(e.target.value); if (missing.username) setMissing((m) => ({ ...m, username: false })); }} disabled={busy} className="h-11"
                 aria-invalid={missing.username || undefined} aria-describedby={missing.username ? "username-missing" : undefined} />
          {missing.username && <p id="username-missing" className="text-xs text-bad">Enter your username or email.</p>}
        </div>
        <div className="grid gap-2">
          <Label2 htmlFor="password" right={
            <Link to="/forgot-password" state={{ identifier: username.trim() }} className="text-xs text-primary underline-offset-4 hover:underline relative after:absolute after:-inset-x-1 after:-inset-y-3 after:content-['']">
              Forgot password?
            </Link>}>Password</Label2>
          <div className="relative">
            <Input id="password" ref={passRef} type={showPassword ? "text" : "password"} autoComplete="current-password" required value={password}
                   onChange={(e) => { setPassword(e.target.value); if (missing.password) setMissing((m) => ({ ...m, password: false })); }} disabled={busy} className="h-11 pr-11"
                   aria-invalid={missing.password || undefined} aria-describedby={missing.password ? "password-missing" : undefined} />
            <button type="button" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}
                    className="absolute top-0.5 right-0.5 grid size-10 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          {missing.password && <p id="password-missing" className="text-xs text-bad">Enter your password.</p>}
        </div>
        <Button type="submit" className="group h-11 justify-between font-semibold" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
          {busy ? <LoaderCircle className="animate-spin" /> : <ArrowRight className="transition-transform group-hover:translate-x-0.5" />}
        </Button>
      </form>

      {providers === "loading" && (
        <div className="mt-8 grid gap-4" aria-hidden>
          <span className="h-4" />
          <span className="h-11 animate-pulse rounded-md bg-muted" />
        </div>
      )}

      {providers === "offline" && (
        <p role="status" className="mt-8 border-l-[3px] border-wait bg-wait/10 px-3 py-2 text-sm leading-relaxed">
          Couldn't reach the server, so Google sign-in can't be shown yet.{" "}
          <button type="button" className="text-primary underline-offset-4 hover:underline relative after:absolute after:-inset-x-1 after:-inset-y-3 after:content-['']" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </p>
      )}

      {providers === "ready" && googleEnabled && (
        <div className="mt-8 grid gap-4">
          <p className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            <span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" />
          </p>
          <Button asChild variant="outline" className="h-11">
            <a href={googleLoginUrl}><GoogleIcon />Continue with Google</a>
          </Button>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Signed in with Google before and never set a password? <Link to="/forgot-password" className="text-primary underline-offset-4 hover:underline">Set one with an emailed code.</Link>
          </p>
        </div>
      )}

      <div className="mt-8 border-t border-border/50 pt-4 text-center text-xs text-muted-foreground">
        Don't have an account?{" "}
        <Link to="/signup" className="font-medium text-foreground underline-offset-4 hover:underline">
          Create an account
        </Link>
      </div>
    </AuthStage>
  );
}
