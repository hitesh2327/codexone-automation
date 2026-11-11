import { api, ApiError } from "./api";

export type TierMetric = {
  id: string;
  name: string;
  count: number;
  mrr_inr: number;
};

export type GstSummary = {
  taxable_inr: number;
  cgst_inr: number;
  sgst_inr: number;
  igst_inr: number;
  export_inr: number;
  total_tax_inr: number;
};

export type StuckJobSummary = {
  id: string;
  user_id: number | null;
  status: string;
  phase: string | null;
  trigger: string;
  created_at: string | null;
  started_at: string | null;
  elapsed_sec: number;
};

export type KillSwitches = {
  generation: boolean;
  publishing: boolean;
  signups: boolean;
  reason: string;
  updated_at: string | null;
  updated_by: string | null;
};

export type AdminOverview = {
  revenue: {
    mrr_inr: number;
    arr_inr: number;
    active_subscribers: number;
    total_users: number;
    total_tenants: number;
    by_tier: TierMetric[];
    by_status: Record<string, number>;
    gst_summary: GstSummary;
  };
  jobs: {
    counts_24h: Record<string, number>;
    counts_7d: Record<string, number>;
    stuck_count: number;
    stuck_jobs: StuckJobSummary[];
  };
  failures: {
    failed_publishes_count: number;
    ig_needs_reauth_count: number;
    yt_quota_errors_count: number;
  };
  youtube_quota: {
    units_used: number;
    daily_limit: number;
    utilization_pct: number;
    uploads_today: number;
    warning: boolean;
  };
  oauth_health: {
    ig_connected_tenants: number;
    yt_connected_tenants: number;
    tg_connected_tenants: number;
    ig_needs_reauth_posts: number;
    config_checks: { integration: string; status: string; message: string; ran_at: string | null }[];
  };
  kill_switches: KillSwitches;
};

export type TenantRow = {
  id: number;
  username: string | null;
  email: string | null;
  name: string;
  role: string;
  is_active: boolean;
  subscription_tier: string;
  subscription_status: string;
  subscription_renews_at: string | null;
  created_at: string | null;
  last_login_at: string | null;
  config_completed: boolean;
  billing_country: string | null;
  billing_state: string | null;
  billing_gstin: string | null;
  quota_used: { reels: number; carousels: number };
  quota_limit: { reels: number; carousels: number };
  bonus_quota: { reels: number; carousels: number };
  generation_jobs_count: number;
  cogs_inr: number;
  revenue_inr: number;
  margin_pct: number | null;
};

export type AdminJob = {
  id: string;
  trigger: string;
  requested_by: string | null;
  user_id: number | null;
  username: string | null;
  email: string | null;
  status: string;
  phase: string | null;
  failure_reason: string | null;
  message: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_sec: number | null;
  topic_title: string | null;
  is_stuck: boolean;
};

export type FailureEntry = {
  id: string;
  kind: string;
  topic: string;
  user_id: number | null;
  username: string | null;
  email: string | null;
  status: string;
  attempts: number;
  error: string | null;
  signature: string;
  platforms: Record<string, { status?: string; error?: string; attempts?: number; at?: string }>;
  publish_at: string | null;
  updated_at: string | null;
};

export type FailureGroup = {
  signature: string;
  count: number;
  sample_error: string;
  post_ids: string[];
};

export type FeatureFlag = {
  key: string;
  enabled: boolean;
  rollout_pct: number;
  description: string;
  allow_user_ids: number[];
  allow_tiers: string[];
  updated_at: string | null;
};

export type AuditEvent = {
  id: number;
  created_at: string | null;
  level: string;
  source: string;
  event: string;
  message: string;
  actor: string | null;
  user_id: number | null;
  detail: Record<string, unknown> | null;
};

export const getOverview = () => api<AdminOverview>("/api/admin/overview");

export const listTenants = (params: { q?: string; tier?: string; status?: string; limit?: number; offset?: number } = {}) => {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.tier) qs.set("tier", params.tier);
  if (params.status) qs.set("status", params.status);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return api<{ tenants: TenantRow[]; total: number; limit: number; offset: number }>(`/api/admin/tenants${suffix}`);
};

export const suspendTenant = (userId: number, active: boolean, reason: string) =>
  api<{ ok: boolean; user_id: number; is_active: boolean }>(`/api/admin/tenants/${userId}/suspend`, {
    method: "POST",
    body: { active, reason },
  });

export const grantBonusQuota = (
  userId: number,
  body: { reels: number; carousels: number; mode?: "add" | "set"; reason: string },
) =>
  api<{ ok: boolean; user_id: number; bonus_quota: { reels: number; carousels: number } }>(
    `/api/admin/tenants/${userId}/bonus-quota`,
    { method: "POST", body },
  );

export const startImpersonation = (userId: number, reason: string) =>
  api<{ ok: boolean; read_only: boolean; expires_at: string; user: unknown }>(
    `/api/admin/tenants/${userId}/impersonate`,
    { method: "POST", body: { reason } },
  );

export const exitImpersonation = () =>
  api<{ ok: boolean; user: unknown }>("/api/admin/impersonation/exit", { method: "POST" });

export const listAdminJobs = (stuckOnly = false) =>
  api<{ jobs: AdminJob[]; stuck_count: number; counts_24h: Record<string, number>; counts_7d: Record<string, number>; github_configured: boolean }>(
    `/api/admin/jobs?stuck_only=${stuckOnly}`,
  );

export const reconcileJobs = (jobIds?: string[]) =>
  api<{ ok: boolean; checked: number; reconciled: string[]; released: string[] }>("/api/admin/jobs/reconcile", {
    method: "POST",
    body: jobIds ? { job_ids: jobIds } : {},
  });

export const listFailures = () =>
  api<{ failures: FailureEntry[]; groups: FailureGroup[]; total: number }>("/api/admin/failures");

export const retryFailures = (body: { post_ids?: string[]; signature?: string }) =>
  api<{ ok: boolean; retried: string[]; count: number }>("/api/admin/failures/retry", {
    method: "POST",
    body,
  });

export const getSafety = () =>
  api<{ kill_switches: KillSwitches; publishing_enabled: boolean }>("/api/admin/safety");

export const updateSafety = (body: Partial<Pick<KillSwitches, "generation" | "publishing" | "signups" | "reason">>) =>
  api<{ kill_switches: KillSwitches; publishing_enabled: boolean }>("/api/admin/safety", {
    method: "PUT",
    body,
  });

export const listFlags = () => api<{ flags: FeatureFlag[] }>("/api/admin/flags");

export const upsertFlag = (flag: Partial<FeatureFlag> & { key: string }) =>
  api<{ flags: FeatureFlag[] }>("/api/admin/flags", {
    method: "PUT",
    body: flag,
  });

export const deleteFlag = (key: string) =>
  api<{ flags: FeatureFlag[] }>(`/api/admin/flags/${encodeURIComponent(key)}`, { method: "DELETE" });

export const listAudit = (limit = 50) => api<{ events: AuditEvent[] }>(`/api/admin/audit?limit=${limit}`);

export async function downloadGstCsv(): Promise<void> {
  const base = (import.meta.env?.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
  const res = await fetch(`${base}/api/admin/revenue/gst-export`, {
    credentials: base ? "include" : "same-origin",
  });
  if (!res.ok) throw new ApiError(res.status, `Failed to export GST CSV (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "mintly-gst-summary.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
