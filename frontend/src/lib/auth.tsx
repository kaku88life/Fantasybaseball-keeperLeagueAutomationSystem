"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { UserInfo } from "@/types";
import { getCurrentUser } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

interface AuthContextType {
  user: UserInfo | null;
  loading: boolean;
  logout: () => void;
  refresh: () => Promise<UserInfo>;
  updateUser: (partial: Partial<UserInfo>) => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  logout: () => {},
  refresh: async () => { throw new Error("not initialized"); },
  updateUser: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (): Promise<UserInfo> => {
    // Clean up legacy localStorage token (old key from before cookie migration)
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
    }
    try {
      // Auth: HttpOnly cookie (primary) or Authorization header via localStorage fallback (iOS)
      const u = await getCurrentUser();
      setUser(u);
      return u;
    } catch (err) {
      setUser(null);
      throw err; // Re-throw so callers (like callback page) can detect failure
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => {}); // Initial load: ignore auth errors (user just not logged in)
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      // Call backend to clear HttpOnly cookie
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Ignore network errors on logout
    }
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
      localStorage.removeItem("auth_token_fallback");
    }
    setUser(null);
  }, []);

  const updateUser = useCallback((partial: Partial<UserInfo>) => {
    setUser((prev) => (prev ? { ...prev, ...partial } : prev));
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, logout, refresh, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
