import type { Item, Platform } from "./posts";

/** The happy path a post travels. Index into STAGES = how far along it is. */
export const STAGES = ["Approval", "Scheduled", "Publishing", "Live"] as const;

export type Tone = "wait" | "go" | "ok" | "bad" | "idle";

export type Stage = {
  /** 0..3 = position on the happy path; -1 = off the path (rejected, expired, replaced, regenerating). */
  step: number;
  tone: Tone;
  title: string;
  note: string;
};

const LABEL: Record<Platform, string> = { ig: "Instagram", yt: "YouTube" };

/** "in 7h 12m", "in 2d 3h", "in 5m"; null once the moment has passed. */
export function untilText(iso: string, now: number): string | null {
  const mins = Math.round((new Date(iso).getTime() - now) / 60000);
  if (mins <= 0) return null;
  if (mins < 60) return `in ${mins}m`;
  if (mins < 48 * 60) return `in ${Math.floor(mins / 60)}h ${mins % 60}m`;
  return `in ${Math.floor(mins / 1440)}d ${Math.floor((mins % 1440) / 60)}h`;
}

/** Where a post is, and what happens next. `slot` is the formatted publish time (IST). */
export function stageOf(item: Pick<Item, "status" | "publish_at" | "platforms" | "targets" | "error">, slot: string, now: number): Stage {
  const wait = untilText(item.publish_at, now);
  switch (item.status) {
    case "pending":
      return {
        step: 0, tone: "wait", title: "Waiting for approval",
        note: wait ? `Approve it to post ${slot}` : "Slot passed; posts as soon as you approve",
      };
    case "approved":
      return {
        step: 1, tone: "go", title: "Approved",
        note: wait ? `Publishes ${slot} · ${wait}` : "Due now; the next poll run publishes it",
      };
    case "publishing":
      return { step: 2, tone: "go", title: "Publishing", note: "Uploading to the platforms…" };
    case "published": {
      const done = item.targets.filter((t) => item.platforms[t]?.status === "published").map((t) => LABEL[t]);
      return { step: 3, tone: "ok", title: "Live", note: done.length ? `On ${done.join(" and ")}` : "Published" };
    }
    case "failed": {
      const bad = item.targets.filter((t) => item.platforms[t]?.status === "failed").map((t) => LABEL[t]);
      const why = item.error || item.platforms[item.targets.find((t) => item.platforms[t]?.status === "failed") ?? "ig"]?.error;
      return {
        step: 2, tone: "bad", title: "Failed",
        note: `${bad.length ? `${bad.join(" and ")}: ` : ""}${why ?? "publish error"}`.slice(0, 140),
      };
    }
    case "regenerate":
      return { step: -1, tone: "go", title: "Regenerating", note: "A new version is being made" };
    case "rejected":
      return { step: -1, tone: "idle", title: "Rejected", note: "Won't be posted" };
    case "expired":
      return { step: -1, tone: "idle", title: "Expired", note: "No decision in time. Schedule it to bring it back" };
    case "replaced":
      return { step: -1, tone: "idle", title: "Replaced", note: "A newer version took over" };
  }
}

/** One-word buckets for the summary strip, so every post lands in exactly one. */
export type Bucket = "approval" | "scheduled" | "live" | "failed";

export function bucketOf(status: Item["status"]): Bucket | null {
  if (status === "pending") return "approval";
  if (status === "approved" || status === "publishing" || status === "regenerate") return "scheduled";
  if (status === "published") return "live";
  if (status === "failed") return "failed";
  return null;
}
