import assert from "node:assert/strict";
import { ago, checkField, cleanValue, errorAnchor, STATE_LABEL, STATE_ROLE } from "../src/lib/config-format.ts";
import { GLOSSARY, GUIDES, TROUBLESHOOTING } from "../src/lib/config-guides.ts";

// paste cleaner mirrors the server (src/verify/base.py clean_value)
assert.deepEqual(cleanValue('  "abc123"\n'), { value: "abc123", notes: ["removed surrounding spaces or line breaks", "removed the quotes"] });
assert.equal(cleanValue(' "GEMINI_API_KEY=k-123"', "GEMINI_API_KEY").value, "k-123");
assert.equal(cleanValue("export TG_BOT_TOKEN='1:a'", "TG_BOT_TOKEN").value, "1:a");
assert.equal(cleanValue("ab​c﻿").value, "abc");
assert.equal(cleanValue("ab​c").value, "abc"); // a second call still cleans (no stateful /g regex)
assert.equal(cleanValue("COUDNARY_API_ENV_VAR=cloudinary://a:b@c", "CLOUDINARY_URL").value, "cloudinary://a:b@c");
assert.equal(cleanValue("https://github.com/acme/automation.git", "GITHUB_REPOSITORY").value, "acme/automation");
for (const n of cleanValue('"secret-value"').notes) assert.ok(!n.includes("secret-value"), "notes never echo the value");

// instant format checks (L1)
assert.equal(checkField("GEMINI_API_KEY", "abc def")?.level, "error");
assert.equal(checkField("GEMINI_API_KEY", "abcdef")?.level, "ok");
assert.equal(checkField("GEMINI_API_KEY", ""), null);
assert.equal(checkField("TG_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")?.level, "ok");
assert.equal(checkField("TG_BOT_TOKEN", "123:abc/../getUpdates")?.level, "error");
assert.equal(checkField("TG_CHAT_ID", "-100123")?.level, "ok");
assert.equal(checkField("TG_CHAT_ID", "@me")?.level, "error");
assert.equal(checkField("CLOUDINARY_URL", "cloudinary://<your_api_key>:<your_api_secret>@demo")?.level, "error");
assert.match(checkField("CLOUDINARY_URL", "cloudinary://<your_api_key>:<your_api_secret>@demo")!.text, /Replace/);
assert.equal(checkField("CLOUDINARY_URL", "cloudinary://123:sec@demo-cloud")?.text, "Cloud: demo-cloud");
assert.equal(checkField("GITHUB_REPOSITORY", "acme/../x")?.level, "error");
assert.equal(checkField("GITHUB_REPOSITORY", "acme/content-automation")?.level, "ok");
assert.equal(checkField("GITHUB_DISPATCH_TOKEN", "ghp_abc")?.level, "warn");
assert.equal(checkField("GEMINI_MODEL", "models/gemini-flash-latest")?.level, "ok");
assert.equal(checkField("GEMINI_FALLBACK_MODELS", "a-1, ../x")?.level, "error");

// every state has a label and a colour role (status is never colour-only: the label is always shown)
for (const s of ["not_set", "checking", "valid", "warning", "invalid", "unknown", "stale", "unverified"]) {
  assert.ok(STATE_LABEL[s] && STATE_ROLE[s], s);
}
assert.equal(errorAnchor("gemini.key_rejected"), "gemini-key_rejected");
const now = new Date("2026-10-06T10:00:00Z").getTime();
assert.equal(ago("2026-10-06T09:59:50Z", now), "just now");
assert.equal(ago("2026-10-06T07:00:00Z", now), "3h ago");
assert.equal(ago(null, now), "never");

// docs: every guide is complete, links are official https pages, troubleshooting entries are actionable
assert.deepEqual(GUIDES.map((g) => g.id), ["gemini", "telegram", "cloudinary", "github", "database"]);
for (const g of GUIDES) {
  assert.ok(g.steps.length >= 3 && g.mistakes.length && g.sources.length && g.success && g.security, g.id);
  for (const s of g.steps) if (s.link) assert.match(s.link.href, /^https:\/\//);
  for (const s of g.sources) assert.match(s.href, /^https:\/\//);
}
for (const [code, t] of Object.entries(TROUBLESHOOTING)) {
  assert.match(code, /^[a-z]+\.[a-z_]+$/);
  assert.ok(t.title && t.cause && t.fix.length, code);
  if (t.link) assert.match(t.link.href, /^https:\/\//);
}
assert.ok(GLOSSARY.length >= 10);
console.log("config.test ok");
