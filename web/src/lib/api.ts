// Thin fetch wrapper: sends the session cookie, adds the CSRF header on writes, and turns
// error responses into ApiError with the server's message.

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

let csrfToken: string | null = null;
export const setCsrfToken = (token: string | null) => {
  csrfToken = token;
};

export class ApiError extends Error {
  status: number;
  retryAfter?: number;
  /** Machine-readable reason, when the server sends {detail: {code, message, ...}}. */
  code?: string;
  /** The rest of that detail object (e.g. the running job for "job_active"). */
  data?: Record<string, unknown>;
  constructor(status: number, message: string, retryAfter?: number, code?: string, data?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
    this.code = code;
    this.data = data;
  }
}

type Options = { method?: string; body?: unknown; signal?: AbortSignal };

export async function api<T = unknown>(path: string, { method = "GET", body, signal }: Options = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: BASE ? "include" : "same-origin",
      signal,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const retry = Number(res.headers.get("Retry-After")) || undefined;
    if (detail && typeof detail === "object" && !Array.isArray(detail) && typeof (detail as { message?: unknown }).message === "string") {
      const { message, code, ...rest } = detail as { message: string; code?: string };
      throw new ApiError(res.status, message, retry, code, rest);
    }
    // FastAPI validation errors arrive as a list of {msg}
    const first = Array.isArray(detail) ? (detail[0] as { msg?: unknown } | undefined)?.msg : undefined;
    const message = typeof detail === "string" ? detail
      : typeof first === "string" ? first.replace(/^Value error, /, "")
      : `Request failed (${res.status})`;
    throw new ApiError(res.status, message, retry);
  }
  return data as T;
}

export const googleLoginUrl = `${BASE}/api/auth/google/login`;

/** Upload raw bytes (e.g. a cropped picture) with the session cookie and CSRF header. */
export async function uploadBlob<T = unknown>(path: string, blob: Blob): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "Content-Type": blob.type || "application/octet-stream" };
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method: "POST", headers, body: blob, credentials: BASE ? "include" : "same-origin" });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return data as T;
}
