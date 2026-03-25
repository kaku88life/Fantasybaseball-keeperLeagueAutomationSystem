/**
 * Shared custom hooks for common UI patterns.
 */
import { useState, useCallback } from "react";

/**
 * Hook for managing table sort state.
 *
 * Usage:
 *   const { sortKey, sortDir, handleSort, arrow } = useTableSort<"name" | "cost">("cost");
 */
export function useTableSort<K extends string>(defaultKey: K, defaultDir: "asc" | "desc" = "desc") {
  const [sortKey, setSortKey] = useState<K>(defaultKey);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(defaultDir);

  const handleSort = useCallback(
    (key: K) => {
      if (key === sortKey) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("desc");
      }
    },
    [sortKey],
  );

  const arrow = useCallback(
    (key: K) => (sortKey === key ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : " \u25BD"),
    [sortKey, sortDir],
  );

  return { sortKey, sortDir, handleSort, arrow } as const;
}
