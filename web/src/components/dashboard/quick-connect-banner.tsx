import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, Circle, ExternalLink, LoaderCircle, Send, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConnectBotDialog } from "@/components/config/connect-bot-dialog";
import { useAuth } from "@/lib/auth";
import { createTelegramLink, getUserIntegrations } from "@/lib/config";
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
  const [ytConnected, setYtConnected] = useState(false);
  const [busyTg, setBusyTg] = useState(false);
  const [botDialogOpen, setBotDialogOpen] = useState(false);

  const defaultBotName = user?.name ? `${user.name}'s Assistant` : "";

  const loadStatus = useCallback(async () => {
    try {
      const data = await getUserIntegrations();
      setTgConnected(Boolean(data.telegram?.connected || data.values?.TG_CHAT_ID?.set));
      setIgConnected(Boolean(data.values?.IG_USER_ID?.set && data.values?.IG_ACCESS_TOKEN?.set));
      setYtConnected(Boolean(data.values?.YOUTUBE_CLIENT_SECRET?.set));
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
                📸 Instagram
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
              Auto-publish 20–25s high-retention Reels &amp; carousels.
            </p>
          </div>
          <div className="mt-3">
            {igConnected ? (
              <span className="text-[11px] text-muted-foreground/70">Ready to publish</span>
            ) : (
              <Button asChild variant="outline" size="sm" className="w-full text-xs font-medium">
                <Link to="/config">
                  Connect Instagram
                  <ArrowRight className="ml-1 size-3" />
                </Link>
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
                🎥 YouTube
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
              Reach technical developers via YouTube Shorts feed.
            </p>
          </div>
          <div className="mt-3">
            {ytConnected ? (
              <span className="text-[11px] text-muted-foreground/70">Ready to publish</span>
            ) : (
              <Button asChild variant="outline" size="sm" className="w-full text-xs font-medium">
                <Link to="/config">
                  Connect YouTube
                  <ArrowRight className="ml-1 size-3" />
                </Link>
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
