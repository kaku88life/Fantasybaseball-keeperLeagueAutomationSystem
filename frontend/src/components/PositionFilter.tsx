"use client";

import { useMemo } from "react";

// Position filter groups
export const POSITION_GROUPS = [
  { label: "全部", value: "ALL" },
  { label: "All Batters", value: "BATTER" },
  { label: "All Pitchers", value: "PITCHER" },
  { label: "C", value: "C" },
  { label: "1B", value: "1B" },
  { label: "2B", value: "2B" },
  { label: "3B", value: "3B" },
  { label: "SS", value: "SS" },
  { label: "IF", value: "IF" },
  { label: "OF", value: "OF" },
  { label: "SP", value: "SP" },
  { label: "RP", value: "RP" },
  { label: "P", value: "P" },
] as const;

/**
 * Check if a player position string matches a given filter value.
 */
const BATTER_POSITIONS = ["C", "1B", "2B", "3B", "SS", "IF", "LF", "CF", "RF", "OF", "UTIL", "DH"];
const PITCHER_POSITIONS = ["SP", "RP", "P"];

export function matchesPosition(positionStr: string, filter: string): boolean {
  if (filter === "ALL") return true;
  const positions = positionStr
    .split(",")
    .map((s) => s.trim().toUpperCase());

  if (filter === "BATTER") {
    // Player is a batter if ANY of their positions is a batter position
    // AND none of their positions is a pitcher position (exclude two-way like Ohtani from pure batters)
    // Actually, include anyone who has at least one batter position
    return positions.some((p) => BATTER_POSITIONS.includes(p)) ||
           (!positions.some((p) => PITCHER_POSITIONS.includes(p)) && positions.length > 0);
  }
  if (filter === "PITCHER") {
    return positions.some((p) => PITCHER_POSITIONS.includes(p));
  }
  if (filter === "IF") {
    return positions.some((p) => ["C", "1B", "2B", "3B", "SS", "IF"].includes(p));
  }
  if (filter === "OF") {
    return positions.some((p) => ["LF", "CF", "RF", "OF"].includes(p));
  }
  if (filter === "P") {
    return positions.some((p) => PITCHER_POSITIONS.includes(p));
  }
  return positions.includes(filter);
}

interface PositionFilterProps {
  /** Array of items with a `position` string field */
  items: Array<{ position: string }>;
  /** Current filter value */
  value: string;
  /** Callback when filter changes */
  onChange: (v: string) => void;
  /** Whether to show count badges (default: true) */
  showCounts?: boolean;
}

/**
 * Shared position filter button group.
 * Works with any array of items that have a `position` field.
 */
export default function PositionFilter({
  items,
  value,
  onChange,
  showCounts = true,
}: PositionFilterProps) {
  // Count items per position group
  const counts = useMemo(() => {
    const map: Record<string, number> = { ALL: items.length };
    // Track per-item batter/pitcher classification to avoid double counting
    for (const item of items) {
      const positions = item.position
        .split(",")
        .map((s) => s.trim());
      let isBatter = false;
      let isPitcherFlag = false;
      for (const pos of positions) {
        if (!pos) continue;
        map[pos] = (map[pos] || 0) + 1;
        // Aggregate groups
        if (["C", "1B", "2B", "3B", "SS"].includes(pos)) {
          map["IF"] = (map["IF"] || 0) + 1;
        }
        if (["LF", "CF", "RF", "OF"].includes(pos)) {
          map["OF"] = (map["OF"] || 0) + 1;
        }
        if (["SP", "RP", "P"].includes(pos)) {
          map["P"] = (map["P"] || 0) + 1;
          isPitcherFlag = true;
        }
        if (BATTER_POSITIONS.includes(pos.toUpperCase())) {
          isBatter = true;
        }
      }
      // Non-pitcher with positions = batter
      if (!isPitcherFlag && positions.filter(Boolean).length > 0) isBatter = true;
      if (isBatter) map["BATTER"] = (map["BATTER"] || 0) + 1;
      if (isPitcherFlag) map["PITCHER"] = (map["PITCHER"] || 0) + 1;
    }
    return map;
  }, [items]);

  return (
    <div className="flex flex-wrap gap-1">
      {POSITION_GROUPS.map((pg) => {
        const count = counts[pg.value] || 0;
        if (pg.value !== "ALL" && count === 0) return null;
        const isActive = value === pg.value;
        return (
          <button
            key={pg.value}
            type="button"
            onClick={() => onChange(pg.value)}
            className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
              isActive
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {pg.label}
            {showCounts && pg.value !== "ALL" && (
              <span
                className={`ml-1 ${isActive ? "text-indigo-200" : "text-gray-400"}`}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
