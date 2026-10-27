import assert from "node:assert/strict";
import {
  PHASES, blockedReason, elapsedSeconds, elapsedText, newIdempotencyKey, phaseSentence, pollDelay, slotHint, stepStates,
} from "../src/lib/generate-format.ts";

const job = (o: object) => ({ status: "running", phase: null, topic: null, message: null, failure_reason: null, topic_title: null, ...o }) as any;

// phases follow the server's order and vocabulary
assert.deepEqual(PHASES.map((p) => p.key), ["starting", "fetching_topics", "ranking", "writing", "rendering", "uploading", "sending_previews"]);

// queued: nothing has started
assert.deepEqual(new Set(stepStates(job({ status: "queued" }))), new Set(["todo"]));
// running in "writing": 3 done, writing current, the rest waiting
assert.deepEqual(stepStates(job({ phase: "writing" })), ["done", "done", "done", "current", "todo", "todo", "todo"]);
// a failed run marks the phase it died in
assert.deepEqual(stepStates(job({ status: "failed", phase: "rendering" })), ["done", "done", "done", "done", "failed", "todo", "todo"]);
// finished: everything done
assert.deepEqual(new Set(stepStates(job({ status: "succeeded", phase: "done" }))), new Set(["done"]));
// a custom topic never fetches or ranks
assert.deepEqual(stepStates(job({ phase: "rendering", topic: "x" })), ["done", "skipped", "skipped", "done", "current", "todo", "todo"]);
// a skipped (did-nothing) run shows no progress
assert.deepEqual(new Set(stepStates(job({ status: "skipped" }))), new Set(["todo"]));

// the live-region sentence says where we are, in words
assert.equal(phaseSentence(job({ phase: "writing" })), "Writing and reviewing the script (step 4 of 7)");
assert.equal(phaseSentence(job({ status: "queued" })), "Waiting for GitHub to start the run");
assert.equal(phaseSentence(job({ status: "failed", message: "Gemini quota" })), "Failed: Gemini quota");
assert.equal(phaseSentence(job({ status: "succeeded", topic_title: "Sharding" })), "Finished: Sharding");

// elapsed time
assert.equal(elapsedText(38), "38s");
assert.equal(elapsedText(245), "4m 05s");
assert.equal(elapsedText(3720), "1h 02m");
const t0 = new Date("2026-10-05T10:00:00Z").getTime();
assert.equal(elapsedSeconds({ active: true, started_at: "2026-10-05T09:58:00Z", created_at: "2026-10-05T09:50:00Z", finished_at: null, duration_sec: null }, t0), 120);
assert.equal(elapsedSeconds({ active: true, started_at: null, created_at: "2026-10-05T09:59:00Z", finished_at: null, duration_sec: null }, t0), 60);
assert.equal(elapsedSeconds({ active: false, started_at: "x", created_at: "x", finished_at: "y", duration_sec: 300 }, t0), 300);

// polling: fast while a run is active, slow when idle, never while the tab is hidden, backs off when GitHub is limited
assert.equal(pollDelay(true, false), 6000);
assert.equal(pollDelay(true, false, false), 15000);
assert.equal(pollDelay(false, false), 60000);
assert.equal(pollDelay(true, true), null);

// why the form is blocked, most important first
const cfg = { dispatch_configured: true, daily_cap: 4, used_today: 1, resets_at: "2026-10-06T00:00:00+05:30" };
const fmt = (iso: string) => iso.slice(11, 16);
assert.equal(blockedReason(cfg, null, fmt), null);
assert.match(blockedReason({ ...cfg, dispatch_configured: false }, null, fmt)!, /token is configured/);
assert.match(blockedReason(cfg, { id: "a", requested_by: "admin", created_at: "2026-10-05T10:05:00+05:30", trigger: "dashboard" }, fmt)!, /already running \(started 10:05 by admin\)/);
assert.match(blockedReason(cfg, { id: "a", requested_by: null, created_at: "2026-10-05T10:05:00+05:30", trigger: "scheduled" }, fmt)!, /by a scheduled run/);
assert.match(blockedReason({ ...cfg, used_today: 4 }, null, fmt)!, /Daily limit \(4\) reached; resets at 00:00/);

// slot hints never promise what the pipeline won't do
assert.match(slotHint({ state: "stale", hours_late: 20, job: null }), /Needs .*extra post/);
assert.match(slotHint({ state: "late", hours_late: 3, job: null }), /posts as soon as you approve/);
assert.equal(slotHint({ state: "failed", hours_late: 0, job: { message: "Quota" } as any }), "Quota");

// idempotency keys are unique and satisfy the API's pattern
const a = newIdempotencyKey();
assert.match(a, /^[A-Za-z0-9_-]{8,64}$/);
assert.notEqual(a, newIdempotencyKey());
console.log("generate.test.mts: ok");
