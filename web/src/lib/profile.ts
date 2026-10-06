import { api, uploadBlob } from "./api";

export type Profile = {
  id: number;
  username: string | null;
  email: string | null;
  email_verified: boolean;
  name: string;
  job_title: string;
  bio: string;
  phone: string;
  timezone: string;
  role: string;
  has_password: boolean;
  google_allowed: boolean;
  has_avatar: boolean;
  avatar_v: number | null;
  member_since: string | null;
  last_login_at: string | null;
  password_changed_at: string | null;
};

export type ProfileEdit = Partial<Pick<Profile, "name" | "job_title" | "bio" | "phone" | "timezone" | "username">>;
export type CodeSent = { ok: true; cooldown: number; sent_to?: string; message?: string };

export const getProfile = () => api<Profile>("/api/profile");
export const updateProfile = (body: ProfileEdit) => api<Profile>("/api/profile", { method: "PATCH", body });
export const uploadAvatar = (blob: Blob) => uploadBlob<Profile>("/api/profile/avatar", blob);
export const deleteAvatar = () => api<Profile>("/api/profile/avatar", { method: "DELETE" });

export const sendEmailCode = (email: string) => api<CodeSent>("/api/profile/email/otp", { method: "POST", body: { email } });
export const changeEmail = (email: string, code: string) => api<Profile>("/api/profile/email", { method: "POST", body: { email, code } });

export const sendPasswordCode = () => api<CodeSent>("/api/profile/password/otp", { method: "POST" });
export const savePassword = (body: { new_password: string; current_password?: string; code?: string }) =>
  api<{ ok: true; csrf: string; profile: Profile }>("/api/profile/password", { method: "POST", body });
export const revokeOtherSessions = () => api<{ ok: true; csrf: string }>("/api/profile/sessions/revoke", { method: "POST" });

// public (signed out)
export const forgotPassword = (identifier: string) => api<CodeSent>("/api/auth/password/forgot", { method: "POST", body: { identifier } });
export const resetPassword = (identifier: string, code: string, new_password: string) =>
  api<{ ok: true }>("/api/auth/password/reset", { method: "POST", body: { identifier, code, new_password } });

export const avatarUrl = (version: number | null | undefined) => (version ? `/api/profile/avatar?v=${version}` : null);

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------
export function initials(name: string | null | undefined, fallback = "?"): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return fallback.slice(0, 1).toUpperCase();
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function firstName(name: string | null | undefined): string {
  return (name ?? "").trim().split(/\s+/)[0] || "there";
}

const IST = "Asia/Kolkata";
export const formatDate = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "numeric", month: "short", year: "numeric" }).format(new Date(iso)) : "—";

export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const mins = Math.round((now - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 48 * 60) return `${Math.round(mins / 60)} h ago`;
  const days = Math.round(mins / 1440);
  return days < 60 ? `${days} days ago` : formatDate(iso);
}

export function timeZones(current?: string): string[] {
  const all: string[] =
    typeof Intl.supportedValuesOf === "function"
      ? Intl.supportedValuesOf("timeZone")
      : ["Asia/Kolkata", "UTC", "Europe/London", "America/New_York", "America/Los_Angeles", "Asia/Dubai", "Asia/Singapore"];
  const list = all.includes("Asia/Kolkata") ? all : ["Asia/Kolkata", ...all];
  return current && !list.includes(current) ? [current, ...list] : list;
}

// ---------------------------------------------------------------------------
// Password rules (mirrors the server: api/app/security.py password_problems)
// ---------------------------------------------------------------------------
export type PasswordCheck = { id: string; label: string; ok: boolean };

export function passwordChecks(pw: string, ...identity: (string | null | undefined)[]): PasswordCheck[] {
  const low = pw.toLowerCase();
  const leaks = identity.some((x) => {
    const piece = (x ?? "").split("@")[0].trim().toLowerCase();
    return piece.length >= 4 && low.includes(piece);
  });
  return [
    { id: "len", label: "10 or more characters", ok: pw.length >= 10 },
    { id: "mix", label: "A real mix, not one repeated character", ok: new Set(pw).size >= 5 },
    { id: "id", label: "Doesn't contain your name or username", ok: pw.length > 0 && !leaks },
  ];
}

/** 0-4: rough strength for the meter (rules + variety + length). */
export function passwordScore(pw: string, ...identity: (string | null | undefined)[]): number {
  if (!pw) return 0;
  if (!passwordChecks(pw, ...identity).every((c) => c.ok)) return pw.length >= 6 ? 1 : 0;
  let s = 2;
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  if (kinds >= 3 || pw.length >= 14) s++;
  if (pw.length >= 16 && kinds >= 3) s++;
  return Math.min(s, 4);
}
