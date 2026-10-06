import { useRef, useState, type ReactNode } from "react";
import {
  ArrowUpRight, CalendarClock, Check, LoaderCircle, RefreshCw, RotateCcw, Send, Undo2, X,
} from "lucide-react";
import { toast } from "sonner";

import { GeneratedBy } from "@/components/generated-by";
import { StatusBadge } from "@/components/status-badge";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import {
  approveItem, editItem, formatIST, fromISTInput, PLATFORM_LABEL, publishNow, regenerateItems,
  rejectItem, retryItem, scheduleItem, STATUS_LABEL, toISTInput, type Group, type Item, type Platform,
} from "@/lib/posts";
import { cn } from "@/lib/utils";

const CAPTION_MAX = 2200;
const YT_TITLE_MAX = 100;
const MONO = "font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground";

function errorMessage(e: unknown) {
  return e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
}

type TargetBox = { key: string; label: string; sub: string; item: Item | null; platform: Platform };

/** label ....... value, the ledger row used across the product */
function Ledger({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-2 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline gap-2">
          <dt className="shrink-0 font-mono text-xs text-muted-foreground">{k}</dt>
          <span aria-hidden className="leader" />
          <dd className="min-w-0 text-right break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Characters used against a limit: a number and a hairline meter that turns red past the limit. */
function Counter({ used, max }: { used: number; max: number }) {
  const over = used > max;
  return (
    <span className="flex items-center gap-2">
      <span aria-hidden className="relative h-[3px] w-14 overflow-hidden rounded-full bg-border">
        <span className={cn("absolute inset-y-0 left-0 rounded-full", over ? "bg-bad" : used / max > 0.9 ? "bg-wait" : "bg-muted-foreground/60")}
              style={{ width: `${Math.min(100, (used / max) * 100)}%` }} />
      </span>
      <span className={cn("font-mono text-[11px] tabular-nums", over ? "text-bad" : "text-muted-foreground")}>{used} / {max}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Platform results (links, errors, retry)
// ---------------------------------------------------------------------------
function PlatformResults({ item, publishingEnabled, onChanged }: { item: Item; publishingEnabled: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState<Platform | null>(null);
  const entries = item.allowed_targets.map((p) => [p, item.platforms[p]] as const);
  if (!entries.some(([, r]) => r) && !item.error) return null;

  async function retry(p: Platform) {
    setBusy(p);
    try {
      await retryItem(item.id, p);
      toast.success(`Retrying ${PLATFORM_LABEL[p]}…`);
      onChanged();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-label="Results by platform" className="divide-y divide-border rounded-lg border border-border">
      {entries.map(([p, r]) =>
        r ? (
          <div key={p} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 text-sm">
            <span className={cn("size-1.5 shrink-0 rounded-full", r.status === "published" ? "bg-ok" : r.status === "failed" ? "bg-bad" : "bg-muted-foreground/60")} aria-hidden />
            <span className="w-20 shrink-0 font-medium">{PLATFORM_LABEL[p]}</span>
            {r.status === "published" && (
              <>
                <span className="text-ok">Published{r.privacy && r.privacy !== "public" ? ` · ${r.privacy}` : ""}</span>
                {r.url && (
                  <a href={r.url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
                    Open <ArrowUpRight className="size-3.5" aria-hidden />
                  </a>
                )}
              </>
            )}
            {r.status === "skipped" && <span className="text-muted-foreground">Skipped: {r.error}</span>}
            {r.status === "failed" && (
              <>
                <span className="min-w-0 flex-1 break-words text-bad">Failed: {r.error}</span>
                <Button size="sm" variant="outline" disabled={!publishingEnabled || busy !== null} onClick={() => retry(p)}
                  title={publishingEnabled ? undefined : "Publishing is turned off in this environment"}>
                  {busy === p ? <LoaderCircle className="animate-spin" /> : <RotateCcw />}
                  Retry
                </Button>
              </>
            )}
          </div>
        ) : null,
      )}
      {item.error && !Object.values(item.platforms).some((r) => r?.status === "failed") && (
        <p className="px-4 py-3 text-sm text-bad">{item.error}</p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Caption + hashtags editor (per item)
// ---------------------------------------------------------------------------
function CaptionEditor({ item, onSaved }: { item: Item; onSaved: () => void }) {
  const [caption, setCaption] = useState(item.caption);
  const [tags, setTags] = useState(item.hashtags.join(" "));
  const [saving, setSaving] = useState(false);


  const dirty = caption !== item.caption || tags.trim() !== item.hashtags.join(" ");
  const length = caption.trim().length + (tags.trim() ? 2 + tags.trim().length : 0);

  async function save() {
    setSaving(true);
    try {
      await editItem(item.id, { caption, hashtags: tags.split(/[\s,]+/).filter(Boolean) });
      toast.success("Caption saved");
      onSaved();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4">
      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor={`caption-${item.id}`} className={MONO}>Caption</Label>
          <Counter used={length} max={CAPTION_MAX} />
        </div>
        <Textarea
          id={`caption-${item.id}`}
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          disabled={!item.editable || saving}
          className="min-h-36 text-sm leading-relaxed"
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`tags-${item.id}`} className={MONO}>Hashtags</Label>
        <Input
          id={`tags-${item.id}`}
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          disabled={!item.editable || saving}
          placeholder="#coding #dsa"
          className="font-mono text-xs text-primary md:text-xs"
        />
      </div>
      {item.editable && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={save} disabled={!dirty || saving || length > CAPTION_MAX}>
            {saving ? <LoaderCircle className="animate-spin" /> : <Check />}
            Save caption
          </Button>
          <Button size="sm" variant="ghost" disabled={!dirty || saving} onClick={() => { setCaption(item.caption); setTags(item.hashtags.join(" ")); }}>
            <Undo2 />
            Discard
          </Button>
          {dirty && <span className="font-mono text-[11px] text-wait">unsaved</span>}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// YouTube title / description (reels)
// ---------------------------------------------------------------------------
function YouTubeEditor({ item, onSaved }: { item: Item; onSaved: () => void }) {
  const yt = item.youtube!;
  const [title, setTitle] = useState(yt.title);
  const [description, setDescription] = useState(yt.description);
  const [saving, setSaving] = useState(false);


  const dirty = title !== yt.title || description !== yt.description;
  const auto = <span className="ml-1.5 rounded-[3px] border border-border px-1 py-px font-mono text-[9px] tracking-[0.12em] normal-case text-muted-foreground">automatic</span>;

  async function save(body: { yt_title?: string; yt_description?: string }, message: string) {
    setSaving(true);
    try {
      await editItem(item.id, body);
      toast.success(message);
      onSaved();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby={`yt-h-${item.id}`} className="grid gap-4 border-t border-dashed border-border pt-6">
      <div>
        <h3 id={`yt-h-${item.id}`} className="font-heading text-base font-semibold tracking-tight">YouTube Short</h3>
        <p className="text-xs text-muted-foreground">Title and description for YouTube. Leave them automatic to follow the caption.</p>
      </div>
      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor={`yt-title-${item.id}`} className={MONO}>YouTube title {!yt.title_is_custom && auto}</Label>
          <Counter used={title.length} max={YT_TITLE_MAX} />
        </div>
        <Input id={`yt-title-${item.id}`} value={title} onChange={(e) => setTitle(e.target.value)} disabled={!item.editable || saving} />
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`yt-desc-${item.id}`} className={MONO}>YouTube description {!yt.description_is_custom && auto}</Label>
        <Textarea id={`yt-desc-${item.id}`} value={description} onChange={(e) => setDescription(e.target.value)} disabled={!item.editable || saving} className="min-h-32 text-sm" />
      </div>
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span className="font-mono">Tags:</span>
        {yt.tags.length ? yt.tags.map((t) => <span key={t} className="font-mono text-foreground/80">{t}</span>).reduce<ReactNode[]>((a, el, i) => (i ? [...a, <span key={`s${i}`} aria-hidden>·</span>, el] : [el]), [])
          : <span>none</span>}
      </p>
      {item.editable && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={!dirty || saving || title.length > YT_TITLE_MAX} onClick={() => save({ yt_title: title, yt_description: description }, "YouTube details saved")}>
            {saving ? <LoaderCircle className="animate-spin" /> : <Check />}
            Save YouTube details
          </Button>
          {(yt.title_is_custom || yt.description_is_custom) && (
            <Button size="sm" variant="ghost" disabled={saving} onClick={() => save({ yt_title: "", yt_description: "" }, "Back to automatic title and description")}>
              <RotateCcw />
              Use automatic
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

function Feedback({ text }: { text: string }) {
  return (
    <blockquote className="border-l-2 border-ai/70 py-0.5 pl-3 text-sm">
      <span className={cn(MONO, "mb-1 block text-[10px]")}>Feedback applied</span>
      {text}
    </blockquote>
  );
}

// ---------------------------------------------------------------------------
// The panel
// ---------------------------------------------------------------------------
export function PostPanel({
  group, open, onOpenChange, onChanged, publishingEnabled,
}: {
  group: Group | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChanged: () => void;
  publishingEnabled: boolean;
}) {
  const reel = group?.items.reel ?? null;
  const carousel = group?.items.carousel ?? null;
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"publish" | "reject" | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [regenOpen, setRegenOpen] = useState(false);
  const [regenScope, setRegenScope] = useState<"content" | "reel" | "carousel">("content");
  const [feedback, setFeedback] = useState("");
  const sheetRef = useRef<HTMLDivElement>(null);

  const boxes: TargetBox[] = [
    { key: "ig-reel", label: "IG Reel", sub: "Instagram", item: reel, platform: "ig" },
    { key: "ig-carousel", label: "IG Carousel", sub: "Instagram", item: carousel, platform: "ig" },
    { key: "yt-short", label: "YT Short", sub: "YouTube", item: reel, platform: "yt" },
  ];
  const items = [reel, carousel].filter(Boolean) as Item[];
  const decidable = items.filter((i) => i.can.approve);
  const rejectable = items.filter((i) => i.can.reject);
  const regenable = items.filter((i) => i.can.regen);

  const plan = decidable.map((i) => ({ item: i, targets: i.targets })).filter((p) => p.targets.length);

  if (!group) return null;

  async function run(label: string, fn: () => Promise<unknown>, success: string) {
    setBusy(label);
    try {
      await fn();
      toast.success(success);
      onChanged();
    } catch (e) {
      toast.error(errorMessage(e));
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  async function toggleTarget(box: TargetBox, checked: boolean) {
    const item = box.item;
    if (!item) return;
    const next = checked ? [...new Set([...item.targets, box.platform])] : item.targets.filter((t) => t !== box.platform);
    await run(`target-${box.key}`, () => editItem(item.id, { targets: next }), `${box.label} ${checked ? "on" : "off"}`);
  }

  const approveAll = () =>
    run("approve", () => Promise.all(decidable.map((i) => approveItem(i.id))), "Approved — it will post at its scheduled time");

  const publishAll = () =>
    run("publish", () => Promise.all(decidable.map((i) => publishNow(i.id))), "Publishing started");

  const rejectAll = () =>
    run("reject", () => Promise.all(rejectable.map((i) => rejectItem(i.id))), "Rejected");

  const scheduleAll = () =>
    run("schedule", () => Promise.all(decidable.map((i) => scheduleItem(i.id, fromISTInput(scheduleAt)))),
      `Scheduled for ${formatIST(fromISTInput(scheduleAt))} IST`).then(() => setScheduleOpen(false));

  const regenerate = () => {
    const ids = regenScope === "content" ? regenable.map((i) => i.id)
      : regenable.filter((i) => i.kind === regenScope).map((i) => i.id);
    return run("regen", () => regenerateItems(ids, feedback), "Regeneration requested — new previews will follow")
      .then(() => { setRegenOpen(false); setFeedback(""); });
  };

  const bothRegenable = regenable.length === 2;

  // Why the decision buttons are off, in words (shown under them).
  const why = !plan.length
    ? decidable.length
      ? "Pick at least one platform under “Post to” to approve, schedule or publish."
      : `Nothing to approve: ${items.map((i) => `${i.kind} ${STATUS_LABEL[i.status].toLowerCase().replace(/…$/, "")}`).join(", ")}.`
    : null;

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          ref={sheetRef}
          // land on the panel itself, not on Approve: opening a post is reading, not deciding
          onOpenAutoFocus={(e) => { e.preventDefault(); sheetRef.current?.focus({ preventScroll: true }); }}
          className="gap-0 overflow-y-auto p-0 outline-none data-[side=right]:w-full data-[side=right]:sm:max-w-2xl"
        >
          <SheetHeader className="gap-3 border-b border-border px-5 pt-7 pb-5 pr-14 sm:px-7">
            <span aria-hidden className="amber-rule" />
            <SheetTitle className="font-heading text-xl leading-snug text-balance sm:text-2xl">{group.topic}</SheetTitle>
            <SheetDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs">
              <span className="tracking-wider text-foreground/85 uppercase">{group.category}</span>
              <span aria-hidden className="text-border">/</span>
              <span className="inline-flex items-center gap-1.5"><CalendarClock className="size-3.5" aria-hidden />{formatIST(group.publish_at)} IST</span>
              {group.versions > 1 && <><span aria-hidden className="text-border">/</span><span>version {group.versions}</span></>}
              <GeneratedBy groupId={group.group_id} />
            </SheetDescription>
          </SheetHeader>

          {/* the decision: primary on the left, quiet and destructive set apart on the right */}
          <section aria-label="Actions" className="z-10 grid gap-2.5 border-b border-border bg-background/95 px-5 py-4 backdrop-blur sm:sticky sm:top-0 sm:px-7">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={approveAll} disabled={!plan.length || busy !== null}>
                {busy === "approve" ? <LoaderCircle className="animate-spin" /> : <Check />}
                Approve
              </Button>
              <Button variant="outline" disabled={!plan.length || busy !== null}
                onClick={() => { setScheduleAt(toISTInput(group.publish_at)); setScheduleOpen(true); }}>
                <CalendarClock />
                Schedule
              </Button>
              <Button variant="secondary" onClick={() => setConfirm("publish")} disabled={!plan.length || !publishingEnabled || busy !== null}
                title={publishingEnabled ? undefined : "Publishing is turned off in this environment"}>
                {busy === "publish" ? <LoaderCircle className="animate-spin" /> : <Send />}
                Publish now
              </Button>
              <span aria-hidden className="mx-1 hidden h-6 w-px bg-border sm:block" />
              <div className="flex gap-1 max-sm:w-full">
                <Button variant="ghost" disabled={!regenable.length || busy !== null}
                  onClick={() => { setRegenScope(bothRegenable ? "content" : (regenable[0]?.kind ?? "content")); setRegenOpen(true); }}>
                  <RefreshCw />
                  Regenerate
                </Button>
                <Button variant="ghost" className="text-bad hover:bg-bad/10 hover:text-bad" disabled={!rejectable.length || busy !== null} onClick={() => setConfirm("reject")}>
                  <X />
                  Reject
                </Button>
              </div>
            </div>
            {(why || !publishingEnabled) && (
              <div className="grid gap-0.5 text-xs text-muted-foreground">
                {why && <p>{why}</p>}
                {!publishingEnabled && <p>Publishing is turned off in this environment (PUBLISH_ENABLED=false).</p>}
              </div>
            )}
          </section>

          <div className="grid gap-8 px-5 py-6 sm:px-7">
            {/* platforms */}
            <section aria-labelledby="platforms-h" className="grid gap-3">
              <h3 id="platforms-h" className={MONO}>Post to</h3>
              <div className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-3">
                {boxes.map((b) => {
                  const disabled = !b.item || !b.item.editable || busy !== null;
                  const checked = !!b.item && b.item.targets.includes(b.platform);
                  return (
                    <label
                      key={b.key}
                      className="relative flex min-h-12 cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 text-sm transition-colors duration-(--dur-fast) hover:border-rule has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-55 has-[[data-state=checked]]:border-primary/55 has-[[data-state=checked]]:bg-primary/[0.07]"
                    >
                      <Checkbox aria-label={b.label} checked={checked} disabled={disabled} onCheckedChange={(v) => toggleTarget(b, v === true)} />
                      <span className="grid leading-tight">
                        <span className="font-medium">{b.label}</span>
                        <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">{b.item ? b.sub : "not in this post"}</span>
                      </span>
                      {busy === `target-${b.key}` && <LoaderCircle className="ml-auto size-3.5 animate-spin text-muted-foreground" aria-hidden />}
                    </label>
                  );
                })}
              </div>
            </section>

            <Tabs defaultValue={reel ? "reel" : "carousel"} className="gap-6">
              <TabsList className="w-full justify-start">
                {reel && <TabsTrigger value="reel" className="flex-none">Reel <StatusBadge status={reel.status} short className="ml-1.5 max-[360px]:hidden" /></TabsTrigger>}
                {carousel && <TabsTrigger value="carousel" className="flex-none">Carousel <StatusBadge status={carousel.status} short className="ml-1.5 max-[360px]:hidden" /></TabsTrigger>}
              </TabsList>

              {reel && (
                <TabsContent value="reel" className="grid gap-7">
                  <PlatformResults item={reel} publishingEnabled={publishingEnabled} onChanged={onChanged} />
                  <div className="grid gap-6 sm:grid-cols-[minmax(0,14rem)_1fr]">
                    <div className="relative mx-auto w-full max-w-56">
                      {reel.media.reel ? (
                        <video
                          key={reel.media.reel}
                          src={reel.media.reel}
                          poster={reel.media.cover}
                          controls
                          playsInline
                          preload="metadata"
                          className="aspect-[9/16] w-full rounded-[18px] border border-rule bg-sunken object-cover"
                        />
                      ) : <div className="grid aspect-[9/16] place-items-center rounded-[18px] border border-dashed border-rule bg-sunken font-mono text-xs text-muted-foreground">No video</div>}
                    </div>
                    <div className="grid content-start gap-5">
                      <Ledger rows={[
                        ["Voice", reel.voice ? reel.voice.split("-")[2]?.replace(/Multilingual|Neural/g, "") : "—"],
                        ["Version", `v${reel.version}`],
                        ["Created", `${formatIST(reel.created_at)} IST`],
                        ["Slot", `${formatIST(reel.publish_at)} IST`],
                      ]} />
                      {reel.feedback && <Feedback text={reel.feedback} />}
                    </div>
                  </div>
                  <CaptionEditor key={reel.id + reel.caption + reel.hashtags.join()} item={reel} onSaved={onChanged} />
                  {reel.youtube && <YouTubeEditor key={reel.id + reel.youtube.title + reel.youtube.description} item={reel} onSaved={onChanged} />}
                </TabsContent>
              )}

              {carousel && (
                <TabsContent value="carousel" className="grid gap-7">
                  <PlatformResults item={carousel} publishingEnabled={publishingEnabled} onChanged={onChanged} />
                  <div className="grid gap-2">
                    <p className={MONO}>{(carousel.media.carousel ?? []).length} slides</p>
                    <div className="-mx-5 flex snap-x snap-mandatory gap-3 overflow-x-auto px-5 pb-3 sm:-mx-7 sm:px-7" aria-label="Carousel slides" role="list">
                      {(carousel.media.carousel ?? []).map((url, i, all) => (
                        <a key={url} href={url} target="_blank" rel="noreferrer" role="listitem" className="group/slide relative shrink-0 snap-start rounded-[12px]">
                          <img
                            src={url}
                            alt={`Slide ${i + 1}`}
                            loading="lazy"
                            className="aspect-[4/5] w-40 rounded-[12px] border border-border bg-sunken object-cover transition-transform duration-(--dur-base) group-hover/slide:-translate-y-0.5 sm:w-48"
                          />
                          <span aria-hidden className="absolute top-2 left-2 rounded-[4px] bg-background/80 px-1.5 py-0.5 font-mono text-[10px] tabular-nums backdrop-blur">
                            {String(i + 1).padStart(2, "0")}/{String(all.length).padStart(2, "0")}
                          </span>
                        </a>
                      ))}
                      {!(carousel.media.carousel ?? []).length && (
                        <div className="grid aspect-[4/5] w-40 place-items-center rounded-[12px] border border-dashed border-rule bg-sunken font-mono text-xs text-muted-foreground">No slides</div>
                      )}
                    </div>
                  </div>
                  {carousel.feedback && <Feedback text={carousel.feedback} />}
                  <CaptionEditor key={carousel.id + carousel.caption + carousel.hashtags.join()} item={carousel} onSaved={onChanged} />
                </TabsContent>
              )}
            </Tabs>
          </div>
        </SheetContent>
      </Sheet>

      {/* confirm: publish now / reject */}
      <AlertDialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirm === "publish" ? "Publish now?" : "Reject this post?"}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              {confirm === "publish" ? (
                <div className="grid w-full gap-3">
                  <p>This posts publicly right away:</p>
                  <ul className="grid gap-1.5 rounded-lg border border-border p-3">
                    {plan.map(({ item, targets }) => (
                      <li key={item.id} className="flex items-baseline gap-2 text-foreground">
                        <span className="font-mono text-xs">{item.kind === "reel" ? "Reel" : "Carousel"}</span>
                        <span aria-hidden className="leader" />
                        <span>→ {targets.map((t) => PLATFORM_LABEL[t]).join(" + ")}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p>{rejectable.map((i) => (i.kind === "reel" ? "The reel" : "The carousel")).join(" and ")} won't be published. This also updates Telegram.</p>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant={confirm === "reject" ? "destructive" : "default"}
              onClick={() => (confirm === "publish" ? publishAll() : rejectAll())}
            >
              {confirm === "publish" ? "Publish now" : "Reject"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* schedule */}
      <Dialog open={scheduleOpen} onOpenChange={setScheduleOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schedule</DialogTitle>
            <DialogDescription>Approves the post and publishes it at this time (Indian Standard Time), at the next check after it.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="schedule-at" className={MONO}>Date and time (IST)</Label>
            <Input id="schedule-at" type="datetime-local" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} className="font-mono" />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setScheduleOpen(false)}>Cancel</Button>
            <Button onClick={scheduleAll} disabled={!scheduleAt || busy !== null}>
              {busy === "schedule" && <LoaderCircle className="animate-spin" />}
              Schedule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* regenerate */}
      <Dialog open={regenOpen} onOpenChange={setRegenOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Regenerate</DialogTitle>
            <DialogDescription>Gemini rewrites it with your feedback; new previews arrive here and in Telegram in about 10 minutes.</DialogDescription>
          </DialogHeader>
          <RadioGroup value={regenScope} onValueChange={(v) => setRegenScope(v as typeof regenScope)} className="grid gap-2">
            {[
              { value: "content", label: "Content (reel + carousel, one new script)", enabled: bothRegenable },
              { value: "reel", label: "Reel only", enabled: regenable.some((i) => i.kind === "reel") },
              { value: "carousel", label: "Carousel only", enabled: regenable.some((i) => i.kind === "carousel") },
            ].map((o) => (
              <label key={o.value} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border px-3 text-sm transition-colors hover:border-rule has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[[data-state=checked]]:border-primary/55 has-[[data-state=checked]]:bg-primary/[0.07]">
                <RadioGroupItem value={o.value} disabled={!o.enabled} />
                {o.label}
              </label>
            ))}
          </RadioGroup>
          <div className="grid gap-2">
            <Label htmlFor="regen-feedback" className={MONO}>Feedback (optional)</Label>
            <Textarea id="regen-feedback" value={feedback} onChange={(e) => setFeedback(e.target.value)}
              placeholder='e.g. "Show the example prompt in a highlighted box" or "use the voice Andrew"' />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRegenOpen(false)}>Cancel</Button>
            <Button onClick={regenerate} disabled={busy !== null}>
              {busy === "regen" ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
              Regenerate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
