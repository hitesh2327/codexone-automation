/**
 * Cloudflare Edge Proxy Worker for CodexOne Authentication & Security
 *
 * Responsibilities:
 * 1. Enforces same-origin routing for /api/*, eliminating cross-subdomain cookie blocks for __Host-cx_session.
 * 2. Injects the shared secret `X-Origin-Verify` to authenticate traffic reaching the origin.
 * 3. Bypasses edge cache on all API requests and cookie-authenticated sessions.
 * 4. Ensures real visitor IP is forwarded via CF-Connecting-IP.
 * 5. Uses ctx.waitUntil() for asynchronous metrics and logging.
 */

export interface Env {
  ORIGIN_URL: string;
  ORIGIN_VERIFY: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Clone headers to mutate
    const originHeaders = new Headers(request.headers);

    // 1. Inject origin verification secret so backend accepts the connection
    if (env.ORIGIN_VERIFY) {
      originHeaders.set("X-Origin-Verify", env.ORIGIN_VERIFY);
    }

    // 2. Ensure CF-Connecting-IP is present
    const clientIp = request.headers.get("CF-Connecting-IP");
    if (clientIp) {
      originHeaders.set("CF-Connecting-IP", clientIp);
    }

    // Construct upstream request to the backend origin
    const originTarget = new URL(url.pathname + url.search, env.ORIGIN_URL);
    const originRequest = new Request(originTarget.toString(), {
      method: request.method,
      headers: originHeaders,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual",
    });

    // 3. Cloudflare-specific edge caching controls: bypass cache for /api/ routes
    const cfOptions: RequestInitCfProperties = {
      cacheEverything: false,
      cacheTtl: 0,
    };

    // Execute origin fetch
    const response = await fetch(originRequest, { cf: cfOptions });

    // Clone response headers to enforce edge cache restrictions on the browser
    const responseHeaders = new Headers(response.headers);
    if (url.pathname.startsWith("/api/")) {
      responseHeaders.set("Cache-Control", "no-store, no-cache, must-revalidate, private");
      responseHeaders.set("Pragma", "no-cache");
    }

    // 4. Asynchronous background auditing/metrics via ctx.waitUntil
    ctx.waitUntil(
      (async () => {
        // Optional background logging or Tail Worker telemetry
        if (response.status >= 500) {
          console.error(`Upstream error: ${request.method} ${url.pathname} -> ${response.status}`);
        }
      })()
    );

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};
