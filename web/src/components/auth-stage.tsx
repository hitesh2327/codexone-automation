import type { ReactNode } from "react";

import { Logo } from "@/components/logo";

/**
 * Shared frame for the signed-out screens: an editorial panel on the left (a ruled grid, a big
 * statement, something specific to the screen) and the actual form, with no card around it, on the right.
 */
export function AuthStage({ handle, aside, children }: { handle?: string; aside: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <aside className="relative hidden overflow-hidden border-r bg-[color-mix(in_srgb,var(--brand-text)_2.5%,var(--brand-bg))] lg:flex lg:flex-col lg:justify-between lg:p-12">
        {/* ruled paper: a fine grid that fades toward the corner the text sits in */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-70 [background-image:linear-gradient(var(--border)_1px,transparent_1px),linear-gradient(90deg,var(--border)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(120%_90%_at_100%_0%,black,transparent_70%)]"
        />
        <span aria-hidden className="absolute top-0 right-12 h-28 w-1.5 bg-[var(--brand-accent)]" />
        <div className="relative flex items-center gap-3">
          <Logo className="size-9 text-xs" />
          <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">{handle ?? "codexone"}</span>
        </div>
        <div className="relative">{aside}</div>
      </aside>

      <main className="grid min-h-dvh place-items-center px-5 py-10 lg:min-h-0">
        <div className="w-full max-w-[22rem]">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <Logo className="size-9 text-xs" />
            <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">{handle ?? "codexone"}</span>
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
