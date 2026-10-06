import { cn } from "@/lib/utils";
import { STAGES, type Stage, type Tone } from "@/lib/stage";

const FILL: Record<Tone, string> = {
  wait: "bg-wait",
  go: "bg-go",
  ok: "bg-ok",
  bad: "bg-bad",
  idle: "bg-muted-foreground/50",
};

const TEXT: Record<Tone, string> = {
  wait: "text-wait",
  go: "text-go",
  ok: "text-ok",
  bad: "text-bad",
  idle: "text-muted-foreground",
};

/**
 * A four-segment rail (Approval → Scheduled → Publishing → Live): reached segments fill in the stage's
 * colour, the current one is full height, the rest are hairlines. Off-path states (rejected, expired,
 * regenerating) show an empty rail. Then the stage name and one line of "what happens next".
 */
export function ProgressTrack({ stage, compact = false }: { stage: Stage; compact?: boolean }) {
  const { step, tone } = stage;
  return (
    <div className="grid min-w-0 gap-1.5" role="group" aria-label={`${stage.title}. ${stage.note}`}>
      <ol className="flex h-1.5 items-center gap-[3px]" aria-hidden>
        {STAGES.map((name, i) => {
          const reached = step >= 0 && i <= step;
          const current = i === step;
          return (
            <li
              key={name}
              title={name}
              className={cn(
                "w-5 rounded-[1px] transition-[height,background-color] duration-(--dur-base)",
                current ? "h-1.5" : "h-[3px]",
                reached ? FILL[tone] : "bg-border",
                reached && !current && tone !== "bad" && "opacity-55",
              )}
            />
          );
        })}
      </ol>
      <div className="grid gap-0.5">
        <p className={cn("text-[13px] leading-tight font-medium", TEXT[tone])}>{stage.title}</p>
        {!compact && <p className="text-xs leading-snug text-muted-foreground">{stage.note}</p>}
      </div>
    </div>
  );
}
