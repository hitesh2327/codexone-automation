import { Link } from "react-router-dom";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { SLOT_LABEL, slotHint, type Slot, type SlotState } from "@/lib/generate-format";
import { type Status } from "@/lib/posts";

/** Ring + centre per state, the same light weight as the Posts rail. The state is also spelled out next to it. */
const DOT: Record<SlotState, { ring: string; core: string }> = {
  generated: { ring: "border-ok", core: "bg-ok-solid" },
  generating: { ring: "border-go", core: "bg-go motion-safe:animate-pulse" },
  failed: { ring: "border-bad", core: "bg-bad" },
  skipped: { ring: "border-border", core: "h-px w-[7px] rounded-none bg-muted-foreground" },
  upcoming: { ring: "border-rule", core: "" },
  late: { ring: "border-wait", core: "bg-wait" },
  stale: { ring: "border-wait border-dashed", core: "" },
};

const TEXT: Record<SlotState, string> = {
  generated: "text-ok",
  generating: "text-go",
  failed: "text-bad",
  skipped: "text-muted-foreground",
  upcoming: "text-muted-foreground",
  late: "text-wait",
  stale: "text-wait",
};

function Dot({ state }: { state: SlotState }) {
  const d = DOT[state];
  return (
    <span className={cn("absolute top-[5px] -left-[8px] grid size-[15px] place-items-center rounded-full border bg-background", d.ring)} aria-hidden>
      {d.core && <span className={cn("size-[7px] rounded-full", d.core)} />}
    </span>
  );
}

function dayTitle(slot: Slot): string {
  const date = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" })
    .format(new Date(slot.slot_at));
  return slot.day === "today" || slot.day === "tomorrow" ? `${slot.day === "today" ? "Today" : "Tomorrow"} · ${date}` : date;
}

/** Today and tomorrow as a vertical timeline: one node per posting slot, coloured and worded by state. */
export function SlotBoard({ slots, lateLimit, onPick, pickDisabled, picked }: {
  slots: Slot[];
  lateLimit: number;
  onPick: (slot: Slot) => void;
  /** Why "Generate for this slot" can't be used right now (shown as the button's tooltip), or null. */
  pickDisabled: string | null;
  picked: string;
}) {
  const days = [...new Set(slots.map((s) => s.date))];
  // one obvious next step: the first slot that can be generated gets the outline button, later ones are quiet
  const next = slots.find((s) => s.can_generate)?.slot_at;
  return (
    <div className="grid gap-5">
      {days.map((date) => {
        const inDay = slots.filter((s) => s.date === date);
        return (
          <div key={date} role="group" aria-label={dayTitle(inDay[0])}>
            <h3 className="label-mono mb-2">{dayTitle(inDay[0])}</h3>
            <ol className="grid">
              {inDay.map((s) => {
                const head = s.items.reel ?? s.items.carousel;
                return (
                  <li key={s.slot_at} className="grid grid-cols-[3.5rem_1fr] gap-x-3">
                    <time dateTime={s.slot_at} className="numeral pt-0.5 text-right text-lg leading-6 font-semibold">
                      {s.time}
                    </time>
                    <div className="relative min-w-0 border-l border-rule pb-6 pl-5">
                      <Dot state={s.state} />
                      <p className={cn("text-sm font-medium", TEXT[s.state])}>{SLOT_LABEL[s.state]}</p>
                      {s.topic && head ? (
                        <Link to={`/posts?post=${head.id}`} className="mt-0.5 block w-fit rounded-[4px] font-medium leading-snug break-words hover:text-primary focus-visible:text-primary">
                          {s.topic}
                        </Link>
                      ) : null}
                      {s.state === "generated" && (
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                          {(["reel", "carousel"] as const).map((k) => s.items[k] && (
                            <span key={k} className="inline-flex items-center gap-1.5">
                              {k === "reel" ? "Reel" : "Carousel"}
                              <StatusBadge status={s.items[k]!.status as Status} short />
                            </span>
                          ))}
                        </div>
                      )}
                      <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{slotHint(s, lateLimit)}</p>
                      {s.can_generate && (
                        <Button
                          variant={picked === s.time ? "secondary" : s.slot_at === next ? "outline" : "ghost"}
                          size="sm"
                          className={cn("mt-2 touch:h-11", s.slot_at !== next && picked !== s.time && "-ml-2.5")}
                          onClick={() => onPick(s)}
                          disabled={!!pickDisabled}
                          title={pickDisabled ?? undefined}
                          aria-pressed={picked === s.time}
                        >
                          {picked === s.time ? "Selected in the form" : s.state === "failed" || s.state === "skipped" ? "Try this slot again" : "Generate for this slot"}
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        );
      })}
    </div>
  );
}
