import { cn } from "@/lib/utils";

/** The brand mark used on slides and reels: a gradient tile with </>. */
export function Logo({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        "grid size-10 shrink-0 place-items-center rounded-xl font-mono text-sm font-bold text-primary-foreground",
        "bg-[linear-gradient(135deg,var(--brand-primary),color-mix(in_srgb,var(--brand-primary)_50%,var(--brand-accent)))]",
        className,
      )}
    >
      &lt;/&gt;
    </div>
  );
}
