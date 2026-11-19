import { useEffect, useState } from "react";
import { Bot, LoaderCircle, Send, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConnectBotDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialBotName?: string;
  onConfirm: (botName: string) => Promise<void> | void;
  isConnecting?: boolean;
}

function sanitizeInitialName(raw?: string): string {
  if (!raw) return "";
  const lower = raw.toLowerCase().trim();
  // Strip hardcoded legacy or default internal names so user is always asked for their own name
  if (lower.includes("codexonebyhitesh") || lower === "codexone assistant") {
    return "";
  }
  return raw.trim();
}

export function ConnectBotDialog({
  open,
  onOpenChange,
  initialBotName = "",
  onConfirm,
  isConnecting = false,
}: ConnectBotDialogProps) {
  const [name, setName] = useState(() => sanitizeInitialName(initialBotName));

  useEffect(() => {
    if (open) {
      setName(sanitizeInitialName(initialBotName));
    }
  }, [open, initialBotName]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = name.trim();
    if (!clean || isConnecting) return;
    onConfirm(clean);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-[var(--brand-accent)]/15 text-[var(--brand-accent)]">
              <Bot className="size-5" />
            </div>
            <DialogTitle className="text-base font-semibold">Name Your Telegram Bot</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              What would you like your AI assistant bot to be called in Telegram?
              Telegram will display this as your bot&apos;s name when you connect.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-2 py-2">
            <Label htmlFor="chatbot-name-input" className="text-xs font-medium">
              Bot Name <span className="text-[var(--brand-accent)]">*</span>
            </Label>
            <Input
              id="chatbot-name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. My Content Assistant"
              maxLength={64}
              disabled={isConnecting}
              autoFocus
              className="text-sm"
              required
            />
            <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <Sparkles className="size-3 text-[var(--brand-accent)] shrink-0" />
              1–64 characters. This name will appear on your bot profile and Telegram chats.
            </p>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={isConnecting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isConnecting || !name.trim()}
              className="gap-2"
            >
              {isConnecting ? (
                <>
                  <LoaderCircle className="size-4 animate-spin" />
                  Connecting…
                </>
              ) : (
                <>
                  <Send className="size-4" />
                  Connect to Telegram
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
