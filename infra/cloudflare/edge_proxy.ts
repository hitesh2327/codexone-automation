/**
 * Cloudflare Edge Proxy Worker for CodexOne Authentication & Security
 *
 * Responsibilities:
 * 1. Enforces same-origin routing for /api/*, eliminating cross-subdomain cookie blocks for __Host-cx_session.
 * 2. Injects the shared secret `X-Origin-Verify` to authenticate traffic reaching the origin, failing closed if unset.
 * 3. Sanitizes spoofable client headers (X-Origin-Verify, True-Client-IP, X-Forwarded-For).
 * 4. Rewrites the Host header to match the upstream target, preventing cloud proxy mismatch errors.
 * 5. Bypasses edge cache on all API requests and enforces multi-CDN zero-store headers on sensitive routes.
 * 6. Ensures real visitor IP is forwarded via CF-Connecting-IP.
 * 7. Streams raw request body to preserve webhook signature verification (Razorpay/Stripe HMAC).
 * 8. Returns structured JSON errors (502/504) on upstream timeouts rather than raw HTML error pages.
 * 9. Uses ctx.waitUntil() for asynchronous metrics and payment audit logging.
 */

export interface Env {
  ORIGIN_URL: string;
  ORIGIN_VERIFY: string;
}

function syntheticJsonError(status: number, code: string, message: string): Response {
  return new Response(
    JSON.stringify({
      detail: {
        code,
        message,
      },
    }),
    {
      status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "CDN-Cache-Control": "no-store",
        "Cloudflare-CDN-Cache-Control": "no-store",
        "Surrogate-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
      },
    }
  );
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Clone headers to mutate
    const originHeaders = new Headers(request.headers);

    // 1. Sanitize spoofable client-supplied headers
    originHeaders.delete("X-Origin-Verify");
    originHeaders.delete("True-Client-IP");
    originHeaders.delete("X-Forwarded-For");

    // 2. Inject origin verification secret so backend accepts the connection (fail closed if unset)
    if (!env.ORIGIN_VERIFY) {
      return syntheticJsonError(
        502,
        "gateway_misconfigured",
        "Origin verification secret is not configured at edge proxy."
      );
    }
    originHeaders.set("X-Origin-Verify", env.ORIGIN_VERIFY);

    // 3. Ensure CF-Connecting-IP is forwarded accurately
    const clientIp = request.headers.get("CF-Connecting-IP");
    if (clientIp) {
      originHeaders.set("CF-Connecting-IP", clientIp);
    }

    // 4. Construct upstream request and rewrite Host header to target origin
    const originTarget = new URL(url.pathname + url.search, env.ORIGIN_URL);
    originHeaders.set("Host", originTarget.host);

    const originRequest = new Request(originTarget.toString(), {
      method: request.method,
      headers: originHeaders,
      // Pass raw ReadableStream without buffering to preserve HMAC signature for payment webhooks
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual",
    });

    // 5. Cloudflare-specific edge caching controls: strictly bypass cache for /api/ routes
    const cfOptions: RequestInitCfProperties = {
      cacheEverything: false,
      cacheTtl: -1,
    };

    // 6. Execute origin fetch with graceful JSON degradation on upstream failure/timeout
    let response: Response;
    try {
      response = await fetch(originRequest, { cf: cfOptions });
    } catch (error) {
      return syntheticJsonError(
        504,
        "gateway_timeout",
        "Upstream origin service is unreachable or timed out. Please try again in a few moments."
      );
    }

    // 7. Enforce multi-CDN and edge cache restrictions on API responses
    const responseHeaders = new Headers(response.headers);
    if (url.pathname.startsWith("/api/")) {
      responseHeaders.set("CDN-Cache-Control", "no-store");
      responseHeaders.set("Cloudflare-CDN-Cache-Control", "no-store");
      responseHeaders.set("Surrogate-Control", "no-store");
      if (!response.headers.has("ETag")) {
        responseHeaders.set("Cache-Control", "no-store, no-cache, must-revalidate, private");
        responseHeaders.set("Pragma", "no-cache");
      }
    }

    // 8. Asynchronous background auditing/metrics via ctx.waitUntil
    ctx.waitUntil(
      (async () => {
        if (url.pathname.startsWith("/api/subscription/")) {
          if (response.status >= 400) {
            console.warn(`[Payment Audit] ${request.method} ${url.pathname} -> ${response.status}`);
          }
        } else if (
          response.status === 403 ||
          (response.status === 404 && (url.pathname.startsWith("/api/posts/") || url.pathname.startsWith("/api/generate/jobs/")))
        ) {
          console.warn(`[Access Audit] Unauthorized or cross-tenant attempt: ${request.method} ${url.pathname} -> ${response.status} from ${clientIp || "unknown"}`);
        } else if (response.status >= 500) {
          console.error(`Upstream error: ${request.method} ${url.pathname} -> ${response.status}`);
        }
      })().catch((err) => {
        console.error("Telemetry error in ctx.waitUntil:", err);
      })
    );

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};
