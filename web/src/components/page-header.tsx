import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The shared page header (docs/design/design-system.md "Page header"): a mono eyebrow with the page's
 * index from the sidebar, a large heading, one line of purpose, actions on the right, and a hairline
 * that the amber rule signs from the left. Pages add their own content below; this only sets the masthead.
 */
export function PageHeader({
  index, eyebrow, title, lead, meta, actions, className,
}: {
  index?: string;
  eyebrow?: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    // flex-wrap, not a 2-column grid: when the actions are wide (Dashboard's segmented controls) they drop below the
    // title instead of squeezing it to one word per line.
    <header className={cn("relative flex flex-wrap items-end gap-x-6 gap-y-3 border-b border-border pb-5", className)}>
      <div className="min-w-0 flex-[1_1_15rem]">
        {(index || eyebrow) && (
          <p className="label-mono mb-2.5 flex items-center gap-2">
            {index && <span className="text-signal tabular-nums">{index}</span>}
            {index && eyebrow && <span aria-hidden className="h-px w-4 bg-rule" />}
            {eyebrow}
          </p>
        )}
        <h1 className="font-heading text-[1.875rem] leading-[1.05] font-semibold tracking-tight sm:text-[2.375rem]">{title}</h1>
        {lead && <p className="mt-2 max-w-prose text-sm text-muted-foreground">{lead}</p>}
      </div>
      {(meta || actions) && (
        <div className="flex max-w-full flex-wrap items-center gap-x-3 gap-y-2">
          {meta}
          {actions}
        </div>
      )}
      <span aria-hidden className="amber-rule absolute -bottom-px left-0" />
    </header>
  );
}
