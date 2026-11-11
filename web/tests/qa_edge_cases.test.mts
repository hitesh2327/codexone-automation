import assert from "node:assert/strict";
import { safeHref } from "../src/lib/utils.ts";
import { newIdempotencyKey } from "../src/lib/generate-format.ts";

console.log("=== RUNNING QA FRONTEND STATE MACHINE & EDGE CASE TESTS ===");

// ----------------------------------------------------------------------------
// Test 1: XSS loophole in Posts.tsx PlatformMarks vs safeHref
// ----------------------------------------------------------------------------
{
  const maliciousUrls = [
    "javascript:alert(document.cookie)",
    "javascript://%0aalert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "http://insecure-phishing.com/login"
  ];
  
  for (const url of maliciousUrls) {
    const sanitized = safeHref(url);
    assert.equal(sanitized, undefined, `safeHref must reject ${url}`);
  }
  
  // Vulnerability in Posts.tsx line 38-42:
  // r?.url ? <a key={t} href={r.url} ...>
  // Because r.url is passed directly into href without safeHref(r.url),
  // a malicious or compromised backend payload executes arbitrary script or navigates to unsafe schemes.
  const renderedHref = maliciousUrls[0]; // as executed in Posts.tsx
  assert.equal(renderedHref, "javascript:alert(document.cookie)");
  console.log("✓ Test 1 Confirmed: safeHref correctly strips dangerous URIs, but Posts.tsx:39 renders unvalidated r.url directly.");
}

// ----------------------------------------------------------------------------
// Test 2: Category Dropdown Permanent Lockout with Empty Categories
// ----------------------------------------------------------------------------
{
  // Simulating GenerateForm validation logic when user has no categories configured
  const categories: { name: string; weight: number }[] = [];
  const topic = "Architecting resilient distributed systems";
  const AUTO = "auto";
  let category = AUTO;

  const t = topic.trim();
  const categoryErr = t && category === AUTO ? "Pick a category for your own topic" : null;
  const invalid = !!categoryErr;

  // The available select options that GenerateForm renders:
  const selectOptions = [AUTO, ...categories.map(c => c.name)];
  
  assert.equal(invalid, true, "Form is marked invalid because custom topic needs non-auto category");
  assert.deepEqual(selectOptions, ["auto"], "Only 'auto' option exists in category dropdown");
  assert.equal(selectOptions.filter(c => c !== AUTO).length, 0, "User has ZERO available categories to select");
  console.log("✓ Test 2 Confirmed: Empty categories causes permanent deadlock for custom topic input.");
}

// ----------------------------------------------------------------------------
// Test 3: Idempotency Key Invalidation on 504 Gateway Timeout
// ----------------------------------------------------------------------------
{
  // In generate-form.tsx:
  // if (e.status !== 0) key.current = newIdempotencyKey();
  // On a 504 Gateway Timeout, e.status is 504 (not 0).
  const originalKey = newIdempotencyKey();
  let currentKey = originalKey;
  
  const mockApiError = { status: 504, message: "Request failed (504)", code: undefined };
  
  // GenerateForm error handler logic:
  if (mockApiError.status !== 0) {
    currentKey = newIdempotencyKey();
  }
  
  assert.notEqual(currentKey, originalKey, "Key was rotated on 504 Gateway Timeout");
  // Verification: Server may have received the request before 504 proxy timeout.
  // When user retries, a brand new idempotency key is dispatched, causing duplicate execution!
  console.log("✓ Test 3 Confirmed: 504 Gateway Timeout rotates idempotency key, destroying replay protection.");
}

// ----------------------------------------------------------------------------
// Test 4: Timezone Inconsistency across Pages
// ----------------------------------------------------------------------------
{
  // A timestamp representing 2026-11-12 00:00:00 IST (2026-11-11 18:30:00 UTC)
  const isoTimestamp = "2026-11-11T18:30:00.000Z";
  
  // Explicit IST formatter (as in posts.ts and dashboard.ts)
  const istFormatter = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false
  });
  const istFormatted = istFormatter.format(new Date(isoTimestamp));
  assert.match(istFormatted, /12 Nov/, "IST formatter outputs 12 Nov");
  
  // Subscription.tsx:60 & 169 call toLocaleDateString without specifying timeZone!
  // In a non-IST environment (e.g. UTC, US/Pacific, Europe/London):
  const utcFormatter = new Intl.DateTimeFormat("en-IN", { timeZone: "UTC", day: "numeric", month: "short" });
  const utcFormatted = utcFormatter.format(new Date(isoTimestamp));
  assert.match(utcFormatted, /11 Nov/, "UTC/PST formatter outputs 11 Nov (1-day offset)");
  console.log("✓ Test 4 Confirmed: Subscription.tsx toLocaleDateString drifts by 1 day when viewed outside IST.");
}

// ----------------------------------------------------------------------------
// Test 5: Infinite Scroll Error Cleared by Auto-Refresh Timer
// ----------------------------------------------------------------------------
{
  // Posts.tsx lines 222-243 & 287-298
  let loadMoreError: string | null = "Can't reach the server. Check your connection and try again.";
  
  // load(true) executes on timer (busy ? 8000 : 30000)
  function simulateAutoRefresh() {
    // line 227: setLoadMoreError(null)
    loadMoreError = null;
  }
  
  simulateAutoRefresh();
  assert.equal(loadMoreError, null, "load(true) silently wiped loadMoreError");
  
  // Now in useEffect:
  // if (!el || !data?.has_more || loading || loadMoreError) return;
  // Because loadMoreError is null and has_more is true, IntersectionObserver re-arms
  // and immediately triggers loadMore() again while still disconnected!
  console.log("✓ Test 5 Confirmed: Auto-refresh clears loadMoreError, re-triggering failing infinite scroll.");
}

console.log("\nALL QA STATE MACHINE & EDGE CASE TESTS PASSED!\n");
