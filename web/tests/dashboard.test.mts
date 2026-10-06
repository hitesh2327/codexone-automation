import assert from "node:assert/strict";
import {
  agoLabel, cadenceSummary, cellSummary, deltaText, fmtMinutes, funnelShape, headline, heatGrid, mixNote, pickWorkspace,
  pctText, ratioText, untilLabel, type CadenceDay, type Overview,
} from "../src/lib/dashboard-format.ts";

// numbers always show numerator and denominator
assert.equal(ratioText({ num: 31, den: 36 }), "31 of 36");
assert.equal(pctText({ num: 0, den: 0, pct: null, judged: false }), "—");
assert.equal(pctText({ num: 7, den: 9, pct: 78, judged: false }), "78%");

assert.equal(fmtMinutes(null), "—");
assert.equal(fmtMinutes(20), "20 min");
assert.equal(fmtMinutes(65), "1 h 05 m");
assert.equal(fmtMinutes(3 * 1440 + 120), "3 d 2 h");

const now = new Date("2026-10-05T12:00:00Z").getTime();
assert.equal(untilLabel("2026-10-05T15:12:00Z", now), "in 3h 12m");
assert.equal(untilLabel("2026-10-05T11:00:00Z", now), "now");
assert.equal(agoLabel("2026-10-05T10:00:00Z", now), "2h ago");
assert.equal(agoLabel(null, now), "never");

// the 10-second sentence
const base = { ok: true, state: "ok", needs_count: 0, reason: null, today_published: 4, today_expected: 4, next_slot_at: "2026-10-05T13:30:00Z" } as Overview["status"];
let h = headline(base, now);
assert.equal(h.title, "All good."); assert.equal(h.tone, "ok"); assert.match(h.sub, /4 of 4 posts live today/); assert.match(h.sub, /19:00 IST \(in 1h 30m\)/);
h = headline({ ...base, state: "heads_up", needs_count: 2 }, now);
assert.equal(h.title, "2 things need you."); assert.equal(h.tone, "wait");
h = headline({ ...base, state: "action", needs_count: 1 }, now);
assert.equal(h.title, "1 thing needs you."); assert.equal(h.tone, "bad"); assert.equal(h.label, "Action needed");
// a failed check is never an all-clear
h = headline({ ...base, ok: false, state: "unknown" }, now);
assert.equal(h.tone, "idle"); assert.doesNotMatch(h.title, /good|clear/i);

// heatmap grid: weeks as Monday-first columns, padded
const day = (date: string, state: CadenceDay["state"] = "full", n = 4): CadenceDay => ({ date, n, topics: 2, expected: 4, state });
const days = ["2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"].map((d) => day(d)); // Wed..Mon
const cols = heatGrid(days);
assert.equal(cols.length, 2); assert.ok(cols.every((c) => c.length === 7));
assert.deepEqual(cols[0].map((c) => c?.date ?? null), [null, null, "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]);
assert.equal(cols[1][0]?.date, "2026-10-05"); assert.equal(cols[1][1], null);
assert.deepEqual(heatGrid([]), []);

// readouts a screen reader hears
assert.equal(cellSummary(day("2026-09-29")), "Tue 29 Sep: 4 of 4 published (2 topics)");
assert.match(cellSummary(day("2026-09-29", "partial", 2)), /2 of 4 published .*partly/);
assert.match(cellSummary(day("2026-09-29", "missed", 0)), /missed, 0 of 4/);
assert.match(cellSummary(day("2026-09-29", "none", 0)), /before the first post/);
assert.equal(cadenceSummary({ full_days: 27, counted_days: 30, streak: 12 }), "27 of 30 days fully published; current streak 12 days");
assert.match(cadenceSummary({ full_days: 0, counted_days: 3, streak: 0 }), /no current streak/);

// funnel shape: bars scale to the first stage, bands join consecutive bars
const g = funnelShape([100, 80, 60, 50], 400, 100);
assert.equal(g.bars.length, 4); assert.equal(g.bands.length, 3);
assert.equal(g.bars[0].h, 100); assert.equal(g.bars[1].h, 80); assert.equal(g.bars[3].h, 50);
assert.equal(g.bars[3].y, 25);                                  // vertically centred
assert.ok(g.bars.every((b, i) => i === 0 || b.x > g.bars[i - 1].x + g.bars[i - 1].w));
assert.ok(g.bands.every((d) => d.startsWith("M") && d.endsWith("Z")));
assert.equal(funnelShape([0, 0], 100, 100).bars[0].h, 0);       // empty data never produces NaN
assert.ok(!funnelShape([0, 0], 100, 100).bands[0].includes("NaN"));

// mix wording: too few topics = no judgement
assert.match(mixNote({ n: 12, judged: false, min_n: 20 }), /too few to judge/);
assert.match(mixNote({ n: 24, judged: true, min_n: 20 }), /n = 24 topics/);
assert.equal(mixNote({ n: 0, judged: false, min_n: 20 }), "No topics in this period yet.");
const row = { category: "DSA", count: 6, share: 25, target: 20, delta: 5, margin: 16, tone: "on" as const };
assert.equal(deltaText(row, true), "+5.0 vs target 20% (margin ±16)");
assert.equal(deltaText(row, false), "+5.0 vs target 20%");
assert.equal(deltaText({ ...row, delta: -9.7 }, false), "−9.7 vs target 20%");

// Live/Demo choice: session or URL; never on by accident; off entirely when the server disables it
assert.equal(pickWorkspace("", null, true), "live");
assert.equal(pickWorkspace("", "demo", true), "demo");
assert.equal(pickWorkspace("?workspace=demo", null, true), "demo");
assert.equal(pickWorkspace("?workspace=live", "demo", true), "live");
assert.equal(pickWorkspace("?workspace=demo", "demo", false), "live");
assert.equal(pickWorkspace("?workspace=bogus", null, true), "live");
console.log("dashboard.test ok");
