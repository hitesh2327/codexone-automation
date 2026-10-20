import type { ReactNode } from "react";

import { Logo, Wordmark } from "@/components/logo";

/** The leaf from the logo, drawn large and faint behind the editorial panel. */
function Leaf({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" aria-hidden className={className}>
      <path d="M12 108 C12 52 58 12 108 12 C108 68 68 108 12 108 Z" fill="currentColor" />
      <path d="M26 94 L94 26" stroke="var(--brand-bg)" strokeWidth="0.8" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/**
 * Shared frame for the signed-out screens, in Mintly's own palette (.mintly, index.css) rather than the
 * channel brand: an editorial panel on the left (a mint-ruled grid, a big statement, something specific
 * to the screen) and the actual form, with no card around it, on the right.
 */
export function AuthStage({ handle, aside, children }: { handle?: string; aside: ReactNode; children: ReactNode }) {
  return (
    <div className="mintly min-h-dvh lg:grid lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <aside className="relative hidden overflow-hidden border-r bg-[color-mix(in_srgb,var(--mint)_3%,var(--brand-bg))] lg:flex lg:flex-col lg:justify-between lg:p-12">
        {/* ruled paper in mint, fading toward the corner the text sits in */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 [background-image:linear-gradient(color-mix(in_srgb,var(--mint)_10%,transparent)_1px,transparent_1px),linear-gradient(90deg,color-mix(in_srgb,var(--mint)_10%,transparent)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(120%_90%_at_0%_0%,black,transparent_70%)]"
        />
        <Leaf className="pointer-events-none absolute -right-28 -bottom-32 size-[36rem] text-[var(--mint)] opacity-[0.07]" />
        <div className="relative flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Logo className="size-10" />
            <Wordmark className="text-2xl" />
          </div>
          {handle && <span className="font-mono text-xs tracking-[0.14em] text-muted-foreground">{handle}</span>}
        </div>
        <div className="relative">{aside}</div>
      </aside>

      <main className="grid min-h-dvh place-items-center px-5 py-10 lg:min-h-0">
        <div className="w-full max-w-[22rem]">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <Logo className="size-9" />
            <Wordmark className="text-xl" />
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

export function Label2({ htmlFor, children, right }: { htmlFor?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <label htmlFor={htmlFor} className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{children}</label>
      {right}
    </div>
  );
}
