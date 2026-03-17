"use client";

import { useAuth } from "@/lib/auth";
import LoadingSpinner from "@/components/LoadingSpinner";

interface AuthGateProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Auth gate component - blocks unauthenticated users from viewing protected content.
 * If `fallback` is provided, renders it instead of the default login prompt.
 */
export default function AuthGate({ children, fallback }: AuthGateProps) {
  const { user, loading } = useAuth();

  if (loading) {
    return <LoadingSpinner />;
  }

  if (!user) {
    if (fallback) return <>{fallback}</>;

    const apiBase =
      process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002";
    return (
      <div className="mx-auto max-w-lg py-20 text-center">
        <div className="rounded-xl border border-gray-200 bg-white p-10 shadow-sm">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50">
            <svg
              className="h-7 w-7 text-indigo-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
              />
            </svg>
          </div>
          <h2 className="mb-2 text-xl font-bold text-gray-800">
            需要登入
          </h2>
          <p className="mb-6 text-sm text-gray-500">
            此頁面僅限聯盟成員閱覽，請先登入 Yahoo 帳號。
          </p>
          <a
            href={`${apiBase}/api/auth/yahoo/login`}
            className="inline-block rounded-lg bg-indigo-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Login with Yahoo
          </a>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
