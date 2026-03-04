"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { authCallback } from "@/lib/api";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { login } = useAuth();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state") || "";

    if (!code) {
      setError("No authorization code received from Yahoo.");
      return;
    }

    authCallback(code, state)
      .then(({ token, user }) => {
        login(token, user);
        router.push("/");
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Authentication failed");
      });
  }, [searchParams, login, router]);

  if (error) {
    return (
      <div className="mx-auto max-w-sm py-20 text-center">
        <h1 className="mb-4 text-xl font-bold text-red-600">Login Failed</h1>
        <p className="mb-6 text-gray-600">{error}</p>
        <a
          href="/login"
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
