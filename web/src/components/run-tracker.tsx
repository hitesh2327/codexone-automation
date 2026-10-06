import { Link } from "react-router-dom";
import { ExternalLink, RotateCcw, ScrollText } from "lucide-react";

import { JobStatusBadge, PhaseTrack } from "@/components/phase-track";
import { Button } from "@/components/ui/button";
import { elapsedSeconds, elapsedText, type GithubState, type Job } from "@/lib/generate-format";
import { formatIST } from "@/lib/posts";

const REASON_TITLE: Record<string, string> = {
  quota: "Gemini quota used up",
  fetch: "Topic search failed",
  rank: "Topic choice failed",
  write: "Writing failed",
  render: "Rendering failed",
  upload: "Upload failed",
  telegram: "Telegram previews failed",
  dispatch_rejected: "GitHub refused the request",
  dispatch_failed: "GitHub unreachable",
  not_started: "GitHub never started the run",
  timeout: "Timed out",
  duplicate: "Topic already covered",
  taken: "Slot already had a post",
  stale: "Slot too old",
  superseded: "Replaced by a newer run",
};

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="label-mono">{label}</dt>
      <dd className="text-sm break-words">{children}</dd>
    </div>
  );
}

/** The live card for the running (or most recent) request: phases, elapsed time, run link, and what to do next. */
export function RunTracker({ job, now, github, onRetry }: {
  job: Job;
  now: number;
  github: GithubState;
  onRetry: (job: Job) => void;
}) {
  const reviewId = job.post_ids[0];
  const failed = job.status === "failed" || job.status === "cancelled";
  const asOf = formatIST(github.as_of, false);
  return (
    <section aria-labelledby="tracker-title" className="grid gap-4 rounded-xl border border-rule bg-card p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id="tracker-title" className="font-heading text-lg font-semibold">
          {job.active ? "Running now" : "Latest request"}
        </h2>
        <JobStatusBadge status={job.status} />
        <span className="ml-auto font-mono text-xs text-muted-foreground" title="Request id (also in the GitHub run name and the Logs)">
          #{job.id}
        </span>
      </div>

      <PhaseTrack job={job} />

      {job.status === "queued" && job.github_run_url && (
        <p className="text-xs text-muted-foreground">GitHub has the run but it is waiting its turn (another generate run may be ahead of it).</p>
      )}
      {job.active && !github.ok && (
        <p role="status" className="text-xs text-wait">
          GitHub status is temporarily unavailable. Showing the last known state (as of {asOf} IST) and retrying.
        </p>
      )}

      {job.status === "succeeded" && (
        <div className="grid gap-1 border-l-[3px] border-ok bg-ok/[0.07] py-3 pr-3 pl-4">
          <p className="font-medium">{job.topic_title ?? "Post generated"}</p>
          <p className="text-sm text-muted-foreground">
            {job.topic_category ? `${job.topic_category} · ` : ""}Previews were sent to Telegram. Nothing is published until you approve.
          </p>
        </div>
      )}
      {(failed || job.status === "skipped") && (
        <div className={`grid gap-1 border-l-[3px] py-3 pr-3 pl-4 text-sm ${failed ? "border-bad bg-bad/10" : "border-rule bg-raised"}`}>
          <p className={failed ? "font-medium text-bad" : "font-medium"}>
            {REASON_TITLE[job.failure_reason ?? ""] ?? (failed ? "The run did not finish" : "Nothing was generated")}
          </p>
          {job.message && <p className="break-words text-muted-foreground">{job.message}</p>}
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <Fact label="Elapsed"><span className="tabular-nums">{elapsedText(elapsedSeconds(job, now))}</span></Fact>
        <Fact label="Slot">{job.slot_at ? `${formatIST(job.slot_at)} IST` : "Next free"}</Fact>
        <Fact label="Category">{job.topic_category ?? job.category ?? "Auto"}</Fact>
        <Fact label="Started by">{job.trigger === "scheduled" ? "Scheduler" : job.requested_by ?? "Dashboard"}</Fact>
        {job.topic && <div className="col-span-2 sm:col-span-4"><Fact label="Your topic">{job.topic}</Fact></div>}
      </dl>

      <div className="flex flex-wrap items-center gap-2">
        {reviewId && (
          <Button asChild size="sm" className="touch:h-11">
            <Link to={`/posts?post=${reviewId}`}>Review in Posts</Link>
          </Button>
        )}
        {job.status === "succeeded" && !reviewId && (
          <Button asChild size="sm" variant="outline" className="touch:h-11"><Link to="/posts">Open Posts</Link></Button>
        )}
        {failed && job.trigger === "dashboard" && (
          <Button size="sm" variant="outline" className="touch:h-11" onClick={() => onRetry(job)}>
            <RotateCcw />
            Retry
          </Button>
        )}
        {job.github_run_url ? (
          <Button asChild size="sm" variant="ghost" className="touch:h-11">
            <a href={job.github_run_url} target="_blank" rel="noreferrer">
              <ExternalLink />
              Open GitHub run<span className="sr-only"> (opens in a new tab)</span>
            </a>
          </Button>
        ) : job.active ? (
          <span className="text-xs text-muted-foreground">Waiting for GitHub to create the run…</span>
        ) : null}
        {(failed || job.status === "skipped") && (
          <Button asChild size="sm" variant="ghost" className="touch:h-11">
            <Link to={`/logs?q=${job.id}`}><ScrollText />Logs</Link>
          </Button>
        )}
      </div>
    </section>
  );
}
