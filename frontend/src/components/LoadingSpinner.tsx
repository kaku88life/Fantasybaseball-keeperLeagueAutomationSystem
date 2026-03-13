"use client";

import { useEffect, useState } from "react";

/**
 * Loading spinner with cold-start message.
 * Shows a helpful message after 5s indicating the server may be waking up.
 */
export default function LoadingSpinner({
  message = "Loading...",
  showColdStartHint = true,
}: {
  message?: string;
  showColdStartHint?: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="py-10 text-center">
      <div className="mb-4 flex justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
      </div>
      <p className="text-gray-500">{message}</p>
      {showColdStartHint && elapsed >= 5 && (
        <p className="mt-2 text-xs text-gray-400">
          伺服器可能正在啟動中 (cold start)，請稍候...
        </p>
      )}
      {showColdStartHint && elapsed >= 15 && (
        <p className="mt-1 text-xs text-gray-400">
          已等待 {elapsed} 秒，如果持續無回應請重新整理頁面
        </p>
      )}
    </div>
  );
}
