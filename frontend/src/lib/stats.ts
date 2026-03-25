/**
 * Shared stat column definitions and formatting for player stats tables.
 *
 * Used by: players/page.tsx, draft-strategy/page.tsx
 */

export const HITTING_COLS: Array<{ key: string; label: string }> = [
  { key: "ab", label: "AB" },
  { key: "r", label: "R" },
  { key: "h", label: "H" },
  { key: "hr", label: "HR" },
  { key: "rbi", label: "RBI" },
  { key: "sb", label: "SB" },
  { key: "avg", label: "AVG" },
  { key: "ops", label: "OPS" },
];

export const PITCHING_COLS: Array<{ key: string; label: string }> = [
  { key: "ip", label: "IP" },
  { key: "w", label: "W" },
  { key: "sv", label: "SV" },
  { key: "hld", label: "HLD" },
  { key: "k", label: "K" },
  { key: "era", label: "ERA" },
  { key: "whip", label: "WHIP" },
  { key: "qs", label: "QS" },
];

/** Rate stats that should display 3 decimal places (e.g. .297) */
const RATE_3 = new Set(["avg", "ops"]);
/** Rate stats that should display 2 decimal places (e.g. 3.42) */
const RATE_2 = new Set(["era", "whip"]);

/**
 * Format a stat value for display.
 * - AVG/OPS: .XXX (3 decimals, strip leading zero)
 * - ERA/WHIP: X.XX (2 decimals)
 * - IP: X.X (1 decimal)
 * - Others: integer
 */
export function formatStat(val: number | undefined | null, key: string): string {
  if (val == null) return "-";
  if (RATE_3.has(key)) return val.toFixed(3).replace(/^0/, "");
  if (RATE_2.has(key)) return val.toFixed(2);
  if (key === "ip") return val.toFixed(1);
  return String(val);
}
