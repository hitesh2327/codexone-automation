import assert from "node:assert/strict";
import { stageOf, untilText, bucketOf } from "../src/lib/stage.ts";

const now = new Date("2026-10-01T02:10:00+05:30").getTime();
const base = { publish_at: "2026-10-01T10:00:00+05:30", platforms: {}, targets: ["ig", "yt"] as any, error: null };

// the real situation: carousel+reel approved at 02:05, slot 10:00 IST
let s = stageOf({ ...base, status: "approved" }, "Thu 1 Oct, 10:00", now);
assert.equal(s.step, 1); assert.equal(s.tone, "go");
assert.equal(s.note, "Publishes Thu 1 Oct, 10:00 · in 7h 50m");

// pending, slot ahead vs. slot passed (the stale 30 Sep pair)
assert.match(stageOf({ ...base, status: "pending" }, "x", now).note, /^Approve it to post/);
s = stageOf({ ...base, status: "pending", publish_at: "2026-09-30T19:00:00+05:30" }, "x", now);
assert.equal(s.step, 0); assert.match(s.note, /Slot passed/);

// approved but slot already passed -> due now
s = stageOf({ ...base, status: "approved", publish_at: "2026-10-01T01:00:00+05:30" }, "x", now);
assert.match(s.note, /Due now/);

// published on both, and on one only
const pub = { ig: { status: "published" }, yt: { status: "published" } } as any;
assert.equal(stageOf({ ...base, status: "published", platforms: pub }, "x", now).note, "On Instagram and YouTube");
assert.equal(stageOf({ ...base, status: "published", targets: ["ig"] as any, platforms: pub }, "x", now).note, "On Instagram");

// failed names the platform and the reason
s = stageOf({ ...base, status: "failed", platforms: { yt: { status: "failed", error: "quota exceeded" } } as any }, "x", now);
assert.equal(s.tone, "bad"); assert.equal(s.step, 2); assert.equal(s.note, "YouTube: quota exceeded");

// off-path states
for (const st of ["rejected", "expired", "replaced", "regenerate"] as const)
  assert.equal(stageOf({ ...base, status: st }, "x", now).step, -1);

// countdown formatting
assert.equal(untilText("2026-10-01T02:40:00+05:30", now), "in 30m");
assert.equal(untilText("2026-10-01T02:10:00+05:30", now), null);
assert.equal(untilText("2026-10-04T05:10:00+05:30", now), "in 3d 3h");

// every status lands in at most one bucket
assert.deepEqual(["pending", "approved", "publishing", "published", "failed", "rejected"].map((x) => bucketOf(x as any)),
  ["approval", "scheduled", "scheduled", "live", "failed", null]);
console.log("stage logic: all assertions passed");
