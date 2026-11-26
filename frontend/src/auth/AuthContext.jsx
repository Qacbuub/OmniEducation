import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { adoptSession, api, tokens } from "../api/client";
import { modeForUser } from "../config/roles";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(tokens.get() || tokens.lastSignIn()));


  // Restore this tab's session on page load (a new tab first gets its own copy of the latest sign-in).
  useEffect(() => {
    let alive = true;
    // Links sent to someone else (invitation, password reset) open signed out in a new tab.
    const linkPage = ["/accept-invitation", "/reset-password"].includes(window.location.pathname);
    (linkPage ? Promise.resolve(Boolean(tokens.get())) : adoptSession()).then((ok) => {
      if (!ok) { if (alive) setLoading(false); return; }
      api.get("/auth/me/")
        .then((u) => alive && setUser(u))
        .catch(() => tokens.clear())
        .finally(() => alive && setLoading(false));
    });
    return () => { alive = false; };
  }, []);

  // The API client fires this when the refresh token is no longer valid.
  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener("omniedu:logout", onLogout);
    return () => window.removeEventListener("omniedu:logout", onLogout);
  }, []);

  const login = useCallback(async (email, password, otp) => {
    const data = await api.post("/auth/login/", { email, password, ...(otp ? { otp } : {}) });
    tokens.set({ access: data.access, refresh: data.refresh });
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    const refresh = tokens.get()?.refresh;
    if (!api.isMock && refresh) {
      // Blacklist the refresh token server-side; ignore network errors on logout.
      await api.post("/auth/logout/", { refresh }).catch(() => {});
    }
    tokens.clear();
    setUser(null);
  }, []);

  // Re-read the signed-in account after the user edits their own profile or security settings.
  const refreshUser = useCallback(() => api.get("/auth/me/").then(setUser), []);

  const value = useMemo(
    () => ({ user, loading, login, logout, refreshUser, mode: modeForUser(user) }),
    [user, loading, login, logout, refreshUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
