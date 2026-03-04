"use client";

import { useState } from "react";
import { loginWithYahoo } from "@/lib/api";

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async () => {
    setLoading(true);
    setError("");
    try {
      const { auth_url } = await loginWithYahoo();
      window.location.href = auth_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm py-20 text-center">
      <h1 className="mb-2 text-2xl font-bold">Login</h1>
      <p className="mb-8 text-gray-600">
        Sign in with your Yahoo account to access the keeper league system.
      </p>

      <button
        onClick={handleLogin}
        disabled={loading}
        className="w-full rounded-lg bg-purple-600 px-6 py-3 text-white hover:bg-purple-500 disabled:opacity-50"
      >
        {loading ? "Redirecting..." : "Login with Yahoo"}
      </button>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <p className="mt-6 text-xs text-gray-400">
        Your Yahoo account will be matched to your team automatically.
      </p>
    </div>
  );
}
