import { useCallback, useEffect, useMemo, useState, type ClipboardEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { BookOpen, Check, CircleDashed, Eye, EyeOff, LoaderCircle, Radar, RefreshCw, Send, ShieldCheck, Trash2, TriangleAlert, X } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { CheckList, GuideSheet, ResultNote, StateDot, StateTag } from "@/components/config/parts";
import { PageHeader } from "@/components/page-header";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import {
  deleteWebhook, detectChat, getOverview, save, verify, type DetectedChat, type FieldState, type Integration,
  type Overview, type Readiness, type State, type VerifyResult,
} from "@/lib/config";
import { ago, checkField, cleanValue } from "@/lib/config-format";
import { cn } from "@/lib/utils";
function safeFix(fix: string | null | undefined): string | undefined {
  if (!fix) return undefined;
  return fix.startsWith("/") ? fix : undefined;
}

const MONO = "label-mono";
const errText = (e: unknown, fallback = "Something went wrong. Please try again.") => (e instanceof ApiError ? e.message : fallback);
const STEP_NO: Record<string, string> = { database: "00", gemini: "01", telegram: "02", cloudinary: "03", github: "04" };

// ---------------------------------------------------------------------------------------------
// Readiness: the verdict first, then exactly what's missing
// ---------------------------------------------------------------------------------------------
function ReadinessBanner({ r, steps }: { r: Readiness; steps: Integration[] }) {
  const done = steps.filter((s) => s.state === "valid" || s.state === "warning").length;
  return (
    <section aria-labelledby="ready-h" className="grid gap-6 border-b border-rule pb-8">
      <div className="grid items-end gap-6 md:grid-cols-[minmax(0,1fr)_auto]">
        <div>
          <p className="label-mono">Readiness</p>
          <h2 id="ready-h" className="mt-1 font-heading text-3xl leading-tight font-semibold tracking-tight sm:text-4xl">
            Ready to generate:{" "}
            <span className={r.ready_to_generate ? "text-ok" : "text-wait"}>{r.ready_to_generate ? "yes" : "not yet"}</span>
          </h2>
          <p className="mt-2 max-w-prose text-sm text-muted-foreground">
            {r.ready_to_generate
              ? "Every required service is set and verified with the values in use now. A first generation won't fail because of configuration."
              : r.missing.length === 1 ? "One thing is missing. Fix it below and you can start." : `${r.missing.length} things are missing. Work through them below, in order.`}
          </p>
        </div>
        <div className="min-w-[12rem]">
          <div className="flex items-baseline justify-between text-xs"><span className={MONO}>Setup {done}/{steps.length}</span><span className="numeral text-muted-foreground">v{r.config_version}</span></div>
          <div className="mt-2 flex gap-1" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done} aria-label="Setup steps verified">
            {steps.map((s) => <span key={s.name} className={cn("h-1.5 flex-1 rounded-full", s.state === "valid" || s.state === "warning" ? "bg-ok-solid" : s.state === "invalid" ? "bg-bad" : "bg-border")} />)}
          </div>
        </div>
      </div>

      {r.missing.length > 0 && (
        <ol className="grid border-t border-rule">
          {r.missing.map((m) => (
            <li key={m.id} className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-rule py-3 sm:grid-cols-[2.5rem_minmax(0,14rem)_minmax(0,1fr)_auto] sm:items-baseline">
              <span className="numeral text-xs text-signal">{m.id}</span>
              <span className="font-medium">{m.label}</span>
              <span className="col-start-2 text-sm text-muted-foreground sm:col-start-3">{m.detail}</span>
              {safeFix(m.fix) && <Link to={safeFix(m.fix)!} className="col-start-2 text-sm text-primary underline-offset-4 hover:underline sm:col-start-4">Fix<span className="sr-only"> {m.label}</span> →</Link>}
            </li>
          ))}
        </ol>
      )}

      <details className="group text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">All conditions, and what “ready” doesn't cover</summary>
        <div className="mt-4 grid gap-8 md:grid-cols-2">
          <ul className="grid gap-2">
            {r.conditions.map((c) => (
              <li key={c.id} className="flex items-start gap-2">
                {c.ok === true ? <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-ok" /> : c.ok === false ? <X aria-hidden className="mt-0.5 size-4 shrink-0 text-bad" /> : <CircleDashed aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
                <span><span className="sr-only">{c.ok === true ? "Met" : c.ok === false ? "Not met" : "Not available"}: </span>
                  <span className="numeral mr-2 text-xs text-muted-foreground">{c.id}</span>{c.label}
                  {!c.blocking && <span className="ml-2 text-xs text-muted-foreground">(not required yet)</span>}
                  {c.ok !== true && <span className="block text-xs text-muted-foreground">{c.detail}</span>}
                </span>
              </li>
            ))}
          </ul>
          <div>
            <p className="label-mono mb-2">Can still happen, not a setup problem</p>
            <ul className="grid gap-1 text-muted-foreground">{r.not_covered.map((x) => <li key={x}>· {x}</li>)}</ul>
          </div>
        </div>
      </details>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
// One field: write-only for secrets, paste cleaner, instant format feedback, where the value comes from
// ---------------------------------------------------------------------------------------------
function SourceNote({ f }: { f: FieldState }) {
  if (!f.is_set) return <span>Not set</span>;
  const who = f.updated_by ? ` by ${f.updated_by}` : "";
  return (
    <span className="grid gap-1">
      {f.source === "env"
        ? <span>From the server environment{f.in_store ? "; it wins over the value saved here" : ""}.</span>
        : <span>Saved here {f.updated_at ? ago(f.updated_at) : ""}{who}.</span>}
      {f.conflict && (
        <span className="flex items-start gap-1.5 text-wait"><TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          The environment and this page hold different values. The environment's is used; remove one so they can't drift.
        </span>
      )}
      {f.undecryptable && <span className="text-bad">Saved, but this server's master key can't read it. Enter it again.</span>}
    </span>
  );
}

function FieldRow({ f, value, onChange, notes, onNotes, disabled }: {
  f: FieldState; value: string | undefined; onChange: (v: string | undefined) => void; notes?: string[];
  onNotes: (n: string[] | undefined) => void; disabled: boolean;
}) {
  const [show, setShow] = useState(false);
  const replacing = value !== undefined;
  const editing = !f.secret || !f.is_set || replacing;
  const current = value ?? (f.secret ? "" : f.value ?? "");
  const hint = editing ? checkField(f.name, cleanValue(current, f.name).value) : null;
  const id = `field-${f.name}`;
  const hintId = `${id}-hint`;

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    const raw = e.clipboardData.getData("text");
    const { value: v, notes: n } = cleanValue(raw, f.name);
    if (n.length) {
      e.preventDefault();
      onChange(v);
      onNotes(n);
    }
  }

  return (
    <div className="grid gap-x-6 gap-y-2 border-b border-rule py-4 sm:grid-cols-[11rem_minmax(0,1fr)]">
      <label htmlFor={id} className="pt-2">
        <span className={MONO}>{f.label}</span>
        {!f.required && <span className="ml-1.5 text-[11px] text-muted-foreground">optional</span>}
      </label>
      <div className="grid min-w-0 gap-1.5">
        {editing ? (
          <div className="flex min-w-0 gap-2">
            <div className="relative min-w-0 flex-1">
              <Input
                id={id} value={current} disabled={disabled}
                type={f.secret && !show ? "password" : "text"}
                onChange={(e) => { onChange(e.target.value); onNotes(undefined); }} onPaste={onPaste}
                placeholder={f.shape} autoComplete="off" spellCheck={false} autoCapitalize="none"
                aria-describedby={hintId} aria-invalid={hint?.level === "error" || undefined}
                className={cn("h-10 font-mono text-sm", f.secret && "pr-10")}
                data-1p-ignore data-lpignore="true"
              />
              {f.secret && (
                <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? `Hide ${f.label}` : `Show ${f.label}`}
                        className="focus-ring absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground">
                  {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              )}
            </div>
            {f.secret && f.is_set && replacing && (
              <Button type="button" variant="ghost" size="sm" className="h-10" onClick={() => { onChange(undefined); onNotes(undefined); }}>Cancel</Button>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="inline-flex items-center gap-1.5 font-mono text-sm"><ShieldCheck aria-hidden className="size-4 text-ok" />Saved{f.fingerprint && <span className="text-muted-foreground" title="A keyed fingerprint: shows whether the value changed, reveals nothing about it">· {f.fingerprint}</span>}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => onChange("")} disabled={disabled}>Replace</Button>
          </div>
        )}
        <div id={hintId} className="grid gap-1 text-xs text-muted-foreground" aria-live="polite">
          {notes && notes.length > 0 && <span className="text-go">Cleaned your paste: {notes.join(", ")}.</span>}
          {hint && hint.level !== "ok" && <span className={hint.level === "error" ? "text-bad" : "text-wait"}>{hint.text}</span>}
          {hint && hint.level === "ok" && current && <span className="text-ok">{hint.text}</span>}
          {!hint && editing && f.help && <span>{f.help}</span>}
          <SourceNote f={f} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// A setup step (one integration)
// ---------------------------------------------------------------------------------------------
type Confirm = { title: string; body: ReactNode; action: string; run: () => void } | null;

function Step({ integ, onChanged, onGuide, setConfirm }: {
  integ: Integration; onChanged: (i: Integration, r?: Readiness) => void; onGuide: (id: string) => void; setConfirm: (c: Confirm) => void;
}) {
  const [edits, setEdits] = useState<Record<string, string | undefined>>({});
  const [notes, setNotes] = useState<Record<string, string[] | undefined>>({});
  const [busy, setBusy] = useState<null | "save" | "verify" | "deep" | "detect">(null);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chats, setChats] = useState<DetectedChat[] | null>(null);
  const [unknownSave, setUnknownSave] = useState(false);

  const changed = useMemo(() => {
    const out: Record<string, string> = {};
    for (const f of integ.fields) {
      const v = edits[f.name];
      if (v === undefined) continue;
      const clean = cleanValue(v, f.name).value;
      if (f.secret ? clean !== "" : clean !== (f.value ?? "")) out[f.name] = clean;
    }
    return out;
  }, [edits, integ.fields]);
  const formatError = Object.entries(changed).some(([k, v]) => checkField(k, v)?.level === "error");
  const shown = result ?? integ.check ?? null;
  const state: State = busy === "save" || busy === "verify" || busy === "deep" ? "checking" : integ.state;
  const visible = integ.fields.filter((f) => !f.advanced);
  const advanced = integ.fields.filter((f) => f.advanced);
  const bot = typeof shown?.evidence?.bot === "string" ? (shown.evidence.bot as string) : null;

  function applySaved(i: Integration, r?: Readiness) {
    setEdits({}); setNotes({}); setChats(null); setUnknownSave(false);
    onChanged(i, r);
  }

  async function doSave(unverified = false) {
    setBusy("save"); setError(null); setUnknownSave(false);
    const expected = Object.fromEntries(Object.keys(changed).map((k) => [k, integ.fields.find((f) => f.name === k)?.version ?? 0]));
    try {
      const r = await save(integ.name, changed, expected, unverified);
      setResult(r.result);
      applySaved(r.integration, r.readiness);
      toast.success(`${integ.title} saved${r.result.status === "warning" ? " (with a warning)" : unverified ? " unverified" : " and verified"}`);
    } catch (x) {
      if (x instanceof ApiError && x.data?.result) setResult(x.data.result as VerifyResult);
      if (x instanceof ApiError && x.code === "verify_unknown") setUnknownSave(true);
      if (x instanceof ApiError && x.code === "conflict") toast.error("Someone changed this while you were editing. Reloaded the latest.");
      setError(x instanceof ApiError && x.code === "verify_failed" ? "Nothing was saved: the check failed. Your previous value still works." : errText(x));
      if (x instanceof ApiError && x.code === "conflict") onChanged(integ);
    } finally { setBusy(null); }
  }

  async function doVerify(deep = false) {
    setBusy(deep ? "deep" : "verify"); setError(null);
    try {
      const r = await verify(integ.name, changed, deep ? "deep" : "live", deep);
      setResult(r.result);
      if (!Object.keys(changed).length) onChanged(integ);  // stored values were re-checked: refresh state
    } catch (x) { setError(errText(x)); } finally { setBusy(null); }
  }

  async function doDetect() {
    setBusy("detect"); setError(null); setChats(null);
    try {
      const token = changed.TG_BOT_TOKEN;
      const r = await detectChat(token);
      if (r.code) setError(`${r.message} ${r.hint ?? ""}`);
      else setChats(r.chats);
    } catch (x) { setError(errText(x)); } finally { setBusy(null); }
  }

  const webhookBlocked = shown?.code === "telegram.webhook_set";
  const canSave = Object.keys(changed).length > 0 && !formatError && !busy && integ.editable;

  return (
    <section id={integ.name} aria-labelledby={`${integ.name}-h`} className="scroll-mt-24 border-t border-rule pt-8 first:border-t-0 first:pt-0">
      <header className="mb-6 grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-4 gap-y-2 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:gap-x-5">
        <span aria-hidden className="select-none font-heading text-4xl leading-none font-bold text-transparent [-webkit-text-stroke:1px_color-mix(in_srgb,var(--brand-text)_30%,transparent)] sm:text-6xl">{STEP_NO[integ.name]}</span>
        <div className="min-w-0 pt-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h2 id={`${integ.name}-h`} className="font-heading text-2xl font-semibold tracking-tight">{integ.title}</h2>
            <StateTag state={state} />
            {integ.minutes > 0 && <span className="font-mono text-[11px] text-muted-foreground">~{integ.minutes} min</span>}
          </div>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">{integ.blurb}</p>
        </div>
        <Button variant="ghost" size="sm" className="col-start-2 -ml-2.5 w-fit sm:col-start-3 sm:ml-0" onClick={() => onGuide(integ.name)}><BookOpen />Where do I get this?</Button>
      </header>

      {integ.name === "gemini" && (
        <p className="mb-4 max-w-prose border-l-2 border-wait/60 pl-3 text-xs leading-relaxed text-muted-foreground">
          Data use: Google states that on the Gemini Paid Tier your prompts and responses are not used to improve its products.
          Read the <a className="text-primary underline-offset-4 hover:underline" href="https://ai.google.dev/gemini-api/terms" target="_blank" rel="noopener noreferrer">Gemini API terms</a> for
          what applies to a Free Tier key before you use it for customers.
        </p>
      )}

      {integ.fields.length > 0 && (
        <div className="border-t border-rule">
          {visible.map((f) => (
            <FieldRow key={f.name} f={f} value={edits[f.name]} disabled={!!busy || !integ.editable}
                      onChange={(v) => setEdits((e) => ({ ...e, [f.name]: v }))} notes={notes[f.name]}
                      onNotes={(n) => setNotes((x) => ({ ...x, [f.name]: n }))} />
          ))}
          {advanced.length > 0 && (
            <details className="border-b border-rule py-3">
              <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">Advanced: model choice</summary>
              {advanced.map((f) => (
                <FieldRow key={f.name} f={f} value={edits[f.name]} disabled={!!busy}
                          onChange={(v) => setEdits((e) => ({ ...e, [f.name]: v }))} notes={notes[f.name]}
                          onNotes={(n) => setNotes((x) => ({ ...x, [f.name]: n }))} />
              ))}
            </details>
          )}
        </div>
      )}

      {integ.name === "telegram" && (
        <div className="mt-4 grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {bot && <Button variant="outline" size="sm" asChild><a href={`https://t.me/${bot.replace(/^@/, "")}?start=setup`} target="_blank" rel="noopener noreferrer"><Send />Open {bot} in Telegram</a></Button>}
            <Button variant="outline" size="sm" onClick={doDetect} disabled={!!busy || (!changed.TG_BOT_TOKEN && !integ.fields.find((f) => f.name === "TG_BOT_TOKEN")?.is_set)}>
              {busy === "detect" ? <LoaderCircle className="animate-spin" /> : <Radar />}Detect my chat
            </Button>
            <span className="text-xs text-muted-foreground">Press Start on your bot first. Detecting never consumes approval button presses.</span>
          </div>
          {chats && (
            <fieldset className="grid gap-1 rounded-md border border-rule p-3">
              <legend className="label-mono px-1">Chats that messaged your bot</legend>
              {chats.map((c) => (
                <label key={c.id} className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-0.5 rounded px-2 py-1.5 hover:bg-raised">
                  <input type="radio" name="tg-chat" className="accent-[var(--brand-primary)]"
                         checked={(edits.TG_CHAT_ID ?? integ.fields.find((f) => f.name === "TG_CHAT_ID")?.value ?? "") === c.id}
                         onChange={() => setEdits((e) => ({ ...e, TG_CHAT_ID: c.id }))} />
                  <span className="min-w-0 flex-1 break-words">{c.title ?? "Untitled chat"}</span>
                  <span className="basis-full pl-7 font-mono text-xs text-muted-foreground sm:basis-auto sm:pl-0">{c.type} · {c.id}</span>
                </label>
              ))}
            </fieldset>
          )}
        </div>
      )}

      {integ.editable || integ.name === "database" ? (
        <div className="mt-5 flex flex-wrap items-center gap-2">
          {integ.editable && (
            <Button onClick={() => doSave()} disabled={!canSave}>
              {busy === "save" ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}Verify &amp; save
            </Button>
          )}
          <Button variant="outline" onClick={() => doVerify()} disabled={!!busy || (!integ.required_set && !Object.keys(changed).length && integ.name !== "database")}>
            {busy === "verify" ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}{Object.keys(changed).length ? "Check without saving" : "Verify again"}
          </Button>
          {integ.name === "gemini" && (
            <Button variant="ghost" disabled={!!busy || !integ.required_set} onClick={() => setConfirm({
              title: "Run a real Gemini request?", action: "Run it",
              body: "This sends one tiny structured request to Gemini. It uses 1 request of today's quota and confirms the model can produce the JSON the pipeline needs.",
              run: () => doVerify(true),
            })}>{busy === "deep" && <LoaderCircle className="animate-spin" />}Run a real test</Button>
          )}
          {integ.name === "telegram" && (
            <Button variant="ghost" disabled={!!busy || !integ.required_set} onClick={() => setConfirm({
              title: "Send a test message?", action: "Send it",
              body: "Your bot will post one plain message (no buttons) in the approval chat. Nothing is published anywhere.",
              run: () => doVerify(true),
            })}>{busy === "deep" ? <LoaderCircle className="animate-spin" /> : <Send />}Send test message</Button>
          )}
          {unknownSave && (
            <Button variant="outline" onClick={() => setConfirm({
              title: "Save without verifying?", action: "Save unverified",
              body: "The service didn't answer, so we couldn't check this value. It will be saved and marked Unknown until a check succeeds.",
              run: () => doSave(true),
            })}>Save unverified</Button>
          )}
          {shown && <span className="ml-auto text-xs text-muted-foreground">{"ran_at" in shown ? `Last verified ${ago((shown as { ran_at: string }).ran_at)}` : `Checked ${ago(shown.checked_at)}`}{shown.latency_ms ? ` · ${shown.latency_ms} ms` : ""}</span>}
        </div>
      ) : null}

      <div aria-live="polite" className="mt-4 grid gap-4">
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        {shown && (shown.code || shown.status !== "valid") && <ResultNote code={shown.code} message={shown.message} hint={shown.hint} />}
        {webhookBlocked && (
          <Button variant="destructive" size="sm" className="w-fit" onClick={() => setConfirm({
            title: "Remove the webhook from this bot?", action: "Remove webhook",
            body: "Telegram sends updates either to a webhook or to polling, never both. Removing it lets this app read approvals. If another app relies on that webhook, it will stop receiving updates.",
            run: async () => { try { await deleteWebhook(changed.TG_BOT_TOKEN); toast.success("Webhook removed. Verifying again…"); doVerify(); } catch (x) { toast.error(errText(x)); } },
          })}><Trash2 />Remove webhook</Button>
        )}
        {shown && shown.checks?.length > 0 && <CheckList checks={shown.checks} />}
        {!shown && integ.last_check && integ.state === "stale" && (
          <p className="text-sm text-wait">A value changed since the last check ({ago(integ.last_check.ran_at)}). Verify again so readiness counts it.</p>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
function Later({ items }: { items: Integration[] }) {
  return (
    <section id="later" aria-labelledby="later-h" className="scroll-mt-24 border-t border-rule pt-8">
      <header className="mb-4 flex items-start gap-5">
        <span aria-hidden className="select-none font-heading text-5xl leading-none font-bold text-transparent [-webkit-text-stroke:1px_color-mix(in_srgb,var(--brand-text)_30%,transparent)] sm:text-6xl">05</span>
        <div className="pt-1">
          <h2 id="later-h" className="font-heading text-2xl font-semibold tracking-tight">Publishing & extras</h2>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">Not needed to generate. These keep working from the server environment; their dashboard checks arrive in the next release, so we don't claim they work.</p>
        </div>
      </header>
      <dl className="border-t border-rule">
        {items.map((i) => (
          <div key={i.name} className="grid gap-x-6 gap-y-1 border-b border-rule py-3 sm:grid-cols-[11rem_minmax(0,1fr)_auto] sm:items-baseline">
            <dt className="font-medium">{i.title}</dt>
            <dd className="text-sm text-muted-foreground">{i.blurb} {i.fields.some((f) => f.is_set) ? `Set (${i.fields.filter((f) => f.is_set).length}/${i.fields.length} values, from the ${i.fields.some((f) => f.source === "store") ? "Config page" : "environment"}).` : "Not set."}</dd>
            <dd><StateTag state={i.fields.some((f) => f.is_set) ? "unverified" : "not_set"} /></dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function ConfigPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guide, setGuide] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const location = useLocation();

  const load = useCallback(() => getOverview().then((d) => { setData(d); setError(null); }).catch((x) => setError(errText(x, "Couldn't load the configuration."))), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {  // deep links like /config#telegram
    if (!data || !location.hash) return;
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [data, location.hash]);

  const tier1 = data?.integrations.filter((i) => i.tier === 1) ?? [];
  const later = data?.integrations.filter((i) => i.tier > 1) ?? [];
  const steps = tier1.filter((i) => i.name !== "database");

  function onChanged(i: Integration, r?: Readiness) {
    if (r) setData((d) => d && { ...d, readiness: r, integrations: d.integrations.map((x) => (x.name === i.name ? i : x)) });
    else load();
  }

  return (
    <AppShell>
      <div className="mx-auto grid max-w-[72rem] gap-8 px-4 py-6 md:px-8 md:py-9">
        <PageHeader
          index="05" eyebrow="Setup & health" title="Config"
          lead="Connect the services this app runs on. Every value is checked against the real service before it is saved, so a typo can't break a working setup."
          actions={<>
            <Button variant="outline" size="sm" asChild><Link to="/config/guide"><BookOpen />Setup guide</Link></Button>
            <Button variant="ghost" size="sm" onClick={load} aria-label="Reload"><RefreshCw /></Button>
          </>}
        />
        {error && <p role="alert" className="rounded-md border border-bad/40 bg-bad/10 p-4 text-sm text-bad">{error}</p>}
        {!data && !error && <div className="grid gap-4" role="status" aria-label="Loading configuration"><div className="shimmer h-28 rounded-md" /><div className="shimmer h-72 rounded-md" /></div>}

        {data && (
          <>
            <ReadinessBanner r={data.readiness} steps={steps} />
            {data.precedence === "env" && tier1.some((i) => i.fields.some((f) => f.source === "env")) && (
              <p className="max-w-prose text-xs text-muted-foreground">
                Some values come from the server environment (marked below). While the app migrates, the environment wins over values
                saved here, and GitHub Actions keeps using its own repository secrets until they are removed.
              </p>
            )}
            <div className="grid gap-10 lg:grid-cols-[12rem_minmax(0,1fr)]">
              <nav aria-label="Setup steps" className="h-fit lg:sticky lg:top-8">
                <ol className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3 lg:grid-cols-1 lg:border-l lg:border-rule">
                  {[...tier1, ...(later.length ? [{ name: "later", title: "Publishing & extras", state: "unverified" as State }] : [])].map((s) => (
                    <li key={s.name}>
                      <a href={`#${s.name}`} className="flex items-center gap-2.5 rounded py-1.5 text-sm text-muted-foreground hover:text-foreground lg:-ml-px lg:border-l-2 lg:border-transparent lg:pl-4">
                        <span className="numeral w-5 text-[11px]">{s.name === "later" ? "05" : STEP_NO[s.name]}</span>
                        <StateDot state={s.state} />
                        <span className="truncate">{s.title}</span>
                      </a>
                    </li>
                  ))}
                </ol>
                <p className="mt-6 hidden text-xs leading-relaxed text-muted-foreground lg:block">
                  Secrets are write-only: once saved they're never shown again, only a fingerprint that changes when the value does.
                </p>
              </nav>
              <div className="grid min-w-0 gap-12">
                {tier1.map((i) => <Step key={i.name} integ={i} onChanged={onChanged} onGuide={setGuide} setConfirm={setConfirm} />)}
                {later.length > 0 && <Later items={later} />}
              </div>
            </div>
          </>
        )}
      </div>
      <GuideSheet id={guide} open={!!guide} onOpenChange={(o) => !o && setGuide(null)} />
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirm?.title}</AlertDialogTitle>
            <AlertDialogDescription>{confirm?.body}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => { const c = confirm; setConfirm(null); c?.run(); }}>{confirm?.action}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppShell>
  );
}
