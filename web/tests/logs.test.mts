import assert from "node:assert/strict";
import { ago, dayKey, dayLabel, groupByDay, logsQuery, mergeNewest, timeIST, type LogEntry } from "../src/lib/log-format.ts";

const e = (id: number, created_at: string): LogEntry =>
  ({ id, created_at, level: "info", source: "dashboard", event: "x", message: "m", post_id: null, actor: null, detail: null });

// IST is UTC+5:30: 19:00Z on 4 Oct is already 00:30 on 5 Oct
assert.equal(dayKey("2026-10-04T19:00:00Z"), "2026-10-05");
assert.equal(dayKey("2026-10-04T18:29:00Z"), "2026-10-04");
assert.equal(timeIST("2026-10-04T19:00:05Z"), "00:30:05");

const now = new Date("2026-10-05T10:00:00Z").getTime();
assert.equal(dayLabel("2026-10-05", now), "Today");
assert.equal(dayLabel("2026-10-04", now), "Yesterday");
assert.match(dayLabel("2026-09-20", now), /20 Sep 2026/);

const groups = groupByDay([e(4, "2026-10-05T09:00:00Z"), e(3, "2026-10-05T01:00:00Z"), e(2, "2026-10-04T08:00:00Z")]);
assert.deepEqual(groups.map((g) => [g.key, g.entries.length]), [["2026-10-05", 2], ["2026-10-04", 1]]);

assert.deepEqual(mergeNewest([e(3, "2026-10-05T01:00:00Z")], [e(5, "2026-10-05T02:00:00Z"), e(4, "2026-10-05T01:30:00Z"), e(3, "2026-10-05T01:00:00Z")]).map((x) => x.id), [5, 4, 3]);
assert.equal(mergeNewest([e(3, "2026-10-05T01:00:00Z")], [e(3, "2026-10-05T01:00:00Z")]).length, 1);
assert.equal(mergeNewest([], [e(1, "2026-10-05T01:00:00Z")]).length, 1);

assert.equal(logsQuery({}), "");
assert.equal(logsQuery({ level: "error,warning", q: "a b" }, { before_id: 9, limit: 50 }), "?level=error&level=warning&q=a+b&before_id=9&limit=50");

assert.equal(ago("2026-10-05T09:59:50Z", now), "just now");
assert.equal(ago("2026-10-05T09:15:00Z", now), "45m ago");
assert.equal(ago("2026-10-05T05:00:00Z", now), "5h ago");
assert.equal(ago("2026-10-02T10:00:00Z", now), "3d ago");
console.log("logs.test ok");
