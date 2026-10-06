import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { api, ApiError, setCsrfToken } from "./api";

export type User = {
  id: number; username: string | null; email: string | null; name: string; csrf: string;
  has_password?: boolean; avatar_v?: number | null;
};

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Merge fresh details (name, picture version...) into the signed-in user, e.g. after a profile edit. */
  patchUser: (p: Partial<User>) => void;
  /** Use a new CSRF token (the server issues one when the password changes and the session is renewed). */
  setCsrf: (token: string) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const accept = (u: User | null) => {
    setCsrfToken(u?.csrf ?? null);
    setUser(u);
  };

  useEffect(() => {
    api<User>("/api/auth/me")
      .then(accept)
      .catch(() => accept(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    accept(await api<User>("/api/auth/login", { method: "POST", body: { username, password } }));
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) throw e;
    }
    accept(null);
  }, []);

  const patchUser = useCallback((p: Partial<User>) => setUser((u) => (u ? { ...u, ...p } : u)), []);
  const setCsrf = useCallback((token: string) => {
    setCsrfToken(token);
    setUser((u) => (u ? { ...u, csrf: token } : u));
  }, []);

  return <AuthContext.Provider value={{ user, loading, login, logout, patchUser, setCsrf }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Renders children only when signed in; otherwise redirects to /login (remembering where you were). */
export function RequireAuth({ children }: { children: ReactNode }) {
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
  return <>{children}</>;
}
