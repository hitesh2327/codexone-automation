// Regression: a request cancelled by its caller (a newer list load replaced it) must reject with AbortError, never
// with "Can't reach the server" (pages showed a false red banner), and never resolve as a null "success" (pages
// stored null over good data and fell back to skeletons). Both were reproduced on Posts with a mocked API.
import assert from "node:assert/strict";
import { api, ApiError } from "../src/lib/api.ts";

type FakeRes = { ok: boolean; status: number; headers: Headers; json: () => Promise<unknown> };
const res = (status: number, json: () => Promise<unknown>): FakeRes => ({ ok: status < 400, status, headers: new Headers(), json });
const setFetch = (f: (url: string, init: RequestInit) => Promise<FakeRes>) => {
  (globalThis as { fetch: unknown }).fetch = f;
};

// 1. Cancelled before the response arrives
{
  const ctrl = new AbortController();
  setFetch((_u, init) => new Promise((_, reject) => {
    init.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  }));
  const p = api("/api/posts", { signal: ctrl.signal });
  ctrl.abort();
  await assert.rejects(p, (e: Error) => e.name === "AbortError" && !(e instanceof ApiError));
}

// 2. Cancelled while the body is streaming: json() fails, which must not read as an empty success
{
  const ctrl = new AbortController();
  setFetch(async () => res(200, () => { ctrl.abort(); return Promise.reject(new DOMException("aborted", "AbortError")); }));
  await assert.rejects(api("/api/posts", { signal: ctrl.signal }), (e: Error) => e.name === "AbortError");
}

// 3. A real network failure (no abort) is still the friendly ApiError
{
  setFetch(() => Promise.reject(new TypeError("Failed to fetch")));
  await assert.rejects(api("/api/posts", { signal: new AbortController().signal }),
    (e: unknown) => e instanceof ApiError && e.status === 0 && /Can't reach the server/.test(e.message));
}

// 4. Normal success and error paths are unchanged
{
  setFetch(async () => res(200, async () => ({ groups: [] })));
  assert.deepEqual(await api("/api/posts", { signal: new AbortController().signal }), { groups: [] });
  setFetch(async () => res(409, async () => ({ detail: "Already decided in Telegram" })));
  await assert.rejects(api("/api/posts/x/approve", { method: "POST" }),
    (e: unknown) => e instanceof ApiError && e.status === 409 && e.message === "Already decided in Telegram");
  setFetch(async () => res(204, async () => { throw new Error("no body"); }));
  assert.equal(await api("/api/x", { method: "DELETE" }), null);
}

console.log("api: ok");
