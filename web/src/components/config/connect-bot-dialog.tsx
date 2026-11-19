import { useEffect, useState } from "react";
import { Bot, LoaderCircle, Send } from "lucide-react";

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

export function ConnectBotDialog({
  open,
  onOpenChange,
  initialBotName = "CodeXone Assistant",
  onConfirm,
  isConnecting = false,
}: ConnectBotDialogProps) {
  const [name, setName] = useState(initialBotName);

  useEffect(() => {
    if (open) {
      setName(initialBotName || "CodeXone Assistant");
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
            <DialogTitle>Name Your Telegram Chatbot</DialogTitle>
            <DialogDescription>
              Choose a display name for your AI assistant bot on Telegram before connecting. You can customize this anytime.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-2 py-2">
            <Label htmlFor="chatbot-name-input" className="text-xs font-medium">
              Chatbot Name
            </Label>
            <Input
              id="chatbot-name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. CodeXone Assistant"
              maxLength={64}
              disabled={isConnecting}
              autoFocus
              className="text-sm"
            />
            <p className="text-[11px] text-muted-foreground">
              Maximum 64 characters. This name will appear on your bot profile and conversations.
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
