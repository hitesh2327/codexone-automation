// Config section API (api/app/routes/config.py). Secrets are write-only: the server never returns one, so
// nothing secret is ever held here beyond what the user is typing (never stored in localStorage/sessionStorage).
import { api } from "@/lib/api";

export type State = "not_set" | "checking" | "valid" | "warning" | "invalid" | "unknown" | "stale" | "unverified";

export type CheckRow = {
  name: string; label: string; ok: boolean | null; depth: "format" | "live" | "deep"; evidence: string;
  code: string | null; soft: boolean;
};

export type VerifyResult = {
  integration: string; status: "not_set" | "valid" | "warning" | "invalid" | "unknown"; depth: string;
  checks: CheckRow[]; error_class: string | null; code: string | null; message: string; hint: string; docs: string;
  evidence: Record<string, unknown>; latency_ms: number; checked_at: string; expires_at: string | null;
  implemented: boolean; reused?: boolean;
};

export type StoredCheck = Omit<VerifyResult, "integration"> & { id: number; integration: string; ran_at: string; actor: string | null };

export type FieldState = {
  name: string; label: string; secret: boolean; required: boolean; shape: string; help: string; advanced: boolean;
  is_set: boolean; source: "env" | "store" | null; in_env: boolean; in_store: boolean; overridden: boolean; conflict: boolean;
  value: string | null; fingerprint: string | null; version: number; updated_at: string | null; updated_by: string | null;
  undecryptable: boolean;
};

export type Integration = {
  name: string; title: string; tier: number; blurb: string; minutes: number; implemented: boolean; editable: boolean;
  state: State; required_set: boolean; fields: FieldState[]; check: StoredCheck | null; last_check: StoredCheck | null;
  conflict: boolean;
};

export type Condition = {
  id: string; label: string; ok: boolean | null; blocking: boolean; detail: string; integration: string | null;
  code: string | null; fix: string | null;
};

export type Readiness = {
  ready_to_generate: boolean; config_version: number; checked_at: string; conditions: Condition[];
  missing: { id: string; label: string; detail: string; fix: string | null }[]; not_covered: string[];
};

export type Overview = {
  integrations: Integration[]; readiness: Readiness; precedence: "env" | "store"; master_key: string;
  store_error: string | null; digest: string;
};

export type SaveResponse = { result: VerifyResult; cleaned: Record<string, string[]>; integration: Integration; readiness: Readiness };

export const getOverview = () => api<Overview>("/api/config");
export const getReadiness = () => api<Readiness>("/api/config/readiness");
export const getHistory = (name: string) => api<{ checks: StoredCheck[] }>(`/api/config/${name}/history`);

export const verify = (name: string, values: Record<string, string> = {}, depth: "format" | "live" | "deep" = "live", consent = false) =>
  api<{ result: VerifyResult; cleaned: Record<string, string[]> }>(`/api/config/${name}/verify`, { method: "POST", body: { values, depth, consent } });

export const save = (name: string, values: Record<string, string>, expected: Record<string, number>, saveUnverified = false) =>
  api<SaveResponse>(`/api/config/${name}`, { method: "PUT", body: { values, expected, save_unverified: saveUnverified } });

export const removeField = (name: string, field: string, version: number) =>
  api<null>(`/api/config/${name}/${field}?version=${version}`, { method: "DELETE" });

export type DetectedChat = { id: string; type: string; title: string | null };
export const detectChat = (token?: string) =>
  api<{ chats: DetectedChat[]; code: string | null; message?: string; hint?: string; docs?: string }>(
    "/api/config/telegram/detect", { method: "POST", body: { token: token || null } });
export const deleteWebhook = (token?: string) =>
  api<{ ok: true }>("/api/config/telegram/delete-webhook", { method: "POST", body: { token: token || null, confirm: true } });

// Owner-only UI preferences (/api/config/ui-preferences)
export type UiPreferences = { show_github_run: boolean };
export const getUiPreferences = () => api<UiPreferences>("/api/config/ui-preferences");
export const saveUiPreferences = (prefs: UiPreferences) =>
  api<UiPreferences>("/api/config/ui-preferences", { method: "PUT", body: prefs });

// Per-user integrations (/api/integrations)
export type KeyStatus = { set: boolean; masked: string | null };
export type TelegramMeta = { connected: boolean; using_custom_bot: boolean; default_bot_configured: boolean };
export type UserIntegrationsResponse = { values: Record<string, KeyStatus>; telegram?: TelegramMeta };

export const getUserIntegrations = () => api<UserIntegrationsResponse>("/api/integrations");
export const putUserIntegration = (key: string, value: string) =>
  api<{ key: string; version: number }>(`/api/integrations/${key}`, { method: "PUT", body: { value } });
export const deleteUserIntegration = (key: string) =>
  api<null>(`/api/integrations/${key}`, { method: "DELETE" });

export type TelegramLinkResponse = { url: string; bot_username: string; using_custom_bot: boolean; expires_in: number };
export const createTelegramLink = () =>
  api<TelegramLinkResponse>("/api/integrations/telegram/link", { method: "POST" });
export const confirmTelegramLink = () =>
  api<{ connected: boolean; chat_id?: string; chat_title?: string | null }>("/api/integrations/telegram/confirm", { method: "POST" });
export const setCustomTelegramBot = (token: string) =>
  api<{ ok: true; bot_username: string; masked: string | null }>("/api/integrations/telegram/bot", { method: "PUT", body: { token } });
export const unlinkTelegram = (includeBot = false) =>
  api<null>(`/api/integrations/telegram?include_bot=${includeBot ? "true" : "false"}`, { method: "DELETE" });
