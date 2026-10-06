import { Ban, Check, CircleSlash, LoaderCircle, Minus, TriangleAlert, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { PHASES, STATUS_LABEL, phaseSentence, stepStates, type Job, type JobStatus, type StepState } from "@/lib/generate-format";

const BAR: Record<StepState, string> = {
  done: "bg-primary",
  current: "bg-primary animate-pulse motion-reduce:animate-none",
  failed: "bg-bad",
  skipped: "bg-muted-foreground/25",
  todo: "bg-border",
};

const STATE_WORD: Record<StepState, string> = {
  done: "done", current: "in progress", failed: "stopped here", skipped: "not needed", todo: "waiting",
};

const BADGE: Record<JobStatus, string> = {
  queued: "bg-wait/10 text-wait border-wait/35",
  running: "bg-go/10 text-go border-go/35",
  succeeded: "bg-ok/10 text-ok border-ok/35",
  failed: "bg-bad/10 text-bad border-bad/40",
  skipped: "bg-muted text-muted-foreground border-border",
  cancelled: "bg-muted text-muted-foreground border-border",
};

const ICON: Record<JobStatus, typeof Check> = {
  queued: LoaderCircle, running: LoaderCircle, succeeded: Check, failed: TriangleAlert, skipped: CircleSlash, cancelled: Ban,
};

/** Status as an icon + word (never colour alone), in StatusBadge's squared-tag shape. */
export function JobStatusBadge({ status, className }: { status: JobStatus; className?: string }) {
  const Icon = ICON[status];
  const spin = status === "queued" || status === "running";
  return (
    <span className={cn("inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-[4px] border px-1.5 text-[11px] leading-none font-medium", BADGE[status], className)}>
      <Icon className={cn("size-3", spin && "animate-spin motion-reduce:animate-none")} aria-hidden />
      {STATUS_LABEL[status]}
    </span>
  );
}

/**
 * The run's seven phases as one segmented bar. Phone: the bar plus the current phase in words (no labels
 * to squeeze). Wider: every phase is labelled under its segment. The sentence below is a polite live region,
 * so a screen reader hears each phase change.
 */
export function PhaseTrack({ job }: { job: Job }) {
  const states = stepStates(job);
  const sentence = phaseSentence(job);
  const bad = job.status === "failed" || job.status === "cancelled";
  return (
    <div className="grid gap-2">
      <ol className="grid grid-cols-7 gap-1" aria-label="Pipeline phases">
        {PHASES.map((p, i) => (
          <li key={p.key} className="grid min-w-0 gap-1.5" aria-current={states[i] === "current" ? "step" : undefined}>
            <span className={cn("h-1.5 rounded-full transition-colors", BAR[states[i]])} aria-hidden />
            <span className={cn(
              "hidden items-center gap-1 truncate text-[11px] leading-none sm:flex",
              states[i] === "current" ? "font-medium text-primary" : states[i] === "failed" ? "font-medium text-bad" : "text-muted-foreground",
              states[i] === "skipped" && "line-through decoration-muted-foreground/40",
            )}>
              {states[i] === "done" ? <Check className="size-3 shrink-0" aria-hidden />
                : states[i] === "failed" ? <X className="size-3 shrink-0" aria-hidden />
                : states[i] === "skipped" ? <Minus className="size-3 shrink-0" aria-hidden /> : null}
              <span className="truncate">{p.label}</span>
            </span>
            <span className="sr-only">{p.verb}: {STATE_WORD[states[i]]}</span>
          </li>
        ))}
      </ol>
      {/* Failed / skipped runs explain themselves in the tracker's reason box, so the sentence is announced, not repeated. */}
      <p aria-live="polite" className={cn("text-sm", bad || job.status === "skipped" ? "sr-only" : job.status === "running" ? "text-primary" : "text-muted-foreground")}>
        {sentence}
      </p>
    </div>
  );
}
