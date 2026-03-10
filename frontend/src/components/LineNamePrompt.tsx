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
        setError("Please enter your LINE name");
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

  const handleSkip = useCallback(() => {
    // Allow dismissing, but it will show again on next page load / refresh
    setOpen(false);
  }, []);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-bold text-gray-900">
          LINE Display Name
        </h2>
        <p className="mb-4 text-sm text-gray-600">
          Please enter your LINE display name so the commissioner can identify
          you more easily. This only needs to be done once.
        </p>

        <form onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your LINE display name"
            className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            disabled={saving}
            maxLength={50}
          />

          {error && (
            <p className="mb-3 text-sm text-red-600">{error}</p>
          )}

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="flex-1 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
            <button
              type="button"
              onClick={handleSkip}
              disabled={saving}
              className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Later
            </button>
          </div>

          <p className="mt-3 text-xs text-amber-600">
            * You will be reminded again next time you log in until you enter
            your LINE name.
          </p>
        </form>
      </div>
    </div>
  );
}
