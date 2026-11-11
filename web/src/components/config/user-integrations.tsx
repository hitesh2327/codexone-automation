/**
 * Per-user integration settings: Telegram 1-click connect/unlink/bot override, Instagram, YouTube.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Check, CircleDashed, ExternalLink, LoaderCircle, Pencil, RotateCcw, Send, Unlink } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  confirmTelegramLink, createTelegramLink, deleteUserIntegration, getUserIntegrations, putUserIntegration,
  setCustomTelegramBot, setTelegramBotName, unlinkTelegram, type KeyStatus, type TelegramLinkResponse, type TelegramMeta,
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

  async function handleConnect() {
    setBusy("link");
    setError(null);
    stopPolling();
    try {
      const res = await createTelegramLink();
      setLink(res);
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
            Bot: {meta?.bot_name || "codeXoneByHitesh"} ({meta?.bot_username || "@codeXoneByHiteshBot"})
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
                placeholder={meta?.bot_name || "codeXoneByHitesh"}
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
// ------------------------------------------------------------------------------------------------
const INSTAGRAM_FIELDS: SectionField[] = [
  { key: "IG_USER_ID", label: "Instagram user ID", secret: false, placeholder: "17841400000000000" },
  { key: "IG_ACCESS_TOKEN", label: "Access token", secret: true, placeholder: "a long token from the Meta App Dashboard" },
];

const YOUTUBE_FIELDS: SectionField[] = [
  { key: "YT_CLIENT_ID", label: "OAuth client ID", secret: false, placeholder: "....apps.googleusercontent.com" },
  { key: "YT_CLIENT_SECRET", label: "OAuth client secret", secret: true, placeholder: "GOCSPX-..." },
  { key: "YT_REFRESH_TOKEN", label: "Refresh token", secret: true, placeholder: "1//..." },
  { key: "YT_PRIVACY", label: "Upload privacy", secret: false, placeholder: "public", choices: ["public", "unlisted", "private"] },
];

export function UserIntegrations() {
  const [statuses, setStatuses] = useState<Record<string, KeyStatus>>({});
  const [tgMeta, setTgMeta] = useState<TelegramMeta | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(() => {
    getUserIntegrations()
      .then((r) => { setStatuses(r.values); setTgMeta(r.telegram); setLoadError(null); })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Couldn't load integration status."));
  }, []);

  useEffect(() => { load(); }, [load]);

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
      <IntegrationSection title="YouTube" fields={YOUTUBE_FIELDS} statuses={statuses} onSaved={load} />
    </div>
  );
}
