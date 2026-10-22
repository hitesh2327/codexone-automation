import { Monitor, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTheme, type ThemePref } from "@/lib/theme";
import { cn } from "@/lib/utils";

const OPTIONS: { value: ThemePref; label: string; icon: typeof Sun; note: string }[] = [
  { value: "light", label: "Light", icon: Sun, note: "Always light. The default." },
  { value: "dark", label: "Dark", icon: Moon, note: "Always dark." },
  { value: "system", label: "System", icon: Monitor, note: "Follows your device, and changes when it does." },
];

/** Light / Dark / System as a segmented control (Profile > Appearance). */
export function ThemeSwitch() {
  const { pref, resolved, setPref } = useTheme();
  const current = OPTIONS.find((o) => o.value === pref)!;
  return (
    <div className="grid gap-3">
      <div role="radiogroup" aria-label="Theme" className="inline-flex w-fit rounded-xl bg-raised p-1 ring-1 ring-border">
        {OPTIONS.map((o) => {
          const on = o.value === pref;
          return (
            <button key={o.value} type="button" role="radio" aria-checked={on} onClick={() => setPref(o.value)}
              className={cn("inline-flex min-h-10 items-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors duration-(--dur-fast)",
                on ? "bg-background text-foreground ring-1 ring-border" : "text-muted-foreground hover:text-foreground")}>
              <o.icon className="size-4" aria-hidden />{o.label}
            </button>
          );
        })}
      </div>
      <p className="text-sm text-muted-foreground">
        {current.note}{pref === "system" && ` Right now that's ${resolved}.`} Saved in this browser.
      </p>
    </div>
  );
}

/** One-click switch between light and dark, for the sidebar. Picking here leaves System if it was on. */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolved, setPref } = useTheme();
  const next = resolved === "dark" ? "light" : "dark";
  return (
    <Button variant="ghost" size="icon" className={className} onClick={() => setPref(next)}
      aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      {resolved === "dark" ? <Sun /> : <Moon />}
    </Button>
  );
}
