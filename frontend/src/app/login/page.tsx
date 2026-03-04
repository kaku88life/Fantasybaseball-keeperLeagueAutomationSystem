"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginWithYahoo, exchangeCode } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { loginWithToken } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showCodeInput, setShowCodeInput] = useState(false);
  const [authCode, setAuthCode] = useState("");
  const [exchanging, setExchanging] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    setError("");
    try {
      const { auth_url } = await loginWithYahoo();
      window.open(auth_url, "_blank");
      setShowCodeInput(true);
      setLoading(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
      setLoading(false);
    }
  };

  const handleExchangeCode = async () => {
    if (!authCode.trim()) return;
    setExchanging(true);
    setError("");
    try {
      const { token } = await exchangeCode(authCode.trim());
      await loginWithToken(token);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Code exchange failed");
      setExchanging(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm py-20 text-center">
      <h1 className="mb-2 text-2xl font-bold">Login</h1>
      <p className="mb-8 text-gray-600">
        Sign in with your Yahoo account to access the keeper league system.
      </p>

      {!showCodeInput ? (
        <>
          <button
            onClick={handleLogin}
            disabled={loading}
            className="w-full rounded-lg bg-purple-600 px-6 py-3 text-white hover:bg-purple-500 disabled:opacity-50"
          >
            {loading ? "Opening Yahoo..." : "Login with Yahoo"}
          </button>
          <p className="mt-6 text-xs text-gray-400">
            Your Yahoo account will be matched to your team automatically.
          </p>
        </>
      ) : (
        <div className="space-y-4 text-left">
          <div className="rounded-lg bg-blue-50 p-4 text-sm text-blue-800">
            <p className="font-semibold mb-1">Step 1: Yahoo login opened in new tab</p>
            <p>Login and authorize the app on Yahoo.</p>
            <p className="font-semibold mt-3 mb-1">Step 2: Copy the authorization code</p>
            <p>After authorizing, Yahoo will display a code. Copy it and paste below.</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Authorization Code
            </label>
            <input
              type="text"
              value={authCode}
              onChange={(e) => setAuthCode(e.target.value)}
              placeholder="Paste the code from Yahoo here"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
              onKeyDown={(e) => e.key === "Enter" && handleExchangeCode()}
            />
          </div>

          <button
            onClick={handleExchangeCode}
            disabled={exchanging || !authCode.trim()}
            className="w-full rounded-lg bg-purple-600 px-6 py-3 text-white hover:bg-purple-500 disabled:opacity-50"
          >
            {exchanging ? "Verifying..." : "Submit Code"}
          </button>

          <button
            onClick={() => { setShowCodeInput(false); setAuthCode(""); setError(""); }}
            className="w-full text-sm text-gray-500 hover:text-gray-700"
          >
            Back
          </button>
        </div>
      )}

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
    </div>
  );
}
