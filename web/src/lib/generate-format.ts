// Types and display helpers for the Generate page (pure: no network, so tests can run them under plain node).

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "skipped" | "cancelled";
export type Phase =
  | "starting" | "fetching_topics" | "ranking" | "writing" | "rendering" | "uploading" | "sending_previews" | "done";

export type Job = {
  id: string;
  trigger: "dashboard" | "scheduled";
  requested_by: string | null;
  status: JobStatus;
  phase: Phase | null;
  active: boolean;
  failure_reason: string | null;
  message: string | null;
  slot_at: string | null;
  category: string | null;
  topic: string | null;
  source_url: string | null;
  force: boolean;
  allow_duplicate: boolean;
  github_run_id: number | null;
  github_run_url: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_sec: number | null;
  topic_title: string | null;
  topic_category: string | null;
  post_group_id: string | null;
  post_ids: string[];
};

export type SlotState = "generated" | "generating" | "failed" | "skipped" | "upcoming" | "late" | "stale";

export type Slot = {
  slot_at: string;
  time: string;
  date: string;
  day: string;
  state: SlotState;
  hours_late: number;
  can_generate: boolean;
  group_id: string | null;
  topic: string | null;
  category: string | null;
  items: { reel: { id: string; status: string } | null; carousel: { id: string; status: string } | null };
  job: Pick<Job, "id" | "status" | "phase" | "failure_reason" | "message" | "trigger"> | null;
};

export type GenConfig = {
  dispatch_configured: boolean;
  slots: string[];
  categories: { name: string; weight: number }[];
  daily_cap: number;
  used_today: number;
  resets_at: string;
  quota_cooldown_until: string | null;
  late_limit_hours: number;
  publishing_enabled: boolean;
  telegram_sync: boolean;
  topic_length: [number, number];
};

export type GithubState = { ok: boolean; as_of: string };
export type JobsResponse = { jobs: Job[]; active: Job | null; github: GithubState };

export type GenerateRequest = {
  slot: string;
  category: string | null;
  topic: string | null;
  source_url: string | null;
  force: boolean;
  allow_duplicate: boolean;
  confirm_quota: boolean;
  idempotency_key: string;
};

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

/** The phases a run walks through, in order (the server's vocabulary), with the words shown to the admin. */
export const PHASES: { key: Phase; label: string; verb: string }[] = [
  { key: "starting", label: "Start", verb: "Starting the run" },
  { key: "fetching_topics", label: "Topics", verb: "Fetching trending topics" },
  { key: "ranking", label: "Pick", verb: "Choosing the topic" },
  { key: "writing", label: "Write", verb: "Writing and reviewing the script" },
  { key: "rendering", label: "Render", verb: "Rendering the carousel and reel" },
  { key: "uploading", label: "Upload", verb: "Uploading the media" },
  { key: "sending_previews", label: "Previews", verb: "Sending the Telegram previews" },
];

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Waiting to start",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Cancelled",
};

export type StepState = "done" | "current" | "todo" | "failed" | "skipped";

/**
 * State of each phase for a job. A custom topic never fetches or ranks, so those two show as "skipped";
 * a failed or cancelled run marks the phase it stopped in; a run that did nothing (skipped) shows none.
 */
export function stepStates(job: Pick<Job, "status" | "phase" | "topic">): StepState[] {
  const started = job.status !== "queued" || !!job.phase;
  const at = job.status === "succeeded" || job.phase === "done" ? PHASES.length
    : Math.max(0, PHASES.findIndex((p) => p.key === job.phase));
  return PHASES.map((p, i) => {
    if (job.topic && started && (p.key === "fetching_topics" || p.key === "ranking")) return "skipped";
    if (!started || job.status === "skipped" || i > at) return "todo";
    if (i < at) return "done";
    return job.status === "running" ? "current" : "failed";
  });
}

/** One line for the live region: "Writing and reviewing the script (step 4 of 7)". */
export function phaseSentence(job: Pick<Job, "status" | "phase" | "message" | "failure_reason" | "topic_title">): string {
  switch (job.status) {
    case "queued": return "Waiting for GitHub to start the run";
    case "succeeded": return `Finished${job.topic_title ? `: ${job.topic_title}` : ""}`;
    case "failed": return `Failed${job.message ? `: ${job.message}` : ""}`;
    case "cancelled": return `Cancelled${job.message ? `: ${job.message}` : ""}`;
    case "skipped": return `Skipped${job.message ? `: ${job.message}` : ""}`;
    default: {
      const i = PHASES.findIndex((p) => p.key === job.phase);
      return i < 0 ? "Running" : `${PHASES[i].verb} (step ${i + 1} of ${PHASES.length})`;
    }
  }
}

/** "4m 05s", "1h 02m", "38s". */
export function elapsedText(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`;
}

/** Seconds a job has been going at `now` (frozen once it has finished). */
export function elapsedSeconds(job: Pick<Job, "started_at" | "created_at" | "finished_at" | "duration_sec" | "active">, now: number): number {
  if (!job.active) return job.duration_sec ?? 0;
  return (now - new Date(job.started_at ?? job.created_at).getTime()) / 1000;
}

export const SLOT_LABEL: Record<SlotState, string> = {
  generated: "Generated",
  generating: "Generating",
  failed: "Last attempt failed",
  skipped: "Skipped",
  upcoming: "Not generated yet",
  late: "Missing (slot passed)",
  stale: "Missing (over 12h ago)",
};

export function slotHint(slot: Pick<Slot, "state" | "hours_late" | "job">, lateLimit = 12): string {
  switch (slot.state) {
    case "generated": return "Review it in Posts";
    case "generating": return slot.job?.phase ? PHASES.find((p) => p.key === slot.job?.phase)?.verb ?? "Running" : "Starting";
    case "failed": return slot.job?.message ?? "The last run for this slot failed";
    case "skipped": return slot.job?.message ?? "The last run for this slot did nothing";
    case "upcoming": return "Scheduled generation runs 1 to 2 hours before the slot";
    case "late": return "Passed. It still generates, and posts as soon as you approve it";
    case "stale": return `Passed over ${lateLimit}h ago. Needs “extra post” to generate`;
  }
}

/** How long to wait before asking again: fast while a run is active, slow otherwise, never while hidden. */
export function pollDelay(active: boolean, hidden: boolean, githubOk = true): number | null {
  if (hidden) return null;
  if (!active) return 60_000;
  return githubOk ? 6_000 : 15_000;
}

/** A fresh key per submission; reused only when the network failed, so a retry can't start a second run. */
export function newIdempotencyKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Plain-language reason a run couldn't be requested right now, or null when the form can be used. */
export function blockedReason(
  cfg: Pick<GenConfig, "dispatch_configured" | "daily_cap" | "used_today" | "resets_at">,
  active: Pick<Job, "id" | "requested_by" | "created_at" | "trigger"> | null,
  formatTime: (iso: string) => string,
): string | null {
  if (!cfg.dispatch_configured) {
    return "Generation can't be started from the dashboard until the GitHub token is configured. Scheduled runs still happen.";
  }
  if (active) {
    const by = active.trigger === "scheduled" ? "a scheduled run" : active.requested_by ?? "someone";
    return `A generation is already running (started ${formatTime(active.created_at)} by ${by}).`;
  }
  if (cfg.used_today >= cfg.daily_cap) {
    return `Daily limit (${cfg.daily_cap}) reached; resets at ${formatTime(cfg.resets_at)}.`;
  }
  return null;
}
