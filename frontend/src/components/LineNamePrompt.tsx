"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { updateLineName } from "@/lib/api";

/**
 * LINE name prompt modal.
 * Shows when user is logged in but has not set their LINE display name.
 * Persists on every page load until the user enters their name.
 */
export default function LineNamePrompt() {
  const { user, updateUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Show prompt when user is logged in but has no line_name
  useEffect(() => {
    if (user && !user.line_name) {
      setOpen(true);
    } else {
      setOpen(false);
    }
  }, [user]);

  // Auto-focus input when modal opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = name.trim();
      if (!trimmed) {
        setError("請輸入你的 LINE 名稱");
        return;
      }
      setSaving(true);
      setError("");
      try {
        const result = await updateLineName(trimmed);
        updateUser({ line_name: result.line_name });
        setOpen(false);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to save";
        setError(msg);
      } finally {
        setSaving(false);
      }
    },
    [name, updateUser],
  );

  // No skip allowed - LINE name is mandatory for identification

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-bold text-gray-900">
          LINE 顯示名稱
        </h2>
        <p className="mb-4 text-sm text-gray-600">
          請輸入你的 LINE 顯示名稱，方便 Commissioner
          辨識你的身份並指派隊伍。<strong className="text-red-600">必填</strong>，只需要設定一次。
        </p>

        <form onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="你的 LINE 顯示名稱"
            className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            disabled={saving}
            maxLength={50}
          />

          {error && (
            <p className="mb-3 text-sm text-red-600">{error}</p>
          )}

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="flex-1 rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {saving ? "儲存中..." : "確認送出"}
            </button>
          </div>

          <p className="mt-3 text-xs text-red-500">
            * 必須輸入 LINE 名稱後才能使用系統功能。
          </p>
        </form>
      </div>
    </div>
  );
}
