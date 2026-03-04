"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002";

export default function LoginPage() {
  const [loading, setLoading] = useState(false);

  const handleLogin = () => {
    setLoading(true);
    // Navigate directly to backend OAuth endpoint.
    // Backend redirects to Yahoo -> Yahoo redirects back to backend callback
    // -> backend redirects to frontend /auth/callback?token=xxx
    window.location.href = `${API_BASE}/api/auth/yahoo/login`;
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
        {loading ? "Redirecting to Yahoo..." : "Login with Yahoo"}
      </button>
      <p className="mt-6 text-xs text-gray-400">
        Your Yahoo account will be matched to your team automatically.
      </p>
    </div>
  );
}
