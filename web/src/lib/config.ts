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
