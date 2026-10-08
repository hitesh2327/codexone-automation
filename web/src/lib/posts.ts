import { api } from "./api";

export type Platform = "ig" | "yt";
export type Kind = "carousel" | "reel";
export type Status =
  | "pending" | "approved" | "publishing" | "rejected" | "regenerate"
  | "replaced" | "published" | "failed" | "expired";

export type PlatformResult = {
  status: "published" | "failed" | "skipped";
  id?: string;
  url?: string;
  error?: string;
  at?: string;
  privacy?: string;
};

export type Item = {
  id: string;
  kind: Kind;
  status: Status;
  version: number;
  group_id: string;
  topic: string;
  category: string;
  date: string;
  caption: string;
  hashtags: string[];
  caption_length: number;
  media: { carousel?: string[]; reel?: string; cover?: string };
  publish_at: string;
  targets: Platform[];
  allowed_targets: Platform[];
  platforms: Partial<Record<Platform, PlatformResult>>;
  feedback: string;
  error: string | null;
  voice: string;
  created_at: string;
  decided_at: string | null;
  published_at: string | null;
  editable: boolean;
  can: { approve: boolean; reject: boolean; regen: boolean };
  source_url: string;
  youtube?: { title: string; description: string; tags: string[]; title_is_custom: boolean; description_is_custom: boolean };
  /** Set when the GitHub job behind this action couldn't be started (not configured / dispatch failed). */
  notice?: string | null;
};

/** The first "couldn't start the GitHub job" warning in an action's result (an Item, a list, or { items, notice }). */
export function noticeOf(result: unknown): string | null {
  const list = Array.isArray(result) ? result : [result];
  for (const r of list) {
    if (r && typeof r === "object" && typeof (r as { notice?: unknown }).notice === "string") {
      return (r as { notice: string }).notice;
    }
  }
  return null;
}

export type Group = {
  group_id: string;
  topic: string;
  category: string;
  date: string;
  publish_at: string;
  created_at: string;
  versions: number;
  items: { carousel: Item | null; reel: Item | null };
};

export type PostsResponse = {
  groups: Group[];
  categories: string[];
  counts: Partial<Record<Status, number>>;
  publishing_enabled: boolean;
  /** Paging (newest first, 200 groups per page by default): pass next_cursor as `cursor` for the next page. */
  total?: number;
  has_more?: boolean;
  next_cursor?: string | null;
};

export type Filters = { status?: string; platform?: string; category?: string; date_from?: string; date_to?: string; q?: string };

export function listPosts(filters: Filters, signal?: AbortSignal) {
  const params = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v) as [string, string][],
  );
  return api<PostsResponse>(`/api/posts${params.size ? `?${params}` : ""}`, { signal });
}

export const syncTelegram = () =>
  api<{ enabled: boolean; changes: { id: string; change: string }[]; error?: string }>("/api/posts/sync-telegram", { method: "POST" });

export const approveItem = (id: string, targets?: Platform[]) =>
  api<Item>(`/api/posts/${id}/approve`, { method: "POST", body: { targets } });

export const scheduleItem = (id: string, publishAt: string, targets?: Platform[]) =>
  api<Item>(`/api/posts/${id}/schedule`, { method: "POST", body: { publish_at: publishAt, targets } });

export const rejectItem = (id: string) => api<Item>(`/api/posts/${id}/reject`, { method: "POST" });

export const publishNow = (id: string, targets?: Platform[]) =>
  api<Item>(`/api/posts/${id}/publish-now`, { method: "POST", body: { targets } });

export const retryItem = (id: string, platform: Platform) =>
  api<Item>(`/api/posts/${id}/retry`, { method: "POST", body: { platform } });

export const regenerateItems = (itemIds: string[], feedback: string) =>
  api<{ items: Item[]; notice?: string | null }>("/api/posts/regenerate", { method: "POST", body: { item_ids: itemIds, feedback } });

export type EditBody = {
  caption?: string;
  hashtags?: string[];
  yt_title?: string;
  yt_description?: string;
  targets?: Platform[];
};
export const editItem = (id: string, body: EditBody) => api<Item>(`/api/posts/${id}`, { method: "PATCH", body });

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------
const IST = "Asia/Kolkata";

export function formatIST(iso: string | null | undefined, withDay = true): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: IST,
    ...(withDay ? { weekday: "short", day: "numeric", month: "short" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

/** "YYYY-MM-DDTHH:mm" in IST, for <input type="datetime-local">. */
export function toISTInput(iso: string): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    }).formatToParts(new Date(iso)).map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour === "24" ? "00" : parts.hour}:${parts.minute}`;
}

/** datetime-local value (interpreted as IST) -> ISO with +05:30. */
export const fromISTInput = (value: string) => `${value}:00+05:30`;

export const PLATFORM_LABEL: Record<Platform, string> = { ig: "Instagram", yt: "YouTube" };

export const STATUS_LABEL: Record<Status, string> = {
  pending: "Waiting for approval",
  approved: "Approved",
  publishing: "Publishing…",
  rejected: "Rejected",
  regenerate: "Regenerating…",
  replaced: "Replaced",
  published: "Published",
  failed: "Failed",
  expired: "Expired",
};

export const ACTIVE_STATUSES: Status[] = ["publishing", "regenerate"];
