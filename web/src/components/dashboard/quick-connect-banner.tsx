import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, Circle, ExternalLink, LoaderCircle, Send, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

function YouTubeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
    </svg>
  );
}

function InstagramIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

import { Button } from "@/components/ui/button";
import { ConnectBotDialog } from "@/components/config/connect-bot-dialog";
import { useAuth } from "@/lib/auth";
import { createInstagramLink, createTelegramLink, createYouTubeLink, getUserIntegrations } from "@/lib/config";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "mintly_dismiss_quick_connect";

export function QuickConnectBanner() {
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });

  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [tgConnected, setTgConnected] = useState(false);
  const [igConnected, setIgConnected] = useState(false);
  const [igAccountInfo, setIgAccountInfo] = useState<string | null>(null);
  const [ytConnected, setYtConnected] = useState(false);
  const [ytChannelInfo, setYtChannelInfo] = useState<string | null>(null);
  const [busyTg, setBusyTg] = useState(false);
  const [busyIg, setBusyIg] = useState(false);
  const [busyYt, setBusyYt] = useState(false);
  const [botDialogOpen, setBotDialogOpen] = useState(false);

  const defaultBotName = user?.name ? `${user.name}'s Assistant` : "";

  const loadStatus = useCallback(async () => {
    try {
      const data = await getUserIntegrations();
      setTgConnected(Boolean(data.telegram?.connected || data.values?.TG_CHAT_ID?.set));
      const igIsConn = Boolean(data.instagram?.connected || (data.values?.IG_USER_ID?.set && data.values?.IG_ACCESS_TOKEN?.set));
      setIgConnected(igIsConn);
      if (igIsConn && data.instagram) {
        setIgAccountInfo(data.instagram.username || null);
      }
      const ytIsConn = Boolean(data.youtube?.connected || data.values?.YT_REFRESH_TOKEN?.set);
      setYtConnected(ytIsConn);
      if (ytIsConn && data.youtube) {
        setYtChannelInfo(data.youtube.channel_handle || data.youtube.channel_title || null);
      }
    } catch {
      // Non-critical background telemetry
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!dismissed) {
      loadStatus();
    }
  }, [dismissed, loadStatus]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "youtube") {
      toast.success("YouTube channel connected!", {
        description: "Your channel is ready for auto-publishing approved YouTube Shorts.",
      });
      loadStatus();
      params.delete("connected");
      const next = window.location.pathname + (params.toString() ? `?${params}` : "");
      window.history.replaceState({}, "", next);
    } else if (params.get("connected") === "instagram") {
      toast.success("Instagram account connected!", {
        description: "Your account is ready for auto-publishing approved reels and carousels.",
      });
      loadStatus();
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
    } else if (params.get("error")?.startsWith("instagram")) {
      const err = params.get("error") || "";
      const msg = err.includes("access_denied")
        ? "Instagram connection permission was declined. Please try again."
        : "Instagram connection could not be completed. Please try again.";
      toast.error("Could not connect Instagram", { description: msg });
      params.delete("error");
      const next = window.location.pathname + (params.toString() ? `?${params}` : "");
      window.history.replaceState({}, "", next);
    }
  }, [loadStatus]);

  const handleDismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // Ignored
    }
  };

  const handleOpenConnectDialog = () => {
    setBotDialogOpen(true);
  };

  const handleConfirmConnectBot = async (botName: string) => {
    setBusyTg(true);
    try {
      const res = await createTelegramLink(botName);
      setBotDialogOpen(false);
      window.open(res.url, "_blank", "noopener,noreferrer");
      toast.success("Opened Telegram! Tap 'Start' in the bot to link your account.", {
        description: `Your chatbot '${botName}' is ready to link.`,
      });
    } catch (err: any) {
      toast.error(err?.message || "Could not generate Telegram link. Please try again.");
    } finally {
      setBusyTg(false);
    }
  };

  if (dismissed || loading) return null;

  const connectedCount = [tgConnected, igConnected, ytConnected].filter(Boolean).length;
  // If all channels are connected, automatically hide the checklist
  if (connectedCount === 3) return null;

  return (
    <div className="relative mb-8 overflow-hidden rounded-2xl border border-[var(--brand-accent)]/30 bg-gradient-to-r from-card via-[color-mix(in_srgb,var(--brand-accent)_7%,var(--brand-bg))] to-card p-5 shadow-sm">
      <button
        type="button"
        onClick={handleDismiss}
        className="absolute top-4 right-4 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        title="Dismiss checklist"
        aria-label="Dismiss quick setup banner"
      >
        <X className="size-4" />
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="grid size-7 place-items-center rounded-lg bg-[var(--brand-accent)]/15 text-[var(--brand-accent)]">
            <Sparkles className="size-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              Quick Channel Setup · {connectedCount} of 3 Ready
            </h3>
            <p className="text-xs text-muted-foreground">
              Your smart strategy is live. Connect channels below whenever you want live automated publishing.
            </p>
          </div>
        </div>

        <Link
          to="/config"
          className="mr-6 flex items-center gap-1 text-xs font-medium text-[var(--brand-accent)] hover:underline"
        >
          Customize Strategy &amp; Keys
          <ArrowRight className="size-3.5" />
        </Link>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {/* Telegram 1-Click Card */}
        <div
          className={cn(
            "flex flex-col justify-between rounded-xl border p-3.5 transition-colors",
            tgConnected ? "border-emerald-500/20 bg-emerald-500/5" : "border-border/80 bg-background/60"
          )}
        >
          <div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Send className="size-3.5 text-sky-400" />
                Telegram Bot
              </span>
              {tgConnected ? (
                <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                  <CheckCircle2 className="size-3" /> Linked
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <Circle className="size-3" /> Not linked
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Get previews &amp; approve posts on your phone in 1 tap.
            </p>
          </div>
          <div className="mt-3">
            {tgConnected ? (
              <span className="text-[11px] text-muted-foreground/70">Ready for mobile approval taps</span>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={handleOpenConnectDialog}
                disabled={busyTg}
                className="w-full text-xs font-medium hover:border-sky-500/50 hover:text-sky-400"
              >
                {busyTg ? (
                  <LoaderCircle className="size-3.5 animate-spin" />
                ) : (
                  <>
                    Connect in 1 Click
                    <ExternalLink className="ml-1 size-3" />
                  </>
                )}
              </Button>
            )}
          </div>
        </div>

        {/* Instagram Card */}
        <div
          className={cn(
            "flex flex-col justify-between rounded-xl border p-3.5 transition-colors",
            igConnected ? "border-emerald-500/20 bg-emerald-500/5" : "border-border/80 bg-background/60"
          )}
        >
          <div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <InstagramIcon className="size-3.5 text-pink-500" />
                Instagram
              </span>
              {igConnected ? (
                <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                  <CheckCircle2 className="size-3" /> Connected
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <Circle className="size-3" /> Not connected
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {igConnected && igAccountInfo
                ? `Connected as @${igAccountInfo}. Auto-publishes approved Reels.`
                : "Auto-publish 20–25s high-retention Reels & carousels."}
            </p>
          </div>
          <div className="mt-3">
            {igConnected ? (
              <span className="text-[11px] text-muted-foreground/70">Ready to publish</span>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  setBusyIg(true);
                  try {
                    const res = await createInstagramLink();
                    window.location.href = res.url;
                  } catch (err: any) {
                    toast.error(err?.message || "Could not initialize Instagram connection.");
                    setBusyIg(false);
                  }
                }}
                disabled={busyIg}
                className="w-full text-xs font-medium hover:border-pink-500/40 hover:bg-pink-500/10 hover:text-pink-500"
              >
                {busyIg ? (
                  <>
                    <LoaderCircle className="mr-1.5 size-3.5 animate-spin" />
                    Opening Meta…
                  </>
                ) : (
                  <>
                    <InstagramIcon className="mr-1.5 size-3.5 text-pink-500" />
                    Connect Instagram
                  </>
                )}
              </Button>
            )}
          </div>
        </div>

        {/* YouTube Shorts Card */}
        <div
          className={cn(
            "flex flex-col justify-between rounded-xl border p-3.5 transition-colors",
            ytConnected ? "border-emerald-500/20 bg-emerald-500/5" : "border-border/80 bg-background/60"
          )}
        >
          <div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <YouTubeIcon className="size-3.5 text-red-500" /> YouTube
              </span>
              {ytConnected ? (
                <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                  <CheckCircle2 className="size-3" /> Connected
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <Circle className="size-3" /> Not connected
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {ytConnected && ytChannelInfo
                ? `Connected as ${ytChannelInfo}. Auto-publishes approved Shorts.`
                : "Reach technical developers via YouTube Shorts feed."}
            </p>
          </div>
          <div className="mt-3">
            {ytConnected ? (
              <span className="text-[11px] text-muted-foreground/70">Ready to publish</span>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  setBusyYt(true);
                  try {
                    const res = await createYouTubeLink();
                    window.location.href = res.url;
                  } catch (err: any) {
                    toast.error(err?.message || "Could not initialize YouTube connection.");
                    setBusyYt(false);
                  }
                }}
                disabled={busyYt}
                className="w-full text-xs font-medium hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-500"
              >
                {busyYt ? (
                  <>
                    <LoaderCircle className="mr-1.5 size-3.5 animate-spin" />
                    Opening Google…
                  </>
                ) : (
                  <>
                    <YouTubeIcon className="mr-1.5 size-3.5 text-red-500" />
                    Connect YouTube
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </div>

      <ConnectBotDialog
        open={botDialogOpen}
        onOpenChange={setBotDialogOpen}
        initialBotName={defaultBotName}
        onConfirm={handleConfirmConnectBot}
        isConnecting={busyTg}
      />
    </div>
  );
}
