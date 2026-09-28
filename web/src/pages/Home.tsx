import { useState } from "react";
import { LogOut } from "lucide-react";
import { toast } from "sonner";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";

// Signed-in shell. Phase 3+ replaces the placeholder with Posts, Generate, Accounts, Config, Logs.
export default function Home() {
  const { user, logout } = useAuth();
  const [busy, setBusy] = useState(false);

  async function onLogout() {
    setBusy(true);
    try {
      await logout();
    } catch {
      toast.error("Couldn't sign out. Please try again.");
      setBusy(false);
    }
  }

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <Logo className="size-8 text-xs" />
          <span className="font-heading font-semibold">Content admin</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden truncate text-sm text-muted-foreground sm:inline">
              {user?.name}
            </span>
            <Button variant="ghost" size="sm" onClick={onLogout} disabled={busy}>
              <LogOut />
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle className="font-heading">You're signed in</CardTitle>
            <CardDescription>
              Posts, Generate, Accounts, Config, Dashboard and Logs arrive in the next phases.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Signed in as <span className="text-foreground">{user?.username ?? user?.email}</span>.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
