"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const { showToast } = useToast();
  const [error, setError] = useState("");

  useEffect(() => {
    const errorParam = searchParams.get("error");
    const authOk = searchParams.get("auth");
    const fallbackToken = searchParams.get("token");

    if (errorParam) {
      setError(`Authentication failed: ${errorParam}`);
      return;
    }

    if (!authOk) {
      setError("No authentication response received.");
      return;
    }

    // Strip token from URL immediately (security: avoid token in browser history)
    if (fallbackToken && typeof window !== "undefined") {
      window.history.replaceState({}, "", "/auth/callback?auth=ok");
    }

    const authenticate = async () => {
      // Strategy 1: Cookie-based auth (works on desktop browsers)
      try {
        await refresh();
        showToast("Welcome to Fantasy Baseball 5-Man Keepers!", "success");
        router.push("/");
        return;
      } catch {
        // Cookie was likely blocked by iOS Safari ITP
      }

      if (!fallbackToken) {
        setError("Authentication cookie was blocked. Please try a different browser.");
        return;
      }

      // Strategy 2: Ask backend to set cookie via same-origin POST
      try {
        const res = await fetch(`${API_BASE}/api/auth/set-cookie`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ token: fallbackToken }),
        });
        if (res.ok) {
          await refresh();
          showToast("Welcome to Fantasy Baseball 5-Man Keepers!", "success");
          router.push("/");
          return;
        }
      } catch {
        // set-cookie also failed (LINE browser blocks cross-origin cookies entirely)
      }

      // Strategy 3: localStorage fallback (iOS Safari / LINE browser)
      // Store token in localStorage; api.ts will add it as Authorization header
      try {
        localStorage.setItem("auth_token_fallback", fallbackToken);
        await refresh();
        showToast("Welcome to Fantasy Baseball 5-Man Keepers!", "success");
        router.push("/");
      } catch (e) {
        localStorage.removeItem("auth_token_fallback");
        setError(
          e instanceof Error ? e.message : "Failed to complete authentication"
        );
      }
    };

    authenticate();
  }, [searchParams, refresh, router, showToast]);

  if (error) {
    return (
      <div className="mx-auto max-w-sm py-20 text-center">
        <h1 className="mb-4 text-xl font-bold text-red-600">Login Failed</h1>
        <p className="mb-6 text-gray-600">{error}</p>
        <a
          href="/"
          className="rounded bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-500"
        >
          Try Again
        </a>
      </div>
    );
  }

  return (
    <div className="py-20 text-center">
      <p className="text-gray-500">Authenticating with Yahoo...</p>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="py-20 text-center">
          <p className="text-gray-500">Loading...</p>
        </div>
      }
    >
      <CallbackHandler />
    </Suspense>
  );
}
