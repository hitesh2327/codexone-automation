import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Camera, Check, KeyRound, LoaderCircle, LogOut, Mail, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { AvatarCropper } from "@/components/avatar-cropper";
import { OtpInput } from "@/components/otp-input";
import { PasswordField, passwordAcceptable } from "@/components/password-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { UserAvatar } from "@/components/user-avatar";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  ago, changeEmail, deleteAvatar, firstName, formatDate, getProfile, revokeOtherSessions, savePassword, sendEmailCode,
  sendPasswordCode, timeZones, updateProfile, uploadAvatar, type Profile as ProfileT,
} from "@/lib/profile";
import { cn } from "@/lib/utils";

const err = (e: unknown, fallback = "Something went wrong. Please try again.") => (e instanceof ApiError ? e.message : fallback);
const MONO = "font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground";
const LINE_INPUT =
  "h-12 rounded-none border-0 border-b border-input bg-transparent px-0 text-lg shadow-none focus-visible:border-[var(--brand-accent)] focus-visible:ring-0 dark:bg-transparent";

const SECTIONS = [
  { id: "identity", n: "01", label: "About you" },
  { id: "signin", n: "02", label: "Sign-in & contact" },
  { id: "security", n: "03", label: "Security" },
  { id: "record", n: "04", label: "Account record" },
] as const;

/** A section with a big outlined number, a title, and a line of purpose: each one is laid out for its job. */
function Section({ id, n, title, lead, children }: { id: string; n: string; title: string; lead: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-8 border-t pt-8 first:border-t-0 first:pt-0">
      <header className="mb-8 flex items-start gap-5">
        <span aria-hidden className="select-none font-heading text-6xl leading-none font-bold text-transparent [-webkit-text-stroke:1px_color-mix(in_srgb,var(--brand-text)_28%,transparent)]">{n}</span>
        <div className="pt-1.5">
          <h2 id={`${id}-h`} className="font-heading text-2xl font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">{lead}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
// Header: picture, name, and how complete the profile is
// ---------------------------------------------------------------------------------------------
function completeness(p: ProfileT) {
  const parts = [
    { ok: p.has_avatar, hint: "Add a picture" },
    { ok: !!p.name.trim(), hint: "Add your name" },
    { ok: !!p.job_title.trim(), hint: "Add your job title" },
    { ok: !!p.bio.trim(), hint: "Write a short bio" },
    { ok: !!p.phone.trim(), hint: "Add a phone number" },
    { ok: !!p.email && p.email_verified, hint: "Verify your email" },
  ];
  return { done: parts.filter((x) => x.ok).length, total: parts.length, next: parts.find((x) => !x.ok)?.hint ?? null };
}

function Hero({ p, onPick, onRemove, busy }: { p: ProfileT; onPick: () => void; onRemove: () => void; busy: boolean }) {
  const c = completeness(p);
  return (
    <header className="grid items-end gap-8 pb-10 sm:grid-cols-[auto_1fr]">
      <div className="relative w-fit">
        <span aria-hidden className="absolute inset-0 translate-x-2.5 translate-y-2.5 rounded-[30%] bg-[var(--brand-accent)]" />
        <button
          type="button" onClick={onPick} disabled={busy} aria-label="Change profile picture"
          className="group relative block rounded-[30%]"
        >
          <UserAvatar name={p.name} email={p.email} version={p.avatar_v} className="size-32 sm:size-40" text="text-4xl sm:text-5xl" />
          <span className="absolute inset-0 grid place-items-center rounded-[30%] bg-black/55 text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            {busy ? <LoaderCircle className="animate-spin" /> : <span className="grid justify-items-center gap-1 text-xs font-medium"><Camera className="size-5" />{p.has_avatar ? "Change" : "Add photo"}</span>}
          </span>
        </button>
        {p.has_avatar && (
          <button type="button" onClick={onRemove} disabled={busy} className="mt-4 inline-flex items-center gap-1 rounded-[4px] text-xs text-muted-foreground hover:text-bad touch:min-h-11">
            <Trash2 className="size-3" aria-hidden />Remove photo
          </button>
        )}
      </div>

      <div className="min-w-0">
        <p className={MONO}>{p.role} · since {formatDate(p.member_since)}</p>
        <h1 className="mt-2 break-words font-heading text-4xl leading-[1.05] font-semibold tracking-tight sm:text-6xl">{p.name || "Your name"}</h1>
        <p className="mt-2 font-mono text-sm text-muted-foreground">
          {p.username ? `@${p.username}` : p.email}
          {p.job_title && <span className="font-sans"> · {p.job_title}</span>}
        </p>
        <div className="mt-6 max-w-md">
          <div className="flex items-baseline justify-between text-xs">
            <span className={MONO}>Profile {c.done}/{c.total}</span>
            <span className="text-muted-foreground">{c.next ?? "All set. Nicely done."}</span>
          </div>
          <div className="mt-2 flex gap-1" role="progressbar" aria-valuemin={0} aria-valuemax={c.total} aria-valuenow={c.done} aria-label="Profile completeness">
            {Array.from({ length: c.total }, (_, i) => <span key={i} className={cn("h-1.5 flex-1 rounded-full", i < c.done ? "bg-wait" : "bg-border")} />)}
          </div>
        </div>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------------------------
// 01 About you
// ---------------------------------------------------------------------------------------------
function Identity({ p, onSaved }: { p: ProfileT; onSaved: (p: ProfileT) => void }) {
  const [f, setF] = useState({ name: p.name, job_title: p.job_title, bio: p.bio, phone: p.phone, timezone: p.timezone });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setF({ name: p.name, job_title: p.job_title, bio: p.bio, phone: p.phone, timezone: p.timezone }), [p]);
  const zones = useMemo(() => timeZones(p.timezone), [p.timezone]);
  const dirty = (Object.keys(f) as (keyof typeof f)[]).some((k) => f[k] !== p[k]);
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onSaved(await updateProfile(f));
      toast.success("Profile saved");
    } catch (x) {
      setError(err(x));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="grid gap-9" noValidate>
      <div className="grid gap-9 sm:grid-cols-2">
        <label className="grid gap-1">
          <span className={MONO}>Full name</span>
          <Input value={f.name} onChange={(e) => set("name")(e.target.value)} maxLength={80} required autoComplete="name" className={LINE_INPUT} />
        </label>
        <label className="grid gap-1">
          <span className={MONO}>Job title</span>
          <Input value={f.job_title} onChange={(e) => set("job_title")(e.target.value)} maxLength={80} placeholder="e.g. Founder, content lead" autoComplete="organization-title" className={LINE_INPUT} />
        </label>
        <label className="grid gap-1">
          <span className={MONO}>Phone</span>
          <Input value={f.phone} onChange={(e) => set("phone")(e.target.value)} maxLength={32} inputMode="tel" placeholder="+91 98765 43210" autoComplete="tel" className={LINE_INPUT} />
        </label>
        <label className="grid gap-1">
          <span className={MONO}>Time zone</span>
          <select value={f.timezone} onChange={(e) => set("timezone")(e.target.value)} className={cn(LINE_INPUT, "w-full appearance-none outline-none")}>
            {zones.map((z) => <option key={z} value={z} className="bg-background text-base">{z.replace(/_/g, " ")}</option>)}
          </select>
        </label>
      </div>
      <label className="grid gap-1">
        <span className={cn(MONO, "flex justify-between")}>Short bio <span className="tabular-nums normal-case tracking-normal">{f.bio.length}/280</span></span>
        <textarea
          value={f.bio} onChange={(e) => set("bio")(e.target.value)} maxLength={280} rows={3}
          placeholder="A line or two about what you do and what you post."
          className="resize-none rounded-none border-0 border-b border-input bg-transparent py-2 text-lg leading-snug outline-none transition-colors placeholder:text-muted-foreground focus:border-[var(--brand-accent)]"
        />
      </label>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      {/* appears only when there is something to save and floats in reach while you scroll. It is fixed (out of the
          grid flow), so while hidden it takes no room: no dead gap under the form. Centred on the content column. */}
      <div className={cn(
        "fixed bottom-[calc(4.75rem+env(safe-area-inset-bottom))] left-1/2 z-30 flex w-max max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-3 rounded-full border border-rule bg-popover/95 py-2 pr-2 pl-5 text-sm shadow-[0_16px_40px_-12px_rgb(0_0_0/0.75)] backdrop-blur transition-[opacity,translate] duration-(--dur-base) ease-(--ease-out) md:bottom-6 md:left-[calc(50%+7.75rem)]",
        dirty ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-3 opacity-0",
      )} aria-hidden={!dirty}>
        <span className="text-muted-foreground">Unsaved changes</span>
        <Button type="button" variant="ghost" size="sm" onClick={() => setF({ name: p.name, job_title: p.job_title, bio: p.bio, phone: p.phone, timezone: p.timezone })} disabled={saving} tabIndex={dirty ? 0 : -1}>Discard</Button>
        <Button type="submit" size="sm" className="rounded-full" disabled={saving || !f.name.trim()} tabIndex={dirty ? 0 : -1}>
          {saving && <LoaderCircle className="animate-spin" />}Save
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------------------------
// 02 Sign-in & contact: a ledger (label | value | action), not cards
// ---------------------------------------------------------------------------------------------
function Row({ label, children, action }: { label: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="grid gap-x-6 gap-y-2 border-b py-5 sm:grid-cols-[9rem_1fr_auto] sm:items-start">
      <dt className={cn(MONO, "pt-1")}>{label}</dt>
      <dd className="min-w-0">{children}</dd>
      {action && <div className="sm:justify-self-end">{action}</div>}
    </div>
  );
}

/** Status tag: squared, 4px, like StatusBadge (fully round pills are reserved for the save bar, dots and meters). */
function Pill({ tone, children }: { tone: "ok" | "warn" | "idle"; children: ReactNode }) {
  const t = { ok: "text-ok border-ok/40 bg-ok-solid/10", warn: "text-wait border-wait/40 bg-wait/10", idle: "text-muted-foreground border-border" }[tone];
  return <span className={cn("ml-2 inline-flex h-5 items-center gap-1 rounded-[4px] border px-1.5 align-middle font-sans text-[11px] font-medium normal-case tracking-normal", t)}>{children}</span>;
}

function UsernameRow({ p, onSaved }: { p: ProfileT; onSaved: (p: ProfileT) => void }) {
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState(p.username ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try { onSaved(await updateProfile({ username: v })); setEditing(false); toast.success("Username updated"); }
    catch (x) { setError(err(x)); } finally { setBusy(false); }
  }
  return (
    <Row label="Username" action={!editing && <Button variant="ghost" size="sm" onClick={() => { setV(p.username ?? ""); setEditing(true); }}><Pencil />{p.username ? "Change" : "Add"}</Button>}>
      {editing ? (
        <form onSubmit={save} className="flex flex-wrap items-start gap-2">
          <div className="grid gap-1">
            <Input value={v} onChange={(e) => setV(e.target.value.toLowerCase())} autoFocus maxLength={32} autoCapitalize="none" spellCheck={false} className="h-10 w-56 font-mono" aria-label="Username" />
            {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          </div>
          <Button type="submit" size="sm" className="h-10" disabled={busy || !v.trim()}>{busy && <LoaderCircle className="animate-spin" />}Save</Button>
          <Button type="button" variant="ghost" size="sm" className="h-10" onClick={() => setEditing(false)}>Cancel</Button>
        </form>
      ) : p.username ? <span className="font-mono">@{p.username}</span>
        : <span className="text-muted-foreground">Not set. You can sign in with your email instead.</span>}
    </Row>
  );
}

/** Changing the address is confirmed with a code sent to the NEW address. */
function EmailRow({ p, onSaved }: { p: ProfileT; onSaved: (p: ProfileT) => void }) {
  const [stage, setStage] = useState<"view" | "enter" | "code">("view");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cancel = () => { setStage("view"); setError(null); setCode(""); };
  async function send(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true); setError(null);
    try { await sendEmailCode(email.trim()); setCode(""); setStage("code"); toast.success(`Code sent to ${email.trim().toLowerCase()}`); }
    catch (x) { setError(err(x)); } finally { setBusy(false); }
  }
  async function verify(v = code) {
    if (v.length !== 6 || busy) return;
    setBusy(true); setError(null);
    try { onSaved(await changeEmail(email.trim(), v)); toast.success("Email confirmed"); cancel(); }
    catch (x) { setError(err(x)); setCode(""); } finally { setBusy(false); }
  }

  return (
    <Row label="Email" action={stage === "view" && <Button variant="ghost" size="sm" onClick={() => { setEmail(p.email ?? ""); setStage("enter"); }}><Mail />{p.email ? "Change" : "Add email"}</Button>}>
      {stage === "view" && (p.email ? (
        <div className="break-all">{p.email}{p.email_verified ? <Pill tone="ok"><Check className="size-3" />Verified</Pill> : <Pill tone="warn">Not verified</Pill>}
          {!p.email_verified && <p className="mt-1 text-sm text-muted-foreground">Confirm it with a code so password resets can reach you. Use “Change” and enter this address again.</p>}
        </div>
      ) : <span className="text-muted-foreground">No email yet. Add one to receive password codes.</span>)}

      {stage === "enter" && (
        <form onSubmit={send} className="flex flex-wrap items-start gap-2">
          <div className="grid gap-1">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus autoComplete="email" className="h-10 w-72 max-w-full" aria-label="New email address" />
            {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          </div>
          <Button type="submit" size="sm" className="h-10" disabled={busy || !email.includes("@")}>{busy && <LoaderCircle className="animate-spin" />}Send code</Button>
          <Button type="button" variant="ghost" size="sm" className="h-10" onClick={cancel}>Cancel</Button>
        </form>
      )}

      {stage === "code" && (
        <div className="grid max-w-sm gap-4">
          <p className="text-sm text-muted-foreground">We sent a 6-digit code to <span className="text-foreground">{email.trim().toLowerCase()}</span>.</p>
          <OtpInput value={code} onChange={(v) => { setCode(v); setError(null); }} onComplete={verify} invalid={!!error} disabled={busy} />
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => verify()} disabled={busy || code.length !== 6}>{busy && <LoaderCircle className="animate-spin" />}Confirm</Button>
            <Button size="sm" variant="ghost" onClick={() => send()} disabled={busy}>Resend</Button>
            <Button size="sm" variant="ghost" onClick={cancel}>Cancel</Button>
          </div>
        </div>
      )}
    </Row>
  );
}

function SignIn({ p, onSaved }: { p: ProfileT; onSaved: (p: ProfileT) => void }) {
  return (
    <dl className="border-t">
      <UsernameRow p={p} onSaved={onSaved} />
      <EmailRow p={p} onSaved={onSaved} />
      <Row label="Ways to sign in" action={<Button variant="ghost" size="sm" asChild><a href="#security"><KeyRound />{p.has_password ? "Manage" : "Set a password"}</a></Button>}>
        <ul className="grid gap-2">
          <li>Password
            {p.has_password ? <Pill tone="ok"><Check className="size-3" />On</Pill> : <Pill tone="warn">Not set</Pill>}
            <span className="ml-2 text-sm text-muted-foreground">{p.has_password ? (p.password_changed_at ? `changed ${ago(p.password_changed_at)}` : "") : "you currently sign in with Google"}</span>
          </li>
          <li>Google
            {p.google_allowed ? <Pill tone="ok"><Check className="size-3" />Available</Pill> : <Pill tone="idle">Not enabled for this email</Pill>}
          </li>
        </ul>
      </Row>
    </dl>
  );
}

// ---------------------------------------------------------------------------------------------
// 03 Security
// ---------------------------------------------------------------------------------------------
/** No password yet (Google sign-in): a three-step rail — code to your inbox, enter it, choose a password. */
function FirstPassword({ p, onDone }: { p: ProfileT; onDone: (r: Awaited<ReturnType<typeof savePassword>>) => void }) {
  const [step, setStep] = useState(0);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);

  async function send() {
    setBusy(true); setError(null);
    try { const r = await sendPasswordCode(); setLeft(r.cooldown ?? 60); setCode(""); setStep(1); toast.success(`Code sent to ${p.email}`); }
    catch (x) { setError(err(x)); if (x instanceof ApiError && x.retryAfter) setLeft(x.retryAfter); } finally { setBusy(false); }
  }
  async function finish(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { onDone(await savePassword({ new_password: pw, code })); }
    catch (x) { setError(err(x)); if (x instanceof ApiError && x.status === 400) { setStep(1); setCode(""); } } finally { setBusy(false); }
  }

  const steps = ["Send a code", "Enter the code", "Choose a password"];
  return (
    <div className="grid gap-8 lg:grid-cols-[14rem_1fr]">
      <div>
        <p className="border-l-2 border-[var(--brand-accent)] pl-3 text-sm leading-relaxed">
          You sign in with Google, so this account has <strong className="font-semibold">no password</strong>. Add one and you can also sign in with your email.
        </p>
        <ol className="relative mt-8 grid gap-6 pl-8 before:absolute before:top-2 before:bottom-2 before:left-[11px] before:w-px before:bg-border">
          {steps.map((s, i) => (
            <li key={s} className={cn("relative text-sm", i > step ? "text-muted-foreground" : i === step ? "font-medium" : "text-muted-foreground")}>
              <span className={cn("absolute top-0 -left-8 grid size-6 place-items-center rounded-full border bg-background font-mono text-[11px]", i < step && "border-ok-solid bg-ok-solid text-background", i === step && "border-signal text-signal")}>
                {i < step ? <><Check className="size-3.5" aria-hidden /><span className="sr-only">(done)</span></> : i + 1}
              </span>
              {s}
            </li>
          ))}
        </ol>
      </div>

      <div className="max-w-md">
        {!p.email ? (
          <p className="text-sm text-muted-foreground">Add an email address in <a href="#signin" className="text-primary underline-offset-4 hover:underline">Sign-in &amp; contact</a> first. That's where the code is sent.</p>
        ) : step === 0 ? (
          <div className="grid gap-4">
            <p className="text-sm text-muted-foreground">We'll email a 6-digit code to <span className="text-foreground">{p.email}</span> to prove it's you.</p>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <Button className="w-fit" onClick={send} disabled={busy}>{busy ? <LoaderCircle className="animate-spin" /> : <Mail />}Email me a code</Button>
          </div>
        ) : step === 1 ? (
          <div className="grid gap-5">
            <p className="text-sm text-muted-foreground">Enter the code we sent to <span className="text-foreground">{p.email}</span>.</p>
            <OtpInput value={code} onChange={(v) => { setCode(v); setError(null); }} onComplete={() => setStep(2)} invalid={!!error} />
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <Button size="sm" onClick={() => setStep(2)} disabled={code.length !== 6}>Continue</Button>
              {left > 0 ? <span className="tabular-nums text-muted-foreground">Resend in 0:{String(left).padStart(2, "0")}</span>
                : <button type="button" className="text-primary underline-offset-4 hover:underline" onClick={send} disabled={busy}>Send a new code</button>}
            </div>
          </div>
        ) : (
          <form onSubmit={finish} className="grid gap-5" noValidate>
            <PasswordField label="New password" value={pw} onChange={setPw} meter identity={[p.username, p.email, p.name]} autoFocus disabled={busy} />
            <PasswordField label="Type it again" value={pw2} onChange={setPw2} disabled={busy} error={pw2 && pw !== pw2 ? "These don't match yet." : null} />
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || !passwordAcceptable(pw, p.username, p.email, p.name) || pw !== pw2}>{busy && <LoaderCircle className="animate-spin" />}Set password</Button>
              <Button type="button" variant="ghost" onClick={() => setStep(1)}>Back</Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function ChangePassword({ p, onDone }: { p: ProfileT; onDone: (r: Awaited<ReturnType<typeof savePassword>>) => void }) {
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { onDone(await savePassword({ new_password: pw, current_password: cur })); setCur(""); setPw(""); setPw2(""); }
    catch (x) { setError(err(x)); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className="grid max-w-md gap-5" noValidate>
      <PasswordField label="Current password" value={cur} onChange={setCur} autoComplete="current-password" disabled={busy} />
      <PasswordField label="New password" value={pw} onChange={setPw} meter identity={[p.username, p.email, p.name]} disabled={busy} />
      <PasswordField label="Type it again" value={pw2} onChange={setPw2} disabled={busy} error={pw2 && pw !== pw2 ? "These don't match yet." : null} />
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy || !cur || !passwordAcceptable(pw, p.username, p.email, p.name) || pw !== pw2}>{busy && <LoaderCircle className="animate-spin" />}Update password</Button>
        <span className="text-xs text-muted-foreground">Other devices will be signed out. Forgot the current one? Sign out, then use “Forgot password?”.</span>
      </div>
    </form>
  );
}

function OtherDevices({ onDone }: { onDone: (csrf: string) => void }) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!armed) return; const t = setTimeout(() => setArmed(false), 4000); return () => clearTimeout(t); }, [armed]);
  async function go() {
    if (!armed) return setArmed(true);
    setBusy(true);
    try { const r = await revokeOtherSessions(); onDone(r.csrf); toast.success("Signed out everywhere else"); }
    catch (x) { toast.error(err(x)); } finally { setBusy(false); setArmed(false); }
  }
  return (
    <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t pt-6">
      <div>
        <p className="font-medium">Signed in somewhere you don't recognise?</p>
        <p className="text-sm text-muted-foreground">Sign out every other device. You'll stay signed in here.</p>
      </div>
      <Button variant={armed ? "destructive" : "outline"} onClick={go} disabled={busy}>
        {busy ? <LoaderCircle className="animate-spin" /> : <LogOut />}{armed ? "Tap again to confirm" : "Sign out other devices"}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// 04 Account record: a receipt, in mono
// ---------------------------------------------------------------------------------------------
function Record({ p }: { p: ProfileT }) {
  const rows: [string, string][] = [
    ["Account", `#${String(p.id).padStart(4, "0")}`],
    ["Role", p.role],
    ["Member since", formatDate(p.member_since)],
    ["Last sign-in", p.last_login_at ? `${formatDate(p.last_login_at)} · ${ago(p.last_login_at)}` : "this is your first one"],
    ["Password changed", p.password_changed_at ? ago(p.password_changed_at) : p.has_password ? "set by the admin setup" : "no password"],
    ["Time zone", p.timezone.replace(/_/g, " ")],
  ];
  return (
    <dl className="max-w-xl rounded-lg border border-dashed bg-[color-mix(in_srgb,var(--brand-text)_2%,transparent)] p-5 font-mono text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline gap-3 py-1.5">
          <dt className="text-muted-foreground">{k}</dt>
          <span aria-hidden className="flex-1 translate-y-[-3px] border-b border-dotted border-foreground/20" />
          <dd className="text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------------------------------------
export default function ProfilePage() {
  const { patchUser, setCsrf } = useAuth();
  const [p, setP] = useState<ProfileT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [crop, setCrop] = useState<File | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [active, setActive] = useState<string>("identity");
  const picker = useRef<HTMLInputElement>(null);

  const accept = useCallback((next: ProfileT) => {
    setP(next);
    patchUser({ name: next.name || next.username || next.email || "", username: next.username, email: next.email, avatar_v: next.avatar_v, has_password: next.has_password });
  }, [patchUser]);

  useEffect(() => { getProfile().then(setP).catch((x) => setError(err(x, "Couldn't load your profile."))); }, []);

  // highlight the section being read in the side index
  useEffect(() => {
    if (!p) return;
    const io = new IntersectionObserver(
      (entries) => { const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]; if (vis) setActive(vis.target.id); },
      { rootMargin: "-15% 0px -70% 0px" },
    );
    SECTIONS.forEach((s) => { const el = document.getElementById(s.id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, [p]);

  async function savePhoto(blob: Blob) {
    setPhotoBusy(true);
    try { accept(await uploadAvatar(blob)); setCrop(null); toast.success("Picture updated"); }
    finally { setPhotoBusy(false); }
  }
  async function removePhoto() {
    setPhotoBusy(true);
    try { accept(await deleteAvatar()); toast.success("Picture removed"); } catch (x) { toast.error(err(x)); } finally { setPhotoBusy(false); }
  }
  function onPassword(r: Awaited<ReturnType<typeof savePassword>>) {
    setCsrf(r.csrf);
    accept(r.profile);
    toast.success(r.profile.has_password ? "Password saved. Other devices were signed out." : "Password saved");
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-5 py-8 md:px-10 md:py-12">
        {error && <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">{error}</p>}
        {!p && !error && (
          <div className="grid gap-6" role="status" aria-label="Loading your profile">
            <div className="flex gap-6"><Skeleton className="size-36 rounded-[30%]" /><div className="grid flex-1 content-end gap-3"><Skeleton className="h-4 w-40" /><Skeleton className="h-12 w-3/4" /></div></div>
            <Skeleton className="h-64 w-full" />
          </div>
        )}

        {p && (
          <>
            <Hero p={p} onPick={() => picker.current?.click()} onRemove={removePhoto} busy={photoBusy} />
            <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" tabIndex={-1} aria-hidden
                   onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; if (!/^image\/(jpeg|png|webp)$/.test(f.type)) toast.error("Use a JPEG, PNG or WebP picture."); else setCrop(f); }} />

            <div className="grid gap-12 lg:grid-cols-[11rem_1fr]">
              <nav aria-label="Profile sections" className="sticky top-8 hidden h-fit lg:block">
                <ul className="grid gap-1 border-l">
                  {SECTIONS.map((s) => (
                    <li key={s.id}>
                      <a href={`#${s.id}`} aria-current={active === s.id ? "true" : undefined}
                         className={cn("-ml-px flex items-baseline gap-3 border-l-2 py-1.5 pl-4 text-sm transition-colors", active === s.id ? "border-[var(--brand-accent)] text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                        <span className="font-mono text-[11px] tabular-nums">{s.n}</span>{s.label}
                      </a>
                    </li>
                  ))}
                </ul>
                <p className="mt-8 flex items-start gap-2 text-xs leading-relaxed text-muted-foreground"><ShieldCheck className="mt-0.5 size-3.5 shrink-0" />Hi {firstName(p.name)}. Changes to your password or email always ask for proof first.</p>
              </nav>

              <div className="grid min-w-0 gap-14">
                <Section id="identity" n="01" title="About you" lead="What shows next to your name around the dashboard.">
                  <Identity p={p} onSaved={accept} />
                </Section>
                <Section id="signin" n="02" title="Sign-in & contact" lead="How you get in, and where we reach you.">
                  <SignIn p={p} onSaved={accept} />
                </Section>
                <Section id="security" n="03" title="Security" lead={p.has_password ? "Keep your password fresh and your sessions tidy." : "Add a password so Google isn't the only way in."}>
                  {p.has_password ? <ChangePassword p={p} onDone={onPassword} /> : <FirstPassword p={p} onDone={onPassword} />}
                  <OtherDevices onDone={(csrf) => setCsrf(csrf)} />
                </Section>
                <Section id="record" n="04" title="Account record" lead="The facts on file. Read-only.">
                  <Record p={p} />
                </Section>
              </div>
            </div>
          </>
        )}
      </div>
      <AvatarCropper file={crop} onCancel={() => setCrop(null)} onSave={savePhoto} />
    </AppShell>
  );
}
