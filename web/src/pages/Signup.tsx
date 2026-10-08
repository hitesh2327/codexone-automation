import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, Eye, EyeOff, LoaderCircle, ShieldCheck, Sparkles } from "lucide-react";

import { AuthStage, Label2 } from "@/components/auth-stage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, googleLoginUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Brand } from "@/lib/brand";

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

function passwordStrength(p: string): { score: number; label: string; color: string } {
  if (!p) return { score: 0, label: "Empty", color: "bg-muted" };
  let score = 0;
  if (p.length >= 8) score++;
  if (p.length >= 12) score++;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) score++;
  if (/[0-9]/.test(p)) score++;
  if (/[^A-Za-z0-9]/.test(p)) score++;

  if (score <= 2) return { score: 1, label: "Weak", color: "bg-amber-500" };
  if (score <= 4) return { score: 2, label: "Good", color: "bg-blue-500" };
  return { score: 3, label: "Strong", color: "bg-emerald-500" };
}

export default function Signup({ brand }: { brand: Brand | null }) {
  const { user, signup } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [providersLoading, setProvidersLoading] = useState(true);

  useEffect(() => {
    if (user) {
      navigate("/config", { replace: true, state: { onboarding: true } });
    }
  }, [user, navigate]);

  useEffect(() => {
    api<{ google: boolean }>("/api/auth/providers")
      .then((p) => setGoogleEnabled(p.google))
      .catch(() => {})
      .finally(() => setProvidersLoading(false));
  }, []);

  const strength = passwordStrength(password);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim() || !email.trim() || !password) {
      setError("Please fill in all required fields.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    setBusy(true);
    try {
      await signup({
        username: username.trim().toLowerCase(),
        email: email.trim().toLowerCase(),
        password,
        name: name.trim() || username.trim(),
      });
      navigate("/config", { replace: true, state: { onboarding: true } });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to create account.");
      } else {
        setError("Network error. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthStage
      handle={brand?.handle}
      aside={
        <>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Get started</p>
          <h1 className="mt-5 max-w-lg font-heading text-[3.4rem] leading-[1.02] font-semibold tracking-tight">
            Automate your reach.
            <br />
            <span className="relative inline-block">
              Your own desk.
              <span aria-hidden className="absolute -bottom-1 left-0 h-[5px] w-full bg-[var(--brand-accent)]" />
            </span>
          </h1>
          <p className="mt-6 max-w-md text-base leading-relaxed text-muted-foreground">
            Generate and schedule high-retention Instagram Reels, Carousels, and YouTube Shorts personalized to your style and audience.
          </p>
          <div className="mt-8 grid max-w-sm gap-3 font-mono text-xs text-foreground/80">
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-signal shrink-0" />
              <span>Personalized AI Scriptwriting & Imagery</span>
            </div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-ok shrink-0" />
              <span>Multi-Platform Auto-Posting (IG + YT Shorts)</span>
            </div>
          </div>
        </>
      }
    >
      <h2 className="font-heading text-3xl font-semibold tracking-tight">Create account</h2>
      <p className="mt-2 text-sm text-muted-foreground">Sign up to configure your automated desk.</p>

      {error && (
        <div role="alert" className="mt-6 flex items-start gap-2 border-l-[3px] border-bad bg-bad/10 px-3 py-2 text-sm text-bad">
          <AlertCircle className="size-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Google Sign Up Button */}
      {(googleEnabled || providersLoading) && (
        <div className="mt-6 grid gap-4">
          <Button asChild variant="outline" className="h-11 w-full font-medium">
            <a href={googleLoginUrl}>
              <GoogleIcon />
              Sign up with Google
            </a>
          </Button>

          <p className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            <span className="h-px flex-1 bg-border" />or with email<span className="h-px flex-1 bg-border" />
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit} className={googleEnabled ? "mt-4 grid gap-4" : "mt-8 grid gap-4"} noValidate>
        <div className="grid gap-1.5">
          <Label2 htmlFor="signup-name">Full Name (Optional)</Label2>
          <Input
            id="signup-name"
            placeholder="Hitesh Lalwani"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            disabled={busy}
            className="h-10"
          />
        </div>

        <div className="grid gap-1.5">
          <Label2 htmlFor="signup-username">Username</Label2>
          <Input
            id="signup-username"
            placeholder="creator_handle"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="username"
            disabled={busy}
            required
            className="h-10"
          />
        </div>

        <div className="grid gap-1.5">
          <Label2 htmlFor="signup-email">Email Address</Label2>
          <Input
            id="signup-email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="email"
            disabled={busy}
            required
            className="h-10"
          />
        </div>

        <div className="grid gap-1.5">
          <Label2 htmlFor="signup-password">Password</Label2>
          <div className="relative">
            <Input
              id="signup-password"
              type={showPassword ? "text" : "password"}
              placeholder="At least 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              disabled={busy}
              className="h-10 pr-10"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-1"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          {password && (
            <div className="flex items-center gap-2 pt-1">
              <div className="flex-1 h-1 rounded-full bg-muted overflow-hidden flex gap-1">
                <div className={`h-full flex-1 transition-all ${strength.score >= 1 ? strength.color : "bg-transparent"}`} />
                <div className={`h-full flex-1 transition-all ${strength.score >= 2 ? strength.color : "bg-transparent"}`} />
                <div className={`h-full flex-1 transition-all ${strength.score >= 3 ? strength.color : "bg-transparent"}`} />
              </div>
              <span className="text-[10px] text-muted-foreground font-mono">{strength.label}</span>
            </div>
          )}
        </div>

        <div className="grid gap-1.5">
          <Label2 htmlFor="signup-confirm-password">Confirm Password</Label2>
          <Input
            id="signup-confirm-password"
            type={showPassword ? "text" : "password"}
            placeholder="Repeat your password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
            disabled={busy}
            required
            className="h-10"
          />
        </div>

        <Button type="submit" className="mt-2 h-11 justify-between font-semibold" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
          {busy ? <LoaderCircle className="animate-spin" /> : <ArrowRight className="size-4" />}
        </Button>
      </form>

      <div className="mt-8 border-t border-border/50 pt-4 text-center text-xs text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </div>
    </AuthStage>
  );
}
