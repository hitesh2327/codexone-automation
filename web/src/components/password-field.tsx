import { useId, useState } from "react";
import { Check, Eye, EyeOff } from "lucide-react";

import { Input } from "@/components/ui/input";
import { passwordChecks, passwordScore } from "@/lib/profile";
import { cn } from "@/lib/utils";

const LEVELS = ["Too short", "Weak", "Okay", "Good", "Strong"];
const COLORS = ["bg-border", "bg-destructive", "bg-wait", "bg-ok", "bg-ok"];

export function PasswordField({
  value, onChange, label, autoComplete = "new-password", meter = false, identity = [], disabled, autoFocus, error, id,
}: {
  value: string; onChange: (v: string) => void; label: string; autoComplete?: string; meter?: boolean;
  identity?: (string | null | undefined)[]; disabled?: boolean; autoFocus?: boolean; error?: string | null; id?: string;
}) {
  const auto = useId();
  const fieldId = id ?? auto;
  const [show, setShow] = useState(false);
  const score = passwordScore(value, ...identity);
  const checks = passwordChecks(value, ...identity);

  return (
    <div className="grid gap-2">
      <label htmlFor={fieldId} className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{label}</label>
      <div className="relative">
        <Input
          id={fieldId} type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete} disabled={disabled} autoFocus={autoFocus} aria-invalid={!!error || undefined}
          aria-describedby={meter ? `${fieldId}-rules` : undefined} className="h-11 pr-11"
        />
        <button
          type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}
          className="absolute top-1 right-1 grid size-9 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>

      {meter && (
        <div id={`${fieldId}-rules`} className="grid gap-2">
          <div className="flex items-center gap-2" aria-live="polite">
            <div className="flex flex-1 gap-1" aria-hidden>
              {[1, 2, 3, 4].map((n) => <span key={n} className={cn("h-1 flex-1 rounded-full transition-colors", score >= n ? COLORS[score] : "bg-border")} />)}
            </div>
            <span className="w-16 text-right text-xs text-muted-foreground">{value ? LEVELS[score] : ""}</span>
          </div>
          <ul className="grid gap-1 text-xs">
            {checks.map((c) => (
              <li key={c.id} className={cn("flex items-center gap-1.5", c.ok ? "text-ok" : "text-muted-foreground")}>
                <Check className={cn("size-3", c.ok ? "opacity-100" : "opacity-25")} aria-hidden />{c.label}
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

export const passwordAcceptable = (pw: string, ...identity: (string | null | undefined)[]) => passwordChecks(pw, ...identity).every((c) => c.ok);
