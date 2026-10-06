import { LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { STATUS_LABEL, type Status } from "@/lib/posts";

/** Status tag: a squared tag with a signal dot, coloured by role (docs/design/design-system.md "Status colours"). */
const STYLE: Record<Status, { tag: string; dot: string }> = {
  pending: { tag: "text-wait border-wait/35 bg-wait/10", dot: "bg-wait" },
  approved: { tag: "text-go border-go/35 bg-go/10", dot: "bg-go" },
  publishing: { tag: "text-go border-go/35 bg-go/10", dot: "bg-go" },
  published: { tag: "text-ok border-ok/35 bg-ok/10", dot: "bg-ok" },
  failed: { tag: "text-bad border-bad/40 bg-bad/10", dot: "bg-bad" },
  regenerate: { tag: "text-ai border-ai/35 bg-ai/10", dot: "bg-ai" },
  rejected: { tag: "text-muted-foreground border-border", dot: "bg-muted-foreground/60" },
  replaced: { tag: "text-muted-foreground border-border", dot: "bg-muted-foreground/60" },
  expired: { tag: "text-muted-foreground border-border", dot: "bg-muted-foreground/60" },
};

export function StatusBadge({ status, short = false, className }: { status: Status; short?: boolean; className?: string }) {
  const busy = status === "publishing" || status === "regenerate";
  const label = short ? status.charAt(0).toUpperCase() + status.slice(1) : STATUS_LABEL[status];
  const s = STYLE[status];
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-1.5 text-[11px] leading-none font-medium",
        s.tag,
        className,
      )}
    >
      {busy ? <LoaderCircle className="size-3 animate-spin" aria-hidden /> : <span aria-hidden className={cn("size-1.5 rounded-[1px]", s.dot)} />}
      {label}
    </span>
  );
}
