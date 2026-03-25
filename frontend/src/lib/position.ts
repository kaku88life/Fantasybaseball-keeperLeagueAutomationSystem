/**
 * Shared position classification utilities.
 *
 * Used by: players/page.tsx, draft-strategy/page.tsx, PositionFilter.tsx, analytics/page.tsx
 */

/** All pitcher position codes (Yahoo + Pipeline/prospect format) */
export const PITCHER_POSITIONS = new Set(["SP", "RP", "P", "LHP", "RHP"]);

/** All batter position codes */
export const BATTER_POSITIONS = new Set([
  "C", "1B", "2B", "3B", "SS", "IF", "LF", "CF", "RF", "OF", "UTIL", "DH",
]);

/**
 * Check if a position string contains any pitcher position.
 * Handles comma-separated multi-position strings (e.g. "SP,RP").
 */
export function isPitcher(position: string): boolean {
  if (!position) return false;
  return position
    .split(",")
    .some((s) => PITCHER_POSITIONS.has(s.trim().toUpperCase()));
}

/**
 * Check if a position string represents a batter (not exclusively pitcher).
 */
export function isBatter(position: string): boolean {
  if (!position) return false;
  return !position
    .split(",")
    .every((s) => PITCHER_POSITIONS.has(s.trim().toUpperCase()));
}

/**
 * Categorize a position into a broad group for analytics.
 * Returns the primary position or "Unknown" if empty.
 */
export function categorizePosition(position: string): string {
  if (!position) return "Unknown";
  const primary = position.split(",")[0].trim();
  return primary || "Unknown";
}

/** Position category colors for badges/chips */
export const POS_COLORS: Record<string, string> = {
  SP: "bg-blue-100 text-blue-800",
  RP: "bg-cyan-100 text-cyan-800",
  C: "bg-purple-100 text-purple-800",
  "1B": "bg-amber-100 text-amber-800",
  "2B": "bg-orange-100 text-orange-800",
  "3B": "bg-yellow-100 text-yellow-800",
  SS: "bg-rose-100 text-rose-800",
  LF: "bg-green-100 text-green-800",
  CF: "bg-emerald-100 text-emerald-800",
  RF: "bg-teal-100 text-teal-800",
  OF: "bg-green-100 text-green-800",
  IF: "bg-amber-100 text-amber-800",
  DH: "bg-gray-100 text-gray-800",
  Unknown: "bg-gray-50 text-gray-500",
};
