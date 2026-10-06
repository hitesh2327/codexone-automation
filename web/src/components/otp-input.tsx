import { useRef } from "react";

import { cn } from "@/lib/utils";

/**
 * Six boxes for the emailed code. Type, paste the whole thing, or use backspace/arrow keys.
 * One-time-code autofill (iOS/Android keyboards) works because the first box declares it.
 */
export function OtpInput({
  value, onChange, onComplete, disabled, invalid, autoFocus = true, label = "6-digit code",
}: {
  value: string; onChange: (v: string) => void; onComplete?: (v: string) => void;
  disabled?: boolean; invalid?: boolean; autoFocus?: boolean; label?: string;
}) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length: 6 }, (_, i) => value[i] ?? "");

  function commit(next: string, focusAt: number) {
    const clean = next.replace(/\D/g, "").slice(0, 6);
    onChange(clean);
    refs.current[Math.min(focusAt, 5)]?.focus();
    if (clean.length === 6) onComplete?.(clean);
  }

  return (
    <div role="group" aria-label={label} className="flex gap-2 sm:gap-2.5">
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          value={d}
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          autoComplete={i === 0 ? "one-time-code" : "off"}
          autoFocus={autoFocus && i === 0}
          disabled={disabled}
          aria-label={`${label}, digit ${i + 1}`}
          aria-invalid={invalid || undefined}
          onFocus={(e) => e.target.select()}
          onChange={(e) => {
            const v = e.target.value.replace(/\D/g, "");
            if (!v) return;
            const next = (value.slice(0, i) + v + value.slice(i + 1)).slice(0, 6);
            commit(next, i + v.length);
          }}
          onPaste={(e) => {
            e.preventDefault();
            const pasted = e.clipboardData.getData("text").replace(/\D/g, "");
            if (pasted) commit(pasted, pasted.length);
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace") {
              e.preventDefault();
              if (d) commit(value.slice(0, i) + value.slice(i + 1), i);
              else if (i > 0) commit(value.slice(0, i - 1) + value.slice(i), i - 1);
            } else if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
            else if (e.key === "ArrowRight" && i < 5) refs.current[i + 1]?.focus();
          }}
          className={cn(
            "h-14 w-full min-w-0 border-0 border-b-2 bg-transparent text-center font-mono text-2xl font-semibold tabular-nums outline-none transition-colors",
            "border-input focus:border-[var(--brand-accent)] focus:bg-[color-mix(in_srgb,var(--brand-accent)_8%,transparent)]",
            d && "border-foreground/60",
            invalid && "border-destructive text-destructive",
            "disabled:opacity-50",
          )}
        />
      ))}
    </div>
  );
}
