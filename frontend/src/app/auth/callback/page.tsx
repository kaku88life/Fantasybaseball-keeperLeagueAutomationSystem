"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getCurrentUser } from "@/lib/api";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { loginWithToken } = useAuth();
  const [error, setError] = useState("");

  useEffect(() => {
    const token = searchParams.get("token");
    const errorParam = searchParams.get("error");

    if (errorParam) {
      setError(`Authentication failed: ${errorParam}`);
      return;
    }

    if (!token) {
      setError("No authentication token received.");
      return;
    }

    // Save token, fetch user info, then redirect to home
    loginWithToken(token)
      .then(() => {
        router.push("/");
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load user info");
      });
  }, [searchParams, loginWithToken, router]);

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
