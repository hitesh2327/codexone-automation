import { useEffect, useId, useRef, useState } from "react";
import { Info, Sparkles, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { checkTopic, requestGeneration } from "@/lib/generate";
import { cn } from "@/lib/utils";
import { SLOT_LABEL, newIdempotencyKey, type GenConfig, type Job, type Slot } from "@/lib/generate-format";

export type Prefill = { nonce: number; slot?: string; category?: string; topic?: string; source_url?: string };

const AUTO = "auto";

function Hint({ id, children, tone = "muted" }: { id: string; children: React.ReactNode; tone?: "muted" | "bad" | "warn" }) {
  return (
    <p id={id} className={cn("text-xs leading-snug", tone === "bad" ? "text-bad" : tone === "warn" ? "text-wait" : "text-muted-foreground")}>
      {children}
    </p>
  );
}

/** "Generate now": slot, category, optional own topic + link. Always confirms before anything is dispatched. */
export function GenerateForm({ cfg, slots, blocked, prefill, onRequested, onActive, onRefresh }: {
  cfg: GenConfig;
  /** Today's slots (the only ones a run can be requested for). */
  slots: Slot[];
  /** Why the form can't be used right now (no token, a run is active, daily limit), or null. */
  blocked: string | null;
  prefill: Prefill | null;
  onRequested: (job: Job) => void;
  onActive: (job: Job) => void;
  onRefresh: () => void;
}) {
  const uid = useId();
  const [slot, setSlot] = useState(AUTO);
  const [category, setCategory] = useState(AUTO);
  const [topic, setTopic] = useState("");
  const [url, setUrl] = useState("");
  const [force, setForce] = useState(false);
  const [allowDup, setAllowDup] = useState(false);
  const [dup, setDup] = useState<{ title: string; date: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const key = useRef(newIdempotencyKey());
  const root = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (!prefill) return;
    setSlot(prefill.slot ?? AUTO);
    if (prefill.category !== undefined) setCategory(prefill.category || AUTO);
    if (prefill.topic !== undefined) setTopic(prefill.topic);
    if (prefill.source_url !== undefined) setUrl(prefill.source_url);
    setForce(false);
    setAllowDup(false);
    setError(null);
    root.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [prefill]);

  const t = topic.trim();
  const [minLen, maxLen] = cfg.topic_length;
  const info = slots.find((s) => s.time === slot);
  const needsForce = !!info && (info.state === "generated" || info.state === "stale");

  // Tell the admin about a repeat while they type, not only after they press the button.
  useEffect(() => {
    setDup(null);
    setAllowDup(false);
    if (t.length < minLen || t.length > maxLen) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      checkTopic(t, ctrl.signal).then((r) => setDup(r.duplicate)).catch(() => {});
    }, 500);
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [t, minLen, maxLen]);

  const topicErr = t && (t.length < minLen ? `At least ${minLen} characters` : t.length > maxLen ? `At most ${maxLen} characters` : null);
  const categoryErr = t && category === AUTO ? "Pick a category for your own topic" : null;
  const urlErr = url.trim() && !/^https:\/\/\S+$/i.test(url.trim()) ? "Use a full https:// link" : null;
  const invalid = !!(topicErr || categoryErr || urlErr || (url.trim() && !t));
  const waiting = (needsForce && !force) || (!!dup && !allowDup);
  const disabled = !!blocked || invalid || waiting || busy;
  const quotaWarn = cfg.quota_cooldown_until && new Date(cfg.quota_cooldown_until).getTime() > Date.now();

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const job = await requestGeneration({
        slot, category: category === AUTO ? null : category, topic: t || null, source_url: url.trim() || null,
        force, allow_duplicate: allowDup, confirm_quota: !!quotaWarn, idempotency_key: key.current,
      });
      key.current = newIdempotencyKey();
      toast.success("Request sent. Previews arrive in Telegram when it finishes.");
      onRequested(job);
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
      if (e.status !== 0) key.current = newIdempotencyKey();  // a network failure may still have reached the server: keep the key
      if (e.code === "job_active" && e.data?.job) onActive(e.data.job as Job);
      else if (e.code === "duplicate_topic") setDup({ title: String(e.data?.title ?? ""), date: String(e.data?.date ?? "") });
      else setError(e.message);
      if (["job_active", "cap_reached", "quota_cooldown", "not_configured", "dispatch_failed"].includes(e.code ?? "")) onRefresh();
      if (e.code !== "duplicate_topic") toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  const slotText = slot === AUTO ? "the next free slot" : `today ${slot} IST`;
  return (
    <form
      ref={root}
      aria-labelledby={`${uid}-title`}
      onSubmit={(e) => { e.preventDefault(); if (!disabled) setConfirm(true); }}
      className="grid gap-5 border-t border-rule pt-7 lg:sticky lg:top-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-8"
    >
      <div>
        <p className="label-mono mb-1.5">New request</p>
        <h2 id={`${uid}-title`} className="font-heading text-xl font-semibold tracking-tight">Generate now</h2>
        <p className="mt-1 text-sm text-muted-foreground">One reel and one carousel. Nothing is posted until you approve it.</p>
      </div>

      {blocked && (
        <p role="status" className="flex gap-2 border-l-[3px] border-wait bg-wait/10 py-2.5 pr-3 pl-3.5 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-wait" aria-hidden />
          <span>{blocked}</span>
        </p>
      )}
      {quotaWarn && !blocked && (
        <p role="status" className="flex gap-2 border-l-[3px] border-wait bg-wait/10 py-2.5 pr-3 pl-3.5 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-wait" aria-hidden />
          <span>Gemini&apos;s free quota ran out recently, so this will probably fail. You can still try; you&apos;ll be asked to confirm.</span>
        </p>
      )}

      <fieldset disabled={!!blocked} className="grid min-w-0 divide-y divide-border border-y border-border disabled:opacity-60 [&>*]:py-4">
        <div className="grid gap-1.5">
          <Label className="label-mono" htmlFor={`${uid}-slot`}>Slot</Label>
          <Select value={slot} onValueChange={(v) => { setSlot(v); setForce(false); }}>
            <SelectTrigger id={`${uid}-slot`} className="w-full data-[size=default]:h-11">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={AUTO}>Next free slot</SelectItem>
              {slots.map((s) => (
                <SelectItem key={s.time} value={s.time}>
                  Today {s.time} IST · {SLOT_LABEL[s.state]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {info?.state === "late" && <Hint id={`${uid}-slot-note`} tone="warn">This slot has passed. The post goes out as soon as you approve it.</Hint>}
          {needsForce && (
            <Hint id={`${uid}-slot-note`} tone="warn">
              {info!.state === "generated" ? "This slot already has a post." : `This slot passed over ${cfg.late_limit_hours}h ago.`} Tick &ldquo;extra post&rdquo; below to generate anyway.
            </Hint>
          )}
        </div>

        <div className="grid gap-1.5">
          <Label className="label-mono" htmlFor={`${uid}-cat`}>Category</Label>
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger id={`${uid}-cat`} className="w-full data-[size=default]:h-11" aria-invalid={!!categoryErr} aria-describedby={categoryErr ? `${uid}-cat-err` : undefined}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={AUTO}>Auto (by weight)</SelectItem>
              {cfg.categories.map((c) => <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {categoryErr && <Hint id={`${uid}-cat-err`} tone="bad">{categoryErr}</Hint>}
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor={`${uid}-topic`} className="label-mono">
            Your own topic <span className="tracking-normal normal-case">(optional)</span>
          </Label>
          <Input
            id={`${uid}-topic`} value={topic} onChange={(e) => setTopic(e.target.value)} className="h-11"
            placeholder="e.g. How consistent hashing works" autoComplete="off" maxLength={maxLen + 40}
            aria-invalid={!!topicErr} aria-describedby={`${uid}-topic-help${topicErr ? ` ${uid}-topic-err` : ""}${dup ? ` ${uid}-dup` : ""}`}
          />
          <Hint id={`${uid}-topic-help`}>
            {t ? `${t.length}/${maxLen}. ` : ""}Skips the trending search. It still gets the same accuracy review; checking it before you approve is on you.
          </Hint>
          {topicErr && <Hint id={`${uid}-topic-err`} tone="bad">{topicErr}</Hint>}
          {dup && (
            <div id={`${uid}-dup`} role="status" className="grid gap-2 border-l-[3px] border-wait bg-wait/10 py-2.5 pr-3 pl-3.5 text-sm">
              <span>
                Looks like &ldquo;{dup.title}&rdquo;{dup.date ? ` (${dup.date})` : ""}, which was covered recently.
              </span>
              <span className="flex items-start gap-2">
                <Checkbox id={`${uid}-dup-ok`} checked={allowDup} onCheckedChange={(v) => setAllowDup(v === true)} className="mt-0.5" />
                <Label htmlFor={`${uid}-dup-ok`} className="text-sm leading-snug font-normal">Generate it anyway (new angle)</Label>
              </span>
            </div>
          )}
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor={`${uid}-url`} className="label-mono">
            Source link <span className="tracking-normal normal-case">(optional)</span>
          </Label>
          <Input
            id={`${uid}-url`} type="url" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} className="h-11"
            placeholder="https://" autoComplete="off" disabled={!t}
            aria-invalid={!!urlErr} aria-describedby={`${uid}-url-help${urlErr ? ` ${uid}-url-err` : ""}`}
          />
          <Hint id={`${uid}-url-help`}>The page is not read. The link is only cited with the post, so the topic must stand on its own.</Hint>
          {urlErr && <Hint id={`${uid}-url-err`} tone="bad">{urlErr}</Hint>}
        </div>

        <div className="flex items-start gap-2.5">
          <Checkbox id={`${uid}-force`} checked={force} onCheckedChange={(v) => setForce(v === true)} className="mt-0.5" />
          <div className="grid gap-0.5">
            <Label htmlFor={`${uid}-force`} className="leading-snug">Extra post for a slot that already has one</Label>
            <p className="text-xs text-muted-foreground">Also needed for a slot that passed over {cfg.late_limit_hours}h ago.</p>
          </div>
        </div>
      </fieldset>

      {error && <p role="alert" className="border-l-[3px] border-bad bg-bad/10 py-2.5 pr-3 pl-3.5 text-sm text-bad">{error}</p>}

      <div className="grid gap-1.5">
        <Button type="submit" size="lg" className="h-11 w-full" disabled={disabled} aria-describedby={`${uid}-quota`}>
          <Sparkles />
          {busy ? "Sending…" : "Generate"}
        </Button>
        <p id={`${uid}-quota`} className="text-center text-xs text-muted-foreground">
          {cfg.used_today} of {cfg.daily_cap} dashboard runs used today
        </p>
      </div>

      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Generate a post for {slotText}?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="grid gap-2 text-left">
                <ul className="grid gap-1 rounded-lg border bg-muted/40 p-3 text-sm text-foreground">
                  <li><span className="text-muted-foreground">Category:</span> {category === AUTO ? "Auto (by weight)" : category}</li>
                  <li><span className="text-muted-foreground">Topic:</span> {t || "Picked from today's trending topics"}</li>
                  {url.trim() && <li className="break-all"><span className="text-muted-foreground">Link:</span> {url.trim()} (cited, not read)</li>}
                  {force && <li>Adds an extra post to a slot that has one or has long passed.</li>}
                </ul>
                <p>It takes about 5 to 10 minutes and uses Gemini quota and GitHub Actions minutes. Previews are sent to Telegram; <strong>nothing is published until you approve it</strong>.</p>
                {quotaWarn && <p className="text-wait">Gemini&apos;s free quota ran out recently. This will probably fail.</p>}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={submit}>{quotaWarn ? "Generate anyway" : "Generate"}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </form>
  );
}
