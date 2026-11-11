import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { api, ApiError, setCsrfToken } from "./api";

export type User = {
  id: number;
  username: string | null;
  email: string | null;
  name: string;
  csrf: string;
  has_password?: boolean;
  avatar_v?: number | null;
  config_completed?: boolean;
  role?: "admin" | "client" | "owner";
  subscription_tier?: string;
  subscription_status?: string;
  impersonated_by?: number | null;
  impersonation_read_only?: boolean;
  impersonation_expires_at?: string | null;
  impersonation_reason?: string | null;
  taste?: {
    niche?: string;
    tone?: string;
    content_type?: string;
    aesthetic?: string;
    template_style?: string;
    target_audience?: string;
    prompt_instructions?: string;
    default_targets?: string[];
    default_language?: "en" | "hi";
    default_post_format?: "carousel" | "image_reel";
  };
  cadence?: {
    posts_per_day?: number;
    slots?: string[];
    schedule_mode?: "uniform" | "weekly" | "ai";
    weekly_slots?: Record<string, string[] | null>;
    ai_schedule?: Record<string, string[]>;
    ai_suggested_at?: string;
  };
};

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  signup: (data: { username: string; email: string; password: string; name?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<User | null>;
  applySessionUser: (u: User | null) => void;
  /** Merge fresh details (name, picture version...) into the signed-in user, e.g. after a profile edit. */
  patchUser: (p: Partial<User>) => void;
  /** Use a new CSRF token (the server issues one when the password changes and the session is renewed). */
  setCsrf: (token: string) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const accept = useCallback((u: User | null) => {
    setCsrfToken(u?.csrf ?? null);
    setUser(u);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const u = await api<User>("/api/auth/me");
      accept(u);
      return u;
    } catch {
      accept(null);
      return null;
    }
  }, [accept]);

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = useCallback(async (username: string, password: string) => {
    accept(await api<User>("/api/auth/login", { method: "POST", body: { username, password } }));
  }, [accept]);

  const signup = useCallback(async (data: { username: string; email: string; password: string; name?: string }) => {
    accept(await api<User>("/api/auth/signup", { method: "POST", body: data }));
  }, [accept]);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) throw e;
    }
    accept(null);
  }, [accept]);

  const patchUser = useCallback((p: Partial<User>) => setUser((u) => (u ? { ...u, ...p } : u)), []);
  const setCsrf = useCallback((token: string) => {
    setCsrfToken(token);
    setUser((u) => (u ? { ...u, csrf: token } : u));
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, login, signup, logout, refreshUser, applySessionUser: accept, patchUser, setCsrf }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Renders children only when signed in; otherwise redirects to /login. If config is incomplete, redirects to /config. */
export function RequireAuth({ children, allowUnconfigured = false }: { children: ReactNode; allowUnconfigured?: boolean }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center text-muted-foreground" role="status">
        Loading…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (
    user.config_completed === false &&
    !allowUnconfigured &&
    !user.impersonated_by &&
    !location.pathname.startsWith("/config") &&
    !location.pathname.startsWith("/profile") &&
    !location.pathname.startsWith("/subscription") &&
    !location.pathname.startsWith("/admin")
  ) {
    return <Navigate to="/config" replace state={{ onboarding: true }} />;
  }
  return <>{children}</>;
}

/** Strict RBAC gate for /admin: redirects non-admin users cleanly to /dashboard. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center text-muted-foreground" role="status">
        Loading…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  const isAdmin = (user.role === "owner" || user.role === "admin") && !user.impersonated_by;
  if (!isAdmin) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
