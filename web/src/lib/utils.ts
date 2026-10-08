export { cn } from "cn"

const SAFE_HOSTS = new Set([
  "instagram.com", "www.instagram.com",
  "youtube.com", "www.youtube.com", "youtu.be",
  "res.cloudinary.com",
  "github.com",
]);

/**
 * Return `url` only when it is https: and (optionally) from an allowed host.
 * Pass `anyHttps = true` to skip the host check (e.g. platform-agnostic links).
 */
export function safeHref(url: string | null | undefined, anyHttps = false): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    if (u.protocol !== "https:") return undefined;
    if (!anyHttps && !SAFE_HOSTS.has(u.hostname)) return undefined;
    return url;
  } catch {
    return undefined;
  }
}
