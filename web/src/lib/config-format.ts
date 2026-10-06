// Pure helpers for the Config page (no React, no "@/" imports: web/tests/config.test.mts runs them under Node).
// The server is authoritative (src/verify/base.py clean_value + each verifier's format checks); these mirror
// them so the page can react while you type, before anything is sent.

export type FieldHint = { level: "error" | "warn" | "ok"; text: string };

const INVISIBLE = /\u200b|\u200c|\u200d|\u2060|\ufeff|\u00ad/g;
const ALIASES: Record<string, string[]> = { CLOUDINARY_URL: ["COUDNARY_API_ENV_VAR", "CLOUDINARY_API_ENV_VAR"] };

/** Strip what copy/paste adds: invisible characters, spaces/newlines, quotes, `NAME=` / `export NAME=`. */
export function cleanValue(raw: string, name = ""): { value: string; notes: string[] } {
  const notes: string[] = [];
  let v = raw.normalize("NFC");
  if (v.replace(INVISIBLE, "") !== v) { // (no .test(): a /g regex keeps state between calls)
    v = v.replace(INVISIBLE, "");
    notes.push("removed invisible characters");
  }
  for (let i = 0; i < 3; i++) {
    const before = v;
    const t = v.trim();
    if (t !== v && !notes.includes("removed surrounding spaces or line breaks")) notes.push("removed surrounding spaces or line breaks");
    v = t;
    if (v.toLowerCase().startsWith("export ")) v = v.slice(7).trimStart();
    if (name) {
      for (const n of [name, ...(ALIASES[name] ?? [])]) {
        if (v.toUpperCase().startsWith(`${n.toUpperCase()}=`)) {
          v = v.slice(n.length + 1).trim();
          notes.push(`removed the leading ${n}=`);
          break;
        }
      }
    }
    if (v.length >= 2 && v[0] === v[v.length - 1] && `"'\``.includes(v[0])) {
      v = v.slice(1, -1);
      if (!notes.includes("removed the quotes")) notes.push("removed the quotes");
    }
    if (v === before) break;
  }
  if (name === "GITHUB_REPOSITORY") {
    const m = /^(?:https?:\/\/)?(?:www\.)?github\.com\/([^/\s]+)\/([^/\s?#]+?)(?:\.git)?\/?(?:[?#].*)?$/i.exec(v);
    if (m) {
      v = `${m[1]}/${m[2]}`;
      notes.push("used owner/name from the link");
    }
  }
  return { value: v, notes };
}

// eslint-disable-next-line no-control-regex
const BAD_CHARS = /[\s\u0000-\u001f\u007f-\u009f]/;
const MODEL = /^[a-z0-9][a-z0-9.-]{0,79}$/;
export const REPO = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\/[A-Za-z0-9._-]{1,100}$/;
const TG_TOKEN = /^\d{3,}:[A-Za-z0-9_-]{20,}$/;
const CHAT = /^-?\d{1,20}$/;
const CLOUDINARY = /^cloudinary:\/\/[^:@\s/]+:[^@\s/]+@[A-Za-z0-9_-]{1,100}(?:\?\S*)?$/i;

/** Instant, local format check (L1). `null` = nothing to say yet (empty field). */
export function checkField(name: string, value: string): FieldHint | null {
  const v = value;
  if (!v) return null;
  switch (name) {
    case "GEMINI_API_KEY":
      return BAD_CHARS.test(v) ? { level: "error", text: "Contains spaces or line breaks. Paste only the key." } : { level: "ok", text: "Looks like a key" };
    case "GEMINI_MODEL":
      return MODEL.test(v.replace(/^models\//, "")) ? { level: "ok", text: "Valid model name" } : { level: "error", text: "Letters, digits, dots and dashes only (e.g. gemini-flash-latest)." };
    case "GEMINI_FALLBACK_MODELS": {
      const bad = v.split(",").map((m) => m.trim().replace(/^models\//, "")).filter((m) => m && !MODEL.test(m));
      return bad.length ? { level: "error", text: `Not a model name: ${bad[0]}` } : { level: "ok", text: "Valid model names" };
    }
    case "TG_BOT_TOKEN":
      return TG_TOKEN.test(v) ? { level: "ok", text: "Looks like a bot token" } : { level: "error", text: "Expected digits, a colon, then letters (as @BotFather sends it)." };
    case "TG_CHAT_ID":
      return CHAT.test(v) ? { level: "ok", text: v.startsWith("-") ? "A group or channel" : "A private chat" } : { level: "error", text: "A whole number (groups start with -). Use Detect my chat." };
    case "CLOUDINARY_URL":
      if (/[<>]/.test(v)) return { level: "error", text: "Replace <your_api_key> and <your_api_secret> with the real key and secret first." };
      if (!/^cloudinary:\/\//i.test(v)) return { level: "error", text: "Should start with cloudinary:// (copy the whole API environment variable)." };
      return CLOUDINARY.test(v) ? { level: "ok", text: `Cloud: ${v.split("@").pop()?.split("?")[0]}` } : { level: "error", text: "Expected cloudinary://<key>:<secret>@<cloud name>." };
    case "GITHUB_REPOSITORY":
      return REPO.test(v) && !v.includes("..") ? { level: "ok", text: "owner/name" } : { level: "error", text: "Write it as owner/name, e.g. acme/content-automation." };
    case "GITHUB_DISPATCH_TOKEN":
      if (BAD_CHARS.test(v)) return { level: "error", text: "Contains spaces or line breaks. Paste only the token." };
      if (v.startsWith("ghp_")) return { level: "warn", text: "A classic token reaches every repository you can. A fine-grained one (github_pat_…) is safer." };
      return { level: "ok", text: v.startsWith("github_pat_") ? "Fine-grained token" : "Token" };
    default:
      return BAD_CHARS.test(v) ? { level: "error", text: "Contains spaces or line breaks." } : null;
  }
}

/** Card states the API returns, with their display label and colour role (status is never colour-only). */
export const STATE_LABEL: Record<string, string> = {
  not_set: "Not set", checking: "Checking", valid: "Valid", warning: "Warning", invalid: "Invalid",
  unknown: "Unknown", stale: "Changed, verify again", unverified: "Not verified",
};
export const STATE_ROLE: Record<string, "ok" | "wait" | "bad" | "go" | "idle"> = {
  valid: "ok", warning: "wait", invalid: "bad", checking: "go", unknown: "wait", stale: "wait", unverified: "idle", not_set: "idle",
};

/** "just now", "5m ago", "3h ago", "2d ago". */
export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/** The anchor id of a troubleshooting entry (matches the server's docs links: /config/guide/errors#<id>). */
export const errorAnchor = (code: string) => code.replace(/\./g, "-");
