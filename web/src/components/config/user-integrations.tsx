/**
 * Per-user integration settings: Telegram 1-click connect/unlink/bot override, Instagram, YouTube.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Check, CircleDashed, ExternalLink, LoaderCircle, Pencil, RotateCcw, Send, Unlink } from "lucide-react";
import { toast } from "sonner";

function YouTubeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
    </svg>
  );
}

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConnectBotDialog } from "@/components/config/connect-bot-dialog";
import { ApiError } from "@/lib/api";
import {
  confirmTelegramLink, createTelegramLink, createYouTubeLink, deleteUserIntegration, getUserIntegrations, putUserIntegration,
  setCustomTelegramBot, setTelegramBotName, unlinkTelegram, unlinkYouTube, type KeyStatus, type TelegramLinkResponse, type TelegramMeta, type YouTubeMeta,
} from "@/lib/config";

// ------------------------------------------------------------------------------------------------
// Telegram 1-click connect + unlink + change bot
// ------------------------------------------------------------------------------------------------
function TelegramSection({
  statuses,
  meta,
  onSaved,
}: {
  statuses: Record<string, KeyStatus>;
  meta?: TelegramMeta;
  onSaved: () => void;
}) {
  const [link, setLink] = useState<TelegramLinkResponse | null>(null);
  const [busy, setBusy] = useState<null | "link" | "confirm" | "unlink" | "bot" | "resetBot" | "manual" | "name">(null);
  const [error, setError] = useState<string | null>(null);
  const [showBotForm, setShowBotForm] = useState(false);
  const [showNameForm, setShowNameForm] = useState(false);
  const [showConnectBotDialog, setShowConnectBotDialog] = useState(false);
  const [botNameInput, setBotNameInput] = useState("");
  const [botToken, setBotToken] = useState("");
  const [manualChatId, setManualChatId] = useState("");
  const pollTimer = useRef<number | null>(null);
  const pollAbort = useRef<AbortController | null>(null);

  const chatStatus = statuses.TG_CHAT_ID;
  const botStatus = statuses.TG_BOT_TOKEN;
  const connected = Boolean(chatStatus?.set || meta?.connected);
  const usingCustomBot = Boolean(botStatus?.set || meta?.using_custom_bot);

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
    pollAbort.current?.abort();
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const checkOnce = useCallback(async (quiet = false) => {
    if (!quiet) setBusy("confirm");
    pollAbort.current?.abort();
    const ctrl = new AbortController();
    pollAbort.current = ctrl;
    try {
      const res = await confirmTelegramLink(ctrl.signal);
      if (ctrl.signal.aborted) return;
      if (res.connected) {
        stopPolling();
        setLink(null);
        setError(null);
        onSaved();
        toast.success(res.chat_title ? `Telegram connected (${res.chat_title})` : "Telegram connected");
      } else if (!quiet) {
        setError("Haven't seen /start yet. Open the Telegram link, press Start, then click Check again.");
      }
    } catch (e) {
      if ((e as Error).name === "AbortError" || ctrl.signal.aborted) return;
      stopPolling();
      if (e instanceof ApiError && e.code === "telegram.link_expired") setLink(null);
      setError(e instanceof ApiError ? e.message : "Could not verify Telegram link.");
    } finally {
      if (!ctrl.signal.aborted && !quiet) setBusy(null);
    }
  }, [onSaved, stopPolling]);

  function handleConnect() {
    setShowConnectBotDialog(true);
  }

  async function handleConfirmConnect(botName: string) {
    setBusy("link");
    setError(null);
    stopPolling();
    try {
      const res = await createTelegramLink(botName);
      setLink(res);
      setShowConnectBotDialog(false);
      window.open(res.url, "_blank", "noopener,noreferrer");
      const deadline = Date.now() + 120_000;
      pollTimer.current = window.setInterval(() => {
        if (Date.now() > deadline) {
          stopPolling();
          return;
        }
        void checkOnce(true);
      }, 2500);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create Telegram link.");
    } finally {
      setBusy(null);
    }
  }

  async function handleUnlink() {
    setBusy("unlink");
    setError(null);
    stopPolling();
    setLink(null);
    try {
      await unlinkTelegram(false);
      onSaved();
      toast.success("Telegram unlinked");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not unlink Telegram.");
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveCustomBot() {
    const token = botToken.trim();
    if (!token) return;
    setBusy("bot");
    setError(null);
    stopPolling();
    setLink(null);
    try {
      const res = await setCustomTelegramBot(token);
      setBotToken("");
      setShowBotForm(false);
      onSaved();
      toast.success(`Switched to ${res.bot_username}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save custom bot token.");
    } finally {
      setBusy(null);
    }
  }

  async function handleResetBot() {
    setBusy("resetBot");
    setError(null);
    stopPolling();
    setLink(null);
    try {
      await deleteUserIntegration("TG_BOT_TOKEN");
      setShowBotForm(false);
      onSaved();
      toast.success("Switched back to Mintly's default bot");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reset bot.");
    } finally {
      setBusy(null);
    }
  }

  async function handleManualSave() {
    const val = manualChatId.trim();
    if (!val) return;
    setBusy("manual");
    setError(null);
    try {
      await putUserIntegration("TG_CHAT_ID", val);
      setManualChatId("");
      onSaved();
      toast.success("Telegram Chat ID saved");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save Chat ID.");
    } finally {
      setBusy(null);
    }
  }

  const handleOpenNameForm = () => {
    setBotNameInput(meta?.bot_name || "");
    setShowNameForm((s) => !s);
    setShowBotForm(false);
  };

  const handleCancelNameForm = () => {
    setShowNameForm(false);
    setBotNameInput("");
  };

  async function handleSaveBotName() {
    const clean = botNameInput.trim();
    if (!clean) return;
    setBusy("name");
    setError(null);
    try {
      const res = await setTelegramBotName(clean);
      setShowNameForm(false);
      onSaved();
      toast.success(res.message || `Telegram bot name updated to '${clean}'`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update Telegram bot name.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Telegram</CardTitle>
          {connected ? (
            <span className="inline-flex items-center gap-1 text-xs text-ok">
              <Check className="size-3" aria-hidden />
              Connected{chatStatus?.masked ? ` · Chat ${chatStatus.masked}` : ""}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <CircleDashed className="size-3" aria-hidden />
              Not connected
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-xs text-muted-foreground">
            {usingCustomBot
              ? `Using your custom Telegram bot (${botStatus?.masked ?? "saved"}).`
              : "Using Mintly's shared approval bot."}
          </p>
          <p className="text-xs font-medium text-foreground">
            Bot: {meta?.bot_name && !meta.bot_name.toLowerCase().includes("codexonebyhitesh") ? meta.bot_name : "AI Assistant"} {meta?.bot_username ? `(${meta.bot_username})` : ""}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={handleConnect} disabled={busy !== null}>
            {busy === "link" ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
            {connected ? "Reconnect Telegram" : "Connect Telegram"}
          </Button>

          {connected && (
            <Button size="sm" variant="outline" onClick={handleUnlink} disabled={busy !== null}>
              {busy === "unlink" ? <LoaderCircle className="size-4 animate-spin" /> : <Unlink className="size-4" />}
              Unlink
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            onClick={handleOpenNameForm}
            disabled={busy !== null}
          >
            <Pencil className="size-4" />
            Change bot name
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setShowBotForm((s) => !s);
              setShowNameForm(false);
            }}
            disabled={busy !== null}
          >
            <Bot className="size-4" />
            Change bot
          </Button>

          {usingCustomBot && (
            <Button size="sm" variant="ghost" onClick={handleResetBot} disabled={busy !== null}>
              {busy === "resetBot" ? <LoaderCircle className="size-4 animate-spin" /> : <RotateCcw className="size-4" />}
              Use default bot
            </Button>
          )}
        </div>

        {link && (
          <div className="grid gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-xs">
            <p className="font-medium text-foreground">
              Waiting for you to press <strong>Start</strong> in {link.bot_username}…
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" asChild>
                <a href={link.url} target="_blank" rel="noopener noreferrer">
                  Open {link.bot_username} <ExternalLink className="size-3.5" />
                </a>
              </Button>
              <Button size="sm" onClick={() => checkOnce(false)} disabled={busy !== null}>
                {busy === "confirm" ? <LoaderCircle className="size-3.5 animate-spin" /> : null}
                I&apos;ve pressed Start
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => { stopPolling(); setLink(null); }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {showNameForm && (
          <div className="grid gap-2 rounded-md border border-border bg-background/50 p-3">
            <Label htmlFor="ucf-TG_BOT_NAME" className="text-xs font-medium">
              Telegram bot display name
            </Label>
            <p className="text-xs text-muted-foreground">
              Enter a new display name for your Telegram bot (1–64 characters).
            </p>
            <div className="flex flex-wrap gap-2">
              <Input
                id="ucf-TG_BOT_NAME"
                type="text"
                placeholder="e.g. My Content Assistant"
                value={botNameInput}
                onChange={(e) => setBotNameInput(e.target.value)}
                disabled={busy !== null}
                maxLength={64}
                autoComplete="off"
                className="min-w-[14rem] flex-1 text-sm"
              />
              <Button size="sm" onClick={handleSaveBotName} disabled={busy !== null || !botNameInput.trim()}>
                {busy === "name" ? <LoaderCircle className="size-4 animate-spin" /> : null}
                Save name
              </Button>
              <Button size="sm" variant="ghost" onClick={handleCancelNameForm} disabled={busy !== null}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {showBotForm && (
          <div className="grid gap-2 rounded-md border border-border bg-background/50 p-3">
            <Label htmlFor="ucf-TG_BOT_TOKEN" className="text-xs font-medium">
              Custom BotFather token (optional)
            </Label>
            <p className="text-xs text-muted-foreground">
              Paste a token from @BotFather to use your own bot instead of Mintly&apos;s default bot, then reconnect your chat.
            </p>
            <div className="flex flex-wrap gap-2">
              <Input
                id="ucf-TG_BOT_TOKEN"
                type="password"
                placeholder="123456789:AA..."
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                disabled={busy !== null}
                autoComplete="off"
                spellCheck={false}
                autoCapitalize="none"
                data-1p-ignore
                data-lpignore="true"
                className="min-w-[14rem] flex-1 font-mono text-sm"
              />
              <Button size="sm" onClick={handleSaveCustomBot} disabled={busy !== null || !botToken.trim()}>
                {busy === "bot" ? "Verifying…" : "Save custom bot"}
              </Button>
            </div>
          </div>
        )}

        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer hover:text-foreground">Or enter Chat ID manually (e.g. for a group)</summary>
          <div className="mt-2 flex flex-wrap gap-2">
            <Input
              id="ucf-TG_CHAT_ID"
              type="text"
              placeholder={chatStatus?.set ? `Current: ${chatStatus.masked ?? "set"}` : "123456789 (a group starts with -)"}
              value={manualChatId}
              onChange={(e) => setManualChatId(e.target.value)}
              disabled={busy !== null}
              autoComplete="off"
              spellCheck={false}
              className="min-w-[12rem] flex-1 font-mono text-sm"
            />
            <Button size="sm" variant="outline" onClick={handleManualSave} disabled={busy !== null || !manualChatId.trim()}>
              {busy === "manual" ? "Saving…" : "Save Chat ID"}
            </Button>
          </div>
        </details>

        {error && <p className="text-xs text-bad">{error}</p>}
      </CardContent>

      <ConnectBotDialog
        open={showConnectBotDialog}
        onOpenChange={setShowConnectBotDialog}
        initialBotName={meta?.bot_name && !meta.bot_name.toLowerCase().includes("codexonebyhitesh") ? meta.bot_name : ""}
        onConfirm={handleConfirmConnect}
        isConnecting={busy === "link"}
      />
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------
// One section (e.g. Instagram) with a set of fields and a single Save button
// ------------------------------------------------------------------------------------------------
type SectionField = { key: string; label: string; secret: boolean; placeholder: string; choices?: string[] };

function IntegrationSection({
  title,
  fields,
  statuses,
  onSaved,
}: {
  title: string;
  fields: SectionField[];
  statuses: Record<string, KeyStatus>;
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const toSave = Object.entries(values).filter(([, v]) => v.trim().length > 0);
    if (!toSave.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const [key, value] of toSave) {
        await putUserIntegration(key, value.trim());
      }
      setValues({});
      onSaved();
      toast.success(`${title} saved`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const dirty = fields.some((f) => (values[f.key] ?? "").trim().length > 0);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {fields.map((f) => {
          const st = statuses[f.key];
          return (
            <div key={f.key} className="grid gap-1.5">
              <div className="flex items-center gap-2">
                <Label htmlFor={`ucf-${f.key}`} className="text-sm font-medium">
                  {f.label}
                </Label>
                {st?.set ? (
                  <span className="inline-flex items-center gap-1 text-xs text-ok">
                    <Check className="size-3" aria-hidden />
                    Set{st.masked ? ` · ${st.masked}` : ""}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <CircleDashed className="size-3" aria-hidden />
                    Not set
                  </span>
                )}
              </div>
              {f.choices ? (
                <select
                  id={`ucf-${f.key}`}
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  disabled={busy}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <option value="" className="bg-popover text-popover-foreground">
                    {st?.set ? `Current: ${st.masked ?? "set"}` : `Select ${f.label.toLowerCase()} (default: ${f.placeholder})`}
                  </option>
                  {f.choices.map((c) => (
                    <option key={c} value={c} className="bg-popover text-popover-foreground">
                      {c}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  id={`ucf-${f.key}`}
                  type={f.secret ? "password" : "text"}
                  placeholder={st?.set ? "Enter a new value to replace" : f.placeholder}
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  disabled={busy}
                  autoComplete="off"
                  spellCheck={false}
                  autoCapitalize="none"
                  data-1p-ignore
                  data-lpignore="true"
                  className="font-mono text-sm"
                />
              )}
            </div>
          );
        })}
        {error && <p className="text-xs text-bad">{error}</p>}
        <Button size="sm" onClick={handleSave} disabled={busy || !dirty} className="w-fit">
          {busy ? "Saving…" : `Save ${title}`}
        </Button>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------
// Full component
function CustomFieldEditor({
  keyName,
  label,
  placeholder,
  secret = false,
  status,
  onSaved,
}: {
  keyName: string;
  label: string;
  placeholder: string;
  secret?: boolean;
  status?: KeyStatus;
  onSaved: () => void;
}) {
  const [val, setVal] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!val.trim()) return;
    setSaving(true);
    try {
      await putUserIntegration(keyName, val.trim());
      setVal("");
      onSaved();
      toast.success(`${label} saved`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setSaving(true);
    try {
      await deleteUserIntegration(keyName);
      onSaved();
      toast.success(`${label} removed`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to delete.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">{label}</span>
        {status?.set ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-ok">
            <Check className="size-3" />
            Set{status.masked ? ` (${status.masked})` : ""}
          </span>
        ) : (
          <span className="text-[11px] text-muted-foreground">Not set</span>
        )}
      </div>
      <div className="flex gap-2">
        <Input
          type={secret ? "password" : "text"}
          placeholder={status?.set ? "Enter a new value to replace" : placeholder}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          disabled={saving}
          autoComplete="off"
          className="h-8 font-mono text-xs"
        />
        <Button size="sm" variant="outline" className="h-8 text-xs shrink-0" onClick={handleSave} disabled={saving || !val.trim()}>
          {saving ? "…" : "Save"}
        </Button>
        {status?.set && (
          <Button size="sm" variant="ghost" className="h-8 text-xs text-bad hover:bg-bad/10" onClick={handleDelete} disabled={saving}>
            Remove
          </Button>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------
// YouTube 1-Click Connect + Disconnect + Channel Display
// ------------------------------------------------------------------------------------------------
function YouTubeSection({
  statuses,
  meta,
  onSaved,
}: {
  statuses: Record<string, KeyStatus>;
  meta?: YouTubeMeta;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState<null | "link" | "unlink" | "privacy">(null);
  const [error, setError] = useState<string | null>(null);
  const [privacy, setPrivacy] = useState(meta?.privacy || "public");

  const connected = Boolean(meta?.connected || statuses.YT_REFRESH_TOKEN?.set);

  useEffect(() => {
    if (meta?.privacy) setPrivacy(meta.privacy);
  }, [meta?.privacy]);

  async function handleConnect() {
    setBusy("link");
    setError(null);
    try {
      const res = await createYouTubeLink();
      window.location.href = res.url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not initialize YouTube connection.");
      setBusy(null);
    }
  }

  async function handleUnlink() {
    setBusy("unlink");
    setError(null);
    try {
      await unlinkYouTube();
      onSaved();
      toast.success("YouTube channel disconnected");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not disconnect YouTube.");
    } finally {
      setBusy(null);
    }
  }

  async function handlePrivacyChange(newPrivacy: string) {
    setPrivacy(newPrivacy);
    setBusy("privacy");
    try {
      await putUserIntegration("YT_PRIVACY", newPrivacy);
      onSaved();
      toast.success(`YouTube upload privacy set to ${newPrivacy}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update privacy setting.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="overflow-hidden border-border/80">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 items-center justify-center rounded-lg bg-red-600/10 text-red-600 dark:bg-red-600/20 dark:text-red-400">
              <YouTubeIcon className="size-5" />
            </div>
            <div>
              <CardTitle className="text-base font-semibold">YouTube Shorts</CardTitle>
              <p className="text-xs text-muted-foreground">
                Auto-publish approved 20–25s videos directly to your YouTube channel as Shorts.
              </p>
            </div>
          </div>
          {connected ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-500 dark:text-emerald-400">
              <Check className="size-3.5" />
              Connected
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <CircleDashed className="size-3.5" />
              Not connected
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 pt-1">
        {connected ? (
          <div className="grid gap-4 rounded-xl border border-border/70 bg-card/60 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                {meta?.channel_thumb ? (
                  <img
                    src={meta.channel_thumb}
                    alt={meta.channel_title || "YouTube Channel"}
                    className="size-11 rounded-full border border-border object-cover"
                  />
                ) : (
                  <div className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <YouTubeIcon className="size-5" />
                  </div>
                )}
                <div>
                  <h4 className="text-sm font-semibold text-foreground">
                    {meta?.channel_title || "Connected YouTube Channel"}
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    {meta?.channel_handle || meta?.channel_id || "Ready to publish Shorts"}
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleUnlink}
                disabled={busy !== null}
                className="text-xs text-bad hover:bg-bad/10 hover:text-bad"
              >
                {busy === "unlink" ? (
                  <>
                    <LoaderCircle className="mr-1.5 size-3.5 animate-spin" />
                    Disconnecting…
                  </>
                ) : (
                  <>
                    <Unlink className="mr-1.5 size-3.5" />
                    Disconnect
                  </>
                )}
              </Button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-3">
              <div>
                <Label htmlFor="yt-privacy-select" className="text-xs font-medium">
                  Upload Privacy
                </Label>
                <p className="text-[11px] text-muted-foreground">
                  Controls whether uploaded Shorts are immediately visible to everyone.
                </p>
              </div>
              <select
                id="yt-privacy-select"
                value={privacy}
                onChange={(e) => handlePrivacyChange(e.target.value)}
                disabled={busy !== null}
                className="h-8 rounded-md border border-input bg-background px-2.5 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
              >
                <option value="public">Public (Recommended for Shorts)</option>
                <option value="unlisted">Unlisted</option>
                <option value="private">Private</option>
              </select>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3 rounded-xl border border-dashed border-border/80 bg-muted/20 p-5 text-center sm:text-left">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h4 className="text-sm font-semibold text-foreground">Link your YouTube channel in 1 click</h4>
                <p className="mt-0.5 max-w-prose text-xs text-muted-foreground">
                  Authorize Mintly to upload approved videos to your YouTube channel as Shorts. No Google Cloud Console or developer keys required.
                </p>
              </div>
              <Button
                size="sm"
                onClick={handleConnect}
                disabled={busy !== null}
                className="shrink-0 bg-red-600 text-white hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
              >
                {busy === "link" ? (
                  <>
                    <LoaderCircle className="mr-1.5 size-3.5 animate-spin" />
                    Opening Google…
                  </>
                ) : (
                  <>
                    <YouTubeIcon className="mr-1.5 size-4" />
                    Connect YouTube
                  </>
                )}
              </Button>
            </div>
          </div>
        )}

        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer hover:text-foreground">
            Advanced: Enter custom Google Cloud credentials
          </summary>
          <div className="mt-3 grid gap-3 rounded-lg border border-border/60 bg-muted/20 p-3.5">
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              If your organization uses its own dedicated Google Cloud OAuth Client ID, you can override the central platform credentials here.
            </p>
            <CustomFieldEditor
              keyName="YT_CLIENT_ID"
              label="Custom OAuth Client ID"
              placeholder="....apps.googleusercontent.com"
              status={statuses.YT_CLIENT_ID}
              onSaved={onSaved}
            />
            <CustomFieldEditor
              keyName="YT_CLIENT_SECRET"
              label="Custom OAuth Client Secret"
              placeholder="GOCSPX-..."
              secret
              status={statuses.YT_CLIENT_SECRET}
              onSaved={onSaved}
            />
          </div>
        </details>

        {error && <p className="text-xs text-bad">{error}</p>}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------
// Full component
// ------------------------------------------------------------------------------------------------
const INSTAGRAM_FIELDS: SectionField[] = [
  { key: "IG_USER_ID", label: "Instagram user ID", secret: false, placeholder: "17841400000000000" },
  { key: "IG_ACCESS_TOKEN", label: "Access token", secret: true, placeholder: "a long token from the Meta App Dashboard" },
];

export function UserIntegrations() {
  const [statuses, setStatuses] = useState<Record<string, KeyStatus>>({});
  const [tgMeta, setTgMeta] = useState<TelegramMeta | undefined>(undefined);
  const [ytMeta, setYtMeta] = useState<YouTubeMeta | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(() => {
    getUserIntegrations()
      .then((r) => {
        setStatuses(r.values);
        setTgMeta(r.telegram);
        setYtMeta(r.youtube);
        setLoadError(null);
      })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Couldn't load integration status."));
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "youtube") {
      toast.success("YouTube channel connected!", {
        description: "Your channel is now ready for auto-publishing approved YouTube Shorts.",
      });
      load();
      params.delete("connected");
      const next = window.location.pathname + (params.toString() ? `?${params}` : "");
      window.history.replaceState({}, "", next);
    } else if (params.get("error")?.startsWith("youtube")) {
      const err = params.get("error") || "";
      const msg = err.includes("no_youtube_channel")
        ? "No YouTube channel found on this Google account. Please create a channel on youtube.com first."
        : "YouTube connection was cancelled or rejected. Please try again.";
      toast.error("Could not connect YouTube", { description: msg });
      params.delete("error");
      const next = window.location.pathname + (params.toString() ? `?${params}` : "");
      window.history.replaceState({}, "", next);
    }
  }, [load]);

  return (
    <div className="grid gap-6">
      <div>
        <p className="label-mono">My Integrations</p>
        <h2 className="mt-1 font-heading text-2xl font-semibold tracking-tight">Your publishing accounts</h2>
        <p className="mt-2 max-w-prose text-sm text-muted-foreground">
          Connect your Telegram chat, Instagram account, and YouTube channel. These are stored securely and used only for your content.
        </p>
      </div>
      {loadError && <p className="rounded-md border border-bad/40 bg-bad/10 p-4 text-sm text-bad">{loadError}</p>}
      <TelegramSection statuses={statuses} meta={tgMeta} onSaved={load} />
      <IntegrationSection title="Instagram" fields={INSTAGRAM_FIELDS} statuses={statuses} onSaved={load} />
      <YouTubeSection statuses={statuses} meta={ytMeta} onSaved={load} />
    </div>
  );
}
