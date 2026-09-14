import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchMe, login as apiLogin, logout as apiLogout } from "../api/auth";
import { getAccessToken, setSessionExpiredHandler } from "../api/client";
import type { Me } from "../types/api";

interface AuthContextValue {
  me: Me | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setSessionExpiredHandler(() => setMe(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!getAccessToken()) {
      setIsLoading(false);
      return;
    }
    fetchMe()
      .then((result) => {
        if (!cancelled) setMe(result);
      })
      .catch(() => {
        // client.ts already cleared the tokens if this was a real 401
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      me,
      isAuthenticated: me !== null,
      isLoading,
      login: async (email: string, password: string) => {
        await apiLogin(email, password);
        setMe(await fetchMe());
      },
      logout: () => {
        apiLogout();
        setMe(null);
      },
    }),
    [me, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
