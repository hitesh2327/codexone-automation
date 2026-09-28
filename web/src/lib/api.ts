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
  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
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
    const message = typeof detail === "string" ? detail : `Request failed (${res.status})`;
    const retry = Number(res.headers.get("Retry-After")) || undefined;
    throw new ApiError(res.status, message, retry);
  }
  return data as T;
}

export const googleLoginUrl = `${BASE}/api/auth/google/login`;
