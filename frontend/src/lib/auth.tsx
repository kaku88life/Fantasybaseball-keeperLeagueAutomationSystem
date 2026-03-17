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
  refresh: () => Promise<void>;
  updateUser: (partial: Partial<UserInfo>) => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  logout: () => {},
  refresh: async () => {},
  updateUser: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    // Clean up any legacy localStorage tokens from before cookie migration
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
    }
    try {
      // Auth is handled by HttpOnly cookie (sent automatically via credentials: 'include')
      const u = await getCurrentUser();
      setUser(u);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
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
    // Clean up legacy localStorage token if any
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
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
